"""Store Module - Biomedical (full replication). Uses line-specific tables and session key.
   Tables: qc_approved_*, store_*_*, bom_metadata_*, bom_items_*, issues_metadata_*, issue_items_*."""
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from auth import module_access_required, can_access_module
from database import execute_query, table_exists
from routes.line_tables import tbl
from datetime import datetime
import logging

logger = logging.getLogger(__name__)
LINE = 'biomedical'
BP = 'store_biomedical'
SESSION_ISSUE = 'pending_issue_biomedical'

CATEGORIES = [
    ('resistors', 'Resistors'), ('capacitors', 'Capacitors'), ('diodes_transistors', 'Diodes & Transistors'),
    ('ics', 'ICs'), ('connectors', 'Connectors'), ('misc_components', 'Misc Components'),
    ('pcbs', 'PCBs'), ('assemblies', 'Assemblies'), ('misc_products', 'Misc Products')
]

def _store_table(cat):
    return tbl(LINE, f'store_{cat}')

def _qc_app():
    return tbl(LINE, 'qc_approved')

def _bm():
    return tbl(LINE, 'bom_metadata')

def _bi():
    return tbl(LINE, 'bom_items')

def _im():
    return tbl(LINE, 'issues_metadata')

def _ii():
    return tbl(LINE, 'issue_items')

def _accessible():
    user_email = session.get('user_email')
    return [m for m in ['rnd', 'production', 'supply_chain', 'qc', 'store'] if can_access_module(user_email, m, LINE)]

def _search_store_items(q, limit=20):
    q = (q or '').strip().lower()
    if not q or len(q) < 1:
        return []
    results = []
    like = f"%{q}%"
    for cat, _ in CATEGORIES:
        table = _store_table(cat)
        if not table_exists(table):
            continue
        sql = f"""SELECT id, part_type, part_value, part_description, footprint, qty FROM {table}
            WHERE LOWER(COALESCE(part_type,'')) LIKE %s OR LOWER(COALESCE(part_value,'')) LIKE %s
            OR LOWER(COALESCE(part_description,'')) LIKE %s OR LOWER(COALESCE(footprint,'')) LIKE %s
            ORDER BY part_type, part_value LIMIT %s"""
        rows = execute_query(sql, (like, like, like, like, limit), fetch=True)
        if rows:
            for r in rows:
                r['store_category'] = cat
                results.append(r)
    return results[:limit]

def _search_boms(q, limit=30):
    q = (q or '').strip().lower()
    if not q:
        return execute_query(f"SELECT id, bom_name, bom_type FROM {_bm()} ORDER BY bom_name LIMIT %s", (limit,), fetch=True) or []
    return execute_query(f"SELECT id, bom_name, bom_type FROM {_bm()} WHERE LOWER(bom_name) LIKE %s ORDER BY bom_name LIMIT %s", (f"%{q}%", limit), fetch=True) or []

def _get_bom_components(bom_id):
    bom = execute_query(f"SELECT bom_name FROM {_bm()} WHERE id = %s", (bom_id,), fetch_one=True)
    if not bom:
        return None, []
    rows = execute_query(f"SELECT part_type, part_value, part_description, footprint, qty FROM {_bi()} WHERE bom_id = %s", (bom_id,), fetch=True)
    return bom['bom_name'], (rows or [])

def _find_in_store(part_type, part_value, part_description, footprint):
    for cat, _ in CATEGORIES:
        table = _store_table(cat)
        if not table_exists(table):
            continue
        row = execute_query(f"""SELECT id, qty FROM {table} WHERE COALESCE(part_type,'') = COALESCE(%s,'') AND COALESCE(part_value,'') = COALESCE(%s,'')
            AND COALESCE(part_description,'') = COALESCE(%s,'') AND COALESCE(footprint,'') = COALESCE(%s,'') LIMIT 1""",
            (part_type, part_value, part_description, footprint), fetch_one=True)
        if row:
            return cat, row
    return None, None

def _pending_reserved_for_store_row(store_category, store_id):
    total = 0
    for it in (session.get(SESSION_ISSUE) or {}).get('items', []):
        if it.get('store_category') == store_category and it.get('store_id') == store_id:
            total += int(it.get('qty', 0) or 0)
    return total

bp = Blueprint(BP, __name__, url_prefix='/biomedical/store')
TP = 'line_store/'

@bp.route('/')
@module_access_required('store', LINE)
def store_dashboard():
    return render_template(TP + 'dashboard.html', show_nav_menu=True, accessible_modules=_accessible(), line=LINE, bp=BP, categories=CATEGORIES)

@bp.route('/enter-items')
@module_access_required('store', LINE)
def enter_items():
    approved_items = execute_query(f"SELECT * FROM {_qc_app()} ORDER BY created_at DESC", fetch=True)
    return render_template(TP + 'enter_items.html', approved_items=approved_items or [], categories=CATEGORIES, show_nav_menu=True, accessible_modules=_accessible(), line=LINE, bp=BP)

@bp.route('/add-to-store/<int:item_id>', methods=['POST'])
@module_access_required('store', LINE)
def add_to_store(item_id):
    category = request.form.get('category', '').strip()
    section = request.form.get('section', '').strip()
    item = execute_query(f"SELECT * FROM {_qc_app()} WHERE id = %s", (item_id,), fetch_one=True)
    if item and category:
        table_name = _store_table(category)
        existing = execute_query(f"""SELECT * FROM {table_name} WHERE part_type = %s AND part_value = %s AND part_description = %s AND footprint = %s LIMIT 1""",
            (item['part_type'], item['part_value'], item['part_description'], item['footprint']), fetch_one=True)
        if existing:
            new_qty = existing['qty'] + item['qty']
            existing_po_nos = (existing.get('po_no') or '').strip()
            new_po = (item.get('po_no') or '').strip()
            updated_po_nos = f"{existing_po_nos}, {new_po}".strip() if new_po and new_po not in existing_po_nos else existing_po_nos
            execute_query(f"UPDATE {table_name} SET qty = %s, po_no = %s WHERE id = %s", (new_qty, updated_po_nos, existing['id']), commit=True)
            flash(f'Item merged with existing inventory. New quantity: {new_qty}', 'success')
        else:
            execute_query(f"""INSERT INTO {table_name} (part_type, part_value, part_description, footprint, qty, po_no, section, project_number)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                (item['part_type'], item['part_value'], item['part_description'], item['footprint'], item['qty'], item.get('po_no', ''), section, item.get('project_number', '')), commit=True)
            flash('Item added to store successfully', 'success')
        execute_query(f"DELETE FROM {_qc_app()} WHERE id = %s", (item_id,), commit=True)
    return redirect(url_for(f'{BP}.enter_items'))

@bp.route('/view-items')
@module_access_required('store', LINE)
def view_items():
    return render_template(TP + 'view_items.html', categories=CATEGORIES, show_nav_menu=True, accessible_modules=_accessible(), line=LINE, bp=BP)

@bp.route('/view-category/<category>')
@module_access_required('store', LINE)
def view_category(category):
    table_name = _store_table(category)
    items = execute_query(f"SELECT * FROM {table_name} ORDER BY created_at DESC", fetch=True)
    category_name = dict(CATEGORIES).get(category, category)
    return render_template(TP + 'view_category.html', items=items or [], category=category, category_name=category_name, show_nav_menu=True, accessible_modules=_accessible(), line=LINE, bp=BP)

@bp.route('/issue-items', methods=['GET', 'POST'])
@module_access_required('store', LINE)
def issue_items():
    if request.method == 'POST':
        issue_number = request.form.get('issue_number', '').strip()
        pcb_assembly_name = request.form.get('pcb_assembly_name', '').strip()
        issued_to = request.form.get('issued_to', '').strip()
        contract_project = request.form.get('contract_project', '').strip()
        if not all([issue_number, pcb_assembly_name, issued_to, contract_project]):
            flash('All fields are required', 'error')
            return redirect(url_for(f'{BP}.issue_items'))
        if execute_query(f"SELECT 1 FROM {_im()} WHERE issue_number = %s", (issue_number,), fetch_one=True):
            flash(f'Issue number "{issue_number}" already exists', 'error')
            return redirect(url_for(f'{BP}.issue_items'))
        session[SESSION_ISSUE] = {'issue_number': issue_number, 'pcb_assembly_name': pcb_assembly_name, 'issued_to': issued_to, 'contract_project': contract_project, 'items': []}
        session.modified = True
        return redirect(url_for(f'{BP}.issue_select_method'))
    return render_template(TP + 'issue_items.html', show_nav_menu=True, accessible_modules=_accessible(), line=LINE, bp=BP)

@bp.route('/issue-select-method')
@module_access_required('store', LINE)
def issue_select_method():
    if not session.get(SESSION_ISSUE):
        flash('Please start by entering issue details', 'error')
        return redirect(url_for(f'{BP}.issue_items'))
    pending_issue = session.get(SESSION_ISSUE)
    return render_template(TP + 'issue_select_method.html', show_nav_menu=True, accessible_modules=_accessible(), line=LINE, bp=BP, pending_issue=pending_issue)

@bp.route('/issue-add-separate')
@module_access_required('store', LINE)
def issue_add_separate():
    if not session.get(SESSION_ISSUE):
        flash('Please start by entering issue details', 'error')
        return redirect(url_for(f'{BP}.issue_items'))
    pending_issue = session.get(SESSION_ISSUE)
    return render_template(TP + 'issue_add_separate.html', show_nav_menu=True, accessible_modules=_accessible(), line=LINE, bp=BP, pending_issue=pending_issue)

@bp.route('/issue-add-from-bom')
@module_access_required('store', LINE)
def issue_add_from_bom():
    if not session.get(SESSION_ISSUE):
        flash('Please start by entering issue details', 'error')
        return redirect(url_for(f'{BP}.issue_items'))
    boms = execute_query(f"SELECT id, bom_name, bom_type FROM {_bm()} ORDER BY bom_name", fetch=True)
    pending_issue = session.get(SESSION_ISSUE)
    return render_template(TP + 'issue_add_from_bom.html', boms=boms or [], show_nav_menu=True, accessible_modules=_accessible(), line=LINE, bp=BP, pending_issue=pending_issue)

@bp.route('/api/pending-items')
@module_access_required('store', LINE)
def api_pending_items():
    pending = session.get(SESSION_ISSUE)
    if not pending:
        return jsonify({'items': []})
    return jsonify({'items': pending.get('items', [])})

@bp.route('/api/available-for-store-item')
@module_access_required('store', LINE)
def api_available_for_store_item():
    store_category = (request.args.get('store_category') or '').strip()
    store_id = request.args.get('store_id')
    if not store_category or not store_id:
        return jsonify({'error': 'Missing store_category or store_id'}), 400
    table = _store_table(store_category)
    if not table_exists(table):
        return jsonify({'error': 'Invalid category'}), 400
    row = execute_query(f"SELECT qty FROM {table} WHERE id = %s", (store_id,), fetch_one=True)
    if not row:
        return jsonify({'error': 'Item not found'}), 404
    store_qty = int(row.get('qty', 0) or 0)
    already = _pending_reserved_for_store_row(store_category, store_id)
    available = max(0, store_qty - already)
    return jsonify({'available': available, 'store_qty': store_qty, 'already_in_issue': already})

@bp.route('/api/search-store-items')
@module_access_required('store', LINE)
def api_search_store_items():
    q = request.args.get('q', '')
    return jsonify({'items': _search_store_items(q, limit=25)})

@bp.route('/api/search-boms')
@module_access_required('store', LINE)
def api_search_boms():
    q = request.args.get('q', '')
    return jsonify({'boms': _search_boms(q, limit=30)})

@bp.route('/api/search-issues')
@module_access_required('store', LINE)
def api_search_issues():
    q = (request.args.get('q') or '').strip().lower()
    if not q:
        results = execute_query(f"SELECT * FROM {_im()} ORDER BY created_at DESC LIMIT 50", fetch=True)
    else:
        like = f"%{q}%"
        results = execute_query(f"""SELECT * FROM {_im()} WHERE LOWER(COALESCE(contract_project,'')) LIKE %s OR LOWER(COALESCE(issue_number,'')) LIKE %s
            OR LOWER(COALESCE(issued_to,'')) LIKE %s OR LOWER(COALESCE(pcb_assembly_name,'')) LIKE %s ORDER BY created_at DESC LIMIT 50""", (like, like, like, like), fetch=True)
    if results:
        for r in results:
            if r.get('date_issued'): r['date_issued'] = str(r['date_issued'])
            if r.get('created_at'): r['created_at'] = r['created_at'].strftime('%Y-%m-%d %H:%M:%S')
    return jsonify({'issues': results or []})

@bp.route('/api/bom-components/<int:bom_id>')
@module_access_required('store', LINE)
def api_bom_components(bom_id):
    bom_name, components = _get_bom_components(bom_id)
    if bom_name is None:
        return jsonify({'error': 'BOM not found'}), 404
    try:
        bom_qty_mult = max(1, int(request.args.get('qty', 1)))
    except (TypeError, ValueError):
        bom_qty_mult = 1
    out = []
    missing = []
    for c in components:
        required = (c.get('qty', 0) or 0) * bom_qty_mult
        cat, row = _find_in_store(c.get('part_type'), c.get('part_value'), c.get('part_description'), c.get('footprint'))
        if cat and row:
            store_qty = row.get('qty', 0) or 0
            if store_qty <= 0:
                missing.append({'part_type': c.get('part_type'), 'part_value': c.get('part_value'), 'part_description': c.get('part_description'), 'footprint': c.get('footprint'), 'qty': required})
                continue
            issue_qty = min(required, store_qty)
            out.append({'part_type': c.get('part_type'), 'part_value': c.get('part_value'), 'part_description': c.get('part_description'), 'footprint': c.get('footprint'),
                'bom_qty': c.get('qty', 0), 'required': required, 'store_qty': store_qty, 'issue_qty': issue_qty, 'store_category': cat, 'store_id': row.get('id'), 'in_store': True, 'insufficient': issue_qty < required})
        else:
            missing.append({'part_type': c.get('part_type'), 'part_value': c.get('part_value'), 'part_description': c.get('part_description'), 'footprint': c.get('footprint'), 'qty': required})
    return jsonify({'bom_name': bom_name, 'bom_qty': bom_qty_mult, 'in_store': out, 'missing': missing})

@bp.route('/issue-add-item', methods=['POST'])
@module_access_required('store', LINE)
def issue_add_item():
    if not session.get(SESSION_ISSUE):
        return jsonify({'error': 'No pending issue'}), 400
    data = request.get_json() or request.form
    store_category = (data.get('store_category') or '').strip()
    store_id = data.get('store_id')
    want_qty = int(data.get('qty', 0) or 0)
    if not store_category or not store_id or want_qty <= 0:
        return jsonify({'error': 'Invalid store_category, store_id, or qty'}), 400
    table = _store_table(store_category)
    if not table_exists(table):
        return jsonify({'error': 'Invalid category'}), 400
    row = execute_query(f"SELECT id, part_type, part_value, part_description, footprint, qty FROM {table} WHERE id = %s", (store_id,), fetch_one=True)
    if not row:
        return jsonify({'error': 'Item not found'}), 404
    store_qty = int(row.get('qty', 0) or 0)
    already = _pending_reserved_for_store_row(store_category, store_id)
    available = max(0, store_qty - already)
    to_add = min(want_qty, available)
    if to_add <= 0:
        return jsonify({'error': f'Only {store_qty} in store and {already} already in this issue.'}), 400
    pending = session[SESSION_ISSUE]['items']
    existing_idx = next((i for i, p in enumerate(pending) if p.get('store_category') == store_category and p.get('store_id') == store_id), None)
    if existing_idx is not None:
        pending[existing_idx]['qty'] = int(pending[existing_idx].get('qty', 0) or 0) + to_add
    else:
        pending.append({'part_type': row.get('part_type') or '', 'part_value': row.get('part_value') or '', 'part_description': row.get('part_description') or '', 'footprint': row.get('footprint') or '', 'qty': to_add, 'store_category': store_category, 'store_id': store_id})
    session.modified = True
    resp = {'success': True, 'items': session[SESSION_ISSUE]['items']}
    if to_add < want_qty:
        resp['message'] = f'Added {to_add} (only {available} available).'
    return jsonify(resp)

@bp.route('/issue-add-bom-items', methods=['POST'])
@module_access_required('store', LINE)
def issue_add_bom_items():
    if not session.get(SESSION_ISSUE):
        return jsonify({'error': 'No pending issue'}), 400
    data = request.get_json() or request.form
    items = data.get('items', []) if isinstance(data.get('items'), list) else []
    pending = session[SESSION_ISSUE]['items']
    for it in items:
        store_category = (it.get('store_category') or '').strip()
        store_id = it.get('store_id')
        want_qty = int(it.get('qty', 0) or 0)
        if not store_category or not store_id or want_qty <= 0:
            continue
        table = _store_table(store_category)
        if not table_exists(table):
            continue
        row = execute_query(f"SELECT id, part_type, part_value, part_description, footprint, qty FROM {table} WHERE id = %s", (store_id,), fetch_one=True)
        if not row:
            continue
        store_qty = int(row.get('qty', 0) or 0)
        already = _pending_reserved_for_store_row(store_category, store_id)
        available = max(0, store_qty - already)
        to_add = min(want_qty, available)
        if to_add <= 0:
            continue
        existing_idx = next((i for i, p in enumerate(pending) if p.get('store_category') == store_category and p.get('store_id') == store_id), None)
        if existing_idx is not None:
            pending[existing_idx]['qty'] = int(pending[existing_idx].get('qty', 0) or 0) + to_add
        else:
            pending.append({'part_type': row.get('part_type') or '', 'part_value': row.get('part_value') or '', 'part_description': row.get('part_description') or '', 'footprint': row.get('footprint') or '', 'qty': to_add, 'store_category': store_category, 'store_id': store_id})
    session.modified = True
    return jsonify({'success': True, 'items': session[SESSION_ISSUE]['items']})

@bp.route('/issue-submit', methods=['POST'])
@module_access_required('store', LINE)
def issue_submit():
    pending = session.get(SESSION_ISSUE)
    if not pending:
        flash('No pending issue to submit', 'error')
        return redirect(url_for(f'{BP}.issue_items'))
    items = pending.get('items') or []
    if not items:
        flash('Add at least one item before issuing', 'error')
        return redirect(url_for(f'{BP}.issue_add_separate'))
    issue_number = pending['issue_number']
    date_issued = datetime.now().strftime('%Y-%m-%d')
    execute_query(f"INSERT INTO {_im()} (issue_number, pcb_assembly_name, date_issued, issued_to, contract_project) VALUES (%s, %s, %s, %s, %s)",
        (issue_number, pending['pcb_assembly_name'], date_issued, pending['issued_to'], pending['contract_project']), commit=True)
    meta_row = execute_query(f"SELECT id FROM {_im()} WHERE issue_number = %s", (issue_number,), fetch_one=True)
    issue_id = meta_row['id'] if meta_row else None
    if not issue_id:
        flash('Failed to create issue', 'error')
        return redirect(url_for(f'{BP}.issue_add_separate'))
    for it in items:
        execute_query(f"INSERT INTO {_ii()} (issue_id, part_type, part_value, part_description, footprint, qty) VALUES (%s, %s, %s, %s, %s, %s)",
            (issue_id, it['part_type'], it['part_value'], it['part_description'], it['footprint'], it['qty']), commit=True)
        st = _store_table(it['store_category'])
        execute_query(f"UPDATE {st} SET qty = qty - %s WHERE id = %s", (it['qty'], it['store_id']), commit=True)
    session.pop(SESSION_ISSUE, None)
    session.modified = True
    flash(f'Issue {issue_number} created successfully', 'success')
    return redirect(url_for(f'{BP}.view_issues'))

@bp.route('/view-issues')
@module_access_required('store', LINE)
def view_issues():
    q = request.args.get('q', '').strip()
    if q:
        issues = execute_query(f"SELECT * FROM {_im()} WHERE LOWER(COALESCE(contract_project,'')) LIKE %s ORDER BY created_at DESC", (f"%{q.lower()}%",), fetch=True)
    else:
        issues = execute_query(f"SELECT * FROM {_im()} ORDER BY created_at DESC", fetch=True)
    return render_template(TP + 'view_issues.html', issues=issues or [], search_q=q, show_nav_menu=True, accessible_modules=_accessible(), line=LINE, bp=BP)


@bp.route('/delete-issue/<issue_number>', methods=['POST'])
@module_access_required('store', LINE)
def delete_issue(issue_number):
    """Delete an issue and its items."""
    try:
        # Get Issue ID first to delete items
        issue = execute_query(f"SELECT id FROM {_im()} WHERE issue_number = %s", (issue_number,), fetch_one=True)
        if issue:
            issue_id = issue['id']
            execute_query(f"DELETE FROM {_ii()} WHERE issue_id = %s", (issue_id,), commit=True)
            execute_query(f"DELETE FROM {_im()} WHERE id = %s", (issue_id,), commit=True)
            flash(f'Issue {issue_number} deleted successfully.', 'success')
        else:
            flash(f'Issue {issue_number} not found.', 'error')
    except Exception as e:
        logger.error(f"Error deleting issue {issue_number}: {e}")
        flash(f'Error deleting issue: {str(e)}', 'error')
    
    return redirect(url_for(f'{BP}.view_issues'))


@bp.route('/delete-issue-item/<int:item_id>', methods=['POST'])
@module_access_required('store', LINE)
def delete_issue_item(item_id):
    """Delete a specific item from an issue."""
    try:
        # Get issue_number to redirect back to detail view
        item = execute_query(f"SELECT issue_id FROM {_ii()} WHERE id = %s", (item_id,), fetch_one=True)
        if item:
            issue_id = item['issue_id']
            issue = execute_query(f"SELECT issue_number FROM {_im()} WHERE id = %s", (issue_id,), fetch_one=True)
            if issue:
                issue_number = issue['issue_number']
                execute_query(f"DELETE FROM {_ii()} WHERE id = %s", (item_id,), commit=True)
                flash('Item deleted successfully.', 'success')
                return redirect(url_for(f'{BP}.view_issue_detail', issue_number=issue_number))
        
        flash('Item or Issue not found.', 'error')
        return redirect(url_for(f'{BP}.view_issues'))

    except Exception as e:
        logger.error(f"Error deleting issue item {item_id}: {e}")
        flash(f'Error deleting item: {str(e)}', 'error')
        return redirect(url_for(f'{BP}.view_issues'))

@bp.route('/view-issue/<issue_number>')
@module_access_required('store', LINE)
def view_issue_detail(issue_number):
    meta = execute_query(f"SELECT * FROM {_im()} WHERE issue_number = %s", (issue_number,), fetch_one=True)
    if not meta:
        flash('Issue not found', 'error')
        return redirect(url_for(f'{BP}.view_issues'))
    items = execute_query(f"SELECT part_type, part_value, part_description, footprint, qty FROM {_ii()} WHERE issue_id = %s ORDER BY id", (meta['id'],), fetch=True) or []
    return render_template(TP + 'view_issue_detail.html', issue=meta, items=items, show_nav_menu=True, accessible_modules=_accessible(), line=LINE, bp=BP)

@bp.route('/delete-item/<category>/<int:item_id>', methods=['POST'])
@module_access_required('store', LINE)
def delete_item(category, item_id):
    try:
        table_name = _store_table(category)
        execute_query(f"DELETE FROM {table_name} WHERE id = %s", (item_id,), commit=True)
        category_name = dict(CATEGORIES).get(category, category)
        flash(f'Item deleted from {category_name} successfully', 'success')
    except Exception as e:
        logger.error(f"Error deleting item {item_id} from {category}: {e}")
        flash(f'Error deleting item: {str(e)}', 'error')
    return redirect(url_for(f'{BP}.view_category', category=category))


