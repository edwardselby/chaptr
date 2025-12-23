"""
Database indexing utilities for CHAPTR API.

Provides functions to create performance-critical indexes on MongoDB collections,
especially for the change_log collection used by the sync protocol.
"""

from motor.motor_asyncio import AsyncIOMotorDatabase
import logging

logger = logging.getLogger(__name__)


async def create_change_log_indexes(db: AsyncIOMotorDatabase) -> None:
    """
    Create indexes for change_log collection to optimize sync queries.

    Indexes Created:
    1. sync_pull_idx: Composite index (changed_at ASC, changed_by_client ASC)
       - Optimizes sync pull queries that filter by timestamp and exclude client's own changes
       - Supports: { changed_at: { $gt: timestamp }, changed_by_client: { $ne: client_id } }

    2. pruning_idx: Single field index on changed_at
       - Optimizes pruning job that deletes old entries: { changed_at: { $lt: cutoff } }

    3. client_filter_idx: Single field index on changed_by_client
       - Optimizes queries filtering by specific client

    :param db: MongoDB database instance
    :type db: AsyncIOMotorDatabase
    :return: None
    :rtype: None

    :Example:

    >>> from api.config import MongoDB
    >>> db = MongoDB.get_database()
    >>> await create_change_log_indexes(db)
    """
    try:
        # Composite index for sync pull queries
        # Query pattern: find changes after timestamp, excluding own client
        await db["change_log"].create_index(
            [("changed_at", 1), ("changed_by_client", 1)],
            name="sync_pull_idx"
        )
        logger.info("✓ Created composite index on change_log (changed_at, changed_by_client)")

        # Index for pruning old entries
        await db["change_log"].create_index(
            "changed_at",
            name="pruning_idx"
        )
        logger.info("✓ Created index on change_log.changed_at for pruning")

        # Index for filtering by client
        await db["change_log"].create_index(
            "changed_by_client",
            name="client_filter_idx"
        )
        logger.info("✓ Created index on change_log.changed_by_client")

    except Exception as e:
        logger.warning(f"⚠ Failed to create change_log indexes: {e}")
        # Don't fail startup if index creation fails
        # Indexes are performance optimization, not required for functionality
