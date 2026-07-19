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
from services.attendance_service import get_student_attendance_summary, get_attendance_trend_for_target
from services.auth_helpers import intern_required

intern_bp = Blueprint("intern", __name__)
logger = logging.getLogger(__name__)
IST = pytz.timezone("Asia/Kolkata")

@intern_bp.route("/dashboard")
@intern_required
def dashboard():
    # Fetch intern's submissions
    att_summary = get_student_attendance_summary(g.user["id"])
    trend_data = get_attendance_trend_for_target({g.user["id"]})
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
    
    # Manager contact info
    from services import supabase_service as supa
    manager_profile = None
    if g.user.get("manager_id"):
        manager_profile = supa.get_user_by_id(g.user["manager_id"])
        
    # Check for today's report to allow editing
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    virtual_task_id = f"REPORT-{today_str}"
    today_report = next((s for s in submissions if str(s.get("task_id")) == virtual_task_id), None)

    return render_template("intern/dashboard.html",
                           att_summary=att_summary,
                           warnings=warnings,
                           submissions=submissions,
                           perf_reports=perf_reports,
                           trend=trend_data,
                           manager_profile=manager_profile,
                           today_report=today_report)

@intern_bp.route("/attendance")
@intern_required
def attendance():
    import calendar
    from datetime import date
    
    today = date.today()
    year = today.year
    month = today.month
    
    # Get all attendance records for this intern
    all_att = ss.get_all_attendance()
    my_att = [a for a in all_att if str(a.get("intern_id")) == str(g.user["id"])]
    
    # Map dates to status for quick lookup
    # Format: YYYY-MM-DD -> status
    att_map = {}
    for a in my_att:
        att_map[a.get("date")] = a.get("status", "Present")
        
    cal = calendar.Calendar(firstweekday=0) # Monday first
    month_days = cal.monthdatescalendar(year, month)
    
    # Pass summary too if we want
    att_summary = get_student_attendance_summary(g.user["id"])
    
    return render_template("intern/attendance.html",
                           month_days=month_days,
                           att_map=att_map,
                           current_month_name=calendar.month_name[month],
                           current_year=year,
                           today=today,
                           att_summary=att_summary)

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
    
    # Check if a report for today already exists
    existing_submissions = ss.get_submissions_for_student(g.user["id"])
    today_report = next((s for s in existing_submissions if str(s.get("task_id")) == virtual_task_id), None)
    
    if today_report:
        ss.update_submission(today_report["submission_id"], "", notes_json, "submitted")
        logger.info("AUDIT: Intern %s updated daily report for %s", g.user["id"], date_str)
        flash("Daily report updated successfully! ✅", "success")
    else:
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
            
    current_month_prefix = datetime.now(timezone.utc).strftime("%Y-%m")
    days_taken_this_month = 0
    for l in approved_leaves:
        if l.get("start_date", "").startswith(current_month_prefix):
            try:
                days_taken_this_month += int(l.get("days_requested", 0))
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
        
        manager = supa.get_profile(manager_id)
        host_url = request.host_url.rstrip("/")
        manager_email = manager.get("email") if manager else None
        
        if not manager_email:
            logger.error("Cannot send leave request email — manager %s has no email on file", manager_id)
        else:
            try:
                success = send_leave_request_notification(manager_email, g.user["name"], leave_record["leave_id"], start_date, end_date, reason, host_url)
                if not success:
                    logger.error("Failed to send leave request email to manager %s", manager_id)
            except Exception as e:
                logger.error("Exception sending leave request email to manager %s: %s", manager_id, str(e))
            
        flash("Leave request submitted successfully.", "success")
        return redirect(url_for("intern.leave"))
        
    all_leaves.sort(key=lambda l: l.get("start_date", ""), reverse=True)
    return render_template("intern/leave.html", leaves=all_leaves, total_allotted=total_allotted, used_days=used_days, remaining_days=remaining_days, days_taken_this_month=days_taken_this_month)

@intern_bp.route("/leave/<leave_id>/withdraw", methods=["POST"])
@intern_required
def withdraw_leave(leave_id):
    from services.sheets_service import get_leaves_for_student, update_leave
    all_leaves = get_leaves_for_student(g.user["id"])
    leave = next((l for l in all_leaves if str(l["leave_id"]) == str(leave_id)), None)
    
    if not leave:
        flash("Leave request not found.", "error")
        return redirect(url_for("intern.leave"))
        
    if leave["status"] != "pending":
        flash("You can only withdraw pending leave requests.", "error")
        return redirect(url_for("intern.leave"))
        
    try:
        update_leave(leave_id, "withdrawn", g.user["id"], "Withdrawn by intern.")
        logger.info("AUDIT: Intern %s withdrew leave request %s", g.user["id"], leave_id)
        flash("Leave request withdrawn successfully.", "success")
    except Exception as e:
        logger.error("Failed to withdraw leave: %s", e)
        flash("Error withdrawing leave request.", "error")
        
    return redirect(url_for("intern.leave"))


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

@intern_bp.route("/performance/acknowledge/<report_id>", methods=["POST"])
@intern_required
def acknowledge_performance(report_id):
    report = next((r for r in ss.get_performance_reports_for_student(g.user["id"]) if r["report_id"] == report_id), None)
    if not report:
        flash("Report not found.", "error")
        return redirect(url_for("intern.performance"))
        
    updates = {
        "intern_acknowledged": "True",
        "intern_ack_date": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    }
    
    ss.update_performance_report(report_id, updates)
    flash("Report acknowledged.", "success")
    return redirect(url_for("intern.performance"))
