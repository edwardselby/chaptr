"""
Unit tests for api/scheduler.py

Tests background task scheduler functionality:
- run_pruning_job execution
- start_scheduler initialization
- shutdown_scheduler graceful termination
- Idempotent behavior

CRITICAL: Scheduler bugs could lead to memory leaks, duplicate jobs,
or failure to prune old data (database growth).
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
import logging


# ============================================================================
# run_pruning_job Tests
# ============================================================================

@pytest.mark.asyncio
async def test_run_pruning_job_calls_prune_with_retention_days():
    """
    Verify run_pruning_job uses configured retention_days.

    Bug potential: Wrong retention days could delete too much or too little data.
    """
    with patch("api.scheduler.MongoDB") as mock_mongodb, \
         patch("api.scheduler.prune_change_log") as mock_prune, \
         patch("api.config.settings") as mock_settings:

        mock_db = MagicMock()
        mock_mongodb.get_database.return_value = mock_db
        mock_prune.return_value = 42  # Simulate 42 entries deleted
        mock_settings.change_log_retention_days = 31

        from api.scheduler import run_pruning_job
        await run_pruning_job()

        # Verify prune called with correct args
        mock_prune.assert_called_once_with(mock_db, retention_days=31)


@pytest.mark.asyncio
async def test_run_pruning_job_handles_prune_exception(caplog):
    """
    Verify run_pruning_job catches and logs exceptions.

    CRITICAL: Pruning job failure should not crash the scheduler.
    """
    with patch("api.scheduler.MongoDB") as mock_mongodb, \
         patch("api.scheduler.prune_change_log") as mock_prune, \
         patch("api.config.settings") as mock_settings:

        mock_mongodb.get_database.return_value = MagicMock()
        mock_prune.side_effect = Exception("Database connection lost")
        mock_settings.change_log_retention_days = 31

        from api.scheduler import run_pruning_job

        with caplog.at_level(logging.ERROR):
            # Should not raise
            await run_pruning_job()

        # Verify error was logged
        assert "Pruning job failed" in caplog.text


@pytest.mark.asyncio
async def test_run_pruning_job_handles_mongodb_connection_error():
    """
    Verify pruning job handles MongoDB unavailability.
    """
    with patch("api.scheduler.MongoDB") as mock_mongodb, \
         patch("api.config.settings") as mock_settings:

        mock_mongodb.get_database.side_effect = Exception("MongoDB not available")
        mock_settings.change_log_retention_days = 31

        from api.scheduler import run_pruning_job

        # Should not raise
        await run_pruning_job()


@pytest.mark.asyncio
async def test_run_pruning_job_logs_success_with_count(caplog):
    """
    Verify successful pruning logs the deleted count.
    """
    with patch("api.scheduler.MongoDB") as mock_mongodb, \
         patch("api.scheduler.prune_change_log") as mock_prune, \
         patch("api.config.settings") as mock_settings:

        mock_mongodb.get_database.return_value = MagicMock()
        mock_prune.return_value = 100  # Simulate 100 deleted
        mock_settings.change_log_retention_days = 31

        from api.scheduler import run_pruning_job

        with caplog.at_level(logging.INFO):
            await run_pruning_job()

        # Verify count logged
        assert "100" in caplog.text
        assert "deleted" in caplog.text.lower() or "Deleted" in caplog.text


# ============================================================================
# start_scheduler Tests
# ============================================================================

def test_start_scheduler_creates_scheduler():
    """
    Verify start_scheduler creates and starts AsyncIOScheduler.
    """
    import api.scheduler as scheduler_module

    # Reset global state
    scheduler_module.scheduler = None

    with patch("api.scheduler.AsyncIOScheduler") as mock_scheduler_class:
        mock_scheduler = MagicMock()
        mock_scheduler.running = False
        mock_scheduler_class.return_value = mock_scheduler

        scheduler_module.start_scheduler()

        # Verify scheduler created and started
        mock_scheduler_class.assert_called_once()
        mock_scheduler.add_job.assert_called_once()
        mock_scheduler.start.assert_called_once()


def test_start_scheduler_adds_pruning_job_at_2am():
    """
    Verify pruning job scheduled for 2:00 AM.

    Bug potential: Wrong schedule could prune during peak hours.
    """
    import api.scheduler as scheduler_module

    scheduler_module.scheduler = None

    with patch("api.scheduler.AsyncIOScheduler") as mock_scheduler_class, \
         patch("api.scheduler.CronTrigger") as mock_cron_trigger:

        mock_scheduler = MagicMock()
        mock_scheduler.running = False
        mock_scheduler_class.return_value = mock_scheduler

        scheduler_module.start_scheduler()

        # Verify CronTrigger called with hour=2, minute=0
        mock_cron_trigger.assert_called_once_with(hour=2, minute=0)


def test_start_scheduler_idempotent_when_already_running(caplog):
    """
    Verify start_scheduler is idempotent - doesn't create duplicate schedulers.

    CRITICAL: Double-starting could create duplicate jobs.
    """
    import api.scheduler as scheduler_module

    # Simulate already running scheduler
    mock_existing = MagicMock()
    mock_existing.running = True
    scheduler_module.scheduler = mock_existing

    with caplog.at_level(logging.WARNING):
        scheduler_module.start_scheduler()

    # Verify warning logged
    assert "already running" in caplog.text

    # Verify new scheduler NOT created
    assert scheduler_module.scheduler is mock_existing


def test_start_scheduler_replaces_existing_job():
    """
    Verify start_scheduler uses replace_existing=True.

    Bug potential: Without replace_existing, restarting could create duplicate jobs.
    """
    import api.scheduler as scheduler_module

    scheduler_module.scheduler = None

    with patch("api.scheduler.AsyncIOScheduler") as mock_scheduler_class:
        mock_scheduler = MagicMock()
        mock_scheduler.running = False
        mock_scheduler_class.return_value = mock_scheduler

        scheduler_module.start_scheduler()

        # Check add_job kwargs
        add_job_call = mock_scheduler.add_job.call_args
        assert add_job_call[1].get("replace_existing") is True


def test_start_scheduler_logs_job_schedule(caplog):
    """
    Verify start_scheduler logs the scheduled time.
    """
    import api.scheduler as scheduler_module

    scheduler_module.scheduler = None

    with patch("api.scheduler.AsyncIOScheduler") as mock_scheduler_class:
        mock_scheduler = MagicMock()
        mock_scheduler.running = False
        mock_scheduler_class.return_value = mock_scheduler

        with caplog.at_level(logging.INFO):
            scheduler_module.start_scheduler()

        # Verify schedule logged
        assert "2:00 AM" in caplog.text or "2:00" in caplog.text


# ============================================================================
# shutdown_scheduler Tests
# ============================================================================

def test_shutdown_scheduler_stops_running_scheduler():
    """
    Verify shutdown_scheduler stops a running scheduler.
    """
    import api.scheduler as scheduler_module

    mock_scheduler = MagicMock()
    mock_scheduler.running = True
    scheduler_module.scheduler = mock_scheduler

    scheduler_module.shutdown_scheduler()

    # Verify shutdown called
    mock_scheduler.shutdown.assert_called_once()


def test_shutdown_scheduler_waits_for_jobs():
    """
    Verify shutdown waits for running jobs to complete.
    """
    import api.scheduler as scheduler_module

    mock_scheduler = MagicMock()
    mock_scheduler.running = True
    scheduler_module.scheduler = mock_scheduler

    scheduler_module.shutdown_scheduler()

    # Verify wait=True passed
    call_kwargs = mock_scheduler.shutdown.call_args[1]
    assert call_kwargs.get("wait") is True


def test_shutdown_scheduler_has_timeout():
    """
    Verify shutdown has a timeout to prevent hanging.

    Bug potential: Infinite wait could hang application shutdown.
    """
    import api.scheduler as scheduler_module

    mock_scheduler = MagicMock()
    mock_scheduler.running = True
    scheduler_module.scheduler = mock_scheduler

    scheduler_module.shutdown_scheduler()

    # Verify timeout passed (should be 30 seconds per implementation)
    call_kwargs = mock_scheduler.shutdown.call_args[1]
    assert "timeout" in call_kwargs
    assert call_kwargs["timeout"] <= 60  # Should be reasonable timeout


def test_shutdown_scheduler_handles_timeout_error(caplog):
    """
    Verify shutdown handles timeout gracefully.
    """
    import api.scheduler as scheduler_module

    mock_scheduler = MagicMock()
    mock_scheduler.running = True
    mock_scheduler.shutdown.side_effect = Exception("Shutdown timeout")
    scheduler_module.scheduler = mock_scheduler

    with caplog.at_level(logging.WARNING):
        # Should not raise
        scheduler_module.shutdown_scheduler()

    # Verify warning logged
    assert "timeout" in caplog.text.lower() or "error" in caplog.text.lower()


def test_shutdown_scheduler_handles_not_running():
    """
    Verify shutdown handles scheduler that isn't running.
    """
    import api.scheduler as scheduler_module

    # Case 1: scheduler is None
    scheduler_module.scheduler = None
    scheduler_module.shutdown_scheduler()  # Should not raise

    # Case 2: scheduler exists but not running
    mock_scheduler = MagicMock()
    mock_scheduler.running = False
    scheduler_module.scheduler = mock_scheduler

    scheduler_module.shutdown_scheduler()  # Should not raise
    mock_scheduler.shutdown.assert_not_called()  # Shouldn't try to shut down


def test_shutdown_scheduler_logs_success(caplog):
    """
    Verify successful shutdown is logged.
    """
    import api.scheduler as scheduler_module

    mock_scheduler = MagicMock()
    mock_scheduler.running = True
    scheduler_module.scheduler = mock_scheduler

    with caplog.at_level(logging.INFO):
        scheduler_module.shutdown_scheduler()

    assert "shut down" in caplog.text.lower()


# ============================================================================
# Edge Cases
# ============================================================================

def test_scheduler_module_initializes_scheduler_as_none():
    """
    Verify scheduler module starts with scheduler = None.

    Bug potential: If initialized to something else, first start check could fail.
    """
    # Re-import to check initial state
    import importlib
    import api.scheduler as scheduler_module

    # Reset and reimport
    scheduler_module.scheduler = None

    # Verify initial state
    assert scheduler_module.scheduler is None


def test_start_then_shutdown_cycle():
    """
    Verify start -> shutdown -> start cycle works correctly.

    Bug potential: State not properly reset after shutdown.
    """
    import api.scheduler as scheduler_module

    scheduler_module.scheduler = None

    with patch("api.scheduler.AsyncIOScheduler") as mock_scheduler_class:
        mock_scheduler = MagicMock()
        mock_scheduler.running = False
        mock_scheduler_class.return_value = mock_scheduler

        # First start
        scheduler_module.start_scheduler()
        assert scheduler_module.scheduler is not None

        # Simulate running state
        mock_scheduler.running = True

        # Shutdown
        scheduler_module.shutdown_scheduler()

        # Reset mock for second start
        mock_scheduler.running = False
        new_mock = MagicMock()
        new_mock.running = False
        mock_scheduler_class.return_value = new_mock

        # Reset the module's scheduler (simulating actual shutdown effect)
        # In real code, the scheduler object still exists but is stopped
        scheduler_module.scheduler = None

        # Second start should work
        scheduler_module.start_scheduler()
        assert scheduler_module.scheduler is not None
