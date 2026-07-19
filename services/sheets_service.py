

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from functools import lru_cache
from threading import Lock
from typing import Any, Dict, List, Optional

import gspread
from google.oauth2.service_account import Credentials

logger = logging.getLogger(__name__)

# ── Column maps (0-indexed) ────────────────────────────────────────────────────
_TASKS_COLS = {
    "task_id": 0, "title": 1, "description": 2, "category": 3,
    "department": 4, "assigned_to": 5, "assigned_by": 6, "due_date": 7, "created_at": 8,
}
_SUBMISSIONS_COLS = {
    "submission_id": 0, "task_id": 1, "intern_id": 2, "submitted_at": 3,
    "status": 4, "content_link": 5, "notes": 6, "remarks": 7,
}
_ATTENDANCE_COLS = {
    "attendance_id": 0, "intern_id": 1, "department": 2, "date": 3, "status": 4,
    "category": 5, "linked_task_id": 6, "marked_at": 7, "notes": 8,
}
_WARNINGS_COLS = {
    "warning_id": 0, "intern_id": 1, "department": 2, "date": 3, "reason": 4,
    "issued_by": 5, "acknowledged": 6, "status": 7
}
_LEAVES_COLS = {
    "leave_id": 0, "intern_id": 1, "department": 2, "manager_id": 3, "start_date": 4,
    "end_date": 5, "days_requested": 6, "reason": 7, "status": 8, "decided_by": 9,
    "decided_at": 10, "remarks": 11,
}
_REPORTS_COLS = {
    "report_id": 0, "intern_id": 1, "department": 2, "manager_id": 3,
    "report_type": 4, "period_start": 5, "period_end": 6, "content": 7,
    "submitted_at": 8, "reviewed_by": 9, "review_notes": 10, "reviewed_at": 11,
}
_MANAGER_NOTES_COLS = {
    "note_id": 0, "intern_id": 1, "manager_id": 2, "timestamp": 3, "content": 4,
}
_PERFORMANCE_COLS = {
    "report_id": 0, "intern_id": 1, "manager_id": 2, "period_start": 3, "period_end": 4,
    "work_quality": 5, "old_task_completion": 6, "learning_ability": 7, "old_teamwork": 8, "old_discipline": 9, "behaviour": 10, "overall": 11,
    "total_score": 12, "grade_band": 13, "strengths": 14, "areas_improvement": 15, "overall_comments": 16, "submitted_at": 17,
    "edit_reason": 18, "intern_acknowledged": 19, "intern_ack_date": 20,
    "technical_skill": 21, "communication": 22, "discipline": 23, "task_completion": 24, "initiative": 25, "teamwork": 26, "code_quality": 27
}
_INVITES_COLS = {
    "invite_id": 0, "email": 1, "department": 2, "role": 3, "token": 4, 
    "invited_by": 5, "created_at": 6, "expires_at": 7, "used": 8,
}

SHEET_HEADERS = {
    "Users":       ["id", "email", "password", "name", "role", "department", "manager_id", "internship_duration_months", "leave_allotted_days", "status", "created_at", "reset_token", "reset_token_expires_at"],
    "Tasks":       ["task_id", "title", "description", "category", "department", "assigned_to", "assigned_by", "due_date", "created_at"],
    "Submissions": ["submission_id", "task_id", "intern_id", "submitted_at", "status", "content_link", "notes", "remarks"],
    "Attendance":  ["attendance_id", "intern_id", "department", "date", "status", "category", "linked_task_id", "marked_at", "notes"],
    "Warnings":    ["warning_id", "intern_id", "department", "date", "reason", "issued_by", "acknowledged", "status"],
    "Leaves":      ["leave_id", "intern_id", "department", "manager_id", "start_date", "end_date", "days_requested", "reason", "status", "decided_by", "decided_at", "remarks"],
    "Reports":     ["report_id", "intern_id", "department", "manager_id", "report_type", "period_start", "period_end", "content", "submitted_at", "reviewed_by", "review_notes", "reviewed_at"],
    "Performance": ["report_id", "intern_id", "manager_id", "period_start", "period_end", "work_quality", "old_task_completion", "learning_ability", "old_teamwork", "old_discipline", "behaviour", "overall", "total_score", "grade_band", "strengths", "areas_improvement", "overall_comments", "submitted_at", "edit_reason", "intern_acknowledged", "intern_ack_date", "technical_skill", "communication", "discipline", "task_completion", "initiative", "teamwork", "code_quality"],
    "Invites":     ["invite_id", "email", "department", "role", "token", "invited_by", "created_at", "expires_at", "used"],
    "ManagerNotes": ["note_id", "intern_id", "manager_id", "timestamp", "content"],
    "Holidays":    ["date", "name"],
    "Settings":    ["key", "value"],
    "AuditLog":    ["timestamp", "actor_id", "action", "details"],
}

_HOLIDAYS_COLS = {"date": 0, "name": 1}
_SETTINGS_COLS = {"key": 0, "value": 1}
_AUDIT_COLS = {"timestamp": 0, "actor_id": 1, "action": 2, "details": 3}

_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# Thread-safe client singleton
_client: Optional[gspread.Client] = None
_client_lock = Lock()


def _get_client() -> gspread.Client:
    global _client
    with _client_lock:
        if _client is None:
            creds_json = os.environ.get("GOOGLE_CREDENTIALS_JSON")
            if not creds_json:
                raise RuntimeError("GOOGLE_CREDENTIALS_JSON env var not set")
            creds_info = json.loads(creds_json)
            creds = Credentials.from_service_account_info(creds_info, scopes=_SCOPES)
            _client = gspread.authorize(creds)
            logger.info("Google Sheets client initialised")
    return _client


_spreadsheet: Optional[gspread.Spreadsheet] = None
_spreadsheet_lock = Lock()

def _get_spreadsheet() -> gspread.Spreadsheet:
    global _spreadsheet
    if _spreadsheet is None:
        with _spreadsheet_lock:
            if _spreadsheet is None:
                spreadsheet_id = os.environ.get("SPREADSHEET_ID")
                if not spreadsheet_id:
                    raise RuntimeError("SPREADSHEET_ID env var not set")
                _spreadsheet = _get_client().open_by_key(spreadsheet_id)
    return _spreadsheet


def _get_sheet(name: str) -> gspread.Worksheet:
    return _get_spreadsheet().worksheet(name)


def _rows_to_dicts(rows: List[List[str]], col_map: Dict[str, int]) -> List[Dict[str, Any]]:
    """Convert raw row list to list of dicts using column map."""
    result = []
    for row in rows:
        # Pad short rows
        padded = row + [""] * (max(col_map.values()) + 1 - len(row))
        result.append({key: padded[idx] for key, idx in col_map.items()})
    return result


def _now_utc_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _new_id() -> str:
    return str(uuid.uuid4())


# ══════════════════════════════════════════════════════════════════════════════
# USERS
# ══════════════════════════════════════════════════════════════════════════════

def add_user_to_sheet(user_dict: Dict) -> None:
    try:
        sheet = _get_sheet("Users")
        row = [
            str(user_dict.get("id", "")),
            str(user_dict.get("email", "")),
            str(user_dict.get("password", "")),
            str(user_dict.get("name", "")),
            str(user_dict.get("role", "")),
            str(user_dict.get("department", "")),
            str(user_dict.get("manager_id", "")),
            str(user_dict.get("internship_duration_months", "")),
            str(user_dict.get("leave_allotted_days", "")),
            str(user_dict.get("status", "")),
            str(user_dict.get("created_at", _now_utc_str())),
            str(user_dict.get("reset_token", "")),
            str(user_dict.get("reset_token_expires_at", ""))
        ]
        try:
            sheet.append_row(row, value_input_option="RAW")
            logger.info("Added user %s to Users sheet", user_dict.get("id"))
        except Exception as e:
            logger.error(f"Failed to add user {user_dict.get('id')} to Sheets: {str(e)}")
            raise ValueError(f"Could not save user to Google Sheets. Please try again later.")
    except Exception as e:
        logger.error(f"Failed to append user to Sheets: {e}")

def delete_user_from_sheet(user_id: str) -> bool:
    try:
        sheet = _get_sheet("Users")
        all_rows = sheet.get_all_values()
        for i, row in enumerate(all_rows[1:], start=2):
            if row[0] == user_id:  # id is index 0
                sheet.delete_rows(i)
                logger.info("Deleted user %s from Users sheet", user_id)
                return True
        return False
    except Exception as e:
        logger.error(f"Error deleting user from sheet: {e}")
        return False

# ══════════════════════════════════════════════════════════════════════════════
# TASKS
# ══════════════════════════════════════════════════════════════════════════════

def get_all_tasks() -> List[Dict]:
    from flask import g, has_app_context
    if has_app_context() and hasattr(g, '_all_tasks'):
        return g._all_tasks

    sheet = _get_sheet("Tasks")
    rows = sheet.get_all_values()[1:]
    res = _rows_to_dicts(rows, _TASKS_COLS)
    
    if has_app_context():
        g._all_tasks = res
    return res


def get_task_by_id(task_id: str) -> Optional[Dict]:
    for t in get_all_tasks():
        if t["task_id"] == task_id:
            return t
    return None


def get_tasks_for_student(intern_id: str, department: str) -> List[Dict]:
    """Return tasks assigned to this intern or to 'all' in their department."""
    return [t for t in get_all_tasks()
            if t["department"] == department and t["assigned_to"] in (intern_id, "all")]


def get_tasks_by_manager(manager_id: str) -> List[Dict]:
    return [t for t in get_all_tasks() if t["assigned_by"] == manager_id]


def create_task(title: str, description: str, category: str, department: str,
                assigned_to: str, assigned_by: str, due_date: str) -> Dict:
    sheet = _get_sheet("Tasks")
    task_id = _new_id()
    row = [task_id, title.strip(), description.strip(), category.strip(), department,
           assigned_to, assigned_by, due_date, _now_utc_str()]
    sheet.append_row(row, value_input_option="RAW")
    logger.info("Created task %s '%s' due=%s", task_id, title, due_date)
    return get_task_by_id(task_id)


def update_task(task_id: str, **fields) -> bool:
    sheet = _get_sheet("Tasks")
    all_rows = sheet.get_all_values()
    for i, row in enumerate(all_rows[1:], start=2):
        if row[_TASKS_COLS["task_id"]] == task_id:
            for field, value in fields.items():
                if field in _TASKS_COLS:
                    sheet.update_cell(i, _TASKS_COLS[field] + 1, value)
            return True
    return False


# ══════════════════════════════════════════════════════════════════════════════
# SUBMISSIONS
# ══════════════════════════════════════════════════════════════════════════════

def get_all_submissions() -> List[Dict]:
    from flask import g, has_app_context
    if has_app_context() and hasattr(g, '_all_submissions'):
        return g._all_submissions

    sheet = _get_sheet("Submissions")
    rows = sheet.get_all_values()[1:]
    res = _rows_to_dicts(rows, _SUBMISSIONS_COLS)

    if has_app_context():
        g._all_submissions = res
    return res


def get_submission(task_id: str, intern_id: str) -> Optional[Dict]:
    for s in get_all_submissions():
        if s["task_id"] == task_id and s["intern_id"] == intern_id:
            return s
    return None


def get_submissions_for_student(intern_id: str) -> List[Dict]:
    return [s for s in get_all_submissions() if s["intern_id"] == intern_id]


def get_submissions_for_task(task_id: str) -> List[Dict]:
    return [s for s in get_all_submissions() if s["task_id"] == task_id]


def get_pending_submissions_for_manager(manager_id: str, intern_ids: set) -> List[Dict]:
    """Return tasks where at least one intern hasn't submitted."""
    tasks = get_tasks_by_manager(manager_id)
    pending = []
    for task in tasks:
        subs = {s["intern_id"] for s in get_submissions_for_task(task["task_id"])}
        not_submitted = intern_ids - subs
        if not_submitted:
            task["missing_count"] = len(not_submitted)
            pending.append(task)
    return pending


def create_submission(task_id: str, intern_id: str, content_link: str,
                      notes: str, submitted_at: str, status: str) -> Dict:
    sheet = _get_sheet("Submissions")
    sub_id = _new_id()
    row = [sub_id, task_id, intern_id, submitted_at, status,
           content_link.strip(), notes.strip(), ""]
    sheet.append_row(row, value_input_option="RAW")
    logger.info("Submission %s task=%s intern=%s status=%s", sub_id, task_id, intern_id, status)
    return {"submission_id": sub_id, "task_id": task_id, "intern_id": intern_id,
            "submitted_at": submitted_at, "status": status, "content_link": content_link,
            "notes": notes, "remarks": ""}


def update_submission(submission_id: str, **fields) -> bool:
    sheet = _get_sheet("Submissions")
    all_rows = sheet.get_all_values()
    for i, row in enumerate(all_rows[1:], start=2):
        if row[_SUBMISSIONS_COLS["submission_id"]] == submission_id:
            for field, value in fields.items():
                if field in _SUBMISSIONS_COLS:
                    sheet.update_cell(i, _SUBMISSIONS_COLS[field] + 1, value)
            return True
    return False


# ══════════════════════════════════════════════════════════════════════════════
# ATTENDANCE
# ══════════════════════════════════════════════════════════════════════════════

def get_all_attendance() -> List[Dict]:
    from flask import g, has_app_context
    if has_app_context() and hasattr(g, '_all_attendance'):
        return g._all_attendance

    sheet = _get_sheet("Attendance")
    rows = sheet.get_all_values()[1:]
    res = _rows_to_dicts(rows, _ATTENDANCE_COLS)
    
    if has_app_context():
        g._all_attendance = res
    return res


def get_attendance_for_student(intern_id: str) -> List[Dict]:
    return [a for a in get_all_attendance() if a["intern_id"] == intern_id]


def get_attendance_for_date(date_str: str) -> List[Dict]:
    return [a for a in get_all_attendance() if a["date"] == date_str]


def upsert_attendance(intern_id: str, department: str, date_str: str, status: str,
                      category: str, linked_task_id: str, notes: str = "") -> Dict:
    """Insert or update a single attendance record."""
    sheet = _get_sheet("Attendance")
    all_rows = sheet.get_all_values()
    for i, row in enumerate(all_rows[1:], start=2):
        padded = row + [""] * 9
        if (padded[_ATTENDANCE_COLS["intern_id"]] == intern_id and
                padded[_ATTENDANCE_COLS["date"]] == date_str and
                padded[_ATTENDANCE_COLS["linked_task_id"]] == linked_task_id):
            # Update existing
            sheet.update_cell(i, _ATTENDANCE_COLS["status"] + 1, status)
            sheet.update_cell(i, _ATTENDANCE_COLS["marked_at"] + 1, _now_utc_str())
            sheet.update_cell(i, _ATTENDANCE_COLS["notes"] + 1, notes)
            logger.info("Updated attendance intern=%s date=%s status=%s", intern_id, date_str, status)
            return {"intern_id": intern_id, "date": date_str, "status": status}

    # Insert new
    att_id = _new_id()
    row = [att_id, intern_id, department, date_str, status, category,
           linked_task_id, _now_utc_str(), notes]
    sheet.append_row(row, value_input_option="RAW")
    logger.info("Inserted attendance intern=%s date=%s status=%s", intern_id, date_str, status)
    return {"attendance_id": att_id, "intern_id": intern_id, "date": date_str, "status": status}


def override_attendance(intern_id: str, date_str: str, linked_task_id: str,
                        new_status: str, admin_id: str, notes: str = "") -> bool:
    sheet = _get_sheet("Attendance")
    all_rows = sheet.get_all_values()
    for i, row in enumerate(all_rows[1:], start=2):
        padded = row + [""] * 9
        if (padded[_ATTENDANCE_COLS["intern_id"]] == intern_id and
                padded[_ATTENDANCE_COLS["date"]] == date_str and
                padded[_ATTENDANCE_COLS["linked_task_id"]] == linked_task_id):
            sheet.update_cell(i, _ATTENDANCE_COLS["status"] + 1, new_status)
            sheet.update_cell(i, _ATTENDANCE_COLS["marked_at"] + 1, _now_utc_str())
            sheet.update_cell(i, _ATTENDANCE_COLS["notes"] + 1, f"[Override by {admin_id}] {notes}")
            logger.info("AUDIT: Admin %s overrode attendance intern=%s date=%s → %s",
                        admin_id, intern_id, date_str, new_status)
            return True
    return False


# ══════════════════════════════════════════════════════════════════════════════
# WARNINGS
# ══════════════════════════════════════════════════════════════════════════════

def get_all_warnings() -> List[Dict]:
    from flask import g, has_app_context
    if has_app_context() and hasattr(g, '_all_warnings'):
        return g._all_warnings

    sheet = _get_sheet("Warnings")
    rows = sheet.get_all_values()[1:]
    res = _rows_to_dicts(rows, _WARNINGS_COLS)
    
    if has_app_context():
        g._all_warnings = res
    return res


def get_warnings_for_student(intern_id: str) -> List[Dict]:
    return [w for w in get_all_warnings() if w["intern_id"] == intern_id]


def get_unacknowledged_warnings() -> List[Dict]:
    return [w for w in get_all_warnings() if w["acknowledged"] != "yes"]


def create_warning(intern_id: str, department: str, date_str: str, reason: str,
                   issued_by: str = "system") -> Dict:
    sheet = _get_sheet("Warnings")
    warning_id = _new_id()
    row = [warning_id, intern_id, department, date_str, reason, issued_by, "no", "active"]
    try:
        sheet.append_row(row, value_input_option="RAW")
        logger.info("Warning created intern=%s reason=%s by=%s", intern_id, reason, issued_by)
    except Exception as e:
        logger.error(f"Failed to create warning for intern {intern_id}: {str(e)}")
        raise ValueError("Could not save warning to Google Sheets. Please try again later.")
        
    return {"warning_id": warning_id, "intern_id": intern_id, "date": date_str,
            "reason": reason, "issued_by": issued_by, "acknowledged": "no", "status": "active"}

def update_warning_status(warning_id: str, status: str, admin_id: str) -> bool:
    sheet = _get_sheet("Warnings")
    all_rows = sheet.get_all_values()
    for i, row in enumerate(all_rows[1:], start=2):
        if row[_WARNINGS_COLS["warning_id"]] == warning_id:
            sheet.update_cell(i, _WARNINGS_COLS["status"] + 1, status)
            logger.info("AUDIT: Admin %s changed warning %s status to %s", admin_id, warning_id, status)
            return True
    return False

def revoke_warning(warning_id: str, manager_id: str) -> bool:
    sheet = _get_sheet("Warnings")
    all_rows = sheet.get_all_values()
    for i, row in enumerate(all_rows[1:], start=2):
        if row[_WARNINGS_COLS["warning_id"]] == warning_id:
            # We can check if it was issued by this manager, but we do that in the route.
            sheet.update_cell(i, _WARNINGS_COLS["status"] + 1, "revoked")
            logger.info("AUDIT: Manager %s revoked warning %s", manager_id, warning_id)
            return True
    return False


def acknowledge_warning(warning_id: str) -> bool:
    sheet = _get_sheet("Warnings")
    all_rows = sheet.get_all_values()
    for i, row in enumerate(all_rows[1:], start=2):
        if row[_WARNINGS_COLS["warning_id"]] == warning_id:
            sheet.update_cell(i, _WARNINGS_COLS["acknowledged"] + 1, "yes")
            return True
    return False


# ══════════════════════════════════════════════════════════════════════════════
# LEAVES
# ══════════════════════════════════════════════════════════════════════════════

def get_all_leaves() -> List[Dict]:
    from flask import g, has_app_context
    if has_app_context() and hasattr(g, '_all_leaves'):
        return g._all_leaves

    try:
        sheet = _get_sheet("Leaves")
        rows = sheet.get_all_values()[1:]
        res = _rows_to_dicts(rows, _LEAVES_COLS)
        if has_app_context():
            g._all_leaves = res
        return res
    except Exception as e:
        logger.warning(f"Failed to fetch Leaves sheet. Have you created the 'Leaves' tab? Error: {e}")
        return []


def get_leaves_for_student(intern_id: str) -> List[Dict]:
    return [l for l in get_all_leaves() if l["intern_id"] == intern_id]


def get_leaves_for_manager(manager_id: str) -> List[Dict]:
    return [l for l in get_all_leaves() if l["manager_id"] == manager_id]


def get_leave_by_id(leave_id: str) -> Optional[Dict]:
    for l in get_all_leaves():
        if l["leave_id"] == leave_id:
            return l
    return None


def create_leave_request(intern_id: str, department: str, manager_id: str, start_date: str, end_date: str, days_requested: int, reason: str) -> Dict:
    try:
        sheet = _get_sheet("Leaves")
    except Exception as e:
        logger.error(f"Failed to access Leaves sheet: {e}")
        raise RuntimeError("Please create a 'Leaves' tab in your Google Sheet first.")
        
    leave_id = _new_id()
    row = [leave_id, intern_id, department, manager_id, start_date, end_date, str(days_requested), reason.strip(), "pending", "", "", ""]
    sheet.append_row(row, value_input_option="RAW")
    logger.info("Leave request created for intern=%s start=%s end=%s", intern_id, start_date, end_date)
    return {
        "leave_id": leave_id, "intern_id": intern_id, "manager_id": manager_id,
        "start_date": start_date, "end_date": end_date, "reason": reason,
        "status": "pending", "decided_by": "", "decided_at": "", "remarks": ""
    }


def update_leave_status(leave_id: str, status: str, decided_by: str, remarks: str = "") -> bool:
    try:
        sheet = _get_sheet("Leaves")
        all_rows = sheet.get_all_values()
        for i, row in enumerate(all_rows[1:], start=2):
            if row[_LEAVES_COLS["leave_id"]] == leave_id:
                sheet.update_cell(i, _LEAVES_COLS["status"] + 1, status)
                sheet.update_cell(i, _LEAVES_COLS["decided_by"] + 1, decided_by)
                sheet.update_cell(i, _LEAVES_COLS["decided_at"] + 1, _now_utc_str())
                sheet.update_cell(i, _LEAVES_COLS["remarks"] + 1, remarks)
                logger.info("Leave %s status updated to %s by %s", leave_id, status, decided_by)
                return True
    except Exception as e:
        logger.error(f"Failed to update leave status: {e}")
    return False

# ══════════════════════════════════════════════════════════════════════════════
# REPORTS
# ══════════════════════════════════════════════════════════════════════════════

def get_all_reports() -> List[Dict]:
    from flask import g, has_app_context
    if has_app_context() and hasattr(g, '_all_reports'):
        return g._all_reports

    try:
        sheet = _get_sheet("Reports")
        rows = sheet.get_all_values()[1:]
        res = _rows_to_dicts(rows, _REPORTS_COLS)
        if has_app_context():
            g._all_reports = res
        return res
    except Exception as e:
        logger.warning(f"Failed to fetch Reports sheet. Have you created the 'Reports' tab? Error: {e}")
        return []


def get_reports_for_intern(intern_id: str) -> List[Dict]:
    return [r for r in get_all_reports() if r["intern_id"] == intern_id]


def get_reports_for_manager(manager_id: str) -> List[Dict]:
    return [r for r in get_all_reports() if r["manager_id"] == manager_id]


def get_report_by_id(report_id: str) -> Optional[Dict]:
    for r in get_all_reports():
        if r["report_id"] == report_id:
            return r
    return None


def create_report(intern_id: str, department: str, manager_id: str, report_type: str, period_start: str, period_end: str, content: str) -> Dict:
    try:
        sheet = _get_sheet("Reports")
    except Exception as e:
        logger.error(f"Failed to access Reports sheet: {e}")
        raise RuntimeError("Please create a 'Reports' tab in your Google Sheet first.")
        
    report_id = _new_id()
    submitted_at = _now_utc_str()
    row = [report_id, intern_id, department, manager_id, report_type, period_start, period_end, content.strip(), submitted_at, "", "", ""]
    sheet.append_row(row, value_input_option="RAW")
    logger.info("Report created for intern=%s type=%s", intern_id, report_type)
    return {
        "report_id": report_id, "intern_id": intern_id, "department": department, "manager_id": manager_id,
        "report_type": report_type, "period_start": period_start, "period_end": period_end,
        "content": content, "submitted_at": submitted_at, "reviewed_by": "", "review_notes": "", "reviewed_at": ""
    }


def review_report(report_id: str, reviewed_by: str, review_notes: str) -> bool:
    try:
        sheet = _get_sheet("Reports")
        all_rows = sheet.get_all_values()
        for i, row in enumerate(all_rows[1:], start=2):
            if row[_REPORTS_COLS["report_id"]] == report_id:
                sheet.update_cell(i, _REPORTS_COLS["reviewed_by"] + 1, reviewed_by)
                sheet.update_cell(i, _REPORTS_COLS["review_notes"] + 1, review_notes)
                sheet.update_cell(i, _REPORTS_COLS["reviewed_at"] + 1, _now_utc_str())
                logger.info("Report %s reviewed by %s", report_id, reviewed_by)
                return True
    except Exception as e:
        logger.error(f"Failed to review report: {e}")
    return False

# ══════════════════════════════════════════════════════════════════════════════
# PERFORMANCE (Legacy/Admin only)
# ══════════════════════════════════════════════════════════════════════════════

def get_all_performance_reports() -> List[Dict]:
    from flask import g, has_app_context
    if has_app_context() and hasattr(g, '_all_performance'):
        return g._all_performance

    sheet = _get_sheet("Performance")
    rows = sheet.get_all_values()[1:]
    res = _rows_to_dicts(rows, _PERFORMANCE_COLS)
    
    if has_app_context():
        g._all_performance = res
    return res

def get_performance_reports_for_student(intern_id: str) -> List[Dict]:
    return [p for p in get_all_performance_reports() if p["intern_id"] == intern_id]

def get_performance_reports_for_manager(manager_id: str) -> List[Dict]:
    return [p for p in get_all_performance_reports() if p["manager_id"] == manager_id]

def create_performance_report(intern_id: str, manager_id: str, period_start: str, period_end: str,
                              technical_skill: int, communication: int, discipline: int, task_completion: int,
                              initiative: int, teamwork: int, code_quality: int, total_score: int, 
                              grade_band: str, strengths: str, areas_improvement: str, overall_comments: str) -> Dict:
    sheet = _get_sheet("Performance")
    report_id = _new_id()
    created_at = _now_utc_str()
    row = [
        report_id, intern_id, manager_id, period_start, period_end,
        "", "", "", "", "", "", "", # 5-11: Legacy columns left blank
        total_score, grade_band, strengths.strip(), areas_improvement.strip(), overall_comments.strip(), created_at,
        "", "False", "", # 18-20: edit_reason, intern_acknowledged, intern_ack_date
        technical_skill, communication, discipline, task_completion, initiative, teamwork, code_quality
    ]
    try:
        sheet.append_row(row, value_input_option="RAW")
    except Exception as e:
        logger.error(f"Failed to create performance report for intern {intern_id}: {str(e)}")
        raise ValueError(f"Could not save performance report to Google Sheets. Please try again later. ({str(e)})")
    
    return {"report_id": report_id}

def update_performance_report(report_id: str, updates: Dict) -> bool:
    sheet = _get_sheet("Performance")
    rows = sheet.get_all_values()
    header = rows[0]
    
    for idx, row in enumerate(rows[1:], start=1):
        if row and row[0] == report_id:
            for key, value in updates.items():
                if key in _PERFORMANCE_COLS:
                    col_idx = _PERFORMANCE_COLS[key]
                    # Pad row if needed
                    while len(row) <= col_idx:
                        row.append("")
                    row[col_idx] = str(value)
            sheet.update(f"A{idx+1}:U{idx+1}", [row], value_input_option="RAW")
            return True
    return False
# ══════════════════════════════════════════════════════════════════════════════
# INVITES
# ══════════════════════════════════════════════════════════════════════════════

def create_invite(email: str, department: str, token: str, admin_id: str) -> None:
    from datetime import timedelta
    sheet = _get_sheet("Invites")
    invite_id = _new_id()
    created_at = _now_utc_str()
    expires_at = (datetime.now(timezone.utc) + timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
    
    row = [
        invite_id,
        email,
        department,
        "manager",
        token,
        admin_id,
        created_at,
        expires_at,
        "no"
    ]
    sheet.append_row(row, value_input_option="RAW")
    logger.info("Created invite for %s", email)

def get_invite_by_token(token: str) -> Optional[Dict]:
    try:
        sheet = _get_sheet("Invites")
        rows = sheet.get_all_values()[1:]
        invites = _rows_to_dicts(rows, _INVITES_COLS)
        for inv in invites:
            if inv["token"] == token:
                inv["used"] = str(inv.get("used", "")).lower() in ("yes", "true", "1")
                return inv
        return None
    except Exception as e:
        logger.error(f"Error fetching invite by token: {e}")
        return None

def mark_invite_used(token: str) -> bool:
    try:
        sheet = _get_sheet("Invites")
        all_rows = sheet.get_all_values()
        for i, row in enumerate(all_rows[1:], start=2):
            if row[_INVITES_COLS["token"]] == token:
                sheet.update_cell(i, _INVITES_COLS["used"] + 1, "yes")
                return True
        return False
    except Exception as e:
        logger.error(f"Error marking invite as used: {e}")
        return False

# ══════════════════════════════════════════════════════════════════════════════
# MANAGER NOTES
# ══════════════════════════════════════════════════════════════════════════════

def get_manager_notes(intern_id: str) -> List[Dict]:
    try:
        sheet = _get_sheet("ManagerNotes")
        rows = sheet.get_all_values()[1:]
        all_notes = _rows_to_dicts(rows, _MANAGER_NOTES_COLS)
        intern_notes = [n for n in all_notes if n["intern_id"] == intern_id]
        # Sort by timestamp descending
        intern_notes.sort(key=lambda x: x["timestamp"], reverse=True)
        return intern_notes
    except Exception as e:
        logger.error(f"Error fetching manager notes for {intern_id}: {e}")
        return []

def create_manager_note(intern_id: str, manager_id: str, content: str) -> Dict:
    try:
        sheet = _get_sheet("ManagerNotes")
    except Exception:
        # If sheet doesn't exist, create it (fallback for initialization)
        client = _get_client()
        ss = client.open_by_key(os.environ["SPREADSHEET_ID"])
        sheet = ss.add_worksheet(title="ManagerNotes", rows=100, cols=20)
        sheet.insert_row(SHEET_HEADERS["ManagerNotes"], index=1)
        
    note_id = _new_id()
    timestamp = _now_utc_str()
    row = [note_id, intern_id, manager_id, timestamp, content.strip()]
    sheet.append_row(row, value_input_option="RAW")
    logger.info("Manager %s created note %s for intern %s", manager_id, note_id, intern_id)
    return {
        "note_id": note_id,
        "intern_id": intern_id,
        "manager_id": manager_id,
        "timestamp": timestamp,
        "content": content.strip()
    }

# ══════════════════════════════════════════════════════════════════════════════
# HOLIDAYS & SETTINGS
# ══════════════════════════════════════════════════════════════════════════════

def get_all_settings() -> Dict[str, str]:
    from flask import g, has_app_context
    if has_app_context() and hasattr(g, '_all_settings'):
        return g._all_settings

    try:
        sheet = _get_sheet("Settings")
        rows = sheet.get_all_values()[1:]
        res = {row[_SETTINGS_COLS["key"]]: row[_SETTINGS_COLS["value"]] for row in rows if len(row) > 1}
        if has_app_context():
            g._all_settings = res
        return res
    except Exception as e:
        logger.warning(f"Failed to fetch Settings sheet: {e}")
        return {}

def update_setting(key: str, value: str) -> bool:
    try:
        sheet = _get_sheet("Settings")
        all_rows = sheet.get_all_values()
        for i, row in enumerate(all_rows[1:], start=2):
            if row[_SETTINGS_COLS["key"]] == key:
                sheet.update_cell(i, _SETTINGS_COLS["value"] + 1, value)
                return True
        # If not found, append it
        sheet.append_row([key, value])
        return True
    except Exception as e:
        logger.error(f"Failed to update setting {key}: {e}")
        return False

# ══════════════════════════════════════════════════════════════════════════════
# HOLIDAYS
# ══════════════════════════════════════════════════════════════════════════════

def get_all_holidays() -> List[Dict]:
    from flask import g, has_app_context
    if has_app_context() and hasattr(g, '_all_holidays'):
        return g._all_holidays

    try:
        sheet = _get_sheet("Holidays")
        rows = sheet.get_all_values()[1:]
        res = _rows_to_dicts(rows, _HOLIDAYS_COLS)
        if has_app_context():
            g._all_holidays = res
        return res
    except Exception as e:
        logger.warning(f"Failed to fetch Holidays sheet: {e}")
        return []

def add_holiday(date_str: str, name: str) -> bool:
    try:
        sheet = _get_sheet("Holidays")
        sheet.append_row([date_str, name])
        return True
    except Exception as e:
        logger.error(f"Failed to add holiday: {e}")
        return False

def delete_holiday(date_str: str) -> bool:
    try:
        sheet = _get_sheet("Holidays")
        all_rows = sheet.get_all_values()
        for i, row in enumerate(all_rows[1:], start=2):
            if row[_HOLIDAYS_COLS["date"]] == date_str:
                sheet.delete_rows(i)
                return True
        return False
    except Exception as e:
        logger.error(f"Failed to delete holiday: {e}")
        return False

# ══════════════════════════════════════════════════════════════════════════════
# AUDIT LOG
# ══════════════════════════════════════════════════════════════════════════════

def get_all_audit_logs() -> List[Dict]:
    try:
        sheet = _get_sheet("AuditLog")
        rows = sheet.get_all_values()[1:]
        res = _rows_to_dicts(rows, _AUDIT_COLS)
        return res
    except Exception as e:
        logger.warning(f"Failed to fetch AuditLog sheet: {e}")
        return []

def log_audit(actor_id: str, action: str, details: str) -> None:
    # We also log to standard stdout
    logger.info(f"AUDIT: [{actor_id}] {action} - {details}")
    try:
        sheet = _get_sheet("AuditLog")
        sheet.append_row([_now_utc_str(), actor_id, action, details])
    except Exception as e:
        logger.error(f"Failed to write to AuditLog sheet: {e}")
