from app import create_app
from services.supabase_service import get_supabase_client
from services.sheets_service import add_user_to_sheet

def sync_existing_users():
    app = create_app()
    with app.app_context():
        supabase = get_supabase_client()
        
        print("Fetching users from Supabase...")
        res = supabase.table("users").select("*").execute()
        
        users = res.data
        if not users:
            print("No users found in Supabase.")
            return
            
        print(f"Found {len(users)} users. Syncing to Google Sheets...")
        for user in users:
            add_user_to_sheet(user)
            print(f"Synced {user['email']}")
            
        print("Done!")

if __name__ == "__main__":
    sync_existing_users()
