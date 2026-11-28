"""Table name suffixes and template prefixes per production line (tanks, biomedical, battery)."""

def table_suffix(line):
    """Return DB table suffix for line: '' for tanks, '_biomedical', '_battery'."""
    if line in ('biomedical', 'biomedical_disposable', 'biomedical_equipment'):
        return '_biomedical'
    if line == 'battery':
        return '_battery'
    return ''

def template_prefix(line):
    if line in ('biomedical', 'biomedical_disposable', 'biomedical_equipment'):
        return 'biomedical/'
    if line == 'battery':
        return 'battery/'
    return ''

def tbl(line, base_name):
    """Return full table name for base (e.g. bom_metadata) and line."""
    return base_name + table_suffix(line)
