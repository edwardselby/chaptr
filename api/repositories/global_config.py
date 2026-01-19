"""
Repository for global configuration and refresh metadata.

This collection stores system-level state that is NOT tenant-specific
and NOT sync-able (unlike the main entity repositories).

Use cases:
- Currency rate refresh tracking (shared across all tenants)
- Other lazy-refresh global data sources
"""

from datetime import datetime
from typing import Optional

from motor.motor_asyncio import AsyncIOMotorDatabase


class GlobalConfigRepository:
    """
    Manages global configuration separate from tenant data.

    Unlike other repositories, this does NOT extend BaseRepository because:
    - Data is global (not per-tenant)
    - Data is not sync-able (internal system state)
    - Simple key-value pattern (no CRUD on entities)

    :param db: MongoDB database instance
    :type db: AsyncIOMotorDatabase

    :Example:

    >>> repo = GlobalConfigRepository(db)
    >>> status = await repo.get_refresh_status("currency_rates")
    >>> await repo.set_refresh_status("currency_rates", {
    ...     "last_refresh": datetime.utcnow(),
    ...     "success": True
    ... })
    """

    def __init__(self, db: AsyncIOMotorDatabase):
        """
        Initialize global config repository.

        :param db: MongoDB database instance
        :type db: AsyncIOMotorDatabase
        """
        self.db = db
        self.collection = db["global_config"]

    async def get_refresh_status(self, key: str) -> Optional[dict]:
        """
        Get refresh status for a given key.

        :param key: Configuration key (e.g., "currency_rates")
        :type key: str
        :return: Status document or None if not found
        :rtype: Optional[dict]

        :Example:

        >>> status = await repo.get_refresh_status("currency_rates")
        >>> if status:
        ...     last_refresh = status.get("last_refresh")
        """
        doc = await self.collection.find_one({"_id": key})
        return doc

    async def set_refresh_status(self, key: str, data: dict) -> None:
        """
        Set refresh status for a given key.

        Uses upsert to create or update the document.

        :param key: Configuration key (e.g., "currency_rates")
        :type key: str
        :param data: Status data to store
        :type data: dict

        :Example:

        >>> await repo.set_refresh_status("currency_rates", {
        ...     "last_refresh": datetime.utcnow(),
        ...     "success": True,
        ...     "rate_count": 30
        ... })
        """
        await self.collection.update_one(
            {"_id": key},
            {"$set": {**data, "updated_at": datetime.utcnow()}},
            upsert=True
        )
