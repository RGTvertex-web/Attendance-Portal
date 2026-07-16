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

def _send_email(to_email: str, subject: str, content: str, html_content: str = None):
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


def send_leave_decision_notification(target_email: str, student_name: str, status: str, start_date: str, end_date: str, remarks: str, host_url: str):
    subject = f"Leave Request {status.title()} for {student_name}"
    content = f"""Hello,

The leave request for {student_name} ({start_date} to {end_date}) has been {status}.

Remarks:
{remarks if remarks else 'None'}

View your dashboard here:
{host_url}

Best,
RGTvertex Attendance Portal
"""
    status_color = "#10b981" if status == "approved" else "#ef4444"
    html_content = _get_html_wrapper(f"""
        <h3>Leave Request Update</h3>
        <p>The leave request for <strong>{student_name}</strong> ({start_date} to {end_date}) has been <span style="color: {status_color}; font-weight: bold;">{status}</span>.</p>
        <p><strong>Remarks:</strong><br>{remarks if remarks else 'None'}</p>
        <a href="{host_url}" style="display: inline-block; padding: 10px 15px; background-color: #000; color: white; text-decoration: none; border-radius: 4px;">View Dashboard</a>
    """, host_url)
    return _send_email(target_email, subject, content, html_content)

def send_attendance_approval_notification(target_email: str, student_name: str, date: str):
    # Pass a dummy host url just for the logo if we can. Actually host_url isn't passed here in the original code, but we can't easily get it.
    # We will just send plain text for this one if host_url is unavailable, or change the signature.
    # The signature doesn't take host_url. Let's add it, but it might break calls.
    # Let's just keep the original plain text for attendance approval, or use a relative path? Relative path in email doesn't work.
    subject = f"Attendance Approved for {date}"
    content = f"""Hello {student_name},

Your attendance for {date} has been approved and marked as Present by your manager.

Best,
RGTvertex Attendance Portal
"""
    return _send_email(target_email, subject, content)

def send_manager_invite_email(target_email: str, token: str, department: str, host_url: str):
    subject = "Invitation to join RGTvertex as a Manager"
    invite_url = f"{host_url}/manager/signup?token={token}"
    content = f"""Hello,

You have been invited to join RGTvertex as a Manager for the {department} department.

Please click the link below to create your account:
{invite_url}

This invite link will expire in 7 days.

Best,
RGTvertex Admin Team
"""
    html_content = _get_html_wrapper(f"""
        <h3>Manager Invitation</h3>
        <p>You have been invited to join RGTvertex as a Manager for the <strong>{department}</strong> department.</p>
        <p>Please click the button below to create your account and set your password:</p>
        <a href="{invite_url}" style="display: inline-block; padding: 12px 24px; background-color: #111111; color: white; text-decoration: none; border-radius: 99px; font-weight: 600;">Create Account</a>
        <p style="font-size: 0.85em; color: #6b7280; margin-top: 20px;">This invite link will expire in 7 days.</p>
    """, host_url)
    return _send_email(target_email, subject, content, html_content)
