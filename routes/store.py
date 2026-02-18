"""Store Module Routes"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from auth import module_access_required
from database import execute_query, table_exists
from datetime import datetime
import re
import logging

logger = logging.getLogger(__name__)

def _get_accessible_modules():
    user_email = session.get('user_email')
    from auth import can_access_module
    return [m for m in ['rnd', 'production', 'supply_chain', 'qc', 'store'] if can_access_module(user_email, m)]


def _search_store_items(q, limit=20):
    """Search part_type, part_value, part_description across all store_* tables. Returns list with category, id, part_*, qty."""
    q = (q or '').strip().lower()
    if not q or len(q) < 1:
        return []
    results = []
    for cat, _ in CATEGORIES:
        table = f"store_{cat}"
        if not table_exists(table):
            continue
        sql = f"""
            SELECT id, part_type, part_value, part_description, footprint, qty
            FROM {table}
            WHERE LOWER(COALESCE(part_type,'')) LIKE %s
               OR LOWER(COALESCE(part_value,'')) LIKE %s
               OR LOWER(COALESCE(part_description,'')) LIKE %s
               OR LOWER(COALESCE(footprint,'')) LIKE %s
            ORDER BY part_type, part_value
            LIMIT %s
        """
        like = f"%{q}%"
        rows = execute_query(sql, (like, like, like, like, limit), fetch=True)
        if rows:
            for r in rows:
                r['store_category'] = cat
                results.append(r)
    return results[:limit]

def _search_boms(q, limit=30):
    """Search BOMs by name."""
    q = (q or '').strip().lower()
    if not q:
        sql = "SELECT id, bom_name, bom_type FROM bom_metadata ORDER BY bom_name LIMIT %s"
        return execute_query(sql, (limit,), fetch=True) or []
    sql = "SELECT id, bom_name, bom_type FROM bom_metadata WHERE LOWER(bom_name) LIKE %s ORDER BY bom_name LIMIT %s"
    return execute_query(sql, (f"%{q}%", limit), fetch=True) or []

def _get_bom_components(bom_id):
    """Get components of a BOM by bom_metadata id."""
    bom = execute_query("SELECT bom_name FROM bom_metadata WHERE id = %s", (bom_id,), fetch_one=True)
    if not bom:
        return None, []
    rows = execute_query(
        "SELECT part_type, part_value, part_description, footprint, qty FROM bom_items WHERE bom_id = %s",
        (bom_id,), fetch=True
    )
    return bom['bom_name'], (rows or [])

def _find_in_store(part_type, part_value, part_description, footprint):
    """Find first matching row across store tables; return (category, row) or (None, None)."""
    for cat, _ in CATEGORIES:
        table = f"store_{cat}"
        if not table_exists(table):
            continue
        sql = f"""
            SELECT id, qty FROM {table}
            WHERE COALESCE(part_type,'') = COALESCE(%s,'')
              AND COALESCE(part_value,'') = COALESCE(%s,'')
              AND COALESCE(part_description,'') = COALESCE(%s,'')
              AND COALESCE(footprint,'') = COALESCE(%s,'')
            LIMIT 1
        """
        row = execute_query(sql, (part_type, part_value, part_description, footprint), fetch_one=True)
        if row:
            return cat, row
    return None, None

bp = Blueprint('store', __name__, url_prefix='/store')

CATEGORIES = [
    ('resistors', 'Resistors'),
    ('capacitors', 'Capacitors'),
    ('diodes_transistors', 'Diodes & Transistors'),
    ('ics', 'ICs'),
    ('connectors', 'Connectors'),
    ('misc_components', 'Misc Components'),
    ('pcbs', 'PCBs'),
    ('assemblies', 'Assemblies'),
    ('misc_products', 'Misc Products')
]

@bp.route('/')
@module_access_required('store')
def store_dashboard():
    """Store dashboard"""
    user_email = session.get('user_email')
    from auth import can_access_module
    accessible_modules = []
    for module in ['rnd', 'production', 'supply_chain', 'qc', 'store']:
        if can_access_module(user_email, module):
            accessible_modules.append(module)
    
    return render_template('store/dashboard.html',
                         show_nav_menu=True,
                         accessible_modules=accessible_modules)

@bp.route('/enter-items')
@module_access_required('store')
def enter_items():
    """Enter items from QC approved"""
    query = "SELECT * FROM qc_approved ORDER BY created_at DESC"
    approved_items = execute_query(query, fetch=True)
    
    user_email = session.get('user_email')
    from auth import can_access_module
    accessible_modules = []
    for module in ['rnd', 'production', 'supply_chain', 'qc', 'store']:
        if can_access_module(user_email, module):
            accessible_modules.append(module)
    
    return render_template('store/enter_items.html',
                         approved_items=approved_items or [],
                         categories=CATEGORIES,
                         show_nav_menu=True,
                         accessible_modules=accessible_modules)

@bp.route('/add-to-store/<int:item_id>', methods=['POST'])
@module_access_required('store')
def add_to_store(item_id):
    """Add item to store inventory"""
    category = request.form.get('category', '')
    section = request.form.get('section', '')
    
    # Get item details
    query = "SELECT * FROM qc_approved WHERE id = %s"
    item = execute_query(query, (item_id,), fetch_one=True)
    
    if item and category:
        table_name = f"store_{category}"
        
        # Check if item already exists (same part_type, part_value, part_description, footprint)
        check_query = f"""
            SELECT * FROM {table_name} 
            WHERE part_type = %s 
            AND part_value = %s 
            AND part_description = %s 
            AND footprint = %s
            LIMIT 1
        """
        existing = execute_query(check_query, (item['part_type'], item['part_value'],
                                               item['part_description'], item['footprint']),
                                fetch_one=True)
        
        if existing:
            # Item exists - merge by updating quantity and appending PO number
            new_qty = existing['qty'] + item['qty']
            
            # Append PO number if not already present
            existing_po_nos = existing.get('po_no', '') or ''
            new_po = item.get('po_no', '') or ''
            
            if new_po and new_po not in existing_po_nos:
                updated_po_nos = f"{existing_po_nos}, {new_po}" if existing_po_nos else new_po
            else:
                updated_po_nos = existing_po_nos
            
            # Update existing item
            update_query = f"""
                UPDATE {table_name} 
                SET qty = %s, po_no = %s
                WHERE id = %s
            """
            execute_query(update_query, (new_qty, updated_po_nos, existing['id']), commit=True)
            flash(f'Item merged with existing inventory. New quantity: {new_qty}', 'success')
        else:
            # Item doesn't exist - insert new
            insert_query = f"""
                INSERT INTO {table_name} 
                (part_type, part_value, part_description, footprint, qty, po_no, section, project_number)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """
            execute_query(insert_query, (item['part_type'], item['part_value'],
                                         item['part_description'], item['footprint'],
                                         item['qty'], item.get('po_no', ''), section, 
                                         item.get('project_number', '')), commit=True)
            flash('Item added to store successfully', 'success')
        
        # Remove from approved
        delete_query = "DELETE FROM qc_approved WHERE id = %s"
        execute_query(delete_query, (item_id,), commit=True)
    
    return redirect(url_for('store.enter_items'))

@bp.route('/view-items')
@module_access_required('store')
def view_items():
    """View store items by category"""
    user_email = session.get('user_email')
    from auth import can_access_module
    accessible_modules = []
    for module in ['rnd', 'production', 'supply_chain', 'qc', 'store']:
        if can_access_module(user_email, module):
            accessible_modules.append(module)
    
    return render_template('store/view_items.html',
                         categories=CATEGORIES,
                         show_nav_menu=True,
                         accessible_modules=accessible_modules)

@bp.route('/view-category/<category>')
@module_access_required('store')
def view_category(category):
    """View items in a specific category"""
    table_name = f"store_{category}"
    query = f"SELECT * FROM {table_name} ORDER BY created_at DESC"
    items = execute_query(query, fetch=True)
    
    category_name = dict(CATEGORIES).get(category, category)
    
    user_email = session.get('user_email')
    from auth import can_access_module
    accessible_modules = []
    for module in ['rnd', 'production', 'supply_chain', 'qc', 'store']:
        if can_access_module(user_email, module):
            accessible_modules.append(module)
    
    return render_template('store/view_category.html',
                         items=items or [],
                         category=category,
                         category_name=category_name,
                         show_nav_menu=True,
                         accessible_modules=accessible_modules)

@bp.route('/issue-items', methods=['GET', 'POST'])
@module_access_required('store')
def issue_items():
    """Step 1: Enter issue number, PCB/assembly name, issued to, contract/project. Then redirect to select method."""
    if request.method == 'POST':
        issue_number = request.form.get('issue_number', '').strip()
        pcb_assembly_name = request.form.get('pcb_assembly_name', '').strip()
        issued_to = request.form.get('issued_to', '').strip()
        contract_project = request.form.get('contract_project', '').strip()
        if not issue_number or not pcb_assembly_name or not issued_to or not contract_project:
            flash('All fields are required', 'error')
            return redirect(url_for('store.issue_items'))
        # Check unique issue number
        existing = execute_query("SELECT 1 FROM issues_metadata WHERE issue_number = %s", (issue_number,), fetch_one=True)
        if existing:
            flash(f'Issue number "{issue_number}" already exists', 'error')
            return redirect(url_for('store.issue_items'))
        session['pending_issue'] = {
            'issue_number': issue_number,
            'pcb_assembly_name': pcb_assembly_name,
            'issued_to': issued_to,
            'contract_project': contract_project,
            'items': []
        }
        return redirect(url_for('store.issue_select_method'))
    return render_template('store/issue_items.html', show_nav_menu=True, accessible_modules=_get_accessible_modules())

@bp.route('/issue-select-method')
@module_access_required('store')
def issue_select_method():
    """Step 2: Choose 'Select from BOM' or 'Select separate items'."""
    if not session.get('pending_issue'):
        flash('Please start by entering issue details', 'error')
        return redirect(url_for('store.issue_items'))
    return render_template('store/issue_select_method.html', show_nav_menu=True, accessible_modules=_get_accessible_modules())

@bp.route('/issue-add-separate')
@module_access_required('store')
def issue_add_separate():
    """Add items from store (predictive search, select item, enter qty, add another)."""
    if not session.get('pending_issue'):
        flash('Please start by entering issue details', 'error')
        return redirect(url_for('store.issue_items'))
    return render_template('store/issue_add_separate.html', show_nav_menu=True, accessible_modules=_get_accessible_modules())

@bp.route('/issue-add-from-bom')
@module_access_required('store')
def issue_add_from_bom():
    """Select a BOM; add all components that exist in store; show which are not in store."""
    if not session.get('pending_issue'):
        flash('Please start by entering issue details', 'error')
        return redirect(url_for('store.issue_items'))
    boms = execute_query("SELECT id, bom_name, bom_type FROM bom_metadata ORDER BY bom_name", fetch=True)
    return render_template('store/issue_add_from_bom.html', boms=boms or [], show_nav_menu=True, accessible_modules=_get_accessible_modules())

@bp.route('/api/pending-items')
@module_access_required('store')
def api_pending_items():
    """Return current pending issue items (for JS table refresh)."""
    pending = session.get('pending_issue')
    if not pending:
        return jsonify({'items': []})
    return jsonify({'items': pending.get('items', [])})

@bp.route('/api/available-for-store-item')
@module_access_required('store')
def api_available_for_store_item():
    """Return available qty for a store row (store qty minus already in pending issue)."""
    store_category = (request.args.get('store_category') or '').strip()
    store_id = request.args.get('store_id')
    if not store_category or not store_id:
        return jsonify({'error': 'Missing store_category or store_id'}), 400
    table = f"store_{store_category}"
    if not table_exists(table):
        return jsonify({'error': 'Invalid category'}), 400
    row = execute_query(
        f"SELECT qty FROM {table} WHERE id = %s",
        (store_id,), fetch_one=True
    )
    if not row:
        return jsonify({'error': 'Item not found'}), 404
    store_qty = int(row.get('qty', 0) or 0)
    already = _pending_reserved_for_store_row(store_category, store_id)
    available = max(0, store_qty - already)
    return jsonify({'available': available, 'store_qty': store_qty, 'already_in_issue': already})

@bp.route('/api/search-store-items')
@module_access_required('store')
def api_search_store_items():
    """Predictive search: part_type, part_value, part_description across store."""
    q = request.args.get('q', '')
    results = _search_store_items(q, limit=25)
    return jsonify({'items': results})

@bp.route('/api/search-boms')
@module_access_required('store')
def api_search_boms():
    """Predictive search BOMs by name."""
    q = request.args.get('q', '')
    results = _search_boms(q, limit=30)
    return jsonify({'boms': results})

@bp.route('/api/search-issues')
@module_access_required('store')
def api_search_issues():
    """Predictive search issues by contract/project, issue number, or issued to."""
    q = (request.args.get('q') or '').strip().lower()
    if not q:
        # Return recent 50 if no query
        sql = "SELECT * FROM issues_metadata ORDER BY created_at DESC LIMIT 50"
        results = execute_query(sql, fetch=True)
    else:
        # Search multiple fields
        sql = """
            SELECT * FROM issues_metadata 
            WHERE LOWER(COALESCE(contract_project,'')) LIKE %s 
               OR LOWER(COALESCE(issue_number,'')) LIKE %s
               OR LOWER(COALESCE(issued_to,'')) LIKE %s
               OR LOWER(COALESCE(pcb_assembly_name,'')) LIKE %s
            ORDER BY created_at DESC LIMIT 50
        """
        like = f"%{q}%"
        results = execute_query(sql, (like, like, like, like), fetch=True)
    
    # Format dates
    if results:
        for r in results:
            if r.get('date_issued'):
                r['date_issued'] = str(r['date_issued'])
            if r.get('created_at'):
                r['created_at'] = r['created_at'].strftime('%Y-%m-%d %H:%M:%S')

    return jsonify({'issues': results or []})

@bp.route('/delete-issue/<issue_number>', methods=['POST'])
@module_access_required('store')
def delete_issue(issue_number):
    """Delete an issue and its items."""
    try:
        # Get Issue ID first to delete items
        issue = execute_query("SELECT id FROM issues_metadata WHERE issue_number = %s", (issue_number,), fetch_one=True)
        if issue:
            issue_id = issue['id']
            execute_query("DELETE FROM issue_items WHERE issue_id = %s", (issue_id,), commit=True)
            execute_query("DELETE FROM issues_metadata WHERE id = %s", (issue_id,), commit=True)
            flash(f'Issue {issue_number} deleted successfully.', 'success')
        else:
            flash(f'Issue {issue_number} not found.', 'error')
    except Exception as e:
        logger.error(f"Error deleting issue {issue_number}: {e}")
        flash(f'Error deleting issue: {str(e)}', 'error')
    
    return redirect(url_for('store.view_issues'))

@bp.route('/delete-issue-item/<int:item_id>', methods=['POST'])
@module_access_required('store')
def delete_issue_item(item_id):
    """Delete a specific item from an issue."""
    try:
        # Get issue_number to redirect back to detail view
        # We need to find the issue_id first from the item, then the issue_number from metadata
        item = execute_query("SELECT issue_id FROM issue_items WHERE id = %s", (item_id,), fetch_one=True)
        if item:
            issue_id = item['issue_id']
            issue = execute_query("SELECT issue_number FROM issues_metadata WHERE id = %s", (issue_id,), fetch_one=True)
            if issue:
                issue_number = issue['issue_number']
                execute_query("DELETE FROM issue_items WHERE id = %s", (item_id,), commit=True)
                flash('Item deleted successfully.', 'success')
                return redirect(url_for('store.view_issue_detail', issue_number=issue_number))
        
        flash('Item or Issue not found.', 'error')
        return redirect(url_for('store.view_issues'))

    except Exception as e:
        logger.error(f"Error deleting issue item {item_id}: {e}")
        flash(f'Error deleting item: {str(e)}', 'error')
        return redirect(url_for('store.view_issues'))

@bp.route('/api/bom-components/<int:bom_id>')
@module_access_required('store')
def api_bom_components(bom_id):
    """Get BOM components and match with store. Query param qty = number of BOM sets (multiplier).
    Only components with store stock > 0 are in in_store; issue_qty = min(required, store_qty)."""
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
        bom_qty_per = c.get('qty', 0) or 0
        required = bom_qty_per * bom_qty_mult
        cat, row = _find_in_store(c.get('part_type'), c.get('part_value'), c.get('part_description'), c.get('footprint'))
        if cat and row:
            store_qty = row.get('qty', 0) or 0
            if store_qty <= 0:
                missing.append({
                    'part_type': c.get('part_type'),
                    'part_value': c.get('part_value'),
                    'part_description': c.get('part_description'),
                    'footprint': c.get('footprint'),
                    'qty': required
                })
                continue
            issue_qty = min(required, store_qty)
            out.append({
                'part_type': c.get('part_type'),
                'part_value': c.get('part_value'),
                'part_description': c.get('part_description'),
                'footprint': c.get('footprint'),
                'bom_qty': bom_qty_per,
                'required': required,
                'store_qty': store_qty,
                'issue_qty': issue_qty,
                'store_category': cat,
                'store_id': row.get('id'),
                'in_store': True,
                'insufficient': issue_qty < required
            })
        else:
            missing.append({
                'part_type': c.get('part_type'),
                'part_value': c.get('part_value'),
                'part_description': c.get('part_description'),
                'footprint': c.get('footprint'),
                'qty': required
            })
    return jsonify({'bom_name': bom_name, 'bom_qty': bom_qty_mult, 'in_store': out, 'missing': missing})

@bp.route('/issue-add-item', methods=['POST'])
@module_access_required('store')
def issue_add_item():
    """Add one item to pending issue (from separate items flow). Merges with existing same store row.
    Only adds up to available (store qty minus already in pending). Expects store_category, store_id, qty."""
    if not session.get('pending_issue'):
        return jsonify({'error': 'No pending issue'}), 400
    data = request.get_json() or request.form
    store_category = (data.get('store_category') or '').strip()
    store_id = data.get('store_id')
    want_qty = int(data.get('qty', 0) or 0)
    if not store_category or not store_id or want_qty <= 0:
        return jsonify({'error': 'Invalid store_category, store_id, or qty'}), 400
    table = f"store_{store_category}"
    if not table_exists(table):
        return jsonify({'error': 'Invalid category'}), 400
    row = execute_query(
        f"SELECT id, part_type, part_value, part_description, footprint, qty FROM {table} WHERE id = %s",
        (store_id,), fetch_one=True
    )
    if not row:
        return jsonify({'error': 'Item not found'}), 404
    store_qty = int(row.get('qty', 0) or 0)
    already = _pending_reserved_for_store_row(store_category, store_id)
    available = max(0, store_qty - already)
    to_add = min(want_qty, available)
    if to_add <= 0:
        return jsonify({
            'error': f'Only {store_qty} in store and {already} already in this issue. Nothing more can be added.'
        }), 400
    pending = session['pending_issue']['items']
    existing_idx = None
    for i, p in enumerate(pending):
        if p.get('store_category') == store_category and p.get('store_id') == store_id:
            existing_idx = i
            break
    if existing_idx is not None:
        pending[existing_idx]['qty'] = int(pending[existing_idx].get('qty', 0) or 0) + to_add
    else:
        pending.append({
            'part_type': row.get('part_type') or '',
            'part_value': row.get('part_value') or '',
            'part_description': row.get('part_description') or '',
            'footprint': row.get('footprint') or '',
            'qty': to_add,
            'store_category': store_category,
            'store_id': store_id
        })
    session.modified = True
    resp = {'success': True, 'items': session['pending_issue']['items']}
    if to_add < want_qty:
        resp['message'] = f'Added {to_add} (only {available} available; {already} already in this issue).'
    return jsonify(resp)

def _pending_reserved_for_store_row(store_category, store_id):
    """Sum qty already in pending issue for this store row."""
    total = 0
    for it in (session.get('pending_issue') or {}).get('items', []):
        if (it.get('store_category') == store_category and it.get('store_id') == store_id):
            total += int(it.get('qty', 0) or 0)
    return total

@bp.route('/issue-add-bom-items', methods=['POST'])
@module_access_required('store')
def issue_add_bom_items():
    """Add BOM-matched items to pending issue. Merges with existing: same store row gets qty added.
    Only adds up to available (store qty minus already in pending)."""
    if not session.get('pending_issue'):
        return jsonify({'error': 'No pending issue'}), 400
    data = request.get_json() or request.form
    items = data.get('items', []) if isinstance(data.get('items'), list) else []
    pending = session['pending_issue']['items']
    for it in items:
        store_category = (it.get('store_category') or '').strip()
        store_id = it.get('store_id')
        want_qty = int(it.get('qty', 0) or 0)
        if not store_category or not store_id or want_qty <= 0:
            continue
        table = f"store_{store_category}"
        if not table_exists(table):
            continue
        row = execute_query(
            f"SELECT id, part_type, part_value, part_description, footprint, qty FROM {table} WHERE id = %s",
            (store_id,), fetch_one=True
        )
        if not row:
            continue
        store_qty = int(row.get('qty', 0) or 0)
        already = _pending_reserved_for_store_row(store_category, store_id)
        available = max(0, store_qty - already)
        to_add = min(want_qty, available)
        if to_add <= 0:
            continue
        existing_idx = None
        for i, p in enumerate(pending):
            if p.get('store_category') == store_category and p.get('store_id') == store_id:
                existing_idx = i
                break
        if existing_idx is not None:
            pending[existing_idx]['qty'] = int(pending[existing_idx].get('qty', 0) or 0) + to_add
        else:
            pending.append({
                'part_type': row.get('part_type') or '',
                'part_value': row.get('part_value') or '',
                'part_description': row.get('part_description') or '',
                'footprint': row.get('footprint') or '',
                'qty': to_add,
                'store_category': store_category,
                'store_id': store_id
            })
    session.modified = True
    return jsonify({'success': True, 'items': session['pending_issue']['items']})

@bp.route('/issue-submit', methods=['POST'])
@module_access_required('store')
def issue_submit():
    """Create issue in DB, deduct from store, clear session."""
    pending = session.get('pending_issue')
    if not pending:
        flash('No pending issue to submit', 'error')
        return redirect(url_for('store.issue_items'))
    items = pending.get('items') or []
    if not items:
        flash('Add at least one item before issuing', 'error')
        return redirect(url_for('store.issue_add_separate'))
    issue_number = pending['issue_number']
    date_issued = datetime.now().strftime('%Y-%m-%d')
    insert_meta = """
        INSERT INTO issues_metadata (issue_number, pcb_assembly_name, date_issued, issued_to, contract_project)
        VALUES (%s, %s, %s, %s, %s)
    """
    execute_query(insert_meta, (
        issue_number, pending['pcb_assembly_name'], date_issued,
        pending['issued_to'], pending['contract_project']
    ), commit=True)
    meta_row = execute_query("SELECT id FROM issues_metadata WHERE issue_number = %s", (issue_number,), fetch_one=True)
    issue_id = meta_row['id'] if meta_row else None
    if not issue_id:
        flash('Failed to create issue', 'error')
        return redirect(url_for('store.issue_add_separate'))
    for it in items:
        execute_query(
            "INSERT INTO issue_items (issue_id, part_type, part_value, part_description, footprint, qty) VALUES (%s, %s, %s, %s, %s, %s)",
            (issue_id, it['part_type'], it['part_value'], it['part_description'], it['footprint'], it['qty']),
            commit=True
        )
        st = f"store_{it['store_category']}"
        execute_query(f"UPDATE {st} SET qty = qty - %s WHERE id = %s", (it['qty'], it['store_id']), commit=True)
    session.pop('pending_issue', None)
    flash(f'Issue {issue_number} created successfully', 'success')
    return redirect(url_for('store.view_issues'))

@bp.route('/view-issues')
@module_access_required('store')
def view_issues():
    """View all issues; predictive search by contract/project name."""
    q = request.args.get('q', '').strip()
    if q:
        sql = "SELECT * FROM issues_metadata WHERE LOWER(COALESCE(contract_project,'')) LIKE %s ORDER BY created_at DESC"
        issues = execute_query(sql, (f"%{q.lower()}%",), fetch=True)
    else:
        issues = execute_query("SELECT * FROM issues_metadata ORDER BY created_at DESC", fetch=True)
    return render_template('store/view_issues.html', issues=issues or [], search_q=q, show_nav_menu=True, accessible_modules=_get_accessible_modules())

@bp.route('/view-issue/<issue_number>')
@module_access_required('store')
def view_issue_detail(issue_number):
    """View components table for one issue."""
    meta = execute_query("SELECT * FROM issues_metadata WHERE issue_number = %s", (issue_number,), fetch_one=True)
    if not meta:
        flash('Issue not found', 'error')
        return redirect(url_for('store.view_issues'))
    items = execute_query(
        "SELECT part_type, part_value, part_description, footprint, qty FROM issue_items WHERE issue_id = %s ORDER BY id",
        (meta['id'],), fetch=True
    ) or []
    return render_template('store/view_issue_detail.html', issue=meta, items=items, show_nav_menu=True, accessible_modules=_get_accessible_modules())

# Delete routes for all store categories
@bp.route('/delete-item/<category>/<int:item_id>', methods=['POST'])
@module_access_required('store')
def delete_item(category, item_id):
    """Delete an item from store inventory"""
    try:
        table_name = f"store_{category}"
        delete_query = f"DELETE FROM {table_name} WHERE id = %s"
        execute_query(delete_query, (item_id,), commit=True)
        
        category_name = dict(CATEGORIES).get(category, category)
        flash(f'Item deleted from {category_name} successfully', 'success')
    except Exception as e:
        logger.error(f"Error deleting item {item_id} from {category}: {e}")
        flash(f'Error deleting item: {str(e)}', 'error')
    
    return redirect(url_for('store.view_category', category=category))



