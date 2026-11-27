"""Database schema initialization"""
from database import execute_query, table_exists
import logging

logger = logging.getLogger(__name__)

def create_all_tables():
    """Create all required tables for the ERP system"""
    
    # Users and Roles
    create_users_table()
    create_roles_table()
    
    # BOM tables
    create_bom_metadata_table()
    
    # Demand notes
    create_demand_notes_table()
    
    # Notifications
    create_notifications_table()
    
    # Purchase orders
    create_po_metadata_table()
    
    # Quality Control
    create_qc_tables()
    
    # Store inventory
    create_store_tables()
    
    # Issues
    create_issues_metadata_table()
    create_issue_items_table()
    
    # Demand items (single table for all demand line items)
    create_demand_items_table()
    
    # PO items (single table for all PO line items)
    create_po_items_table()
    
    # BOM items (single table for all BOM components)
    create_bom_items_table()
    
    # Contracts
    create_contracts_metadata_table()
    create_contract_items_table()
    create_contracts_daily_check_table()
    create_cdr_table()
    
    # Biomedical and Battery production line tables (full replica per line)
    create_line_tables('_biomedical')
    create_line_tables('_biomedical_disposable')
    create_line_tables('_biomedical_equipment')
    create_line_tables('_battery')
    
    # Initialize default admin
    initialize_default_admin()
    
    # Refresh table cache so all newly created tables are immediately recognized
    from database import get_existing_tables
    get_existing_tables(force_refresh=True)

def create_line_tables(suffix):
    """Create full set of tables for a production line (suffix = '_biomedical' or '_battery')."""
    create_bom_metadata_table_suffix(suffix)
    create_bom_items_table_suffix(suffix)
    create_demand_notes_table_suffix(suffix)
    create_demand_items_table_suffix(suffix)
    create_po_metadata_table_suffix(suffix)
    create_po_items_table_suffix(suffix)
    create_qc_tables_suffix(suffix)
    create_store_tables_suffix(suffix)
    create_issues_metadata_table_suffix(suffix)
    create_issue_items_table_suffix(suffix)
    create_contracts_metadata_table_suffix(suffix)
    create_contract_items_table_suffix(suffix)
    create_contracts_daily_check_table_suffix(suffix)
    create_cdr_table_suffix(suffix)

def create_bom_metadata_table_suffix(suffix):
    t = f'bom_metadata{suffix}'
    if table_exists(t):
        return
    execute_query(f"""
    CREATE TABLE {t} (
        id INT AUTO_INCREMENT PRIMARY KEY,
        bom_name VARCHAR(255) NOT NULL,
        bom_type ENUM('PCB', 'Assembly') NOT NULL,
        tank VARCHAR(255) NULL,
        assembly_name VARCHAR(255) NULL,
        sub_assembly_name VARCHAR(255) NULL,
        currency VARCHAR(50) DEFAULT 'RMB',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        INDEX idx_bom_name (bom_name)
    )
    """, commit=True)
    logger.info(f"Created {t} table")

def create_bom_items_table_suffix(suffix):
    meta = f'bom_metadata{suffix}'
    t = f'bom_items{suffix}'
    if table_exists(t):
        return
    execute_query(f"""
    CREATE TABLE {t} (
        id INT AUTO_INCREMENT PRIMARY KEY,
        bom_id INT NOT NULL,
        designator VARCHAR(255),
        part_type VARCHAR(255),
        part_value VARCHAR(255),
        part_description TEXT,
        footprint VARCHAR(255),
        qty INT NOT NULL,
        unit_price DECIMAL(15, 2) DEFAULT 0.00,
        total_price DECIMAL(15, 2) DEFAULT 0.00,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_bom_id (bom_id),
        FOREIGN KEY (bom_id) REFERENCES {meta}(id) ON DELETE CASCADE
    )
    """, commit=True)
    logger.info(f"Created {t} table")

def create_demand_notes_table_suffix(suffix):
    t = f'demand_notes{suffix}'
    if table_exists(t):
        return
    execute_query(f"""
    CREATE TABLE {t} (
        id INT AUTO_INCREMENT PRIMARY KEY,
        demand_no INT NOT NULL,
        demand_date DATE NOT NULL,
        department VARCHAR(255) NOT NULL,
        required_date DATE NOT NULL,
        demanded_by VARCHAR(255) NOT NULL,
        demand_type ENUM('import', 'local') DEFAULT 'import',
        approved BOOLEAN DEFAULT FALSE,
        approval_status VARCHAR(50),
        approved_by_director VARCHAR(255),
        director_approved_at TIMESTAMP NULL,
        approved_by_gm VARCHAR(255),
        gm_approved_at TIMESTAMP NULL,
        decline_remarks TEXT NULL,
        declined_by VARCHAR(255) NULL,
        declined_at TIMESTAMP NULL,
        supply_chain_archived BOOLEAN DEFAULT FALSE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        INDEX idx_demand_no (demand_no),
        INDEX idx_approved (approved)
    )
    """, commit=True)
    logger.info(f"Created {t} table")

def create_demand_items_table_suffix(suffix):
    notes = f'demand_notes{suffix}'
    t = f'demand_items{suffix}'
    if table_exists(t):
        return
    execute_query(f"""
    CREATE TABLE {t} (
        id INT AUTO_INCREMENT PRIMARY KEY,
        demand_id INT NOT NULL,
        sr_no INT,
        part_type VARCHAR(255),
        part_value VARCHAR(255),
        part_description TEXT,
        footprint VARCHAR(255),
        qty INT NOT NULL,
        unit_price DECIMAL(15, 2) DEFAULT 0.00,
        total_price DECIMAL(15, 2) DEFAULT 0.00,
        persons_demand VARCHAR(255),
        project VARCHAR(255),
        remarks TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_demand_id (demand_id),
        FOREIGN KEY (demand_id) REFERENCES {notes}(id) ON DELETE CASCADE
    )
    """, commit=True)
    logger.info(f"Created {t} table")

def create_po_metadata_table_suffix(suffix):
    t = f'po_metadata{suffix}'
    if table_exists(t):
        return
    execute_query(f"""
    CREATE TABLE {t} (
        id INT AUTO_INCREMENT PRIMARY KEY,
        po_number VARCHAR(50) NOT NULL,
        supplier_name VARCHAR(255) NOT NULL,
        supplier_company VARCHAR(255) NOT NULL,
        supplier_address TEXT NOT NULL,
        supplier_telephone VARCHAR(50) NOT NULL,
        supplier_postal_code VARCHAR(20) NOT NULL,
        currency VARCHAR(20) DEFAULT 'RMB',
        po_type ENUM('import', 'local') DEFAULT 'import',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_po_number (po_number)
    )
    """, commit=True)
    logger.info(f"Created {t} table")

def create_po_items_table_suffix(suffix):
    meta = f'po_metadata{suffix}'
    t = f'po_items{suffix}'
    if table_exists(t):
        return
    execute_query(f"""
    CREATE TABLE {t} (
        id INT AUTO_INCREMENT PRIMARY KEY,
        po_id INT NOT NULL,
        part_type VARCHAR(255),
        part_value VARCHAR(255),
        part_description TEXT,
        footprint VARCHAR(255),
        qty INT NOT NULL,
        unit_price DECIMAL(10, 2),
        total_price DECIMAL(10, 2),
        project VARCHAR(255),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_po_id (po_id),
        FOREIGN KEY (po_id) REFERENCES {meta}(id) ON DELETE CASCADE
    )
    """, commit=True)
    logger.info(f"Created {t} table")

def create_qc_tables_suffix(suffix):
    for name, create in [
        (f'qc_components{suffix}', f"""
            CREATE TABLE qc_components{suffix} (
                id INT AUTO_INCREMENT PRIMARY KEY,
                part_type VARCHAR(255),
                part_value VARCHAR(255),
                part_description TEXT,
                footprint VARCHAR(255),
                po_no VARCHAR(50),
                po_type ENUM('import', 'local') DEFAULT 'import',
                qty INT NOT NULL,
                good_qty INT DEFAULT 0,
                status VARCHAR(50) DEFAULT 'Pending',
                project_number VARCHAR(100),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_po_no (po_no)
            )
        """),
        (f'qc_products{suffix}', f"""
            CREATE TABLE qc_products{suffix} (
                id INT AUTO_INCREMENT PRIMARY KEY,
                pcb_assembly_name VARCHAR(255) NOT NULL,
                part_type VARCHAR(255),
                part_value VARCHAR(255),
                part_description TEXT,
                footprint VARCHAR(255),
                qty INT NOT NULL,
                is_pcb BOOLEAN NOT NULL,
                project_number VARCHAR(100),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """),
        (f'qc_approved{suffix}', f"""
            CREATE TABLE qc_approved{suffix} (
                id INT AUTO_INCREMENT PRIMARY KEY,
                item_type ENUM('component', 'product') NOT NULL,
                part_type VARCHAR(255),
                part_value VARCHAR(255),
                part_description TEXT,
                footprint VARCHAR(255),
                po_no VARCHAR(50),
                pcb_assembly_name VARCHAR(255),
                qty INT NOT NULL,
                is_pcb BOOLEAN,
                project_number VARCHAR(100),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
    ]:
        if table_exists(name):
            continue
        execute_query(create, commit=True)
        logger.info(f"Created {name} table")

def create_store_tables_suffix(suffix):
    categories = [
        'resistors', 'capacitors', 'diodes_transistors', 'ics', 'connectors',
        'misc_components', 'pcbs', 'assemblies', 'misc_products'
    ]
    for category in categories:
        t = f'store_{category}{suffix}'
        if table_exists(t):
            continue
        execute_query(f"""
        CREATE TABLE {t} (
            id INT AUTO_INCREMENT PRIMARY KEY,
            part_type VARCHAR(255),
            part_value VARCHAR(255),
            part_description TEXT,
            footprint VARCHAR(255),
            qty INT NOT NULL DEFAULT 0,
            po_no TEXT,
            section VARCHAR(255),
            project_number VARCHAR(100),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        )
        """, commit=True)
        logger.info(f"Created {t} table")

def create_issues_metadata_table_suffix(suffix):
    t = f'issues_metadata{suffix}'
    if table_exists(t):
        return
    execute_query(f"""
    CREATE TABLE {t} (
        id INT AUTO_INCREMENT PRIMARY KEY,
        issue_number VARCHAR(50) NOT NULL,
        pcb_assembly_name VARCHAR(255) NOT NULL,
        date_issued DATE NOT NULL,
        issued_to VARCHAR(255) NOT NULL,
        contract_project VARCHAR(255) NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_issue_number (issue_number)
    )
    """, commit=True)
    logger.info(f"Created {t} table")

def create_issue_items_table_suffix(suffix):
    meta = f'issues_metadata{suffix}'
    t = f'issue_items{suffix}'
    if table_exists(t):
        return
    execute_query(f"""
    CREATE TABLE {t} (
        id INT AUTO_INCREMENT PRIMARY KEY,
        issue_id INT NOT NULL,
        part_type VARCHAR(255),
        part_value VARCHAR(255),
        part_description TEXT,
        footprint VARCHAR(255),
        qty INT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_issue_id (issue_id),
        FOREIGN KEY (issue_id) REFERENCES {meta}(id) ON DELETE CASCADE
    )
    """, commit=True)
    logger.info(f"Created {t} table")

def create_contracts_metadata_table_suffix(suffix):
    t = f'contracts_metadata{suffix}'
    if table_exists(t):
        return
    execute_query(f"""
    CREATE TABLE {t} (
        contract_id INT AUTO_INCREMENT PRIMARY KEY,
        contract_no VARCHAR(100) NOT NULL,
        contract_date DATE NOT NULL,
        contract_type ENUM('manufacturing', 'supply') NOT NULL,
        total_value DECIMAL(15, 2) NOT NULL,
        delivery_deadline DATE NOT NULL,
        bg_number VARCHAR(500),
        bg_amount DECIMAL(15, 2),
        bg_expiry_date VARCHAR(500),
        bg_issue_date VARCHAR(500),
        bank_name VARCHAR(255),
        expected_bg_release_date DATE,
        remarks TEXT,
        beneficiary VARCHAR(255),
        bg_type TEXT,
        department TEXT,
        contract_status ENUM('active', 'completed', 'warranty period') DEFAULT 'active',
        amount_given DECIMAL(15, 2) DEFAULT 0,
        amount_balance DECIMAL(15, 2) NOT NULL,
        final_crv_no VARCHAR(100),
        final_crv_date VARCHAR(50),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        INDEX idx_contract_no (contract_no),
        INDEX idx_contract_status (contract_status)
    )
    """, commit=True)
    logger.info(f"Created {t} table")

def create_contract_items_table_suffix(suffix):
    meta = f'contracts_metadata{suffix}'
    t = f'contract_items{suffix}'
    if table_exists(t):
        return
    execute_query(f"""
    CREATE TABLE {t} (
        item_id INT AUTO_INCREMENT PRIMARY KEY,
        contract_id INT NOT NULL,
        item_name VARCHAR(255),
        part_number VARCHAR(255),
        qty INT NOT NULL,
        unit_price DECIMAL(15, 2) NOT NULL,
        total_price DECIMAL(15, 2) NOT NULL,
        delivered_qty INT DEFAULT 0,
        deliver_balance INT NOT NULL,
        inspection_note_no VARCHAR(100),
        inspection_note_date DATE,
        delivery_no VARCHAR(100),
        delivery_date DATE,
        crv_no VARCHAR(100),
        crv_date DATE,
        invoice_no VARCHAR(100),
        submission_date DATE,
        ld_charges DECIMAL(15, 2),
        income_tax DECIMAL(15, 2),
        other_charges DECIMAL(15, 2),
        net_amount DECIMAL(15, 2),
        cheque_no VARCHAR(100),
        cheque_date DATE,
        bank_deposit_date DATE,
        warranty_expiry_date DATE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        INDEX idx_contract_id (contract_id),
        FOREIGN KEY (contract_id) REFERENCES {meta}(contract_id) ON DELETE CASCADE
    )
    """, commit=True)
    logger.info(f"Created {t} table")

def create_contracts_daily_check_table_suffix(suffix):
    t = f'contracts_daily_check{suffix}'
    if table_exists(t):
        return
    execute_query(f"""
    CREATE TABLE {t} (
        id INT AUTO_INCREMENT PRIMARY KEY,
        last_checked_date DATE NOT NULL,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
    )
    """, commit=True)
    logger.info(f"Created {t} table")

def create_users_table():
    """Create users table"""
    if table_exists('users'):
        logger.info("Users table already exists")
        return
    
    query = """
    CREATE TABLE users (
        id INT AUTO_INCREMENT PRIMARY KEY,
        email VARCHAR(255) UNIQUE NOT NULL,
        password_hash VARCHAR(255) NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_email (email)
    )
    """
    execute_query(query, commit=True)
    logger.info("Created users table")

def create_roles_table():
    """Create roles table for user role assignments"""
    if table_exists('user_roles'):
        logger.info("User roles table already exists")
        return
    
    query = """
    CREATE TABLE user_roles (
        id INT AUTO_INCREMENT PRIMARY KEY,
        email VARCHAR(255) NOT NULL,
        role VARCHAR(100) NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY unique_user_role (email, role),
        INDEX idx_email (email),
        INDEX idx_role (role)
    )
    """
    execute_query(query, commit=True)
    logger.info("Created user_roles table")

def create_bom_metadata_table():
    """Create BOM metadata table to track all BOMs"""
    if table_exists('bom_metadata'):
        logger.info("BOM metadata table already exists")
        return
    
    query = """
    CREATE TABLE bom_metadata (
        id INT AUTO_INCREMENT PRIMARY KEY,
        bom_name VARCHAR(255) UNIQUE NOT NULL,
        bom_type ENUM('PCB', 'Assembly') NOT NULL,
        tank VARCHAR(255) NULL,
        assembly_name VARCHAR(255) NULL,
        sub_assembly_name VARCHAR(255) NULL,
        currency VARCHAR(50) DEFAULT 'RMB',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        INDEX idx_bom_name (bom_name)
    )
    """
    execute_query(query, commit=True)
    logger.info("Created bom_metadata table")

def create_demand_notes_table():
    """Create demand notes metadata table"""
    if table_exists('demand_notes'):
        logger.info("Demand notes table already exists")
        return
    
    query = """
    CREATE TABLE demand_notes (
        id INT AUTO_INCREMENT PRIMARY KEY,
        demand_no INT UNIQUE NOT NULL,
        demand_date DATE NOT NULL,
        department VARCHAR(255) NOT NULL,
        required_date DATE NOT NULL,
        demanded_by VARCHAR(255) NOT NULL,
        demand_type ENUM('import', 'local') DEFAULT 'import',
        approved BOOLEAN DEFAULT FALSE,
        approval_status VARCHAR(50),
        approved_by_director VARCHAR(255),
        director_approved_at TIMESTAMP NULL,
        approved_by_gm VARCHAR(255),
        gm_approved_at TIMESTAMP NULL,
        decline_remarks TEXT NULL,
        declined_by VARCHAR(255) NULL,
        declined_at TIMESTAMP NULL,
        supply_chain_archived BOOLEAN DEFAULT FALSE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        INDEX idx_demand_no (demand_no),
        INDEX idx_approved (approved)
    )
    """
    execute_query(query, commit=True)
    logger.info("Created demand_notes table")

def create_notifications_table():
    """Create notifications table"""
    if table_exists('notifications'):
        logger.info("Notifications table already exists")
        return
    
    query = """
    CREATE TABLE notifications (
        id INT AUTO_INCREMENT PRIMARY KEY,
        recipient_role VARCHAR(100) NOT NULL,
        message TEXT NOT NULL,
        related_id INT,
        notification_type VARCHAR(50) NOT NULL,
        is_read BOOLEAN DEFAULT FALSE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_role (recipient_role),
        INDEX idx_read (is_read)
    )
    """
    execute_query(query, commit=True)
    logger.info("Created notifications table")

def create_po_metadata_table():
    """Create purchase order metadata table"""
    if table_exists('po_metadata'):
        logger.info("PO metadata table already exists")
        return
    
    query = """
    CREATE TABLE po_metadata (
        id INT AUTO_INCREMENT PRIMARY KEY,
        po_number VARCHAR(50) UNIQUE NOT NULL,
        supplier_name VARCHAR(255) NOT NULL,
        supplier_company VARCHAR(255) NOT NULL,
        supplier_address TEXT NOT NULL,
        supplier_telephone VARCHAR(50) NOT NULL,
        supplier_postal_code VARCHAR(20) NOT NULL,
        currency VARCHAR(20) DEFAULT 'RMB',
        po_type ENUM('import', 'local') DEFAULT 'import',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_po_number (po_number)
    )
    """
    execute_query(query, commit=True)
    logger.info("Created po_metadata table")

def create_qc_tables():
    """Create quality control tables"""
    
    # QC Components
    if not table_exists('qc_components'):
        query = """
        CREATE TABLE qc_components (
            id INT AUTO_INCREMENT PRIMARY KEY,
            part_type VARCHAR(255),
            part_value VARCHAR(255),
            part_description TEXT,
            footprint VARCHAR(255),
            po_no VARCHAR(50),
            po_type ENUM('import', 'local') DEFAULT 'import',
            qty INT NOT NULL,
            good_qty INT DEFAULT 0,
            status VARCHAR(50) DEFAULT 'Pending',
            project_number VARCHAR(100),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_po_no (po_no)
        )
        """
        execute_query(query, commit=True)
        logger.info("Created qc_components table")
    
    # QC Products
    if not table_exists('qc_products'):
        query = """
        CREATE TABLE qc_products (
            id INT AUTO_INCREMENT PRIMARY KEY,
            pcb_assembly_name VARCHAR(255) NOT NULL,
            part_type VARCHAR(255),
            part_value VARCHAR(255),
            part_description TEXT,
            footprint VARCHAR(255),
            qty INT NOT NULL,
            is_pcb BOOLEAN NOT NULL,
            project_number VARCHAR(100),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
        execute_query(query, commit=True)
        logger.info("Created qc_products table")
    
    # QC Approved (temporary storage before entering store)
    if not table_exists('qc_approved'):
        query = """
        CREATE TABLE qc_approved (
            id INT AUTO_INCREMENT PRIMARY KEY,
            item_type ENUM('component', 'product') NOT NULL,
            part_type VARCHAR(255),
            part_value VARCHAR(255),
            part_description TEXT,
            footprint VARCHAR(255),
            po_no VARCHAR(50),
            pcb_assembly_name VARCHAR(255),
            qty INT NOT NULL,
            is_pcb BOOLEAN,
            project_number VARCHAR(100),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
        execute_query(query, commit=True)
        logger.info("Created qc_approved table")

def create_store_tables():
    """Create store inventory tables for different categories"""
    
    categories = [
        'resistors',
        'capacitors',
        'diodes_transistors',
        'ics',
        'connectors',
        'misc_components',
        'pcbs',
        'assemblies',
        'misc_products'
    ]
    
    for category in categories:
        if table_exists(f'store_{category}'):
            continue
        
        query = f"""
        CREATE TABLE store_{category} (
            id INT AUTO_INCREMENT PRIMARY KEY,
            part_type VARCHAR(255),
            part_value VARCHAR(255),
            part_description TEXT,
            footprint VARCHAR(255),
            qty INT NOT NULL DEFAULT 0,
            po_no TEXT,
            section VARCHAR(255),
            project_number VARCHAR(100),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        )
        """
        execute_query(query, commit=True)
        logger.info(f"Created store_{category} table")

def create_issues_metadata_table():
    """Create issues metadata table"""
    if table_exists('issues_metadata'):
        logger.info("Issues metadata table already exists")
        return
    
    query = """
    CREATE TABLE issues_metadata (
        id INT AUTO_INCREMENT PRIMARY KEY,
        issue_number VARCHAR(50) UNIQUE NOT NULL,
        pcb_assembly_name VARCHAR(255) NOT NULL,
        date_issued DATE NOT NULL,
        issued_to VARCHAR(255) NOT NULL,
        contract_project VARCHAR(255) NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_issue_number (issue_number)
    )
    """
    execute_query(query, commit=True)
    logger.info("Created issues_metadata table")

def create_issue_items_table():
    """Single table for all issue line items; issue_id FK -> issues_metadata.id"""
    if table_exists('issue_items'):
        logger.info("issue_items table already exists")
        return
    query = """
    CREATE TABLE issue_items (
        id INT AUTO_INCREMENT PRIMARY KEY,
        issue_id INT NOT NULL,
        part_type VARCHAR(255),
        part_value VARCHAR(255),
        part_description TEXT,
        footprint VARCHAR(255),
        qty INT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_issue_id (issue_id),
        FOREIGN KEY (issue_id) REFERENCES issues_metadata(id) ON DELETE CASCADE
    )
    """
    execute_query(query, commit=True)
    logger.info("Created issue_items table")

def create_demand_items_table():
    """Single table for all demand note line items; demand_id FK -> demand_notes.id"""
    if table_exists('demand_items'):
        logger.info("demand_items table already exists")
        return
    query = """
    CREATE TABLE demand_items (
        id INT AUTO_INCREMENT PRIMARY KEY,
        demand_id INT NOT NULL,
        sr_no INT,
        part_type VARCHAR(255),
        part_value VARCHAR(255),
        part_description TEXT,
        footprint VARCHAR(255),
        qty INT NOT NULL,
        unit_price DECIMAL(15, 2) DEFAULT 0.00,
        total_price DECIMAL(15, 2) DEFAULT 0.00,
        persons_demand VARCHAR(255),
        project VARCHAR(255),
        remarks TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_demand_id (demand_id),
        FOREIGN KEY (demand_id) REFERENCES demand_notes(id) ON DELETE CASCADE
    )
    """
    execute_query(query, commit=True)
    logger.info("Created demand_items table")

def create_po_items_table():
    """Single table for all PO line items; po_id FK -> po_metadata.id"""
    if table_exists('po_items'):
        logger.info("po_items table already exists")
        return
    query = """
    CREATE TABLE po_items (
        id INT AUTO_INCREMENT PRIMARY KEY,
        po_id INT NOT NULL,
        part_type VARCHAR(255),
        part_value VARCHAR(255),
        part_description TEXT,
        footprint VARCHAR(255),
        qty INT NOT NULL,
        unit_price DECIMAL(10, 2),
        total_price DECIMAL(10, 2),
        project VARCHAR(255),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_po_id (po_id),
        FOREIGN KEY (po_id) REFERENCES po_metadata(id) ON DELETE CASCADE
    )
    """
    execute_query(query, commit=True)
    logger.info("Created po_items table")

def create_bom_items_table():
    """Single table for all BOM components; bom_id FK -> bom_metadata.id"""
    if table_exists('bom_items'):
        logger.info("bom_items table already exists")
        return
    query = """
    CREATE TABLE bom_items (
        id INT AUTO_INCREMENT PRIMARY KEY,
        bom_id INT NOT NULL,
        designator VARCHAR(255),
        part_type VARCHAR(255),
        part_value VARCHAR(255),
        part_description TEXT,
        footprint VARCHAR(255),
        qty INT NOT NULL,
        unit_price DECIMAL(15, 2) DEFAULT 0.00,
        total_price DECIMAL(15, 2) DEFAULT 0.00,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_bom_id (bom_id),
        FOREIGN KEY (bom_id) REFERENCES bom_metadata(id) ON DELETE CASCADE
    )
    """
    execute_query(query, commit=True)
    logger.info("Created bom_items table")

def create_contracts_metadata_table():
    """Contracts metadata: one row per contract."""
    if table_exists('contracts_metadata'):
        logger.info("contracts_metadata table already exists")
        return
    query = """
    CREATE TABLE contracts_metadata (
        contract_id INT AUTO_INCREMENT PRIMARY KEY,
        contract_no VARCHAR(100) NOT NULL,
        contract_date DATE NOT NULL,
        contract_type ENUM('manufacturing', 'supply') NOT NULL,
        total_value DECIMAL(15, 2) NOT NULL,
        delivery_deadline DATE NOT NULL,
        bg_number VARCHAR(500),
        bg_amount DECIMAL(15, 2),
        bg_expiry_date VARCHAR(500),
        bg_issue_date VARCHAR(500),
        bank_name VARCHAR(255),
        expected_bg_release_date DATE,
        remarks TEXT,
        beneficiary VARCHAR(255),
        bg_type TEXT,
        department TEXT,
        contract_status ENUM('active', 'completed', 'warranty period') DEFAULT 'active',
        amount_given DECIMAL(15, 2) DEFAULT 0,
        amount_balance DECIMAL(15, 2) NOT NULL,
        final_crv_no VARCHAR(100),
        final_crv_date VARCHAR(50),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        INDEX idx_contract_no (contract_no),
        INDEX idx_contract_status (contract_status)
    )
    """
    execute_query(query, commit=True)
    logger.info("Created contracts_metadata table")

def create_contract_items_table():
    """Contract line items; contract_id FK -> contracts_metadata.contract_id."""
    if table_exists('contract_items'):
        logger.info("contract_items table already exists")
        return
    query = """
    CREATE TABLE contract_items (
        item_id INT AUTO_INCREMENT PRIMARY KEY,
        contract_id INT NOT NULL,
        item_name VARCHAR(255),
        part_number VARCHAR(255),
        qty INT NOT NULL,
        unit_price DECIMAL(15, 2) NOT NULL,
        total_price DECIMAL(15, 2) NOT NULL,
        delivered_qty INT DEFAULT 0,
        deliver_balance INT NOT NULL,
        inspection_note_no VARCHAR(100),
        inspection_note_date DATE,
        delivery_no VARCHAR(100),
        delivery_date DATE,
        crv_no VARCHAR(100),
        crv_date DATE,
        invoice_no VARCHAR(100),
        submission_date DATE,
        ld_charges DECIMAL(15, 2),
        income_tax DECIMAL(15, 2),
        other_charges DECIMAL(15, 2),
        net_amount DECIMAL(15, 2),
        cheque_no VARCHAR(100),
        cheque_date DATE,
        bank_deposit_date DATE,
        warranty_expiry_date DATE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        INDEX idx_contract_id (contract_id),
        FOREIGN KEY (contract_id) REFERENCES contracts_metadata(contract_id) ON DELETE CASCADE
    )
    """
    execute_query(query, commit=True)
    logger.info("Created contract_items table")

def create_contracts_daily_check_table():
    """Store last date when daily contract checks (status + notifications) were run."""
    if table_exists('contracts_daily_check'):
        logger.info("contracts_daily_check table already exists")
        return
    query = """
    CREATE TABLE contracts_daily_check (
        id INT AUTO_INCREMENT PRIMARY KEY,
        last_checked_date DATE NOT NULL,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
    )
    """
    execute_query(query, commit=True)
    logger.info("Created contracts_daily_check table")

def initialize_default_admin():
    """Initialize default admin accounts with executive roles across lines"""
    import os
    import bcrypt
    
    admin_accounts = [
        # Primary administrator account
        (
            'khalid.pk38@gmail.com',
            'deltaplus123'
        ),
        # Demo / environment-configured administrator account
        (
            os.getenv('DEFAULT_ADMIN_EMAIL', 'admin@deltaplus.com').strip().lower(),
            os.getenv('DEFAULT_ADMIN_PASSWORD', 'admin123')
        )
    ]

    roles_to_assign = [
        'director',
        'general manager',
        'general manager_biomedical',
        'general manager_battery',
        'gm logistics'
    ]

    for admin_email, default_password in admin_accounts:
        if not admin_email:
            continue

        user_check = execute_query("SELECT COUNT(*) as count FROM users WHERE email = %s", (admin_email,), fetch_one=True)
        if not user_check or user_check['count'] == 0:
            password_hash = bcrypt.hashpw(default_password.encode('utf-8'), bcrypt.gensalt())
            user_query = "INSERT INTO users (email, password_hash) VALUES (%s, %s)"
            execute_query(user_query, (admin_email, password_hash.decode('utf-8')), commit=True)
            logger.info(f"Created administrator account: {admin_email}")
        
        # Assign key executive roles so admin has access to all lines and features
        for role in roles_to_assign:
            role_check = execute_query(
                "SELECT COUNT(*) as count FROM user_roles WHERE email = %s AND role = %s",
                (admin_email, role),
                fetch_one=True
            )
            if not role_check or role_check['count'] == 0:
                execute_query(
                    "INSERT INTO user_roles (email, role) VALUES (%s, %s)",
                    (admin_email, role),
                    commit=True
                )
    
    logger.info("Administrator accounts and executive roles verified successfully.")

def create_cdr_table():
    """CDR (Call Deposit Receipt) table for Tanks production line."""
    if table_exists('cdr_info'):
        logger.info("cdr_info table already exists")
        return
    query = """
    CREATE TABLE cdr_info (
        cdr_id INT AUTO_INCREMENT PRIMARY KEY,
        cdr_date DATE,
        cdr_no VARCHAR(100),
        cdr_ref_no VARCHAR(100),
        bank VARCHAR(255),
        cdr_amount DECIMAL(15, 2),
        organization VARCHAR(255),
        tender_no VARCHAR(100),
        tender_submission_date DATE,
        quoted_item TEXT,
        cdr_receiving_date DATE,
        remarks TEXT,
        pv_no VARCHAR(100),
        pv_date DATE,
        status VARCHAR(100),
        release_date DATE,
        rv_no VARCHAR(100),
        rv_date DATE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
    )
    """
    execute_query(query, commit=True)
    logger.info("Created cdr_info table")

def create_cdr_table_suffix(suffix):
    """CDR table for Biomedical/Battery production lines."""
    t = f'cdr_info{suffix}'
    if table_exists(t):
        logger.info(f"{t} table already exists")
        return
    query = f"""
    CREATE TABLE {t} (
        cdr_id INT AUTO_INCREMENT PRIMARY KEY,
        cdr_date DATE,
        cdr_no VARCHAR(100),
        cdr_ref_no VARCHAR(100),
        bank VARCHAR(255),
        cdr_amount DECIMAL(15, 2),
        organization VARCHAR(255),
        tender_no VARCHAR(100),
        tender_submission_date DATE,
        quoted_item TEXT,
        cdr_receiving_date DATE,
        remarks TEXT,
        pv_no VARCHAR(100),
        pv_date DATE,
        status VARCHAR(100),
        release_date DATE,
        rv_no VARCHAR(100),
        rv_date DATE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
    )
    """
    execute_query(query, commit=True)
    logger.info(f"Created {t} table")

if __name__ == '__main__':
    from database import init_connection_pool
    print("Connecting to database...")
    if init_connection_pool():
        print("Creating all tables and initializing default schema...")
        create_all_tables()
        print("All tables and default admin initialized successfully!")
    else:
        print("Error: Could not connect to database. Please check your DB credentials in .env or environment variables.")
