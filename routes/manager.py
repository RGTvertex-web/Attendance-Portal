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
from services.attendance_service import get_manager_summary, get_attendance_trend_for_target

manager_bp = Blueprint("manager", __name__)
logger = logging.getLogger(__name__)

@manager_bp.route("/dashboard")
@manager_required
def dashboard():
    summary = get_manager_summary(g.user["id"])
    interns = supa.get_profiles_by_manager(g.user["id"])
    intern_ids = {s["id"] for s in interns}
    trend_data = get_attendance_trend_for_target(intern_ids) if intern_ids else {"labels": ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"], "values": [0,0,0,0,0,0,0]}
    return render_template("manager/dashboard.html", summary=summary, students=interns, trend=trend_data)


@manager_bp.route("/attendance")
@manager_required
def attendance():
    interns = supa.get_profiles_by_manager(g.user["id"])
    
    # Fetch requested date or default to today
    selected_date_str = request.args.get("date", "").strip()
    if not selected_date_str:
        selected_date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        
    try:
        selected_dt = datetime.strptime(selected_date_str, "%Y-%m-%d")
        is_weekend = selected_dt.weekday() >= 5
    except ValueError:
        is_weekend = False
        
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

    return render_template("manager/attendance.html", students=interns, today=selected_date_str, is_weekend=is_weekend)


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
    intern_email = intern.get("email")
    if not intern_email:
        logger.error("Cannot send attendance email — intern %s has no email on file", intern_id)
    else:
        try:
            success = send_attendance_notification(intern_email, intern.get("name", "Intern"), date_str, status, g.user["name"], department)
            if not success:
                logger.error("Failed to send attendance email to intern %s", intern_id)
        except Exception as e:
            logger.error("Exception sending attendance email to intern %s: %s", intern_id, str(e))
        
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

    manager_notes = ss.get_manager_notes(intern_id)

    return render_template("manager/student_detail.html",
                           student=intern, att_summary=att_summary,
                           warnings=warnings, submissions=submissions,
                           perf_reports=perf_reports, manager_notes=manager_notes)

@manager_bp.route("/interns/<intern_id>/notes", methods=["POST"])
@manager_required
def add_manager_note(intern_id):
    intern = supa.get_profile(intern_id)
    if not intern or (intern.get("manager_id") != g.user["id"] and g.user_role != "admin"):
        flash("Access denied.", "error")
        return redirect(url_for("manager.dashboard"))
        
    note_content = request.form.get("note", "").strip()
    if not note_content:
        flash("Note cannot be empty.", "error")
    else:
        ss.create_manager_note(intern_id, g.user["id"], note_content)
        flash("Note added.", "success")
        
    return redirect(url_for("manager.student_detail", intern_id=intern_id))


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

@manager_bp.route("/warnings/<warning_id>/revoke", methods=["POST"])
@manager_required
def revoke_warning_route(warning_id):
    # Verify manager owns the warning (or is admin)
    all_warnings = ss.get_all_warnings()
    warning = next((w for w in all_warnings if w["warning_id"] == warning_id), None)
    
    if not warning:
        flash("Warning not found.", "error")
        return redirect(request.referrer or url_for("manager.dashboard"))
        
    if warning["issued_by"] != g.user["name"] and g.user_role != "admin":
        flash("You can only revoke warnings that you issued.", "error")
        return redirect(request.referrer or url_for("manager.dashboard"))
        
    ss.revoke_warning(warning_id, g.user["name"])
    flash("Warning revoked.", "success")
    return redirect(request.referrer or url_for("manager.dashboard"))



@manager_bp.route("/leaves")
@manager_required
def leaves():
    leaves_list = ss.get_leaves_for_manager(g.user["id"])
    # Sort pending first, then by date descending
    leaves_list.sort(key=lambda l: (0 if l["status"] == "pending" else 1, l.get("start_date", "")), reverse=True)
    
    # Map intern names and calculate leave balance
    for l in leaves_list:
        intern = supa.get_profile(l["intern_id"])
        if intern:
            l["student_name"] = intern["name"]
            try:
                allotted = int(intern.get("leave_allotted_days", 0))
            except ValueError:
                allotted = 0
                
            intern_leaves = ss.get_leaves_for_student(l["intern_id"])
            used = sum(float(il.get("days_count", 0)) for il in intern_leaves if il["status"] == "approved")
            l["leave_balance"] = f"{allotted - used:g} / {allotted}"
        else:
            l["student_name"] = "Unknown Intern"
            l["leave_balance"] = "—"
            
    return render_template("manager/leaves.html", leaves=leaves_list)


@manager_bp.route("/leaves/<leave_id>")
@manager_required
def leave_detail(leave_id):
    leave = ss.get_leave_by_id(leave_id)
    if not leave:
        flash("Leave request not found.", "error")
        return redirect(url_for("manager.leaves"))
        
    intern = supa.get_profile(leave["intern_id"])
    if not intern or (intern.get("manager_id") != g.user["id"] and g.user_role != "admin"):
        flash("Access denied.", "error")
        return redirect(url_for("manager.leaves"))
        
    leave["student_name"] = intern["name"] if intern else "Unknown Intern"
    return render_template("manager/leave_detail.html", leave=leave)


@manager_bp.route("/leaves/<leave_id>/decide", methods=["POST"])
@manager_required
def decide_leave(leave_id):
    from services.email_service import send_leave_decision_notification
    
    leave = ss.get_leave_by_id(leave_id)
    if not leave:
        flash("Leave request not found.", "error")
        return redirect(url_for("manager.leaves"))
        
    intern = supa.get_profile(leave["intern_id"])
    if not intern or (intern.get("manager_id") != g.user["id"] and g.user_role != "admin"):
        flash("Access denied.", "error")
        return redirect(url_for("manager.leaves"))
        
    status = request.form.get("status", "").strip()
    remarks = request.form.get("remarks", "").strip()
    
    if status not in ["approved", "rejected"]:
        flash("Invalid status.", "error")
        return redirect(url_for("manager.leave_detail", leave_id=leave_id))
        
    ss.update_leave_status(leave_id, status, decided_by=g.user["name"], remarks=remarks)
    logger.info("AUDIT: Manager %s %s leave %s", g.user["id"], status, leave_id)
    
    intern_email = intern.get("email")
    if not intern_email:
        logger.error("Cannot send leave decision email — intern %s has no email on file", intern["id"])
    else:
        try:
            success = send_leave_decision_notification(intern_email, intern.get("name", ""), status, leave["start_date"], leave["end_date"], remarks, g.user["name"])
            if not success:
                logger.error("Failed to send leave decision email to intern %s", intern["id"])
        except Exception as e:
            logger.error("Exception sending leave decision email to intern %s: %s", intern["id"], str(e))
        
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

@manager_bp.route("/performance", methods=["GET", "POST"])
@manager_required
def performance():
    interns = supa.get_profiles_by_manager(g.user["id"])
    if request.method == "POST":
        intern_id = request.form.get("intern_id")
        period_start = request.form.get("period_start")
        period_end = request.form.get("period_end")
        
        # New 7 criteria (scored out of 10)
        technical_skill = int(request.form.get("technical_skill", 0))
        communication = int(request.form.get("communication", 0))
        discipline = int(request.form.get("discipline", 0))
        task_completion = int(request.form.get("task_completion", 0))
        initiative = int(request.form.get("initiative", 0))
        teamwork = int(request.form.get("teamwork", 0))
        code_quality = int(request.form.get("code_quality", 0))
        
        strengths = request.form.get("strengths", "")
        areas_improvement = request.form.get("areas_improvement", "")
        overall_comments = request.form.get("overall_comments", "")
        
        total_score = technical_skill + communication + discipline + task_completion + initiative + teamwork + code_quality
        percentage = (total_score / 70.0) * 100
        
        if percentage >= 90:
            grade_band = "Outstanding"
        elif percentage >= 80:
            grade_band = "Excellent"
        elif percentage >= 70:
            grade_band = "Good"
        elif percentage >= 60:
            grade_band = "Satisfactory"
        else:
            grade_band = "Needs Improvement"
            
        ss.create_performance_report(
            intern_id, g.user["id"], period_start, period_end,
            technical_skill, communication, discipline, task_completion,
            initiative, teamwork, code_quality,
            total_score, grade_band, strengths, areas_improvement, overall_comments
        )
        flash("Monthly performance report submitted successfully.", "success")
        return redirect(url_for("manager.performance"))
        
    reports = ss.get_performance_reports_for_manager(g.user["id"])
    return render_template("manager/performance.html", interns=interns, reports=reports)

@manager_bp.route("/performance/edit/<report_id>", methods=["POST"])
@manager_required
def edit_performance(report_id):
    # Only process edits within 7 days or if edit_reason is provided
    report = next((r for r in ss.get_performance_reports_for_manager(g.user["id"]) if r["report_id"] == report_id), None)
    if not report:
        flash("Report not found.", "error")
        return redirect(url_for("manager.performance"))
        
    created_at = datetime.fromisoformat(report["submitted_at"].replace("Z", "+00:00"))
    days_old = (datetime.now(timezone.utc) - created_at).days
    
    edit_reason = request.form.get("edit_reason", "").strip()
    if days_old > 7 and not edit_reason:
        flash("Reports older than 7 days require an Amendment Reason.", "error")
        return redirect(url_for("manager.performance"))
        
    technical_skill = int(request.form.get("technical_skill", report["technical_skill"]))
    communication = int(request.form.get("communication", report["communication"]))
    discipline = int(request.form.get("discipline", report["discipline"]))
    task_completion = int(request.form.get("task_completion", report["task_completion"]))
    initiative = int(request.form.get("initiative", report["initiative"]))
    teamwork = int(request.form.get("teamwork", report["teamwork"]))
    code_quality = int(request.form.get("code_quality", report["code_quality"]))
    
    total_score = technical_skill + communication + discipline + task_completion + initiative + teamwork + code_quality
    percentage = (total_score / 70.0) * 100
    
    if percentage >= 90:
        grade_band = "Outstanding"
    elif percentage >= 80:
        grade_band = "Excellent"
    elif percentage >= 70:
        grade_band = "Good"
    elif percentage >= 60:
        grade_band = "Satisfactory"
    else:
        grade_band = "Needs Improvement"
        
    updates = {
        "technical_skill": technical_skill,
        "communication": communication,
        "discipline": discipline,
        "task_completion": task_completion,
        "initiative": initiative,
        "teamwork": teamwork,
        "code_quality": code_quality,
        "total_score": total_score,
        "grade_band": grade_band,
        "strengths": request.form.get("strengths", report["strengths"]),
        "areas_improvement": request.form.get("areas_improvement", report["areas_improvement"]),
        "overall_comments": request.form.get("overall_comments", report["overall_comments"]),
        "edit_reason": edit_reason
    }
    
    ss.update_performance_report(report_id, updates)
    flash("Report updated successfully.", "success")
    return redirect(url_for("manager.performance"))

# ══════════════════════════════════════════════════════════════════════════════
# TASK MANAGEMENT
# ══════════════════════════════════════════════════════════════════════════════

@manager_bp.route("/tasks")
@manager_required
def tasks():
    tasks_list = ss.get_tasks_by_manager(g.user["id"])
    interns = supa.get_profiles_by_manager(g.user["id"])
    
    # Get all submissions to cross-reference
    all_subs = ss.get_all_submissions()
    
    # Map tasks with submission counts and details
    for t in tasks_list:
        subs = [s for s in all_subs if s["task_id"] == t["task_id"]]
        t["submission_count"] = len(subs)
            
    # Need categories for the template dropdown
    from config import TASK_CATEGORIES
    return render_template("manager/tasks.html", tasks=tasks_list, students=interns, categories=TASK_CATEGORIES)

@manager_bp.route("/tasks/create", methods=["POST"])
@manager_required
def create_task():
    title = request.form.get("title", "").strip()
    description = request.form.get("description", "").strip()
    category = request.form.get("category", "Project Task").strip()
    assigned_to = request.form.get("assigned_to", "All").strip()
    due_date = request.form.get("due_date", "").strip()
    
    if not title or not due_date:
        flash("Title and Due Date are required.", "error")
        return redirect(url_for("manager.tasks"))
        
    department = g.user.get("department", "Unknown")
    
    try:
        ss.create_task(
            title=title,
            description=description,
            category=category,
            department=department,
            assigned_to=assigned_to,
            assigned_by=g.user["id"],
            due_date=due_date
        )
        flash("Task created successfully.", "success")
    except Exception as e:
        logger.error(f"Failed to create task: {e}")
        flash(f"Failed to create task: {e}", "error")
        
    return redirect(url_for("manager.tasks"))

@manager_bp.route("/tasks/<task_id>/update", methods=["POST"])
@manager_required
def update_task(task_id):
    # E.g. allowing manager to close/delete or extend due date.
    # We will implement extending due date or closing here.
    action = request.form.get("action")
    if action == "delete":
        # We don't have hard delete right now, but we can set a status if we add one to the schema.
        # Actually, let's just allow extending due date for now.
        new_date = request.form.get("due_date")
        if new_date:
            ss.update_task(task_id, due_date=new_date)
            flash("Task due date updated.", "success")
    
    return redirect(url_for("manager.tasks"))

