from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for, flash
from auth import can_access_contracts, get_user_roles, module_access_required, login_required
from database import execute_query

bp = Blueprint('contracts_main', __name__, url_prefix='/contracts')

@bp.route('/')
@login_required
def dashboard():
    """Central Contracts Dashboard."""
    if not can_access_contracts(session.get('user_email')):
        flash('You do not have permission to access Contracts', 'error')
        return redirect(url_for('dashboard'))
    
    return render_template('contracts/main_dashboard.html')

@bp.route('/all')
@login_required
def view_all():
    """View all contracts from all lines."""
    if not can_access_contracts(session.get('user_email')):
        flash('You do not have permission to access Contracts', 'error')
        return redirect(url_for('dashboard'))
    
    return render_template('contracts/view_all.html')

@bp.route('/all-bgs')
@login_required
def view_all_bgs():
    """View all bank guarantees from all lines."""
    if not can_access_contracts(session.get('user_email')):
        flash('You do not have permission to access Contracts', 'error')
        return redirect(url_for('dashboard'))
    
    query = """
        SELECT contract_id, contract_no, contract_date, total_value, delivery_deadline, department, 
               bank_name, bg_number, bg_type, bg_amount, bg_issue_date, bg_expiry_date, 
               final_crv_no, final_crv_date, 'Tanks' as line 
        FROM contracts_metadata
        UNION ALL
        SELECT contract_id, contract_no, contract_date, total_value, delivery_deadline, department, 
               bank_name, bg_number, bg_type, bg_amount, bg_issue_date, bg_expiry_date, 
               final_crv_no, final_crv_date, 'Biomedical' as line 
        FROM contracts_metadata_biomedical
        UNION ALL
        SELECT contract_id, contract_no, contract_date, total_value, delivery_deadline, department, 
               bank_name, bg_number, bg_type, bg_amount, bg_issue_date, bg_expiry_date, 
               final_crv_no, final_crv_date, 'Battery' as line 
        FROM contracts_metadata_battery
        ORDER BY contract_no
    """
    contracts = execute_query(query, fetch=True) or []
    
    return render_template('contracts/display_all_bgs.html', contracts=contracts)


@bp.route('/pending-bills')
@login_required
def view_pending_bills():
    """View all contracts (all lines) where some items have invoice_no but no payment (net_amount)."""
    if not can_access_contracts(session.get('user_email')):
        flash('You do not have permission to access Contracts', 'error')
        return redirect(url_for('dashboard'))
    
    return render_template('contracts/pending_bills.html')

@bp.route('/api/search-all')
@login_required
def api_search_all():
    """Search contracts across all lines: Tanks, Biomedical, Battery."""
    if not can_access_contracts(session.get('user_email')):
        return jsonify({'contracts': []})

    q = (request.args.get('q') or '').strip()
    status = (request.args.get('status') or 'all').strip().lower()

    # Map incoming status filter to DB values
    STATUS_MAP = {
        'active': 'active',
        'completed': 'completed',
        'warranty': 'warranty period',
        'warranty period': 'warranty period',
        'all': None
    }
    status_value = STATUS_MAP.get(status, None)
    
    # We need to query three tables: contracts_metadata, contracts_metadata_biomedical, contracts_metadata_battery
    # And maybe indicate which line they belong to.
    
    tables = [
        ('contracts_metadata', 'Tanks'),
        ('contracts_metadata_biomedical', 'Biomedical'),
        ('contracts_metadata_battery', 'Battery'),
    ]

    queries = []
    params = []

    if q:
        like_q = f'%{q}%'
        # Build search query with optional status filter
        for table, line_name in tables:
            base = (
                f"SELECT contract_id, contract_no, contract_date, total_value, "
                f"delivery_deadline, department, contract_status, '{line_name}' as line "
                f"FROM {table}"
            )
            conditions = ["contract_no LIKE %s"]
            params.append(like_q)

            if status_value:
                conditions.append("contract_status = %s")
                params.append(status_value)

            base += " WHERE " + " AND ".join(conditions)
            queries.append(base)

        query = f"""
            ({') UNION ALL ('.join(queries)})
            ORDER BY contract_no
            LIMIT 50
        """
    else:
        # Initial load or empty search: recent contracts with optional status filter
        for table, line_name in tables:
            base = (
                f"SELECT contract_id, contract_no, contract_date, total_value, "
                f"delivery_deadline, department, contract_status, '{line_name}' as line "
                f"FROM {table}"
            )
            conditions = []
            if status_value:
                conditions.append("contract_status = %s")
                params.append(status_value)

            if conditions:
                base += " WHERE " + " AND ".join(conditions)

            base += " ORDER BY contract_id DESC LIMIT 20"
            queries.append(base)

        query = f"""
            ({') UNION ALL ('.join(queries)})
            ORDER BY contract_id DESC
            LIMIT 50
        """

    results = execute_query(query, tuple(params), fetch=True) or []
    
    # Format dates
    for r in results:
        if r.get('contract_date'):
            r['contract_date'] = str(r['contract_date'])
        if r.get('delivery_deadline'):
            r['delivery_deadline'] = str(r['delivery_deadline'])
            
    return jsonify({'contracts': results})


@bp.route('/api/pending-bills')
@login_required
def api_pending_bills():
    """List/search contracts across all lines with pending bills (invoice entered, payment not)."""
    if not can_access_contracts(session.get('user_email')):
        return jsonify({'contracts': []})

    q = (request.args.get('q') or '').strip()

    tables = [
        ('contracts_metadata', 'contract_items', 'Tanks'),
        ('contracts_metadata_biomedical', 'contract_items_biomedical', 'Biomedical'),
        ('contracts_metadata_battery', 'contract_items_battery', 'Battery'),
    ]

    subqueries = []
    params = []

    for meta_t, items_t, line_name in tables:
        base = (
            f"SELECT DISTINCT cm.contract_id, cm.contract_no, cm.contract_date, cm.total_value, "
            f"cm.delivery_deadline, cm.department, '{line_name}' AS line "
            f"FROM {meta_t} cm "
            f"JOIN {items_t} ci ON ci.contract_id = cm.contract_id "
            f"WHERE cm.contract_status != 'completed' "
            f"AND (ci.invoice_no IS NOT NULL AND ci.invoice_no != '') "
            f"AND (ci.net_amount IS NULL OR ci.net_amount = 0)"
        )

        if q:
            like_q = f"%{q}%"
            base += (
                " AND ("
                "cm.contract_no LIKE %s "
                "OR ci.invoice_no LIKE %s "
                "OR CAST(cm.total_value AS CHAR) LIKE %s "
                "OR CAST(ci.net_amount AS CHAR) LIKE %s"
                ")"
            )
            params.extend([like_q, like_q, like_q, like_q])

        subqueries.append(base)

    if not subqueries:
        return jsonify({'contracts': []})

    query = f"""
        ({') UNION ALL ('.join(subqueries)})
        ORDER BY contract_no
    """

    results = execute_query(query, tuple(params), fetch=True) or []

    for r in results:
        if r.get('contract_date'):
            r['contract_date'] = str(r['contract_date'])
        if r.get('delivery_deadline'):
            r['delivery_deadline'] = str(r['delivery_deadline'])

    return jsonify({'contracts': results})
