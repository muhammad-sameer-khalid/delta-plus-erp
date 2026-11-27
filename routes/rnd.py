"""RND Module Routes"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session
from auth import module_access_required
from database import execute_query
import logging

logger = logging.getLogger(__name__)

def merge_duplicate_components(components):
    """
    Merge components with identical designator, part_type, part_value, 
    part_description, and footprint. Sum their quantities.
    Recalculates total_price based on merged quantity and unit_price.
    Uses nested loop to check each component against all others.
    """
    if not components:
        return []
    
    logger.info(f"Starting merge with {len(components)} components using nested loop approach")
    
    # List to track which components have been merged
    merged_indices = set()
    result = []
    
    # Outer loop: iterate through each component
    for i, comp1 in enumerate(components):
        if i in merged_indices:
            # This component was already merged into another
            continue
        
        # Start with the current component
        u_price = float(comp1.get('unit_price', 0) or 0)
        qty = int(comp1.get('qty', 0) or 0)
        tot_price = float(comp1.get('total_price', 0) or (u_price * qty))
        
        merged_comp = {
            'designator': comp1.get('designator', ''),
            'part_type': comp1.get('part_type', ''),
            'part_value': comp1.get('part_value', ''),
            'part_description': comp1.get('part_description', ''),
            'footprint': comp1.get('footprint', ''),
            'qty': qty,
            'unit_price': u_price,
            'total_price': tot_price
        }
        
        # Inner loop: check this component against all others
        for j, comp2 in enumerate(components):
            if i == j or j in merged_indices:
                # Skip same component or already merged
                continue
            
            # Check if all 5 fields match (case-insensitive)
            if (comp1.get('designator', '').strip().lower() == comp2.get('designator', '').strip().lower() and
                comp1.get('part_type', '').strip().lower() == comp2.get('part_type', '').strip().lower() and
                comp1.get('part_value', '').strip().lower() == comp2.get('part_value', '').strip().lower() and
                comp1.get('part_description', '').strip().lower() == comp2.get('part_description', '').strip().lower() and
                comp1.get('footprint', '').strip().lower() == comp2.get('footprint', '').strip().lower()):
                
                # Match found! Merge quantities
                logger.info(f"Merging component at index {j} ({comp2.get('designator')}, qty={comp2.get('qty')}) into index {i} (current qty={merged_comp['qty']})")
                merged_comp['qty'] += int(comp2.get('qty', 0) or 0)
                if not merged_comp['unit_price'] and comp2.get('unit_price'):
                    merged_comp['unit_price'] = float(comp2.get('unit_price') or 0)
                merged_comp['total_price'] = round(merged_comp['unit_price'] * merged_comp['qty'], 2)
                merged_indices.add(j)
        
        # Add the merged component to result
        result.append(merged_comp)
        logger.info(f"Component {i} ({merged_comp['designator']}): final qty = {merged_comp['qty']}")
    
    logger.info(f"Merge complete: {len(components)} components reduced to {len(result)} unique components")
    return result


bp = Blueprint('rnd', __name__, url_prefix='/rnd')

@bp.route('/')
@module_access_required('rnd')
def rnd_dashboard():
    """RND dashboard with action cards"""
    user_email = session.get('user_email')
    from auth import can_access_module
    
    # Get accessible modules for navbar
    accessible_modules = []
    for module in ['rnd', 'production', 'supply_chain', 'qc', 'store']:
        if can_access_module(user_email, module):
            accessible_modules.append(module)
    
    return render_template('rnd/dashboard.html',
                         show_nav_menu=True,
                         accessible_modules=accessible_modules)

@bp.route('/generate-bom', methods=['GET', 'POST'])
@module_access_required('rnd')
def generate_bom():
    """Generate a new Bill of Materials"""
    if request.method == 'POST':
        bom_name = request.form.get('bom_name', '').strip()
        bom_type = request.form.get('bom_type', '').strip()  # PCB or Assembly
        tank = request.form.get('tank', '').strip()
        assembly_name = request.form.get('assembly_name', '').strip()
        sub_assembly_name = request.form.get('sub_assembly_name', '').strip()
        currency = request.form.get('currency', 'RMB').strip().upper() or 'RMB'
        
        if not bom_name or not bom_type:
            flash('BOM name and type are required', 'error')
            return redirect(url_for('rnd.generate_bom'))
        
        # Check if BOM already exists
        check_query = "SELECT COUNT(*) as count FROM bom_metadata WHERE bom_name = %s"
        result = execute_query(check_query, (bom_name,), fetch_one=True)
        
        if result and result['count'] > 0:
            flash(f'A BOM with the name "{bom_name}" already exists', 'error')
            return redirect(url_for('rnd.generate_bom'))
        
        # Insert BOM metadata
        insert_query = """
            INSERT INTO bom_metadata (bom_name, bom_type, tank, assembly_name, sub_assembly_name, currency)
            VALUES (%s, %s, %s, %s, %s, %s)
        """
        execute_query(insert_query, (bom_name, bom_type, tank, assembly_name, sub_assembly_name, currency), commit=True)
        
        bom_row = execute_query("SELECT id FROM bom_metadata WHERE bom_name = %s", (bom_name,), fetch_one=True)
        bom_id = bom_row['id'] if bom_row else None
        if not bom_id:
            flash('Failed to create BOM', 'error')
            return redirect(url_for('rnd.generate_bom'))
        
        # Get components from form
        components = []
        i = 0
        while f'designator_{i}' in request.form or f'part_description_{i}' in request.form:
            try:
                unit_price = float(request.form.get(f'unit_price_{i}', 0) or 0)
            except:
                unit_price = 0.0
            qty = int(request.form.get(f'qty_{i}', '') or 1)
            try:
                total_price = float(request.form.get(f'total_price_{i}', 0) or (unit_price * qty))
            except:
                total_price = round(unit_price * qty, 2)
            
            component = {
                'designator': request.form.get(f'designator_{i}', ''),
                'part_type': request.form.get(f'part_type_{i}', ''),
                'part_value': request.form.get(f'part_value_{i}', ''),
                'part_description': request.form.get(f'part_description_{i}', ''),
                'footprint': request.form.get(f'footprint_{i}', ''),
                'qty': qty,
                'unit_price': unit_price,
                'total_price': total_price
            }
            components.append(component)
            i += 1
        
        # Merge duplicate components based on part_value, part_description, and footprint
        merged_components = merge_duplicate_components(components)
        
        # Insert components into bom_items
        if merged_components:
            insert_comp_query = """
                INSERT INTO bom_items (bom_id, designator, part_type, part_value, part_description, footprint, qty, unit_price, total_price)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            params_list = [
                (bom_id, c['designator'], c['part_type'], c['part_value'],
                 c['part_description'], c['footprint'], c['qty'],
                 c.get('unit_price', 0.0), c.get('total_price', 0.0))
                for c in merged_components
            ]
            from database import execute_many
            execute_many(insert_comp_query, params_list)
        
        flash(f'BOM "{bom_name}" created successfully', 'success')
        return redirect(url_for('rnd.display_bom'))
    
    user_email = session.get('user_email')
    from auth import can_access_module
    accessible_modules = []
    for module in ['rnd', 'production', 'supply_chain', 'qc', 'store']:
        if can_access_module(user_email, module):
            accessible_modules.append(module)
    
    return render_template('rnd/generate_bom.html',
                         show_nav_menu=True,
                         accessible_modules=accessible_modules)

@bp.route('/display-bom')
@module_access_required('rnd')
def display_bom():
    """Display list of all BOMs"""
    query = "SELECT * FROM bom_metadata ORDER BY created_at DESC"
    boms = execute_query(query, fetch=True)
    
    user_email = session.get('user_email')
    from auth import can_access_module
    accessible_modules = []
    for module in ['rnd', 'production', 'supply_chain', 'qc', 'store']:
        if can_access_module(user_email, module):
            accessible_modules.append(module)
    
    return render_template('rnd/display_bom.html',
                         boms=boms or [],
                         show_nav_menu=True,
                         accessible_modules=accessible_modules)

@bp.route('/view-bom/<int:bom_id>')
@module_access_required('rnd')
def view_bom(bom_id):
    """View a specific BOM"""
    # Get BOM metadata
    query = "SELECT * FROM bom_metadata WHERE id = %s"
    bom = execute_query(query, (bom_id,), fetch_one=True)
    
    if not bom:
        flash('BOM not found', 'error')
        return redirect(url_for('rnd.display_bom'))
    
    components = execute_query("SELECT * FROM bom_items WHERE bom_id = %s ORDER BY id", (bom_id,), fetch=True) or []
    
    user_email = session.get('user_email')
    from auth import can_access_module
    accessible_modules = []
    for module in ['rnd', 'production', 'supply_chain', 'qc', 'store']:
        if can_access_module(user_email, module):
            accessible_modules.append(module)
    
    return render_template('rnd/view_bom.html',
                         bom=bom,
                         components=components or [],
                         show_nav_menu=True,
                         accessible_modules=accessible_modules)

@bp.route('/edit-bom-form/<int:bom_id>', methods=['GET', 'POST'])
@module_access_required('rnd')
def edit_bom_form(bom_id):
    """Edit a specific BOM with editable table"""
    # Get BOM metadata
    query = "SELECT * FROM bom_metadata WHERE id = %s"
    bom = execute_query(query, (bom_id,), fetch_one=True)
    
    if not bom:
        flash('BOM not found', 'error')
        return redirect(url_for('rnd.edit_bom'))
    
    bom_id = bom['id']
    
    if request.method == 'POST':
        # Update components: delete existing then insert
        execute_query("DELETE FROM bom_items WHERE bom_id = %s", (bom_id,), commit=True)
        
        components = []
        i = 0
        while f'designator_{i}' in request.form or f'part_description_{i}' in request.form:
            try:
                unit_price = float(request.form.get(f'unit_price_{i}', 0) or 0)
            except:
                unit_price = 0.0
            qty = int(request.form.get(f'qty_{i}', 0) or 0)
            try:
                total_price = float(request.form.get(f'total_price_{i}', 0) or (unit_price * qty))
            except:
                total_price = round(unit_price * qty, 2)

            component = {
                'designator': request.form.get(f'designator_{i}', ''),
                'part_type': request.form.get(f'part_type_{i}', ''),
                'part_value': request.form.get(f'part_value_{i}', ''),
                'part_description': request.form.get(f'part_description_{i}', ''),
                'footprint': request.form.get(f'footprint_{i}', ''),
                'qty': qty,
                'unit_price': unit_price,
                'total_price': total_price
            }
            components.append(component)
            i += 1
        
        # Merge duplicate components based on part_value, part_description, and footprint
        merged_components = merge_duplicate_components(components)
        
        if merged_components:
            insert_comp_query = """
                INSERT INTO bom_items (bom_id, designator, part_type, part_value, part_description, footprint, qty, unit_price, total_price)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            params_list = [
                (bom_id, c['designator'], c['part_type'], c['part_value'],
                 c['part_description'], c['footprint'], c['qty'],
                 c.get('unit_price', 0.0), c.get('total_price', 0.0))
                for c in merged_components
            ]
            from database import execute_many
            execute_many(insert_comp_query, params_list)
        
        flash(f'BOM "{bom["bom_name"]}" updated successfully', 'success')
        return redirect(url_for('rnd.edit_bom'))
    
    # GET request - display editable form
    components = execute_query("SELECT * FROM bom_items WHERE bom_id = %s ORDER BY id", (bom_id,), fetch=True) or []
    
    user_email = session.get('user_email')
    from auth import can_access_module
    accessible_modules = []
    for module in ['rnd', 'production', 'supply_chain', 'qc', 'store']:
        if can_access_module(user_email, module):
            accessible_modules.append(module)
    
    return render_template('rnd/edit_bom_form.html',
                         bom=bom,
                         components=components or [],
                         show_nav_menu=True,
                         accessible_modules=accessible_modules)


@bp.route('/edit-bom')
@module_access_required('rnd')
def edit_bom():
    """Edit or delete BOMs"""
    query = "SELECT * FROM bom_metadata ORDER BY created_at DESC"
    boms = execute_query(query, fetch=True)
    
    user_email = session.get('user_email')
    from auth import can_access_module
    accessible_modules = []
    for module in ['rnd', 'production', 'supply_chain', 'qc', 'store']:
        if can_access_module(user_email, module):
            accessible_modules.append(module)
    
    return render_template('rnd/edit_bom.html',
                         boms=boms or [],
                         show_nav_menu=True,
                         accessible_modules=accessible_modules)

@bp.route('/delete-bom/<int:bom_id>', methods=['POST'])
@module_access_required('rnd')
def delete_bom(bom_id):
    """Delete a BOM (bom_items cascade or explicit delete, then metadata)"""
    bom = execute_query("SELECT id FROM bom_metadata WHERE id = %s", (bom_id,), fetch_one=True)
    if bom:
        execute_query("DELETE FROM bom_items WHERE bom_id = %s", (bom_id,), commit=True)
        execute_query("DELETE FROM bom_metadata WHERE id = %s", (bom_id,), commit=True)
        flash('BOM deleted successfully', 'success')
    else:
        flash('BOM not found', 'error')
    return redirect(url_for('rnd.edit_bom'))

@bp.route('/api/boms')
@module_access_required('rnd')
def get_boms_api():
    """API endpoint to get all BOMs"""
    query = "SELECT id, bom_name, bom_type, tank, assembly_name, sub_assembly_name, currency FROM bom_metadata ORDER BY bom_name"
    boms = execute_query(query, fetch=True)
    return jsonify({'success': True, 'boms': boms or []})

@bp.route('/api/bom/<int:bom_id>/components')
@module_access_required('rnd')
def get_bom_components_api(bom_id):
    """API endpoint to get BOM components"""
    # Get BOM metadata
    query = "SELECT * FROM bom_metadata WHERE id = %s"
    bom = execute_query(query, (bom_id,), fetch_one=True)
    
    if not bom:
        return jsonify({'success': False, 'message': 'BOM not found'})
    
    components = execute_query("SELECT * FROM bom_items WHERE bom_id = %s ORDER BY id", (bom_id,), fetch=True) or []
    return jsonify({'success': True, 'components': components})
