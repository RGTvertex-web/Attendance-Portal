"""
services/email_service.py
─────────────────────────
Handles SMTP email notifications.
"""
import os
import smtplib
import logging
from email.message import EmailMessage

logger = logging.getLogger(__name__)

def _send_email(to_email: str, subject: str, content: str, html_content: str = None, from_name: str = None):
    smtp_server = os.environ.get("SMTP_SERVER")
    smtp_port = os.environ.get("SMTP_PORT")
    smtp_username = os.environ.get("SMTP_USERNAME")
    smtp_password = os.environ.get("SMTP_PASSWORD")
    
    if not all([smtp_server, smtp_port, smtp_username, smtp_password]):
        logger.warning("SMTP configuration is missing. Email '%s' not sent.", subject)
        return False
        
    try:
        msg = EmailMessage()
        msg.set_content(content)
        
        if html_content:
            msg.add_alternative(html_content, subtype='html')
            
        msg["Subject"] = subject
        if from_name:
            msg["From"] = f"{from_name} <{smtp_username}>"
        else:
            msg["From"] = smtp_username
        msg["To"] = to_email

        with smtplib.SMTP(smtp_server, int(smtp_port)) as server:
            server.starttls()
            server.login(smtp_username, smtp_password)
            server.send_message(msg)
            
        logger.info("Sent email to %s: %s", to_email, subject)
        return True
    except Exception as e:
        logger.error("Failed to send email to %s: %s", to_email, e)
        return False

def _get_html_wrapper(content_html: str, host_url: str):
    logo_url = f"{host_url}/static/img/brand/RGTvertex-icon.png"
    return f"""
    <html>
      <body style="font-family: Arial, sans-serif; color: #333; line-height: 1.5;">
        <div style="text-align: center; margin-bottom: 20px;">
          <img src="{logo_url}" alt="RGTvertex Logo" style="height: 40px;">
        </div>
        <div style="max-width: 600px; margin: 0 auto; background: #fff; padding: 20px; border-radius: 8px; border: 1px solid #ddd;">
          {content_html}
          <br><br>
          <div style="color: #666; font-size: 12px; text-align: center;">
            &copy; RGTvertex. All rights reserved.
          </div>
        </div>
      </body>
    </html>
    """

def send_leave_request_notification(manager_email: str, student_name: str, leave_id: str, start_date: str, end_date: str, reason: str, host_url: str):
    subject = f"Leave Request from {student_name}"
    content = f"""Hello,

{student_name} has requested a leave from {start_date} to {end_date}.

Reason:
{reason}

You can review and approve or reject this request by clicking the link below:
{host_url}/manager/leaves/{leave_id}

Best,
RGTvertex Attendance Portal
"""
    html_content = _get_html_wrapper(f"""
        <h3>Leave Request</h3>
        <p><strong>{student_name}</strong> has requested a leave from <strong>{start_date}</strong> to <strong>{end_date}</strong>.</p>
        <p><strong>Reason:</strong><br>{reason}</p>
        <a href="{host_url}/manager/leaves/{leave_id}" style="display: inline-block; padding: 10px 15px; background-color: #10b981; color: white; text-decoration: none; border-radius: 4px;">Review Request</a>
    """, host_url)
    return _send_email(manager_email, subject, content, html_content)


def send_leave_decision_notification(target_email: str, student_name: str, status: str, start_date: str, end_date: str, remarks: str, manager_name: str):
    if status.lower() == "approved":
        subject = f"Leave Approved – {start_date} to {end_date}"
        # Calculate days (dummy logic or just omit if not easily calculated, but the template has [X] days)
        # The user template says: Your leave request for [Start Date] to [End Date] ([X] days) has been approved.
        # We will just pass the dates for now. 
        content = f"""Hi {student_name},

Your leave request for {start_date} to {end_date} has been approved.

Regards,
{manager_name}
RGTvertex"""
    else:
        subject = "Leave Request – Not Approved"
        content = f"""Hi {student_name},

Your leave request for {start_date} to {end_date} could not be approved at this time due to {remarks if remarks else 'workload/coverage'}.

Please reach out if you'd like to discuss alternate dates.

Regards,
{manager_name}
RGTvertex"""

    return _send_email(target_email, subject, content)

def send_attendance_notification(target_email: str, student_name: str, date: str, status: str, manager_name: str, department: str):
    # From name logic for attendance emails
    from_name = f"{manager_name} at RGTvertex"
    
    from datetime import datetime, timezone
    time_marked = datetime.now(timezone.utc).strftime("%H:%M UTC")
    
    details = f"""
--
Attendance Details:
Status: {status.title()}
Date: {date}
Time Marked: {time_marked}
Manager: {manager_name}
Department: {department}
--"""

    if status == "present":
        subject = f"Attendance – Marked Present ({date})"
        content = f"""Hi {student_name},

Your attendance for {date} has been marked Present.
{details}

Regards,
RGTvertex Attendance System"""
    elif status == "absent":
        subject = f"Attendance – Marked Absent ({date})"
        content = f"""Hi {student_name},

You have been marked Absent for {date} as no check-in was recorded.

If incorrect, please inform your manager within 24 hours.
{details}

Regards,
RGTvertex Attendance System"""
    elif status == "on_leave":
        subject = f"Attendance – On Leave ({date})"
        content = f"""Hi {student_name},

Your leave for {date} has been approved by {manager_name}. Attendance marked as On Leave.
{details}

Regards,
RGTvertex Attendance System"""
    else:
        return False
        
    return _send_email(target_email, subject, content, from_name=from_name)

def send_manager_invite_email(target_email: str, token: str, department: str, host_url: str):
    subject = f"Invitation – Department Manager Role at RGTvertex"
    invite_url = f"{host_url}/manager/signup?token={token}"
    content = f"""Hi Admin,

We're pleased to invite you to take on the role of Department Manager for {department} at RGTvertex.

Responsibilities include:
• Approving/reviewing leave requests and monitoring team attendance
• Coordinating onboarding and daily team operations
• Reporting progress to the founding team

Let us know if you accept, and we'll schedule a call to align on next steps.

Please click the link below to create your account:
{invite_url}

Regards,
Admin
RGTvertex"""
    return _send_email(target_email, subject, content)
