"""
Settings management endpoints.

Provides GET and PUT operations for application settings using singleton pattern.
Settings are global (not per-user) and admin-only for modification.
"""

from fastapi import APIRouter, Depends

from api.config import MongoDB
from api.models import Settings, SettingsUpdate
from api.repositories.settings import SettingsRepository
from api.utils.auth import get_current_admin_user

router = APIRouter()


def get_settings_repo() -> SettingsRepository:
    """
    Dependency injection for SettingsRepository.

    :return: Initialized SettingsRepository
    :rtype: SettingsRepository
    """
    db = MongoDB.get_database()
    return SettingsRepository(db)


@router.get("/settings", response_model=Settings)
async def get_settings(
    repo: SettingsRepository = Depends(get_settings_repo)
):
    """
    Get application settings (singleton pattern).

    If no settings exist, creates default settings with:
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
    return await repo.get_or_create_default()


@router.put("/settings", response_model=Settings)
async def update_settings(
    data: SettingsUpdate,
    current_user: dict = Depends(get_current_admin_user),
    repo: SettingsRepository = Depends(get_settings_repo)
):
    """
    Update application settings (admin-only).

    Supports partial updates - only provided fields are updated.
    Requires admin role - non-admin users receive 403 Forbidden.

    Business Rules:
    - Only one settings document exists (singleton)
    - Admin-only operation (auth check placeholder until Phase 1.5)
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
    # TODO Phase 1.5: Add admin-only check
    # if not current_user.is_admin:
    #     raise ResourceConflictError("Settings can only be modified by admins")

    return await repo.update_singleton(data)
