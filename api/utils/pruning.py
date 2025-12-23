"""
Change log pruning utilities for sync protocol maintenance.

Provides automatic cleanup of old change_log entries to prevent
unbounded database growth while maintaining sync capability.
"""

from datetime import timedelta
from typing import Optional

from motor.motor_asyncio import AsyncIOMotorDatabase

from api.utils.db import utc_now


async def prune_change_log(
    db: AsyncIOMotorDatabase,
    retention_days: int = 31
) -> int:
    """
    Remove change_log entries older than retention period.

    Deletes change log records that are older than the specified retention
    period. This prevents the change_log collection from growing indefinitely
    while maintaining enough history for sync operations.

    :param db: MongoDB database instance
    :type db: AsyncIOMotorDatabase
    :param retention_days: Number of days to retain change log entries (default: 31)
    :type retention_days: int
    :return: Number of deleted change log entries
    :rtype: int

    :Example:

    >>> from api.config import MongoDB
    >>> db = MongoDB.get_database()
    >>> deleted_count = await prune_change_log(db, retention_days=31)
    >>> print(f"Pruned {deleted_count} old change log entries")

    **Business Rules**:
    - Default retention: 31 days (balances sync capability vs storage)
    - Clients syncing after retention period will trigger full_sync_required
    - Deletion is permanent - no recovery possible
    - Pruning runs daily at 2:00 AM server time (see scheduler.py)

    **See Spec**: Sync Protocol > Stale Client Handling
    """
    cutoff = utc_now() - timedelta(days=retention_days)

    result = await db["change_log"].delete_many({
        "changed_at": {"$lt": cutoff.isoformat()}
    })

    return result.deleted_count
