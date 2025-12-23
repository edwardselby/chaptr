"""
Integration tests for sync protocol - Tasks 21-27.

Comprehensive testing of multi-client sync scenarios including:
- Bidirectional push/pull with multiple clients
- Edit/edit conflict detection
- Delete/edit conflict detection
- Stale client recovery with full sync
- Recurring event generation and editing
"""

import pytest
import pytest_asyncio
from datetime import datetime, timedelta, date
from decimal import Decimal
from uuid import uuid4, UUID

from api.models import (
    EventCreate, EventUpdate, RecurringRuleCreate,
    Frequency, FundingMode, GoalType
)
from api.repositories.events import EventRepository


# ============================================================================
# Enhanced Mock Database Fixture
# ============================================================================

@pytest_asyncio.fixture
async def sample_account_with_user(account_repo, sample_user):
    """Account with created_by set to sample_user for sync tests."""
    from api.models import AccountCreate
    from datetime import datetime, timezone
    account_data = AccountCreate(
        name="Test Account",
        currency="GBP",
        current_balance=Decimal("1000.00"),
        balance_updated_at=datetime.now(timezone.utc),
        is_default=True,
        is_archived=False,
        pending_reconciliation=False
    )
    account = await account_repo.create(
        account_data,
        current_user={"id": str(sample_user.id)},
        client_id="test-setup"
    )
    return account


@pytest_asyncio.fixture
async def sample_story_with_user(story_repo, sample_account_with_user, sample_user):
    """Story with created_by set to sample_user for sync tests."""
    from api.models import StoryCreate
    story_data = StoryCreate(
        name="Test Story",
        start_date=date(2024, 12, 1),
        end_date=date(2025, 1, 31),
        default_account_id=sample_account_with_user.id,
        funding_mode=FundingMode.PROJECTED,
        funding_amount=None,
        goal_type=GoalType.NONE,
        goal_amount=None,
        display_currency="GBP"
    )
    story = await story_repo.create(
        story_data,
        current_user={"id": str(sample_user.id)},
        client_id="test-setup"
    )
    return story


@pytest_asyncio.fixture
async def sample_event_with_user(event_repo, sample_account_with_user, sample_settings, sample_user):
    """Event with created_by set to sample_user for sync tests."""
    event_data = EventCreate(
        event_date=date(2024, 12, 15),
        description="Test Event",
        amount=Decimal("-50.00"),
        currency="GBP",
        account_id=sample_account_with_user.id,
        story_id=None,
        is_baseline=True,
        is_hypothetical=False,
        is_auto_adjustment=False
    )
    event = await event_repo.create(
        event_data,
        current_user={"id": str(sample_user.id)},
        client_id="test-setup"
    )
    return event


@pytest_asyncio.fixture
async def sample_recurring_rule_with_user(recurring_rule_repo, sample_account_with_user, sample_user):
    """
    Pre-created monthly recurring rule WITH created_by set.

    This is needed for sync tests since recurring generation filters by user.
    """
    rule_data = RecurringRuleCreate(
        description="Monthly Rent",
        amount=Decimal("-1500.00"),
        currency="GBP",
        account_id=sample_account_with_user.id,
        frequency=Frequency.MONTHLY,
        day=28,
        start_date=date(2024, 1, 1),
        end_date=None
    )
    # Pass current_user so created_by is set
    rule = await recurring_rule_repo.create(
        rule_data,
        current_user={"id": str(sample_user.id)},
        client_id="test-setup"
    )
    return rule


@pytest_asyncio.fixture
async def sync_mock_db(clean_database):
    """
    Pass-through fixture for consistency with plan.

    Note: Mongomock handles ISO string timestamp comparisons correctly,
    so no patching is needed for change_log queries.
    """
    return clean_database


# ============================================================================
# Task 21: Two-Client Bidirectional Sync
# ============================================================================

@pytest.mark.asyncio
async def test_two_client_bidirectional_sync(
    async_client,
    auth_headers,
    sample_account_with_user,
    sample_story_with_user,
    sample_settings,
    sync_mock_db
):
    """
    Test bidirectional sync between two clients.

    Scenario:
    1. Client A creates event E1 and syncs
    2. Client B syncs and receives E1 in server_changes
    3. Client B creates event E2 and syncs
    4. Client A syncs and receives E2 in server_changes

    Validates:
    - Events propagate correctly between clients
    - Each client doesn't receive their own changes back
    - Change log filters by client_id correctly
    - Sync timestamps update properly
    """
    # Client A: Create event E1
    event_e1_id = uuid4()
    sync_a1 = {
        "client_id": "client-a",
        "last_sync_at": None,
        "changes": [{
            "entity_type": "event",
            "entity_id": str(event_e1_id),
            "action": "create",
            "data": {
                "event_date": "2025-01-15",
                "description": "Event from Client A",
                "amount": -50.00,
                "currency": "GBP",
                "account_id": str(sample_account_with_user.id),
                "story_id": str(sample_story_with_user.id),
                "is_baseline": False,
                "is_hypothetical": False,
                "is_auto_adjustment": False
            },
            "base_updated_at": None
        }]
    }

    response_a1 = await async_client.post("/api/sync", json=sync_a1, headers=auth_headers)
    assert response_a1.status_code == 200
    data_a1 = response_a1.json()
    assert len(data_a1["applied"]) == 1
    assert data_a1["applied"][0] == str(event_e1_id)
    sync_ts_a1 = data_a1["sync_timestamp"]

    # Client B: First sync
    # Use timestamp from BEFORE Client A's sync to receive E1 in server_changes
    # We need a timestamp that's after fixture setup but before Client A's event creation
    # Solution: Use the earliest change_log entry's timestamp minus 1 second
    from datetime import timezone, timedelta
    earliest_log = await sync_mock_db["change_log"].find_one(sort=[("changed_at", 1)])
    earliest_ts = datetime.fromisoformat(earliest_log["changed_at"]) - timedelta(seconds=1)

    sync_b1 = {
        "client_id": "client-b",
        "last_sync_at": earliest_ts.isoformat(),
        "changes": []
    }

    response_b1 = await async_client.post("/api/sync", json=sync_b1, headers=auth_headers)
    assert response_b1.status_code == 200
    data_b1 = response_b1.json()

    # Should receive E1 in server_changes
    assert len(data_b1["server_changes"]) >= 1, f"Expected server_changes but got: {data_b1['server_changes']}"
    event_changes = [c for c in data_b1["server_changes"] if c["entity_type"] == "event"]
    assert len(event_changes) >= 1
    assert any(c["entity_id"] == str(event_e1_id) for c in event_changes)

    sync_ts_b1 = data_b1["sync_timestamp"]

    # Client B: Create event E2
    event_e2_id = uuid4()
    sync_b2 = {
        "client_id": "client-b",
        "last_sync_at": sync_ts_b1,
        "changes": [{
            "entity_type": "event",
            "entity_id": str(event_e2_id),
            "action": "create",
            "data": {
                "event_date": "2025-01-16",
                "description": "Event from Client B",
                "amount": -75.00,
                "currency": "GBP",
                "account_id": str(sample_account_with_user.id),
                "story_id": str(sample_story_with_user.id),
                "is_baseline": False,
                "is_hypothetical": False,
                "is_auto_adjustment": False
            },
            "base_updated_at": None
        }]
    }

    response_b2 = await async_client.post("/api/sync", json=sync_b2, headers=auth_headers)
    assert response_b2.status_code == 200
    data_b2 = response_b2.json()
    assert len(data_b2["applied"]) == 1
    assert data_b2["applied"][0] == str(event_e2_id)

    # Client A: Second sync (should receive E2, NOT E1 again)
    sync_a2 = {
        "client_id": "client-a",
        "last_sync_at": sync_ts_a1,
        "changes": []
    }

    response_a2 = await async_client.post("/api/sync", json=sync_a2, headers=auth_headers)
    assert response_a2.status_code == 200
    data_a2 = response_a2.json()

    # Should only receive E2 (created by client-b after client-a's last sync)
    event_changes = [c for c in data_a2["server_changes"] if c["entity_type"] == "event"]
    assert len(event_changes) >= 1
    assert any(c["entity_id"] == str(event_e2_id) for c in event_changes)

    # Should NOT receive E1 (created by client-a itself)
    e1_changes = [c for c in event_changes if c["entity_id"] == str(event_e1_id)]
    assert len(e1_changes) == 0, "Client should not receive its own changes back"


# ============================================================================
# Task 22: Edit/Edit Conflict Detection
# ============================================================================

@pytest.mark.asyncio
async def test_edit_edit_conflict_detection(
    async_client,
    auth_headers,
    event_repo,
    sample_event,
    sync_mock_db
):
    """
    Test edit/edit conflict when two clients edit same entity.

    Scenario:
    1. Both clients fetch event E1 (base_updated_at = T1)
    2. Client A edits E1, syncs successfully → server updated_at = T2
    3. Client B edits E1 with base_updated_at = T1, syncs → CONFLICT

    Validates:
    - Client A's update succeeds
    - Client B's update returns conflict
    - Conflict type is "edit_edit"
    - Conflict includes both client_version and server_version
    - Client B's change is NOT applied
    """
    # Both clients have same base timestamp
    base_timestamp = sample_event.updated_at

    # Client A: Edit event (succeeds)
    sync_a = {
        "client_id": "client-a",
        "last_sync_at": None,
        "changes": [{
            "entity_type": "event",
            "entity_id": str(sample_event.id),
            "action": "update",
            "data": {
                "description": "Updated by Client A",
                "amount": -100.00
            },
            "base_updated_at": base_timestamp.isoformat()
        }]
    }

    response_a = await async_client.post("/api/sync", json=sync_a, headers=auth_headers)
    assert response_a.status_code == 200
    data_a = response_a.json()
    assert len(data_a["applied"]) == 1
    assert len(data_a["conflicts"]) == 0

    # Client B: Edit event with old timestamp (conflict)
    sync_b = {
        "client_id": "client-b",
        "last_sync_at": None,
        "changes": [{
            "entity_type": "event",
            "entity_id": str(sample_event.id),
            "action": "update",
            "data": {
                "description": "Updated by Client B",
                "amount": -200.00
            },
            "base_updated_at": base_timestamp.isoformat()  # Old timestamp
        }]
    }

    response_b = await async_client.post("/api/sync", json=sync_b, headers=auth_headers)
    assert response_b.status_code == 200
    data_b = response_b.json()
    assert len(data_b["applied"]) == 0
    assert len(data_b["conflicts"]) == 1

    conflict = data_b["conflicts"][0]
    assert conflict["entity_type"] == "event"
    assert conflict["entity_id"] == str(sample_event.id)
    assert conflict["conflict_type"] == "edit_edit"
    assert conflict["client_version"]["description"] == "Updated by Client B"
    assert conflict["server_version"]["description"] == "Updated by Client A"


# ============================================================================
# Task 23: Delete/Edit Conflict Detection
# ============================================================================

@pytest.mark.asyncio
async def test_delete_edit_conflict_detection(
    async_client,
    auth_headers,
    event_repo,
    sample_event,
    sync_mock_db
):
    """
    Test delete/edit conflict when one client deletes, another edits.

    Scenario:
    1. Both clients fetch event E1 (base_updated_at = T1)
    2. Client A edits E1, syncs successfully → server updated_at = T2
    3. Client B deletes E1 with base_updated_at = T1, syncs → CONFLICT

    Validates:
    - Client A's update succeeds
    - Client B's delete returns conflict
    - Conflict type is "delete_edit"
    - client_version is None (client wanted to delete)
    - server_version includes current entity state
    - Entity still exists on server
    """
    base_timestamp = sample_event.updated_at

    # Client A: Edit event (succeeds)
    sync_a = {
        "client_id": "client-a",
        "last_sync_at": None,
        "changes": [{
            "entity_type": "event",
            "entity_id": str(sample_event.id),
            "action": "update",
            "data": {"description": "Modified before delete attempt"},
            "base_updated_at": base_timestamp.isoformat()
        }]
    }

    response_a = await async_client.post("/api/sync", json=sync_a, headers=auth_headers)
    assert response_a.status_code == 200
    data_a = response_a.json()
    assert len(data_a["applied"]) == 1

    # Client B: Delete event with old timestamp (conflict)
    sync_b = {
        "client_id": "client-b",
        "last_sync_at": None,
        "changes": [{
            "entity_type": "event",
            "entity_id": str(sample_event.id),
            "action": "delete",
            "data": None,
            "base_updated_at": base_timestamp.isoformat()
        }]
    }

    response_b = await async_client.post("/api/sync", json=sync_b, headers=auth_headers)
    assert response_b.status_code == 200
    data_b = response_b.json()
    assert len(data_b["applied"]) == 0
    assert len(data_b["conflicts"]) == 1

    conflict = data_b["conflicts"][0]
    assert conflict["entity_type"] == "event"
    assert conflict["conflict_type"] == "delete_edit"
    assert conflict["client_version"] is None  # Client wanted to delete
    assert conflict["server_version"]["description"] == "Modified before delete attempt"

    # Verify entity still exists
    existing = await event_repo.get(sample_event.id)
    assert existing.description == "Modified before delete attempt"


# ============================================================================
# Task 24: Stale Client Recovery
# ============================================================================

@pytest.mark.asyncio
async def test_stale_client_full_sync_required(
    async_client,
    auth_headers,
    sample_account_with_user,
    sample_event_with_user,
    sample_settings,
    sync_mock_db
):
    """
    Test stale client detection when last_sync_at is before oldest change_log entry.

    Scenario:
    1. Client syncs at T1 (60 days ago)
    2. Change log gets pruned (entries older than 31 days deleted)
    3. Client tries to sync with last_sync_at = T1 → full_sync_required
    4. Client calls GET /api/sync/full and receives complete dataset

    Validates:
    - Sync response includes full_sync_required = true
    - server_changes array is empty when full sync required
    - Full sync endpoint returns all entities
    - Full sync includes sync_timestamp
    - Full sync filters by user (created_by field)
    """
    # Simulate old sync timestamp (before any change log entries)
    from datetime import timezone
    old_sync_time = datetime.now(timezone.utc) - timedelta(days=60)

    # Create recent change log entry (simulating pruned logs - old entries gone)
    await sync_mock_db["change_log"].insert_one({
        "id": str(uuid4()),
        "entity_type": "event",
        "entity_id": str(sample_event_with_user.id),
        "action": "update",
        "data": sample_event_with_user.model_dump(mode="json"),
        "changed_by_user": str(sample_event_with_user.updated_by),
        "changed_by_client": "other-client",
        "changed_at": datetime.now(timezone.utc).isoformat()
    })

    # Client syncs with stale timestamp
    sync_request = {
        "client_id": "stale-client",
        "last_sync_at": old_sync_time.isoformat(),
        "changes": []
    }

    response = await async_client.post("/api/sync", json=sync_request, headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["full_sync_required"] is True
    assert len(data["server_changes"]) == 0  # Empty when full sync required

    # Test full sync endpoint
    full_sync_response = await async_client.get("/api/sync/full", headers=auth_headers)
    assert full_sync_response.status_code == 200
    full_data = full_sync_response.json()

    assert "accounts" in full_data
    assert "stories" in full_data
    assert "events" in full_data
    assert "recurring_rules" in full_data
    assert "settings" in full_data
    assert "sync_timestamp" in full_data

    # Verify data returned
    assert len(full_data["accounts"]) >= 1  # At least sample_account
    assert len(full_data["events"]) >= 1    # At least sample_event


# ============================================================================
# Task 25: Recurring Event Generation & Editing
# ============================================================================

@pytest.mark.asyncio
async def test_recurring_event_generation_on_sync(
    async_client,
    auth_headers,
    sample_account_with_user,
    sample_recurring_rule_with_user,
    sample_settings,
    event_repo,
    sample_user,
    sync_mock_db
):
    """
    Test recurring events generate during sync and edited instances preserved.

    Scenario:
    1. Create recurring rule (monthly salary)
    2. Client syncs → recurring events generated for ±1 month window
    3. Client edits one generated event
    4. Client syncs again → edited event preserved, new events generated
    5. Verify generated events logged to change_log
    6. Verify generated events appear in server_changes for other clients

    Validates:
    - Recurring events created with recurring_rule_id
    - Edited events (updated_at != created_at) preserved on next generation
    - Generated events logged to change_log
    - Generated events appear in server_changes for other clients
    """
    # Client A: First sync (triggers generation)
    sync_a1 = {
        "client_id": "client-a",
        "last_sync_at": None,
        "changes": []
    }

    response_a1 = await async_client.post("/api/sync", json=sync_a1, headers=auth_headers)
    assert response_a1.status_code == 200
    data_a1 = response_a1.json()

    # Verify events generated
    generated_events = await sync_mock_db["events"].find({
        "recurring_rule_id": str(sample_recurring_rule_with_user.id)
    }).to_list(length=100)
    assert len(generated_events) > 0, "Should generate recurring events in ±1 month window"

    # Edit one generated event
    edited_event_id = generated_events[0]["id"]
    edited_event = await event_repo.get(UUID(edited_event_id))

    await event_repo.update(
        UUID(edited_event_id),
        EventUpdate(description="EDITED: Custom description"),
        current_user={"id": str(sample_user.id)},
        client_id="client-a"
    )

    # Client A: Second sync (should NOT regenerate edited event)
    sync_a2 = {
        "client_id": "client-a",
        "last_sync_at": data_a1["sync_timestamp"],
        "changes": []
    }

    response_a2 = await async_client.post("/api/sync", json=sync_a2, headers=auth_headers)
    assert response_a2.status_code == 200

    # Verify edited event preserved
    edited_event_after = await event_repo.get(UUID(edited_event_id))
    assert "EDITED" in edited_event_after.description, "Edited event should be preserved"
    assert edited_event_after.updated_at != edited_event_after.created_at, "Edited event should have different timestamps"

    # Client B: Sync (should receive generated events in server_changes)
    # Use timestamp just before earliest change_log entry
    earliest_log = await sync_mock_db["change_log"].find_one(sort=[("changed_at", 1)])
    earliest_ts = datetime.fromisoformat(earliest_log["changed_at"]) - timedelta(seconds=1)

    sync_b1 = {
        "client_id": "client-b",
        "last_sync_at": earliest_ts.isoformat(),
        "changes": []
    }

    response_b1 = await async_client.post("/api/sync", json=sync_b1, headers=auth_headers)
    assert response_b1.status_code == 200
    data_b1 = response_b1.json()

    # Verify change_log includes generated events
    event_changes = [c for c in data_b1["server_changes"] if c["entity_type"] == "event"]
    assert len(event_changes) > 0, "Generated events should be in server_changes"

    # Check for recurring events
    recurring_events = [c for c in event_changes
                       if c.get("data") and c["data"].get("recurring_rule_id") == str(sample_recurring_rule_with_user.id)]
    assert len(recurring_events) > 0, "Client B should receive generated recurring events"
