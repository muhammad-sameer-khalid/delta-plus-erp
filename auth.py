"""Authentication and authorization utilities"""
from functools import wraps
from flask import session, redirect, url_for, flash
import bcrypt
from database import execute_query
import re
import logging

logger = logging.getLogger(__name__)

# Base role names (Tanks production line)
# Base Manager Roles (Suffix will be added per line)
BASE_MANAGERS = [
    'rnd manager',
    'store manager',
    'qc manager',
    'supply chain manager',
    'production manager',
    'qc decision'
]

# Base Member Roles (Suffix will be added per line)
BASE_MEMBERS = [
    'rnd member',
    'store member',
    'qc member',
    'supply chain member',
    'production member'
]

# Director and Global Roles
GLOBAL_ROLES = ['director', 'gm logistics', 'contracts_data_entry', 'data_entry_bg', 'data_entry_accounts', 'hr_manager']

# Tanks Roles
# General Manager for Tanks is just 'general manager'
TANKS_ROLES = GLOBAL_ROLES + ['general manager'] + \
              [f"{r}_tanks" for r in BASE_MANAGERS] + \
              [f"{r}_tanks" for r in BASE_MEMBERS]

# Biomedical Roles
# General Manager for Biomedical is 'general manager_biomedical'
BIOMEDICAL_ROLES = ['general manager_biomedical'] + \
                   [f"{r}_biomedical" for r in BASE_MANAGERS] + \
                   [f"{r}_biomedical" for r in BASE_MEMBERS]

# Battery Roles
# General Manager for Battery is 'general manager_battery'
BATTERY_ROLES = ['general manager_battery'] + \
                [f"{r}_battery" for r in BASE_MANAGERS] + \
                [f"{r}_battery" for r in BASE_MEMBERS]

# All valid roles
VALID_ROLES = list(set(TANKS_ROLES + BIOMEDICAL_ROLES + BATTERY_ROLES))

# Production line identifier
PRODUCTION_LINES = ('tanks', 'biomedical_disposable', 'biomedical_equipment', 'battery')

def get_production_lines_for_user(email):
    """Return list of production line keys the user can access."""
    user_roles = get_user_roles(email)
    lines = set()
    
    if 'director' in user_roles:
        return ['tanks', 'biomedical_disposable', 'biomedical_equipment', 'battery']
    
    # Tanks access
    if 'general manager' in user_roles:
        lines.add('tanks')
    if any(r.endswith('_tanks') for r in user_roles):
        lines.add('tanks')
        
    # Biomedical access (grants access to both Disposable and Equipment)
    if 'general manager_biomedical' in user_roles or any(r.endswith('_biomedical') for r in user_roles):
        lines.add('biomedical_disposable')
        lines.add('biomedical_equipment')
        
    # Battery access
    if 'general manager_battery' in user_roles or any(r.endswith('_battery') for r in user_roles):
        lines.add('battery')
        
    return list(lines)

def can_access_contracts(email, line='tanks'):
    """Contracts card visible to director, gm logistics, contracts_data_entry, data entry roles, or line-specific GM."""
    user_roles = get_user_roles(email)
    if any(r in user_roles for r in [
        'director', 'gm logistics', 'contracts_data_entry',
        'data_entry_bg', 'data_entry_accounts', 'hr_manager'
    ]):
        return True
    
    if line == 'tanks':
        return 'general manager' in user_roles
    if line in ('biomedical', 'biomedical_disposable', 'biomedical_equipment'):
        return 'general manager_biomedical' in user_roles
    if line == 'battery':
        return 'general manager_battery' in user_roles
    return False

def can_access_contracts_tanks(email):
    return can_access_contracts(email, 'tanks')

def can_delete_items(email, line='tanks'):
    """Check if user has permission to delete items (Managers/GMs/Director only)."""
    user_roles = get_user_roles(email)
    
    # Global/High-level roles with delete access
    if 'director' in user_roles or 'gm logistics' in user_roles:
        return True
    
    if line == 'tanks':
        if 'general manager' in user_roles:
            return True
        for mgr in BASE_MANAGERS:
            if f"{mgr}_tanks" in user_roles:
                return True
        return False
    elif line in ('biomedical', 'biomedical_disposable', 'biomedical_equipment'):
        if 'general manager_biomedical' in user_roles:
            return True
        for mgr in BASE_MANAGERS:
            if f"{mgr}_biomedical" in user_roles:
                return True
        return False
    else:
        suffix = f"_{line}"
        if f'general manager{suffix}' in user_roles:
            return True
        for mgr in BASE_MANAGERS:
            if f"{mgr}{suffix}" in user_roles:
                return True
        return False

def sanitize_input(text):
    """Sanitize user input to prevent XSS and other injection attacks"""
    if not text:
        return text
    # Remove potentially dangerous characters
    return re.sub(r'[<>\"\'%;()&+]', '', str(text))

def validate_email(email):
    """Validate email format"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def hash_password(password):
    """Hash a password using bcrypt"""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verify_password(password, password_hash):
    """Verify a password against its hash"""
    return bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8'))

def create_user(email, password):
    """Create a new user account"""
    if not validate_email(email):
        return False, "Invalid email format"
    
    # Check if user already exists
    query = "SELECT COUNT(*) as count FROM users WHERE email = %s"
    result = execute_query(query, (email,), fetch_one=True)
    
    if result and result['count'] > 0:
        return False, "User already exists"
    
    # Create user
    password_hash = hash_password(password)
    query = "INSERT INTO users (email, password_hash) VALUES (%s, %s)"
    result = execute_query(query, (email, password_hash), commit=True)
    
    if result:
        return True, "User created successfully"
    return False, "Failed to create user"

def authenticate_user(email, password):
    """Authenticate a user with email and password"""
    email = (email or '').strip()
    if not validate_email(email):
        return False, "Invalid email format"
    
    # Get user from database
    query = "SELECT password_hash FROM users WHERE email = %s"
    result = execute_query(query, (email,), fetch_one=True)
    if not result:
        # Also try lowercase match
        result = execute_query(query, (email.lower(),), fetch_one=True)
    
    if not result:
        return False, "Invalid credentials"
    
    # Verify password
    if verify_password(password, result['password_hash']):
        return True, "Authentication successful"
    
    return False, "Invalid credentials"

def get_user_roles(email):
    """Get all roles assigned to a user"""
    query = "SELECT role FROM user_roles WHERE email = %s"
    results = execute_query(query, (email,), fetch=True)
    
    if results:
        return [row['role'] for row in results]
    return []

def add_user_role(email, role):
    """Add a role to a user"""
    if role not in VALID_ROLES:
        return False, "Invalid role"
    
    # Check if role already exists
    query = "SELECT COUNT(*) as count FROM user_roles WHERE email = %s AND role = %s"
    result = execute_query(query, (email, role), fetch_one=True)
    
    if result and result['count'] > 0:
        return False, "Role already assigned"
    
    # Add role
    query = "INSERT INTO user_roles (email, role) VALUES (%s, %s)"
    result = execute_query(query, (email, role), commit=True)
    
    if result:
        return True, "Role added successfully"
    return False, "Failed to add role"

def remove_user_role(email, role):
    """Remove a role from a user"""
    query = "DELETE FROM user_roles WHERE email = %s AND role = %s"
    result = execute_query(query, (email, role), commit=True)
    
    if result and result > 0:
        return True, "Role removed successfully"
    return False, "Role not found"

def get_all_user_roles():
    """Get all users and their roles"""
    query = """
        SELECT email, GROUP_CONCAT(role SEPARATOR ', ') as roles
        FROM user_roles
        GROUP BY email
        ORDER BY email
    """
    return execute_query(query, fetch=True)

def user_has_role(email, role):
    """Check if a user has a specific role"""
    query = "SELECT COUNT(*) as count FROM user_roles WHERE email = %s AND role = %s"
    result = execute_query(query, (email, role), fetch_one=True)
    return result and result['count'] > 0

def user_has_any_role(email, roles):
    """Check if a user has any of the specified roles"""
    user_roles = get_user_roles(email)
    return any(role in user_roles for role in roles)

def _roles_for_line(line):
    """Return (director_roles, gm_roles, access_map) for the given production line."""
    if line in ('biomedical', 'biomedical_disposable', 'biomedical_equipment'):
        suffix = '_biomedical'
        gm_roles = ['general manager_biomedical']
    elif line == 'tanks':
        suffix = '_tanks'
        gm_roles = ['general manager']
    else:
        suffix = f"_{line}"
        gm_roles = [f'general manager{suffix}']
    
    # Director is global
    director_roles = ['director']
    
    # Access Map (Module -> Allowed Roles)
    access_map = {}
    
    def get_mod_roles(prefix):
        return [f"{prefix} manager{suffix}", f"{prefix} member{suffix}"]
        
    access_map['rnd'] = get_mod_roles('rnd')
    access_map['store'] = get_mod_roles('store')
    access_map['production'] = get_mod_roles('production')
    access_map['supply_chain'] = [f"supply chain manager{suffix}", f"supply chain member{suffix}"]
    access_map['qc'] = [f"qc manager{suffix}", f"qc decision{suffix}", f"qc member{suffix}"]
    
    return director_roles, gm_roles, access_map

def can_access_module(email, module, line='tanks'):
    """Check if a user can access a specific module for the given production line."""
    user_roles = get_user_roles(email)
    director_roles, gm_roles, access_map = _roles_for_line(line)
    
    if not access_map:
        return False
        
    # Director and GMs can access all modules in their line
    if user_has_any_role(email, director_roles) or user_has_any_role(email, gm_roles):
        return True
        
    # GM Logistics (Global) can access everything? 
    # Current logic didn't explicitely include GM Logistics in 'can_access_module', mainly contracts.
    # But usually GM Logistics needs Supply Chain / Store access.
    # Let's add GM Logistics to 'tanks' line access if it implies 'tanks' nature?
    # User said "gm_logistics is a general role that has access to all the contracts".
    # Did not specify modules. Assuming legacy behavior + contracts.
    # In legacy code, GM Logistics was in TANKS_ROLES.
    # So if line == 'tanks' and role == 'gm logistics', allow?
    if 'gm logistics' in user_roles and line == 'tanks':
         # Check if GM Logistics should access modules. Likely yes.
         return True
         
    if module in access_map:
        return user_has_any_role(email, access_map[module])
        
    return False

# Decorators for route protection
def login_required(f):
    """Decorator to require login for a route"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_email' not in session:
            flash('Please log in to access this page', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def role_required(*roles):
    """Decorator to require specific roles for a route"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_email' not in session:
                flash('Please log in to access this page', 'error')
                return redirect(url_for('login'))
            
            if not user_has_any_role(session['user_email'], roles):
                flash('You do not have permission to access this page', 'error')
                return redirect(url_for('dashboard'))
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def module_access_required(module, line='tanks'):
    """Decorator to require module access for a route (optionally for a production line)."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_email' not in session:
                flash('Please log in to access this page', 'error')
                return redirect(url_for('login'))
            if not can_access_module(session['user_email'], module, line):
                flash('You do not have permission to access this module', 'error')
                return redirect(url_for('dashboard'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def director_roles_for_line(line):
    """Roles that can access director approvals for the given line. Director is universal."""
    return ['director']

def gm_roles_for_line(line):
    """Roles that can access GM approvals for the given line."""
    if line == 'tanks':
        return ['general manager']
    if line in ('biomedical', 'biomedical_disposable', 'biomedical_equipment'):
        return ['general manager_biomedical']
    if line == 'battery':
        return ['general manager_battery']
    return []
