"""
seed_sheets.py — One-time setup script to initialize Google Sheet structure.

Run once before starting the app:
    python seed_sheets.py

To clear all existing data and reset headers, run:
    python seed_sheets.py --reset
"""

import os
import sys
from datetime import datetime, timezone
import argparse

from dotenv import load_dotenv
load_dotenv()

# Must be set before importing services
required_env = ["GOOGLE_CREDENTIALS_JSON", "SPREADSHEET_ID"]
missing = [v for v in required_env if not os.environ.get(v)]
if missing:
    print(f"ERROR: Missing env vars: {', '.join(missing)}")
    print("Copy .env.example to .env and fill in all values.")
    sys.exit(1)

from services.sheets_service import (
    SHEET_HEADERS, _get_spreadsheet, _get_sheet, _new_id, _now_utc_str
)

def seed(reset=False):
    print("Connecting to Google Sheets...")
    spreadsheet = _get_spreadsheet()
    existing_sheets = {ws.title: ws for ws in spreadsheet.worksheets()}

    for sheet_name, headers in SHEET_HEADERS.items():
        if sheet_name not in existing_sheets:
            print(f"  Creating worksheet: {sheet_name}")
            ws = spreadsheet.add_worksheet(title=sheet_name, rows=1000, cols=len(headers))
            ws.append_row(headers, value_input_option="RAW")
        else:
            if reset:
                print(f"  Resetting worksheet: {sheet_name}")
                ws = existing_sheets[sheet_name]
                ws.clear()
                ws.append_row(headers, value_input_option="RAW")
            else:
                print(f"  Worksheet already exists: {sheet_name} ✓ (run with --reset to clear and recreate headers)")

    print("\n✅ Seed complete! All sheets are ready.")
    print(f"   Spreadsheet: https://docs.google.com/spreadsheets/d/{os.environ['SPREADSHEET_ID']}/edit")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--reset', action='store_true', help='Clear existing sheets and reset headers')
    args = parser.parse_args()
    seed(reset=args.reset)
