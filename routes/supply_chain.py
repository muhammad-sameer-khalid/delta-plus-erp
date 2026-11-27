"""Supply Chain Module Routes - Tanks (Import & Local Workflows)"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from auth import module_access_required, can_delete_items
from database import execute_query, execute_many, table_exists
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
        if can_access_module(user_email, module, 'tanks'):
            accessible_modules.append(module)
    return accessible_modules

def deduplicate_po_components(components):
    """
    Deduplicate components based on part_value, part_description, and footprint.
    Merge quantities and total prices for duplicates.
    """
    merged = {}
    for comp in components:
        key = (
            str(comp.get('part_value', '')).strip().lower(),
            str(comp.get('part_description', '')).strip().lower(),
            str(comp.get('footprint', '')).strip().lower()
        )
        
        if key in merged:
            merged[key]['qty'] += comp.get('qty', 0)
            merged[key]['total_price'] += comp.get('total_price', 0)
            source = comp.get('source_demand_no')
            if source and source not in merged[key]['source_demand_nos']:
                merged[key]['source_demand_nos'].append(source)
        else:
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
@module_access_required('supply_chain', 'tanks')
def supply_chain_dashboard():
    """Supply chain dashboard with action cards"""
    return render_template('supply_chain/dashboard.html',
                         show_nav_menu=True,
                         accessible_modules=get_accessible_modules())

# ============================================
# Demands - Import & Local Views
# ============================================

@bp.route('/demands')
@module_access_required('supply_chain', 'tanks')
def demands():
    """View approved import demand notes"""
    query = """
        SELECT * FROM demand_notes 
        WHERE approved = TRUE AND supply_chain_archived = FALSE 
          AND (demand_type = 'import' OR demand_type IS NULL) 
        ORDER BY created_at DESC
    """
    demands_list = execute_query(query, fetch=True)
    return render_template('supply_chain/demands.html',
                         demands=demands_list or [],
                         is_local=False,
                         show_nav_menu=True,
                         accessible_modules=get_accessible_modules())

@bp.route('/local-demands')
@module_access_required('supply_chain', 'tanks')
def local_demands():
    """View approved local demand notes"""
    query = """
        SELECT * FROM demand_notes 
        WHERE approved = TRUE AND supply_chain_archived = FALSE 
          AND demand_type = 'local' 
        ORDER BY created_at DESC
    """
    demands_list = execute_query(query, fetch=True)
    return render_template('supply_chain/demands.html',
                         demands=demands_list or [],
                         is_local=True,
                         show_nav_menu=True,
                         accessible_modules=get_accessible_modules())

@bp.route('/archive-demand/<int:demand_no>', methods=['POST'])
@module_access_required('supply_chain', 'tanks')
def archive_demand(demand_no):
    """Archive (hide) a demand note from Supply Chain view"""
    execute_query("UPDATE demand_notes SET supply_chain_archived = TRUE WHERE demand_no = %s", (demand_no,), commit=True)
    flash(f'Demand note #{demand_no} removed from list', 'success')
    demand = execute_query("SELECT demand_type FROM demand_notes WHERE demand_no = %s", (demand_no,), fetch_one=True)
    if demand and demand.get('demand_type') == 'local':
        return redirect(url_for('supply_chain.local_demands'))
    return redirect(url_for('supply_chain.demands'))

@bp.route('/view-demand/<int:demand_no>')
@module_access_required('supply_chain', 'tanks')
def view_demand(demand_no):
    """View full demand note details with components"""
    demand = execute_query("SELECT * FROM demand_notes WHERE demand_no = %s", (demand_no,), fetch_one=True)
    if not demand:
        flash('Demand note not found', 'error')
        return redirect(url_for('supply_chain.demands'))
    
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
# Generate Import Purchase Order Workflow
# ============================================

@bp.route('/generate-po')
@module_access_required('supply_chain', 'tanks')
def generate_po():
    """Step 1: Enter Import PO number & Currency"""
    session.pop('po_draft', None)
    session.pop('current_demand_no', None)
    return render_template('supply_chain/generate_po_step1.html',
                         is_local=False,
                         show_nav_menu=True,
                         accessible_modules=get_accessible_modules())

@bp.route('/generate-po/select-demand', methods=['GET', 'POST'])
@module_access_required('supply_chain', 'tanks')
def generate_po_select_demand():
    """Step 2: Select approved import demand note"""
    if request.method == 'POST':
        po_number = request.form.get('po_number', '').strip()
        currency = request.form.get('currency', 'RMB').strip().upper() or 'RMB'
        
        if not po_number:
            flash('Please enter a PO number', 'error')
            return redirect(url_for('supply_chain.generate_po'))
        
        result = execute_query("SELECT COUNT(*) as count FROM po_metadata WHERE po_number = %s", (po_number,), fetch_one=True)
        if result and result['count'] > 0:
            flash(f'PO {po_number} already exists', 'error')
            return redirect(url_for('supply_chain.generate_po'))
        
        session['po_draft'] = {
            'po_number': po_number,
            'currency': currency,
            'po_type': 'import',
            'components': []
        }
        session.modified = True
    
    if 'po_draft' not in session or session['po_draft'].get('po_type') != 'import':
        flash('PO session expired. Please start over.', 'error')
        return redirect(url_for('supply_chain.generate_po'))
    
    po_number = session['po_draft']['po_number']
    query = """
        SELECT demand_no FROM demand_notes 
        WHERE approved = TRUE AND supply_chain_archived = FALSE 
          AND (demand_type = 'import' OR demand_type IS NULL) 
        ORDER BY demand_no DESC
    """
    demands = execute_query(query, fetch=True)
    demand_numbers = [d['demand_no'] for d in demands] if demands else []
    
    return render_template('supply_chain/generate_po_step2.html',
                         po_number=po_number,
                         demand_numbers=demand_numbers,
                         is_local=False,
                         show_nav_menu=True,
                         accessible_modules=get_accessible_modules())

@bp.route('/generate-po/add-components', methods=['GET', 'POST'])
@module_access_required('supply_chain', 'tanks')
def generate_po_add_components():
    """Step 3: Select components from import demand with editable unit prices"""
    if request.method == 'POST':
        demand_no = request.form.get('demand_no', '').strip()
        if not demand_no:
            flash('Please select a demand note', 'error')
            return redirect(url_for('supply_chain.generate_po_select_demand'))
        if 'po_draft' not in session:
            flash('PO session expired. Please start over.', 'error')
            return redirect(url_for('supply_chain.generate_po'))
        session['current_demand_no'] = demand_no
        session.modified = True
    
    if request.method == 'GET':
        if 'po_draft' not in session or 'current_demand_no' not in session:
            flash('Please select a demand note first.', 'error')
            return redirect(url_for('supply_chain.generate_po_select_demand'))
        demand_no = session['current_demand_no']
    
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
                         is_local=False,
                         show_nav_menu=True,
                         accessible_modules=get_accessible_modules())

@bp.route('/generate-po/save-components', methods=['POST'])
@module_access_required('supply_chain', 'tanks')
def generate_po_save_components():
    """Step 4: Save selected components to import PO draft"""
    if 'po_draft' not in session:
        flash('PO session expired. Please start over.', 'error')
        return redirect(url_for('supply_chain.generate_po'))
    
    demand_no = request.form.get('demand_no')
    selected_indices = request.form.getlist('selected')
    
    demand_row = execute_query("SELECT id FROM demand_notes WHERE demand_no = %s", (demand_no,), fetch_one=True)
    if not demand_row:
        flash(f'Demand note {demand_no} not found', 'error')
        return redirect(url_for('supply_chain.generate_po_review'))
        
    all_components = execute_query("SELECT * FROM demand_items WHERE demand_id = %s ORDER BY sr_no", (demand_row['id'],), fetch=True) or []
    
    for idx_str in selected_indices:
        idx = int(idx_str)
        if idx < len(all_components):
            comp = all_components[idx]
            unit_price_str = request.form.get(f'unit_price_{idx}', '0')
            try:
                unit_price = float(unit_price_str)
            except:
                unit_price = 0.0
            
            qty = comp.get('qty', 0)
            total_price = round(unit_price * qty, 2)
            
            session['po_draft']['components'].append({
                'part_type': comp.get('part_type', ''),
                'part_value': comp.get('part_value', ''),
                'part_description': comp.get('part_description', ''),
                'footprint': comp.get('footprint', ''),
                'qty': qty,
                'unit_price': unit_price,
                'total_price': total_price,
                'project': comp.get('project', ''),
                'source_demand_no': demand_no
            })
    
    session.modified = True
    flash(f'Components from demand note {demand_no} added to PO', 'success')
    return redirect(url_for('supply_chain.generate_po_review'))

@bp.route('/generate-po/review')
@module_access_required('supply_chain', 'tanks')
def generate_po_review():
    """Step 5: Review Import PO draft"""
    if 'po_draft' not in session or not session['po_draft'].get('components'):
        flash('No components in PO draft', 'error')
        return redirect(url_for('supply_chain.generate_po'))
    
    po_draft = session['po_draft']
    components = po_draft['components']
    
    demand_groups = {}
    for comp in components:
        source = comp.get('source_demand_no', 'Unknown')
        if source not in demand_groups:
            demand_groups[source] = []
        demand_groups[source].append(comp)
    
    deduplicated_components = deduplicate_po_components(components)
    
    query = """
        SELECT demand_no FROM demand_notes 
        WHERE approved = TRUE AND supply_chain_archived = FALSE 
          AND (demand_type = 'import' OR demand_type IS NULL) 
        ORDER BY demand_no DESC
    """
    demands = execute_query(query, fetch=True)
    demand_numbers = [d['demand_no'] for d in demands] if demands else []
    
    return render_template('supply_chain/generate_po_review.html',
                         po_draft=po_draft,
                         demand_groups=demand_groups,
                         deduplicated_components=deduplicated_components,
                         demand_numbers=demand_numbers,
                         currency=po_draft.get('currency', 'RMB'),
                         is_local=False,
                         show_nav_menu=True,
                         accessible_modules=get_accessible_modules())

@bp.route('/generate-po/remove-demand/<demand_no>', methods=['POST'])
@module_access_required('supply_chain', 'tanks')
def generate_po_remove_demand(demand_no):
    """Remove all components from a specific demand note from import PO draft"""
    if 'po_draft' not in session:
        return redirect(url_for('supply_chain.generate_po'))
    
    session['po_draft']['components'] = [
        comp for comp in session['po_draft']['components']
        if str(comp.get('source_demand_no', '')) != str(demand_no)
    ]
    session.modified = True
    
    if not session['po_draft']['components']:
        flash(f'Demand note #{demand_no} removed from PO. Draft is now empty.', 'warning')
        return redirect(url_for('supply_chain.generate_po_select_demand'))
    
    flash(f'Demand note #{demand_no} removed from PO', 'success')
    return redirect(url_for('supply_chain.generate_po_review'))

@bp.route('/generate-po/supplier-form')
@module_access_required('supply_chain', 'tanks')
def generate_po_supplier_form():
    """Step 6: Supplier info form for Import PO (address & postal code NOT required)"""
    if 'po_draft' not in session or not session['po_draft'].get('components'):
        flash('No components in PO draft', 'error')
        return redirect(url_for('supply_chain.generate_po'))
    
    return render_template('supply_chain/generate_po_supplier.html',
                         po_number=session['po_draft']['po_number'],
                         currency=session['po_draft'].get('currency', 'RMB'),
                         is_local=False,
                         show_nav_menu=True,
                         accessible_modules=get_accessible_modules())

@bp.route('/generate-po/finalize', methods=['POST'])
@module_access_required('supply_chain', 'tanks')
def generate_po_finalize():
    """Step 7: Finalize Import PO (address and postal_code are optional)"""
    if 'po_draft' not in session:
        flash('PO session expired. Please start over.', 'error')
        return redirect(url_for('supply_chain.generate_po'))
    
    supplier_name = request.form.get('name', '').strip()
    supplier_company = request.form.get('company', '').strip()
    supplier_address = request.form.get('address', '').strip()
    supplier_telephone = request.form.get('telephone', '').strip()
    supplier_postal_code = request.form.get('postal_code', '').strip()
    
    # Address and postal code are NOT required per requirement!
    if not all([supplier_name, supplier_company, supplier_telephone]):
        flash('Supplier Name, Company, and Telephone are required', 'error')
        return redirect(url_for('supply_chain.generate_po_supplier_form'))
    
    po_draft = session['po_draft']
    po_number = po_draft['po_number']
    currency = po_draft.get('currency', 'RMB')
    raw_components = po_draft['components']
    
    components = deduplicate_po_components(raw_components)
    
    insert_meta_query = """
        INSERT INTO po_metadata 
        (po_number, supplier_name, supplier_company, supplier_address, 
         supplier_telephone, supplier_postal_code, currency, po_type)
        VALUES (%s, %s, %s, %s, %s, %s, %s, 'import')
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
    
    if components:
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
        
        qc_insert_query = """
            INSERT INTO qc_components 
            (part_type, part_value, part_description, footprint, po_no, qty, project_number, po_type)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 'import')
        """
        qc_data = [
            (c['part_type'], c['part_value'], c['part_description'], c['footprint'],
             po_number, c['qty'], c['project'])
            for c in components
        ]
        execute_many(qc_insert_query, qc_data, commit=True)
    
    session.pop('po_draft', None)
    session.pop('current_demand_no', None)
    session.modified = True
    
    flash(f'Import Purchase Order {po_number} created successfully and sent to QC!', 'success')
    return redirect(url_for('supply_chain.view_po', po_number=po_number))

# ============================================
# Generate Local Purchase Order Workflow
# ============================================

@bp.route('/generate-local-po')
@module_access_required('supply_chain', 'tanks')
def generate_local_po():
    """Step 1: Enter Local PO number (Currency fixed to RS)"""
    session.pop('po_draft_local', None)
    session.pop('current_demand_no_local', None)
    return render_template('supply_chain/generate_po_step1.html',
                         is_local=True,
                         show_nav_menu=True,
                         accessible_modules=get_accessible_modules())

@bp.route('/generate-local-po/select-demand', methods=['GET', 'POST'])
@module_access_required('supply_chain', 'tanks')
def generate_local_po_select_demand():
    """Step 2: Select approved local demand note"""
    if request.method == 'POST':
        po_number = request.form.get('po_number', '').strip()
        if not po_number:
            flash('Please enter a PO number', 'error')
            return redirect(url_for('supply_chain.generate_local_po'))
        
        result = execute_query("SELECT COUNT(*) as count FROM po_metadata WHERE po_number = %s", (po_number,), fetch_one=True)
        if result and result['count'] > 0:
            flash(f'PO {po_number} already exists', 'error')
            return redirect(url_for('supply_chain.generate_local_po'))
        
        session['po_draft_local'] = {
            'po_number': po_number,
            'currency': 'RS',
            'po_type': 'local',
            'components': []
        }
        session.modified = True
    
    if 'po_draft_local' not in session:
        flash('Local PO session expired. Please start over.', 'error')
        return redirect(url_for('supply_chain.generate_local_po'))
    
    po_number = session['po_draft_local']['po_number']
    query = """
        SELECT demand_no FROM demand_notes 
        WHERE approved = TRUE AND supply_chain_archived = FALSE 
          AND demand_type = 'local' 
        ORDER BY demand_no DESC
    """
    demands = execute_query(query, fetch=True)
    demand_numbers = [d['demand_no'] for d in demands] if demands else []
    
    return render_template('supply_chain/generate_po_step2.html',
                         po_number=po_number,
                         demand_numbers=demand_numbers,
                         is_local=True,
                         show_nav_menu=True,
                         accessible_modules=get_accessible_modules())

@bp.route('/generate-local-po/add-components', methods=['GET', 'POST'])
@module_access_required('supply_chain', 'tanks')
def generate_local_po_add_components():
    """Step 3: Select components from local demand with editable unit prices (RS)"""
    if request.method == 'POST':
        demand_no = request.form.get('demand_no', '').strip()
        if not demand_no:
            flash('Please select a demand note', 'error')
            return redirect(url_for('supply_chain.generate_local_po_select_demand'))
        if 'po_draft_local' not in session:
            flash('Local PO session expired. Please start over.', 'error')
            return redirect(url_for('supply_chain.generate_local_po'))
        session['current_demand_no_local'] = demand_no
        session.modified = True
    
    if request.method == 'GET':
        if 'po_draft_local' not in session or 'current_demand_no_local' not in session:
            flash('Please select a demand note first.', 'error')
            return redirect(url_for('supply_chain.generate_local_po_select_demand'))
        demand_no = session['current_demand_no_local']
    
    demand_row = execute_query("SELECT id FROM demand_notes WHERE demand_no = %s", (demand_no,), fetch_one=True)
    if not demand_row:
        flash(f'Demand note {demand_no} not found', 'error')
        return redirect(url_for('supply_chain.generate_local_po_select_demand'))
        
    components = execute_query("SELECT * FROM demand_items WHERE demand_id = %s ORDER BY sr_no", (demand_row['id'],), fetch=True)
    if not components:
        flash(f'No components found in demand note {demand_no}', 'error')
        return redirect(url_for('supply_chain.generate_local_po_select_demand'))
    
    return render_template('supply_chain/generate_po_step3.html',
                         demand_no=demand_no,
                         components=components,
                         po_number=session['po_draft_local']['po_number'],
                         currency='RS',
                         is_local=True,
                         show_nav_menu=True,
                         accessible_modules=get_accessible_modules())

@bp.route('/generate-local-po/save-components', methods=['POST'])
@module_access_required('supply_chain', 'tanks')
def generate_local_po_save_components():
    """Step 4: Save selected components to local PO draft"""
    if 'po_draft_local' not in session:
        flash('Local PO session expired. Please start over.', 'error')
        return redirect(url_for('supply_chain.generate_local_po'))
    
    demand_no = request.form.get('demand_no')
    selected_indices = request.form.getlist('selected')
    
    demand_row = execute_query("SELECT id FROM demand_notes WHERE demand_no = %s", (demand_no,), fetch_one=True)
    if not demand_row:
        flash(f'Demand note {demand_no} not found', 'error')
        return redirect(url_for('supply_chain.generate_local_po_review'))
        
    all_components = execute_query("SELECT * FROM demand_items WHERE demand_id = %s ORDER BY sr_no", (demand_row['id'],), fetch=True) or []
    
    for idx_str in selected_indices:
        idx = int(idx_str)
        if idx < len(all_components):
            comp = all_components[idx]
            unit_price_str = request.form.get(f'unit_price_{idx}', '0')
            try:
                unit_price = float(unit_price_str)
            except:
                unit_price = 0.0
            
            qty = comp.get('qty', 0)
            total_price = round(unit_price * qty, 2)
            
            session['po_draft_local']['components'].append({
                'part_type': comp.get('part_type', ''),
                'part_value': comp.get('part_value', ''),
                'part_description': comp.get('part_description', ''),
                'footprint': comp.get('footprint', ''),
                'qty': qty,
                'unit_price': unit_price,
                'total_price': total_price,
                'project': comp.get('project', ''),
                'source_demand_no': demand_no
            })
    
    session.modified = True
    flash(f'Components from local demand note {demand_no} added to Local PO', 'success')
    return redirect(url_for('supply_chain.generate_local_po_review'))

@bp.route('/generate-local-po/review')
@module_access_required('supply_chain', 'tanks')
def generate_local_po_review():
    """Step 5: Review Local PO draft"""
    if 'po_draft_local' not in session or not session['po_draft_local'].get('components'):
        flash('No components in Local PO draft', 'error')
        return redirect(url_for('supply_chain.generate_local_po'))
    
    po_draft = session['po_draft_local']
    components = po_draft['components']
    
    demand_groups = {}
    for comp in components:
        source = comp.get('source_demand_no', 'Unknown')
        if source not in demand_groups:
            demand_groups[source] = []
        demand_groups[source].append(comp)
    
    deduplicated_components = deduplicate_po_components(components)
    
    query = """
        SELECT demand_no FROM demand_notes 
        WHERE approved = TRUE AND supply_chain_archived = FALSE 
          AND demand_type = 'local' 
        ORDER BY demand_no DESC
    """
    demands = execute_query(query, fetch=True)
    demand_numbers = [d['demand_no'] for d in demands] if demands else []
    
    return render_template('supply_chain/generate_po_review.html',
                         po_draft=po_draft,
                         demand_groups=demand_groups,
                         deduplicated_components=deduplicated_components,
                         demand_numbers=demand_numbers,
                         currency='RS',
                         is_local=True,
                         show_nav_menu=True,
                         accessible_modules=get_accessible_modules())

@bp.route('/generate-local-po/remove-demand/<demand_no>', methods=['POST'])
@module_access_required('supply_chain', 'tanks')
def generate_local_po_remove_demand(demand_no):
    """Remove all components from a specific local demand note from draft"""
    if 'po_draft_local' not in session:
        return redirect(url_for('supply_chain.generate_local_po'))
    
    session['po_draft_local']['components'] = [
        comp for comp in session['po_draft_local']['components']
        if str(comp.get('source_demand_no', '')) != str(demand_no)
    ]
    session.modified = True
    
    if not session['po_draft_local']['components']:
        flash(f'Demand note #{demand_no} removed from Local PO. Draft is now empty.', 'warning')
        return redirect(url_for('supply_chain.generate_local_po_select_demand'))
    
    flash(f'Demand note #{demand_no} removed from Local PO', 'success')
    return redirect(url_for('supply_chain.generate_local_po_review'))

@bp.route('/generate-local-po/supplier-form')
@module_access_required('supply_chain', 'tanks')
def generate_local_po_supplier_form():
    """Step 6: Supplier info form for Local PO (ALL fields optional)"""
    if 'po_draft_local' not in session or not session['po_draft_local'].get('components'):
        flash('No components in Local PO draft', 'error')
        return redirect(url_for('supply_chain.generate_local_po'))
    
    return render_template('supply_chain/generate_po_supplier.html',
                         po_number=session['po_draft_local']['po_number'],
                         currency='RS',
                         is_local=True,
                         show_nav_menu=True,
                         accessible_modules=get_accessible_modules())

@bp.route('/generate-local-po/finalize', methods=['POST'])
@module_access_required('supply_chain', 'tanks')
def generate_local_po_finalize():
    """Step 7: Finalize Local PO (nothing is required in supplier details!)"""
    if 'po_draft_local' not in session:
        flash('Local PO session expired. Please start over.', 'error')
        return redirect(url_for('supply_chain.generate_local_po'))
    
    supplier_name = request.form.get('name', '').strip()
    supplier_company = request.form.get('company', '').strip()
    supplier_address = request.form.get('address', '').strip()
    supplier_telephone = request.form.get('telephone', '').strip()
    supplier_postal_code = request.form.get('postal_code', '').strip()
    
    po_draft = session['po_draft_local']
    po_number = po_draft['po_number']
    raw_components = po_draft['components']
    
    components = deduplicate_po_components(raw_components)
    
    insert_meta_query = """
        INSERT INTO po_metadata 
        (po_number, supplier_name, supplier_company, supplier_address, 
         supplier_telephone, supplier_postal_code, currency, po_type)
        VALUES (%s, %s, %s, %s, %s, %s, 'RS', 'local')
    """
    execute_query(insert_meta_query, 
                 (po_number, supplier_name, supplier_company, supplier_address,
                  supplier_telephone, supplier_postal_code),
                 commit=True)
    
    po_row = execute_query("SELECT id FROM po_metadata WHERE po_number = %s", (po_number,), fetch_one=True)
    po_id = po_row['id'] if po_row else None
    if not po_id:
        flash('Failed to create Local PO', 'error')
        return redirect(url_for('supply_chain.generate_local_po_review'))
    
    if components:
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
        
        qc_insert_query = """
            INSERT INTO qc_components 
            (part_type, part_value, part_description, footprint, po_no, qty, project_number, po_type)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 'local')
        """
        qc_data = [
            (c['part_type'], c['part_value'], c['part_description'], c['footprint'],
             po_number, c['qty'], c['project'])
            for c in components
        ]
        execute_many(qc_insert_query, qc_data, commit=True)
    
    session.pop('po_draft_local', None)
    session.pop('current_demand_no_local', None)
    session.modified = True
    
    flash(f'Local Purchase Order {po_number} created successfully and sent to QC!', 'success')
    return redirect(url_for('supply_chain.view_local_po', po_number=po_number))

# ============================================
# Display & View POs
# ============================================

@bp.route('/display-po')
@module_access_required('supply_chain', 'tanks')
def display_po():
    """List Import purchase orders"""
    query = "SELECT * FROM po_metadata WHERE po_type = 'import' OR po_type IS NULL ORDER BY created_at DESC"
    pos = execute_query(query, fetch=True)
    return render_template('supply_chain/display_po.html',
                         pos=pos or [],
                         is_local=False,
                         show_nav_menu=True,
                         accessible_modules=get_accessible_modules())

@bp.route('/display-local-po')
@module_access_required('supply_chain', 'tanks')
def display_local_po():
    """List Local purchase orders"""
    query = "SELECT * FROM po_metadata WHERE po_type = 'local' ORDER BY created_at DESC"
    pos = execute_query(query, fetch=True)
    return render_template('supply_chain/display_po.html',
                         pos=pos or [],
                         is_local=True,
                         show_nav_menu=True,
                         accessible_modules=get_accessible_modules())

@bp.route('/view-po/<po_number>')
@module_access_required('supply_chain', 'tanks')
def view_po(po_number):
    """View formatted Import PO with A4 print layout"""
    po_meta = execute_query("SELECT * FROM po_metadata WHERE po_number = %s", (po_number,), fetch_one=True)
    if not po_meta:
        flash('Purchase order not found', 'error')
        return redirect(url_for('supply_chain.display_po'))
    
    po_id = po_meta.get('id')
    items = execute_query("SELECT * FROM po_items WHERE po_id = %s ORDER BY id", (po_id,), fetch=True) if po_id else []
    
    project_subtotals = {}
    for item in items:
        project = item.get('project', 'N/A')
        if project not in project_subtotals:
            project_subtotals[project] = 0
        project_subtotals[project] += float(item.get('total_price', 0))
    
    grand_total = sum(project_subtotals.values())
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

@bp.route('/view-local-po/<po_number>')
@module_access_required('supply_chain', 'tanks')
def view_local_po(po_number):
    """View formatted Local PO with specified A4 print layout"""
    po_meta = execute_query("SELECT * FROM po_metadata WHERE po_number = %s", (po_number,), fetch_one=True)
    if not po_meta:
        flash('Local purchase order not found', 'error')
        return redirect(url_for('supply_chain.display_local_po'))
    
    po_id = po_meta.get('id')
    items = execute_query("SELECT * FROM po_items WHERE po_id = %s ORDER BY id", (po_id,), fetch=True) if po_id else []
    
    net_amount = sum(float(item.get('total_price', 0) or 0) for item in items)
    gst_amount = round(net_amount * 0.17, 2)
    grand_total = round(net_amount + gst_amount, 2)
    current_date = datetime.now().strftime('%Y-%m-%d')
    
    return render_template('supply_chain/view_local_po.html',
                         po=po_meta,
                         items=items or [],
                         net_amount=net_amount,
                         gst_amount=gst_amount,
                         grand_total=grand_total,
                         current_date=current_date,
                         show_nav_menu=True,
                         accessible_modules=get_accessible_modules())

@bp.route('/delete-po/<po_number>', methods=['POST'])
@module_access_required('supply_chain', 'tanks')
def delete_po(po_number):
    """Delete a Purchase Order and its items."""
    try:
        po = execute_query("SELECT id, po_type FROM po_metadata WHERE po_number = %s", (po_number,), fetch_one=True)
        if po:
            po_id = po['id']
            po_type = po.get('po_type', 'import')
            execute_query("DELETE FROM po_items WHERE po_id = %s", (po_id,), commit=True)
            execute_query("DELETE FROM qc_components WHERE po_no = %s", (po_number,), commit=True)
            execute_query("DELETE FROM po_metadata WHERE id = %s", (po_id,), commit=True)
            flash(f'Purchase Order {po_number} deleted successfully.', 'success')
            if po_type == 'local':
                return redirect(url_for('supply_chain.display_local_po'))
        else:
            flash(f'Purchase Order {po_number} not found.', 'error')
    except Exception as e:
        logger.error(f"Error deleting PO {po_number}: {e}")
        flash(f'Error deleting Purchase Order: {str(e)}', 'error')
    
    return redirect(url_for('supply_chain.display_po'))
