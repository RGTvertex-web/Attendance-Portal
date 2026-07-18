import os
from dotenv import load_dotenv
import pytz

load_dotenv(override=True)

IST = pytz.timezone("Asia/Kolkata")
UTC = pytz.utc

# At-Risk threshold constants
AT_RISK_CONSECUTIVE = 3       # 3 consecutive absent days
AT_RISK_ROLLING_WINDOW = 7    # days to look back
AT_RISK_ROLLING_COUNT = 3     # absences needed within window

DEPARTMENTS = ["Full Stack", "AI Engineer", "Social Media", "Sales", "Business Analyst"]

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
