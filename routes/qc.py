"""Quality Control Module Routes"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from auth import module_access_required
from database import execute_query
import logging

logger = logging.getLogger(__name__)

bp = Blueprint('qc', __name__, url_prefix='/qc')

@bp.route('/')
@module_access_required('qc')
def qc_dashboard():
    """QC dashboard"""
    return render_template('qc/dashboard.html',
                         show_nav_menu=True,
                         accessible_modules=_get_accessible_modules())

def _get_accessible_modules():
    """Helper to get accessible modules for current user"""
    user_email = session.get('user_email')
    from auth import can_access_module
    return [m for m in ['rnd', 'production', 'supply_chain', 'qc', 'store'] if can_access_module(user_email, m)]

@bp.route('/components')
@module_access_required('qc')
def components():
    """List of POs that have components pending QC"""
    query = """
        SELECT po_no, COUNT(*) as component_count 
        FROM qc_components 
        WHERE po_no IS NOT NULL AND po_no != ''
        GROUP BY po_no 
        ORDER BY po_no DESC
    """
    po_list = execute_query(query, fetch=True)
    
    return render_template('qc/components.html',
                         po_list=po_list or [],
                         show_nav_menu=True,
                         accessible_modules=_get_accessible_modules())

@bp.route('/components/po/<po_number>')
@module_access_required('qc')
def po_components(po_number):
    """View all components for a specific PO - click component to enter good qty and send to store"""
    query = "SELECT * FROM qc_components WHERE po_no = %s ORDER BY id"
    components = execute_query(query, (po_number,), fetch=True)
    
    if not components:
        flash(f'No components pending for PO {po_number}', 'warning')
        return redirect(url_for('qc.components'))
    
    return render_template('qc/po_components.html',
                         po_number=po_number,
                         components=components,
                         show_nav_menu=True,
                         accessible_modules=_get_accessible_modules())

@bp.route('/products')
@module_access_required('qc')
def products():
    """View products pending QC"""
    query = "SELECT * FROM qc_products ORDER BY created_at DESC"
    products = execute_query(query, fetch=True)
    
    return render_template('qc/products.html',
                         products=products or [],
                         show_nav_menu=True,
                         accessible_modules=_get_accessible_modules())

@bp.route('/approve-component/<int:component_id>', methods=['POST'])
@module_access_required('qc')
def approve_component(component_id):
    """Approve a component: enter good quantity, remove from QC list, send to Enter Store Items"""
    good_qty = int(request.form.get('good_qty', 0))
    po_number = request.form.get('po_number', '').strip()
    
    # Get component details
    query = "SELECT * FROM qc_components WHERE id = %s"
    component = execute_query(query, (component_id,), fetch_one=True)
    
    if component:
        # Add to qc_approved (so it appears in Store → Enter Store Items)
        insert_query = """
            INSERT INTO qc_approved 
            (item_type, part_type, part_value, part_description, footprint, po_no, qty, project_number)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """
        execute_query(insert_query, ('component', component['part_type'], component['part_value'],
                                     component['part_description'], component['footprint'],
                                     component['po_no'], good_qty, component.get('project_number', '')), commit=True)
        
        # Remove from QC components list
        delete_query = "DELETE FROM qc_components WHERE id = %s"
        execute_query(delete_query, (component_id,), commit=True)
        
        flash(f'Component approved (qty {good_qty}) and sent to Enter Store Items', 'success')
    
    # Redirect back to PO components page if we came from there, else to PO list
    if po_number:
        return redirect(url_for('qc.po_components', po_number=po_number))
    return redirect(url_for('qc.components'))

@bp.route('/approve-product/<int:product_id>', methods=['POST'])
@module_access_required('qc')
def approve_product(product_id):
    """Approve a product"""
    good_qty = int(request.form.get('good_qty', 0))
    
    # Get product details
    query = "SELECT * FROM qc_products WHERE id = %s"
    product = execute_query(query, (product_id,), fetch_one=True)
    
    if product:
        # Add to approved table
        insert_query = """
            INSERT INTO qc_approved 
            (item_type, pcb_assembly_name, part_type, part_value, part_description, 
             footprint, qty, is_pcb, project_number)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        execute_query(insert_query, ('product', product['pcb_assembly_name'],
                                     product['part_type'], product['part_value'],
                                     product['part_description'], product['footprint'],
                                     good_qty, product['is_pcb'], product.get('project_number', '')), commit=True)
        
        # Remove from QC table
        delete_query = "DELETE FROM qc_products WHERE id = %s"
        execute_query(delete_query, (product_id,), commit=True)
        
        flash('Product approved and sent to store', 'success')
    
    return redirect(url_for('qc.products'))
