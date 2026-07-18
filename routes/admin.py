"""
routes/admin.py — Admin-only routes
"""
import logging
from datetime import datetime, timezone
from flask import Blueprint, flash, redirect, render_template, request, url_for, g

from services import sheets_service as ss
from services import supabase_service as supa
from services.email_service import send_manager_invite_email
from services.auth_helpers import admin_required
from services.attendance_service import evaluate_attendance_for_date, get_org_summary
from config import DEPARTMENTS

admin_bp = Blueprint("admin", __name__)
logger = logging.getLogger(__name__)

VALID_ROLES = ("admin", "manager", "intern")
VALID_STATUSES = ("active", "inactive")

# ── Dashboard ─────────────────────────────────────────────────────────────────
@admin_bp.route("/dashboard")
@admin_required
def dashboard():
    department = request.args.get("department", "")
    
    from services.attendance_service import get_org_summary, get_attendance_trend_for_target, get_org_performance_analytics
    org = get_org_summary(department=department if department else None)
    managers = supa.get_all_managers()
    
    # Filter managers if department selected
    if department:
        managers = [m for m in managers if m.get("department") == department]
        
    all_warnings = ss.get_all_warnings()
    if department:
        # We need to filter warnings by department. 
        all_warnings = [w for w in all_warnings if w.get("department") == department]
    recent_warnings = sorted(all_warnings, key=lambda w: w["date"], reverse=True)[:10]
    
    # Filter trend data
    all_users = supa.get_all_profiles()
    if department:
        dept_intern_ids = {u["id"] for u in all_users if u.get("role") == "intern" and u.get("department") == department}
        trend_data = get_attendance_trend_for_target(dept_intern_ids)
    else:
        trend_data = get_attendance_trend_for_target(None)
        
    perf_analytics = get_org_performance_analytics(department=department if department else None)
    
    # Calculate department-wise intern numbers
    all_users = supa.get_all_profiles()
    dept_stats = {}
    for u in all_users:
        if u.get("role") == "intern":
            d = u.get("department") or "Unknown"
            dept_stats[d] = dept_stats.get(d, 0) + 1
            
    return render_template("admin/dashboard.html",
                           org=org, managers=managers,
                           recent_warnings=recent_warnings,
                           dept_stats=dept_stats,
                           trend=trend_data,
                           perf_analytics=perf_analytics,
                           department_filter=department)


# ── Users ─────────────────────────────────────────────────────────────────────
@admin_bp.route("/users")
@admin_required
def users():
    all_users = supa.get_all_profiles()
    role_filter = request.args.get("role", "")
    status_filter = request.args.get("status", "")
    department_filter = request.args.get("department", "")
    
    if role_filter:
        all_users = [u for u in all_users if u.get("role") == role_filter]
    if status_filter:
        all_users = [u for u in all_users if u.get("status") == status_filter]
    if department_filter:
        all_users = [u for u in all_users if u.get("department") == department_filter]
        
    managers = [u for u in supa.get_all_profiles() if u.get("role") in ("manager", "admin") and u.get("status") == "active"]
    return render_template("admin/users.html", users=all_users, managers=managers,
                           role_filter=role_filter, status_filter=status_filter, department_filter=department_filter)


@admin_bp.route("/users/create", methods=["GET", "POST"])
@admin_required
def create_user():
    managers = supa.get_all_managers()
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        role = request.form.get("role", "intern")
        department = request.form.get("department", "")
        manager_id = request.form.get("manager_id", "")
        duration = request.form.get("internship_duration_months", "")

        errors = _validate_user_form(name, email, password, role)

        if errors:
            for e in errors:
                flash(e, "error")
            return render_template("admin/user_form.html", managers=managers,
                                   action="create", form_data=request.form)

        try:
            supa.sign_up(email, password, name, role, department, manager_id, duration if role == "intern" else None)
            logger.info("AUDIT: Admin %s created user %s role=%s", g.user["id"], email, role)
            flash(f"User '{name}' created successfully.", "success")
            return redirect(url_for("admin.users"))
        except Exception as e:
            flash(f"Failed to create user: {str(e)}", "error")
            return render_template("admin/user_form.html", managers=managers,
                                   action="create", form_data=request.form)

    return render_template("admin/user_form.html", managers=managers,
                           action="create", form_data={})


@admin_bp.route("/users/<user_id>/edit", methods=["GET", "POST"])
@admin_required
def edit_user(user_id):
    user_data = supa.get_profile(user_id)
    if not user_data:
        flash("User not found.", "error")
        return redirect(url_for("admin.users"))
        
    managers = supa.get_all_managers()

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        role = request.form.get("role", user_data.get("role"))
        department = request.form.get("department", user_data.get("department"))
        manager_id = request.form.get("manager_id", "")
        status = request.form.get("status", user_data.get("status"))

        updates = {"name": name, "role": role, "department": department, "manager_id": manager_id if manager_id else None, "status": status}
        
        try:
            supa.update_profile(user_id, **updates)
            logger.info("AUDIT: Admin %s edited user %s", g.user["id"], user_id)
            if role != user_data.get("role"):
                logger.info("AUDIT: Admin %s escalated user %s role from %s to %s", g.user["id"], user_id, user_data.get("role"), role)
            flash("User updated.", "success")
            return redirect(url_for("admin.users"))
        except Exception as e:
            flash(f"Failed to update user: {str(e)}", "error")

    return render_template("admin/user_form.html", managers=managers,
                           action="edit", form_data=user_data, user_id=user_id)


@admin_bp.route("/users/<user_id>/deactivate", methods=["POST"])
@admin_required
def deactivate_user(user_id):
    if user_id == g.user["id"]:
        flash("You cannot deactivate your own account.", "warning")
        return redirect(url_for("admin.users"))
    
    try:
        supa.delete_user(user_id)
        
        # Also remove from Google Sheets
        try:
            from services import sheets_service as ss
            ss.delete_user_from_sheet(user_id)
        except Exception as e:
            logger.error("Failed to delete user from sheets: %s", str(e))
            
        logger.info("AUDIT: Admin %s deleted user %s", g.user["id"], user_id)
        flash("User permanently deleted.", "success")
    except Exception as e:
        flash(f"Failed to deactivate user: {str(e)}", "error")
        
    return redirect(url_for("admin.users"))


# ── Invites ───────────────────────────────────────────────────────────────────
@admin_bp.route("/managers/invite", methods=["GET", "POST"])
@admin_required
def invite_manager():
    departments = DEPARTMENTS
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        department = request.form.get("department", "")

        if not email or department not in departments:
            flash("Valid email and department are required.", "error")
            return redirect(url_for("admin.invite_manager"))

        import secrets
        token = secrets.token_urlsafe(32)
        
        try:
            ss.create_invite(email, department, token, g.user["id"])
            host_url = request.host_url.rstrip("/")
            send_manager_invite_email(email, token, department, host_url)
            logger.info("AUDIT: Admin %s created manager invite for %s (dept: %s)", g.user["id"], email, department)
            flash(f"Invite sent successfully to {email}.", "success")
            return redirect(url_for("admin.users"))
        except Exception as e:
            flash(f"Failed to create invite: {str(e)}", "error")
            return redirect(url_for("admin.invite_manager"))

    return render_template("admin/invite_manager.html", departments=departments)


# ── Global Attendance & Reports ───────────────────────────────────────────────
@admin_bp.route("/attendance")
@admin_required
def attendance():
    # Fetch requested date or default to today
    selected_date_str = request.args.get("date", "").strip()
    if not selected_date_str:
        selected_date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        
    import json
    interns = [u for u in supa.get_all_profiles() if u.get("role") == "intern"]
    todays_attendance = ss.get_attendance_for_date(selected_date_str)
    
    for intern in interns:
        # Check attendance
        att = next((a for a in todays_attendance if a["intern_id"] == intern["id"]), None)
        intern["today_status"] = att["status"] if att else "pending"
        
        # Get report specifically for the selected date
        subs = ss.get_submissions_for_student(intern["id"])
        daily_sub = None
        if subs:
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

    return render_template("admin/attendance.html", students=interns, today=selected_date_str)


@admin_bp.route("/attendance/mark", methods=["POST"])
@admin_required
def mark_attendance():
    intern_id = request.form.get("student_id", "").strip()
    status = request.form.get("status", "").strip() # 'present', 'absent', or 'on_leave'
    date_str = request.form.get("date", "").strip()
    
    if not date_str:
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        
    if not intern_id or status not in ['present', 'absent', 'on_leave']:
        flash("Invalid attendance data.", "error")
        return redirect(url_for("admin.attendance", date=date_str))
        
    intern = supa.get_profile(intern_id)
    if not intern:
        flash("Intern not found.", "error")
        return redirect(url_for("admin.attendance", date=date_str))
        
    # Check if there is a daily report for this date
    subs = ss.get_submissions_for_student(intern_id)
    has_report = any(s["task_id"] == f"REPORT-{date_str}" or s["submitted_at"][:10] == date_str for s in subs)

    department = intern.get("department", "Unknown")
    ss.upsert_attendance(intern_id, department, date_str, status, "admin_override", "daily", f"Marked by {g.user['name']} (Admin)")
    logger.info("AUDIT: Admin %s marked attendance %s for intern %s on %s", g.user["id"], status, intern_id, date_str)
    
    flash_msg = f"Attendance marked as {status.upper()} for {intern['name']} on {date_str}."
    
    # Auto-issue warning if absent and no report
    if status == 'absent' and not has_report:
        reason = f"Marked absent and no daily report submitted for {date_str}."
        ss.create_warning(intern_id, department, date_str, reason, issued_by="system")
        logger.info("AUDIT: System auto-issued warning for intern %s on %s", intern_id, date_str)
        flash_msg += " (Warning auto-issued for missing report)"
        
    flash(flash_msg, "success")
    return redirect(url_for("admin.attendance", date=date_str))


# ── Attendance Override (Legacy) ──────────────────────────────────────────────
@admin_bp.route("/attendance/override", methods=["POST"])
@admin_required
def override_attendance():
    intern_id = request.form.get("student_id", "")
    date_str = request.form.get("date", "")
    linked_task_id = request.form.get("linked_task_id", "")
    new_status = request.form.get("new_status", "")
    notes = request.form.get("notes", "")

    allowed_statuses = ("present", "present_late", "absent", "on_leave")
    if new_status not in allowed_statuses:
        flash("Invalid status for override.", "error")
        return redirect(request.referrer or url_for("admin.dashboard"))

    success = ss.override_attendance(intern_id, date_str, linked_task_id,
                                     new_status, g.user["id"], notes)
    if success:
        logger.info("AUDIT: Admin %s overrode attendance intern=%s date=%s → %s",
                    g.user["id"], intern_id, date_str, new_status)
        flash("Attendance overridden.", "success")
    else:
        flash("Attendance record not found.", "error")
    return redirect(request.referrer or url_for("admin.dashboard"))


# ── Manual Attendance Trigger ─────────────────────────────────────────────────
@admin_bp.route("/trigger-attendance", methods=["POST"])
@admin_required
def trigger_attendance():
    date_str = request.form.get("date", "")
    try:
        if date_str:
            target = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        else:
            target = datetime.now(timezone.utc)
    except ValueError:
        flash("Invalid date format.", "error")
        return redirect(url_for("admin.dashboard"))

    summary = evaluate_attendance_for_date(target)
    logger.info("AUDIT: Admin %s manually triggered attendance for %s", g.user["id"], summary["date"])
    flash(f"Attendance evaluated for {summary['date']}: "
          f"{summary['present']} present, {summary['absent']} absent, "
          f"{summary['warnings_created']} warnings created.", "success")
    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/leaves")
@admin_required
def leaves():
    leaves_list = ss.get_all_leaves()
    leaves_list.sort(key=lambda l: (0 if l["status"] == "pending" else 1, l.get("start_date", "")), reverse=True)
    
    for l in leaves_list:
        intern = supa.get_profile(l["intern_id"])
        l["student_name"] = intern["name"] if intern else "Unknown Intern"
        
    return render_template("admin/leaves.html", leaves=leaves_list)


@admin_bp.route("/leaves/<leave_id>")
@admin_required
def leave_detail(leave_id):
    leave = ss.get_leave_by_id(leave_id)
    if not leave:
        flash("Leave request not found.", "error")
        return redirect(url_for("admin.leaves"))
        
    intern = supa.get_profile(leave["intern_id"])
    leave["student_name"] = intern["name"] if intern else "Unknown Intern"
    
    return render_template("admin/leave_detail.html", leave=leave)


@admin_bp.route("/leaves/<leave_id>/decide", methods=["POST"])
@admin_required
def decide_leave(leave_id):
    from services.email_service import send_leave_decision_notification
    
    leave = ss.get_leave_by_id(leave_id)
    if not leave:
        flash("Leave request not found.", "error")
        return redirect(url_for("admin.leaves"))
        
    status = request.form.get("status", "").strip()
    remarks = request.form.get("remarks", "").strip()
    
    if status not in ["approved", "rejected"]:
        flash("Invalid status.", "error")
        return redirect(url_for("admin.leave_detail", leave_id=leave_id))
        
    ss.update_leave_status(leave_id, status, decided_by=g.user["name"], remarks=remarks)
    logger.info("AUDIT: Admin %s %s leave %s", g.user["id"], status, leave_id)
    
    intern = supa.get_profile(leave["intern_id"])
    intern_email = intern.get("email", "intern@example.com")
    send_leave_decision_notification(intern_email, intern.get("name", ""), status, leave["start_date"], leave["end_date"], remarks, g.user["name"])
        
    flash(f"Leave request has been {status}.", "success")
    return redirect(url_for("admin.leaves"))


@admin_bp.route("/reports")
@admin_required
def reports():
    reports_list = ss.get_all_reports()
    reports_list.sort(key=lambda r: (0 if not r["reviewed_by"] else 1, r.get("submitted_at", "")), reverse=True)
    
    for r in reports_list:
        intern = supa.get_profile(r["intern_id"])
        r["student_name"] = intern["name"] if intern else "Unknown Intern"
        
    return render_template("admin/reports.html", reports=reports_list)

import io
from flask import make_response

@admin_bp.route("/exports/<report_type>/<format>")
@admin_required
def export_data(report_type, format):
    if report_type not in ["performance", "attendance", "leaves"]:
        flash("Invalid export type.", "error")
        return redirect(url_for("admin.dashboard"))
        
    dept_filter = request.args.get("department", "").strip()
    manager_filter = request.args.get("manager_id", "").strip()
    date_filter = request.args.get("date", "").strip()
        
    data = []
    if report_type == "performance":
        data = ss.get_all_performance_reports()
        if date_filter:
            # Filter by week_start or week_end
            data = [d for d in data if d.get("week_start") == date_filter or d.get("week_end") == date_filter]
    elif report_type == "attendance":
        if date_filter:
            data = ss.get_attendance_for_date(date_filter)
        else:
            data = ss.get_all_attendance()
    elif report_type == "leaves":
        data = ss.get_all_leaves()
        if date_filter:
            data = [d for d in data if d.get("start_date") <= date_filter <= d.get("end_date")]
    
    # Filter by department or manager if applicable
    if data and (dept_filter or manager_filter):
        all_users = supa.get_all_profiles()
        user_map = {u["id"]: u for u in all_users}
        filtered_data = []
        for d in data:
            intern = user_map.get(d.get("intern_id"))
            if not intern:
                continue
            if dept_filter and intern.get("department") != dept_filter:
                continue
            if manager_filter and intern.get("manager_id") != manager_filter:
                continue
            filtered_data.append(d)
        data = filtered_data
    
    if not data:
        flash("No data available to export with the given filters.", "warning")
        return redirect(url_for("admin.dashboard"))
        
    headers = list(data[0].keys())
    
    if format == "csv":
        import csv
        si = io.StringIO()
        cw = csv.DictWriter(si, fieldnames=headers)
        cw.writeheader()
        cw.writerows(data)
        output = make_response(si.getvalue())
        output.headers["Content-Disposition"] = f"attachment; filename={report_type}.csv"
        output.headers["Content-type"] = "text/csv"
        return output
        
    elif format == "excel":
        try:
            import pandas as pd
            df = pd.DataFrame(data)
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, index=False, sheet_name='Sheet1')
            response = make_response(output.getvalue())
            response.headers["Content-Disposition"] = f"attachment; filename={report_type}.xlsx"
            response.headers["Content-type"] = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            return response
        except ImportError:
            flash("Excel export requires pandas and openpyxl.", "error")
            return redirect(url_for("admin.dashboard"))
            
    elif format == "pdf":
        try:
            from reportlab.lib.pagesizes import letter
            from reportlab.pdfgen import canvas
            buffer = io.BytesIO()
            p = canvas.Canvas(buffer, pagesize=letter)
            p.drawString(100, 750, f"RGTvertex {report_type.title()} Report")
            y = 700
            for row in data:
                line = " | ".join([f"{str(v)[:20]}" for v in row.values()])
                p.drawString(50, y, line)
                y -= 20
                if y < 50:
                    p.showPage()
                    y = 750
            p.save()
            response = make_response(buffer.getvalue())
            response.headers["Content-Disposition"] = f"attachment; filename={report_type}.pdf"
            response.headers["Content-type"] = "application/pdf"
            return response
        except ImportError:
            flash("PDF export requires reportlab.", "error")
            return redirect(url_for("admin.dashboard"))
            
    flash("Invalid format.", "error")
    return redirect(url_for("admin.dashboard"))

def _validate_user_form(name, email, password, role):
    errors = []
    if not name:
        errors.append("Name is required.")
    if not email or "@" not in email:
        errors.append("Valid email is required.")
    if not password or len(password) < 8:
        errors.append("Password must be at least 8 characters.")
    if role not in VALID_ROLES:
        errors.append("Invalid role.")
    return errors
