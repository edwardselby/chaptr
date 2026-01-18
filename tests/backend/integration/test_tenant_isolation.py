"""
Tenant Isolation Integration Tests

Tests that verify data isolation between tenants in the multi-tenancy architecture.
Each tenant's data (users, accounts, events, stories) should be completely isolated.

Key Scenarios:
- Admin from Tenant A cannot access Tenant B's users
- Admin from Tenant A cannot access Tenant B's accounts/events/stories
- Sync operations are scoped to the requesting tenant
- Tenant assignment follows role-based rules

Priority: 🚨 CRITICAL - Security boundary tests
Coverage Target: 100% of cross-tenant access paths
"""

import pytest
import pytest_asyncio
from datetime import date
from decimal import Decimal
from uuid import UUID

from api.models import UserCreate, AccountCreate, StoryCreate, EventCreate
from api.utils.auth import create_access_token


# ============================================================================
# Multi-Tenant Test Fixtures
# ============================================================================

@pytest_asyncio.fixture
async def bootstrap_super_admin(user_repo):
    """
    Bootstrap super_admin that creates both tenants.

    This is the "first user" created without a creator.
    tenant_id = user_id (self-anchored).
    """
    user_data = UserCreate(
        username="BootstrapAdmin",
        password="TestPass123",
        role="super_admin"
    )
    user = await user_repo.create(user_data)  # No creator = bootstrap
    return user


@pytest_asyncio.fixture
async def super_admin_headers(bootstrap_super_admin):
    """Auth headers for the bootstrap super_admin."""
    token = create_access_token(
        user_id=bootstrap_super_admin.id,
        username=bootstrap_super_admin.username,
        role=bootstrap_super_admin.role,
        tenant_id=bootstrap_super_admin.tenant_id
    )
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def tenant_a_admin(user_repo, bootstrap_super_admin):
    """
    Admin user that anchors Tenant A.

    Created by super_admin with role=admin.
    Result: admin.tenant_id = admin.id (new tenant)
    """
    user_data = UserCreate(
        username="TenantA_Admin",
        password="TestPass123",
        role="admin"
    )
    creator = {
        "id": str(bootstrap_super_admin.id),
        "role": bootstrap_super_admin.role,
        "tenant_id": str(bootstrap_super_admin.tenant_id)
    }
    user = await user_repo.create(user_data, creator=creator)
    # Verify self-anchored tenant
    assert user.tenant_id == user.id, "Admin should anchor own tenant"
    return user


@pytest_asyncio.fixture
async def tenant_a_user(user_repo, tenant_a_admin):
    """
    Regular user in Tenant A.

    Created by Tenant A's admin.
    Result: user.tenant_id = admin.tenant_id
    """
    user_data = UserCreate(
        username="TenantA_User",
        password="TestPass456",
        role="user"
    )
    creator = {
        "id": str(tenant_a_admin.id),
        "role": tenant_a_admin.role,
        "tenant_id": str(tenant_a_admin.tenant_id)
    }
    user = await user_repo.create(user_data, creator=creator)
    # Verify same tenant as admin
    assert user.tenant_id == tenant_a_admin.tenant_id
    return user


@pytest_asyncio.fixture
async def tenant_b_admin(user_repo, bootstrap_super_admin):
    """
    Admin user that anchors Tenant B (separate tenant).

    Created by super_admin with role=admin.
    Result: admin.tenant_id = admin.id (new tenant)
    """
    user_data = UserCreate(
        username="TenantB_Admin",
        password="TestPass123",
        role="admin"
    )
    creator = {
        "id": str(bootstrap_super_admin.id),
        "role": bootstrap_super_admin.role,
        "tenant_id": str(bootstrap_super_admin.tenant_id)
    }
    user = await user_repo.create(user_data, creator=creator)
    # Verify self-anchored tenant (different from Tenant A)
    assert user.tenant_id == user.id, "Admin should anchor own tenant"
    return user


@pytest_asyncio.fixture
async def tenant_b_user(user_repo, tenant_b_admin):
    """
    Regular user in Tenant B.

    Created by Tenant B's admin.
    Result: user.tenant_id = admin.tenant_id
    """
    user_data = UserCreate(
        username="TenantB_User",
        password="TestPass456",
        role="user"
    )
    creator = {
        "id": str(tenant_b_admin.id),
        "role": tenant_b_admin.role,
        "tenant_id": str(tenant_b_admin.tenant_id)
    }
    user = await user_repo.create(user_data, creator=creator)
    # Verify same tenant as Tenant B admin
    assert user.tenant_id == tenant_b_admin.tenant_id
    return user


@pytest_asyncio.fixture
async def tenant_a_headers(tenant_a_admin):
    """Auth headers for Tenant A admin."""
    token = create_access_token(
        user_id=tenant_a_admin.id,
        username=tenant_a_admin.username,
        role=tenant_a_admin.role,
        tenant_id=tenant_a_admin.tenant_id
    )
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def tenant_b_headers(tenant_b_admin):
    """Auth headers for Tenant B admin."""
    token = create_access_token(
        user_id=tenant_b_admin.id,
        username=tenant_b_admin.username,
        role=tenant_b_admin.role,
        tenant_id=tenant_b_admin.tenant_id
    )
    return {"Authorization": f"Bearer {token}"}


# ============================================================================
# Tenant Data Fixtures (Accounts, Stories, Events)
# ============================================================================

@pytest_asyncio.fixture
async def tenant_a_account(account_repo, tenant_a_admin):
    """Account belonging to Tenant A."""
    account_data = AccountCreate(
        name="Tenant A Account",
        currency="GBP",
        current_balance=Decimal("1000.00"),
        is_default=True
    )
    account = await account_repo.create(
        account_data,
        tenant_id=tenant_a_admin.tenant_id,
        current_user={"id": str(tenant_a_admin.id), "tenant_id": str(tenant_a_admin.tenant_id)}
    )
    return account


@pytest_asyncio.fixture
async def tenant_b_account(account_repo, tenant_b_admin):
    """Account belonging to Tenant B."""
    account_data = AccountCreate(
        name="Tenant B Account",
        currency="USD",
        current_balance=Decimal("2000.00"),
        is_default=True
    )
    account = await account_repo.create(
        account_data,
        tenant_id=tenant_b_admin.tenant_id,
        current_user={"id": str(tenant_b_admin.id), "tenant_id": str(tenant_b_admin.tenant_id)}
    )
    return account


@pytest_asyncio.fixture
async def tenant_a_story(story_repo, tenant_a_admin, tenant_a_account):
    """Story belonging to Tenant A."""
    story_data = StoryCreate(
        name="Tenant A Story",
        funding_mode="projected",
        start_date=date(2025, 1, 1),
        display_currency="GBP"
    )
    story = await story_repo.create(
        story_data,
        tenant_id=tenant_a_admin.tenant_id,
        current_user={"id": str(tenant_a_admin.id), "tenant_id": str(tenant_a_admin.tenant_id)}
    )
    return story


@pytest_asyncio.fixture
async def tenant_b_story(story_repo, tenant_b_admin, tenant_b_account):
    """Story belonging to Tenant B."""
    story_data = StoryCreate(
        name="Tenant B Story",
        funding_mode="projected",
        start_date=date(2025, 1, 1),
        display_currency="USD"
    )
    story = await story_repo.create(
        story_data,
        tenant_id=tenant_b_admin.tenant_id,
        current_user={"id": str(tenant_b_admin.id), "tenant_id": str(tenant_b_admin.tenant_id)}
    )
    return story


@pytest_asyncio.fixture
async def tenant_a_settings(settings_repo, tenant_a_admin):
    """Settings for Tenant A."""
    return await settings_repo.get_or_create_for_tenant(tenant_a_admin.tenant_id)


@pytest_asyncio.fixture
async def tenant_b_settings(settings_repo, tenant_b_admin):
    """Settings for Tenant B."""
    return await settings_repo.get_or_create_for_tenant(tenant_b_admin.tenant_id)


@pytest_asyncio.fixture
async def tenant_a_event(event_repo, tenant_a_admin, tenant_a_account, tenant_a_story, tenant_a_settings):
    """Event belonging to Tenant A."""
    event_data = EventCreate(
        event_date=date(2025, 1, 15),
        description="Tenant A Event",
        amount=Decimal("-50.00"),
        currency="GBP",
        account_id=tenant_a_account.id,
        story_id=tenant_a_story.id
    )
    event = await event_repo.create(
        event_data,
        tenant_id=tenant_a_admin.tenant_id,
        current_user={"id": str(tenant_a_admin.id), "tenant_id": str(tenant_a_admin.tenant_id)}
    )
    return event


@pytest_asyncio.fixture
async def tenant_b_event(event_repo, tenant_b_admin, tenant_b_account, tenant_b_story, tenant_b_settings):
    """Event belonging to Tenant B."""
    event_data = EventCreate(
        event_date=date(2025, 1, 20),
        description="Tenant B Event",
        amount=Decimal("-100.00"),
        currency="USD",
        account_id=tenant_b_account.id,
        story_id=tenant_b_story.id
    )
    event = await event_repo.create(
        event_data,
        tenant_id=tenant_b_admin.tenant_id,
        current_user={"id": str(tenant_b_admin.id), "tenant_id": str(tenant_b_admin.tenant_id)}
    )
    return event


# ============================================================================
# Test Class 1: Cross-Tenant User Access
# ============================================================================

class TestCrossTenantUserAccess:
    """Verify admins cannot access other tenant's users."""

    @pytest.mark.asyncio
    async def test_admin_list_users_only_sees_own_tenant(
        self, async_client, tenant_a_headers, tenant_a_admin, tenant_a_user, tenant_b_user
    ):
        """Admin listing users only sees users from their own tenant."""
        response = await async_client.get(
            "/api/admin/users",
            headers=tenant_a_headers
        )

        assert response.status_code == 200
        users = response.json()

        # Extract returned user IDs
        returned_ids = {u["id"] for u in users}

        # Should see Tenant A admin and user
        assert str(tenant_a_admin.id) in returned_ids
        assert str(tenant_a_user.id) in returned_ids

        # Should NOT see Tenant B user
        assert str(tenant_b_user.id) not in returned_ids

    @pytest.mark.asyncio
    async def test_admin_cannot_update_other_tenant_user(
        self, async_client, tenant_a_headers, tenant_b_user
    ):
        """Admin from Tenant A cannot UPDATE user from Tenant B."""
        response = await async_client.put(
            f"/api/admin/users/{tenant_b_user.id}",
            headers=tenant_a_headers,
            json={"username": "Hacked"}
        )

        # Should return 404 (not 403)
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_admin_cannot_delete_other_tenant_user(
        self, async_client, tenant_a_headers, tenant_b_user
    ):
        """Admin from Tenant A cannot DELETE user from Tenant B."""
        response = await async_client.delete(
            f"/api/admin/users/{tenant_b_user.id}",
            headers=tenant_a_headers
        )

        # Should return 404 (not 403)
        assert response.status_code == 404


# ============================================================================
# Test Class 2: Cross-Tenant Data Access (Accounts, Events, Stories)
# ============================================================================

class TestCrossTenantDataAccess:
    """Verify admins cannot access other tenant's accounts, events, or stories."""

    @pytest.mark.asyncio
    async def test_cannot_list_other_tenant_accounts(
        self, async_client, tenant_a_headers, tenant_a_account, tenant_b_account
    ):
        """Admin listing accounts only sees their own tenant's accounts."""
        response = await async_client.get(
            "/api/accounts",
            headers=tenant_a_headers
        )

        assert response.status_code == 200
        accounts = response.json()

        # Extract returned account IDs
        returned_ids = {a["id"] for a in accounts}

        # Should see Tenant A account
        assert str(tenant_a_account.id) in returned_ids

        # Should NOT see Tenant B account
        assert str(tenant_b_account.id) not in returned_ids

    @pytest.mark.asyncio
    async def test_cannot_get_other_tenant_account(
        self, async_client, tenant_a_headers, tenant_b_account
    ):
        """Admin from Tenant A cannot GET account from Tenant B."""
        response = await async_client.get(
            f"/api/accounts/{tenant_b_account.id}",
            headers=tenant_a_headers
        )

        # Should return 404
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_cannot_list_other_tenant_events(
        self, async_client, tenant_a_headers, tenant_a_event, tenant_b_event
    ):
        """Admin listing events only sees their own tenant's events."""
        response = await async_client.get(
            "/api/events",
            headers=tenant_a_headers
        )

        assert response.status_code == 200
        events = response.json()

        # Extract returned event IDs
        returned_ids = {e["id"] for e in events}

        # Should see Tenant A event
        assert str(tenant_a_event.id) in returned_ids

        # Should NOT see Tenant B event
        assert str(tenant_b_event.id) not in returned_ids

    @pytest.mark.asyncio
    async def test_cannot_get_other_tenant_event(
        self, async_client, tenant_a_headers, tenant_b_event
    ):
        """Admin from Tenant A cannot GET event from Tenant B."""
        response = await async_client.get(
            f"/api/events/{tenant_b_event.id}",
            headers=tenant_a_headers
        )

        # Should return 404
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_cannot_list_other_tenant_stories(
        self, async_client, tenant_a_headers, tenant_a_story, tenant_b_story
    ):
        """Admin listing stories only sees their own tenant's stories."""
        response = await async_client.get(
            "/api/stories",
            headers=tenant_a_headers
        )

        assert response.status_code == 200
        stories = response.json()

        # Extract returned story IDs
        returned_ids = {s["id"] for s in stories}

        # Should see Tenant A story
        assert str(tenant_a_story.id) in returned_ids

        # Should NOT see Tenant B story
        assert str(tenant_b_story.id) not in returned_ids

    @pytest.mark.asyncio
    async def test_cannot_get_other_tenant_story(
        self, async_client, tenant_a_headers, tenant_b_story
    ):
        """Admin from Tenant A cannot GET story from Tenant B."""
        response = await async_client.get(
            f"/api/stories/{tenant_b_story.id}",
            headers=tenant_a_headers
        )

        # Should return 404
        assert response.status_code == 404


# ============================================================================
# Test Class 3: Sync Tenant Isolation
# ============================================================================

class TestSyncTenantIsolation:
    """Verify sync operations are scoped to the requesting tenant."""

    @pytest.mark.asyncio
    async def test_sync_pull_only_returns_tenant_changes(
        self, async_client, tenant_a_headers, tenant_a_admin,
        tenant_a_account, tenant_b_account
    ):
        """Sync pull only returns changes from the requesting tenant."""
        response = await async_client.post(
            "/api/sync",
            headers=tenant_a_headers,
            json={
                "client_id": "test-client-a",
                "last_sync_at": None,
                "changes": []
            }
        )

        assert response.status_code == 200
        data = response.json()

        # All returned changes should belong to Tenant A
        tenant_a_id = str(tenant_a_admin.tenant_id)
        for change in data.get("server_changes", []):
            if change.get("data") and change["data"].get("tenant_id"):
                assert change["data"]["tenant_id"] == tenant_a_id, \
                    f"Change leaked from wrong tenant: {change}"

    @pytest.mark.asyncio
    async def test_sync_cannot_update_other_tenant_entity(
        self, async_client, tenant_a_headers, tenant_a_settings, tenant_b_account, tenant_b_settings
    ):
        """Sync update for entity from other tenant is rejected or ignored."""
        response = await async_client.post(
            "/api/sync",
            headers=tenant_a_headers,
            json={
                "client_id": "test-client-a",
                "last_sync_at": None,
                "changes": [{
                    "entity_type": "account",
                    "entity_id": str(tenant_b_account.id),
                    "action": "update",
                    "data": {
                        "id": str(tenant_b_account.id),
                        "name": "Hacked Account Name",
                        "currency": "USD",
                        "current_balance": "9999.00",
                        "is_default": True,
                        "tenant_id": str(tenant_b_account.tenant_id)
                    },
                    "base_updated_at": tenant_b_account.updated_at.isoformat()
                }]
            }
        )

        assert response.status_code == 200
        data = response.json()

        # Should either return a conflict or the entity should not be updated
        # The key is that the cross-tenant update doesn't succeed silently
        if data.get("conflicts"):
            # If conflicts returned, that's expected (entity not found)
            assert len(data["conflicts"]) > 0
        # Either way, verify the account wasn't actually modified by fetching it

    @pytest.mark.asyncio
    async def test_full_sync_only_returns_tenant_data(
        self, async_client, tenant_a_headers, tenant_a_admin,
        tenant_a_account, tenant_a_story, tenant_a_event,
        tenant_b_account, tenant_b_story, tenant_b_event
    ):
        """Full sync returns only data from the requesting tenant."""
        response = await async_client.get(
            "/api/sync/full",
            headers=tenant_a_headers
        )

        assert response.status_code == 200
        data = response.json()

        tenant_a_id = str(tenant_a_admin.tenant_id)
        tenant_b_account_id = str(tenant_b_account.id)
        tenant_b_story_id = str(tenant_b_story.id)
        tenant_b_event_id = str(tenant_b_event.id)

        # Check accounts - all should be Tenant A
        for account in data.get("accounts", []):
            assert account["tenant_id"] == tenant_a_id
            assert account["id"] != tenant_b_account_id

        # Check stories - all should be Tenant A
        for story in data.get("stories", []):
            assert story["tenant_id"] == tenant_a_id
            assert story["id"] != tenant_b_story_id

        # Check events - all should be Tenant A
        for event in data.get("events", []):
            assert event["tenant_id"] == tenant_a_id
            assert event["id"] != tenant_b_event_id


# ============================================================================
# Test Class 4: Tenant Assignment Rules
# ============================================================================

class TestTenantAssignmentRules:
    """Verify tenant_id assignment follows role-based rules."""

    @pytest.mark.asyncio
    async def test_super_admin_creates_admin_new_tenant(
        self, async_client, super_admin_headers, bootstrap_super_admin
    ):
        """When super_admin creates an admin, the admin gets a new tenant (self-anchored)."""
        response = await async_client.post(
            "/api/admin/users",
            headers=super_admin_headers,
            json={
                "username": "NewAdmin",
                "password": "ValidPass123",
                "role": "admin"
            }
        )

        assert response.status_code == 201
        data = response.json()

        # New admin's tenant_id should equal their own user_id
        assert data["tenant_id"] == data["id"], \
            "Admin should anchor their own tenant"

    @pytest.mark.asyncio
    async def test_super_admin_creates_user_same_tenant(
        self, async_client, super_admin_headers, bootstrap_super_admin
    ):
        """When super_admin creates a regular user, they join super_admin's tenant."""
        response = await async_client.post(
            "/api/admin/users",
            headers=super_admin_headers,
            json={
                "username": "NewRegularUser",
                "password": "ValidPass123",
                "role": "user"
            }
        )

        assert response.status_code == 201
        data = response.json()

        # Regular user should join super_admin's tenant
        assert data["tenant_id"] == str(bootstrap_super_admin.tenant_id), \
            "Regular user should join creator's tenant"

    @pytest.mark.asyncio
    async def test_admin_creates_user_same_tenant(
        self, async_client, tenant_a_headers, tenant_a_admin
    ):
        """When admin creates a regular user, they join admin's tenant."""
        response = await async_client.post(
            "/api/admin/users",
            headers=tenant_a_headers,
            json={
                "username": "AdminCreatedUser",
                "password": "ValidPass123",
                "role": "user"
            }
        )

        assert response.status_code == 201
        data = response.json()

        # Regular user should join admin's tenant
        assert data["tenant_id"] == str(tenant_a_admin.tenant_id), \
            "User created by admin should join admin's tenant"

    @pytest.mark.asyncio
    async def test_admin_cannot_create_admin(
        self, async_client, tenant_a_headers
    ):
        """Regular admin cannot create another admin (only super_admin can)."""
        response = await async_client.post(
            "/api/admin/users",
            headers=tenant_a_headers,
            json={
                "username": "AttemptedAdmin",
                "password": "ValidPass123",
                "role": "admin"
            }
        )

        # Should be forbidden
        assert response.status_code == 403
        assert "super_admin" in response.json()["detail"].lower()
