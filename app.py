

import logging
import os
from flask import Flask, session, g, redirect, url_for, request
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from config import get_config

from extensions import csrf, limiter


from werkzeug.middleware.proxy_fix import ProxyFix

def create_app():
    app = Flask(__name__)
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
    app.config.from_object(get_config())

    # ── Jinja ──────────────────────────────────────────────────────────────────
    import jinja2
    app.jinja_env.undefined = jinja2.StrictUndefined if app.debug else jinja2.Undefined

    # ── Logging ────────────────────────────────────────────────────────────────
    logging.basicConfig(
        level=app.config.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    app.logger.setLevel(app.config.get("LOG_LEVEL", "INFO"))

    # ── Extensions ─────────────────────────────────────────────────────────────
    csrf.init_app(app)
    limiter.init_app(app)

    # ── Register Blueprints ────────────────────────────────────────────────────
    from routes.auth import auth_bp
    from routes.admin import admin_bp
    from routes.manager import manager_bp
    from routes.intern import intern_bp
    from routes.reports import reports_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp, url_prefix="/admin")
    app.register_blueprint(manager_bp, url_prefix="/manager")
    app.register_blueprint(intern_bp, url_prefix="/intern")
    app.register_blueprint(reports_bp, url_prefix="/reports")

    # ── Auth Hook ──────────────────────────────────────────────────────────────
    @app.before_request
    def load_user_from_session():
        g.user = None
        g.user_role = None
        
        # Don't try to auth static assets
        if request.endpoint and request.endpoint.startswith('static'):
            return

        user_id = session.get("user_id")
        if user_id:
            try:
                from services.supabase_service import get_profile
                user_data = get_profile(user_id)
                if user_data:
                    g.user = user_data
                    g.user_role = user_data.get("role")
            except Exception as e:
                app.logger.warning(f"Session user invalid: {e}")
                session.pop("user_id", None)

    # ── APScheduler ────────────────────────────────────────────────────────────
    # Do not start background threads on Vercel serverless runtime
    if not app.testing and not os.environ.get("VERCEL"):
        from scheduler import start_scheduler
        start_scheduler(app)

    # ── Root redirect ──────────────────────────────────────────────────────────
    @app.route("/")
    def index():
        if getattr(g, "user", None):
            role = g.user_role
            if role == "admin":
                return redirect(url_for("admin.dashboard"))
            elif role == "manager":
                return redirect(url_for("manager.dashboard"))
            elif role == "intern":
                return redirect(url_for("intern.dashboard"))
        return redirect(url_for("auth.login"))

    @app.context_processor
    def inject_global_vars():
        from config import get_departments
        from services import sheets_service as ss
        from services import supabase_service as supa
        from flask import url_for
        
        notifications = []
        try:
            if getattr(g, "user", None):
                if g.user_role == "manager":
                    manager_leaves = ss.get_leaves_for_manager(g.user["id"])
                    pending_leaves = [l for l in manager_leaves if l.get("status") == "pending"]
                    if pending_leaves:
                        notifications.append({"text": f"{len(pending_leaves)} pending leave requests", "link": url_for("manager.leaves")})
                    
                    students = [s["id"] for s in supa.get_profiles_by_manager(g.user["id"])]
                    pending_reports = ss.get_pending_submissions_for_manager(g.user["id"], set(students))
                    if pending_reports:
                        notifications.append({"text": f"{len(pending_reports)} reports to review", "link": url_for("manager.reports")})
                elif g.user_role == "intern":
                    # Warnings
                    unack = [w for w in ss.get_warnings_for_student(g.user["id"]) if w.get("acknowledged") != "yes"]
                    if unack:
                        notifications.append({"text": f"You have {len(unack)} unacknowledged warning(s)", "link": url_for("intern.dashboard")})
                    
                    # Leaves (decided recently)
                    from datetime import datetime, timedelta, timezone
                    now = datetime.now(timezone.utc)
                    recent_leaves = [l for l in ss.get_leaves_for_student(g.user["id"]) if l.get("status") in ("approved", "rejected") and l.get("decided_at")]
                    # Filter to last 3 days
                    for l in recent_leaves:
                        try:
                            decided_dt = datetime.fromisoformat(l["decided_at"].replace("Z", "+00:00"))
                            if now - decided_dt <= timedelta(days=3):
                                notifications.append({"text": f"Leave from {l['start_date']} was {l['status']}", "link": url_for("intern.leave")})
                        except:
                            pass
                    
                    # Performance Reports (recent)
                    recent_perfs = [p for p in ss.get_performance_reports_for_student(g.user["id"]) if p.get("submitted_at")]
                    for p in recent_perfs:
                        try:
                            sub_dt = datetime.fromisoformat(p["submitted_at"].replace("Z", "+00:00"))
                            if now - sub_dt <= timedelta(days=3):
                                notifications.append({"text": f"New performance report for {p.get('period_start', '')}", "link": url_for("intern.performance")})
                        except:
                            pass
                    
                    # Attendance marked today
                    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                    att = [a for a in ss.get_all_attendance() if str(a.get("intern_id")) == str(g.user["id"]) and a.get("date") == today_str]
                    if att:
                        notifications.append({"text": f"Attendance marked as {att[0].get('status', '')} today", "link": url_for("intern.attendance")})
        except Exception as e:
            app.logger.error("Notification context processor failed: %s", e)
            notifications = []
                    
        return dict(DEPARTMENTS=get_departments(), notifications=notifications)

    @app.errorhandler(500)
    def handle_500(e):
        from flask import render_template
        app.logger.error("Unhandled exception: %s", e, exc_info=True)
        return render_template("errors/500.html"), 500

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
