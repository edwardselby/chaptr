"""
Settings repository for CHAPTR API.

Provides data access layer for per-tenant application settings.
Multi-tenancy: Each tenant has its own settings instance.
"""

from uuid import UUID
from typing import Optional
from decimal import Decimal

from api.repositories.base import BaseRepository
from api.models import Settings, SettingsUpdate
from api.utils.db import generate_id, utc_now


class SettingsRepository(BaseRepository[Settings]):
    """
    Repository for managing per-tenant application settings.

    Multi-tenancy pattern:
    - Each tenant has their own settings document
    - GET creates default settings for tenant if none exist
    - PUT updates the tenant's settings document

    :Example:

    >>> repo = SettingsRepository(db)
    >>> settings = await repo.get_or_create_for_tenant(tenant_id)
    >>> updated = await repo.update_for_tenant(tenant_id, SettingsUpdate(base_currency="USD"))
    """

    def __init__(self, db):
        """
        Initialize settings repository.

        :param db: MongoDB database instance
        :type db: AsyncIOMotorDatabase
        """
        super().__init__(db, "settings", Settings)

    async def get_for_tenant(self, tenant_id: UUID) -> Optional[Settings]:
        """
        Get settings for a specific tenant.

        :param tenant_id: Tenant identifier
        :type tenant_id: UUID
        :return: Settings for tenant or None if not found
        :rtype: Optional[Settings]

        :Example:

        >>> settings = await repo.get_for_tenant(tenant_id)
        >>> if settings:
        ...     print(settings.base_currency)
        """
        doc = await self.collection.find_one({"tenant_id": str(tenant_id)})
        return Settings(**doc) if doc else None

    async def get_or_create_for_tenant(self, tenant_id: UUID) -> Settings:
        """
        Get existing settings for tenant or create defaults.

        Called during sync and by other repositories that need settings
        (e.g., for currency rates).

        Default settings:
        - base_currency: GBP
        - default_currency: GBP
        - date_format: DD/MM/YYYY
        - baseline_display_months: 1
        - rates: USD, CAD, EUR conversion rates
        - version: 1.0.0
        - tenant_id: provided tenant_id

        :param tenant_id: Tenant identifier
        :type tenant_id: UUID
        :return: Settings document (existing or newly created)
        :rtype: Settings

        :Example:

        >>> settings = await repo.get_or_create_for_tenant(tenant_id)
        >>> settings.base_currency
        'GBP'
        """
        # Try to get existing settings for tenant
        existing = await self.get_for_tenant(tenant_id)
        if existing:
            return existing

        # Create default settings for tenant
        settings = Settings(
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
            tenant_id=tenant_id,
            created_at=utc_now(),
            updated_at=utc_now()
        )

        await self.collection.insert_one(settings.model_dump(mode="json"))
        return settings

    async def get_or_create_default(self, tenant_id: Optional[UUID] = None) -> Settings:
        """
        Backward-compatible method - get or create settings.

        If tenant_id provided, uses per-tenant settings.
        Otherwise, returns first settings found (for migration compatibility).

        :param tenant_id: Optional tenant identifier
        :type tenant_id: Optional[UUID]
        :return: Settings document
        :rtype: Settings
        """
        if tenant_id:
            return await self.get_or_create_for_tenant(tenant_id)

        # Fallback for backward compatibility (pre-migration)
        doc = await self.collection.find_one({})
        if doc:
            return Settings(**doc)

        # Create default settings without tenant_id (migration will fix)
        settings = Settings(
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
            tenant_id=None,
            created_at=utc_now(),
            updated_at=utc_now()
        )

        await self.collection.insert_one(settings.model_dump(mode="json"))
        return settings

    async def update_for_tenant(
        self,
        tenant_id: UUID,
        data: SettingsUpdate,
        current_user: Optional[dict] = None,
        client_id: Optional[str] = None
    ) -> Settings:
        """
        Update settings for a specific tenant.

        This updates the settings document for the specified tenant.
        Creates default settings if none exist yet.

        :param tenant_id: Tenant identifier
        :type tenant_id: UUID
        :param data: Update data (partial)
        :type data: SettingsUpdate
        :param current_user: Current authenticated user
        :type current_user: Optional[dict]
        :param client_id: Client ID for change log
        :type client_id: Optional[str]
        :return: Updated settings
        :rtype: Settings

        :Example:

        >>> settings = await repo.update_for_tenant(
        ...     tenant_id,
        ...     SettingsUpdate(
        ...         rates={
        ...             "USD": "1.30",
        ...             "EUR": "1.15"
        ...         }
        ...     )
        ... )
        """
        # Get or create settings for tenant
        existing = await self.get_or_create_for_tenant(tenant_id)

        # Prepare update dictionary
        update_dict = data.model_dump(exclude_unset=True)

        # Always update timestamp
        update_dict['updated_at'] = utc_now()

        # Convert Decimals to strings (for mongomock compatibility)
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
            {"id": str(existing.id), "tenant_id": str(tenant_id)},
            {"$set": {k: convert_decimals(v) for k, v in update_dict.items()}}
        )

        # Get updated settings
        updated_settings = await self.get_or_create_for_tenant(tenant_id)

        # NOTE: Settings changes are NOT logged to change_log per spec
        # Sync happens through /api/settings endpoint, not change_log protocol

        return updated_settings

    async def update_singleton(
        self,
        data: SettingsUpdate,
        updated_by: Optional[UUID] = None,
        current_user: Optional[dict] = None,
        client_id: Optional[str] = None,
        tenant_id: Optional[UUID] = None
    ) -> Settings:
        """
        Backward-compatible update method.

        If tenant_id provided, updates that tenant's settings.
        Otherwise, updates the first settings found.

        :param data: Update data (partial)
        :type data: SettingsUpdate
        :param updated_by: User ID updating settings (Phase 1.5, admin-only)
        :type updated_by: Optional[UUID]
        :param tenant_id: Optional tenant identifier
        :type tenant_id: Optional[UUID]
        :return: Updated settings
        :rtype: Settings
        """
        # If tenant_id provided, use per-tenant update
        if tenant_id:
            return await self.update_for_tenant(tenant_id, data, current_user, client_id)

        # If current_user has tenant_id, use it
        if current_user and current_user.get("tenant_id"):
            return await self.update_for_tenant(
                UUID(current_user["tenant_id"]),
                data,
                current_user,
                client_id
            )

        # Fallback for backward compatibility (pre-migration)
        existing = await self.get_or_create_default()

        # Prepare update dictionary
        update_dict = data.model_dump(exclude_unset=True)

        # Always update timestamp
        update_dict['updated_at'] = utc_now()

        # Convert Decimals to strings (for mongomock compatibility)
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

        return updated_settings
