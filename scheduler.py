"""
scheduler.py — APScheduler daily attendance job
"""

import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz

logger = logging.getLogger(__name__)


def start_scheduler(app):
    """Start the background scheduler attached to the Flask app context."""
    hour_utc   = app.config.get("ATTENDANCE_JOB_HOUR_UTC", 13)
    minute_utc = app.config.get("ATTENDANCE_JOB_MINUTE_UTC", 0)

    scheduler = BackgroundScheduler(timezone=pytz.utc)

    def run_daily_job():
        with app.app_context():
            from services.attendance_service import evaluate_attendance_for_date, check_and_send_absence_warnings
            logger.info("Scheduler: running daily attendance evaluation")
            try:
                summary = evaluate_attendance_for_date()
                logger.info("Scheduler: completed %s", summary)
                
                logger.info("Scheduler: running absence warning evaluation")
                check_and_send_absence_warnings()
                logger.info("Scheduler: completed absence warnings")
            except Exception as exc:
                logger.error("Scheduler: attendance job failed — %s", exc, exc_info=True)

    scheduler.add_job(
        run_daily_job,
        trigger=CronTrigger(hour=hour_utc, minute=minute_utc, timezone=pytz.utc),
        id="daily_attendance",
        name="Daily Attendance Evaluation",
        replace_existing=True,
        misfire_grace_time=3600,  # Allow up to 1hr late firing
    )
    
    def run_monthly_report_check():
        with app.app_context():
            from services.attendance_service import check_missing_monthly_reports
            logger.info("Scheduler: running monthly missing report check")
            try:
                check_missing_monthly_reports()
                logger.info("Scheduler: completed monthly report check")
            except Exception as exc:
                logger.error("Scheduler: monthly report check failed — %s", exc, exc_info=True)

    # Run on the 1st of every month at 8:00 AM UTC
    scheduler.add_job(
        run_monthly_report_check,
        trigger=CronTrigger(day=1, hour=8, minute=0, timezone=pytz.utc),
        id="monthly_missing_reports",
        name="Monthly Missing Reports Check",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    scheduler.start()
    logger.info("APScheduler started — attendance job at %02d:%02d UTC daily, monthly reports check on 1st of month", hour_utc, minute_utc)
    return scheduler
