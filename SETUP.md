# Creator Attendance Portal — Setup Guide

## Prerequisites
- Python 3.10+
- A Google account with access to Google Cloud Console
- A Google Spreadsheet (blank)

---

## 1. Google Cloud: Create Service Account

1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Create a new project (or use an existing one)
3. Enable these two APIs:
   - **Google Sheets API**
   - **Google Drive API**
4. Navigate to **IAM & Admin → Service Accounts**
5. Click **Create Service Account**
   - Name: `attendance-portal`
   - Role: `Editor` (or custom role with Sheets + Drive read/write)
6. Click the service account → **Keys → Add Key → Create new key → JSON**
7. Download the JSON file — **keep it secret, never commit it**

---

## 2. Share Your Spreadsheet

1. Create a blank Google Spreadsheet at [sheets.google.com](https://sheets.google.com)
2. Copy the **Spreadsheet ID** from the URL:
   ```
   https://docs.google.com/spreadsheets/d/SPREADSHEET_ID/edit
   ```
3. Click **Share** → paste the service account's `client_email` from the JSON file
4. Give it **Editor** access
5. Click **Send** (ignore the warning about sharing outside organization)

---

## 3. Environment Setup

```bash
# Clone / navigate to project
cd creator-attendance-portal

# Create virtual environment
python -m venv venv
venv\Scripts\activate      # Windows
# source venv/bin/activate  # Linux/Mac

# Install dependencies
pip install -r requirements.txt

# Copy env template
copy .env.example .env
```

Edit `.env` and fill in:

```env
FLASK_ENV=development
SECRET_KEY=<generate with: python -c "import secrets; print(secrets.token_hex(32))">
SPREADSHEET_ID=<your spreadsheet ID>
GOOGLE_CREDENTIALS_JSON=<paste minified JSON — see below>

# SMTP Configuration for Email Notifications
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your.email@gmail.com
SMTP_PASSWORD=your_app_password
```

### Minify the JSON credentials
```bash
python -c "import json,sys; print(json.dumps(json.load(open('your-key.json'))))"
```
Copy the output (one long line) as the value of `GOOGLE_CREDENTIALS_JSON`.

---

## 4. Seed the Database (run once)

```bash
# Optional: set default admin credentials
set SEED_ADMIN_EMAIL=admin@yourcompany.com
set SEED_ADMIN_PASSWORD=SecurePassword123!
set SEED_ADMIN_NAME=Admin

python seed_sheets.py
```

This will:
- Create 5 worksheets: `Users`, `Tasks`, `Submissions`, `Attendance`, `Warnings`
- Create the initial admin user

> ⚠️ **Change the default admin password immediately after first login.**

---

## 5. Run Locally

```bash
python app.py
# or
flask --app app:create_app run --debug
```

Visit: [http://localhost:5000](http://localhost:5000)

---

## 6. Deploy to Render

1. Push the repo to GitHub (ensure `.env` is in `.gitignore`)
2. Create a new **Web Service** on [render.com](https://render.com)
3. Connect your GitHub repo
4. Configure:
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn app:create_app()`
   - **Environment:** Add all variables from `.env.example` in the Render dashboard
5. Set `FLASK_ENV=production`
6. Deploy!

---

## 7. Sheet Structure Reference

| Worksheet   | Key Columns                                                  |
|-------------|--------------------------------------------------------------|
| Users       | user_id, name, email, password_hash, role, manager_id, status |
| Tasks       | task_id, title, description, category, assigned_to, due_date  |
| Submissions | submission_id, task_id, student_id, submitted_at, status, content_link |
| Attendance  | attendance_id, student_id, date, status, category, linked_task_id |
| Warnings    | warning_id, student_id, date, reason, issued_by, acknowledged  |
| Performance | report_id, student_id, manager_id, report_type, rating, discipline, feedback, created_at |
| Leaves      | leave_id, student_id, manager_id, start_date, end_date, reason, status, decided_by, decided_at, remarks |

---

## 8. Security Notes

- Never commit `.env` or your service account JSON to Git
- Add both to `.gitignore`:
  ```
  .env
  *.json
  __pycache__/
  venv/
  ```
- Rotate `SECRET_KEY` if it's ever exposed
- The attendance scheduler fires daily at **13:00 UTC (18:30 IST)**
- Admin can manually trigger it via the dashboard
