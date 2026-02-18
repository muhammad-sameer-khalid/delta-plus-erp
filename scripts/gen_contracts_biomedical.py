"""Generate contracts_biomedical.py from contracts.py with line-specific tables and session."""
import re

with open('routes/contracts.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Remove the startup checks block (lines 35-147) - we don't duplicate that in line modules
content = re.sub(
    r'# ========== Daily/startup checks.*?def run_contracts_startup_checks\(\):.*?\)\n\n',
    '',
    content,
    flags=re.DOTALL
)

# Replace blueprint and add LINE, BP, SESSION_KEY, _cm, _ci at top
old_bp = "bp = Blueprint('contracts', __name__, url_prefix='/contracts')"
new_header = '''LINE = 'biomedical'
BP = 'contracts_biomedical'
SESSION_KEY = 'contracts_pending_metadata_biomedical'

from routes.line_tables import tbl
def _cm(): return tbl(LINE, 'contracts_metadata')
def _ci(): return tbl(LINE, 'contract_items')

bp = Blueprint(BP, __name__, url_prefix='/biomedical/contracts')
TP = 'line_contracts/'
'''
content = content.replace(old_bp, new_header)

# Decorator: can_access_contracts(session['user_email']) -> can_access_contracts(session['user_email'], LINE)
content = content.replace(
    "if not can_access_contracts(session['user_email']):",
    "if not can_access_contracts(session['user_email'], LINE):"
)
content = content.replace(
    "return redirect(url_for('tanks_dashboard'))",
    "return redirect(url_for('biomedical_dashboard'))"
)

# Session key
content = content.replace("session['contracts_pending_metadata']", 'session[SESSION_KEY]')
content = content.replace("session.get('contracts_pending_metadata')", 'session.get(SESSION_KEY)')
content = content.replace("session.pop('contracts_pending_metadata', None)", 'session.pop(SESSION_KEY, None)')

# Table names in SQL - contracts_metadata and contract_items
# Replace "SELECT * FROM contracts_metadata" with f"SELECT * FROM {_cm()}"
content = re.sub(r'"SELECT \* FROM contracts_metadata', r'f"SELECT * FROM {_cm()}', content)
content = re.sub(r'"SELECT 1 FROM contracts_metadata', r'f"SELECT 1 FROM {_cm()}', content)
content = re.sub(r'"SELECT contract_id FROM contracts_metadata', r'f"SELECT contract_id FROM {_cm()}', content)
content = re.sub(r'FROM contracts_metadata WHERE', r'FROM {_cm()} WHERE', content)
content = re.sub(r'FROM contracts_metadata ORDER', r'FROM {_cm()} ORDER', content)
content = re.sub(r'UPDATE contracts_metadata SET', r'f"UPDATE {_cm()} SET', content)
content = re.sub(r'INSERT INTO contracts_metadata', r'f"INSERT INTO {_cm()}', content)

content = re.sub(r'"SELECT \* FROM contract_items', r'f"SELECT * FROM {_ci()}', content)
content = re.sub(r'FROM contract_items WHERE', r'FROM {_ci()} WHERE', content)
content = re.sub(r'FROM contract_items ORDER', r'FROM {_ci()} ORDER', content)
content = re.sub(r'UPDATE contract_items SET', r'f"UPDATE {_ci()} SET', content)
content = re.sub(r'INSERT INTO contract_items ', r'f"INSERT INTO {_ci()} ', content)
content = re.sub(r'SELECT COALESCE\(SUM\(net_amount\).*?FROM contract_items', r'f"SELECT COALESCE(SUM(net_amount), 0) as s FROM {_ci()}', content)

# Fix double f" when we added f" before INSERT/UPDATE
content = content.replace('f"f"', 'f"')

# url_for('contracts. -> url_for(f'{BP}.
content = content.replace("url_for('contracts.", "url_for(f'{BP}.")

# render_template('contracts/ -> render_template(TP +
content = content.replace("render_template('contracts/", "render_template(TP + '")

# _get_accessible_modules with LINE
content = content.replace(
    "if can_access_module(user_email, m)]",
    "if can_access_module(user_email, m, LINE)]"
)

# Fix iterate_url and specific_url in templates - they are passed from view, so no change needed in route

with open('routes/contracts_biomedical.py', 'w', encoding='utf-8') as f:
    f.write(content)
print('Generated routes/contracts_biomedical.py')
