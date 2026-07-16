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
            from services.attendance_service import evaluate_attendance_for_date
            logger.info("Scheduler: running daily attendance evaluation")
            try:
                summary = evaluate_attendance_for_date()
                logger.info("Scheduler: completed %s", summary)
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

    scheduler.start()
    logger.info("APScheduler started — attendance job at %02d:%02d UTC daily", hour_utc, minute_utc)
    return scheduler
