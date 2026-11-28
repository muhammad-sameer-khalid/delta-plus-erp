import os
import time
import logging
import mysql.connector
from mysql.connector import Error, pooling
from config import Config

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Connection pool for better performance
connection_pool = None
_schema_initialized = False
_existing_tables_cache = None

def get_existing_tables(force_refresh=False):
    """
    Fetch all table names in the current database in a single round-trip.
    Caches the set in-memory to prevent hundreds of redundant queries to information_schema.
    """
    global _existing_tables_cache
    if _existing_tables_cache is not None and not force_refresh:
        return _existing_tables_cache

    db_name = Config.DB_CONFIG.get('database')
    if not db_name:
        _existing_tables_cache = set()
        return _existing_tables_cache

    try:
        query = "SELECT table_name FROM information_schema.tables WHERE table_schema = %s"
        rows = execute_query(query, (db_name,), fetch=True)
        if rows:
            _existing_tables_cache = {r['table_name'].lower() for r in rows if 'table_name' in r}
        else:
            _existing_tables_cache = set()
    except Exception as e:
        logger.warning(f"Could not retrieve existing tables: {e}")
        _existing_tables_cache = set()

    return _existing_tables_cache

def ensure_database_exists():
    """
    Ensure the target MySQL/TiDB database exists.
    Connects to server and executes CREATE DATABASE IF NOT EXISTS.
    Works seamlessly with local MySQL and cloud databases (like TiDB Cloud).
    """
    target_db = Config.DB_CONFIG.get('database')
    if not target_db:
        return True

    host = Config.DB_CONFIG.get('host', 'localhost')
    is_cloud = os.getenv('RENDER') == 'true' or os.getenv('VERCEL') == '1'
    if is_cloud and host in ('localhost', '127.0.0.1'):
        logger.warning("Running on cloud with DB_HOST=localhost. Remote database environment variables need to be set in Render settings.")
        return False
    
    server_config = {k: v for k, v in Config.DB_CONFIG.items() if k != 'database'}
    server_config['raise_on_warnings'] = False
    server_config['connect_timeout'] = 3
    try:
        conn = mysql.connector.connect(**server_config)
        cursor = conn.cursor()
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{target_db}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
        cursor.close()
        conn.close()
        logger.info(f"Database `{target_db}` verified/created successfully.")
        return True
    except Exception as e:
        logger.info(f"Direct connection without database parameter: {e}. Trying fallback 'test' database...")
        try:
            # Some cloud providers (e.g., TiDB Cloud default) supply a default 'test' database to connect to first
            fallback_config = dict(server_config)
            fallback_config['database'] = 'test'
            fallback_config['raise_on_warnings'] = False
            fallback_config['connect_timeout'] = 3
            conn = mysql.connector.connect(**fallback_config)
            cursor = conn.cursor()
            cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{target_db}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
            cursor.close()
            conn.close()
            logger.info(f"Database `{target_db}` verified/created via fallback 'test' database.")
            return True
        except Exception as e2:
            logger.warning(f"Fallback database verification attempt: {e2}")
            return False

def init_connection_pool():
    """Initialize MySQL connection pool with fast-path connection and auto-database creation on error 1049"""
    global connection_pool
    if connection_pool is not None:
        return True

    host = Config.DB_CONFIG.get('host', 'localhost')
    is_cloud = os.getenv('RENDER') == 'true' or os.getenv('VERCEL') == '1'
    if is_cloud and host in ('localhost', '127.0.0.1'):
        logger.warning("Cloud deployment detected without DB_HOST set in environment variables.")
        return False

    pool_size = int(os.getenv('DB_POOL_SIZE', 5))

    # Fast path: try connecting directly to target database
    try:
        logger.info("Initializing MySQL connection pool...")
        connection_pool = pooling.MySQLConnectionPool(
            pool_name="delta_plus_pool",
            pool_size=pool_size,
            pool_reset_session=True,
            **Config.DB_CONFIG
        )
        logger.info("MySQL connection pool created successfully")
        return True
    except Error as e:
        # Check if database does not exist (MySQL error 1049 / Unknown database)
        err_no = getattr(e, 'errno', None)
        if err_no == 1049 or 'Unknown database' in str(e):
            logger.info(f"Database does not exist yet (error {err_no}). Creating database...")
            if ensure_database_exists():
                try:
                    connection_pool = pooling.MySQLConnectionPool(
                        pool_name="delta_plus_pool",
                        pool_size=pool_size,
                        pool_reset_session=True,
                        **Config.DB_CONFIG
                    )
                    logger.info("MySQL connection pool created successfully after database creation")
                    return True
                except Error as pool_err:
                    logger.error(f"Failed to create pool after creating database: {pool_err}")
                    return False
        logger.error(f"Error creating connection pool: {e}")
        return False

def get_db_connection():
    """Get a connection from the pool with auto-reconnect resilience"""
    global connection_pool
    try:
        if connection_pool is None:
            if not init_connection_pool():
                logger.error("Failed to initialize connection pool.")
                return None
        
        # Double check pool is not None after attempt
        if connection_pool:
            try:
                conn = connection_pool.get_connection()
            except Error as pool_err:
                logger.warning(f"Connection pool error: {pool_err}. Re-initializing pool...")
                init_connection_pool()
                conn = connection_pool.get_connection() if connection_pool else None

            if conn:
                try:
                    if not conn.is_connected():
                        conn.ping(reconnect=True, attempts=1, delay=0)
                except Exception as ping_err:
                    logger.warning(f"Connection ping/reconnect issue: {ping_err}")
                return conn
        return None
        
    except Error as e:
        logger.error(f"Error getting connection from pool: {e}")
        return None

def execute_query(query, params=None, fetch=False, fetch_one=False, commit=False, connection=None):
    """
    Execute a SQL query with parameterized inputs to prevent SQL injection
    
    Args:
        query: SQL query string with %s placeholders
        params: Tuple of parameters to substitute
        fetch: Whether to fetch results
        fetch_one: Whether to fetch only one result
        commit: Whether to commit the transaction
        connection: Optional existing connection to reuse (avoids pool overhead)
    
    Returns:
        Query results if fetch=True, affected row count if commit=True, None otherwise
    """
    should_close = False
    if connection is None:
        connection = get_db_connection()
        should_close = True

    if connection is None:
        return None
    
    cursor = None
    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(query, params or ())
        
        if fetch_one:
            result = cursor.fetchone()
            try:
                cursor.fetchall()
            except Exception:
                pass
        elif fetch:
            result = cursor.fetchall()
        else:
            result = cursor.rowcount
        
        if commit:
            connection.commit()
        
        return result
    
    except Error as e:
        logger.error(f"Database error: {e}")
        if commit:
            connection.rollback()
        return None
    
    finally:
        if cursor:
            cursor.close()
        if should_close and connection:
            connection.close()

def execute_many(query, params_list, commit=True, connection=None):
    """
    Execute multiple queries with different parameters (batch insert/update)
    
    Args:
        query: SQL query string
        params_list: List of parameter tuples
        commit: Whether to commit the transaction
        connection: Optional existing connection to reuse
    
    Returns:
        Number of affected rows or None on error
    """
    should_close = False
    if connection is None:
        connection = get_db_connection()
        should_close = True

    if connection is None:
        return None
    
    cursor = None
    try:
        cursor = connection.cursor()
        cursor.executemany(query, params_list)
        
        if commit:
            connection.commit()
        
        return cursor.rowcount
    
    except Error as e:
        logger.error(f"Database error in batch operation: {e}")
        if commit:
            connection.rollback()
        return None
    
    finally:
        if cursor:
            cursor.close()
        if should_close and connection:
            connection.close()

def table_exists(table_name):
    """Check if a table exists in the database using the cached table set"""
    tables = get_existing_tables()
    return table_name.lower() in tables

def create_table(create_query, table_name=None):
    """Create a table with the given CREATE TABLE query"""
    res = execute_query(create_query, commit=True)
    if table_name and _existing_tables_cache is not None:
        _existing_tables_cache.add(table_name.lower())
    return res

def ensure_demand_notes_remarks_columns():
    """Ensure gm_remarks and director_remarks columns exist on all demand_notes tables (idempotent migration)"""
    tables = [
        'demand_notes',
        'demand_notes_battery',
        'demand_notes_biomedical_disposable',
        'demand_notes_biomedical_equipment',
        'demand_notes_biomedical'
    ]
    db_name = Config.DB_CONFIG.get('database')
    if not db_name:
        return
    for t in tables:
        try:
            if not table_exists(t):
                continue
            cols = execute_query(
                "SELECT COLUMN_NAME FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s",
                (db_name, t),
                fetch=True
            )
            col_names = {c['COLUMN_NAME'].lower() for c in cols} if cols else set()
            if 'gm_remarks' not in col_names:
                execute_query(f"ALTER TABLE {t} ADD COLUMN gm_remarks TEXT NULL", commit=True)
                logger.info(f"Added gm_remarks column to {t}")
            if 'director_remarks' not in col_names:
                execute_query(f"ALTER TABLE {t} ADD COLUMN director_remarks TEXT NULL", commit=True)
                logger.info(f"Added director_remarks column to {t}")
        except Exception as e:
            logger.warning(f"Could not verify/add remarks columns to {t}: {e}")

def ensure_contracts_category_column():
    """Ensure category column exists on contracts_metadata tables (idempotent migration)"""
    tables = [
        'contracts_metadata',
        'contracts_metadata_biomedical',
        'contracts_metadata_battery',
        'contracts_metadata_biomedical_disposable',
        'contracts_metadata_biomedical_equipment'
    ]
    db_name = Config.DB_CONFIG.get('database')
    if not db_name:
        return
    for t in tables:
        try:
            if not table_exists(t):
                continue
            cols = execute_query(
                "SELECT COLUMN_NAME FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s",
                (db_name, t),
                fetch=True
            )
            col_names = {c['COLUMN_NAME'].lower() for c in cols} if cols else set()
            if 'category' not in col_names:
                execute_query(f"ALTER TABLE {t} ADD COLUMN category VARCHAR(50) NULL DEFAULT 'Disposable'", commit=True)
                logger.info(f"Added category column to {t}")
        except Exception as e:
            logger.warning(f"Could not verify/add category column to {t}: {e}")

def migrate_biomedical_unified_tables():
    """Ensure unified biomedical tables exist and migrate data from legacy split tables."""
    from schema import create_line_tables
    try:
        create_line_tables('_biomedical')
    except Exception as e:
        logger.warning(f"Notice while ensuring _biomedical line tables: {e}")

    ensure_contracts_category_column()
    ensure_demand_notes_remarks_columns()

    db_name = Config.DB_CONFIG.get('database')
    if not db_name:
        return

    # 1. Contracts migration from split tables to unified contracts_metadata_biomedical
    for src_table, default_cat in [
        ('contracts_metadata_biomedical_disposable', 'Disposable'),
        ('contracts_metadata_biomedical_equipment', 'Equipment')
    ]:
        try:
            if table_exists(src_table) and table_exists('contracts_metadata_biomedical'):
                src_contracts = execute_query(f"SELECT * FROM {src_table}", fetch=True) or []
                for sc in src_contracts:
                    c_no = sc.get('contract_no')
                    if not c_no:
                        continue
                    cat_val = sc.get('category') or default_cat
                    exists = execute_query(
                        "SELECT contract_id FROM contracts_metadata_biomedical WHERE contract_no = %s",
                        (c_no,), fetch_one=True
                    )
                    if not exists:
                        execute_query(f"""
                            INSERT INTO contracts_metadata_biomedical
                            (contract_no, contract_date, contract_type, category, total_value, delivery_deadline,
                             bg_number, bg_amount, bg_expiry_date, bg_issue_date, bank_name, expected_bg_release_date,
                             remarks, beneficiary, bg_type, department, contract_status, amount_given, amount_balance,
                             final_crv_no, final_crv_date)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """, (
                            sc.get('contract_no'), sc.get('contract_date'), sc.get('contract_type'), cat_val,
                            sc.get('total_value', 0), sc.get('delivery_deadline'), sc.get('bg_number'),
                            sc.get('bg_amount'), sc.get('bg_expiry_date'), sc.get('bg_issue_date'),
                            sc.get('bank_name'), sc.get('expected_bg_release_date'), sc.get('remarks'),
                            sc.get('beneficiary'), sc.get('bg_type'), sc.get('department'),
                            sc.get('contract_status', 'active'), sc.get('amount_given', 0),
                            sc.get('amount_balance', sc.get('total_value', 0)),
                            sc.get('final_crv_no'), sc.get('final_crv_date')
                        ), commit=True)
                        new_c = execute_query(
                            "SELECT contract_id FROM contracts_metadata_biomedical WHERE contract_no = %s",
                            (c_no,), fetch_one=True
                        )
                        new_c_id = new_c.get('contract_id') if new_c else None
                        old_c_id = sc.get('contract_id')
                        src_items_table = src_table.replace('contracts_metadata', 'contract_items')
                        if old_c_id and new_c_id and table_exists(src_items_table) and table_exists('contract_items_biomedical'):
                            old_items = execute_query(f"SELECT * FROM {src_items_table} WHERE contract_id = %s", (old_c_id,), fetch=True) or []
                            for oi in old_items:
                                execute_query(f"""
                                    INSERT INTO contract_items_biomedical
                                    (contract_id, item_name, part_number, qty, unit_price, total_price, delivered_qty,
                                     deliver_balance, inspection_note_no, inspection_note_date, delivery_no, delivery_date,
                                     crv_no, crv_date, invoice_no, invoice_date, payment_received_amount, net_amount,
                                     payment_date, tax_deductions, security_deposit_deducted, other_deductions, remarks)
                                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                                """, (
                                    new_c_id, oi.get('item_name'), oi.get('part_number'), oi.get('qty', 0),
                                    oi.get('unit_price', 0), oi.get('total_price', 0), oi.get('delivered_qty', 0),
                                    oi.get('deliver_balance', 0), oi.get('inspection_note_no'), oi.get('inspection_note_date'),
                                    oi.get('delivery_no'), oi.get('delivery_date'), oi.get('crv_no'), oi.get('crv_date'),
                                    oi.get('invoice_no'), oi.get('invoice_date'), oi.get('payment_received_amount'),
                                    oi.get('net_amount'), oi.get('payment_date'), oi.get('tax_deductions'),
                                    oi.get('security_deposit_deducted'), oi.get('other_deductions'), oi.get('remarks')
                                ), commit=True)
                    else:
                        execute_query(
                            "UPDATE contracts_metadata_biomedical SET category = COALESCE(category, %s) WHERE contract_no = %s",
                            (cat_val, c_no), commit=True
                        )
        except Exception as e:
            logger.warning(f"Notice while migrating {src_table}: {e}")

    # 2. Demand notes migration from split tables to unified demand_notes_biomedical
    for src_dn_table in ['demand_notes_biomedical_disposable', 'demand_notes_biomedical_equipment']:
        try:
            if table_exists(src_dn_table) and table_exists('demand_notes_biomedical'):
                old_dns = execute_query(f"SELECT * FROM {src_dn_table}", fetch=True) or []
                for odn in old_dns:
                    dn_no = odn.get('demand_no')
                    if not dn_no:
                        continue
                    exists = execute_query("SELECT id FROM demand_notes_biomedical WHERE demand_no = %s", (dn_no,), fetch_one=True)
                    if not exists:
                        execute_query(f"""
                            INSERT INTO demand_notes_biomedical
                            (demand_no, demand_date, department, required_date, demanded_by, remarks,
                             approval_status, approved, approved_by_director, director_approved_at,
                             approved_by_gm, gm_approved_at, gm_remarks, director_remarks,
                             decline_remarks, declined_by, declined_at, demand_type)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """, (
                            odn.get('demand_no'), odn.get('demand_date'), odn.get('department'),
                            odn.get('required_date'), odn.get('demanded_by'), odn.get('remarks'),
                            odn.get('approval_status', 'draft'), odn.get('approved', False),
                            odn.get('approved_by_director'), odn.get('director_approved_at'),
                            odn.get('approved_by_gm'), odn.get('gm_approved_at'),
                            odn.get('gm_remarks'), odn.get('director_remarks'),
                            odn.get('decline_remarks'), odn.get('declined_by'), odn.get('declined_at'),
                            odn.get('demand_type', 'local')
                        ), commit=True)
                        new_dn = execute_query("SELECT id FROM demand_notes_biomedical WHERE demand_no = %s", (dn_no,), fetch_one=True)
                        new_dn_id = new_dn.get('id') if new_dn else None
                        old_dn_id = odn.get('id')
                        src_di_table = src_dn_table.replace('demand_notes', 'demand_items')
                        if old_dn_id and new_dn_id and table_exists(src_di_table) and table_exists('demand_items_biomedical'):
                            old_items = execute_query(f"SELECT * FROM {src_di_table} WHERE demand_id = %s", (old_dn_id,), fetch=True) or []
                            for oi in old_items:
                                execute_query(f"""
                                    INSERT INTO demand_items_biomedical
                                    (demand_id, sr_no, part_description, qty, persons_demand, project, unit_price, total_price, remarks)
                                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                                """, (
                                    new_dn_id, oi.get('sr_no'), oi.get('part_description'), oi.get('qty', 0),
                                    oi.get('persons_demand'), oi.get('project'), oi.get('unit_price'),
                                    oi.get('total_price'), oi.get('remarks')
                                ), commit=True)
        except Exception as e:
            logger.warning(f"Notice while migrating {src_dn_table}: {e}")

def init_database():
    """Initialize database with required tables on first run (thread-safe, idempotent)"""
    global _schema_initialized
    if _schema_initialized:
        return
        
    logger.info("Verifying database schema initialization...")
    if connection_pool is None:
        init_connection_pool()
    
    if connection_pool is None:
        logger.warning("Database connection pool could not be initialized. Schema initialization deferred.")
        return
    
    # Check if 'users' table exists; if not, create all tables and seed admin
    if not table_exists('users'):
        logger.info("Fresh database detected. Initializing entire schema and default admin...")
        from schema import create_all_tables
        create_all_tables()
        logger.info("Database schema and default admin initialized successfully!")
    else:
        # Check and ensure line tables exist if added in new updates
        if not table_exists('bom_metadata_biomedical'):
            from schema import create_line_tables
            create_line_tables('_biomedical')
        
        # Ensure default administrator accounts and executive roles are provisioned
        try:
            from schema import initialize_default_admin
            initialize_default_admin()
        except Exception as admin_err:
            logger.warning(f"Admin accounts check notice: {admin_err}")
            
    # Ensure approval remarks columns exist across all production lines
    ensure_demand_notes_remarks_columns()

    # Ensure category column exists on contracts and biomedical tables are unified
    migrate_biomedical_unified_tables()

    _schema_initialized = True
    logger.info("Database verification complete.")
