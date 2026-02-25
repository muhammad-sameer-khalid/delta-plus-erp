"""Supply Chain Module Routes - Complete Rewrite"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from auth import module_access_required
from database import execute_query, table_exists
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

bp = Blueprint('supply_chain', __name__, url_prefix='/supply-chain')

def get_accessible_modules():
    """Helper to get accessible modules for current user"""
    user_email = session.get('user_email')
    from auth import can_access_module
    accessible_modules = []
    for module in ['rnd', 'production', 'supply_chain', 'qc', 'store']:
        if can_access_module(user_email, module):
            accessible_modules.append(module)
    return accessible_modules

def deduplicate_po_components(components):
    """
    Deduplicate components based on part_value, part_description, and footprint.
    Merge quantities and total prices for duplicates.
    """
    merged = {}
    
    for comp in components:
        # Create key from part_value, part_description, footprint (only 3 fields)
        key = (
            str(comp.get('part_value', '')).strip().lower(),
            str(comp.get('part_description', '')).strip().lower(),
            str(comp.get('footprint', '')).strip().lower()
        )
        
        if key in merged:
            # Merge: add quantity and total price
            merged[key]['qty'] += comp.get('qty', 0)
            merged[key]['total_price'] += comp.get('total_price', 0)
            # Track multiple source demand notes
            source = comp.get('source_demand_no')
            if source and source not in merged[key]['source_demand_nos']:
                merged[key]['source_demand_nos'].append(source)
        else:
            # First occurrence
            merged[key] = {
                'part_type': comp.get('part_type', ''),
                'part_value': comp.get('part_value', ''),
                'part_description': comp.get('part_description', ''),
                'footprint': comp.get('footprint', ''),
                'qty': comp.get('qty', 0),
                'unit_price': comp.get('unit_price', 0),
                'total_price': comp.get('total_price', 0),
                'project': comp.get('project', ''),
                'source_demand_nos': [comp.get('source_demand_no')] if comp.get('source_demand_no') else []
            }
    
    return list(merged.values())

# ============================================
# Dashboard
# ============================================

@bp.route('/')
@module_access_required('supply_chain')
def supply_chain_dashboard():
    """Supply chain dashboard with action cards"""
    return render_template('supply_chain/dashboard.html',
                         show_nav_menu=True,
                         accessible_modules=get_accessible_modules())

# ============================================
# Demands - View approved demand notes
# ============================================

@bp.route('/demands')
@module_access_required('supply_chain')
def demands():
    """View all approved demand notes (approved by Director)"""
    query = "SELECT * FROM demand_notes WHERE approved = TRUE AND supply_chain_archived = FALSE ORDER BY created_at DESC"
    demands = execute_query(query, fetch=True)
    
    return render_template('supply_chain/demands.html',
                         demands=demands or [],
                         show_nav_menu=True,
                         accessible_modules=get_accessible_modules())

@bp.route('/archive-demand/<int:demand_no>', methods=['POST'])
@module_access_required('supply_chain')
def archive_demand(demand_no):
    """Archive (hide) a demand note from Supply Chain view"""
    query = "UPDATE demand_notes SET supply_chain_archived = TRUE WHERE demand_no = %s"
    execute_query(query, (demand_no,), commit=True)
    
    flash(f'Demand note #{demand_no} removed from list', 'success')
    return redirect(url_for('supply_chain.demands'))

@bp.route('/view-demand/<int:demand_no>')
@module_access_required('supply_chain')
def view_demand(demand_no):
    """View full demand note details with components"""
    # Get demand metadata
    demand_query = "SELECT * FROM demand_notes WHERE demand_no = %s"
    demand = execute_query(demand_query, (demand_no,), fetch_one=True)
    
    if not demand:
        flash('Demand note not found', 'error')
        return redirect(url_for('supply_chain.demands'))
    
    # Get components from demand_items
    demand_id = demand.get('id')
    components = execute_query(
        "SELECT * FROM demand_items WHERE demand_id = %s ORDER BY sr_no",
        (demand_id,), fetch=True
    ) if demand_id else []
    
    return render_template('supply_chain/view_demand.html',
                         demand=demand,
                         components=components or [],
                         show_nav_menu=True,
                         accessible_modules=get_accessible_modules())

# ============================================
# Generate PO - Multi-step workflow
# ============================================

@bp.route('/generate-po')
@module_access_required('supply_chain')
def generate_po():
    """Step 1: Enter PO number"""
    # Clear any existing PO session data
    session.pop('po_draft', None)
    
    return render_template('supply_chain/generate_po_step1.html',
                         show_nav_menu=True,
                         accessible_modules=get_accessible_modules())

@bp.route('/generate-po/select-demand', methods=['GET', 'POST'])
@module_access_required('supply_chain')
def generate_po_select_demand():
    """Step 2: Select demand note from dropdown"""
    if request.method == 'POST':
        po_number = request.form.get('po_number', '').strip()
        currency = request.form.get('currency', 'RMB').strip().upper() or 'RMB'
        
        if not po_number:
            flash('Please enter a PO number', 'error')
            return redirect(url_for('supply_chain.generate_po'))
        
        # Check if PO already exists
        check_query = "SELECT COUNT(*) as count FROM po_metadata WHERE po_number = %s"
        result = execute_query(check_query, (po_number,), fetch_one=True)
        if result and result['count'] > 0:
            flash(f'PO {po_number} already exists', 'error')
            return redirect(url_for('supply_chain.generate_po'))
        
        # Initialize PO draft in session
        if 'po_draft' not in session:
            session['po_draft'] = {
                'po_number': po_number,
                'currency': currency,
                'components': []
            }
        else:
            session['po_draft']['po_number'] = po_number
            session['po_draft']['currency'] = currency
        
        session.modified = True
    
    # GET or after POST - show the form
    if 'po_draft' not in session:
        flash('PO session expired. Please start over.', 'error')
        return redirect(url_for('supply_chain.generate_po'))
    
    po_number = session['po_draft']['po_number']
    
    # Get all approved demands (excluding archived)
    query = "SELECT demand_no FROM demand_notes WHERE approved = TRUE AND supply_chain_archived = FALSE ORDER BY demand_no DESC"
    demands = execute_query(query, fetch=True)
    demand_numbers = [d['demand_no'] for d in demands] if demands else []
    
    return render_template('supply_chain/generate_po_step2.html',
                         po_number=po_number,
                         demand_numbers=demand_numbers,
                         show_nav_menu=True,
                         accessible_modules=get_accessible_modules())

@bp.route('/generate-po/add-components', methods=['GET', 'POST'])
@module_access_required('supply_chain')
def generate_po_add_components():
    """Step 3: Show components from selected demand with checkboxes and price fields"""
    if request.method == 'POST':
        demand_no = request.form.get('demand_no', '').strip()
        
        if not demand_no:
            flash('Please select a demand note', 'error')
            return redirect(url_for('supply_chain.generate_po'))
        
        if 'po_draft' not in session:
            flash('PO session expired. Please start over.', 'error')
            return redirect(url_for('supply_chain.generate_po'))
        
        # Store the selected demand_no in session for GET requests
        session['current_demand_no'] = demand_no
        session.modified = True
    
    # GET request - check if we have a demand_no in session
    if request.method == 'GET':
        if 'po_draft' not in session or 'current_demand_no' not in session:
            flash('Please select a demand note first.', 'error')
            return redirect(url_for('supply_chain.generate_po_select_demand'))
        demand_no = session['current_demand_no']
    
    # Get components from demand_items
    demand_row = execute_query("SELECT id FROM demand_notes WHERE demand_no = %s", (demand_no,), fetch_one=True)
    if not demand_row:
        flash(f'Demand note {demand_no} not found', 'error')
        return redirect(url_for('supply_chain.generate_po_select_demand'))
    components = execute_query("SELECT * FROM demand_items WHERE demand_id = %s ORDER BY sr_no", (demand_row['id'],), fetch=True)
    if not components:
        flash(f'No components found in demand note {demand_no}', 'error')
        return redirect(url_for('supply_chain.generate_po_select_demand'))
    
    return render_template('supply_chain/generate_po_step3.html',
                         demand_no=demand_no,
                         components=components,
                         po_number=session['po_draft']['po_number'],
                         currency=session['po_draft'].get('currency', 'RMB'),
                         show_nav_menu=True,
                         accessible_modules=get_accessible_modules())

@bp.route('/generate-po/save-components', methods=['POST'])
@module_access_required('supply_chain')
def generate_po_save_components():
    """Step 4: Save selected components with prices to PO draft"""
    if 'po_draft' not in session:
        flash('PO session expired. Please start over.', 'error')
        return redirect(url_for('supply_chain.generate_po'))
    
    demand_no = request.form.get('demand_no')
    selected_indices = request.form.getlist('selected')
    
    # Get components from demand_items
    demand_row = execute_query("SELECT id FROM demand_notes WHERE demand_no = %s", (demand_no,), fetch_one=True)
    if not demand_row:
        flash(f'Demand note {demand_no} not found', 'error')
        return redirect(url_for('supply_chain.generate_po_review'))
    all_components = execute_query("SELECT * FROM demand_items WHERE demand_id = %s ORDER BY sr_no", (demand_row['id'],), fetch=True) or []
    
    # Process selected components with prices
    for idx_str in selected_indices:
        idx = int(idx_str)
        if idx < len(all_components):
            comp = all_components[idx]
            unit_price_str = request.form.get(f'unit_price_{idx}', '0')
            
            try:
                unit_price = float(unit_price_str)
            except:
                unit_price = 0
            
            qty = comp.get('qty', 0)
            total_price = unit_price * qty
            
            # Add to PO draft with source tracking
            session['po_draft']['components'].append({
                'part_type': comp.get('part_type', ''),
                'part_value': comp.get('part_value', ''),
                'part_description': comp.get('part_description', ''),
                'footprint': comp.get('footprint', ''),
                'qty': qty,
                'unit_price': unit_price,
                'total_price': total_price,
                'project': comp.get('project', ''),
                'source_demand_no': demand_no  # Track which demand this came from
            })
    
    session.modified = True
    
    # Don't deduplicate yet - keep source tracking for removal functionality
    # Deduplication happens at review display and final save
    
    flash(f'Components from demand note {demand_no} added to PO', 'success')
    
    # Show review page
    return redirect(url_for('supply_chain.generate_po_review'))

@bp.route('/generate-po/review')
@module_access_required('supply_chain')
def generate_po_review():
    """Step 5: Review PO draft - option to add more demands or finalize"""
    if 'po_draft' not in session or not session['po_draft'].get('components'):
        flash('No components in PO draft', 'error')
        return redirect(url_for('supply_chain.generate_po'))
    
    po_draft = session['po_draft']
    components = po_draft['components']
    
    # Group components by source demand note
    demand_groups = {}
    for comp in components:
        source = comp.get('source_demand_no', 'Unknown')
        if source not in demand_groups:
            demand_groups[source] = []
        demand_groups[source].append(comp)
    
    # Deduplicate components for display
    deduplicated_components = deduplicate_po_components(components)
    
    # Get all approved demands for adding more (excluding archived)
    query = "SELECT demand_no FROM demand_notes WHERE approved = TRUE AND supply_chain_archived = FALSE ORDER BY demand_no DESC"
    demands = execute_query(query, fetch=True)
    demand_numbers = [d['demand_no'] for d in demands] if demands else []
    
    return render_template('supply_chain/generate_po_review.html',
                         po_draft=po_draft,
                         demand_groups=demand_groups,
                         deduplicated_components=deduplicated_components,
                         demand_numbers=demand_numbers,
                         currency=po_draft.get('currency', 'RMB'),
                         show_nav_menu=True,
                         accessible_modules=get_accessible_modules())

@bp.route('/generate-po/remove-demand/<demand_no>', methods=['POST'])
@module_access_required('supply_chain')
def generate_po_remove_demand(demand_no):
    """Remove all components from a specific demand note from PO draft"""
    if 'po_draft' not in session:
        return jsonify({'success': False, 'message': 'PO session expired'})
    
    # Remove all components with matching source_demand_no
    original_count = len(session['po_draft']['components'])
    session['po_draft']['components'] = [
        comp for comp in session['po_draft']['components']
        if str(comp.get('source_demand_no', '')) != str(demand_no)
    ]
    removed_count = original_count - len(session['po_draft']['components'])
    session.modified = True
    
    logger.info(f"Removed {removed_count} components from demand {demand_no} from PO draft")
    
    # Check if any components remain
    if not session['po_draft']['components']:
        flash(f'Demand note #{demand_no} removed from PO. PO draft is now empty.', 'warning')
        return redirect(url_for('supply_chain.generate_po_select_demand'))
    
    flash(f'Demand note #{demand_no} removed from PO ({removed_count} components)', 'success')
    return redirect(url_for('supply_chain.generate_po_review'))

@bp.route('/generate-po/supplier-form')
@module_access_required('supply_chain')
def generate_po_supplier_form():
    """Step 6: Enter supplier information"""
    if 'po_draft' not in session or not session['po_draft'].get('components'):
        flash('No components in PO draft', 'error')
        return redirect(url_for('supply_chain.generate_po'))
    
    return render_template('supply_chain/generate_po_supplier.html',
                         po_number=session['po_draft']['po_number'],
                         currency=session['po_draft'].get('currency', 'RMB'),
                         show_nav_menu=True,
                         accessible_modules=get_accessible_modules())

@bp.route('/generate-po/finalize', methods=['POST'])
@module_access_required('supply_chain')
def generate_po_finalize():
    """Step 7: Save PO to database, send components to QC, and show formatted PO"""
    if 'po_draft' not in session:
        flash('PO session expired. Please start over.', 'error')
        return redirect(url_for('supply_chain.generate_po'))
    
    # Get supplier info
    supplier_name = request.form.get('name', '').strip()
    supplier_company = request.form.get('company', '').strip()
    supplier_address = request.form.get('address', '').strip()
    supplier_telephone = request.form.get('telephone', '').strip()
    supplier_postal_code = request.form.get('postal_code', '').strip()
    
    if not all([supplier_name, supplier_company, supplier_address, supplier_telephone, supplier_postal_code]):
        flash('All supplier fields are required', 'error')
        return redirect(url_for('supply_chain.generate_po_supplier_form'))
    
    po_draft = session['po_draft']
    po_number = po_draft['po_number']
    currency = po_draft.get('currency', 'RMB')
    raw_components = po_draft['components']
    
    # Deduplicate components before saving
    components = deduplicate_po_components(raw_components)
    logger.info(f"Deduplicated {len(raw_components)} components to {len(components)} unique components")
    
    # Insert PO metadata
    insert_meta_query = """
        INSERT INTO po_metadata 
        (po_number, supplier_name, supplier_company, supplier_address, 
         supplier_telephone, supplier_postal_code, currency)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """
    execute_query(insert_meta_query, 
                 (po_number, supplier_name, supplier_company, supplier_address,
                  supplier_telephone, supplier_postal_code, currency),
                 commit=True)
    
    po_row = execute_query("SELECT id FROM po_metadata WHERE po_number = %s", (po_number,), fetch_one=True)
    po_id = po_row['id'] if po_row else None
    if not po_id:
        flash('Failed to create PO', 'error')
        return redirect(url_for('supply_chain.generate_po_review'))
    
    # Insert components into po_items
    if components:
        from database import execute_many
        insert_comps_query = """
            INSERT INTO po_items
            (po_id, part_type, part_value, part_description, footprint, qty, unit_price, total_price, project)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        comp_data = [
            (po_id, c['part_type'], c['part_value'], c['part_description'], c['footprint'],
             c['qty'], c['unit_price'], c['total_price'], c['project'])
            for c in components
        ]
        execute_many(insert_comps_query, comp_data, commit=True)
        
        # Send all components to QC for quality checking
        qc_insert_query = """
            INSERT INTO qc_components 
            (part_type, part_value, part_description, footprint, po_no, qty, project_number)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """
        qc_data = [
            (c['part_type'], c['part_value'], c['part_description'], c['footprint'],
             po_number, c['qty'], c['project'])
            for c in components
        ]
        execute_many(qc_insert_query, qc_data, commit=True)
        logger.info(f"Sent {len(components)} components from PO {po_number} to QC")
    
    # Clear session
    session.pop('po_draft', None)
    session.modified = True
    
    flash(f'Purchase Order {po_number} created successfully and sent to QC!', 'success')
    return redirect(url_for('supply_chain.view_po', po_number=po_number))

# ============================================
# Display PO - List all POs
# ============================================

@bp.route('/display-po')
@module_access_required('supply_chain')
def display_po():
    """List all purchase orders"""
    query = "SELECT * FROM po_metadata ORDER BY created_at DESC"
    pos = execute_query(query, fetch=True)
    
    return render_template('supply_chain/display_po.html',
                         pos=pos or [],
                         show_nav_menu=True,
                         accessible_modules=get_accessible_modules())

# ============================================
# View PO - Formatted A4 layout for printing
# ============================================

@bp.route('/view-po/<po_number>')
@module_access_required('supply_chain')
def view_po(po_number):
    """View formatted PO with A4 print layout"""
    # Get PO metadata
    meta_query = "SELECT * FROM po_metadata WHERE po_number = %s"
    po_meta = execute_query(meta_query, (po_number,), fetch_one=True)
    
    if not po_meta:
        flash('Purchase order not found', 'error')
        return redirect(url_for('supply_chain.display_po'))
    
    # Get components from po_items
    po_id = po_meta.get('id')
    items = execute_query("SELECT * FROM po_items WHERE po_id = %s ORDER BY id", (po_id,), fetch=True) if po_id else []
    
    # Calculate project subtotals
    project_subtotals = {}
    for item in items:
        project = item.get('project', 'N/A')
        if project not in project_subtotals:
            project_subtotals[project] = 0
        project_subtotals[project] += float(item.get('total_price', 0))
    
    # Calculate grand total
    grand_total = sum(project_subtotals.values())
    
    # Current date
    current_date = datetime.now().strftime('%Y-%m-%d')
    
    return render_template('supply_chain/view_po.html',
                         po=po_meta,
                         items=items or [],
                         project_subtotals=project_subtotals,
                         grand_total=grand_total,
                         current_date=current_date,
                         currency=po_meta.get('currency', 'RMB'),
                         show_nav_menu=True,
                         accessible_modules=get_accessible_modules())


@bp.route('/delete-po/<po_number>', methods=['POST'])
@module_access_required('supply_chain')
def delete_po(po_number):
    """Delete a Purchase Order and its items."""
    try:
        # Get PO ID first to delete items
        po = execute_query("SELECT id FROM po_metadata WHERE po_number = %s", (po_number,), fetch_one=True)
        if po:
            po_id = po['id']
            execute_query("DELETE FROM po_items WHERE po_id = %s", (po_id,), commit=True)
            execute_query("DELETE FROM qc_components WHERE po_no = %s", (po_number,), commit=True)
            execute_query("DELETE FROM po_metadata WHERE id = %s", (po_id,), commit=True)
            flash(f'Purchase Order {po_number} deleted successfully.', 'success')
        else:
            flash(f'Purchase Order {po_number} not found.', 'error')
    except Exception as e:
        logger.error(f"Error deleting PO {po_number}: {e}")
        flash(f'Error deleting Purchase Order: {str(e)}', 'error')
    
    return redirect(url_for('supply_chain.display_po'))

