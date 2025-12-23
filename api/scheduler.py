"""
Background task scheduler for CHAPTR API maintenance jobs.

Uses APScheduler to run periodic maintenance tasks:
- Change log pruning (daily at 2:00 AM)
- Future: Recurring event generation, drift detection, etc.
"""

import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from api.config import MongoDB
from api.utils.pruning import prune_change_log

logger = logging.getLogger(__name__)


# Global scheduler instance
scheduler: AsyncIOScheduler | None = None


async def run_pruning_job():
    """
    Scheduled job: Prune old change_log entries.

    Runs daily at 2:00 AM server time to remove change_log entries
    older than 31 days. Keeps database size manageable while maintaining
    sync capability for active clients.

    **See Spec**: Sync Protocol > Change Log Pruning
    """
    try:
        logger.info("Starting scheduled change_log pruning job...")
        db = MongoDB.get_database()

        deleted_count = await prune_change_log(db, retention_days=31)

        logger.info(f"✓ Pruning job completed: Deleted {deleted_count} old change_log entries")
    except Exception as e:
        logger.error(f"✗ Pruning job failed: {e}", exc_info=True)


def start_scheduler():
    """
    Initialize and start the background task scheduler.

    Creates an AsyncIOScheduler instance and schedules all maintenance jobs.
    Should be called once during application startup.

    **Scheduled Jobs**:
    - Pruning: Daily at 2:00 AM server time
    - Future: Recurring event generation, drift detection, etc.

    :Example:

    >>> # In main.py lifespan startup
    >>> from api.scheduler import start_scheduler
    >>> start_scheduler()

    **Safety Notes**:
    - Idempotent: Safe to call multiple times (checks if already started)
    - Uses AsyncIOScheduler for compatibility with FastAPI async context
    - Jobs are non-blocking and run in background
    """
    global scheduler

    if scheduler is not None and scheduler.running:
        logger.warning("Scheduler already running, skipping initialization")
        return

    logger.info("Initializing background task scheduler...")

    scheduler = AsyncIOScheduler()

    # Schedule pruning job: Daily at 2:00 AM
    scheduler.add_job(
        run_pruning_job,
        trigger=CronTrigger(hour=2, minute=0),
        id='prune_change_log',
        name='Prune old change_log entries',
        replace_existing=True
    )

    scheduler.start()
    logger.info("✓ Background scheduler started successfully")
    logger.info("  - Pruning job: Daily at 2:00 AM")


def shutdown_scheduler():
    """
    Gracefully shutdown the background task scheduler.

    Should be called during application shutdown to ensure all jobs
    complete cleanly.

    :Example:

    >>> # In main.py lifespan shutdown
    >>> from api.scheduler import shutdown_scheduler
    >>> shutdown_scheduler()
    """
    global scheduler

    if scheduler is not None and scheduler.running:
        logger.info("Shutting down background scheduler...")
        scheduler.shutdown(wait=True)
        logger.info("✓ Background scheduler shut down successfully")
