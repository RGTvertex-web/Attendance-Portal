"""
make_env.py — Auto-generates .env from your JSON key file
Run: python make_env.py
"""
import json, secrets, os

JSON_FILE = "your_google_service_account.json"
SPREADSHEET_ID = "your_spreadsheet_id_here"

try:
    with open(JSON_FILE) as f:
        creds = json.load(f)
    creds_json_str = json.dumps(creds)
except FileNotFoundError:
    print(f"⚠️ Warning: '{JSON_FILE}' not found. Using placeholder for credentials.")
    creds_json_str = '{"type":"service_account"}'

secret_key = secrets.token_hex(32)

env_content = f"""FLASK_ENV=development
SECRET_KEY={secret_key}
SPREADSHEET_ID={SPREADSHEET_ID}
GOOGLE_CREDENTIALS_JSON={creds_json_str}

# Optional seed defaults (used by seed_sheets.py)
SEED_ADMIN_EMAIL=admin@company.com
SEED_ADMIN_PASSWORD=Admin@123456
SEED_ADMIN_NAME=Admin
"""

with open(".env", "w") as f:
    f.write(env_content)

print("✅ .env file created successfully!")
print(f"   SECRET_KEY: {secret_key[:16]}...")
print(f"   SPREADSHEET_ID: {SPREADSHEET_ID}")
print(f"   GOOGLE_CREDENTIALS_JSON: loaded from {JSON_FILE}")
print()
print("Next: python seed_sheets.py")
