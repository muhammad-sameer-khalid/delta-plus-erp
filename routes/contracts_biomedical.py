"""Contracts module: metadata + items, inspection, delivery, CRV, payment, display."""
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from auth import module_access_required
from database import execute_query
from datetime import datetime, date, timedelta
import logging

logger = logging.getLogger(__name__)

LINE = 'biomedical'
BP = 'contracts_biomedical'
SESSION_KEY = 'contracts_pending_metadata_biomedical'

from routes.line_tables import tbl
def _cm(): return tbl(LINE, 'contracts_metadata')
def _ci(): return tbl(LINE, 'contract_items')

bp = Blueprint(BP, __name__, url_prefix='/biomedical/contracts')
TP = 'line_contracts/'


def _contracts_access_required(f):
    """Allow access for director, general manager, gm logistics (no single module)."""
    from functools import wraps
    from auth import can_access_contracts
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_email' not in session:
            flash('Please log in', 'error')
            return redirect(url_for('login'))
        if not can_access_contracts(session['user_email'], LINE):
            flash('You do not have permission to access Contracts', 'error')
            return redirect(url_for('biomedical_dashboard'))
        return f(*args, **kwargs)
    return decorated

def _get_accessible_modules():
    from auth import can_access_module
    user_email = session.get('user_email')
    return [m for m in ['rnd', 'production', 'supply_chain', 'qc', 'store'] if can_access_module(user_email, m, LINE)]



@bp.route('/api/search-contracts')
@_contracts_access_required
def api_search_contracts():
    """Predictive search contracts by number."""
    q = (request.args.get('q') or '').strip()
    from flask import jsonify

    base_query = f"SELECT * FROM {_cm()}"
    params = []
    
    if q:
        base_query += " WHERE contract_no LIKE %s"
        params.append(f'%{q}%')
    
    base_query += " ORDER BY contract_no"
    
    
    contracts = execute_query(base_query, tuple(params), fetch=True) or []
    # Format dates to string YYYY-MM-DD to match server-side rendering
    for c in contracts:
        if c.get('contract_date'):
            c['contract_date'] = str(c['contract_date'])
        if c.get('bg_expiry_date'):
            c['bg_expiry_date'] = str(c['bg_expiry_date'])
        if c.get('delivery_deadline'):
            c['delivery_deadline'] = str(c['delivery_deadline'])
            
    return jsonify({'contracts': contracts})

@bp.route('/api/search-contract-items/<int:contract_id>')
@_contracts_access_required
def api_search_contract_items(contract_id):
    """Predictive search items within a contract."""
    q = (request.args.get('q') or '').strip().lower()
    from flask import jsonify

    base_query = f"SELECT * FROM {_ci()} WHERE contract_id = %s"
    params = [contract_id]
    
    if q:
        base_query += " AND (LOWER(COALESCE(item_name,'')) LIKE %s OR LOWER(COALESCE(part_number,'')) LIKE %s)"
        like = f"%{q}%"
        params.extend([like, like])
    
    base_query += " ORDER BY item_id"
    
    items = execute_query(base_query, tuple(params), fetch=True) or []
    return jsonify({'items': items})

@bp.route('/')
@_contracts_access_required
def contracts_dashboard():
    """Contracts dashboard with 6 cards."""
    return render_template(TP + 'dashboard.html', show_nav_menu=True, accessible_modules=_get_accessible_modules(), line=LINE, bp=BP)


# ========== 1. Input a contract ==========
@bp.route('/input-contract', methods=['GET', 'POST'])
@_contracts_access_required
def input_contract():
    if request.method == 'POST':
        contract_no = (request.form.get('contract_no') or '').strip()
        contract_date = request.form.get('contract_date', '').strip()
        contract_type = request.form.get('contract_type', 'manufacturing').strip()
        if contract_type not in ('manufacturing', 'supply'):
            contract_type = 'manufacturing'
        try:
            total_value = float(request.form.get('total_value') or 0)
        except Exception:
            total_value = 0
        delivery_deadline = request.form.get('delivery_deadline', '').strip()
        bg_number = (request.form.get('bg_number') or '').strip()
        try:
            bg_amount = float(request.form.get('bg_amount') or 0)
        except Exception:
            bg_amount = 0
        bg_expiry_date = (request.form.get('bg_expiry_date') or '').strip() or None

        bg_type_list = request.form.getlist('bg_type')
        bg_type = ', '.join(bg_type_list) if bg_type_list else None
        department = (request.form.get('department') or '').strip()

        if not contract_no or not contract_date or not delivery_deadline:
            flash('Contract No., Contract Date and Delivery Deadline are required', 'error')
            return redirect(url_for(f'{BP}.input_contract'))
        if not bg_number:
            flash('BG Number is required', 'error')
            return redirect(url_for(f'{BP}.input_contract'))
        if total_value <= 0:
            flash('Total Value must be greater than 0', 'error')
            return redirect(url_for(f'{BP}.input_contract'))
        if not bg_expiry_date:
            flash('BG Expiry Date is required', 'error')
            return redirect(url_for(f'{BP}.input_contract'))
        if bg_amount <= 0:
            flash('BG Amount must be greater than 0', 'error')
            return redirect(url_for(f'{BP}.input_contract'))
        if not department:
            flash('Department is required', 'error')
            return redirect(url_for(f'{BP}.input_contract'))

        existing = execute_query(f"SELECT 1 FROM {_cm()} WHERE contract_no = %s", (contract_no,), fetch_one=True)
        if existing:
            flash(f'Contract number "{contract_no}" already exists', 'error')
            return redirect(url_for(f'{BP}.input_contract'))

        # Do not save to DB yet; store in session until user adds items and clicks Save
        session[SESSION_KEY] = {
            'contract_no': contract_no,
            'contract_date': contract_date,
            'contract_type': contract_type,
            'total_value': total_value,
            'delivery_deadline': delivery_deadline,
            'bg_number': bg_number,
            'bg_amount': bg_amount,
            'bg_expiry_date': bg_expiry_date,
            'bg_type': bg_type,
            'department': department,
        }
        flash('Enter items below, then click Save to save the contract and all items.', 'success')
        return redirect(url_for(f'{BP}.input_contract_items_new'))

    return render_template(TP + 'input_contract.html', show_nav_menu=True, accessible_modules=_get_accessible_modules(), line=LINE, bp=BP)


@bp.route('/input-contract-items', methods=['GET', 'POST'])
@_contracts_access_required
def input_contract_items_new():
    """Add items for a new contract (metadata in session). Contract is saved only when user clicks Save here."""
    pending = session.get(SESSION_KEY)
    if not pending:
        flash('Please enter contract details first.', 'error')
        return redirect(url_for(f'{BP}.input_contract'))

    if request.method == 'POST':
        # Validate items and collect them
        i = 0
        items_data = []
        while request.form.get(f'item_name_{i}') is not None:
            item_name = (request.form.get(f'item_name_{i}') or '').strip()
            part_number = (request.form.get(f'part_number_{i}') or '').strip() or None
            try:
                qty = int(request.form.get(f'qty_{i}') or 0)
            except Exception:
                qty = 0
            try:
                unit_price = float(request.form.get(f'unit_price_{i}') or 0)
            except Exception:
                unit_price = 0
            if not item_name and not part_number and qty == 0 and unit_price == 0:
                i += 1
                continue
            if not item_name:
                flash('Item name is required for every item', 'error')
                return redirect(url_for(f'{BP}.input_contract_items_new'))
            if qty <= 0:
                flash('Qty must be greater than 0 for every item', 'error')
                return redirect(url_for(f'{BP}.input_contract_items_new'))
            if unit_price < 0:
                flash('Unit price cannot be negative', 'error')
                return redirect(url_for(f'{BP}.input_contract_items_new'))
            total_price = round(qty * unit_price, 2)
            items_data.append((item_name, part_number, qty, unit_price, total_price, qty))
            i += 1

        if not items_data:
            flash('At least one item is required with all fields (Item name, Part number, Qty, Unit price) filled.', 'error')
            return redirect(url_for(f'{BP}.input_contract_items_new'))

        # Save contract and items together
        contract_no = pending['contract_no']
        contract_date = pending['contract_date']
        contract_type = pending['contract_type']
        total_value = pending['total_value']
        delivery_deadline = pending['delivery_deadline']
        bg_number = pending['bg_number']
        bg_amount = pending['bg_amount']
        bg_expiry_date = pending['bg_expiry_date']
        bg_type = pending.get('bg_type')
        department = pending.get('department')

        execute_query(f"""
            INSERT INTO {_cm()}
            (contract_no, contract_date, contract_type, total_value, delivery_deadline, bg_number, bg_amount, bg_expiry_date, bg_type, department, contract_status, amount_given, amount_balance)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'active', 0, %s)
        """, (contract_no, contract_date, contract_type, total_value, delivery_deadline, bg_number, bg_amount, bg_expiry_date, bg_type, department, total_value), commit=True)
        meta = execute_query(f"SELECT contract_id FROM {_cm()} WHERE contract_no = %s", (contract_no,), fetch_one=True)
        contract_id = meta['contract_id']

        for item_name, part_number, qty, unit_price, total_price, deliver_balance in items_data:
            execute_query(f"""
                INSERT INTO {_ci()} (contract_id, item_name, part_number, qty, unit_price, total_price, delivered_qty, deliver_balance)
                VALUES (%s, %s, %s, %s, %s, %s, 0, %s)
            """, (contract_id, item_name, part_number, qty, unit_price, total_price, deliver_balance), commit=True)

        session.pop(SESSION_KEY, None)
        session.pop('contracts_new_contract_id', None)
        flash('Contract and items saved.', 'success')
        return redirect(url_for(f'{BP}.contracts_dashboard'))

    # GET: show items form; contract is from session (no contract_id yet)
    return render_template(TP + 'input_contract_items.html', contract=pending, contract_id=None, existing_items=[],
                           show_nav_menu=True, accessible_modules=_get_accessible_modules(), line=LINE, bp=BP)


@bp.route('/input-contract-items/<int:contract_id>', methods=['GET', 'POST'])
@_contracts_access_required
def input_contract_items(contract_id):
    """Add items to an existing contract (e.g. from a link)."""
    meta = execute_query(f"SELECT * FROM {_cm()} WHERE contract_id = %s", (contract_id,), fetch_one=True)
    if not meta:
        flash('Contract not found', 'error')
        return redirect(url_for(f'{BP}.contracts_dashboard'))

    if request.method == 'POST':
        i = 0
        item_count = 0
        while request.form.get(f'item_name_{i}') is not None:
            item_name = (request.form.get(f'item_name_{i}') or '').strip()
            part_number = (request.form.get(f'part_number_{i}') or '').strip() or None
            try:
                qty = int(request.form.get(f'qty_{i}') or 0)
            except Exception:
                qty = 0
            try:
                unit_price = float(request.form.get(f'unit_price_{i}') or 0)
            except Exception:
                unit_price = 0
            if not item_name and not part_number and qty == 0 and unit_price == 0:
                i += 1
                continue
            if not item_name:
                flash('Item name is required for every item', 'error')
                return redirect(url_for(f'{BP}.input_contract_items', contract_id=contract_id))
            if qty <= 0:
                flash('Qty must be greater than 0 for every item', 'error')
                return redirect(url_for(f'{BP}.input_contract_items', contract_id=contract_id))
            if unit_price < 0:
                flash('Unit price cannot be negative', 'error')
                return redirect(url_for(f'{BP}.input_contract_items', contract_id=contract_id))
            total_price = round(qty * unit_price, 2)
            deliver_balance = qty
            execute_query(f"""
                INSERT INTO {_ci()} (contract_id, item_name, part_number, qty, unit_price, total_price, delivered_qty, deliver_balance)
                VALUES (%s, %s, %s, %s, %s, %s, 0, %s)
            """, (contract_id, item_name, part_number, qty, unit_price, total_price, deliver_balance), commit=True)
            item_count += 1
            i += 1
        if item_count == 0:
            flash('At least one item is required with all fields (Item name, Part number, Qty, Unit price) filled.', 'error')
            return redirect(url_for(f'{BP}.input_contract_items', contract_id=contract_id))
        session.pop('contracts_new_contract_id', None)
        flash('Items saved.', 'success')
        return redirect(url_for(f'{BP}.contracts_dashboard'))

    existing_items = execute_query(f"SELECT * FROM {_ci()} WHERE contract_id = %s ORDER BY item_id", (contract_id,), fetch=True) or []
    return render_template(TP + 'input_contract_items.html', contract=meta, contract_id=contract_id, existing_items=existing_items,
                           show_nav_menu=True, accessible_modules=_get_accessible_modules(), line=LINE, bp=BP)


# ========== 2. Input inspection info ==========
@bp.route('/input-inspection')
@_contracts_access_required
def input_inspection_list():
    q = (request.args.get('q') or '').strip()
    if q:
        contracts = execute_query(f"SELECT * FROM {_cm()} WHERE contract_no LIKE %s ORDER BY contract_no", (f'%{q}%',), fetch=True) or []
    else:
        contracts = execute_query(f"SELECT * FROM {_cm()} ORDER BY contract_no", fetch=True) or []
    return render_template(TP + 'select_contract.html', contracts=contracts, search_q=q, mode='inspection',
                           show_nav_menu=True, accessible_modules=_get_accessible_modules(), line=LINE, bp=BP)


@bp.route('/input-inspection/<int:contract_id>')
@_contracts_access_required
def input_inspection_choose(contract_id):
    meta = execute_query(f"SELECT * FROM {_cm()} WHERE contract_id = %s", (contract_id,), fetch_one=True)
    if not meta:
        flash('Contract not found', 'error')
        return redirect(url_for(f'{BP}.input_inspection_list'))
    items = execute_query(f"SELECT * FROM {_ci()} WHERE contract_id = %s ORDER BY item_id", (contract_id,), fetch=True) or []
    iterate_url = url_for(f'{BP}.input_inspection_iterate', contract_id=contract_id)
    specific_url = url_for(f'{BP}.input_inspection_specific', contract_id=contract_id)
    return render_template(TP + 'inspection_choose.html', contract=meta, items=items, mode='inspection',
                           iterate_url=iterate_url, specific_url=specific_url,
                           show_nav_menu=True, accessible_modules=_get_accessible_modules(), line=LINE, bp=BP)


@bp.route('/input-inspection/<int:contract_id>/iterate', methods=['GET', 'POST'])
@_contracts_access_required
def input_inspection_iterate(contract_id):
    meta = execute_query(f"SELECT * FROM {_cm()} WHERE contract_id = %s", (contract_id,), fetch_one=True)
    if not meta:
        flash('Contract not found', 'error')
        return redirect(url_for(f'{BP}.input_inspection_list'))
    items = execute_query(f"SELECT * FROM {_ci()} WHERE contract_id = %s ORDER BY item_id", (contract_id,), fetch=True) or []
    if request.method == 'POST':
        item_id = request.form.get('item_id', type=int)
        inspection_note_no = (request.form.get('inspection_note_no') or '').strip()
        inspection_note_date = (request.form.get('inspection_note_date') or '').strip() or None
        execute_query(f"UPDATE {_ci()} SET inspection_note_no = %s, inspection_note_date = %s WHERE item_id = %s AND contract_id = %s",
                      (inspection_note_no or None, inspection_note_date, item_id, contract_id), commit=True)
        index = request.form.get('next_index', type=int)
        if index >= len(items):
            flash('Inspection info saved for all items.', 'success')
            return redirect(url_for(f'{BP}.input_inspection_choose', contract_id=contract_id))
        return redirect(url_for(f'{BP}.input_inspection_iterate', contract_id=contract_id, index=index))
    index = int(request.args.get('index', 0))
    if index >= len(items):
        flash('Inspection info saved for all items.', 'success')
        return redirect(url_for(f'{BP}.input_inspection_choose', contract_id=contract_id))
    return render_template(TP + 'inspection_form.html', contract=meta, item=items[index], item_index=index, total_items=len(items), mode='inspection',
                           show_nav_menu=True, accessible_modules=_get_accessible_modules(), line=LINE, bp=BP)


@bp.route('/input-inspection/<int:contract_id>/item/<int:item_id>', methods=['GET', 'POST'])
@_contracts_access_required
def input_inspection_item(contract_id, item_id):
    meta = execute_query(f"SELECT * FROM {_cm()} WHERE contract_id = %s", (contract_id,), fetch_one=True)
    item = execute_query(f"SELECT * FROM {_ci()} WHERE contract_id = %s AND item_id = %s", (contract_id, item_id), fetch_one=True)
    if not meta or not item:
        flash('Not found', 'error')
        return redirect(url_for(f'{BP}.input_inspection_choose', contract_id=contract_id))
    if request.method == 'POST':
        inspection_note_no = (request.form.get('inspection_note_no') or '').strip()
        inspection_note_date = (request.form.get('inspection_note_date') or '').strip() or None
        execute_query(f"UPDATE {_ci()} SET inspection_note_no = %s, inspection_note_date = %s WHERE item_id = %s",
                      (inspection_note_no or None, inspection_note_date, item_id), commit=True)
        flash('Saved.', 'success')
        return redirect(url_for(f'{BP}.input_inspection_specific', contract_id=contract_id))
    return render_template(TP + 'inspection_form.html', contract=meta, item=item, item_index=0, total_items=1, mode='inspection', single=True,
                           show_nav_menu=True, accessible_modules=_get_accessible_modules(), line=LINE, bp=BP)


@bp.route('/input-inspection/<int:contract_id>/specific')
@_contracts_access_required
def input_inspection_specific(contract_id):
    meta = execute_query(f"SELECT * FROM {_cm()} WHERE contract_id = %s", (contract_id,), fetch_one=True)
    if not meta:
        flash('Contract not found', 'error')
        return redirect(url_for(f'{BP}.input_inspection_list'))
    q = (request.args.get('q') or '').strip()
    items = execute_query(f"SELECT * FROM {_ci()} WHERE contract_id = %s ORDER BY item_id", (contract_id,), fetch=True) or []
    if q:
        ql = q.lower()
        items = [i for i in items if (i.get('item_name') or '').lower().find(ql) >= 0 or (i.get('part_number') or '').lower().find(ql) >= 0]
    return render_template(TP + 'specific_items_list.html', contract=meta, items=items, search_q=q, mode='inspection',
                           show_nav_menu=True, accessible_modules=_get_accessible_modules(), line=LINE, bp=BP)


# ========== 3. Input delivery info ==========
@bp.route('/input-delivery')
@_contracts_access_required
def input_delivery_list():
    q = (request.args.get('q') or '').strip()
    if q:
        contracts = execute_query(f"SELECT * FROM {_cm()} WHERE contract_no LIKE %s ORDER BY contract_no", (f'%{q}%',), fetch=True) or []
    else:
        contracts = execute_query(f"SELECT * FROM {_cm()} ORDER BY contract_no", fetch=True) or []
    return render_template(TP + 'select_contract.html', contracts=contracts, search_q=q, mode='delivery',
                           show_nav_menu=True, accessible_modules=_get_accessible_modules(), line=LINE, bp=BP)


@bp.route('/input-delivery/<int:contract_id>')
@_contracts_access_required
def input_delivery_choose(contract_id):
    meta = execute_query(f"SELECT * FROM {_cm()} WHERE contract_id = %s", (contract_id,), fetch_one=True)
    if not meta:
        flash('Contract not found', 'error')
        return redirect(url_for(f'{BP}.input_delivery_list'))
    items = execute_query(f"SELECT * FROM {_ci()} WHERE contract_id = %s ORDER BY item_id", (contract_id,), fetch=True) or []
    iterate_url = url_for(f'{BP}.input_delivery_iterate', contract_id=contract_id)
    specific_url = url_for(f'{BP}.input_delivery_specific', contract_id=contract_id)
    return render_template(TP + 'inspection_choose.html', contract=meta, items=items, mode='delivery',
                           iterate_url=iterate_url, specific_url=specific_url,
                           show_nav_menu=True, accessible_modules=_get_accessible_modules(), line=LINE, bp=BP)


@bp.route('/input-delivery/<int:contract_id>/iterate', methods=['GET', 'POST'])
@_contracts_access_required
def input_delivery_iterate(contract_id):
    meta = execute_query(f"SELECT * FROM {_cm()} WHERE contract_id = %s", (contract_id,), fetch_one=True)
    if not meta:
        flash('Contract not found', 'error')
        return redirect(url_for(f'{BP}.input_delivery_list'))
    items = execute_query(f"SELECT * FROM {_ci()} WHERE contract_id = %s ORDER BY item_id", (contract_id,), fetch=True) or []
    index = int(request.args.get('index', 0))
    if request.method == 'POST' and index < len(items):
        item_id = request.form.get('item_id', type=int)
        try:
            delivered_amount = int(request.form.get('delivered_amount') or 0)
        except Exception:
            delivered_amount = 0
        delivery_no = (request.form.get('delivery_no') or '').strip()
        delivery_date = (request.form.get('delivery_date') or '').strip() or None
        row = execute_query(f"SELECT delivered_qty, qty FROM {_ci()} WHERE item_id = %s", (item_id,), fetch_one=True)
        if row:
            current_delivered = row.get('delivered_qty') or 0
            total_qty = row.get('qty') or 0
            remaining_balance = total_qty - current_delivered
            
            if delivered_amount > remaining_balance:
                flash(f'Error: Delivery amount ({delivered_amount}) exceeds remaining balance ({remaining_balance})', 'error')
                return redirect(url_for(f'{BP}.input_delivery_iterate', contract_id=contract_id, index=index))

            new_delivered = current_delivered + delivered_amount
            deliver_balance = max(0, total_qty - new_delivered)
            execute_query(f"UPDATE {_ci()} SET delivered_qty = %s, deliver_balance = %s, delivery_no = %s, delivery_date = %s WHERE item_id = %s",
                          (new_delivered, deliver_balance, delivery_no or None, delivery_date, item_id), commit=True)
        next_index = request.form.get('next_index', type=int)
        if next_index >= len(items):
            flash('Delivery info saved for all items.', 'success')
            return redirect(url_for(f'{BP}.input_delivery_choose', contract_id=contract_id))
        return redirect(url_for(f'{BP}.input_delivery_iterate', contract_id=contract_id, index=next_index))
    if index >= len(items):
        flash('Delivery info saved for all items.', 'success')
        return redirect(url_for(f'{BP}.input_delivery_choose', contract_id=contract_id))
    return render_template(TP + 'delivery_form.html', contract=meta, item=items[index], item_index=index, total_items=len(items), single=False,
                           show_nav_menu=True, accessible_modules=_get_accessible_modules(), line=LINE, bp=BP)


@bp.route('/input-delivery/<int:contract_id>/item/<int:item_id>', methods=['GET', 'POST'])
@_contracts_access_required
def input_delivery_item(contract_id, item_id):
    meta = execute_query(f"SELECT * FROM {_cm()} WHERE contract_id = %s", (contract_id,), fetch_one=True)
    item = execute_query(f"SELECT * FROM {_ci()} WHERE contract_id = %s AND item_id = %s", (contract_id, item_id), fetch_one=True)
    if not meta or not item:
        flash('Not found', 'error')
        return redirect(url_for(f'{BP}.input_delivery_specific', contract_id=contract_id))
    if request.method == 'POST':
        try:
            delivered_amount = int(request.form.get('delivered_amount') or 0)
        except Exception:
            delivered_amount = 0
        delivery_no = (request.form.get('delivery_no') or '').strip()
        delivery_date = (request.form.get('delivery_date') or '').strip() or None
        
        current_delivered = item.get('delivered_qty') or 0
        total_qty = item.get('qty') or 0
        remaining_balance = total_qty - current_delivered
        
        if delivered_amount > remaining_balance:
            flash(f'Error: Delivery amount ({delivered_amount}) exceeds remaining balance ({remaining_balance})', 'error')
            return redirect(url_for(f'{BP}.input_delivery_item', contract_id=contract_id, item_id=item_id))

        new_delivered = current_delivered + delivered_amount
        deliver_balance = max(0, total_qty - new_delivered)
        execute_query(f"UPDATE {_ci()} SET delivered_qty = %s, deliver_balance = %s, delivery_no = %s, delivery_date = %s WHERE item_id = %s",
                      (new_delivered, deliver_balance, delivery_no or None, delivery_date, item_id), commit=True)
        flash('Saved.', 'success')
        return redirect(url_for(f'{BP}.input_delivery_specific', contract_id=contract_id))
    return render_template(TP + 'delivery_form.html', contract=meta, item=item, item_index=0, total_items=1, single=True,
                           show_nav_menu=True, accessible_modules=_get_accessible_modules(), line=LINE, bp=BP)


@bp.route('/input-delivery/<int:contract_id>/specific')
@_contracts_access_required
def input_delivery_specific(contract_id):
    meta = execute_query(f"SELECT * FROM {_cm()} WHERE contract_id = %s", (contract_id,), fetch_one=True)
    if not meta:
        flash('Contract not found', 'error')
        return redirect(url_for(f'{BP}.input_delivery_list'))
    q = (request.args.get('q') or '').strip()
    items = execute_query(f"SELECT * FROM {_ci()} WHERE contract_id = %s ORDER BY item_id", (contract_id,), fetch=True) or []
    if q:
        ql = q.lower()
        items = [i for i in items if (i.get('item_name') or '').lower().find(ql) >= 0 or (i.get('part_number') or '').lower().find(ql) >= 0]
    return render_template(TP + 'specific_items_list.html', contract=meta, items=items, search_q=q, mode='delivery',
                           show_nav_menu=True, accessible_modules=_get_accessible_modules(), line=LINE, bp=BP)


# ========== 4. Input CRV info ==========
@bp.route('/input-crv')
@_contracts_access_required
def input_crv_list():
    q = (request.args.get('q') or '').strip()
    if q:
        contracts = execute_query(f"SELECT * FROM {_cm()} WHERE contract_no LIKE %s ORDER BY contract_no", (f'%{q}%',), fetch=True) or []
    else:
        contracts = execute_query(f"SELECT * FROM {_cm()} ORDER BY contract_no", fetch=True) or []
    return render_template(TP + 'select_contract.html', contracts=contracts, search_q=q, mode='crv',
                           show_nav_menu=True, accessible_modules=_get_accessible_modules(), line=LINE, bp=BP)


@bp.route('/input-crv/<int:contract_id>')
@_contracts_access_required
def input_crv_choose(contract_id):
    meta = execute_query(f"SELECT * FROM {_cm()} WHERE contract_id = %s", (contract_id,), fetch_one=True)
    if not meta:
        flash('Contract not found', 'error')
        return redirect(url_for(f'{BP}.input_crv_list'))
    items = execute_query(f"SELECT * FROM {_ci()} WHERE contract_id = %s ORDER BY item_id", (contract_id,), fetch=True) or []
    iterate_url = url_for(f'{BP}.input_crv_iterate', contract_id=contract_id)
    specific_url = url_for(f'{BP}.input_crv_specific', contract_id=contract_id)
    return render_template(TP + 'inspection_choose.html', contract=meta, items=items, mode='crv',
                           iterate_url=iterate_url, specific_url=specific_url,
                           show_nav_menu=True, accessible_modules=_get_accessible_modules(), line=LINE, bp=BP)


@bp.route('/input-crv/<int:contract_id>/iterate', methods=['GET', 'POST'])
@_contracts_access_required
def input_crv_iterate(contract_id):
    meta = execute_query(f"SELECT * FROM {_cm()} WHERE contract_id = %s", (contract_id,), fetch_one=True)
    if not meta:
        flash('Contract not found', 'error')
        return redirect(url_for(f'{BP}.input_crv_list'))
    items = execute_query(f"SELECT * FROM {_ci()} WHERE contract_id = %s ORDER BY item_id", (contract_id,), fetch=True) or []
    index = int(request.args.get('index', 0))
    if request.method == 'POST' and index < len(items):
        item_id = request.form.get('item_id', type=int)
        crv_no = (request.form.get('crv_no') or '').strip()
        crv_date = (request.form.get('crv_date') or '').strip() or None
        execute_query(f"UPDATE {_ci()} SET crv_no = %s, crv_date = %s WHERE item_id = %s", (crv_no or None, crv_date, item_id), commit=True)
        next_index = request.form.get('next_index', type=int)
        if next_index >= len(items):
            flash('CRV info saved for all items.', 'success')
            return redirect(url_for(f'{BP}.input_crv_choose', contract_id=contract_id))
        return redirect(url_for(f'{BP}.input_crv_iterate', contract_id=contract_id, index=next_index))
    if index >= len(items):
        flash('CRV info saved for all items.', 'success')
        return redirect(url_for(f'{BP}.input_crv_choose', contract_id=contract_id))
    return render_template(TP + 'crv_form.html', contract=meta, item=items[index], item_index=index, total_items=len(items), single=False,
                           show_nav_menu=True, accessible_modules=_get_accessible_modules(), line=LINE, bp=BP)


@bp.route('/input-crv/<int:contract_id>/item/<int:item_id>', methods=['GET', 'POST'])
@_contracts_access_required
def input_crv_item(contract_id, item_id):
    meta = execute_query(f"SELECT * FROM {_cm()} WHERE contract_id = %s", (contract_id,), fetch_one=True)
    item = execute_query(f"SELECT * FROM {_ci()} WHERE contract_id = %s AND item_id = %s", (contract_id, item_id), fetch_one=True)
    if not meta or not item:
        flash('Not found', 'error')
        return redirect(url_for(f'{BP}.input_crv_specific', contract_id=contract_id))
    if request.method == 'POST':
        crv_no = (request.form.get('crv_no') or '').strip()
        crv_date = (request.form.get('crv_date') or '').strip() or None
        execute_query(f"UPDATE {_ci()} SET crv_no = %s, crv_date = %s WHERE item_id = %s", (crv_no or None, crv_date, item_id), commit=True)
        flash('Saved.', 'success')
        return redirect(url_for(f'{BP}.input_crv_specific', contract_id=contract_id))
    return render_template(TP + 'crv_form.html', contract=meta, item=item, item_index=0, total_items=1, single=True,
                           show_nav_menu=True, accessible_modules=_get_accessible_modules(), line=LINE, bp=BP)


@bp.route('/input-crv/<int:contract_id>/specific')
@_contracts_access_required
def input_crv_specific(contract_id):
    meta = execute_query(f"SELECT * FROM {_cm()} WHERE contract_id = %s", (contract_id,), fetch_one=True)
    if not meta:
        flash('Contract not found', 'error')
        return redirect(url_for(f'{BP}.input_crv_list'))
    q = (request.args.get('q') or '').strip()
    items = execute_query(f"SELECT * FROM {_ci()} WHERE contract_id = %s ORDER BY item_id", (contract_id,), fetch=True) or []
    if q:
        ql = q.lower()
        items = [i for i in items if (i.get('item_name') or '').lower().find(ql) >= 0 or (i.get('part_number') or '').lower().find(ql) >= 0]
    return render_template(TP + 'specific_items_list.html', contract=meta, items=items, search_q=q, mode='crv',
                           show_nav_menu=True, accessible_modules=_get_accessible_modules(), line=LINE, bp=BP)


# ========== 5. Input Invoice Check ==========
@bp.route('/input-invoice')
@_contracts_access_required
def input_invoice_list():
    q = (request.args.get('q') or '').strip()
    if q:
        contracts = execute_query(f"SELECT * FROM {_cm()} WHERE contract_no LIKE %s ORDER BY contract_no", (f'%{q}%',), fetch=True) or []
    else:
        contracts = execute_query(f"SELECT * FROM {_cm()} ORDER BY contract_no", fetch=True) or []
    return render_template(TP + 'select_contract.html', contracts=contracts, search_q=q, mode='invoice',
                           show_nav_menu=True, accessible_modules=_get_accessible_modules(), line=LINE, bp=BP)


@bp.route('/input-invoice/<int:contract_id>')
@_contracts_access_required
def input_invoice_choose(contract_id):
    meta = execute_query(f"SELECT * FROM {_cm()} WHERE contract_id = %s", (contract_id,), fetch_one=True)
    if not meta:
        flash('Contract not found', 'error')
        return redirect(url_for(f'{BP}.input_invoice_list'))
    items = execute_query(f"SELECT * FROM {_ci()} WHERE contract_id = %s ORDER BY item_id", (contract_id,), fetch=True) or []
    iterate_url = url_for(f'{BP}.input_invoice_iterate', contract_id=contract_id)
    specific_url = url_for(f'{BP}.input_invoice_specific', contract_id=contract_id)
    return render_template(TP + 'inspection_choose.html', contract=meta, items=items, mode='invoice',
                           iterate_url=iterate_url, specific_url=specific_url,
                           show_nav_menu=True, accessible_modules=_get_accessible_modules(), line=LINE, bp=BP)


@bp.route('/input-invoice/<int:contract_id>/iterate', methods=['GET', 'POST'])
@_contracts_access_required
def input_invoice_iterate(contract_id):
    meta = execute_query(f"SELECT * FROM {_cm()} WHERE contract_id = %s", (contract_id,), fetch_one=True)
    if not meta:
        flash('Contract not found', 'error')
        return redirect(url_for(f'{BP}.input_invoice_list'))
    items = execute_query(f"SELECT * FROM {_ci()} WHERE contract_id = %s ORDER BY item_id", (contract_id,), fetch=True) or []
    index = int(request.args.get('index', 0))
    if request.method == 'POST' and index < len(items):
        item_id = request.form.get('item_id', type=int)
        invoice_no = (request.form.get('invoice_no') or '').strip()
        submission_date = (request.form.get('submission_date') or '').strip() or None
        
        execute_query(f"UPDATE {_ci()} SET invoice_no = %s, submission_date = %s WHERE item_id = %s",
                      (invoice_no or None, submission_date, item_id), commit=True)
        
        next_index = request.form.get('next_index', type=int)
        if next_index >= len(items):
            flash('Invoice info saved for all items.', 'success')
            return redirect(url_for(f'{BP}.input_invoice_choose', contract_id=contract_id))
        return redirect(url_for(f'{BP}.input_invoice_iterate', contract_id=contract_id, index=next_index))
    if index >= len(items):
        flash('Invoice info saved for all items.', 'success')
        return redirect(url_for(f'{BP}.input_invoice_choose', contract_id=contract_id))
    return render_template(TP + 'invoice_form.html', contract=meta, item=items[index], item_index=index, total_items=len(items), single=False,
                           show_nav_menu=True, accessible_modules=_get_accessible_modules(), line=LINE, bp=BP)


@bp.route('/input-invoice/<int:contract_id>/item/<int:item_id>', methods=['GET', 'POST'])
@_contracts_access_required
def input_invoice_item(contract_id, item_id):
    meta = execute_query(f"SELECT * FROM {_cm()} WHERE contract_id = %s", (contract_id,), fetch_one=True)
    item = execute_query(f"SELECT * FROM {_ci()} WHERE contract_id = %s AND item_id = %s", (contract_id, item_id), fetch_one=True)
    if not meta or not item:
        flash('Not found', 'error')
        return redirect(url_for(f'{BP}.input_invoice_specific', contract_id=contract_id))
    if request.method == 'POST':
        invoice_no = (request.form.get('invoice_no') or '').strip()
        submission_date = (request.form.get('submission_date') or '').strip() or None
        
        execute_query(f"UPDATE {_ci()} SET invoice_no = %s, submission_date = %s WHERE item_id = %s",
                      (invoice_no or None, submission_date, item_id), commit=True)
        flash('Saved.', 'success')
        return redirect(url_for(f'{BP}.input_invoice_specific', contract_id=contract_id))
    return render_template(TP + 'invoice_form.html', contract=meta, item=item, item_index=0, total_items=1, single=True,
                           show_nav_menu=True, accessible_modules=_get_accessible_modules(), line=LINE, bp=BP)


@bp.route('/input-invoice/<int:contract_id>/specific')
@_contracts_access_required
def input_invoice_specific(contract_id):
    meta = execute_query(f"SELECT * FROM {_cm()} WHERE contract_id = %s", (contract_id,), fetch_one=True)
    if not meta:
        flash('Contract not found', 'error')
        return redirect(url_for(f'{BP}.input_invoice_list'))
    q = (request.args.get('q') or '').strip()
    items = execute_query(f"SELECT * FROM {_ci()} WHERE contract_id = %s ORDER BY item_id", (contract_id,), fetch=True) or []
    if q:
        ql = q.lower()
        items = [i for i in items if (i.get('item_name') or '').lower().find(ql) >= 0 or (i.get('part_number') or '').lower().find(ql) >= 0]
    return render_template(TP + 'specific_items_list.html', contract=meta, items=items, search_q=q, mode='invoice',
                           show_nav_menu=True, accessible_modules=_get_accessible_modules(), line=LINE, bp=BP)


# ========== Delete Routes ==========
@bp.route('/delete-contract/<int:contract_id>', methods=['POST'])
@_contracts_access_required
def delete_contract(contract_id):
    """Delete a contract and all its items."""
    try:
        execute_query(f"DELETE FROM {_ci()} WHERE contract_id = %s", (contract_id,), commit=True)
        execute_query(f"DELETE FROM {_cm()} WHERE contract_id = %s", (contract_id,), commit=True)
        flash('Contract deleted successfully.', 'success')
    except Exception as e:
        logger.error("Error deleting contract %s: %s", contract_id, e)
        flash('Error deleting contract.', 'error')
    return redirect(url_for(f'{BP}.contracts_dashboard'))


@bp.route('/delete-contract-item/<int:contract_id>/<int:item_id>', methods=['POST'])
@_contracts_access_required
def delete_contract_item(contract_id, item_id):
    """Delete a specific item from a contract."""
    try:
        execute_query(f"DELETE FROM {_ci()} WHERE contract_id = %s AND item_id = %s", (contract_id, item_id), commit=True)
        flash('Item deleted successfully.', 'success')
    except Exception as e:
        logger.error("Error deleting contract item %s: %s", item_id, e)
        flash('Error deleting item.', 'error')
    return redirect(url_for(f'{BP}.display_contract_detail', contract_id=contract_id))


# ========== 6. Input payment info ==========
@bp.route('/input-payment')
@_contracts_access_required
def input_payment_list():
    q = (request.args.get('q') or '').strip()
    if q:
        contracts = execute_query(f"SELECT * FROM {_cm()} WHERE contract_no LIKE %s ORDER BY contract_no", (f'%{q}%',), fetch=True) or []
    else:
        contracts = execute_query(f"SELECT * FROM {_cm()} ORDER BY contract_no", fetch=True) or []
    return render_template(TP + 'select_contract.html', contracts=contracts, search_q=q, mode='payment',
                           show_nav_menu=True, accessible_modules=_get_accessible_modules(), line=LINE, bp=BP)


@bp.route('/input-payment/<int:contract_id>')
@_contracts_access_required
def input_payment_choose(contract_id):
    meta = execute_query(f"SELECT * FROM {_cm()} WHERE contract_id = %s", (contract_id,), fetch_one=True)
    if not meta:
        flash('Contract not found', 'error')
        return redirect(url_for(f'{BP}.input_payment_list'))
    items = execute_query(f"SELECT * FROM {_ci()} WHERE contract_id = %s ORDER BY item_id", (contract_id,), fetch=True) or []
    iterate_url = url_for(f'{BP}.input_payment_iterate', contract_id=contract_id)
    specific_url = url_for(f'{BP}.input_payment_specific', contract_id=contract_id)
    return render_template(TP + 'inspection_choose.html', contract=meta, items=items, mode='payment',
                           iterate_url=iterate_url, specific_url=specific_url,
                           show_nav_menu=True, accessible_modules=_get_accessible_modules(), line=LINE, bp=BP)


@bp.route('/input-payment/<int:contract_id>/iterate', methods=['GET', 'POST'])
@_contracts_access_required
def input_payment_iterate(contract_id):
    meta = execute_query(f"SELECT * FROM {_cm()} WHERE contract_id = %s", (contract_id,), fetch_one=True)
    if not meta:
        flash('Contract not found', 'error')
        return redirect(url_for(f'{BP}.input_payment_list'))
    items = execute_query(f"SELECT * FROM {_ci()} WHERE contract_id = %s ORDER BY item_id", (contract_id,), fetch=True) or []
    index = int(request.args.get('index', 0))
    if request.method == 'POST' and index < len(items):
        item_id = request.form.get('item_id', type=int)
        # Invoice fields removed from here
        try:
            ld_charges = float(request.form.get('ld_charges') or 0)
        except Exception:
            ld_charges = None
        try:
            income_tax = float(request.form.get('income_tax') or 0)
        except Exception:
            income_tax = None
        try:
            other_charges = float(request.form.get('other_charges') or 0)
        except Exception:
            other_charges = None
        try:
            net_amount = float(request.form.get('net_amount') or 0)
        except Exception:
            net_amount = None
        cheque_no = (request.form.get('cheque_no') or '').strip()
        cheque_date = (request.form.get('cheque_date') or '').strip() or None
        bank_deposit_date = (request.form.get('bank_deposit_date') or '').strip() or None
        warranty_expiry_date = (request.form.get('warranty_expiry_date') or '').strip() or None
        
        execute_query(f"""UPDATE {_ci()} SET ld_charges = %s, income_tax = %s, other_charges = %s, net_amount = %s,
            cheque_no = %s, cheque_date = %s, bank_deposit_date = %s, warranty_expiry_date = %s WHERE item_id = %s""",
                      (ld_charges, income_tax, other_charges, net_amount, cheque_no or None, cheque_date, bank_deposit_date, warranty_expiry_date, item_id), commit=True)
        # Update contract amount_given and amount_balance
        tot = execute_query(f"SELECT COALESCE(SUM(net_amount), 0) as s FROM {_ci()} WHERE contract_id = %s", (contract_id,), fetch_one=True)
        given = float(tot.get('s') or 0)
        total_value = float(meta.get('total_value') or 0)
        balance = total_value - given
        execute_query(f"UPDATE {_cm()} SET amount_given = %s, amount_balance = %s WHERE contract_id = %s", (given, balance, contract_id), commit=True)
        next_index = request.form.get('next_index', type=int)
        if next_index >= len(items):
            flash('Payment info saved for all items.', 'success')
            return redirect(url_for(f'{BP}.input_payment_choose', contract_id=contract_id))
        return redirect(url_for(f'{BP}.input_payment_iterate', contract_id=contract_id, index=next_index))
    if index >= len(items):
        flash('Payment info saved for all items.', 'success')
        return redirect(url_for(f'{BP}.input_payment_choose', contract_id=contract_id))
    return render_template(TP + 'payment_form.html', contract=meta, item=items[index], item_index=index, total_items=len(items), single=False,
                           show_nav_menu=True, accessible_modules=_get_accessible_modules(), line=LINE, bp=BP)


@bp.route('/input-payment/<int:contract_id>/item/<int:item_id>', methods=['GET', 'POST'])
@_contracts_access_required
def input_payment_item(contract_id, item_id):
    meta = execute_query(f"SELECT * FROM {_cm()} WHERE contract_id = %s", (contract_id,), fetch_one=True)
    item = execute_query(f"SELECT * FROM {_ci()} WHERE contract_id = %s AND item_id = %s", (contract_id, item_id), fetch_one=True)
    if not meta or not item:
        flash('Not found', 'error')
        return redirect(url_for(f'{BP}.input_payment_specific', contract_id=contract_id))
    if request.method == 'POST':
        # Invoice fields removed from here
        try:
            ld_charges = float(request.form.get('ld_charges') or 0)
        except Exception:
            ld_charges = None
        try:
            income_tax = float(request.form.get('income_tax') or 0)
        except Exception:
            income_tax = None
        try:
            other_charges = float(request.form.get('other_charges') or 0)
        except Exception:
            other_charges = None
        try:
            net_amount = float(request.form.get('net_amount') or 0)
        except Exception:
            net_amount = None
        cheque_no = (request.form.get('cheque_no') or '').strip()
        cheque_date = (request.form.get('cheque_date') or '').strip() or None
        bank_deposit_date = (request.form.get('bank_deposit_date') or '').strip() or None
        warranty_expiry_date = (request.form.get('warranty_expiry_date') or '').strip() or None
        
        execute_query(f"""UPDATE {_ci()} SET ld_charges = %s, income_tax = %s, other_charges = %s, net_amount = %s,
            cheque_no = %s, cheque_date = %s, bank_deposit_date = %s, warranty_expiry_date = %s WHERE item_id = %s""",
                      (ld_charges, income_tax, other_charges, net_amount, cheque_no or None, cheque_date, bank_deposit_date, warranty_expiry_date, item_id), commit=True)
        tot = execute_query(f"SELECT COALESCE(SUM(net_amount), 0) as s FROM {_ci()} WHERE contract_id = %s", (contract_id,), fetch_one=True)
        given = float(tot.get('s') or 0)
        total_value = float(meta.get('total_value') or 0)
        execute_query(f"UPDATE {_cm()} SET amount_given = %s, amount_balance = %s WHERE contract_id = %s", (given, total_value - given, contract_id), commit=True)
        flash('Saved.', 'success')
        return redirect(url_for(f'{BP}.input_payment_specific', contract_id=contract_id))
    return render_template(TP + 'payment_form.html', contract=meta, item=item, item_index=0, total_items=1, single=True,
                           show_nav_menu=True, accessible_modules=_get_accessible_modules(), line=LINE, bp=BP)


@bp.route('/input-payment/<int:contract_id>/specific')
@_contracts_access_required
def input_payment_specific(contract_id):
    meta = execute_query(f"SELECT * FROM {_cm()} WHERE contract_id = %s", (contract_id,), fetch_one=True)
    if not meta:
        flash('Contract not found', 'error')
        return redirect(url_for(f'{BP}.input_payment_list'))
    q = (request.args.get('q') or '').strip()
    items = execute_query(f"SELECT * FROM {_ci()} WHERE contract_id = %s ORDER BY item_id", (contract_id,), fetch=True) or []
    if q:
        ql = q.lower()
        items = [i for i in items if (i.get('item_name') or '').lower().find(ql) >= 0 or (i.get('part_number') or '').lower().find(ql) >= 0]
    return render_template(TP + 'specific_items_list.html', contract=meta, items=items, search_q=q, mode='payment',
                           show_nav_menu=True, accessible_modules=_get_accessible_modules(), line=LINE, bp=BP)


# ========== 7. Display contract ==========
@bp.route('/display-contract')
@_contracts_access_required
def display_contract_list():
    q = (request.args.get('q') or '').strip()
    if q:
        contracts = execute_query(f"SELECT * FROM {_cm()} WHERE contract_no LIKE %s ORDER BY contract_no", (f'%{q}%',), fetch=True) or []
    else:
        contracts = execute_query(f"SELECT * FROM {_cm()} ORDER BY contract_no", fetch=True) or []
    return render_template(TP + 'display_list.html', contracts=contracts, search_q=q,
                           show_nav_menu=True, accessible_modules=_get_accessible_modules(), line=LINE, bp=BP)


@bp.route('/display-contract/<int:contract_id>')
@_contracts_access_required
def display_contract_detail(contract_id):
    meta = execute_query(f"SELECT * FROM {_cm()} WHERE contract_id = %s", (contract_id,), fetch_one=True)
    if not meta:
        flash('Contract not found', 'error')
        return redirect(url_for(f'{BP}.display_contract_list'))
    items = execute_query(f"SELECT * FROM {_ci()} WHERE contract_id = %s ORDER BY item_id", (contract_id,), fetch=True) or []
    return render_template(TP + 'display_detail.html', contract=meta, items=items,
                           show_nav_menu=True, accessible_modules=_get_accessible_modules(), line=LINE, bp=BP)


# ========== 8. Renew BG ==========
@bp.route('/renew-bg')
@_contracts_access_required
def renew_bg_list():
    q = (request.args.get('q') or '').strip()
    if q:
        contracts = execute_query(f"SELECT * FROM {_cm()} WHERE contract_no LIKE %s ORDER BY contract_no", (f'%{q}%',), fetch=True) or []
    else:
        contracts = execute_query(f"SELECT * FROM {_cm()} ORDER BY contract_no", fetch=True) or []
    return render_template(TP + 'select_contract.html', contracts=contracts, search_q=q, mode='renew_bg',
                           show_nav_menu=True, accessible_modules=_get_accessible_modules(), line=LINE, bp=BP)


@bp.route('/renew-bg/<int:contract_id>', methods=['GET', 'POST'])
@_contracts_access_required
def renew_bg_edit(contract_id):
    meta = execute_query(f"SELECT * FROM {_cm()} WHERE contract_id = %s", (contract_id,), fetch_one=True)
    if not meta:
        flash('Contract not found', 'error')
        return redirect(url_for(f'{BP}.renew_bg_list'))
    
    if request.method == 'POST':
        bg_number = (request.form.get('bg_number') or '').strip()
        bg_expiry_date = (request.form.get('bg_expiry_date') or '').strip()
        bg_types = request.form.getlist('bg_type')
        bg_type_str = ', '.join(bg_types) if bg_types else None
        
        execute_query(f"UPDATE {_cm()} SET bg_number = %s, bg_expiry_date = %s, bg_type = %s WHERE contract_id = %s",
                      (bg_number, bg_expiry_date, bg_type_str, contract_id), commit=True)
        flash('BG details updated successfully.', 'success')
        return redirect(url_for(f'{BP}.display_contract_list'))

    return render_template(TP + 'renew_bg_form.html', contract=meta,
                           show_nav_menu=True, accessible_modules=_get_accessible_modules(), line=LINE, bp=BP)


