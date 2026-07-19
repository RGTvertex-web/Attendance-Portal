import os
import sys
import traceback
from flask import Flask, render_template

app = Flask(__name__, template_folder='templates')
app.secret_key = 'test'

# Mock data
org = {
    "total_students": 5,
    "today_present": 3,
    "today_absent": 2,
    "today_on_leave": 0,
    "at_risk_students": [{"name": "Test", "manager_id": "M1"}],
    "total_warnings": 1,
    "unack_warnings": 1,
}
managers = [{"id": "M1", "name": "Manager One", "department": "AI"}]
recent_warnings = [{"reason": "test", "intern_id": "123", "date": "2023-01-01", "acknowledged": "no"}]
dept_stats = {"AI": 5}
trend_data = {"labels": ["Mon"], "values": [100.0]}
perf_analytics = {
    "average_score": 50,
    "grade_distribution": {"Good": 1},
    "department_averages": {"AI": 50},
    "manager_leaderboard": [{"name": "M1", "reports": 1, "score": 50}],
    "total_reports": 1
}

DEPARTMENTS = ["AI", "Sales"]

@app.context_processor
def inject_global():
    return dict(
        DEPARTMENTS=DEPARTMENTS,
        g=type('obj', (object,), {'user': type('obj', (object,), {'name': 'Admin'})()})
    )

with app.app_context():
    try:
        html = render_template("admin/dashboard.html",
                               org=org,
                               managers=managers,
                               recent_warnings=recent_warnings,
                               dept_stats=dept_stats,
                               trend=trend_data,
                               perf_analytics=perf_analytics,
                               department_filter="")
        with open("render_test.log", "w", encoding="utf-8") as f:
            f.write("SUCCESS\n")
    except Exception as e:
        with open("render_test.log", "w", encoding="utf-8") as f:
            f.write(traceback.format_exc())
