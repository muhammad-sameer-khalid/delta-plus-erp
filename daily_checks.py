import logging
from datetime import date
from database import execute_query
from routes.contracts_tanks import run_contracts_startup_checks

logger = logging.getLogger(__name__)

def run_daily_checks():
    """
    Check if daily checks have been run for today.
    If not, run them and update the database.
    """
    try:
        today = date.today()
        
        # Check last run date from global contracts_daily_check table
        # We assume this table exists from schema.py
        row = execute_query("SELECT last_checked_date FROM contracts_daily_check ORDER BY id DESC LIMIT 1", fetch_one=True)
        
        last_checked = row['last_checked_date'] if row else None
        
        if last_checked != today:
            logger.info(f"Daily checks not run for {today} (Last: {last_checked}). Running now...")
            
            # Run the actual checks (logic imported from contracts_tanks)
            run_contracts_startup_checks()
            
            # Update/Insert new date
            # We can just insert a new row or update the existing one. 
            # Let's update if exists, insert if not, to keep table small.
            if row:
                execute_query("UPDATE contracts_daily_check SET last_checked_date = %s WHERE id = 1", (today,), commit=True)
            else:
                execute_query("INSERT INTO contracts_daily_check (last_checked_date) VALUES (%s)", (today,), commit=True)
                
            logger.info("Daily checks completed and date updated.")
            return True
            
        return False
        
    except Exception as e:
        logger.error(f"Error in run_daily_checks: {e}")
        return False
