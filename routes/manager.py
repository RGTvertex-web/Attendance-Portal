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
        
    from services.email_service import send_attendance_notification
    # We pass the dummy email for now since profile doesn't have email in this version, 
    # but theoretically intern.get("email", "intern@example.com") would be used.
    # The requirement didn't specify where to get the email from.
    intern_email = intern.get("email", "intern@example.com")
    send_attendance_notification(intern_email, intern.get("name", "Intern"), date_str, status, g.user["name"], department)
        
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

@manager_bp.route("/performance", methods=["GET", "POST"])
@manager_required
def performance():
    interns = supa.get_profiles_by_manager(g.user["id"])
    if request.method == "POST":
        intern_id = request.form.get("intern_id")
        week_start = request.form.get("week_start")
        week_end = request.form.get("week_end")
        work_quality = int(request.form.get("work_quality", 0))
        task_completion = int(request.form.get("task_completion", 0))
        learning_ability = int(request.form.get("learning_ability", 0))
        teamwork = int(request.form.get("teamwork", 0))
        discipline = int(request.form.get("discipline", 0))
        behaviour = int(request.form.get("behaviour", 0))
        overall = int(request.form.get("overall", 0))
        
        strengths = request.form.get("strengths", "")
        areas_improvement = request.form.get("areas_improvement", "")
        overall_comments = request.form.get("overall_comments", "")
        
        total_score = work_quality + task_completion + learning_ability + teamwork + discipline + behaviour + overall
        
        if total_score >= 90:
            grade_band = "Outstanding"
        elif total_score >= 80:
            grade_band = "Excellent"
        elif total_score >= 70:
            grade_band = "Good"
        elif total_score >= 60:
            grade_band = "Satisfactory"
        else:
            grade_band = "Needs Improvement"
            
        ss.create_performance_report(
            intern_id, g.user["id"], week_start, week_end,
            work_quality, task_completion, learning_ability,
            teamwork, discipline, behaviour, overall,
            total_score, grade_band, strengths, areas_improvement, overall_comments
        )
        flash("Weekly performance report submitted successfully.", "success")
        return redirect(url_for("manager.performance"))
        
    reports = ss.get_performance_reports_for_manager(g.user["id"])
    return render_template("manager/performance.html", interns=interns, reports=reports)
