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
        logger.info(f"Direct connection without database parameter: {e}. Trying fallback...")
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
            logger.info(f"Fallback database verification attempt: {e2}. Proceeding to pool initialization...")
            return False

def init_connection_pool():
    """Initialize MySQL connection pool with retry logic and auto-database creation"""
    global connection_pool
    max_retries = 2
    retry_delay = 1  # seconds

    host = Config.DB_CONFIG.get('host', 'localhost')
    if os.getenv('VERCEL') == '1' and host in ('localhost', '127.0.0.1'):
        logger.warning("Vercel deployment detected without DB_HOST set in environment variables.")
        return False

    # Ensure database exists before attempting to open pooled connections
    try:
        ensure_database_exists()
    except Exception as e:
        logger.warning(f"ensure_database_exists notice: {e}")

    for attempt in range(max_retries):
        try:
            logger.info(f"Attempting to connect to database (Attempt {attempt + 1}/{max_retries})...")
            connection_pool = pooling.MySQLConnectionPool(
                pool_name="delta_plus_pool",
                pool_size=int(os.getenv('DB_POOL_SIZE', 5)),
                pool_reset_session=True,
                **Config.DB_CONFIG
            )
            logger.info("MySQL connection pool created successfully")
            return True
        except Error as e:
            logger.error(f"Error creating connection pool: {e}")
            if attempt < max_retries - 1:
                logger.info(f"Retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)
            else:
                logger.error("Max retries reached. Could not connect to database.")
                return False
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
                        conn.reconnect(attempts=3, delay=1)
                    else:
                        conn.ping(reconnect=True, attempts=3, delay=1)
                except Exception as ping_err:
                    logger.warning(f"Connection ping/reconnect issue: {ping_err}")
                return conn
        return None
        
    except Error as e:
        logger.error(f"Error getting connection from pool: {e}")
        return None

def execute_query(query, params=None, fetch=False, fetch_one=False, commit=False):
    """
    Execute a SQL query with parameterized inputs to prevent SQL injection
    
    Args:
        query: SQL query string with %s placeholders
        params: Tuple of parameters to substitute
        fetch: Whether to fetch results
        fetch_one: Whether to fetch only one result
        commit: Whether to commit the transaction
    
    Returns:
        Query results if fetch=True, affected row count if commit=True, None otherwise
    """
    connection = get_db_connection()
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
        if connection:
            connection.close()

def execute_many(query, params_list, commit=True):
    """
    Execute multiple queries with different parameters (batch insert/update)
    
    Args:
        query: SQL query string
        params_list: List of parameter tuples
        commit: Whether to commit the transaction
    
    Returns:
        Number of affected rows or None on error
    """
    connection = get_db_connection()
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
        if connection:
            connection.close()

def table_exists(table_name):
    """Check if a table exists in the database"""
    query = """
        SELECT COUNT(*) as count
        FROM information_schema.tables 
        WHERE table_schema = %s AND table_name = %s
    """
    result = execute_query(query, (Config.DB_CONFIG['database'], table_name), fetch_one=True)
    return result and result['count'] > 0

def create_table(create_query):
    """Create a table with the given CREATE TABLE query"""
    return execute_query(create_query, commit=True)

def init_database():
    """Initialize database with required tables on first run (thread-safe, idempotent)"""
    global _schema_initialized
    if _schema_initialized:
        return
        
    logger.info("Verifying database schema initialization...")
    ensure_database_exists()
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
        if not table_exists('users_biomedical_disposable') or not table_exists('users_biomedical_equipment'):
            from schema import create_line_tables
            create_line_tables('_biomedical_disposable')
            create_line_tables('_biomedical_equipment')
            
    _schema_initialized = True
    logger.info("Database verification complete.")
