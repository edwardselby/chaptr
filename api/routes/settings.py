"""
Settings management endpoints.

Provides GET and PUT operations for per-tenant application settings.
Multi-tenancy: Each tenant has their own settings instance.
Settings are admin-only for modification within each tenant.
"""

from fastapi import APIRouter, Depends
from uuid import UUID

from api.config import MongoDB
from api.models import Settings, SettingsUpdate
from api.repositories.settings import SettingsRepository
from api.utils.auth import get_current_admin_user, get_current_user

router = APIRouter()


def get_settings_repo() -> SettingsRepository:
    """
    Dependency injection for SettingsRepository.

    :return: Initialized SettingsRepository
    :rtype: SettingsRepository
    """
    db = MongoDB.get_database()
    return SettingsRepository(db)


def get_tenant_id(current_user: dict) -> UUID:
    """
    Extract tenant_id from current user for multi-tenancy filtering.

    :param current_user: Current user dict from JWT token
    :type current_user: dict
    :return: Tenant UUID
    :rtype: UUID
    """
    return UUID(current_user["tenant_id"])


@router.get("/settings", response_model=Settings)
async def get_settings(
    current_user: dict = Depends(get_current_user),
    repo: SettingsRepository = Depends(get_settings_repo)
):
    """
    Get application settings for current tenant.

    Multi-tenancy: Returns settings for the current user's tenant.
    If no settings exist for tenant, creates default settings with:
    - base_currency: GBP
    - default_currency: GBP
    - date_format: DD/MM/YYYY
    - baseline_display_months: 1
    - Default rates: USD=1.27, CAD=1.76, EUR=1.20

    :param repo: Injected SettingsRepository
    :type repo: SettingsRepository
    :return: Settings document
    :rtype: Settings

    :Example:

    ```bash
    curl http://localhost:8000/api/settings
    ```
    """
    tenant_id = get_tenant_id(current_user)
    return await repo.get_or_create_for_tenant(tenant_id)


@router.put("/settings", response_model=Settings)
async def update_settings(
    data: SettingsUpdate,
    current_user: dict = Depends(get_current_admin_user),
    repo: SettingsRepository = Depends(get_settings_repo)
):
    """
    Update application settings for current tenant (admin-only).

    Supports partial updates - only provided fields are updated.
    Requires admin role - non-admin users receive 403 Forbidden.

    Multi-tenancy: Updates settings for the current user's tenant only.

    Business Rules:
    - Each tenant has their own settings document
    - Admin-only operation (requires admin or super_admin role)
    - Changing base_currency affects projection calculations
    - Changing rates affects display conversions (not locked event rates)

    :param data: Update data (partial)
    :type data: SettingsUpdate
    :param repo: Injected SettingsRepository
    :type repo: SettingsRepository
    :return: Updated settings
    :rtype: Settings

    :Example:

    ```bash
    # Update currency rates
    curl -X PUT http://localhost:8000/api/settings \\
      -H "Content-Type: application/json" \\
      -d '{
        "rates": {
          "USD": 1.30,
          "CAD": 1.80,
          "EUR": 1.18
        }
      }'

    # Change base currency
    curl -X PUT http://localhost:8000/api/settings \\
      -H "Content-Type: application/json" \\
      -d '{"base_currency": "USD"}'

    # Update server URL for sync
    curl -X PUT http://localhost:8000/api/settings \\
      -H "Content-Type: application/json" \\
      -d '{"server_url": "https://chaptr.example.com"}'
    ```
    """
    tenant_id = get_tenant_id(current_user)
    return await repo.update_for_tenant(tenant_id, data, current_user=current_user, client_id=None)
