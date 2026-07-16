"""
routes/auth.py — Authentication routes (login, signup, logout) using Supabase Auth.
"""
import logging
from flask import Blueprint, render_template, redirect, url_for, flash, request, session, g
from app import limiter
from services import supabase_service as supa
from services import sheets_service as ss

logger = logging.getLogger(__name__)
auth_bp = Blueprint("auth", __name__)

@auth_bp.route("/login", methods=["GET", "POST"])
@limiter.limit("10 per minute")
def login():
    if getattr(g, "user", None):
        return redirect(url_for("index"))

    error = None
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        
        if not email or not password:
            error = "Email and password are required."
        else:
            try:
                auth_data = supa.sign_in(email, password)
                if auth_data and auth_data.get("profile"):
                    profile = auth_data["profile"]
                    session["user_id"] = profile["id"]
                    
                    # Log them in
                    flash("Logged in successfully.", "success")
                    role = profile.get("role")
                    if role == "admin":
                        return redirect(url_for("admin.dashboard"))
                    elif role == "manager":
                        return redirect(url_for("manager.dashboard"))
                    else:
                        return redirect(url_for("intern.dashboard"))
                else:
                    error = "Invalid credentials."
            except Exception as e:
                error = f"Login failed: {str(e)}"
                logger.warning("Login failed for %s: %s", email, str(e))

    return render_template("auth/login.html", error=error)

@auth_bp.route("/signup", methods=["GET", "POST"])
@limiter.limit("5 per minute")
def signup():
    if getattr(g, "user", None):
        return redirect(url_for("index"))

    error = None
    managers = supa.get_all_managers()
    departments = ["Full-Stack", "AI", "Sales", "Social Business Analysis"]

    if request.method == "POST":
        name = request.form.get("name")
        email = request.form.get("email")
        password = request.form.get("password")
        role = "intern"  # Public signup is strictly for interns now
        department = request.form.get("department")
        manager_id = request.form.get("manager_id")
        internship_duration = request.form.get("internship_duration_months")
        
        if not name or not email or not password or not department:
            error = "Name, email, password, and department are required."
        elif department not in departments:
            error = "Invalid department selected."
        else:
            try:
                if role == "intern" and not internship_duration:
                    error = "Interns must select an internship duration."
                else:
                    # Validate manager is in same department (if one is selected)
                    if manager_id:
                        manager_profile = supa.get_profile(manager_id)
                        if manager_profile and manager_profile.get("department") != department:
                            error = "Manager must be in the same department."
                    
                    if not error:
                        auth_data = supa.sign_up(
                            email=email,
                            password=password,
                            name=name,
                            role=role,
                            department=department,
                            manager_id=manager_id if manager_id else None,
                            internship_duration_months=internship_duration if role == "intern" else None
                        )
                        
                        if auth_data and auth_data.get("profile"):
                            profile = auth_data["profile"]
                            session["user_id"] = profile["id"]
                            flash("Account created! Welcome.", "success")
                            
                            if role == "manager":
                                return redirect(url_for("manager.dashboard"))
                            else:
                                return redirect(url_for("intern.dashboard"))
                        else:
                            error = "Failed to create account."
            except Exception as e:
                error = f"Sign up failed: {str(e)}"
                logger.error("Signup failed for %s: %s", email, str(e))

    return render_template("auth/signup.html", error=error, managers=managers, departments=departments)

@auth_bp.route("/manager/signup", methods=["GET", "POST"])
@limiter.limit("5 per minute")
def manager_signup():
    if getattr(g, "user", None):
        return redirect(url_for("index"))

    token = request.args.get("token")
    if not token:
        flash("This invite link is invalid or has expired.", "error")
        return redirect(url_for("auth.login"))

    from datetime import datetime, timezone
    
    invite = ss.get_invite_by_token(token)
    
    if not invite:
        flash("This invite link is invalid.", "error")
        return redirect(url_for("auth.login"))
        
    if invite.get("used"):
        flash("This invite link has already been used.", "error")
        return redirect(url_for("auth.login"))
        
    expires_at = datetime.fromisoformat(invite.get("expires_at"))
    if datetime.now(timezone.utc) > expires_at:
        flash("This invite link has expired.", "error")
        return redirect(url_for("auth.login"))

    error = None
    if request.method == "POST":
        name = request.form.get("name")
        password = request.form.get("password")
        
        if not name or not password:
            error = "Name and password are required."
        else:
            try:
                auth_data = supa.sign_up(
                    email=invite["email"],
                    password=password,
                    name=name,
                    role="manager",
                    department=invite["department"]
                )
                
                if auth_data and auth_data.get("profile"):
                    ss.mark_invite_used(token)
                    profile = auth_data["profile"]
                    session["user_id"] = profile["id"]
                    flash("Manager account created! Welcome.", "success")
                    return redirect(url_for("manager.dashboard"))
                else:
                    error = "Failed to create account."
            except Exception as e:
                error = f"Sign up failed: {str(e)}"
                logger.error("Manager signup failed for %s: %s", invite["email"], str(e))

    return render_template("auth/manager_signup.html", error=error, invite=invite, token=token)

@auth_bp.route("/logout")
def logout():
    session.pop("user_id", None)
    supa.sign_out()
    flash("You have been logged out.", "info")
    return redirect(url_for("auth.login"))

@auth_bp.route("/forgot-password", methods=["GET", "POST"])
@limiter.limit("3 per hour")
def forgot_password():
    if getattr(g, "user", None):
        return redirect(url_for("index"))

    error = None
    if request.method == "POST":
        email = request.form.get("email")
        if email:
            # Password reset flow is disabled since we are using a custom auth table.
            flash("Password reset is currently disabled. Please contact your administrator.", "warning")
            return redirect(url_for("auth.login"))
        else:
            error = "Email is required."
            
    return render_template("auth/forgot_password.html", error=error)
