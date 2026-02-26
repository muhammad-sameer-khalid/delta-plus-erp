"""
Delta Plus ERP System - Main Flask Application
A comprehensive ERP system for manufacturing management
"""

from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
from config import Config
from database import init_connection_pool, init_database
from auth import (
    login_required, role_required, module_access_required,
    authenticate_user, get_user_roles, can_access_module,
    get_all_user_roles, add_user_role, remove_user_role,
    get_all_user_roles, add_user_role, remove_user_role,
    VALID_ROLES, create_user, get_production_lines_for_user,
    can_access_contracts, can_delete_items
)
import logging
from datetime import datetime
import os

# Initialize Flask app
app = Flask(__name__)
app.config.from_object(Config)
app.secret_key = Config.SECRET_KEY

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Database initialization will be done in main block

# Error handlers
@app.errorhandler(404)
def not_found(error):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    logger.error(f"Internal error: {error}")
    return render_template('500.html'), 500

# ============================================
# Authentication Routes
# ============================================

@app.route('/')
def index():
    """Redirect to login or dashboard based on auth status"""
    if 'user_email' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Login page"""
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        
        success, message = authenticate_user(email, password)
        
        if success:
            session['user_email'] = email
            session['user_roles'] = get_user_roles(email)
            flash('Login successful!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash(message, 'error')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    """Logout and clear session"""
    session.clear()
    flash('You have been logged out', 'info')
    return redirect(url_for('login'))

# ============================================
# Admin Routes
# ============================================

@app.route('/admin', methods=['GET', 'POST'])
@role_required('director', 'general manager', 'gm logistics')
def admin():
    """Admin page for role management"""
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        role = request.form.get('role', '').strip()
        password = request.form.get('password', '').strip()
        
        if not email or not role:
            flash('Email and role are required', 'error')
        else:
            # Check if role already exists
            user_roles = get_user_roles(email)
            
            if role in user_roles:
                # Remove role
                success, message = remove_user_role(email, role)
                flash(message, 'success' if success else 'error')
            else:
                # Add role (create user if doesn't exist)
                from database import execute_query
                user_check = execute_query(
                    "SELECT COUNT(*) as count FROM users WHERE email = %s",
                    (email,),
                    fetch_one=True
                )
                
                if user_check and user_check['count'] == 0:
                    # Create user with provided password or default
                    user_password = password if password else 'password123'
                    create_user(email, user_password)
                    flash(f'New user created with {"custom" if password else "default"} password', 'info')
                
                success, message = add_user_role(email, role)
                flash(message, 'success' if success else 'error')
    
    # Get all user roles
    user_roles_data = get_all_user_roles()
    
    return render_template('admin.html', 
                         user_roles=user_roles_data,
                         valid_roles=VALID_ROLES)


@app.route('/admin/sync-database')
@role_required('director', 'general manager', 'gm logistics')
def sync_database():
    """Generate a full mysqldump and serve it as a .sql download."""
    import subprocess
    import tempfile
    from flask import send_file
    from config import Config

    db_host = getattr(Config, 'DB_HOST', 'localhost')
    db_user = getattr(Config, 'DB_USER', 'root')
    db_password = getattr(Config, 'DB_PASSWORD', '')
    db_name = getattr(Config, 'DB_NAME', 'delta_plus_erp')

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f'delta_plus_erp_backup_{timestamp}.sql'

    try:
        # Build mysqldump command
        cmd = ['mysqldump', f'--host={db_host}', f'--user={db_user}']
        if db_password:
            cmd.append(f'--password={db_password}')
        cmd += ['--single-transaction', '--routines', '--triggers', db_name]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            flash(f'Database sync failed: {result.stderr[:200]}', 'error')
            return redirect(url_for('admin'))

        # Write to temp file and send as download
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.sql', mode='w', encoding='utf-8')
        tmp.write(result.stdout)
        tmp.close()

        return send_file(
            tmp.name,
            as_attachment=True,
            download_name=filename,
            mimetype='application/sql'
        )
    except FileNotFoundError:
        flash('mysqldump not found. Make sure MySQL is installed and mysqldump is in the system PATH.', 'error')
        return redirect(url_for('admin'))
    except subprocess.TimeoutExpired:
        flash('Database sync timed out. Try again.', 'error')
        return redirect(url_for('admin'))



# Dashboard Routes
# ============================================

@app.route('/dashboard')
@login_required
def dashboard():
    """Main dashboard: show only production line cards the user can access."""
    production_lines = get_production_lines_for_user(session.get('user_email', ''))
    can_access = can_access_contracts(session.get('user_email', ''))
    return render_template('dashboard.html', production_lines=production_lines, can_access_contracts=can_access)

@app.context_processor
def inject_permissions():
    """Inject permission helpers into all templates"""
    return dict(
        can_access_contracts=can_access_contracts,
        can_delete_items=can_delete_items
    )

@app.template_filter('commas')
def commas_filter(value):
    """Format a number with commas and 2 decimal places"""
    if value is None or value == '':
        return '0.00'
    try:
        return "{:,.2f}".format(float(value))
    except (ValueError, TypeError, Exception):
        return '0.00'

@app.route('/tanks')
@login_required
def tanks_dashboard():
    """Tanks production dashboard with module cards. Only for users with tanks roles."""
    user_email = session.get('user_email')
    if 'tanks' not in get_production_lines_for_user(user_email):
        flash('You do not have access to the Tanks production line.', 'error')
        return redirect(url_for('dashboard'))
    user_roles = session.get('user_roles', [])
    accessible_modules = []
    for module in ['rnd', 'production', 'supply_chain', 'qc', 'store']:
        if can_access_module(user_email, module, 'tanks'):
            accessible_modules.append(module)
    return render_template('tanks_dashboard.html',
                         accessible_modules=accessible_modules,
                         user_roles=user_roles,
                         can_access_contracts=can_access_contracts(user_email, 'tanks'))

@app.route('/biomedical')
@login_required
def biomedical_dashboard():
    """Biomedical production dashboard. Only for users with biomedical roles."""
    user_email = session.get('user_email')
    if 'biomedical' not in get_production_lines_for_user(user_email):
        flash('You do not have access to the Biomedical production line.', 'error')
        return redirect(url_for('dashboard'))
    user_roles = session.get('user_roles', [])
    accessible_modules = []
    for module in ['rnd', 'production', 'supply_chain', 'qc', 'store']:
        if can_access_module(user_email, module, 'biomedical'):
            accessible_modules.append(module)
    return render_template('biomedical_dashboard.html',
                         accessible_modules=accessible_modules,
                         user_roles=user_roles,
                         can_access_contracts=can_access_contracts(user_email, 'biomedical'),
                         line='biomedical')

@app.route('/battery')
@login_required
def battery_dashboard():
    """Battery production dashboard. Only for users with battery roles."""
    user_email = session.get('user_email')
    if 'battery' not in get_production_lines_for_user(user_email):
        flash('You do not have access to the Battery production line.', 'error')
        return redirect(url_for('dashboard'))
    user_roles = session.get('user_roles', [])
    accessible_modules = []
    for module in ['rnd', 'production', 'supply_chain', 'qc', 'store']:
        if can_access_module(user_email, module, 'battery'):
            accessible_modules.append(module)
    return render_template('battery_dashboard.html',
                         accessible_modules=accessible_modules,
                         user_roles=user_roles,
                         can_access_contracts=can_access_contracts(user_email, 'battery'),
                         line='battery')

# ============================================
# Notification Routes
# ============================================

def _notification_line(recipient_role):
    """Infer production line from recipient_role for tabs (tanks / biomedical / battery)."""
    if not recipient_role:
        return 'tanks'
    if recipient_role.endswith('_biomedical'):
        return 'biomedical'
    if recipient_role.endswith('_battery'):
        return 'battery'
    return 'tanks'


@app.route('/notifications')
@login_required
def notifications_page():
    """Notifications page with Tanks / Biomedical / Battery tabs"""
    from database import execute_query
    
    user_roles = session.get('user_roles', [])
    
    if not user_roles:
        return render_template('notifications.html', notifications=[])
    
    placeholders = ','.join(['%s'] * len(user_roles))
    query = f"""
        SELECT * FROM notifications 
        WHERE recipient_role IN ({placeholders})
        ORDER BY is_read ASC, created_at DESC
    """
    rows = execute_query(query, tuple(user_roles), fetch=True) or []
    notifications = []
    for r in rows:
        n = dict(r)
        n['line'] = _notification_line(r.get('recipient_role'))
        notifications.append(n)
    
    return render_template('notifications.html', notifications=notifications)

@app.route('/api/notifications')
@login_required
def get_notifications():
    """Get notifications for the current user"""
    from database import execute_query
    
    user_roles = session.get('user_roles', [])
    
    if not user_roles:
        return jsonify({'success': True, 'count': 0, 'notifications': []})
    
    # Get unread notifications for user's roles
    placeholders = ','.join(['%s'] * len(user_roles))
    query = f"""
        SELECT * FROM notifications 
        WHERE recipient_role IN ({placeholders}) AND is_read = FALSE
        ORDER BY created_at DESC
    """
    
    notifications = execute_query(query, tuple(user_roles), fetch=True)
    
    return jsonify({
        'success': True,
        'count': len(notifications) if notifications else 0,
        'notifications': notifications or []
    })

@app.route('/notifications/mark-read/<int:notification_id>', methods=['POST'])
@login_required
def mark_notification_read(notification_id):
    """Mark a notification as read"""
    from database import execute_query
    
    query = "UPDATE notifications SET is_read = TRUE WHERE id = %s"
    execute_query(query, (notification_id,), commit=True)
    
    return jsonify({'success': True})

@app.route('/notifications/mark-all-read', methods=['POST'])
@login_required
def mark_all_read():
    """Mark all notifications as read for current user"""
    from database import execute_query
    
    user_roles = session.get('user_roles', [])
    
    if user_roles:
        placeholders = ','.join(['%s'] * len(user_roles))
        query = f"""
            UPDATE notifications 
            SET is_read = TRUE 
            WHERE recipient_role IN ({placeholders})
        """
        execute_query(query, tuple(user_roles), commit=True)
    
    return jsonify({'success': True})

@app.route('/notifications/delete/<int:notification_id>', methods=['POST'])
@login_required
def delete_notification(notification_id):
    """Delete a notification"""
    from database import execute_query
    
    query = "DELETE FROM notifications WHERE id = %s"
    execute_query(query, (notification_id,), commit=True)
    
    return jsonify({'success': True})

# ============================================
# Approval Routes (Director & GM)
# ============================================

@app.route('/director-approvals')
@role_required('director')
def director_approvals():
    """List demand notes pending director approval"""
    from database import execute_query
    
    query = """
        SELECT * FROM demand_notes 
        WHERE approval_status = 'pending_director'
        ORDER BY created_at DESC
    """
    demands = execute_query(query, fetch=True)
    
    return render_template('approvals/director_list.html', demands=demands or [])

@app.route('/director-approve/<demand_no>')
@role_required('director')
def director_approve_view(demand_no):
    """View demand note details for director approval"""
    from database import execute_query
    
    # Get demand note details
    demand_query = "SELECT * FROM demand_notes WHERE demand_no = %s"
    demand = execute_query(demand_query, (demand_no,), fetch_one=True)
    
    if not demand:
        flash('Demand note not found', 'error')
        return redirect(url_for('director_approvals'))
    
    # Get components from demand_items
    demand_id = demand.get('id')
    components = execute_query("SELECT * FROM demand_items WHERE demand_id = %s ORDER BY sr_no", (demand_id,), fetch=True) if demand_id else []
    
    return render_template('approvals/director_view.html', 
                         demand=demand, 
                         components=components or [],
                         total_components=len(components or []))

@app.route('/director-approve/<demand_no>/submit', methods=['POST'])
@role_required('director')
def director_approve_submit(demand_no):
    """Final approve demand note and send to Supply Chain"""
    from database import execute_query
    
    user_email = session.get('user_email')
    
    # Update approval status to approved and set approved flag
    update_query = """
        UPDATE demand_notes 
        SET approval_status = 'approved',
            approved = TRUE,
            approved_by_director = %s,
            director_approved_at = NOW()
        WHERE demand_no = %s
    """
    execute_query(update_query, (user_email, demand_no), commit=True)
    
    flash(f'Demand note {demand_no} approved and sent to Supply Chain', 'success')
    return redirect(url_for('director_approvals'))

@app.route('/gm-approvals')
@role_required('general manager')
def gm_approvals():
    """List demand notes pending GM approval"""
    from database import execute_query
    
    query = """
        SELECT * FROM demand_notes 
        WHERE approval_status = 'pending_gm'
        ORDER BY created_at DESC
    """
    demands = execute_query(query, fetch=True)
    
    return render_template('approvals/gm_list.html', demands=demands or [])

@app.route('/gm-approve/<demand_no>')
@role_required('general manager')
def gm_approve_view(demand_no):
    """View demand note details for GM approval"""
    from database import execute_query
    
    # Get demand note details
    demand_query = "SELECT * FROM demand_notes WHERE demand_no = %s"
    demand = execute_query(demand_query, (demand_no,), fetch_one=True)
    
    if not demand:
        flash('Demand note not found', 'error')
        return redirect(url_for('gm_approvals'))
    
    # Get components from demand_items
    demand_id = demand.get('id')
    components = execute_query("SELECT * FROM demand_items WHERE demand_id = %s ORDER BY sr_no", (demand_id,), fetch=True) if demand_id else []
    
    return render_template('approvals/gm_view.html', 
                         demand=demand, 
                         components=components or [],
                         total_components=len(components or []))

@app.route('/gm-approve/<demand_no>/submit', methods=['POST'])
@role_required('general manager')
def gm_approve_submit(demand_no):
    """Approve demand note and send to Director"""
    from database import execute_query
    
    user_email = session.get('user_email')
    
    # Update approval status to pending_director
    update_query = """
        UPDATE demand_notes 
        SET approval_status = 'pending_director',
            approved_by_gm = %s,
            gm_approved_at = NOW()
        WHERE demand_no = %s
    """
    execute_query(update_query, (user_email, demand_no), commit=True)
    
    # Send notification to Director
    notif_query = """
        INSERT INTO notifications 
        (recipient_role, message, notification_type, related_id)
        VALUES (%s, %s, %s, %s)
    """
    message = f'Demand Note #{demand_no} requires your approval'
    execute_query(notif_query, ('director', message, 'demand_approval', demand_no), commit=True)
    
    flash(f'Demand note {demand_no} approved and sent to Director', 'success')
    return redirect(url_for('gm_approvals'))

# ============================================
# Biomedical approval routes
# ============================================

@app.route('/biomedical/director-approvals')
@role_required('director')
def director_approvals_biomedical():
    from database import execute_query
    demands = execute_query(
        "SELECT * FROM demand_notes_biomedical WHERE approval_status = 'pending_director' ORDER BY created_at DESC",
        fetch=True
    )
    return render_template('approvals/director_list.html', demands=demands or [], line='biomedical')

@app.route('/biomedical/director-approve/<demand_no>')
@role_required('director')
def director_approve_view_biomedical(demand_no):
    from database import execute_query
    demand = execute_query("SELECT * FROM demand_notes_biomedical WHERE demand_no = %s", (demand_no,), fetch_one=True)
    if not demand:
        flash('Demand note not found', 'error')
        return redirect(url_for('director_approvals_biomedical'))
    demand_id = demand.get('id')
    components = execute_query("SELECT * FROM demand_items_biomedical WHERE demand_id = %s ORDER BY sr_no", (demand_id,), fetch=True) if demand_id else []
    return render_template('approvals/director_view.html', demand=demand, components=components or [], total_components=len(components or []), line='biomedical')

@app.route('/biomedical/director-approve/<demand_no>/submit', methods=['POST'])
@role_required('director')
def director_approve_submit_biomedical(demand_no):
    from database import execute_query
    user_email = session.get('user_email')
    execute_query("""
        UPDATE demand_notes_biomedical SET approval_status = 'approved', approved = TRUE, approved_by_director = %s, director_approved_at = NOW() WHERE demand_no = %s
    """, (user_email, demand_no), commit=True)
    flash(f'Demand note {demand_no} approved and sent to Supply Chain', 'success')
    return redirect(url_for('director_approvals_biomedical'))

@app.route('/biomedical/gm-approvals')
@role_required('general manager_biomedical')
def gm_approvals_biomedical():
    from database import execute_query
    demands = execute_query(
        "SELECT * FROM demand_notes_biomedical WHERE approval_status = 'pending_gm' ORDER BY created_at DESC",
        fetch=True
    )
    return render_template('approvals/gm_list.html', demands=demands or [], line='biomedical')

@app.route('/biomedical/gm-approve/<demand_no>')
@role_required('general manager_biomedical')
def gm_approve_view_biomedical(demand_no):
    from database import execute_query
    demand = execute_query("SELECT * FROM demand_notes_biomedical WHERE demand_no = %s", (demand_no,), fetch_one=True)
    if not demand:
        flash('Demand note not found', 'error')
        return redirect(url_for('gm_approvals_biomedical'))
    demand_id = demand.get('id')
    components = execute_query("SELECT * FROM demand_items_biomedical WHERE demand_id = %s ORDER BY sr_no", (demand_id,), fetch=True) if demand_id else []
    return render_template('approvals/gm_view.html', demand=demand, components=components or [], total_components=len(components or []), line='biomedical')

@app.route('/biomedical/gm-approve/<demand_no>/submit', methods=['POST'])
@role_required('general manager_biomedical')
def gm_approve_submit_biomedical(demand_no):
    from database import execute_query
    user_email = session.get('user_email')
    execute_query("""
        UPDATE demand_notes_biomedical SET approval_status = 'pending_director', approved_by_gm = %s, gm_approved_at = NOW() WHERE demand_no = %s
    """, (user_email, demand_no), commit=True)
    execute_query("INSERT INTO notifications (recipient_role, message, notification_type, related_id) VALUES (%s, %s, %s, %s)",
                  ('director', f'Demand Note #{demand_no} requires your approval (Biomedical)', 'demand_approval', demand_no), commit=True)
    flash(f'Demand note {demand_no} approved and sent to Director', 'success')
    return redirect(url_for('gm_approvals_biomedical'))

# ============================================
# Battery approval routes
# ============================================

@app.route('/battery/director-approvals')
@role_required('director')
def director_approvals_battery():
    from database import execute_query
    demands = execute_query(
        "SELECT * FROM demand_notes_battery WHERE approval_status = 'pending_director' ORDER BY created_at DESC",
        fetch=True
    )
    return render_template('approvals/director_list.html', demands=demands or [], line='battery')

@app.route('/battery/director-approve/<demand_no>')
@role_required('director')
def director_approve_view_battery(demand_no):
    from database import execute_query
    demand = execute_query("SELECT * FROM demand_notes_battery WHERE demand_no = %s", (demand_no,), fetch_one=True)
    if not demand:
        flash('Demand note not found', 'error')
        return redirect(url_for('director_approvals_battery'))
    demand_id = demand.get('id')
    components = execute_query("SELECT * FROM demand_items_battery WHERE demand_id = %s ORDER BY sr_no", (demand_id,), fetch=True) if demand_id else []
    return render_template('approvals/director_view.html', demand=demand, components=components or [], total_components=len(components or []), line='battery')

@app.route('/battery/director-approve/<demand_no>/submit', methods=['POST'])
@role_required('director')
def director_approve_submit_battery(demand_no):
    from database import execute_query
    user_email = session.get('user_email')
    execute_query("""
        UPDATE demand_notes_battery SET approval_status = 'approved', approved = TRUE, approved_by_director = %s, director_approved_at = NOW() WHERE demand_no = %s
    """, (user_email, demand_no), commit=True)
    flash(f'Demand note {demand_no} approved and sent to Supply Chain', 'success')
    return redirect(url_for('director_approvals_battery'))

@app.route('/battery/gm-approvals')
@role_required('general manager_battery')
def gm_approvals_battery():
    from database import execute_query
    demands = execute_query(
        "SELECT * FROM demand_notes_battery WHERE approval_status = 'pending_gm' ORDER BY created_at DESC",
        fetch=True
    )
    return render_template('approvals/gm_list.html', demands=demands or [], line='battery')

@app.route('/battery/gm-approve/<demand_no>')
@role_required('general manager_battery')
def gm_approve_view_battery(demand_no):
    from database import execute_query
    demand = execute_query("SELECT * FROM demand_notes_battery WHERE demand_no = %s", (demand_no,), fetch_one=True)
    if not demand:
        flash('Demand note not found', 'error')
        return redirect(url_for('gm_approvals_battery'))
    demand_id = demand.get('id')
    components = execute_query("SELECT * FROM demand_items_battery WHERE demand_id = %s ORDER BY sr_no", (demand_id,), fetch=True) if demand_id else []
    return render_template('approvals/gm_view.html', demand=demand, components=components or [], total_components=len(components or []), line='battery')

@app.route('/battery/gm-approve/<demand_no>/submit', methods=['POST'])
@role_required('general manager_battery')
def gm_approve_submit_battery(demand_no):
    from database import execute_query
    user_email = session.get('user_email')
    execute_query("""
        UPDATE demand_notes_battery SET approval_status = 'pending_director', approved_by_gm = %s, gm_approved_at = NOW() WHERE demand_no = %s
    """, (user_email, demand_no), commit=True)
    execute_query("INSERT INTO notifications (recipient_role, message, notification_type, related_id) VALUES (%s, %s, %s, %s)",
                  ('director', f'Demand Note #{demand_no} requires your approval (Battery)', 'demand_approval', demand_no), commit=True)
    flash(f'Demand note {demand_no} approved and sent to Director', 'success')
    return redirect(url_for('gm_approvals_battery'))

# ============================================
# Import module routes
# ============================================

try:
    from routes import rnd, production, supply_chain, qc, store, contracts_tanks, contracts_main
    from routes import rnd_biomedical, rnd_battery
    from routes import production_biomedical, production_battery
    from routes import supply_chain_biomedical, supply_chain_battery
    from routes import qc_biomedical, qc_battery
    from routes import store_biomedical, store_battery
    from routes import contracts_biomedical, contracts_battery
    
    app.register_blueprint(rnd.bp)
    app.register_blueprint(production.bp)
    app.register_blueprint(supply_chain.bp)
    app.register_blueprint(qc.bp)
    app.register_blueprint(store.bp)
    app.register_blueprint(contracts_tanks.bp)
    app.register_blueprint(contracts_main.bp)
    app.register_blueprint(rnd_biomedical.bp)
    app.register_blueprint(rnd_battery.bp)
    app.register_blueprint(production_biomedical.bp)
    app.register_blueprint(production_battery.bp)
    app.register_blueprint(supply_chain_biomedical.bp)
    app.register_blueprint(supply_chain_battery.bp)
    app.register_blueprint(qc_biomedical.bp)
    app.register_blueprint(qc_battery.bp)
    app.register_blueprint(store_biomedical.bp)
    app.register_blueprint(store_battery.bp)
    app.register_blueprint(contracts_biomedical.bp)
    app.register_blueprint(contracts_battery.bp)
except ImportError as e:
    logger.warning(f"Could not import route modules: {e}")
    logger.info("Route modules will be loaded when available")

# ============================================
# Main Entry Point
# ============================================

if __name__ == '__main__':
    # Create necessary directories
    os.makedirs('static/uploads', exist_ok=True)
    os.makedirs('static/images', exist_ok=True)
    
    # Initialize database
    logger.info("Initializing application...")
    init_connection_pool()
    init_database()
    logger.info("Application initialized successfully")
    
    # Run the application
    # Run the application using Waitress (production server)
    logger.info(f"Starting Delta Plus ERP on {Config.HOST}:{Config.PORT}")
    logger.info("Access from other devices using: http://<server-ip>:5000")
    
    # Run the application
    # Run the application using Waitress (production server)
    logger.info(f"Starting Delta Plus ERP on {Config.HOST}:{Config.PORT}")
    logger.info("Access from other devices using: http://<server-ip>:5000")

    from waitress import serve
    serve(app, host=Config.HOST, port=Config.PORT)

@app.before_request
def check_daily_tasks():
    # Run daily checks (once per day)
    # Avoid running on static files to save resources
    if request.endpoint and 'static' not in request.endpoint:
        from daily_checks import run_daily_checks
        try:
            run_daily_checks()
        except Exception as e:
            logger.error(f"Failed to run daily checks: {e}")
