import os
from dotenv import load_dotenv
import pytz

load_dotenv(override=True)

IST = pytz.timezone("Asia/Kolkata")
UTC = pytz.utc

# Default Settings Fallbacks
AT_RISK_CONSECUTIVE = 3
AT_RISK_ROLLING_WINDOW = 7
AT_RISK_ROLLING_COUNT = 3
DEPARTMENTS = ["Full Stack", "AI Engineer", "Social Media", "Sales", "Business Analyst"]

def get_departments():
    from services import sheets_service as ss
    import json
    settings = ss.get_all_settings()
    dept_str = settings.get("departments")
    if dept_str:
        try:
            return json.loads(dept_str)
        except:
            return DEPARTMENTS
    return DEPARTMENTS

def get_at_risk_settings():
    from services import sheets_service as ss
    settings = ss.get_all_settings()
    try:
        consecutive = int(settings.get("at_risk_consecutive", AT_RISK_CONSECUTIVE))
        window = int(settings.get("at_risk_rolling_window", AT_RISK_ROLLING_WINDOW))
        count = int(settings.get("at_risk_rolling_count", AT_RISK_ROLLING_COUNT))
        return consecutive, window, count
    except ValueError:
        return AT_RISK_CONSECUTIVE, AT_RISK_ROLLING_WINDOW, AT_RISK_ROLLING_COUNT

class BaseConfig:
    SECRET_KEY = os.environ.get("SECRET_KEY", "change-me-in-production")
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = 3600  # 1 hour
    WTF_CSRF_SSL_STRICT = False

    # Google Sheets
    GOOGLE_CREDENTIALS_JSON = os.environ.get("GOOGLE_CREDENTIALS_JSON")  # Full JSON string
    SPREADSHEET_ID = os.environ.get("SPREADSHEET_ID", "")

    # Supabase
    SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
    SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

    # Rate limiting
    RATELIMIT_DEFAULT = "200 per day"
    RATELIMIT_STORAGE_URL = "memory://"

    # Session
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"

    # Logging
    LOG_LEVEL = "INFO"

    # Attendance job schedule (UTC) — 13:00 UTC = 18:30 IST
    ATTENDANCE_JOB_HOUR_UTC = 13
    ATTENDANCE_JOB_MINUTE_UTC = 0


class DevelopmentConfig(BaseConfig):
    DEBUG = True
    TESTING = False
    SESSION_COOKIE_SECURE = False


class ProductionConfig(BaseConfig):
    DEBUG = False
    TESTING = False
    SESSION_COOKIE_SECURE = True
    WTF_CSRF_SSL_STRICT = False


def get_config():
    env = os.environ.get("FLASK_ENV", "development").lower()
    return ProductionConfig if env == "production" else DevelopmentConfig
