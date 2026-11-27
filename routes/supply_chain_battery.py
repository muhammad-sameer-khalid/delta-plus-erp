"""Supply Chain Module - Battery (Import & Local Workflows)"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from auth import module_access_required, can_access_module, can_delete_items
from database import execute_query, execute_many
from routes.line_tables import tbl
from datetime import datetime
import logging

logger = logging.getLogger(__name__)
LINE = 'battery'
BP = 'supply_chain_battery'
SESSION_PO = 'po_draft_battery'
SESSION_PO_LOCAL = 'po_draft_local_battery'
SESSION_DEMAND = 'current_demand_no_battery'
SESSION_DEMAND_LOCAL = 'current_demand_no_local_battery'

def _dn(): return tbl(LINE, 'demand_notes')
def _di(): return tbl(LINE, 'demand_items')
def _po_meta(): return tbl(LINE, 'po_metadata')
def _po_items(): return tbl(LINE, 'po_items')
def _qc_comp(): return tbl(LINE, 'qc_components')

def _accessible():
    user_email = session.get('user_email')
    return [m for m in ['rnd', 'production', 'supply_chain', 'qc', 'store'] if can_access_module(user_email, m, LINE)]

def deduplicate_po_components(components):
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
            src = comp.get('source_demand_no')
            if src and src not in merged[key]['source_demand_nos']:
                merged[key]['source_demand_nos'].append(src)
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

bp = Blueprint(BP, __name__, url_prefix='/battery/supply-chain')
TP = 'line_supply_chain/'

@bp.route('/')
@module_access_required('supply_chain', LINE)
def supply_chain_dashboard():
    return render_template(TP + 'dashboard.html', show_nav_menu=True, accessible_modules=_accessible(), line=LINE, bp=BP)

@bp.route('/demands')
@module_access_required('supply_chain', LINE)
def demands():
    demands_list = execute_query(f"""
        SELECT * FROM {_dn()} 
        WHERE approved = TRUE AND supply_chain_archived = FALSE 
          AND (demand_type = 'import' OR demand_type IS NULL) 
        ORDER BY created_at DESC
    """, fetch=True)
    return render_template(TP + 'demands.html', demands=demands_list or [], is_local=False, show_nav_menu=True, accessible_modules=_accessible(), line=LINE, bp=BP)

@bp.route('/local-demands')
@module_access_required('supply_chain', LINE)
def local_demands():
    demands_list = execute_query(f"""
        SELECT * FROM {_dn()} 
        WHERE approved = TRUE AND supply_chain_archived = FALSE 
          AND demand_type = 'local' 
        ORDER BY created_at DESC
    """, fetch=True)
    return render_template(TP + 'demands.html', demands=demands_list or [], is_local=True, show_nav_menu=True, accessible_modules=_accessible(), line=LINE, bp=BP)

@bp.route('/archive-demand/<int:demand_no>', methods=['POST'])
@module_access_required('supply_chain', LINE)
def archive_demand(demand_no):
    execute_query(f"UPDATE {_dn()} SET supply_chain_archived = TRUE WHERE demand_no = %s", (demand_no,), commit=True)
    flash(f'Demand note #{demand_no} removed from list', 'success')
    demand = execute_query(f"SELECT demand_type FROM {_dn()} WHERE demand_no = %s", (demand_no,), fetch_one=True)
    if demand and demand.get('demand_type') == 'local':
        return redirect(url_for(f'{BP}.local_demands'))
    return redirect(url_for(f'{BP}.demands'))

@bp.route('/view-demand/<int:demand_no>')
@module_access_required('supply_chain', LINE)
def view_demand(demand_no):
    demand = execute_query(f"SELECT * FROM {_dn()} WHERE demand_no = %s", (demand_no,), fetch_one=True)
    if not demand:
        flash('Demand note not found', 'error')
        return redirect(url_for(f'{BP}.demands'))
    demand_id = demand.get('id')
    components = execute_query(f"SELECT * FROM {_di()} WHERE demand_id = %s ORDER BY sr_no", (demand_id,), fetch=True) if demand_id else []
    return render_template(TP + 'view_demand.html', demand=demand, components=components or [], show_nav_menu=True, accessible_modules=_accessible(), line=LINE, bp=BP)

# Import PO Workflow
@bp.route('/generate-po')
@module_access_required('supply_chain', LINE)
def generate_po():
    session.pop(SESSION_PO, None)
    session.pop(SESSION_DEMAND, None)
    return render_template(TP + 'generate_po_step1.html', is_local=False, show_nav_menu=True, accessible_modules=_accessible(), line=LINE, bp=BP)

@bp.route('/generate-po/select-demand', methods=['GET', 'POST'])
@module_access_required('supply_chain', LINE)
def generate_po_select_demand():
    if request.method == 'POST':
        po_number = request.form.get('po_number', '').strip()
        currency = request.form.get('currency', 'RMB').strip().upper() or 'RMB'
        if not po_number:
            flash('Please enter a PO number', 'error')
            return redirect(url_for(f'{BP}.generate_po'))
        result = execute_query(f"SELECT COUNT(*) as count FROM {_po_meta()} WHERE po_number = %s", (po_number,), fetch_one=True)
        if result and result['count'] > 0:
            flash(f'PO {po_number} already exists', 'error')
            return redirect(url_for(f'{BP}.generate_po'))
        session[SESSION_PO] = {'po_number': po_number, 'currency': currency, 'po_type': 'import', 'components': []}
        session.modified = True
    if SESSION_PO not in session:
        flash('PO session expired. Please start over.', 'error')
        return redirect(url_for(f'{BP}.generate_po'))
    po_number = session[SESSION_PO]['po_number']
    demands = execute_query(f"SELECT demand_no FROM {_dn()} WHERE approved = TRUE AND supply_chain_archived = FALSE AND (demand_type = 'import' OR demand_type IS NULL) ORDER BY demand_no DESC", fetch=True)
    demand_numbers = [d['demand_no'] for d in demands] if demands else []
    return render_template(TP + 'generate_po_step2.html', po_number=po_number, demand_numbers=demand_numbers, is_local=False, show_nav_menu=True, accessible_modules=_accessible(), line=LINE, bp=BP)

@bp.route('/generate-po/add-components', methods=['GET', 'POST'])
@module_access_required('supply_chain', LINE)
def generate_po_add_components():
    if request.method == 'POST':
        demand_no = request.form.get('demand_no', '').strip()
        if not demand_no:
            flash('Please select a demand note', 'error')
            return redirect(url_for(f'{BP}.generate_po_select_demand'))
        if SESSION_PO not in session:
            flash('PO session expired. Please start over.', 'error')
            return redirect(url_for(f'{BP}.generate_po'))
        session[SESSION_DEMAND] = demand_no
        session.modified = True
    if request.method == 'GET':
        if SESSION_PO not in session or SESSION_DEMAND not in session:
            flash('Please select a demand note first.', 'error')
            return redirect(url_for(f'{BP}.generate_po_select_demand'))
        demand_no = session[SESSION_DEMAND]
    demand_row = execute_query(f"SELECT id FROM {_dn()} WHERE demand_no = %s", (demand_no,), fetch_one=True)
    if not demand_row:
        flash(f'Demand note {demand_no} not found', 'error')
        return redirect(url_for(f'{BP}.generate_po_select_demand'))
    components = execute_query(f"SELECT * FROM {_di()} WHERE demand_id = %s ORDER BY sr_no", (demand_row['id'],), fetch=True)
    return render_template(TP + 'generate_po_step3.html', demand_no=demand_no, components=components or [], po_number=session[SESSION_PO]['po_number'], currency=session[SESSION_PO].get('currency', 'RMB'), is_local=False, show_nav_menu=True, accessible_modules=_accessible(), line=LINE, bp=BP)

@bp.route('/generate-po/save-components', methods=['POST'])
@module_access_required('supply_chain', LINE)
def generate_po_save_components():
    if SESSION_PO not in session:
        return redirect(url_for(f'{BP}.generate_po'))
    demand_no = request.form.get('demand_no')
    selected_indices = request.form.getlist('selected')
    demand_row = execute_query(f"SELECT id FROM {_dn()} WHERE demand_no = %s", (demand_no,), fetch_one=True)
    all_components = execute_query(f"SELECT * FROM {_di()} WHERE demand_id = %s ORDER BY sr_no", (demand_row['id'],), fetch=True) if demand_row else []
    for idx_str in selected_indices:
        idx = int(idx_str)
        if idx < len(all_components):
            comp = all_components[idx]
            try:
                unit_price = float(request.form.get(f'unit_price_{idx}', '0'))
            except:
                unit_price = 0.0
            qty = comp.get('qty', 0)
            session[SESSION_PO]['components'].append({
                'part_type': comp.get('part_type', ''), 'part_value': comp.get('part_value', ''),
                'part_description': comp.get('part_description', ''), 'footprint': comp.get('footprint', ''),
                'qty': qty, 'unit_price': unit_price, 'total_price': round(unit_price * qty, 2),
                'project': comp.get('project', ''), 'source_demand_no': demand_no
            })
    session.modified = True
    flash(f'Components from demand note {demand_no} added to PO', 'success')
    return redirect(url_for(f'{BP}.generate_po_review'))

@bp.route('/generate-po/review')
@module_access_required('supply_chain', LINE)
def generate_po_review():
    if SESSION_PO not in session or not session[SESSION_PO].get('components'):
        flash('No components in PO draft', 'error')
        return redirect(url_for(f'{BP}.generate_po'))
    po_draft = session[SESSION_PO]
    components = po_draft['components']
    demand_groups = {}
    for comp in components:
        src = comp.get('source_demand_no', 'Unknown')
        if src not in demand_groups: demand_groups[src] = []
        demand_groups[src].append(comp)
    dedup = deduplicate_po_components(components)
    demands = execute_query(f"SELECT demand_no FROM {_dn()} WHERE approved = TRUE AND supply_chain_archived = FALSE AND (demand_type = 'import' OR demand_type IS NULL) ORDER BY demand_no DESC", fetch=True)
    demand_numbers = [d['demand_no'] for d in demands] if demands else []
    return render_template(TP + 'generate_po_review.html', po_draft=po_draft, demand_groups=demand_groups, deduplicated_components=dedup, demand_numbers=demand_numbers, currency=po_draft.get('currency', 'RMB'), is_local=False, show_nav_menu=True, accessible_modules=_accessible(), line=LINE, bp=BP)

@bp.route('/generate-po/remove-demand/<demand_no>', methods=['POST'])
@module_access_required('supply_chain', LINE)
def generate_po_remove_demand(demand_no):
    if SESSION_PO not in session: return redirect(url_for(f'{BP}.generate_po'))
    session[SESSION_PO]['components'] = [c for c in session[SESSION_PO]['components'] if str(c.get('source_demand_no', '')) != str(demand_no)]
    session.modified = True
    if not session[SESSION_PO]['components']:
        flash(f'Demand note #{demand_no} removed. Draft is now empty.', 'warning')
        return redirect(url_for(f'{BP}.generate_po_select_demand'))
    flash(f'Demand note #{demand_no} removed from PO', 'success')
    return redirect(url_for(f'{BP}.generate_po_review'))

@bp.route('/generate-po/supplier-form')
@module_access_required('supply_chain', LINE)
def generate_po_supplier_form():
    if SESSION_PO not in session or not session[SESSION_PO].get('components'):
        return redirect(url_for(f'{BP}.generate_po'))
    return render_template(TP + 'generate_po_supplier.html', po_number=session[SESSION_PO]['po_number'], currency=session[SESSION_PO].get('currency', 'RMB'), is_local=False, show_nav_menu=True, accessible_modules=_accessible(), line=LINE, bp=BP)

@bp.route('/generate-po/finalize', methods=['POST'])
@module_access_required('supply_chain', LINE)
def generate_po_finalize():
    if SESSION_PO not in session: return redirect(url_for(f'{BP}.generate_po'))
    name = request.form.get('name', '').strip()
    company = request.form.get('company', '').strip()
    address = request.form.get('address', '').strip()
    telephone = request.form.get('telephone', '').strip()
    postal_code = request.form.get('postal_code', '').strip()
    if not all([name, company, telephone]):
        flash('Name, Company, and Telephone are required', 'error')
        return redirect(url_for(f'{BP}.generate_po_supplier_form'))
    po_draft = session[SESSION_PO]
    po_number = po_draft['po_number']
    currency = po_draft.get('currency', 'RMB')
    components = deduplicate_po_components(po_draft['components'])
    execute_query(f"INSERT INTO {_po_meta()} (po_number, supplier_name, supplier_company, supplier_address, supplier_telephone, supplier_postal_code, currency, po_type) VALUES (%s, %s, %s, %s, %s, %s, %s, 'import')",
                  (po_number, name, company, address, telephone, postal_code, currency), commit=True)
    po_row = execute_query(f"SELECT id FROM {_po_meta()} WHERE po_number = %s", (po_number,), fetch_one=True)
    po_id = po_row['id'] if po_row else None
    if po_id and components:
        comp_data = [(po_id, c['part_type'], c['part_value'], c['part_description'], c['footprint'], c['qty'], c['unit_price'], c['total_price'], c['project']) for c in components]
        execute_many(f"INSERT INTO {_po_items()} (po_id, part_type, part_value, part_description, footprint, qty, unit_price, total_price, project) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)", comp_data, commit=True)
        qc_data = [(c['part_type'], c['part_value'], c['part_description'], c['footprint'], po_number, c['qty'], c['project']) for c in components]
        execute_many(f"INSERT INTO {_qc_comp()} (part_type, part_value, part_description, footprint, po_no, qty, project_number, po_type) VALUES (%s, %s, %s, %s, %s, %s, %s, 'import')", qc_data, commit=True)
    session.pop(SESSION_PO, None)
    session.pop(SESSION_DEMAND, None)
    session.modified = True
    flash(f'Purchase Order {po_number} created successfully and sent to QC!', 'success')
    return redirect(url_for(f'{BP}.view_po', po_number=po_number))

# Local PO Workflow
@bp.route('/generate-local-po')
@module_access_required('supply_chain', LINE)
def generate_local_po():
    session.pop(SESSION_PO_LOCAL, None)
    session.pop(SESSION_DEMAND_LOCAL, None)
    return render_template(TP + 'generate_po_step1.html', is_local=True, show_nav_menu=True, accessible_modules=_accessible(), line=LINE, bp=BP)

@bp.route('/generate-local-po/select-demand', methods=['GET', 'POST'])
@module_access_required('supply_chain', LINE)
def generate_local_po_select_demand():
    if request.method == 'POST':
        po_number = request.form.get('po_number', '').strip()
        if not po_number:
            flash('Please enter a PO number', 'error')
            return redirect(url_for(f'{BP}.generate_local_po'))
        result = execute_query(f"SELECT COUNT(*) as count FROM {_po_meta()} WHERE po_number = %s", (po_number,), fetch_one=True)
        if result and result['count'] > 0:
            flash(f'PO {po_number} already exists', 'error')
            return redirect(url_for(f'{BP}.generate_local_po'))
        session[SESSION_PO_LOCAL] = {'po_number': po_number, 'currency': 'RS', 'po_type': 'local', 'components': []}
        session.modified = True
    if SESSION_PO_LOCAL not in session:
        flash('Local PO session expired. Please start over.', 'error')
        return redirect(url_for(f'{BP}.generate_local_po'))
    po_number = session[SESSION_PO_LOCAL]['po_number']
    demands = execute_query(f"SELECT demand_no FROM {_dn()} WHERE approved = TRUE AND supply_chain_archived = FALSE AND demand_type = 'local' ORDER BY demand_no DESC", fetch=True)
    demand_numbers = [d['demand_no'] for d in demands] if demands else []
    return render_template(TP + 'generate_po_step2.html', po_number=po_number, demand_numbers=demand_numbers, is_local=True, show_nav_menu=True, accessible_modules=_accessible(), line=LINE, bp=BP)

@bp.route('/generate-local-po/add-components', methods=['GET', 'POST'])
@module_access_required('supply_chain', LINE)
def generate_local_po_add_components():
    if request.method == 'POST':
        demand_no = request.form.get('demand_no', '').strip()
        if not demand_no:
            flash('Please select a demand note', 'error')
            return redirect(url_for(f'{BP}.generate_local_po_select_demand'))
        if SESSION_PO_LOCAL not in session:
            flash('Local PO session expired. Please start over.', 'error')
            return redirect(url_for(f'{BP}.generate_local_po'))
        session[SESSION_DEMAND_LOCAL] = demand_no
        session.modified = True
    if request.method == 'GET':
        if SESSION_PO_LOCAL not in session or SESSION_DEMAND_LOCAL not in session:
            flash('Please select a demand note first.', 'error')
            return redirect(url_for(f'{BP}.generate_local_po_select_demand'))
        demand_no = session[SESSION_DEMAND_LOCAL]
    demand_row = execute_query(f"SELECT id FROM {_dn()} WHERE demand_no = %s", (demand_no,), fetch_one=True)
    components = execute_query(f"SELECT * FROM {_di()} WHERE demand_id = %s ORDER BY sr_no", (demand_row['id'],), fetch=True) if demand_row else []
    return render_template(TP + 'generate_po_step3.html', demand_no=demand_no, components=components or [], po_number=session[SESSION_PO_LOCAL]['po_number'], currency='RS', is_local=True, show_nav_menu=True, accessible_modules=_accessible(), line=LINE, bp=BP)

@bp.route('/generate-local-po/save-components', methods=['POST'])
@module_access_required('supply_chain', LINE)
def generate_local_po_save_components():
    if SESSION_PO_LOCAL not in session: return redirect(url_for(f'{BP}.generate_local_po'))
    demand_no = request.form.get('demand_no')
    selected_indices = request.form.getlist('selected')
    demand_row = execute_query(f"SELECT id FROM {_dn()} WHERE demand_no = %s", (demand_no,), fetch_one=True)
    all_components = execute_query(f"SELECT * FROM {_di()} WHERE demand_id = %s ORDER BY sr_no", (demand_row['id'],), fetch=True) if demand_row else []
    for idx_str in selected_indices:
        idx = int(idx_str)
        if idx < len(all_components):
            comp = all_components[idx]
            try:
                unit_price = float(request.form.get(f'unit_price_{idx}', '0'))
            except:
                unit_price = 0.0
            qty = comp.get('qty', 0)
            session[SESSION_PO_LOCAL]['components'].append({
                'part_type': comp.get('part_type', ''), 'part_value': comp.get('part_value', ''),
                'part_description': comp.get('part_description', ''), 'footprint': comp.get('footprint', ''),
                'qty': qty, 'unit_price': unit_price, 'total_price': round(unit_price * qty, 2),
                'project': comp.get('project', ''), 'source_demand_no': demand_no
            })
    session.modified = True
    flash(f'Components from local demand note {demand_no} added to Local PO', 'success')
    return redirect(url_for(f'{BP}.generate_local_po_review'))

@bp.route('/generate-local-po/review')
@module_access_required('supply_chain', LINE)
def generate_local_po_review():
    if SESSION_PO_LOCAL not in session or not session[SESSION_PO_LOCAL].get('components'):
        flash('No components in Local PO draft', 'error')
        return redirect(url_for(f'{BP}.generate_local_po'))
    po_draft = session[SESSION_PO_LOCAL]
    components = po_draft['components']
    demand_groups = {}
    for comp in components:
        src = comp.get('source_demand_no', 'Unknown')
        if src not in demand_groups: demand_groups[src] = []
        demand_groups[src].append(comp)
    dedup = deduplicate_po_components(components)
    demands = execute_query(f"SELECT demand_no FROM {_dn()} WHERE approved = TRUE AND supply_chain_archived = FALSE AND demand_type = 'local' ORDER BY demand_no DESC", fetch=True)
    demand_numbers = [d['demand_no'] for d in demands] if demands else []
    return render_template(TP + 'generate_po_review.html', po_draft=po_draft, demand_groups=demand_groups, deduplicated_components=dedup, demand_numbers=demand_numbers, currency='RS', is_local=True, show_nav_menu=True, accessible_modules=_accessible(), line=LINE, bp=BP)

@bp.route('/generate-local-po/remove-demand/<demand_no>', methods=['POST'])
@module_access_required('supply_chain', LINE)
def generate_local_po_remove_demand(demand_no):
    if SESSION_PO_LOCAL not in session: return redirect(url_for(f'{BP}.generate_local_po'))
    session[SESSION_PO_LOCAL]['components'] = [c for c in session[SESSION_PO_LOCAL]['components'] if str(c.get('source_demand_no', '')) != str(demand_no)]
    session.modified = True
    if not session[SESSION_PO_LOCAL]['components']:
        flash(f'Demand note #{demand_no} removed. Draft is now empty.', 'warning')
        return redirect(url_for(f'{BP}.generate_local_po_select_demand'))
    flash(f'Demand note #{demand_no} removed from Local PO', 'success')
    return redirect(url_for(f'{BP}.generate_local_po_review'))

@bp.route('/generate-local-po/supplier-form')
@module_access_required('supply_chain', LINE)
def generate_local_po_supplier_form():
    if SESSION_PO_LOCAL not in session or not session[SESSION_PO_LOCAL].get('components'):
        return redirect(url_for(f'{BP}.generate_local_po'))
    return render_template(TP + 'generate_po_supplier.html', po_number=session[SESSION_PO_LOCAL]['po_number'], currency='RS', is_local=True, show_nav_menu=True, accessible_modules=_accessible(), line=LINE, bp=BP)

@bp.route('/generate-local-po/finalize', methods=['POST'])
@module_access_required('supply_chain', LINE)
def generate_local_po_finalize():
    if SESSION_PO_LOCAL not in session: return redirect(url_for(f'{BP}.generate_local_po'))
    name = request.form.get('name', '').strip()
    company = request.form.get('company', '').strip()
    address = request.form.get('address', '').strip()
    telephone = request.form.get('telephone', '').strip()
    postal_code = request.form.get('postal_code', '').strip()
    po_draft = session[SESSION_PO_LOCAL]
    po_number = po_draft['po_number']
    components = deduplicate_po_components(po_draft['components'])
    execute_query(f"INSERT INTO {_po_meta()} (po_number, supplier_name, supplier_company, supplier_address, supplier_telephone, supplier_postal_code, currency, po_type) VALUES (%s, %s, %s, %s, %s, %s, 'RS', 'local')",
                  (po_number, name, company, address, telephone, postal_code), commit=True)
    po_row = execute_query(f"SELECT id FROM {_po_meta()} WHERE po_number = %s", (po_number,), fetch_one=True)
    po_id = po_row['id'] if po_row else None
    if po_id and components:
        comp_data = [(po_id, c['part_type'], c['part_value'], c['part_description'], c['footprint'], c['qty'], c['unit_price'], c['total_price'], c['project']) for c in components]
        execute_many(f"INSERT INTO {_po_items()} (po_id, part_type, part_value, part_description, footprint, qty, unit_price, total_price, project) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)", comp_data, commit=True)
        qc_data = [(c['part_type'], c['part_value'], c['part_description'], c['footprint'], po_number, c['qty'], c['project']) for c in components]
        execute_many(f"INSERT INTO {_qc_comp()} (part_type, part_value, part_description, footprint, po_no, qty, project_number, po_type) VALUES (%s, %s, %s, %s, %s, %s, %s, 'local')", qc_data, commit=True)
    session.pop(SESSION_PO_LOCAL, None)
    session.pop(SESSION_DEMAND_LOCAL, None)
    session.modified = True
    flash(f'Local Purchase Order {po_number} created successfully and sent to QC!', 'success')
    return redirect(url_for(f'{BP}.view_local_po', po_number=po_number))

# Display & View POs
@bp.route('/display-po')
@module_access_required('supply_chain', LINE)
def display_po():
    pos = execute_query(f"SELECT * FROM {_po_meta()} WHERE po_type = 'import' OR po_type IS NULL ORDER BY created_at DESC", fetch=True)
    return render_template(TP + 'display_po.html', pos=pos or [], is_local=False, show_nav_menu=True, accessible_modules=_accessible(), line=LINE, bp=BP)

@bp.route('/display-local-po')
@module_access_required('supply_chain', LINE)
def display_local_po():
    pos = execute_query(f"SELECT * FROM {_po_meta()} WHERE po_type = 'local' ORDER BY created_at DESC", fetch=True)
    return render_template(TP + 'display_po.html', pos=pos or [], is_local=True, show_nav_menu=True, accessible_modules=_accessible(), line=LINE, bp=BP)

@bp.route('/view-po/<po_number>')
@module_access_required('supply_chain', LINE)
def view_po(po_number):
    po_meta = execute_query(f"SELECT * FROM {_po_meta()} WHERE po_number = %s", (po_number,), fetch_one=True)
    if not po_meta:
        flash('Purchase order not found', 'error')
        return redirect(url_for(f'{BP}.display_po'))
    po_id = po_meta.get('id')
    items = execute_query(f"SELECT * FROM {_po_items()} WHERE po_id = %s ORDER BY id", (po_id,), fetch=True) if po_id else []
    project_subtotals = {}
    for item in items:
        p = item.get('project', 'N/A')
        project_subtotals[p] = project_subtotals.get(p, 0) + float(item.get('total_price', 0) or 0)
    grand_total = sum(project_subtotals.values())
    current_date = datetime.now().strftime('%Y-%m-%d')
    return render_template(TP + 'view_po.html', po=po_meta, items=items or [], project_subtotals=project_subtotals, grand_total=grand_total, current_date=current_date, currency=po_meta.get('currency', 'RMB'), show_nav_menu=True, accessible_modules=_accessible(), line=LINE, bp=BP)

@bp.route('/view-local-po/<po_number>')
@module_access_required('supply_chain', LINE)
def view_local_po(po_number):
    po_meta = execute_query(f"SELECT * FROM {_po_meta()} WHERE po_number = %s", (po_number,), fetch_one=True)
    if not po_meta:
        flash('Local purchase order not found', 'error')
        return redirect(url_for(f'{BP}.display_local_po'))
    po_id = po_meta.get('id')
    items = execute_query(f"SELECT * FROM {_po_items()} WHERE po_id = %s ORDER BY id", (po_id,), fetch=True) if po_id else []
    net_amount = sum(float(item.get('total_price', 0) or 0) for item in items)
    gst_amount = round(net_amount * 0.17, 2)
    grand_total = round(net_amount + gst_amount, 2)
    current_date = datetime.now().strftime('%Y-%m-%d')
    return render_template(TP + 'view_local_po.html', po=po_meta, items=items or [], net_amount=net_amount, gst_amount=gst_amount, grand_total=grand_total, current_date=current_date, show_nav_menu=True, accessible_modules=_accessible(), line=LINE, bp=BP)

@bp.route('/delete-po/<po_number>', methods=['POST'])
@module_access_required('supply_chain', LINE)
def delete_po(po_number):
    try:
        po = execute_query(f"SELECT id, po_type FROM {_po_meta()} WHERE po_number = %s", (po_number,), fetch_one=True)
        if po:
            po_id = po['id']
            po_type = po.get('po_type', 'import')
            execute_query(f"DELETE FROM {_po_items()} WHERE po_id = %s", (po_id,), commit=True)
            execute_query(f"DELETE FROM {_qc_comp()} WHERE po_no = %s", (po_number,), commit=True)
            execute_query(f"DELETE FROM {_po_meta()} WHERE id = %s", (po_id,), commit=True)
            flash(f'Purchase Order {po_number} deleted successfully.', 'success')
            if po_type == 'local':
                return redirect(url_for(f'{BP}.display_local_po'))
    except Exception as e:
        logger.error(f"Error deleting PO {po_number}: {e}")
        flash(f'Error deleting Purchase Order: {str(e)}', 'error')
    return redirect(url_for(f'{BP}.display_po'))
