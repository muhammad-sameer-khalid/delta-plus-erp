"""Production Module Routes"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session
from auth import module_access_required, can_access_module
from database import execute_query, execute_many
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

bp = Blueprint('production', __name__, url_prefix='/production')

def _accessible_modules():
    user_email = session.get('user_email')
    accessible = []
    for module in ['rnd', 'production', 'supply_chain', 'qc', 'store']:
        if can_access_module(user_email, module, 'tanks'):
            accessible.append(module)
    return accessible

@bp.route('/')
@module_access_required('production')
def production_dashboard():
    """Production dashboard"""
    return render_template('production/dashboard.html',
                         show_nav_menu=True,
                         accessible_modules=_accessible_modules())

@bp.route('/generate-demand', methods=['GET', 'POST'])
@bp.route('/generate-import-demand', methods=['GET', 'POST'])
@module_access_required('production')
def generate_demand():
    """Generate Import demand note"""
    if request.method == 'POST':
        demand_no = int(request.form.get('demand_no', 0) or 0)
        department = request.form.get('department', '').strip()
        required_date = request.form.get('required_date', '').strip()
        demanded_by = request.form.get('demanded_by', '').strip()
        demand_date = datetime.now().strftime('%Y-%m-%d')
        
        if not demand_no or not department or not required_date or not demanded_by:
            flash('All demand note header fields are required', 'error')
            return redirect(url_for('production.generate_demand'))

        # Check if demand number already exists
        check_query = "SELECT COUNT(*) as count FROM demand_notes WHERE demand_no = %s"
        result = execute_query(check_query, (demand_no,), fetch_one=True)
        if result and result['count'] > 0:
            flash(f'Demand note #{demand_no} already exists', 'error')
            return redirect(url_for('production.generate_demand'))
        
        # Get components from form
        components = []
        i = 0
        while f'part_description_{i}' in request.form:
            part_desc = request.form.get(f'part_description_{i}', '').strip()
            qty = int(request.form.get(f'qty_{i}', 0) or 0)
            try:
                unit_price = float(request.form.get(f'unit_price_{i}', 0) or 0)
            except:
                unit_price = 0.0
            try:
                total_price = float(request.form.get(f'total_price_{i}', 0) or (unit_price * qty))
            except:
                total_price = round(unit_price * qty, 2)
            
            if part_desc and qty > 0:
                components.append({
                    'sr_no': i + 1,
                    'part_type': request.form.get(f'part_type_{i}', ''),
                    'part_value': request.form.get(f'part_value_{i}', ''),
                    'part_description': part_desc,
                    'footprint': request.form.get(f'footprint_{i}', ''),
                    'qty': qty,
                    'unit_price': unit_price,
                    'total_price': total_price,
                    'persons_demand': request.form.get(f'persons_demand_{i}', ''),
                    'project': request.form.get(f'project_{i}', ''),
                    'remarks': request.form.get(f'remarks_{i}', '')
                })
            i += 1
        
        # Validation: A demand note without components cannot be created
        if not components:
            flash('A Demand Note without components cannot be created. Please add at least one component.', 'error')
            return redirect(url_for('production.generate_demand'))

        # Insert demand note metadata with demand_type = 'import'
        insert_query = """
            INSERT INTO demand_notes 
            (demand_no, demand_date, department, required_date, demanded_by, approved, demand_type)
            VALUES (%s, %s, %s, %s, %s, FALSE, 'import')
        """
        execute_query(insert_query, (demand_no, demand_date, department, required_date, demanded_by), commit=True)
        
        demand_row = execute_query("SELECT id FROM demand_notes WHERE demand_no = %s", (demand_no,), fetch_one=True)
        demand_id = demand_row['id'] if demand_row else None
        if not demand_id:
            flash('Failed to create demand note', 'error')
            return redirect(url_for('production.generate_demand'))
        
        # Merge duplicate components based on BOM fields + project + remarks
        merged_components = []
        for comp in components:
            key = (
                comp['part_type'].strip().lower(),
                comp['part_value'].strip().lower(),
                comp['part_description'].strip().lower(),
                comp['footprint'].strip().lower(),
                comp['project'].strip().lower(),
                comp['remarks'].strip().lower()
            )
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
                    merged['qty'] += comp['qty']
                    if not merged['unit_price'] and comp['unit_price']:
                        merged['unit_price'] = comp['unit_price']
                    merged['total_price'] = round(merged['qty'] * merged['unit_price'], 2)
                    found = True
                    break
            if not found:
                merged_components.append(comp.copy())
        
        for idx, comp in enumerate(merged_components):
            comp['sr_no'] = idx + 1
        
        insert_comp_query = """
            INSERT INTO demand_items
            (demand_id, sr_no, part_type, part_value, part_description, footprint, qty, unit_price, total_price, persons_demand, project, remarks)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        params_list = [
            (demand_id, c['sr_no'], c['part_type'], c['part_value'], c['part_description'],
             c['footprint'], c['qty'], c['unit_price'], c['total_price'], c['persons_demand'], c['project'], c['remarks'])
            for c in merged_components
        ]
        execute_many(insert_comp_query, params_list)
        
        flash(f'Import Demand note #{demand_no} created successfully', 'success')
        return redirect(url_for('production.display_demand'))
    
    current_date = datetime.now().strftime('%Y-%m-%d')
    return render_template('production/generate_demand.html',
                         show_nav_menu=True,
                         accessible_modules=_accessible_modules(),
                         current_date=current_date)

@bp.route('/generate-local-demand', methods=['GET', 'POST'])
@module_access_required('production')
def generate_local_demand():
    """Generate Local demand note"""
    if request.method == 'POST':
        demand_no = int(request.form.get('demand_no', 0) or 0)
        department = request.form.get('department', '').strip()
        required_date = request.form.get('required_date', '').strip()
        demanded_by = request.form.get('demanded_by', '').strip()
        demand_date = datetime.now().strftime('%Y-%m-%d')
        
        if not demand_no or not department or not required_date or not demanded_by:
            flash('All demand note header fields are required', 'error')
            return redirect(url_for('production.generate_local_demand'))

        check_query = "SELECT COUNT(*) as count FROM demand_notes WHERE demand_no = %s"
        result = execute_query(check_query, (demand_no,), fetch_one=True)
        if result and result['count'] > 0:
            flash(f'Demand note #{demand_no} already exists', 'error')
            return redirect(url_for('production.generate_local_demand'))

        # Get components from form
        components = []
        i = 0
        while f'part_description_{i}' in request.form:
            desc = request.form.get(f'part_description_{i}', '').strip()
            qty = int(request.form.get(f'qty_{i}', 0) or 0)
            try:
                unit_price = float(request.form.get(f'unit_price_{i}', 0) or 0)
            except:
                unit_price = 0.0
            try:
                total_price = float(request.form.get(f'total_price_{i}', 0) or (unit_price * qty))
            except:
                total_price = round(unit_price * qty, 2)
            
            if desc and qty > 0:
                components.append({
                    'sr_no': i + 1,
                    'part_type': request.form.get(f'part_type_{i}', ''),
                    'part_value': request.form.get(f'part_value_{i}', ''),
                    'part_description': desc,
                    'footprint': request.form.get(f'footprint_{i}', ''),
                    'qty': qty,
                    'unit_price': unit_price,
                    'total_price': total_price,
                    'persons_demand': request.form.get(f'persons_demand_{i}', ''),
                    'project': request.form.get(f'project_{i}', ''),
                    'remarks': request.form.get(f'remarks_{i}', '')
                })
            i += 1

        if not components:
            flash('A Demand Note without components cannot be created. Please add at least one component.', 'error')
            return redirect(url_for('production.generate_local_demand'))

        insert_query = """
            INSERT INTO demand_notes 
            (demand_no, demand_date, department, required_date, demanded_by, approved, demand_type)
            VALUES (%s, %s, %s, %s, %s, FALSE, 'local')
        """
        execute_query(insert_query, (demand_no, demand_date, department, required_date, demanded_by), commit=True)
        
        demand_row = execute_query("SELECT id FROM demand_notes WHERE demand_no = %s", (demand_no,), fetch_one=True)
        demand_id = demand_row['id'] if demand_row else None
        if not demand_id:
            flash('Failed to create demand note', 'error')
            return redirect(url_for('production.generate_local_demand'))

        insert_comp_query = """
            INSERT INTO demand_items
            (demand_id, sr_no, part_type, part_value, part_description, footprint, qty, unit_price, total_price, persons_demand, project, remarks)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        params_list = [
            (demand_id, c['sr_no'], c['part_type'], c['part_value'], c['part_description'],
             c['footprint'], c['qty'], c['unit_price'], c['total_price'], c['persons_demand'], c['project'], c['remarks'])
            for c in components
        ]
        execute_many(insert_comp_query, params_list)
        
        flash(f'Local Demand note #{demand_no} created successfully', 'success')
        return redirect(url_for('production.display_local_demands'))
    
    current_date = datetime.now().strftime('%Y-%m-%d')
    return render_template('production/generate_local_demand.html',
                         show_nav_menu=True,
                         accessible_modules=_accessible_modules(),
                         current_date=current_date)

@bp.route('/display-demand')
@bp.route('/display-import-demands')
@module_access_required('production')
def display_demand():
    """Display all import demand notes"""
    query = "SELECT * FROM demand_notes WHERE demand_type = 'import' OR demand_type IS NULL ORDER BY created_at DESC"
    demands = execute_query(query, fetch=True)
    return render_template('production/display_demand.html',
                         demands=demands or [],
                         show_nav_menu=True,
                         accessible_modules=_accessible_modules())

@bp.route('/display-local-demands')
@module_access_required('production')
def display_local_demands():
    """Display all local demand notes"""
    query = "SELECT * FROM demand_notes WHERE demand_type = 'local' ORDER BY created_at DESC"
    demands = execute_query(query, fetch=True)
    return render_template('production/display_local_demands.html',
                         demands=demands or [],
                         show_nav_menu=True,
                         accessible_modules=_accessible_modules())

@bp.route('/view-demand/<int:demand_no>')
@module_access_required('production')
def view_demand(demand_no):
    """View a specific demand note"""
    query = "SELECT * FROM demand_notes WHERE demand_no = %s"
    demand = execute_query(query, (demand_no,), fetch_one=True)
    if not demand:
        flash('Demand note not found', 'error')
        return redirect(url_for('production.display_demand'))
    
    demand_id = demand.get('id')
    components = execute_query(
        "SELECT * FROM demand_items WHERE demand_id = %s ORDER BY sr_no",
        (demand_id,), fetch=True
    ) if demand_id else []
    
    return render_template('production/view_demand.html',
                         demand=demand,
                         components=components or [],
                         show_nav_menu=True,
                         accessible_modules=_accessible_modules())

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
        
        insert_query = """
            INSERT INTO qc_products 
            (pcb_assembly_name, qty, is_pcb, part_type, part_value, part_description, footprint, project_number)
            VALUES (%s, %s, TRUE, %s, %s, %s, %s, %s)
        """
        execute_query(insert_query, (product_name, qty, part_type, part_value, product_name, footprint, project_number), commit=True)
        
        notif_query = """
            INSERT INTO notifications 
            (recipient_role, message, notification_type, related_id)
            VALUES (%s, %s, %s, %s)
        """
        message = f'New product "{product_name}" (Qty: {qty}) sent for quality check'
        execute_query(notif_query, ('qc manager', message, 'qc_product', 0), commit=True)
        
        flash(f'Product "{product_name}" sent to QC successfully', 'success')
        return redirect(url_for('production.production_dashboard'))
    
    return render_template('production/send_to_qc.html',
                         show_nav_menu=True,
                         accessible_modules=_accessible_modules())

@bp.route('/approve-demand/<int:demand_no>', methods=['POST'])
def approve_demand(demand_no):
    """Send demand note for approval (starts approval workflow)"""
    demand = execute_query("SELECT demand_type FROM demand_notes WHERE demand_no = %s", (demand_no,), fetch_one=True)
    update_query = """
        UPDATE demand_notes 
        SET approval_status = 'pending_gm'
        WHERE demand_no = %s
    """
    execute_query(update_query, (demand_no,), commit=True)
    
    notif_query = """
        INSERT INTO notifications 
        (recipient_role, message, notification_type, related_id)
        VALUES (%s, %s, %s, %s)
    """
    dtype_label = 'Local' if demand and demand.get('demand_type') == 'local' else 'Import'
    message = f'{dtype_label} Demand Note #{demand_no} requires your approval'
    execute_query(notif_query, ('general manager', message, 'demand_approval', demand_no), commit=True)
    
    flash(f'Demand note #{demand_no} sent for GM approval', 'success')
    if demand and demand.get('demand_type') == 'local':
        return redirect(url_for('production.display_local_demands'))
    return redirect(url_for('production.display_demand'))

@bp.route('/delete-demand/<int:demand_no>', methods=['POST'])
@module_access_required('production')
def delete_demand(demand_no):
    """Delete a demand note and its components"""
    try:
        demand = execute_query("SELECT id, demand_type FROM demand_notes WHERE demand_no = %s", (demand_no,), fetch_one=True)
        if demand:
            execute_query("DELETE FROM demand_items WHERE demand_id = %s", (demand['id'],), commit=True)
            execute_query("DELETE FROM demand_notes WHERE demand_no = %s", (demand_no,), commit=True)
            flash(f'Demand note #{demand_no} deleted successfully', 'success')
            if demand.get('demand_type') == 'local':
                return redirect(url_for('production.display_local_demands'))
    except Exception as e:
        logger.error(f"Error deleting demand note {demand_no}: {e}")
        flash(f'Error deleting demand note: {str(e)}', 'error')
    
    return redirect(url_for('production.display_demand'))
