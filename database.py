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
    if os.getenv('VERCEL') == '1' and host in ('localhost', '127.0.0.1'):
        logger.warning("Running on Vercel with DB_HOST=localhost. Remote database environment variables need to be set in Vercel settings.")
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
    if os.getenv('VERCEL') == '1' and host in ('localhost', '127.0.0.1'):
        logger.warning("Vercel deployment detected without DB_HOST set in environment variables.")
        return False

    default_pool_size = 1 if os.getenv('VERCEL') == '1' else 5
    pool_size = int(os.getenv('DB_POOL_SIZE', default_pool_size))

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
        if not table_exists('bom_metadata_biomedical_disposable') or not table_exists('bom_metadata_biomedical_equipment'):
            from schema import create_line_tables
            create_line_tables('_biomedical_disposable')
            create_line_tables('_biomedical_equipment')
            
    _schema_initialized = True
    logger.info("Database verification complete.")
