"""Production Module Routes"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session
from auth import module_access_required
from database import execute_query
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

bp = Blueprint('production', __name__, url_prefix='/production')

@bp.route('/')
@module_access_required('production')
def production_dashboard():
    """Production dashboard"""
    user_email = session.get('user_email')
    from auth import can_access_module
    accessible_modules = []
    for module in ['rnd', 'production', 'supply_chain', 'qc', 'store']:
        if can_access_module(user_email, module):
            accessible_modules.append(module)
    
    return render_template('production/dashboard.html',
                         show_nav_menu=True,
                         accessible_modules=accessible_modules)

@bp.route('/generate-demand', methods=['GET', 'POST'])
@module_access_required('production')
def generate_demand():
    """Generate demand note"""
    if request.method == 'POST':
        demand_no = int(request.form.get('demand_no', 0))
        department = request.form.get('department', '')
        required_date = request.form.get('required_date', '')
        demanded_by = request.form.get('demanded_by', '')
        demand_date = datetime.now().strftime('%Y-%m-%d')
        
        # Check if demand number already exists
        check_query = "SELECT COUNT(*) as count FROM demand_notes WHERE demand_no = %s"
        result = execute_query(check_query, (demand_no,), fetch_one=True)
        
        if result and result['count'] > 0:
            flash(f'Demand note #{demand_no} already exists', 'error')
            return redirect(url_for('production.generate_demand'))
        
        # Insert demand note metadata
        insert_query = """
            INSERT INTO demand_notes 
            (demand_no, demand_date, department, required_date, demanded_by, approved)
            VALUES (%s, %s, %s, %s, %s, FALSE)
        """
        execute_query(insert_query, (demand_no, demand_date, department, required_date, demanded_by), commit=True)
        
        # Get demand_id for new demand
        demand_row = execute_query("SELECT id FROM demand_notes WHERE demand_no = %s", (demand_no,), fetch_one=True)
        demand_id = demand_row['id'] if demand_row else None
        if not demand_id:
            flash('Failed to create demand note', 'error')
            return redirect(url_for('production.generate_demand'))
        
        # Get components from form
        components = []
        i = 0
        while f'part_description_{i}' in request.form:
            component = {
                'sr_no': i + 1,  # Auto-increment sr#
                'part_type': request.form.get(f'part_type_{i}', ''),
                'part_value': request.form.get(f'part_value_{i}', ''),
                'part_description': request.form.get(f'part_description_{i}', ''),
                'footprint': request.form.get(f'footprint_{i}', ''),
                'qty': int(request.form.get(f'qty_{i}', 0)),
                'persons_demand': request.form.get(f'persons_demand_{i}', ''),
                'project': request.form.get(f'project_{i}', ''),
                'remarks': request.form.get(f'remarks_{i}', '')
            }
            components.append(component)
            i += 1
        
        # Merge duplicate components based on all BOM fields + project + remarks
        merged_components = []
        for comp in components:
            # Create key for matching
            key = (
                comp['part_type'].strip().lower(),
                comp['part_value'].strip().lower(),
                comp['part_description'].strip().lower(),
                comp['footprint'].strip().lower(),
                comp['project'].strip().lower(),
                comp['remarks'].strip().lower()
            )
            
            # Check if already exists in merged list
            found = False
            for merged in merged_components:
                merged_key = (
                    merged['part_type'].strip().lower(),
                    merged['part_value'].strip().lower(),
                    merged['part_description'].strip().lower(),
                    merged['footprint'].strip().lower(),
                    merged['project'].strip().lower(),
                    merged['remarks'].strip().lower()
                )
                
                if key == merged_key:
                    # Merge: add quantities
                    merged['qty'] += comp['qty']
                    found = True
                    break
            
            if not found:
                merged_components.append(comp.copy())
        
        # Renumber sr_no after merging
        for idx, comp in enumerate(merged_components):
            comp['sr_no'] = idx + 1
        
        # Insert merged components into demand_items
        if merged_components:
            insert_comp_query = """
                INSERT INTO demand_items
                (demand_id, sr_no, part_type, part_value, part_description, footprint, qty, persons_demand, project, remarks)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            params_list = [
                (demand_id, c['sr_no'], c['part_type'], c['part_value'], c['part_description'],
                 c['footprint'], c['qty'], c['persons_demand'], c['project'], c['remarks'])
                for c in merged_components
            ]
            from database import execute_many
            execute_many(insert_comp_query, params_list)
        
        flash(f'Demand note #{demand_no} created successfully', 'success')
        return redirect(url_for('production.display_demand'))
    
    user_email = session.get('user_email')
    from auth import can_access_module
    accessible_modules = []
    for module in ['rnd', 'production', 'supply_chain', 'qc', 'store']:
        if can_access_module(user_email, module):
            accessible_modules.append(module)
    
    current_date = datetime.now().strftime('%Y-%m-%d')
    
    return render_template('production/generate_demand.html',
                         show_nav_menu=True,
                         accessible_modules=accessible_modules,
                         current_date=current_date)

@bp.route('/display-demand')
@module_access_required('production')
def display_demand():
    """Display all demand notes"""
    query = "SELECT * FROM demand_notes ORDER BY created_at DESC"
    demands = execute_query(query, fetch=True)
    
    user_email = session.get('user_email')
    from auth import can_access_module
    accessible_modules = []
    for module in ['rnd', 'production', 'supply_chain', 'qc', 'store']:
        if can_access_module(user_email, module):
            accessible_modules.append(module)
    
    return render_template('production/display_demand.html',
                         demands=demands or [],
                         show_nav_menu=True,
                         accessible_modules=accessible_modules)

@bp.route('/view-demand/<int:demand_no>')
@module_access_required('production')
def view_demand(demand_no):
    """View a specific demand note"""
    # Get demand metadata
    query = "SELECT * FROM demand_notes WHERE demand_no = %s"
    demand = execute_query(query, (demand_no,), fetch_one=True)
    
    if not demand:
        flash('Demand note not found', 'error')
        return redirect(url_for('production.display_demand'))
    
    # Get components from demand_items
    demand_id = demand.get('id')
    components = execute_query(
        "SELECT * FROM demand_items WHERE demand_id = %s ORDER BY sr_no",
        (demand_id,), fetch=True
    ) if demand_id else []
    
    user_email = session.get('user_email')
    from auth import can_access_module
    accessible_modules = []
    for module in ['rnd', 'production', 'supply_chain', 'qc', 'store']:
        if can_access_module(user_email, module):
            accessible_modules.append(module)
    
    return render_template('production/view_demand.html',
                         demand=demand,
                         components=components or [],
                         show_nav_menu=True,
                         accessible_modules=accessible_modules)


@bp.route('/send-to-qc', methods=['GET', 'POST'])
@module_access_required('production')
def send_to_qc():
    """Send product to QC"""
    if request.method == 'POST':
        product_name = request.form.get('product_name', '')
        part_type = request.form.get('part_type', '')
        part_value = request.form.get('part_value', '')
        footprint = request.form.get('footprint', '')
        project_number = request.form.get('project_number', '')
        qty = int(request.form.get('qty', 0))
        
        # Add to QC products table
        insert_query = """
            INSERT INTO qc_products 
            (pcb_assembly_name, qty, is_pcb, part_type, part_value, part_description, footprint, project_number)
            VALUES (%s, %s, TRUE, %s, %s, %s, %s, %s)
        """
        execute_query(insert_query, (product_name, qty, part_type, part_value, product_name, footprint, project_number), commit=True)
        
        # Create notification for QC managers
        notif_query = """
            INSERT INTO notifications 
            (recipient_role, message, notification_type, related_id)
            VALUES (%s, %s, %s, %s)
        """
        message = f'New product "{product_name}" (Qty: {qty}) sent for quality check'
        execute_query(notif_query, ('qc manager', message, 'qc_product', 0), commit=True)
        
        flash(f'Product "{product_name}" sent to QC successfully', 'success')
        return redirect(url_for('production.production_dashboard'))
    
    user_email = session.get('user_email')
    from auth import can_access_module
    accessible_modules = []
    for module in ['rnd', 'production', 'supply_chain', 'qc', 'store']:
        if can_access_module(user_email, module):
            accessible_modules.append(module)
    
    return render_template('production/send_to_qc.html',
                         show_nav_menu=True,
                         accessible_modules=accessible_modules)

@bp.route('/approve-demand/<int:demand_no>', methods=['POST'])
def approve_demand(demand_no):
    """Send demand note for approval (starts approval workflow)"""
    # Update approval status to pending_gm (first stage of approval now)
    update_query = """
        UPDATE demand_notes 
        SET approval_status = 'pending_gm'
        WHERE demand_no = %s
    """
    execute_query(update_query, (demand_no,), commit=True)
    
    # Send notification to General Manager
    notif_query = """
        INSERT INTO notifications 
        (recipient_role, message, notification_type, related_id)
        VALUES (%s, %s, %s, %s)
    """
    message = f'Demand Note #{demand_no} requires your approval'
    execute_query(notif_query, ('general manager', message, 'demand_approval', demand_no), commit=True)
    
    flash(f'Demand note #{demand_no} sent for GM approval', 'success')
    return redirect(url_for('production.display_demand'))

@bp.route('/delete-demand/<int:demand_no>', methods=['POST'])
@module_access_required('production')
def delete_demand(demand_no):
    """Delete a demand note and its components"""
    try:
        demand_row = execute_query("SELECT id FROM demand_notes WHERE demand_no = %s", (demand_no,), fetch_one=True)
        if demand_row:
            execute_query("DELETE FROM demand_items WHERE demand_id = %s", (demand_row['id'],), commit=True)
        execute_query("DELETE FROM demand_notes WHERE demand_no = %s", (demand_no,), commit=True)
        
        flash(f'Demand note #{demand_no} deleted successfully', 'success')
    except Exception as e:
        logger.error(f"Error deleting demand note {demand_no}: {e}")
        flash(f'Error deleting demand note: {str(e)}', 'error')
    
    return redirect(url_for('production.display_demand'))

