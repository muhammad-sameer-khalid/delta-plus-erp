"""Production Module - Battery (full replication)."""
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from auth import module_access_required, can_access_module
from database import execute_query, execute_many
from routes.line_tables import tbl
from datetime import datetime
import logging

logger = logging.getLogger(__name__)
LINE = 'battery'
BP = 'production_battery'

def _dn(): return tbl(LINE, 'demand_notes')
def _di(): return tbl(LINE, 'demand_items')
def _qp(): return tbl(LINE, 'qc_products')

def _accessible():
    user_email = session.get('user_email')
    return [m for m in ['rnd', 'production', 'supply_chain', 'qc', 'store'] if can_access_module(user_email, m, LINE)]

bp = Blueprint(BP, __name__, url_prefix='/battery/production')
TP = 'line_production/'

@bp.route('/')
@module_access_required('production', LINE)
def production_dashboard():
    return render_template(TP + 'dashboard.html', show_nav_menu=True, accessible_modules=_accessible(), line=LINE, bp=BP)

@bp.route('/generate-demand', methods=['GET', 'POST'])
@module_access_required('production', LINE)
def generate_demand():
    if request.method == 'POST':
        demand_no = int(request.form.get('demand_no', 0))
        department = request.form.get('department', '')
        required_date = request.form.get('required_date', '')
        demanded_by = request.form.get('demanded_by', '')
        demand_date = datetime.now().strftime('%Y-%m-%d')
        check_query = f"SELECT COUNT(*) as count FROM {_dn()} WHERE demand_no = %s"
        if execute_query(check_query, (demand_no,), fetch_one=True).get('count', 0) > 0:
            flash(f'Demand note #{demand_no} already exists', 'error')
            return redirect(url_for(f'{BP}.generate_demand'))
        execute_query(f"""
            INSERT INTO {_dn()} (demand_no, demand_date, department, required_date, demanded_by, approved)
            VALUES (%s, %s, %s, %s, %s, FALSE)
        """, (demand_no, demand_date, department, required_date, demanded_by), commit=True)
        demand_row = execute_query(f"SELECT id FROM {_dn()} WHERE demand_no = %s", (demand_no,), fetch_one=True)
        demand_id = demand_row['id'] if demand_row else None
        if not demand_id:
            flash('Failed to create demand note', 'error')
            return redirect(url_for(f'{BP}.generate_demand'))
        components = []
        i = 0
        while f'part_description_{i}' in request.form:
            components.append({
                'sr_no': i + 1,
                'part_type': request.form.get(f'part_type_{i}', ''),
                'part_value': request.form.get(f'part_value_{i}', ''),
                'part_description': request.form.get(f'part_description_{i}', ''),
                'footprint': request.form.get(f'footprint_{i}', ''),
                'qty': int(request.form.get(f'qty_{i}', 0)),
                'persons_demand': request.form.get(f'persons_demand_{i}', ''),
                'project': request.form.get(f'project_{i}', ''),
                'remarks': request.form.get(f'remarks_{i}', '')
            })
            i += 1
        merged = []
        for comp in components:
            key = (comp['part_type'].strip().lower(), comp['part_value'].strip().lower(), comp['part_description'].strip().lower(),
                   comp['footprint'].strip().lower(), comp['project'].strip().lower(), comp['remarks'].strip().lower())
            found = False
            for m in merged:
                mk = (m['part_type'].strip().lower(), m['part_value'].strip().lower(), m['part_description'].strip().lower(),
                      m['footprint'].strip().lower(), m['project'].strip().lower(), m['remarks'].strip().lower())
                if key == mk:
                    m['qty'] += comp['qty']
                    found = True
                    break
            if not found:
                merged.append(comp.copy())
        for idx, c in enumerate(merged):
            c['sr_no'] = idx + 1
        if merged:
            insert_q = f"""INSERT INTO {_di()} (demand_id, sr_no, part_type, part_value, part_description, footprint, qty, persons_demand, project, remarks)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"""
            params = [(demand_id, c['sr_no'], c['part_type'], c['part_value'], c['part_description'], c['footprint'], c['qty'], c['persons_demand'], c['project'], c['remarks']) for c in merged]
            execute_many(insert_q, params)
        flash(f'Demand note #{demand_no} created successfully', 'success')
        return redirect(url_for(f'{BP}.display_demand'))
    current_date = datetime.now().strftime('%Y-%m-%d')
    rnd_bp = 'rnd_battery'
    return render_template(TP + 'generate_demand.html', show_nav_menu=True, accessible_modules=_accessible(), current_date=current_date, line=LINE, bp=BP, rnd_bp=rnd_bp)

@bp.route('/display-demand')
@module_access_required('production', LINE)
def display_demand():
    demands = execute_query(f"SELECT * FROM {_dn()} ORDER BY created_at DESC", fetch=True)
    return render_template(TP + 'display_demand.html', demands=demands or [], show_nav_menu=True, accessible_modules=_accessible(), line=LINE, bp=BP)

@bp.route('/view-demand/<int:demand_no>')
@module_access_required('production', LINE)
def view_demand(demand_no):
    demand = execute_query(f"SELECT * FROM {_dn()} WHERE demand_no = %s", (demand_no,), fetch_one=True)
    if not demand:
        flash('Demand note not found', 'error')
        return redirect(url_for(f'{BP}.display_demand'))
    demand_id = demand.get('id')
    components = execute_query(f"SELECT * FROM {_di()} WHERE demand_id = %s ORDER BY sr_no", (demand_id,), fetch=True) if demand_id else []
    return render_template(TP + 'view_demand.html', demand=demand, components=components or [], show_nav_menu=True, accessible_modules=_accessible(), line=LINE, bp=BP)

@bp.route('/send-to-qc', methods=['GET', 'POST'])
@module_access_required('production', LINE)
def send_to_qc():
    if request.method == 'POST':
        product_name = request.form.get('product_name', '')
        part_type = request.form.get('part_type', '')
        part_value = request.form.get('part_value', '')
        footprint = request.form.get('footprint', '')
        project_number = request.form.get('project_number', '')
        qty = int(request.form.get('qty', 0))
        execute_query(f"""
            INSERT INTO {_qp()} (pcb_assembly_name, qty, is_pcb, part_type, part_value, part_description, footprint, project_number)
            VALUES (%s, %s, TRUE, %s, %s, %s, %s, %s)
        """, (product_name, qty, part_type, part_value, product_name, footprint, project_number), commit=True)
        execute_query(
            "INSERT INTO notifications (recipient_role, message, notification_type, related_id) VALUES (%s, %s, %s, %s)",
            ('qc manager_battery', f'New product "{product_name}" (Qty: {qty}) sent for quality check (Battery)', 'qc_product', 0), commit=True)
        flash(f'Product "{product_name}" sent to QC successfully', 'success')
        return redirect(url_for(f'{BP}.production_dashboard'))
    return render_template(TP + 'send_to_qc.html', show_nav_menu=True, accessible_modules=_accessible(), line=LINE, bp=BP)

@bp.route('/approve-demand/<int:demand_no>', methods=['POST'])
@module_access_required('production', LINE)
def approve_demand(demand_no):
    execute_query(f"UPDATE {_dn()} SET approval_status = 'pending_gm' WHERE demand_no = %s", (demand_no,), commit=True)
    execute_query(
        "INSERT INTO notifications (recipient_role, message, notification_type, related_id) VALUES (%s, %s, %s, %s)",
        ('general manager_battery', f'Demand Note #{demand_no} requires your approval (Battery)', 'demand_approval', demand_no), commit=True)
    flash(f'Demand note #{demand_no} sent for GM approval', 'success')
    return redirect(url_for(f'{BP}.display_demand'))

@bp.route('/delete-demand/<int:demand_no>', methods=['POST'])
@module_access_required('production', LINE)
def delete_demand(demand_no):
    try:
        demand_row = execute_query(f"SELECT id FROM {_dn()} WHERE demand_no = %s", (demand_no,), fetch_one=True)
        if demand_row:
            execute_query(f"DELETE FROM {_di()} WHERE demand_id = %s", (demand_row['id'],), commit=True)
        execute_query(f"DELETE FROM {_dn()} WHERE demand_no = %s", (demand_no,), commit=True)
        flash(f'Demand note #{demand_no} deleted successfully', 'success')
    except Exception as e:
        logger.error(f"Error deleting demand note {demand_no}: {e}")
        flash(f'Error deleting demand note: {str(e)}', 'error')
    return redirect(url_for(f'{BP}.display_demand'))
