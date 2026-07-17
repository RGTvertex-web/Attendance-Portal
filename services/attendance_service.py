"""
services/attendance_service.py
───────────────────────────────
Attendance evaluation engine.

Called by:
  - APScheduler daily job (scheduler.py)
  - Admin manual trigger route

At-Risk rule: 3 consecutive absences OR 3 absences in rolling 7-day window
(per task category, so a student can be at-risk in one category but not another)
"""

import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

import pytz

from config import AT_RISK_CONSECUTIVE, AT_RISK_ROLLING_COUNT, AT_RISK_ROLLING_WINDOW, UTC
from services import sheets_service as ss
from services import supabase_service as supa

logger = logging.getLogger(__name__)


def evaluate_attendance_for_date(target_date: Optional[datetime] = None) -> Dict:
    """
    Main daily job. Evaluates all active tasks whose due_date falls on target_date
    (UTC date), marks attendance for each assigned student, creates warnings for
    absences, and checks At-Risk status.

    Returns a summary dict with counts.
    """
    if target_date is None:
        target_date = datetime.now(UTC)

    date_str = target_date.strftime("%Y-%m-%d")
    logger.info("=== Attendance evaluation for %s ===", date_str)

    all_tasks = ss.get_all_tasks()
    all_profiles = supa.get_all_profiles()
    active_students = {u["id"]: u for u in all_profiles
                       if u.get("role") == "student" and u.get("status") in ("active", "at_risk")}

    summary = {"date": date_str, "evaluated": 0, "present": 0,
               "present_late": 0, "absent": 0, "warnings_created": 0, "at_risk_flagged": 0}

    all_leaves = ss.get_all_leaves()

    due_today = []
    for task in all_tasks:
        due_raw = task.get("due_date", "")
        if not due_raw:
            continue
        try:
            if "T" in due_raw:
                due_dt = datetime.fromisoformat(due_raw.replace("Z", "+00:00"))
            else:
                due_dt = datetime.strptime(due_raw, "%Y-%m-%d").replace(tzinfo=UTC)
            if due_dt.strftime("%Y-%m-%d") == date_str:
                due_today.append((task, due_dt))
        except ValueError:
            logger.warning("Could not parse due_date '%s' for task %s", due_raw, task["task_id"])

    if not due_today:
        logger.info("No tasks due on %s — nothing to evaluate", date_str)
        return summary

    for task, due_dt in due_today:
        task_id = task["task_id"]
        category = task.get("category", "General")
        assigned_to = task.get("assigned_to", "")

        if assigned_to == "all":
            target_students = list(active_students.values())
        elif assigned_to in active_students:
            target_students = [active_students[assigned_to]]
        else:
            target_students = [s for s in active_students.values()
                                if s.get("manager_id") == assigned_to]

        for student in target_students:
            student_id = student["id"]
            submission = ss.get_submission(task_id, student_id)
            summary["evaluated"] += 1

            if submission:
                submitted_at_raw = submission.get("submitted_at", "")
                try:
                    submitted_dt = datetime.fromisoformat(submitted_at_raw.replace("Z", "+00:00"))
                except ValueError:
                    submitted_dt = None

                if submitted_dt and submitted_dt <= due_dt:
                    att_status = "present"
                    sub_status = "submitted"
                    summary["present"] += 1
                else:
                    att_status = "present_late"
                    sub_status = "late"
                    summary["present_late"] += 1

                ss.update_submission(submission["submission_id"], status=sub_status)
            else:
                # Check if on approved leave
                is_on_leave = any(
                    l["student_id"] == student_id and 
                    l["status"] == "approved" and 
                    l["start_date"] <= date_str <= l["end_date"]
                    for l in all_leaves
                )
                
                if is_on_leave:
                    att_status = "on_leave"
                    # We do NOT create a warning. We do NOT increment absent.
                else:
                    att_status = "absent"
                    summary["absent"] += 1
                    reason = f"No submission for task '{task['title']}' (category: {category}) due {date_str}"
                    ss.create_warning(student_id, date_str, reason, issued_by="system")
                    summary["warnings_created"] += 1

            ss.upsert_attendance(
                student_id=student_id,
                date_str=date_str,
                status=att_status,
                category=category,
                linked_task_id=task_id,
            )

            if _check_and_flag_at_risk(student_id, category):
                summary["at_risk_flagged"] += 1

    logger.info("Evaluation complete: %s", summary)
    return summary


def _check_and_flag_at_risk(student_id: str, category: str) -> bool:
    attendance = [
        a for a in ss.get_attendance_for_student(student_id)
        if a.get("category") == category
    ]

    try:
        attendance.sort(key=lambda x: x["date"], reverse=True)
    except Exception:
        return False

    if not attendance:
        return False

    consecutive = 0
    for record in attendance:
        if record["status"] == "absent":
            consecutive += 1
            if consecutive >= AT_RISK_CONSECUTIVE:
                logger.warning("AUDIT: Student %s flagged At-Risk (consecutive) in %s", student_id, category)
                supa.update_profile(student_id, status="at_risk")
                return True
        else:
            break

    cutoff = (datetime.now(UTC) - timedelta(days=AT_RISK_ROLLING_WINDOW)).strftime("%Y-%m-%d")
    recent_absences = sum(
        1 for a in attendance
        if a["status"] == "absent" and a["date"] >= cutoff
    )
    if recent_absences >= AT_RISK_ROLLING_COUNT:
        logger.warning("AUDIT: Student %s flagged At-Risk (rolling) in %s", student_id, category)
        supa.update_profile(student_id, status="at_risk")
        return True

    return False


def get_attendance_percentage(student_id: str, days: int = 30) -> float:
    cutoff = (datetime.now(UTC) - timedelta(days=days)).strftime("%Y-%m-%d")
    records = [a for a in ss.get_attendance_for_student(student_id) if a["date"] >= cutoff]
    if not records:
        return 0.0
    present_count = sum(1 for a in records if a["status"] in ("present", "present_late"))
    return round((present_count / len(records)) * 100, 1)


def get_student_attendance_summary(student_id: str) -> Dict:
    records = ss.get_attendance_for_student(student_id)
    total = len(records)
    present = sum(1 for a in records if a["status"] == "present")
    late = sum(1 for a in records if a["status"] == "present_late")
    absent = sum(1 for a in records if a["status"] == "absent")
    on_leave = sum(1 for a in records if a["status"] == "on_leave")
    percentage = get_attendance_percentage(student_id)
    return {
        "total": total, "present": present, "late": late,
        "absent": absent, "on_leave": on_leave, "percentage": percentage,
        "records": sorted(records, key=lambda x: x["date"], reverse=True),
    }


def get_org_summary() -> Dict:
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    all_att = ss.get_all_attendance()
    today_records = [a for a in all_att if a["date"] == today]

    all_profiles = supa.get_all_profiles()
    total_students = len([u for u in all_profiles if u.get("role") == "student" and u.get("status") != "inactive"])
    at_risk = [u for u in all_profiles if u.get("status") == "at_risk"]
    warnings = ss.get_all_warnings()

    today_present = sum(1 for a in today_records if a["status"] in ("present", "present_late"))
    today_absent = sum(1 for a in today_records if a["status"] == "absent")
    today_on_leave = sum(1 for a in today_records if a["status"] == "on_leave")

    return {
        "total_students": total_students,
        "today_present": today_present,
        "today_absent": today_absent,
        "today_on_leave": today_on_leave,
        "at_risk_students": at_risk,
        "total_warnings": len(warnings),
        "unack_warnings": len(ss.get_unacknowledged_warnings()),
    }


def get_manager_summary(manager_id: str) -> Dict:
    students = supa.get_profiles_by_manager(manager_id)
    student_ids = {s["id"] for s in students}
    today = datetime.now(UTC).strftime("%Y-%m-%d")

    today_att = {a["intern_id"]: a["status"]
                 for a in ss.get_attendance_for_date(today)
                 if a["intern_id"] in student_ids}

    at_risk = [s for s in students if s.get("status") == "at_risk"]
    pending = ss.get_pending_submissions_for_manager(manager_id, student_ids)

    student_summaries = []
    for s in students:
        student_summaries.append({
            **s,
            "attendance_pct": get_attendance_percentage(s["id"]),
            "today_status": today_att.get(s["id"], "—"),
            "warnings": len(ss.get_warnings_for_student(s["id"])),
        })

    return {
        "students": student_summaries,
        "at_risk": at_risk,
        "pending_tasks": pending,
        "total_students": len(students),
    }
