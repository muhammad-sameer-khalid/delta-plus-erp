"""
Migration script for major ERP enhancements:
1. BOM Tank, Assembly, Sub-Assembly, Currency, Unit Price, Total Price
2. Demand Notes Unit Price, Total Price, Decline Remarks, Demand Type (import/local)
3. PO Metadata & QC Components Type (import/local)
4. Split Biomedical into Biomedical - Disposable and Biomedical - Equipment
"""
import sys
import os

# Add root directory to python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from database import init_connection_pool, execute_query, table_exists
from config import Config
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def column_exists(table_name, column_name):
    query = """
        SELECT COUNT(*) as count 
        FROM information_schema.columns 
        WHERE table_schema = %s AND table_name = %s AND column_name = %s
    """
    res = execute_query(query, (Config.DB_CONFIG['database'], table_name, column_name), fetch_one=True)
    return res and res['count'] > 0

def add_column_if_missing(table_name, column_name, column_def):
    if not table_exists(table_name):
        return
    if not column_exists(table_name, column_name):
        logger.info(f"Adding column {column_name} to {table_name}")
        sql = f"ALTER TABLE `{table_name}` ADD COLUMN `{column_name}` {column_def}"
        execute_query(sql, commit=True)
    else:
        logger.info(f"Column {column_name} already exists in {table_name}")

def main():
    logger.info("Starting database migration...")
    init_connection_pool()
    
    # First, create all tables for _biomedical_disposable and _biomedical_equipment
    from schema import create_line_tables
    logger.info("Creating tables for _biomedical_disposable...")
    create_line_tables('_biomedical_disposable')
    logger.info("Creating tables for _biomedical_equipment...")
    create_line_tables('_biomedical_equipment')
    
    # All production line suffixes
    suffixes = ['', '_battery', '_biomedical', '_biomedical_disposable', '_biomedical_equipment']
    
    for s in suffixes:
        # 1. BOM metadata
        add_column_if_missing(f'bom_metadata{s}', 'tank', 'VARCHAR(255) NULL')
        add_column_if_missing(f'bom_metadata{s}', 'assembly_name', 'VARCHAR(255) NULL')
        add_column_if_missing(f'bom_metadata{s}', 'sub_assembly_name', 'VARCHAR(255) NULL')
        add_column_if_missing(f'bom_metadata{s}', 'currency', "VARCHAR(50) DEFAULT 'RMB'")
        
        # 2. BOM items
        add_column_if_missing(f'bom_items{s}', 'unit_price', 'DECIMAL(15, 2) DEFAULT 0.00')
        add_column_if_missing(f'bom_items{s}', 'total_price', 'DECIMAL(15, 2) DEFAULT 0.00')
        
        # 3. Demand notes
        add_column_if_missing(f'demand_notes{s}', 'demand_type', "ENUM('import', 'local') DEFAULT 'import'")
        add_column_if_missing(f'demand_notes{s}', 'decline_remarks', 'TEXT NULL')
        add_column_if_missing(f'demand_notes{s}', 'declined_by', 'VARCHAR(255) NULL')
        add_column_if_missing(f'demand_notes{s}', 'declined_at', 'TIMESTAMP NULL')
        
        # 4. Demand items
        add_column_if_missing(f'demand_items{s}', 'unit_price', 'DECIMAL(15, 2) DEFAULT 0.00')
        add_column_if_missing(f'demand_items{s}', 'total_price', 'DECIMAL(15, 2) DEFAULT 0.00')
        
        # 5. PO metadata
        add_column_if_missing(f'po_metadata{s}', 'po_type', "ENUM('import', 'local') DEFAULT 'import'")
        
        # 6. QC components
        add_column_if_missing(f'qc_components{s}', 'po_type', "ENUM('import', 'local') DEFAULT 'import'")

    logger.info("Migration completed successfully!")

if __name__ == '__main__':
    main()
