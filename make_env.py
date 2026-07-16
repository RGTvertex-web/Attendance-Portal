"""
make_env.py — Auto-generates .env from your JSON key file
Run: python make_env.py
"""
import json, secrets, os

JSON_FILE = "attendance-portal-502411-46a0840cea1d.json"
SPREADSHEET_ID = "1CArWpWPAAr7DKwrKIzhdRstbJKiQ0NGztmjDUE2Lg3I"

with open(JSON_FILE) as f:
    creds = json.load(f)

secret_key = secrets.token_hex(32)
creds_json_str = json.dumps(creds)

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
