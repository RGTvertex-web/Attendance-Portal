

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
    app.jinja_env.undefined = jinja2.StrictUndefined

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
        from config import DEPARTMENTS
        return dict(DEPARTMENTS=DEPARTMENTS)

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
