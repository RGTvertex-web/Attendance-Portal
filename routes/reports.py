"""
routes/reports.py — Filterable reports + CSV export
"""
import csv
import io
import logging
from datetime import datetime, timezone
from flask import Blueprint, Response, flash, redirect, render_template, request, url_for, g

from services import sheets_service as ss
from services import supabase_service as supa
from services.auth_helpers import manager_required

reports_bp = Blueprint("reports", __name__)
logger = logging.getLogger(__name__)


@reports_bp.route("/")
@manager_required
def index():
    student_id = request.args.get("student_id", "")
    department = request.args.get("department", "")
    status = request.args.get("status", "")
    date_from = request.args.get("date_from", "")
    date_to = request.args.get("date_to", "")

    if g.user_role == "admin":
        students = [u for u in supa.get_all_profiles() if u.get("role") == "intern"]
    else:
        students = supa.get_profiles_by_manager(g.user["id"])

    if department:
        students = [s for s in students if s.get("department") == department]

    student_ids = {s["id"] for s in students}
    student_map = {s["id"]: s["name"] for s in students}

    all_att = ss.get_all_attendance()
    records = [a for a in all_att if a.get("intern_id") in student_ids]

    if student_id:
        records = [r for r in records if r.get("intern_id") == student_id]
    if status:
        records = [r for r in records if r.get("status") == status]
    if date_from:
        records = [r for r in records if r["date"] >= date_from]
    if date_to:
        records = [r for r in records if r["date"] <= date_to]

    for r in records:
        r["student_name"] = student_map.get(r.get("intern_id"), r.get("intern_id"))

    records.sort(key=lambda x: x["date"], reverse=True)

    return render_template("reports/index.html",
                           records=records, students=students,
                           statuses=["present", "absent", "on_leave"],
                           filters={"student_id": student_id, "department": department, "status": status,
                                    "date_from": date_from, "date_to": date_to})


@reports_bp.route("/export")
@manager_required
def export_csv():
    student_id = request.args.get("student_id", "")
    department = request.args.get("department", "")
    status = request.args.get("status", "")
    date_from = request.args.get("date_from", "")
    date_to = request.args.get("date_to", "")

    if g.user_role == "admin":
        students = [u for u in supa.get_all_profiles() if u.get("role") == "intern"]
    else:
        students = supa.get_profiles_by_manager(g.user["id"])

    if department:
        students = [s for s in students if s.get("department") == department]

    student_ids = {s["id"] for s in students}
    student_map = {s["id"]: s["name"] for s in students}

    all_att = ss.get_all_attendance()
    records = [a for a in all_att if a.get("intern_id") in student_ids]

    if student_id:
        records = [r for r in records if r.get("intern_id") == student_id]
    if status:
        records = [r for r in records if r.get("status") == status]
    if date_from:
        records = [r for r in records if r["date"] >= date_from]
    if date_to:
        records = [r for r in records if r["date"] <= date_to]

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["attendance_id", "intern_id", "Intern Name", "date",
                     "status", "category", "linked_task_id", "marked_at", "notes"])
    for r in sorted(records, key=lambda x: x["date"], reverse=True):
        writer.writerow([
            r.get("attendance_id", ""), r.get("intern_id", ""),
            student_map.get(r.get("intern_id"), ""), r.get("date", ""),
            r.get("status", ""), r.get("category", ""),
            r.get("linked_task_id", ""), r.get("marked_at", ""), r.get("notes", ""),
        ])

    logger.info("AUDIT: %s exported attendance report (student=%s dept=%s %s→%s)",
                g.user["id"], student_id, department, date_from, date_to)

    filename = f"attendance_report_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment;filename={filename}"},
    )

@reports_bp.route("/performance/export/<report_id>")
@manager_required
def export_performance(report_id):
    # Actually, let's just get it from all performance reports
    all_perf = ss.get_all_performance_reports()
    report = next((r for r in all_perf if r["report_id"] == report_id), None)
    
    if not report:
        flash("Performance report not found.", "error")
        return redirect(request.referrer or url_for("manager.performance"))
        
    # Check access
    if g.user_role != "admin" and report["manager_id"] != g.user["id"] and report["intern_id"] != g.user["id"]:
        flash("Access denied.", "error")
        return redirect(url_for("manager.dashboard"))
        
    intern = supa.get_profile(report["intern_id"])
    manager = supa.get_profile(report["manager_id"])
    
    return render_template("reports/performance_print.html", report=report, intern=intern, manager=manager)
