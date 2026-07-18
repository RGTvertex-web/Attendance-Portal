"""
routes/student.py — Student routes + daily report API
"""
import logging
import json
from datetime import datetime, timezone
import pytz

from flask import Blueprint, flash, redirect, render_template, request, url_for, g
from extensions import limiter
from services import sheets_service as ss
from services.attendance_service import get_student_attendance_summary
from services.auth_helpers import student_required

student_bp = Blueprint("student", __name__)
logger = logging.getLogger(__name__)
IST = pytz.timezone("Asia/Kolkata")

@student_bp.route("/dashboard")
@student_required
def dashboard():
    # Fetch student's submissions (now used as Daily Reports)
    att_summary = get_student_attendance_summary(g.user["id"])
    warnings = ss.get_warnings_for_student(g.user["id"])
    submissions = ss.get_submissions_for_student(g.user["id"])
    perf_reports = ss.get_performance_reports_for_student(g.user["id"])
    
    # Parse JSON notes if possible
    for sub in submissions:
        try:
            sub["report_data"] = json.loads(sub.get("notes", "{}"))
        except:
            sub["report_data"] = {"given": "Unknown", "done": sub.get("notes", ""), "remaining": "Unknown"}
            
    # Sort submissions by date descending
    submissions.sort(key=lambda s: s.get("submitted_at", ""), reverse=True)
    perf_reports.sort(key=lambda p: p.get("created_at", ""), reverse=True)

    return render_template("student/dashboard.html",
                           att_summary=att_summary,
                           warnings=warnings,
                           submissions=submissions,
                           perf_reports=perf_reports)


@student_bp.route("/api/submit-report", methods=["POST"])
@student_required
@limiter.limit("10 per hour")
def submit_report():
    task_given = request.form.get("task_given", "").strip()
    task_done = request.form.get("task_done", "").strip()
    task_remaining = request.form.get("task_remaining", "").strip()

    if not task_given or not task_done:
        flash("Please fill in what task was given and what is done.", "error")
        return redirect(url_for("student.dashboard"))

    # We will store this as a JSON string in the 'notes' column to easily parse it later
    report_data = {
        "given": task_given[:1000],
        "done": task_done[:2000],
        "remaining": task_remaining[:2000]
    }
    notes_json = json.dumps(report_data)

    # For the daily report, we'll use a virtual 'task_id' based on the date
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    virtual_task_id = f"REPORT-{date_str}"
    
    submitted_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    
    # Create the submission in sheets
    ss.create_submission(virtual_task_id, g.user["id"], "", notes_json, submitted_at, "submitted")
    logger.info("AUDIT: Student %s submitted daily report for %s", g.user["id"], date_str)

    flash("Daily report submitted successfully! ✅", "success")
    return redirect(url_for("student.dashboard"))


@student_bp.route("/leave", methods=["GET", "POST"])
@student_required
def leave():
    from services.email_service import send_leave_request_notification
    from services import supabase_service as supa
    
    if request.method == "POST":
        start_date = request.form.get("start_date", "").strip()
        end_date = request.form.get("end_date", "").strip()
        reason = request.form.get("reason", "").strip()
        
        if not start_date or not end_date or not reason:
            flash("All fields are required.", "error")
            return redirect(url_for("student.leave"))
            
        manager_id = g.user.get("manager_id")
        if not manager_id:
            flash("You do not have a manager assigned.", "error")
            return redirect(url_for("student.leave"))
            
        # Create leave
        leave_record = ss.create_leave_request(g.user["id"], manager_id, start_date, end_date, reason)
        logger.info("AUDIT: Student %s requested leave from %s to %s", g.user["id"], start_date, end_date)
        
        # Send email
        manager = supa.get_profile(manager_id)
        if manager and manager.get("email"):
            host_url = request.host_url.rstrip("/")
            send_leave_request_notification(manager["email"], g.user["name"], leave_record["leave_id"], start_date, end_date, reason, host_url)
            
        flash("Leave request submitted successfully.", "success")
        return redirect(url_for("student.leave"))
        
    leaves = ss.get_leaves_for_student(g.user["id"])
    leaves.sort(key=lambda l: l.get("start_date", ""), reverse=True)
    return render_template("student/leave.html", leaves=leaves)
