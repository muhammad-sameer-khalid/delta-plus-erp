"""Table name suffixes and template prefixes per production line (biomedical, battery)."""

def table_suffix(line):
    """Return DB table suffix for line: '' for tanks, '_biomedical' or '_battery'."""
    if line == 'biomedical':
        return '_biomedical'
    if line == 'battery':
        return '_battery'
    return ''

def template_prefix(line):
    """Return template folder prefix: 'rnd/' for tanks, 'biomedical/rnd/' for biomedical, etc."""
    if line == 'biomedical':
        return 'biomedical/'
    if line == 'battery':
        return 'battery/'
    return ''

def tbl(line, base_name):
    """Return full table name for base (e.g. bom_metadata) and line."""
    return base_name + table_suffix(line)
