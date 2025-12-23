"""
Settings repository for CHAPTR API.

Provides data access layer for application settings using singleton pattern.
Settings are global (not per-user) and admin-only for modification.
"""

from uuid import UUID
from typing import Optional
from decimal import Decimal

from api.repositories.base import BaseRepository
from api.models import Settings, SettingsUpdate
from api.utils.db import generate_id, utc_now


class SettingsRepository(BaseRepository[Settings]):
    """
    Repository for managing application settings.

    Implements singleton pattern:
    - Only one settings document exists in the database
    - GET creates default settings if none exist
    - PUT updates the singleton document

    :Example:

    >>> repo = SettingsRepository(db)
    >>> settings = await repo.get_or_create_default()
    >>> updated = await repo.update_singleton(SettingsUpdate(base_currency="USD"))
    """

    def __init__(self, db):
        """
        Initialize settings repository.

        :param db: MongoDB database instance
        :type db: AsyncIOMotorDatabase
        """
        super().__init__(db, "settings", Settings)

    async def get_or_create_default(self) -> Settings:
        """
        Get existing settings or create default if none exist.

        This implements the singleton pattern - there should only be one
        settings document in the database.

        :return: Settings document
        :rtype: Settings

        :Example:

        >>> settings = await repo.get_or_create_default()
        >>> print(settings.base_currency)  # "GBP"
        """
        # Try to find existing settings
        doc = await self.collection.find_one({})

        if doc:
            return Settings(**doc)

        # Create default settings if none exist
        default_settings = Settings(
            id=generate_id(),
            base_currency="GBP",
            default_currency="GBP",
            date_format="DD/MM/YYYY",
            baseline_display_months=1,
            rates={
                "USD": "1.27",
                "CAD": "1.76",
                "EUR": "1.20"
            },
            server_url="",
            last_backup_date=None,
            version="1.0.0",
            created_at=utc_now(),
            updated_at=utc_now()
        )

        # Insert into MongoDB
        await self.collection.insert_one(default_settings.model_dump(mode="json"))

        return default_settings

    async def update_singleton(
        self,
        data: SettingsUpdate,
        updated_by: Optional[UUID] = None,
        current_user: Optional[dict] = None,
        client_id: Optional[str] = None
    ) -> Settings:
        """
        Update the singleton settings document.

        This updates the one and only settings document in the database.
        Creates default settings if none exist yet.

        :param data: Update data (partial)
        :type data: SettingsUpdate
        :param updated_by: User ID updating settings (Phase 1.5, admin-only)
        :type updated_by: Optional[UUID]
        :return: Updated settings
        :rtype: Settings

        :Example:

        >>> settings = await repo.update_singleton(
        ...     SettingsUpdate(
        ...         rates={
        ...             "USD": "1.30",
        ...             "EUR": "1.15"
        ...         }
        ...     )
        ... )
        """
        # Get or create settings
        existing = await self.get_or_create_default()

        # Prepare update dictionary
        update_dict = data.model_dump(exclude_unset=True)

        # Always update timestamp
        update_dict['updated_at'] = utc_now()

        # Convert Decimals to strings (for mongomock compatibility)
        # This handles both top-level Decimals and nested Decimals in dicts (rates)
        def convert_decimals(value):
            """Recursively convert Decimals to strings in nested structures."""
            if isinstance(value, Decimal):
                return str(value)
            elif isinstance(value, dict):
                return {k: convert_decimals(v) for k, v in value.items()}
            elif isinstance(value, list):
                return [convert_decimals(item) for item in value]
            elif hasattr(value, 'isoformat'):
                return value.isoformat()
            elif isinstance(value, UUID):
                return str(value)
            else:
                return value

        # Apply update with Decimal handling
        await self.collection.update_one(
            {"id": str(existing.id)},
            {"$set": {k: convert_decimals(v) for k, v in update_dict.items()}}
        )

        # Get updated settings
        updated_settings = await self.get_or_create_default()

        # NOTE: Settings changes are NOT logged to change_log per spec
        # Settings are a global singleton shared across all devices
        # Sync happens through /api/settings endpoint, not change_log protocol

        # Return updated settings
        return updated_settings
