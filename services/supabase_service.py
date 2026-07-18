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
        
    try:
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
    supabase = get_supabase_client()
    try:
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
    supabase = get_supabase_client()
    try:
        res = supabase.table("users").select("*").eq("id", user_id).execute()
        if res.data:
            return res.data[0]
        return None
    except Exception:
        return None

def get_all_profiles():
    """Fetch all users."""
    supabase = get_supabase_client()
    try:
        res = supabase.table("users").select("*").execute()
        return res.data
    except Exception:
        return []

def get_profiles_by_manager(manager_id):
    """Fetch interns assigned to a specific manager."""
    supabase = get_supabase_client()
    try:
        res = supabase.table("users").select("*").eq("manager_id", manager_id).execute()
        return res.data
    except Exception:
        return []

def get_managers_by_department(department):
    """Fetch all users with the 'manager' role in a specific department."""
    if not department:
        return []
    supabase = get_supabase_client()
    try:
        res = supabase.table("users").select("*").eq("role", "manager").eq("department", department).execute()
        return res.data
    except Exception:
        return []

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
    """Fetch all users with the 'manager' role."""
    supabase = get_supabase_client()
    try:
        res = supabase.table("users").select("*").eq("role", "manager").execute()
        return res.data
    except Exception:
        return []

def update_profile(user_id, **fields):
    """Update specific fields for a user."""
    supabase = get_supabase_client()
    try:
        res = supabase.table("users").update(fields).eq("id", user_id).execute()
        return res.data
    except Exception as e:
        raise ValueError(f"Failed to update user: {str(e)}")

def delete_user(user_id):
    """Completely delete a user from the database and cascade their records."""
    supabase = get_supabase_client()
    try:
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
