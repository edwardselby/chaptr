"""
Integration tests for admin endpoints - api/routes/admin.py

Tests for destructive database operations:
- POST /api/admin/clear-changelog - Clear user's change log
- POST /api/admin/nuclear-reset - Wipe entire database

CRITICAL: These tests verify security controls and isolation.
"""

import pytest
import pytest_asyncio
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from api.models import AccountCreate, EventCreate


# ============================================================================
# Clear Changelog Tests
# ============================================================================

@pytest.mark.integration
@pytest.mark.asyncio
async def test_clear_changelog_requires_authentication(async_client_real):
    """
    Verify clear_changelog endpoint requires authentication.

    Without auth headers, should return 401 Unauthorized.
    """
    response = await async_client_real.post("/api/admin/clear-changelog")
    assert response.status_code == 401


@pytest.mark.integration
@pytest.mark.asyncio
async def test_clear_changelog_deletes_only_user_entries(
    async_client_real,
    auth_headers_real,
    sample_user_real,
    clean_database_real
):
    """
    Verify clear_changelog only deletes current user's entries.

    Scenario:
    1. Create change_log entries for User A (current user)
    2. Create change_log entries for User B (other user)
    3. User A calls clear-changelog
    4. User A's entries deleted, User B's preserved

    CRITICAL: Tests user isolation for multi-user scenarios.
    """
    db = clean_database_real
    user_a_id = str(sample_user_real.id)
    tenant_id = str(sample_user_real.tenant_id)  # Multi-tenancy: use user's tenant_id
    user_b_id = str(uuid4())  # Different user

    # Create entries for User A (will be deleted)
    for i in range(5):
        await db["change_log"].insert_one({
            "id": str(uuid4()),
            "entity_type": "event",
            "entity_id": str(uuid4()),
            "action": "create",
            "data": {"description": f"User A event {i}"},
            "changed_by": user_a_id,  # This is the key field
            "changed_by_client": "client-a",
            "changed_at": datetime.now(timezone.utc).isoformat(),
            "tenant_id": tenant_id  # Multi-tenancy: required for filtering
        })

    # Create entries for User B (must be preserved - same tenant, different user)
    for i in range(3):
        await db["change_log"].insert_one({
            "id": str(uuid4()),
            "entity_type": "event",
            "entity_id": str(uuid4()),
            "action": "create",
            "data": {"description": f"User B event {i}"},
            "changed_by": user_b_id,  # Different user
            "changed_by_client": "client-b",
            "changed_at": datetime.now(timezone.utc).isoformat(),
            "tenant_id": tenant_id  # Same tenant, different user
        })

    # Verify setup
    user_a_count = await db["change_log"].count_documents({"changed_by": user_a_id})
    user_b_count = await db["change_log"].count_documents({"changed_by": user_b_id})
    assert user_a_count == 5, f"Expected 5 User A entries, got {user_a_count}"
    assert user_b_count == 3, f"Expected 3 User B entries, got {user_b_count}"

    # User A clears their changelog
    response = await async_client_real.post(
        "/api/admin/clear-changelog",
        headers=auth_headers_real
    )
    assert response.status_code == 200
    data = response.json()

    # Verify response
    assert data["deleted_count"] == 5, "Should delete 5 entries"
    assert user_a_id in data["message"]

    # Verify User A's entries deleted
    user_a_after = await db["change_log"].count_documents({"changed_by": user_a_id})
    assert user_a_after == 0, "User A's entries should be deleted"

    # CRITICAL: Verify User B's entries preserved
    user_b_after = await db["change_log"].count_documents({"changed_by": user_b_id})
    assert user_b_after == 3, "User B's entries must be preserved"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_clear_changelog_returns_zero_when_no_entries(
    async_client_real,
    auth_headers_real,
    sample_user_real,
    clean_database_real
):
    """
    Verify clear_changelog handles case with no entries gracefully.

    Should return deleted_count: 0, not error.
    """
    db = clean_database_real
    user_id = str(sample_user_real.id)

    # Ensure no entries for this user
    await db["change_log"].delete_many({"changed_by": user_id})

    response = await async_client_real.post(
        "/api/admin/clear-changelog",
        headers=auth_headers_real
    )
    assert response.status_code == 200
    data = response.json()

    assert data["deleted_count"] == 0


# ============================================================================
# Nuclear Reset Tests
# ============================================================================

@pytest.mark.integration
@pytest.mark.asyncio
async def test_nuclear_reset_requires_authentication(async_client_real):
    """
    Verify nuclear_reset endpoint requires authentication.
    """
    response = await async_client_real.post(
        "/api/admin/nuclear-reset",
        json={"password": "anything"}
    )
    assert response.status_code == 401


@pytest.mark.integration
@pytest.mark.asyncio
async def test_nuclear_reset_rejects_wrong_password(
    async_client_real,
    auth_headers_real,
    monkeypatch
):
    """
    Verify nuclear_reset rejects incorrect password.

    SECURITY: Must not proceed with wrong password.
    """
    from api import config

    # Set a known admin password
    monkeypatch.setattr(config.settings, "admin_password", "correct-secret-password")

    response = await async_client_real.post(
        "/api/admin/nuclear-reset",
        json={"password": "wrong-password"},
        headers=auth_headers_real
    )

    assert response.status_code == 403
    assert "Invalid password" in response.json()["detail"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_nuclear_reset_fails_when_admin_password_not_set(
    async_client_real,
    auth_headers_real,
    monkeypatch
):
    """
    Verify nuclear_reset fails if ADMIN_PASSWORD env var not configured.

    SECURITY: Server should return 500, not proceed without password requirement.
    """
    from api import config

    # Clear admin password
    monkeypatch.setattr(config.settings, "admin_password", None)

    response = await async_client_real.post(
        "/api/admin/nuclear-reset",
        json={"password": "any-password"},
        headers=auth_headers_real
    )

    assert response.status_code == 500
    assert "ADMIN_PASSWORD" in response.json()["detail"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_nuclear_reset_deletes_all_data_preserves_users_settings(
    async_client_real,
    auth_headers_real,
    sample_user_real,
    sample_settings_real,
    account_repo_real,
    event_repo_real,
    story_repo_real,
    clean_database_real,
    monkeypatch
):
    """
    Verify nuclear_reset deletes data but preserves users and settings.

    Scenario:
    1. Create accounts, events, stories, change_log entries
    2. Call nuclear_reset with correct password
    3. Verify data deleted but users/settings preserved

    CRITICAL: Tests the most destructive endpoint in the system.
    """
    from api import config
    db = clean_database_real

    # Set admin password
    test_password = "test-admin-password-123"
    monkeypatch.setattr(config.settings, "admin_password", test_password)

    # Create test data
    account = await account_repo_real.create(
        AccountCreate(
            name="Test Account",
            currency="GBP",
            current_balance=Decimal("1000.00")
        ),
        current_user={"id": str(sample_user_real.id), "tenant_id": str(sample_user_real.tenant_id)},
        client_id=None
    )

    event = await event_repo_real.create(
        EventCreate(
            event_date="2025-01-15",
            description="Test Event",
            amount=Decimal("-100.00"),
            currency="GBP",
            account_id=account.id
        ),
        current_user={"id": str(sample_user_real.id), "tenant_id": str(sample_user_real.tenant_id)},
        client_id=None
    )

    # Verify data exists before reset
    assert await db["accounts"].count_documents({}) >= 1
    assert await db["events"].count_documents({}) >= 1
    assert await db["users"].count_documents({}) >= 1
    assert await db["settings"].count_documents({}) >= 1

    # Execute nuclear reset
    response = await async_client_real.post(
        "/api/admin/nuclear-reset",
        json={"password": test_password},
        headers=auth_headers_real
    )

    assert response.status_code == 200
    data = response.json()

    # Verify response structure
    assert data["success"] is True
    assert "deleted" in data
    assert "preserved" in data
    assert "users" in data["preserved"]
    assert "settings" in data["preserved"]

    # Verify deletion counts
    assert data["deleted"]["accounts"] >= 1
    assert data["deleted"]["events"] >= 1

    # Verify data deleted
    assert await db["accounts"].count_documents({}) == 0
    assert await db["events"].count_documents({}) == 0
    assert await db["stories"].count_documents({}) == 0
    assert await db["recurring_rules"].count_documents({}) == 0
    assert await db["change_log"].count_documents({}) == 0
    assert await db["conflicts"].count_documents({}) == 0

    # CRITICAL: Verify users and settings preserved
    users_count = await db["users"].count_documents({})
    settings_count = await db["settings"].count_documents({})
    assert users_count >= 1, "Users should be preserved after nuclear reset"
    assert settings_count >= 1, "Settings should be preserved after nuclear reset"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_nuclear_reset_empty_password_rejected(
    async_client_real,
    auth_headers_real,
    monkeypatch
):
    """
    Verify nuclear_reset rejects empty password.

    SECURITY: Empty string should not match any password.
    """
    from api import config

    monkeypatch.setattr(config.settings, "admin_password", "real-password")

    response = await async_client_real.post(
        "/api/admin/nuclear-reset",
        json={"password": ""},
        headers=auth_headers_real
    )

    assert response.status_code == 403


@pytest.mark.integration
@pytest.mark.asyncio
async def test_nuclear_reset_missing_password_field(
    async_client_real,
    auth_headers_real,
    monkeypatch
):
    """
    Verify nuclear_reset requires password field in request body.

    Pydantic validation should reject missing required field.
    """
    from api import config

    monkeypatch.setattr(config.settings, "admin_password", "real-password")

    response = await async_client_real.post(
        "/api/admin/nuclear-reset",
        json={},  # Missing password
        headers=auth_headers_real
    )

    # Pydantic should return 422 for validation error
    assert response.status_code == 422
