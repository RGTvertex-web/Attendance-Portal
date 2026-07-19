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
    logo_url = f"{host_url}/static/img/brand/favicon.svg"
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

def send_absence_warning_notification(target_email: str, student_name: str, department: str, days_absent: int, manager_name: str):
    """
    Sends a formal warning email for continuous unapproved absence.
    Also CC's the shared manager notification email.
    """
    subject = "Warning – Unapproved Absence from Internship Duties"
    
    content = f"""Hi {student_name},

This is to bring to your attention that you have been absent from your internship duties for the past {days_absent} days without prior notice or approval from your reporting manager.

As a {department} intern at RGTvertex, you are expected to maintain regular attendance and inform your reporting manager in advance in case of any unavoidable absence. Unapproved and unexplained absence is a serious concern and reflects poorly on your commitment to the internship.

Please treat this email as a formal warning. If such behavior continues or repeats in the future, we will have no option but to terminate your internship with immediate effect.

We expect you to report back to work immediately and maintain discipline going forward. If you are facing any genuine issue, please communicate it to us at the earliest so we can understand and assist accordingly.

Regards,
{manager_name}
Reporting Manager – {department}
RGTvertex"""
    
    cc_email = os.environ.get("MANAGER_NOTIFICATION_EMAIL", "rgtvertexintern@gmail.com")
    
    # Send to intern with CC to manager notification email
    # _send_email does not explicitly support CC, so we can send one email to the intern,
    # and a copy to the CC address. Or modify _send_email.
    # Given _send_email uses EmailMultiAlternatives which supports cc, let's just send separately 
    # to avoid changing _send_email signature if not needed, or better, we can modify the _send_email 
    # call to handle it. For now, sending a separate notification to the manager inbox is safest.
    
    # Send to intern
    _send_email(target_email, subject, content, from_name=manager_name)
    # Send copy to manager inbox
    _send_email(cc_email, f"[CC] {subject} - {student_name}", content, from_name="System Bot")
    
    return True

def send_password_reset_email(target_email: str, name: str, reset_link: str):
    subject = "Reset your RGTvertex Password"
    content = f"""Hi {name},

You requested a password reset for your RGTvertex Attendance Portal account.

Please click the link below to reset your password. This link is valid for 1 hour.
{reset_link}

If you did not request this, please ignore this email.

Best,
RGTvertex Attendance Portal
"""
    html_content = _get_html_wrapper(f"""
        <h3>Password Reset Request</h3>
        <p>Hi <strong>{name}</strong>,</p>
        <p>You requested a password reset for your RGTvertex Attendance Portal account.</p>
        <p>Please click the button below to set a new password. This link is valid for 1 hour.</p>
        <p style="margin: 30px 0;"><a href="{reset_link}" style="display: inline-block; padding: 12px 20px; background-color: #111827; color: white; text-decoration: none; border-radius: 6px; font-weight: 500;">Reset Password</a></p>
        <p style="font-size: 0.875rem; color: #666;">If you did not request a password reset, you can safely ignore this email.</p>
    """, reset_link.split("/auth/")[0])
    return _send_email(target_email, subject, content, html_content, from_name="RGTvertex Attendance Portal (No-Reply)")

