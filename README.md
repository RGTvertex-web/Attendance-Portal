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
   - **Admin**: Has global visibility. Can approve leaves, view organization-wide dashboards, and export reports in CSV/Excel/PDF.
   - **Department Manager**: Restricted to viewing interns within their assigned department. Can mark daily attendance and submit weekly performance reports.
   - **Intern**: Can view their own attendance history, submit leave requests, and read their weekly performance evaluations.

2. **Automated Attendance**
   - Managers mark attendance via the portal.
   - The system automatically fires an email to the intern on behalf of the manager notifying them if they were marked Present, Absent, or On Leave.

3. **Leave Management**
   - Interns submit leave requests detailing start/end dates and reasoning.
   - Emails are routed to a centralized admin inbox (`rgtvertexintern@gmail.com`).
   - Admins review and approve/reject leave requests from the Admin dashboard.

4. **Weekly Performance Reports**
   - Managers submit a weekly graded report for each intern based on 6 criteria (Work Quality, Task Completion, Learning Ability, Teamwork, Discipline, Behaviour).
   - System auto-calculates total scores out of 100 and applies a Grade Band (Outstanding, Excellent, Good, Satisfactory, Needs Improvement).

5. **Analytics & Exports**
   - Admin dashboard displays active KPIs (Present/Absent counts, unread warnings, at-risk students).
   - One-click exports of Attendance, Leave, and Performance data to **CSV**, **Excel (.xlsx)**, and **PDF**.

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
MAIL_USERNAME=your_sender_email@gmail.com
MAIL_PASSWORD=your_gmail_app_password
MAIL_DEFAULT_SENDER=your_sender_email@gmail.com
```

### 4. Database Setup
1. **Supabase**: Ensure your `profiles` table is set up in Supabase matching the expected schema (must include `id`, `name`, `role`, `department`, `manager_id`).
2. **Google Sheets**: Ensure your Google Sheet has the following tabs created exactly as named:
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
