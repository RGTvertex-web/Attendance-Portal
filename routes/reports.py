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

TASK_CATEGORIES = ["Daily Log", "Weekly Deliverable", "CTF Challenge", "Project Milestone", "Other"]

@reports_bp.route("/")
@manager_required
def index():
    student_id = request.args.get("student_id", "")
    category = request.args.get("category", "")
    date_from = request.args.get("date_from", "")
    date_to = request.args.get("date_to", "")

    if g.user_role == "admin":
        students = [u for u in supa.get_all_profiles() if u.get("role") == "student"]
    else:
        students = supa.get_profiles_by_manager(g.user["id"])

    student_ids = {s["id"] for s in students}
    student_map = {s["id"]: s["name"] for s in students}

    all_att = ss.get_all_attendance()
    records = [a for a in all_att if a.get("intern_id") in student_ids]

    if student_id:
        records = [r for r in records if r.get("intern_id") == student_id]
    if category:
        records = [r for r in records if r["category"] == category]
    if date_from:
        records = [r for r in records if r["date"] >= date_from]
    if date_to:
        records = [r for r in records if r["date"] <= date_to]

    for r in records:
        r["student_name"] = student_map.get(r.get("intern_id"), r.get("intern_id"))

    records.sort(key=lambda x: x["date"], reverse=True)

    return render_template("reports/index.html",
                           records=records, students=students,
                           categories=TASK_CATEGORIES,
                           filters={"student_id": student_id, "category": category,
                                    "date_from": date_from, "date_to": date_to})


@reports_bp.route("/export")
@manager_required
def export_csv():
    student_id = request.args.get("student_id", "")
    category = request.args.get("category", "")
    date_from = request.args.get("date_from", "")
    date_to = request.args.get("date_to", "")

    if g.user_role == "admin":
        students = [u for u in supa.get_all_profiles() if u.get("role") == "student"]
    else:
        students = supa.get_profiles_by_manager(g.user["id"])

    student_ids = {s["id"] for s in students}
    student_map = {s["id"]: s["name"] for s in students}

    all_att = ss.get_all_attendance()
    records = [a for a in all_att if a.get("intern_id") in student_ids]

    if student_id:
        records = [r for r in records if r.get("intern_id") == student_id]
    if category:
        records = [r for r in records if r["category"] == category]
    if date_from:
        records = [r for r in records if r["date"] >= date_from]
    if date_to:
        records = [r for r in records if r["date"] <= date_to]

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["attendance_id", "intern_id", "student_name", "date",
                     "status", "category", "linked_task_id", "marked_at", "notes"])
    for r in sorted(records, key=lambda x: x["date"], reverse=True):
        writer.writerow([
            r.get("attendance_id", ""), r.get("intern_id", ""),
            student_map.get(r.get("intern_id"), ""), r.get("date", ""),
            r.get("status", ""), r.get("category", ""),
            r.get("linked_task_id", ""), r.get("marked_at", ""), r.get("notes", ""),
        ])

    logger.info("AUDIT: %s exported attendance report (student=%s category=%s %s→%s)",
                g.user["id"], student_id, category, date_from, date_to)

    filename = f"attendance_report_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment;filename={filename}"},
    )
