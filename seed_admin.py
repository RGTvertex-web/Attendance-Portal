"""
seed_admin.py — Script to create the initial admin user in the custom users table.

Run once to bootstrap the admin account:
    python seed_admin.py
"""

import os
import sys
import getpass
from dotenv import load_dotenv

load_dotenv()

required_env = ["SUPABASE_URL", "SUPABASE_KEY"]
missing = [v for v in required_env if not os.environ.get(v)]
if missing:
    print(f"ERROR: Missing env vars: {', '.join(missing)}")
    sys.exit(1)

from services.supabase_service import get_supabase_client
from app import create_app
from werkzeug.security import generate_password_hash

def create_admin():
    print("--- Create Initial Admin Account ---")
    
    default_name = os.environ.get("SEED_ADMIN_NAME", "Admin")
    default_email = os.environ.get("SEED_ADMIN_EMAIL", "admin@yourcompany.com")
    
    name_input = input(f"Admin Name [{default_name}]: ").strip()
    name = name_input if name_input else default_name
    
    email_input = input(f"Admin Email [{default_email}]: ").strip()
    email = email_input if email_input else default_email
    
    password = os.environ.get("SEED_ADMIN_PASSWORD")
    if not password:
        password = getpass.getpass("Admin Password (min 6 chars): ")
    
    if not name or not email or len(password) < 6:
        print("Invalid input. Name, email required. Password > 6 chars.")
        sys.exit(1)
        
    app = create_app()
    with app.app_context():
        supabase = get_supabase_client()
        
        print(f"\nCreating admin user '{email}'...")
        try:
            # Hash the password manually
            password_hash = generate_password_hash(password)
            
            # Insert into users with role="admin"
            user_data = {
                "name": name,
                "email": email,
                "password_hash": password_hash,
                "role": "admin",
                "department": None,
                "status": "active"
            }
            
            res = supabase.table("users").insert(user_data).execute()
            
            from services.sheets_service import add_user_to_sheet
            sheet_user_data = res.data[0] if res.data else user_data
            sheet_user_data["password"] = password
            add_user_to_sheet(sheet_user_data)
            
            print("\n✅ Admin account created successfully!")
            print("You can now log in at /login with this account.")
            
        except Exception as e:
            print(f"\n❌ Error creating admin: {e}")
            print("Note: If the email is already registered, this will fail.")

if __name__ == "__main__":
    create_admin()
