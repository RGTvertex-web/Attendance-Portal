"""
supabase_service.py - Handles user authentication and table operations directly via Supabase.
Uses a standalone 'users' table and manual password hashing.
"""
from supabase import create_client, Client
from flask import current_app
from werkzeug.security import generate_password_hash, check_password_hash
import uuid
from datetime import datetime, timedelta, timezone
from services.sheets_service import add_user_to_sheet

def get_supabase_client() -> Client:
    url = current_app.config.get("SUPABASE_URL")
    key = current_app.config.get("SUPABASE_KEY")
    if not url or not key:
        raise ValueError("Supabase credentials not configured.")
    return create_client(url, key)

# ── Auth Methods ──────────────────────────────────────────────────────────────

def sign_up(email, password, name, role, department=None, manager_id=None, internship_duration_months=None):
    """Sign up using manual hash and insert into users table."""
    try:
        supabase = get_supabase_client()
        
        # Check if email exists
        existing = supabase.table("users").select("id").eq("email", email).execute()
        if existing.data:
            raise ValueError("Email already registered.")
        
        # Hash the password
        password_hash = generate_password_hash(password)
        
        # Compute leave_allotted_days if intern
        leave_allotted_days = None
        if role == "intern" and internship_duration_months:
            try:
                dur = int(internship_duration_months)
                leave_allotted_days = round(dur * 3.33)
            except ValueError:
                pass

        # Create Profile
        user_data = {
            "email": email,
            "password_hash": password_hash,
            "name": name,
            "role": role,
            "department": department if department else None,
            "status": "active"
        }
        
        if manager_id:
            user_data["manager_id"] = manager_id
        if internship_duration_months:
            user_data["internship_duration_months"] = int(internship_duration_months)
        if leave_allotted_days is not None:
            user_data["leave_allotted_days"] = leave_allotted_days
            
        res = supabase.table("users").insert(user_data).execute()
        
        # Return structured data like before
        created_user = res.data[0] if res.data else user_data
        
        # Sync to Google Sheets with plain text password for visibility (per user request)
        sheet_user_data = created_user.copy()
        sheet_user_data["password"] = password
        add_user_to_sheet(sheet_user_data)
        
        return {
            "user": created_user,
            "session": {"user_id": created_user["id"]},
            "profile": created_user
        }
    except Exception as e:
        raise ValueError(f"User creation failed: {str(e)}")

def sign_in(email, password):
    """Sign in using manual password verification."""
    try:
        supabase = get_supabase_client()
        res = supabase.table("users").select("*").eq("email", email).execute()
        if not res.data:
            raise ValueError("Invalid credentials.")
            
        user = res.data[0]
        
        if not check_password_hash(user["password_hash"], password):
            raise ValueError("Invalid credentials.")
            
        return {
            "user": user,
            "session": {"user_id": user["id"]},
            "profile": user
        }
    except Exception as e:
        raise ValueError(f"Invalid credentials. {str(e)}")

def sign_out():
    # Manual auth doesn't require backend sign out for Supabase
    pass

def update_profile_and_password(user_id: str, name: str = None, new_password: str = None) -> dict:
    """Updates the user's name and/or password in the manual users table."""
    updates = {}
    
    if name:
        updates["name"] = name
        
    if new_password:
        updates["password_hash"] = generate_password_hash(new_password)
        
    if not updates:
        return None
        
    try:
        supabase = get_supabase_client()
        res = supabase.table("users").update(updates).eq("id", user_id).execute()
        
        if res.data:
            # Update the sheet as well for consistency
            from services.sheets_service import _get_sheet, _get_client
            try:
                sheet = _get_sheet("Users")
                all_rows = sheet.get_all_values()
                for i, row in enumerate(all_rows[1:], start=2):
                    if row[0] == str(user_id):
                        if name:
                            sheet.update_cell(i, 4, name) # Name column is index 3 -> 4
                        if new_password:
                            sheet.update_cell(i, 3, new_password) # Password column is index 2 -> 3
                        break
            except Exception as e:
                current_app.logger.error("Failed to sync profile update to Google Sheets: %s", e)
                
            return res.data[0]
        return None
    except Exception as e:
        current_app.logger.error("Failed to update profile for %s: %s", user_id, str(e))
        raise ValueError(f"Profile update failed: {str(e)}")


def get_user_by_id(user_id):
    """Fetch profile data by user ID."""
    if not user_id:
        return None
    return get_profile(user_id)


# ── Profile CRUD Methods ──────────────────────────────────────────────────────

def get_profile(user_id):
    """Fetch a specific user."""
    if not user_id:
        return None
    try:
        supabase = get_supabase_client()
        res = supabase.table("users").select("*").eq("id", user_id).execute()
        if res.data:
            return res.data[0]
        return None
    except Exception as e:
        current_app.logger.error("Supabase get_profile failed for %s: %s", user_id, e)
        return None

def get_all_profiles():
    """Fetch all users."""
    from flask import g, has_app_context
    if has_app_context() and hasattr(g, '_all_profiles'):
        return g._all_profiles

    try:
        supabase = get_supabase_client()
        res = supabase.table("users").select("*").execute()
        
        if has_app_context():
            g._all_profiles = res.data
        return res.data
    except Exception as e:
        current_app.logger.error("Supabase get_all_profiles failed: %s", e)
        return []

def get_profiles_by_manager(manager_id):
    """Fetch interns assigned to a specific manager."""
    return [p for p in get_all_profiles() if p.get("manager_id") == manager_id]

def get_managers_by_department(department):
    """Fetch all users with the 'manager' role in a specific department."""
    if not department:
        return []
    return [p for p in get_all_profiles() if p.get("role") == "manager" and p.get("department") == department]

def get_least_loaded_manager(department):
    """
    Finds the manager in the department with the fewest interns assigned.
    Returns the manager_id or None if no managers exist.
    """
    dept_managers = get_managers_by_department(department)
    if not dept_managers:
        return None
        
    all_profiles = get_all_profiles()
    interns = [p for p in all_profiles if p.get("role") == "intern" and p.get("department") == department]
    
    counts = {m["id"]: 0 for m in dept_managers}
    for intern in interns:
        i_mid = intern.get("manager_id")
        if i_mid in counts:
            counts[i_mid] += 1
            
    best_manager = min(dept_managers, key=lambda m: (counts[m["id"]], m["id"]))
    return best_manager["id"]

def get_all_managers():
    """Fetch all users with the 'manager' or 'admin' role."""
    return [p for p in get_all_profiles() if p.get("role") in ("manager", "admin")]

def update_profile(user_id, **fields):
    """Update specific fields for a user."""
    try:
        supabase = get_supabase_client()
        res = supabase.table("users").update(fields).eq("id", user_id).execute()
        return res.data
    except Exception as e:
        raise ValueError(f"Failed to update user: {str(e)}")

def delete_user(user_id):
    """Completely delete a user from the database and cascade their records."""
    try:
        supabase = get_supabase_client()
        # 1. Delete intern-related records
        for table in ["attendance", "submissions", "tasks", "warnings", "leaves", "reports", "performance"]:
            try:
                if table == "tasks":
                    supabase.table(table).delete().eq("assigned_to", user_id).execute()
                else:
                    supabase.table(table).delete().eq("intern_id", user_id).execute()
            except Exception:
                pass
                
        # 2. Delete manager-related records
        for table in ["tasks", "warnings", "leaves", "reports", "performance"]:
            try:
                if table == "tasks":
                    supabase.table(table).delete().eq("assigned_by", user_id).execute()
                elif table == "warnings":
                    supabase.table(table).delete().eq("issued_by", user_id).execute()
                elif table in ["leaves", "reports", "performance"]:
                    supabase.table(table).delete().eq("manager_id", user_id).execute()
            except Exception:
                pass

        # 3. Finally delete the user
        res = supabase.table("users").delete().eq("id", user_id).execute()
        return True
    except Exception as e:
        raise ValueError(f"Failed to delete user: {str(e)}")

# ── Password Reset Methods ───────────────────────────────────────────────────

def get_user_by_email(email):
    """Fetch user by email."""
    try:
        supabase = get_supabase_client()
        res = supabase.table("users").select("*").eq("email", email).execute()
        if res.data:
            return res.data[0]
        return None
    except Exception as e:
        current_app.logger.error("Supabase get_user_by_email failed for %s: %s", email, e)
        return None

def set_reset_token(user_id, token, expires_at):
    """Set reset token and expiry for a user, syncing with Google Sheets."""
    try:
        supabase = get_supabase_client()
        expires_str = expires_at.isoformat()
        res = supabase.table("users").update({
            "reset_token": token,
            "reset_token_expires_at": expires_str
        }).eq("id", user_id).execute()
        
        if res.data:
            from services.sheets_service import _get_sheet
            try:
                sheet = _get_sheet("Users")
                all_rows = sheet.get_all_values()
                for i, row in enumerate(all_rows[1:], start=2):
                    if row[0] == str(user_id):
                        sheet.update_cell(i, 12, token) # reset_token is index 11 -> 12
                        sheet.update_cell(i, 13, expires_str) # reset_token_expires_at is index 12 -> 13
                        break
            except Exception as e:
                current_app.logger.error("Failed to sync reset token to Sheets: %s", e)
        return True
    except Exception as e:
        current_app.logger.error("Failed to set reset token: %s", str(e))
        return False

def get_user_by_reset_token(token):
    """Fetch user by reset token if valid and not expired."""
    try:
        supabase = get_supabase_client()
        res = supabase.table("users").select("*").eq("reset_token", token).execute()
        if res.data:
            user = res.data[0]
            expires_at = datetime.fromisoformat(user.get("reset_token_expires_at"))
            if datetime.now(timezone.utc) <= expires_at:
                return user
        return None
    except Exception as e:
        current_app.logger.error("Supabase get_user_by_reset_token failed: %s", e)
        return None

def update_password_with_token(user_id, new_password):
    """Update password, clear reset token, and sync with Sheets."""
    password_hash = generate_password_hash(new_password)
    try:
        supabase = get_supabase_client()
        res = supabase.table("users").update({
            "password_hash": password_hash,
            "reset_token": None,
            "reset_token_expires_at": None
        }).eq("id", user_id).execute()
        
        if res.data:
            from services.sheets_service import _get_sheet
            try:
                sheet = _get_sheet("Users")
                all_rows = sheet.get_all_values()
                for i, row in enumerate(all_rows[1:], start=2):
                    if row[0] == str(user_id):
                        sheet.update_cell(i, 3, new_password) # password is index 2 -> 3
                        sheet.update_cell(i, 12, "")
                        sheet.update_cell(i, 13, "")
                        break
            except Exception as e:
                current_app.logger.error("Failed to sync new password to Sheets: %s", e)
        return True
    except Exception as e:
        current_app.logger.error("Failed to update password with token: %s", str(e))
        return False
