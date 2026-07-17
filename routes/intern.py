"""
routes/intern.py — Intern routes + daily report API + weekly/monthly reports + leave
"""
import logging
import json
from datetime import datetime, timezone
import pytz

from flask import Blueprint, flash, redirect, render_template, request, url_for, g
from extensions import limiter
from services import sheets_service as ss
from services.attendance_service import get_student_attendance_summary
from services.auth_helpers import intern_required

intern_bp = Blueprint("intern", __name__)
logger = logging.getLogger(__name__)
IST = pytz.timezone("Asia/Kolkata")

@intern_bp.route("/dashboard")
@intern_required
def dashboard():
    # Fetch intern's submissions
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

    return render_template("intern/dashboard.html",
                           att_summary=att_summary,
                           warnings=warnings,
                           submissions=submissions,
                           perf_reports=perf_reports)


@intern_bp.route("/api/submit-report", methods=["POST"])
@intern_required
@limiter.limit("10 per hour")
def submit_report():
    task_given = request.form.get("task_given", "").strip()
    task_done = request.form.get("task_done", "").strip()
    task_remaining = request.form.get("task_remaining", "").strip()

    if not task_given or not task_done:
        flash("Please fill in what task was given and what is done.", "error")
        return redirect(url_for("intern.dashboard"))

    report_data = {
        "given": task_given[:1000],
        "done": task_done[:2000],
        "remaining": task_remaining[:2000]
    }
    notes_json = json.dumps(report_data)

    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    virtual_task_id = f"REPORT-{date_str}"
    
    submitted_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    
    ss.create_submission(virtual_task_id, g.user["id"], "", notes_json, submitted_at, "submitted")
    logger.info("AUDIT: Intern %s submitted daily report for %s", g.user["id"], date_str)

    flash("Daily report submitted successfully! ✅", "success")
    return redirect(url_for("intern.dashboard"))


@intern_bp.route("/leave", methods=["GET", "POST"])
@intern_required
def leave():
    from services.email_service import send_leave_request_notification
    from services import supabase_service as supa
    
    # Calculate leave balance
    all_leaves = ss.get_leaves_for_student(g.user["id"])
    approved_leaves = [l for l in all_leaves if l["status"] == "approved"]
    
    total_allotted = g.user.get("leave_allotted_days", 0)
    
    used_days = 0
    for l in approved_leaves:
        try:
            used_days += int(l.get("days_requested", 0))
        except ValueError:
            pass
            
    remaining_days = max(0, total_allotted - used_days)
    
    if request.method == "POST":
        start_date = request.form.get("start_date", "").strip()
        end_date = request.form.get("end_date", "").strip()
        reason = request.form.get("reason", "").strip()
        
        if not start_date or not end_date or not reason:
            flash("All fields are required.", "error")
            return redirect(url_for("intern.leave"))
            
        manager_id = g.user.get("manager_id")
        if not manager_id:
            flash("You do not have a manager assigned.", "error")
            return redirect(url_for("intern.leave"))
            
        # Calculate days requested
        try:
            sd = datetime.strptime(start_date, "%Y-%m-%d")
            ed = datetime.strptime(end_date, "%Y-%m-%d")
            days_requested = (ed - sd).days + 1
            if days_requested <= 0:
                flash("End date must be on or after start date.", "error")
                return redirect(url_for("intern.leave"))
        except ValueError:
            flash("Invalid date format.", "error")
            return redirect(url_for("intern.leave"))
            
        if days_requested > remaining_days:
            flash(f"Warning: Requesting {days_requested} days exceeds your remaining balance of {remaining_days}. Your manager may reject this.", "warning")
            
        # Create leave
        leave_record = ss.create_leave_request(g.user["id"], g.user.get("department", "Unknown"), manager_id, start_date, end_date, days_requested, reason)
        logger.info("AUDIT: Intern %s requested leave from %s to %s", g.user["id"], start_date, end_date)
        
        # Send email (In real app, fetch manager email from auth.users or profiles if stored there)
        manager = supa.get_profile(manager_id)
        # Note: profiles table doesn't have email in our schema, so email_service needs to handle this or we store email in profiles.
        # The prompt says: Supabase Auth for signup. We should probably fetch manager's email if possible, or just pass a dummy.
        host_url = request.host_url.rstrip("/")
        # We will update email_service to accept these arguments
        send_leave_request_notification("rgtvertexintern@gmail.com", g.user["name"], leave_record["leave_id"], start_date, end_date, reason, host_url)
            
        flash("Leave request submitted successfully.", "success")
        return redirect(url_for("intern.leave"))
        
    all_leaves.sort(key=lambda l: l.get("start_date", ""), reverse=True)
    return render_template("intern/leave.html", leaves=all_leaves, total_allotted=total_allotted, used_days=used_days, remaining_days=remaining_days)


@intern_bp.route("/reports", methods=["GET", "POST"])
@intern_required
def reports():
    if request.method == "POST":
        report_type = request.form.get("report_type")
        period_start = request.form.get("period_start")
        period_end = request.form.get("period_end")
        content = request.form.get("content")
        
        if not report_type or not period_start or not period_end or not content:
            flash("All fields are required.", "error")
            return redirect(url_for("intern.reports"))
            
        manager_id = g.user.get("manager_id")
        department = g.user.get("department", "Unknown")
        
        ss.create_report(g.user["id"], department, manager_id, report_type, period_start, period_end, content)
        flash(f"{report_type.title()} report submitted successfully.", "success")
        return redirect(url_for("intern.reports"))
        
    my_reports = ss.get_reports_for_intern(g.user["id"])
    my_reports.sort(key=lambda r: r.get("submitted_at", ""), reverse=True)
    return render_template("intern/reports.html", reports=my_reports)

@intern_bp.route("/performance")
@intern_required
def performance():
    reports = ss.get_performance_reports_for_student(g.user["id"])
    reports.sort(key=lambda r: r.get("submitted_at", ""), reverse=True)
    return render_template("intern/performance.html", reports=reports)
