"""
routes/manager.py — Manager routes
"""
import logging
import json
from datetime import datetime, timezone
from flask import Blueprint, flash, redirect, render_template, request, url_for, g

from services import sheets_service as ss
from services import supabase_service as supa
from services.auth_helpers import manager_required
from services.attendance_service import get_manager_summary

manager_bp = Blueprint("manager", __name__)
logger = logging.getLogger(__name__)

@manager_bp.route("/dashboard")
@manager_required
def dashboard():
    summary = get_manager_summary(g.user["id"])
    interns = supa.get_profiles_by_manager(g.user["id"])
    return render_template("manager/dashboard.html", summary=summary, students=interns)


@manager_bp.route("/attendance")
@manager_required
def attendance():
    interns = supa.get_profiles_by_manager(g.user["id"])
    
    # Fetch requested date or default to today
    selected_date_str = request.args.get("date", "").strip()
    if not selected_date_str:
        selected_date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        
    todays_attendance = ss.get_attendance_for_date(selected_date_str)
    
    for intern in interns:
        # Check attendance
        att = next((a for a in todays_attendance if a["intern_id"] == intern["id"]), None)
        intern["today_status"] = att["status"] if att else "pending"
        
        # Get report specifically for the selected date
        subs = ss.get_submissions_for_student(intern["id"])
        daily_sub = None
        if subs:
            # Look for a submission with task_id == REPORT-{selected_date_str} OR submitted on that date
            for s in subs:
                if s["task_id"] == f"REPORT-{selected_date_str}" or s["submitted_at"][:10] == selected_date_str:
                    daily_sub = s
                    break
            
        if daily_sub:
            try:
                daily_sub["report_data"] = json.loads(daily_sub.get("notes", "{}"))
            except:
                daily_sub["report_data"] = {"given": "Unknown", "done": daily_sub.get("notes", ""), "remaining": "Unknown"}
            intern["latest_report"] = daily_sub
        else:
            intern["latest_report"] = None

    return render_template("manager/attendance.html", students=interns, today=selected_date_str)


@manager_bp.route("/attendance/mark", methods=["POST"])
@manager_required
def mark_attendance():
    intern_id = request.form.get("student_id", "").strip()
    status = request.form.get("status", "").strip() # 'present', 'absent', or 'on_leave'
    date_str = request.form.get("date", "").strip()
    
    if not date_str:
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        
    if not intern_id or status not in ['present', 'absent', 'on_leave']:
        flash("Invalid attendance data.", "error")
        return redirect(url_for("manager.attendance", date=date_str))
        
    # Verify manager owns this intern
    intern = supa.get_profile(intern_id)
    if not intern or (intern.get("manager_id") != g.user["id"] and g.user_role != "admin"):
        flash("Access denied.", "error")
        return redirect(url_for("manager.attendance", date=date_str))
        
    # Check if there is a daily report for this date
    subs = ss.get_submissions_for_student(intern_id)
    has_report = any(s["task_id"] == f"REPORT-{date_str}" or s["submitted_at"][:10] == date_str for s in subs)

    # Upsert attendance
    department = intern.get("department", "Unknown")
    ss.upsert_attendance(intern_id, department, date_str, status, "manager_override", "daily", f"Marked by {g.user['name']}")
    logger.info("AUDIT: Manager %s marked attendance %s for intern %s on %s", g.user["id"], status, intern_id, date_str)
    
    flash_msg = f"Attendance marked as {status.upper()} for {intern['name']} on {date_str}."
    
    # Auto-issue warning if absent and no report
    if status == 'absent' and not has_report:
        reason = f"Marked absent and no daily report submitted for {date_str}."
        ss.create_warning(intern_id, department, date_str, reason, issued_by="system")
        logger.info("AUDIT: System auto-issued warning for intern %s on %s", intern_id, date_str)
        flash_msg += " (Warning auto-issued for missing report)"
    elif status == 'present':
        from services.email_service import send_attendance_approval_notification
        if intern.get("email"):
            send_attendance_approval_notification(intern["email"], intern.get("name", "Intern"), date_str)
        
    flash(flash_msg, "success")
    return redirect(url_for("manager.attendance", date=date_str))


@manager_bp.route("/interns/<intern_id>")
@manager_required
def student_detail(intern_id):
    intern = supa.get_profile(intern_id)
    if not intern or (intern.get("manager_id") != g.user["id"] and g.user_role != "admin"):
        flash("Access denied.", "error")
        return redirect(url_for("manager.dashboard"))

    from services.attendance_service import get_student_attendance_summary
    att_summary = get_student_attendance_summary(intern_id)
    warnings = ss.get_warnings_for_student(intern_id)
    submissions = ss.get_submissions_for_student(intern_id)
    perf_reports = ss.get_performance_reports_for_student(intern_id)
    
    # Parse JSON notes if possible
    for sub in submissions:
        try:
            sub["report_data"] = json.loads(sub.get("notes", "{}"))
        except:
            sub["report_data"] = {"given": "Unknown", "done": sub.get("notes", ""), "remaining": "Unknown"}

    return render_template("manager/student_detail.html",
                           student=intern, att_summary=att_summary,
                           warnings=warnings, submissions=submissions,
                           perf_reports=perf_reports)


@manager_bp.route("/warnings/issue", methods=["POST"])
@manager_required
def issue_warning():
    intern_id = request.form.get("student_id", "")
    reason = request.form.get("reason", "").strip()
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    if not intern_id or not reason:
        flash("Intern and reason are required.", "error")
        return redirect(request.referrer or url_for("manager.dashboard"))

    intern = supa.get_profile(intern_id)
    if not intern or (intern.get("manager_id") != g.user["id"] and g.user_role != "admin"):
        flash("Access denied.", "error")
        return redirect(url_for("manager.dashboard"))

    ss.create_warning(intern_id, intern.get("department", "Unknown"), date_str, reason, issued_by=g.user["name"])
    logger.info("AUDIT: Manager %s issued warning for intern %s", g.user["id"], intern_id)
    flash("Warning issued.", "success")
    return redirect(request.referrer or url_for("manager.dashboard"))


@manager_bp.route("/performance/issue", methods=["POST"])
@manager_required
def issue_performance():
    intern_id = request.form.get("student_id", "")
    report_type = request.form.get("report_type", "").strip()
    rating = request.form.get("rating", "").strip()
    discipline = request.form.get("discipline", "").strip()
    feedback = request.form.get("feedback", "").strip()

    if not intern_id or not report_type or not rating or not feedback:
        flash("All fields are required.", "error")
        return redirect(request.referrer or url_for("manager.dashboard"))

    intern = supa.get_profile(intern_id)
    if not intern or (intern.get("manager_id") != g.user["id"] and g.user_role != "admin"):
        flash("Access denied.", "error")
        return redirect(url_for("manager.dashboard"))

    ss.create_performance_report(intern_id, g.user["id"], report_type, rating, discipline, feedback)
    logger.info("AUDIT: Manager %s issued performance report for intern %s", g.user["id"], intern_id)
    flash("Performance report issued.", "success")
    return redirect(request.referrer or url_for("manager.dashboard"))


@manager_bp.route("/leaves")
@manager_required
def leaves():
    leaves_list = ss.get_leaves_for_manager(g.user["id"])
    # Sort pending first, then by date descending
    leaves_list.sort(key=lambda l: (0 if l["status"] == "pending" else 1, l.get("start_date", "")), reverse=True)
    
    # Map intern names
    for l in leaves_list:
        intern = supa.get_profile(l["intern_id"])
        l["student_name"] = intern["name"] if intern else "Unknown Intern"
        
    return render_template("manager/leaves.html", leaves=leaves_list)


@manager_bp.route("/leaves/<leave_id>")
@manager_required
def leave_detail(leave_id):
    leave = ss.get_leave_by_id(leave_id)
    if not leave or leave["manager_id"] != g.user["id"]:
        flash("Leave request not found or access denied.", "error")
        return redirect(url_for("manager.leaves"))
        
    intern = supa.get_profile(leave["intern_id"])
    leave["student_name"] = intern["name"] if intern else "Unknown Intern"
    
    return render_template("manager/leave_detail.html", leave=leave)


@manager_bp.route("/leaves/<leave_id>/decide", methods=["POST"])
@manager_required
def decide_leave(leave_id):
    from services.email_service import send_leave_decision_notification
    
    leave = ss.get_leave_by_id(leave_id)
    if not leave or leave["manager_id"] != g.user["id"]:
        flash("Leave request not found or access denied.", "error")
        return redirect(url_for("manager.leaves"))
        
    status = request.form.get("status", "").strip()
    remarks = request.form.get("remarks", "").strip()
    
    if status not in ["approved", "rejected"]:
        flash("Invalid status.", "error")
        return redirect(url_for("manager.leave_detail", leave_id=leave_id))
        
    ss.update_leave_status(leave_id, status, decided_by=g.user["name"], remarks=remarks)
    logger.info("AUDIT: Manager %s %s leave %s", g.user["id"], status, leave_id)
    
    # Send email (In real app, we would fetch the user's email via auth API if possible)
    # For now we'll pass placeholder if it doesn't exist in profile
    intern = supa.get_profile(leave["intern_id"])
    host_url = request.host_url.rstrip("/")
    # Using dummy emails since profiles no longer stores email
    intern_email = "intern@example.com"
    send_leave_decision_notification(intern_email, intern.get("name", ""), status, leave["start_date"], leave["end_date"], remarks, host_url)
        
    flash(f"Leave request has been {status}.", "success")
    return redirect(url_for("manager.leaves"))


@manager_bp.route("/reports")
@manager_required
def reports():
    reports_list = ss.get_reports_for_manager(g.user["id"])
    reports_list.sort(key=lambda r: (0 if not r["reviewed_by"] else 1, r.get("submitted_at", "")), reverse=True)
    
    for r in reports_list:
        intern = supa.get_profile(r["intern_id"])
        r["student_name"] = intern["name"] if intern else "Unknown Intern"
        
    return render_template("manager/reports.html", reports=reports_list)


@manager_bp.route("/reports/<report_id>/review", methods=["POST"])
@manager_required
def review_report(report_id):
    notes = request.form.get("notes", "").strip()
    if not notes:
        flash("Review notes cannot be empty.", "error")
        return redirect(url_for("manager.reports"))
        
    report = ss.get_report_by_id(report_id)
    if not report or report["manager_id"] != g.user["id"]:
        flash("Report not found or access denied.", "error")
        return redirect(url_for("manager.reports"))
        
    ss.review_report(report_id, g.user["name"], notes)
    flash("Report marked as reviewed.", "success")
    return redirect(url_for("manager.reports"))
