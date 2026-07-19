import os
import sys
import logging
from dotenv import load_dotenv

# Setup path so we can import services
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv()

from services import sheets_service as ss

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    spreadsheet = ss._get_spreadsheet()
    existing_sheets = [ws.title for ws in spreadsheet.worksheets()]
    
    # 1. Holidays
    if "Holidays" not in existing_sheets:
        logger.info("Creating Holidays sheet...")
        ws = spreadsheet.add_worksheet(title="Holidays", rows=100, cols=3)
        ws.append_row(["date", "name"])
    else:
        logger.info("Holidays sheet already exists.")

    # 2. Settings
    if "Settings" not in existing_sheets:
        logger.info("Creating Settings sheet...")
        ws = spreadsheet.add_worksheet(title="Settings", rows=100, cols=3)
        ws.append_row(["key", "value"])
        # Seed initial data from config.py equivalents
        from config import DEPARTMENTS
        import json
        settings_data = [
            ["departments", json.dumps(DEPARTMENTS)],
            ["at_risk_consecutive", "2"],
            ["at_risk_rolling_count", "4"],
            ["at_risk_rolling_window", "30"],
            ["manager_notification_email", "admin@rgtvertex.com"]
        ]
        for row in settings_data:
            ws.append_row(row)
    else:
        logger.info("Settings sheet already exists.")
        
    # 3. AuditLog
    if "AuditLog" not in existing_sheets:
        logger.info("Creating AuditLog sheet...")
        ws = spreadsheet.add_worksheet(title="AuditLog", rows=1000, cols=5)
        ws.append_row(["timestamp", "actor_id", "action", "details"])
    else:
        logger.info("AuditLog sheet already exists.")

    logger.info("Migration complete!")

if __name__ == "__main__":
    main()
