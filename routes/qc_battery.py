"""QC Module - Battery (full replication)."""
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from auth import module_access_required, can_access_module
from database import execute_query
from routes.line_tables import tbl
import logging

logger = logging.getLogger(__name__)
LINE = 'battery'
BP = 'qc_battery'

def _qc_comp(): return tbl(LINE, 'qc_components')
def _qc_prod(): return tbl(LINE, 'qc_products')
def _qc_app(): return tbl(LINE, 'qc_approved')

def _accessible():
    user_email = session.get('user_email')
    return [m for m in ['rnd', 'production', 'supply_chain', 'qc', 'store'] if can_access_module(user_email, m, LINE)]

bp = Blueprint(BP, __name__, url_prefix='/battery/qc')
TP = 'line_qc/'

@bp.route('/')
@module_access_required('qc', LINE)
def qc_dashboard():
    return render_template(TP + 'dashboard.html', show_nav_menu=True, accessible_modules=_accessible(), line=LINE, bp=BP)

@bp.route('/components')
@module_access_required('qc', LINE)
def components():
    po_list = execute_query(f"""
        SELECT po_no, COUNT(*) as component_count FROM {_qc_comp()}
        WHERE po_no IS NOT NULL AND po_no != ''
        GROUP BY po_no ORDER BY po_no DESC
    """, fetch=True)
    return render_template(TP + 'components.html', po_list=po_list or [], show_nav_menu=True, accessible_modules=_accessible(), line=LINE, bp=BP)

@bp.route('/components/po/<po_number>')
@module_access_required('qc', LINE)
def po_components(po_number):
    components_list = execute_query(f"SELECT * FROM {_qc_comp()} WHERE po_no = %s ORDER BY id", (po_number,), fetch=True)
    if not components_list:
        flash(f'No components pending for PO {po_number}', 'warning')
        return redirect(url_for(f'{BP}.components'))
    return render_template(TP + 'po_components.html', po_number=po_number, components=components_list, show_nav_menu=True, accessible_modules=_accessible(), line=LINE, bp=BP)

@bp.route('/products')
@module_access_required('qc', LINE)
def products():
    products_list = execute_query(f"SELECT * FROM {_qc_prod()} ORDER BY created_at DESC", fetch=True)
    return render_template(TP + 'products.html', products=products_list or [], show_nav_menu=True, accessible_modules=_accessible(), line=LINE, bp=BP)

@bp.route('/approve-component/<int:component_id>', methods=['POST'])
@module_access_required('qc', LINE)
def approve_component(component_id):
    good_qty = int(request.form.get('good_qty', 0))
    po_number = request.form.get('po_number', '').strip()
    component = execute_query(f"SELECT * FROM {_qc_comp()} WHERE id = %s", (component_id,), fetch_one=True)
    if component:
        execute_query(f"""
            INSERT INTO {_qc_app()} (item_type, part_type, part_value, part_description, footprint, po_no, qty, project_number)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, ('component', component['part_type'], component['part_value'], component['part_description'], component['footprint'],
              component['po_no'], good_qty, component.get('project_number', '')), commit=True)
        execute_query(f"DELETE FROM {_qc_comp()} WHERE id = %s", (component_id,), commit=True)
        flash(f'Component approved (qty {good_qty}) and sent to Enter Store Items', 'success')
    if po_number:
        return redirect(url_for(f'{BP}.po_components', po_number=po_number))
    return redirect(url_for(f'{BP}.components'))

@bp.route('/approve-product/<int:product_id>', methods=['POST'])
@module_access_required('qc', LINE)
def approve_product(product_id):
    good_qty = int(request.form.get('good_qty', 0))
    product = execute_query(f"SELECT * FROM {_qc_prod()} WHERE id = %s", (product_id,), fetch_one=True)
    if product:
        execute_query(f"""
            INSERT INTO {_qc_app()} (item_type, pcb_assembly_name, part_type, part_value, part_description, footprint, qty, is_pcb, project_number)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, ('product', product['pcb_assembly_name'], product['part_type'], product['part_value'],
              product['part_description'], product['footprint'], good_qty, product['is_pcb'], product.get('project_number', '')), commit=True)
        execute_query(f"DELETE FROM {_qc_prod()} WHERE id = %s", (product_id,), commit=True)
        flash('Product approved and sent to store', 'success')
    return redirect(url_for(f'{BP}.products'))
