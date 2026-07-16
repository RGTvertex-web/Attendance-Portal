"""
auth_helpers.py - Decorators for role-based access control using Flask's g object.
"""
from functools import wraps
from flask import g, redirect, url_for, flash, request

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not getattr(g, "user", None):
            flash("Please log in to access this page.", "warning")
            return redirect(url_for("auth.login", next=request.url))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if g.user_role != "admin":
            flash("Administrator access required.", "error")
            return redirect(url_for("index"))
        return f(*args, **kwargs)
    return decorated_function

def manager_required(f):
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if g.user_role not in ["manager", "admin"]:
            flash("Manager access required.", "error")
            return redirect(url_for("index"))
        return f(*args, **kwargs)
    return decorated_function

def intern_required(f):
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        # Admins and managers shouldn't normally be accessing intern endpoints, 
        # but you can decide if they should be allowed. 
        # For this portal, we restrict it to interns.
        if g.user_role != "intern":
            flash("Intern access required.", "error")
            return redirect(url_for("index"))
        return f(*args, **kwargs)
    return decorated_function
