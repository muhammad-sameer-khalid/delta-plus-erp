"""
Utility functions for the Delta Plus ERP system
"""

def deduplicate_components(components_list):
    """
    Deduplicate components and aggregate quantities
    
    Args:
        components_list: List of component dictionaries with keys:
                        part_type, part_value, part_description, footprint, qty
    
    Returns:
        List of deduplicated components with aggregated quantities
    """
    component_map = {}
    
    for component in components_list:
        # Create unique key based on component attributes
        key = (
            component.get('part_type', '').strip().lower(),
            component.get('part_value', '').strip().lower(),
            component.get('part_description', '').strip().lower(),
            component.get('footprint', '').strip().lower()
        )
        
        if key in component_map:
            # Aggregate quantity
            component_map[key]['qty'] += component.get('qty', 0)
        else:
            # Add new component
            component_map[key] = {
                'part_type': component.get('part_type', ''),
                'part_value': component.get('part_value', ''),
                'part_description': component.get('part_description', ''),
                'footprint': component.get('footprint', ''),
                'qty': component.get('qty', 0)
            }
    
    # Convert back to list and sort by part_type
    deduplicated = list(component_map.values())
    deduplicated.sort(key=lambda x: (x['part_type'], x['part_value']))
    
    return deduplicated


def check_inventory_availability(part_type, part_value, part_description, footprint, required_qty, db_execute_query):
    """
    Check if sufficient quantity is available in inventory
    
    Args:
        part_type: Component part type
        part_value: Component part value
        part_description: Component description
        footprint: Component footprint
        required_qty: Required quantity
        db_execute_query: Database execute_query function
    
    Returns:
        Tuple (is_available: bool, available_qty: int, message: str)
    """
    # Search across all store categories
    categories = [
        'resistors', 'capacitors', 'inductors', 'diodes', 
        'transistors', 'ics', 'connectors', 'misc', 'pcbs'
    ]
    
    total_available = 0
    
    for category in categories:
        query = f"""
            SELECT SUM(qty) as total_qty 
            FROM store_{category}
            WHERE part_type = %s 
            AND part_value = %s 
            AND part_description = %s 
            AND footprint = %s
        """
        
        result = db_execute_query(
            query, 
            (part_type, part_value, part_description, footprint),
            fetch_one=True
        )
        
        if result and result.get('total_qty'):
            total_available += result['total_qty']
    
    is_available = total_available >= required_qty
    
    if is_available:
        message = f"Available: {total_available} units"
    else:
        shortage = required_qty - total_available
        message = f"Insufficient stock! Available: {total_available}, Required: {required_qty}, Short: {shortage}"
    
    return is_available, total_available, message


def validate_issue_quantities(components, db_execute_query):
    """
    Validate that all components in an issue have sufficient inventory
    
    Args:
        components: List of components to issue
        db_execute_query: Database execute_query function
    
    Returns:
        Tuple (all_available: bool, validation_results: list)
    """
    validation_results = []
    all_available = True
    
    for component in components:
        is_available, available_qty, message = check_inventory_availability(
            component.get('part_type', ''),
            component.get('part_value', ''),
            component.get('part_description', ''),
            component.get('footprint', ''),
            component.get('qty', 0),
            db_execute_query
        )
        
        validation_results.append({
            'component': component,
            'is_available': is_available,
            'available_qty': available_qty,
            'message': message
        })
        
        if not is_available:
            all_available = False
    
    return all_available, validation_results


def format_component_display(component):
    """
    Format component for display in dropdowns and lists
    
    Args:
        component: Component dictionary
    
    Returns:
        Formatted string
    """
    parts = []
    
    if component.get('part_type'):
        parts.append(component['part_type'])
    if component.get('part_value'):
        parts.append(component['part_value'])
    if component.get('part_description'):
        parts.append(component['part_description'])
    if component.get('footprint'):
        parts.append(f"[{component['footprint']}]")
    
    return ' - '.join(parts) if parts else 'Unknown Component'


def generate_po_number(prefix='PO', db_execute_query):
    """
    Generate next PO number automatically
    
    Args:
        prefix: PO number prefix (default: 'PO')
        db_execute_query: Database execute_query function
    
    Returns:
        Next PO number (e.g., 'PO-001', 'PO-002')
    """
    query = """
        SELECT po_no FROM purchase_orders 
        WHERE po_no LIKE %s 
        ORDER BY po_no DESC 
        LIMIT 1
    """
    
    result = db_execute_query(query, (f"{prefix}-%",), fetch_one=True)
    
    if result and result.get('po_no'):
        # Extract number from last PO
        last_po = result['po_no']
        try:
            last_num = int(last_po.split('-')[-1])
            next_num = last_num + 1
        except (ValueError, IndexError):
            next_num = 1
    else:
        next_num = 1
    
    return f"{prefix}-{next_num:03d}"


def generate_demand_number(db_execute_query):
    """
    Generate next demand note number automatically
    
    Args:
        db_execute_query: Database execute_query function
    
    Returns:
        Next demand number (integer)
    """
    query = "SELECT MAX(demand_no) as max_demand FROM demand_notes"
    result = db_execute_query(query, fetch_one=True)
    
    if result and result.get('max_demand'):
        return result['max_demand'] + 1
    else:
        return 1


def calculate_total_cost(components):
    """
    Calculate total cost of components
    
    Args:
        components: List of components with unit_price and qty
    
    Returns:
        Total cost
    """
    total = 0
    for component in components:
        unit_price = component.get('unit_price', 0) or 0
        qty = component.get('qty', 0) or 0
        total += unit_price * qty
    
    return total


def sanitize_table_name(name):
    """
    Sanitize table name to prevent SQL injection
    
    Args:
        name: Table name to sanitize
    
    Returns:
        Sanitized table name
    """
    # Remove any non-alphanumeric characters except underscore
    import re
    sanitized = re.sub(r'[^a-zA-Z0-9_]', '_', str(name))
    
    # Ensure it starts with a letter
    if sanitized and not sanitized[0].isalpha():
        sanitized = 'tbl_' + sanitized
    
    return sanitized.lower()
