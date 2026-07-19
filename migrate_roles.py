import os
import sys

# Add current directory to path to import services
sys.path.append(os.getcwd())

from services import supabase_service as supa
from services import sheets_service as ss

def migrate_roles():
    print("Starting Role Migration...")
    
    # 1. Update Supabase
    profiles = supa.get_all_profiles()
    student_profiles = [p for p in profiles if p.get("role") == "student"]
    
    print(f"Found {len(student_profiles)} 'student' profiles in Supabase.")
    
    for p in student_profiles:
        supa.update_profile(p["id"], role="intern")
        print(f"Updated Supabase profile {p['id']} to 'intern'")

    # 2. Update Sheets
    try:
        sheet = ss._get_sheet("Users")
        rows = sheet.get_all_values()
        header = rows[0]
        if "role" in header:
            role_idx = header.index("role")
            
            updates = 0
            # iterate 1-indexed for row numbers in Sheets
            for i, row in enumerate(rows[1:], start=2):
                if len(row) > role_idx and row[role_idx] == "student":
                    sheet.update_cell(i, role_idx + 1, "intern")
                    updates += 1
            print(f"Updated {updates} 'student' rows in Google Sheets.")
        else:
            print("Could not find 'role' column in Users sheet.")
    except Exception as e:
        print(f"Failed to update Google Sheets: {e}")

if __name__ == "__main__":
    migrate_roles()
