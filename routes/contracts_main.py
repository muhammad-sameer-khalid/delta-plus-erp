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

@bp.route('/api/search-all')
@login_required
def api_search_all():
    """Search contracts across all lines: Tanks, Biomedical, Battery."""
    if not can_access_contracts(session.get('user_email')):
        return jsonify({'contracts': []})

    q = (request.args.get('q') or '').strip()
    
    # We need to query three tables: contracts_metadata, contracts_metadata_biomedical, contracts_metadata_battery
    # And maybe indicate which line they belong to.
    
    # Helper to construct query for one table
    def get_query(table, line_name):
        base = f"SELECT contract_id, contract_no, contract_date, total_value, delivery_deadline, department, '{line_name}' as line FROM {table}"
        if q:
            base += f" WHERE contract_no LIKE %s"
        return base

    # Params
    params = []
    if q:
        like_q = f'%{q}%'
        params = [like_q, like_q, like_q]
    
    # Combine queries
    query = f"""
        ({get_query('contracts_metadata', 'Tanks')})
        UNION ALL
        ({get_query('contracts_metadata_biomedical', 'Biomedical')})
        UNION ALL
        ({get_query('contracts_metadata_battery', 'Battery')})
        ORDER BY contract_no
        LIMIT 50
    """
    
    # If no query, we might want to return everything or just recent ones. 
    # But usually predictive search needs a query. If empty, maybe show top 50 recent?
    # The snippet above requires parameters if q is present.
    # Let's adjust logic for empty q to just showing nothing or top 20 recent from each?
    # User asked for "predictive search functionality", usually implies typing.
    # If q is empty, let's return empty to avoid massive load, or maybe just recent.
    # Let's stick to the search logic.
    
    if not q:
        # Initial load or empty search: return top 20 from each to show something?
        # Or just empty. Let's return empty for now, or maybe recent.
        # Let's return recent 20 combined.
        query = f"""
            (SELECT contract_id, contract_no, contract_date, total_value, delivery_deadline, department, 'Tanks' as line FROM contracts_metadata ORDER BY contract_id DESC LIMIT 20)
            UNION ALL
            (SELECT contract_id, contract_no, contract_date, total_value, delivery_deadline, department, 'Biomedical' as line FROM contracts_metadata_biomedical ORDER BY contract_id DESC LIMIT 20)
            UNION ALL
            (SELECT contract_id, contract_no, contract_date, total_value, delivery_deadline, department, 'Battery' as line FROM contracts_metadata_battery ORDER BY contract_id DESC LIMIT 20)
            ORDER BY contract_id DESC
            LIMIT 50
        """
        params = []

    results = execute_query(query, tuple(params), fetch=True) or []
    
    # Format dates
    for r in results:
        if r.get('contract_date'):
            r['contract_date'] = str(r['contract_date'])
        if r.get('delivery_deadline'):
            r['delivery_deadline'] = str(r['delivery_deadline'])
            
    return jsonify({'contracts': results})
