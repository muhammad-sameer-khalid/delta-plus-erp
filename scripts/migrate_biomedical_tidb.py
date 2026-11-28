"""
Standalone Database Migration Script for Delta Plus ERP
Applies schema migrations to TiDB Cloud or local MySQL database:
1. Adds gm_remarks and director_remarks to all demand_notes tables.
2. Ensures category column exists on contracts_metadata tables (Disposable / Equipment).
3. Ensures all unified _biomedical tables exist.
4. Migrates data from legacy split tables (_biomedical_disposable, _biomedical_equipment) to unified _biomedical tables.
"""
import sys
import os

# Add root folder to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger('migration')

def run_migration():
    from config import Config
    from database import init_connection_pool, ensure_demand_notes_remarks_columns, ensure_contracts_category_column, migrate_biomedical_unified_tables

    logger.info("Connecting to database: %s@%s:%s/%s",
                Config.DB_CONFIG.get('user'),
                Config.DB_CONFIG.get('host'),
                Config.DB_CONFIG.get('port'),
                Config.DB_CONFIG.get('database'))
    
    init_connection_pool()
    
    logger.info("Step 1: Ensuring gm_remarks and director_remarks on demand_notes...")
    ensure_demand_notes_remarks_columns()

    logger.info("Step 2: Ensuring category column on contracts_metadata...")
    ensure_contracts_category_column()

    logger.info("Step 3: Ensuring unified _biomedical tables and migrating legacy data...")
    migrate_biomedical_unified_tables()

    logger.info("Migration completed successfully!")

if __name__ == '__main__':
    run_migration()
