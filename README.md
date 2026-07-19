# Intern Management Portal

A full-stack Flask web application built to manage interns, track attendance, handle leave requests, and conduct weekly performance evaluations. The application uses a role-based access control (RBAC) system with three distinct roles: Admin, Department Manager, and Intern.

## Tech Stack
- **Backend**: Python, Flask
- **Database**: Supabase (PostgreSQL) for Profiles/Auth, Google Sheets for dynamic analytics and tabular data tracking (Attendance, Leaves, Reports).
- **Authentication**: Supabase Auth
- **Email Notifications**: Native `smtplib` connected to a Gmail account.
- **Exports**: `pandas`, `openpyxl`, `reportlab`
- **Deployment**: Configured for Vercel Serverless Functions (`vercel.json`).

## Key Features
1. **Role-Based Access Control (RBAC)**
   - **Admin**: Has global visibility. Can approve leaves, view organization-wide dashboards, manage users, handle roles, and export reports in CSV/Excel/PDF.
   - **Department Manager**: Restricted to viewing interns within their assigned department. Can mark daily attendance, assign/review tasks, and submit monthly performance reports.
   - **Intern**: Can view their own attendance calendar, submit and withdraw leave requests, submit daily task reports, view notifications, and read their performance evaluations.

2. **Automated Attendance**
   - Managers mark attendance via the portal.
   - The system automatically fires an email to the intern on behalf of the manager notifying them if they were marked Present, Absent, or On Leave.

3. **Leave Management**
   - Interns submit leave requests detailing start/end dates and reasoning.
   - Emails are routed to a centralized admin inbox (`rgtvertexintern@gmail.com`).
   - Admins review and approve/reject leave requests from the Admin dashboard.

4. **Performance & Task Tracking**
   - Managers submit a monthly graded performance report for each intern based on 7 criteria, with auto-calculated scores (out of 100) and grade bands.
   - Managers assign tasks to interns, and interns submit daily progress reports (which they can edit on the same day).

5. **Analytics & Exports**
   - Admin dashboard displays active KPIs (Present/Absent counts, unread warnings, at-risk interns).
   - One-click exports of Attendance, Leave, and Performance data to **CSV**, **Excel (.xlsx)**, and **PDF**.

6. **Self-Service & Security**
   - Built-in "Forgot Password" flow using secure email reset tokens.
   - "My Profile" allows all roles to update their names and change passwords.

---

## Local Setup Instructions

### 1. Prerequisites
- Python 3.9+
- A Supabase Project
- A Google Cloud Service Account (with Sheets/Drive API enabled)
- A Gmail account with an App Password (for SMTP)

### 2. Install Dependencies
In your terminal, navigate to the project root and install the required packages:

```bash
pip install -r requirements.txt
```

### 3. Environment Variables
Create a `.env` file in the root directory and populate it with your credentials:

```env
# Flask Settings
SECRET_KEY=your_secure_random_string_here

# Supabase Credentials
SUPABASE_URL=https://your-project-id.supabase.co
SUPABASE_KEY=your-anon-key-here

# Google Sheets Config
# Paste the entire JSON string on one line, or export it in your environment
GOOGLE_CREDENTIALS_JSON={"type": "service_account", "project_id": "...", ...}
SPREADSHEET_ID=your_google_sheet_id_here

# Email Configuration (for automated notifications)
SMTP_SERVER=smtp-mail.outlook.com
SMTP_PORT=587
SMTP_USERNAME=your-email@outlook.com
SMTP_PASSWORD=your_app_password
MANAGER_NOTIFICATION_EMAIL=your-manager-notification-email@example.com
```

### 4. Database Setup
1. **Supabase (PostgreSQL)**: Ensure your Supabase project is set up. You **must** run the SQL migration scripts located in the root directory via your Supabase SQL Editor in the following order:
   - `supabase_migration.sql` (Creates base `users` table and sync triggers)
   - `supabase_unblock_rls.sql` (Disables/configures RLS for application access)
   - `supabase_migration_manager_invites.sql` (Adds invite-related columns)
   - `supabase_migration_password_reset.sql` (Adds password reset token columns)
2. **Google Sheets**: Ensure your Google Sheet has the following tabs created exactly as named, with matching headers as defined in `services/sheets_service.py`:
   - `Users`, `Tasks`, `Submissions`, `Attendance`, `Warnings`, `Leaves`, `Reports`, `Performance`, `Invites`

### 5. Run the Application
Start the Flask development server:

```bash
python app.py
```

The app will be available at `http://127.0.0.1:5000/`.

---

## Deployment
This project is configured for deployment on **Vercel**. 
The `vercel.json` and `app.py` root file ensure the Flask WSGI app is properly handled by Vercel Serverless Functions.

1. Install the Vercel CLI.
2. Run `vercel` in the project root.
3. Add your Environment Variables via the Vercel Dashboard.
