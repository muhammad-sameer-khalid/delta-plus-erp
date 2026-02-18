"""RND Module Routes - Biomedical production line"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session
from auth import module_access_required, can_access_module
from database import execute_query
from routes.line_tables import table_suffix, tbl
import logging

logger = logging.getLogger(__name__)
LINE = 'biomedical'
SUFFIX = table_suffix(LINE)
TEMPLATE_PREFIX = 'line_rnd/'

def merge_duplicate_components(components):
    if not components:
        return []
    merged_indices = set()
    result = []
    for i, comp1 in enumerate(components):
        if i in merged_indices:
            continue
        merged_comp = {
            'designator': comp1.get('designator', ''),
            'part_type': comp1.get('part_type', ''),
            'part_value': comp1.get('part_value', ''),
            'part_description': comp1.get('part_description', ''),
            'footprint': comp1.get('footprint', ''),
            'qty': comp1.get('qty', 0)
        }
        for j, comp2 in enumerate(components):
            if i == j or j in merged_indices:
                continue
            if (comp1.get('designator', '').strip().lower() == comp2.get('designator', '').strip().lower() and
                comp1.get('part_type', '').strip().lower() == comp2.get('part_type', '').strip().lower() and
                comp1.get('part_value', '').strip().lower() == comp2.get('part_value', '').strip().lower() and
                comp1.get('part_description', '').strip().lower() == comp2.get('part_description', '').strip().lower() and
                comp1.get('footprint', '').strip().lower() == comp2.get('footprint', '').strip().lower()):
                merged_comp['qty'] += comp2.get('qty', 0)
                merged_indices.add(j)
        result.append(merged_comp)
    return result

bp = Blueprint('rnd_biomedical', __name__, url_prefix='/biomedical/rnd')
bm, bi = lambda: tbl(LINE, 'bom_metadata'), lambda: tbl(LINE, 'bom_items')

def _accessible(line):
    user_email = session.get('user_email')
    return [m for m in ['rnd', 'production', 'supply_chain', 'qc', 'store'] if can_access_module(user_email, m, line)]

@bp.route('/')
@module_access_required('rnd', LINE)
def rnd_dashboard():
    return render_template(TEMPLATE_PREFIX + 'dashboard.html', show_nav_menu=True, accessible_modules=_accessible(LINE), line=LINE, bp='rnd_biomedical')

@bp.route('/generate-bom', methods=['GET', 'POST'])
@module_access_required('rnd', LINE)
def generate_bom():
    if request.method == 'POST':
        bom_name = request.form.get('bom_name', '').strip()
        bom_type = request.form.get('bom_type', '').strip()
        if not bom_name or not bom_type:
            flash('BOM name and type are required', 'error')
            return redirect(url_for('rnd_biomedical.generate_bom'))
        check_query = f"SELECT COUNT(*) as count FROM {bm()} WHERE bom_name = %s"
        result = execute_query(check_query, (bom_name,), fetch_one=True)
        if result and result['count'] > 0:
            flash(f'A BOM with the name "{bom_name}" already exists', 'error')
            return redirect(url_for('rnd_biomedical.generate_bom'))
        execute_query(f"INSERT INTO {bm()} (bom_name, bom_type) VALUES (%s, %s)", (bom_name, bom_type), commit=True)
        bom_row = execute_query(f"SELECT id FROM {bm()} WHERE bom_name = %s", (bom_name,), fetch_one=True)
        bom_id = bom_row['id'] if bom_row else None
        if not bom_id:
            flash('Failed to create BOM', 'error')
            return redirect(url_for('rnd_biomedical.generate_bom'))
        components = []
        i = 0
        while f'designator_{i}' in request.form:
            components.append({
                'designator': request.form.get(f'designator_{i}', ''),
                'part_type': request.form.get(f'part_type_{i}', ''),
                'part_value': request.form.get(f'part_value_{i}', ''),
                'part_description': request.form.get(f'part_description_{i}', ''),
                'footprint': request.form.get(f'footprint_{i}', ''),
                'qty': int(request.form.get(f'qty_{i}', 0))
            })
            i += 1
        merged_components = merge_duplicate_components(components)
        if merged_components:
            from database import execute_many
            insert_comp_query = f"INSERT INTO {bi()} (bom_id, designator, part_type, part_value, part_description, footprint, qty) VALUES (%s, %s, %s, %s, %s, %s, %s)"
            params_list = [(bom_id, c['designator'], c['part_type'], c['part_value'], c['part_description'], c['footprint'], c['qty']) for c in merged_components]
            execute_many(insert_comp_query, params_list)
        flash(f'BOM "{bom_name}" created successfully', 'success')
        return redirect(url_for('rnd_biomedical.display_bom'))
    return render_template(TEMPLATE_PREFIX + 'generate_bom.html', show_nav_menu=True, accessible_modules=_accessible(LINE), line=LINE, bp='rnd_biomedical')

@bp.route('/display-bom')
@module_access_required('rnd', LINE)
def display_bom():
    boms = execute_query(f"SELECT * FROM {bm()} ORDER BY created_at DESC", fetch=True)
    return render_template(TEMPLATE_PREFIX + 'display_bom.html', boms=boms or [], show_nav_menu=True, accessible_modules=_accessible(LINE), line=LINE, bp='rnd_biomedical')

@bp.route('/view-bom/<int:bom_id>')
@module_access_required('rnd', LINE)
def view_bom(bom_id):
    bom = execute_query(f"SELECT * FROM {bm()} WHERE id = %s", (bom_id,), fetch_one=True)
    if not bom:
        flash('BOM not found', 'error')
        return redirect(url_for('rnd_biomedical.display_bom'))
    components = execute_query(f"SELECT * FROM {bi()} WHERE bom_id = %s ORDER BY id", (bom_id,), fetch=True) or []
    return render_template(TEMPLATE_PREFIX + 'view_bom.html', bom=bom, components=components or [], show_nav_menu=True, accessible_modules=_accessible(LINE), line=LINE, bp='rnd_biomedical')

@bp.route('/edit-bom-form/<int:bom_id>', methods=['GET', 'POST'])
@module_access_required('rnd', LINE)
def edit_bom_form(bom_id):
    bom = execute_query(f"SELECT * FROM {bm()} WHERE id = %s", (bom_id,), fetch_one=True)
    if not bom:
        flash('BOM not found', 'error')
        return redirect(url_for('rnd_biomedical.edit_bom'))
    bid = bom['id']
    if request.method == 'POST':
        execute_query(f"DELETE FROM {bi()} WHERE bom_id = %s", (bid,), commit=True)
        components = []
        i = 0
        while f'designator_{i}' in request.form:
            components.append({
                'designator': request.form.get(f'designator_{i}', ''),
                'part_type': request.form.get(f'part_type_{i}', ''),
                'part_value': request.form.get(f'part_value_{i}', ''),
                'part_description': request.form.get(f'part_description_{i}', ''),
                'footprint': request.form.get(f'footprint_{i}', ''),
                'qty': int(request.form.get(f'qty_{i}', 0))
            })
            i += 1
        merged_components = merge_duplicate_components(components)
        if merged_components:
            from database import execute_many
            insert_comp_query = f"INSERT INTO {bi()} (bom_id, designator, part_type, part_value, part_description, footprint, qty) VALUES (%s, %s, %s, %s, %s, %s, %s)"
            params_list = [(bid, c['designator'], c['part_type'], c['part_value'], c['part_description'], c['footprint'], c['qty']) for c in merged_components]
            execute_many(insert_comp_query, params_list)
        flash(f'BOM "{bom["bom_name"]}" updated successfully', 'success')
        return redirect(url_for('rnd_biomedical.edit_bom'))
    components = execute_query(f"SELECT * FROM {bi()} WHERE bom_id = %s ORDER BY id", (bid,), fetch=True) or []
    return render_template(TEMPLATE_PREFIX + 'edit_bom_form.html', bom=bom, components=components or [], show_nav_menu=True, accessible_modules=_accessible(LINE), line=LINE, bp='rnd_biomedical')

@bp.route('/edit-bom')
@module_access_required('rnd', LINE)
def edit_bom():
    boms = execute_query(f"SELECT * FROM {bm()} ORDER BY created_at DESC", fetch=True)
    return render_template(TEMPLATE_PREFIX + 'edit_bom.html', boms=boms or [], show_nav_menu=True, accessible_modules=_accessible(LINE), line=LINE, bp='rnd_biomedical')

@bp.route('/delete-bom/<int:bom_id>', methods=['POST'])
@module_access_required('rnd', LINE)
def delete_bom(bom_id):
    bom = execute_query(f"SELECT id FROM {bm()} WHERE id = %s", (bom_id,), fetch_one=True)
    if bom:
        execute_query(f"DELETE FROM {bi()} WHERE bom_id = %s", (bom_id,), commit=True)
        execute_query(f"DELETE FROM {bm()} WHERE id = %s", (bom_id,), commit=True)
        flash('BOM deleted successfully', 'success')
    else:
        flash('BOM not found', 'error')
    return redirect(url_for('rnd_biomedical.edit_bom'))

@bp.route('/api/boms')
@module_access_required('rnd', LINE)
def get_boms_api():
    boms = execute_query(f"SELECT id, bom_name, bom_type FROM {bm()} ORDER BY bom_name", fetch=True)
    return jsonify({'success': True, 'boms': boms or []})

@bp.route('/api/bom/<int:bom_id>/components')
@module_access_required('rnd', LINE)
def get_bom_components_api(bom_id):
    bom = execute_query(f"SELECT * FROM {bm()} WHERE id = %s", (bom_id,), fetch_one=True)
    if not bom:
        return jsonify({'success': False, 'message': 'BOM not found'})
    components = execute_query(f"SELECT * FROM {bi()} WHERE bom_id = %s ORDER BY id", (bom_id,), fetch=True) or []
    return jsonify({'success': True, 'components': components})
