"""
Integration tests for sync protocol - Tasks 21-27.

Comprehensive testing of multi-client sync scenarios including:
- Bidirectional push/pull with multiple clients
- Edit/edit conflict detection
- Delete/edit conflict detection
- Stale client recovery with full sync
- Recurring event generation and editing

**Uses real MongoDB** for accurate change_log query simulation.
Mark tests with @pytest.mark.integration for selective execution.
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
# Test Fixtures - Now using conftest.py fixtures instead of local overrides
# ============================================================================

# Removed local fixture overrides - using conftest.py versions with client_id=None

@pytest_asyncio.fixture
async def sample_recurring_rule_with_user(recurring_rule_repo_real, sample_account_with_user, sample_user_real):
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
    # Use client_id=None so fixture creation is NOT logged as a sync client change
    rule = await recurring_rule_repo_real.create(
        rule_data,
        current_user={"id": str(sample_user_real.id)},
        client_id=None  # Changed from "test-setup" to prevent change_log pollution
    )
    return rule


# ============================================================================
# Task 21: Two-Client Bidirectional Sync
# ============================================================================

@pytest.mark.integration
@pytest.mark.asyncio
async def test_two_client_bidirectional_sync(
    async_client_real,
    auth_headers_real,
    sample_account_with_user,
    sample_story_with_user,
    sample_settings_real,
    clean_database_real
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

    response_a1 = await async_client_real.post("/api/sync", json=sync_a1, headers=auth_headers_real)
    assert response_a1.status_code == 200
    data_a1 = response_a1.json()
    assert len(data_a1["applied"]) == 1
    assert data_a1["applied"][0] == str(event_e1_id)
    sync_ts_a1 = data_a1["sync_timestamp"]

    # Client B: First sync
    # Use timestamp from BEFORE Client A's sync to receive E1 in server_changes
    # We use the earliest change_log entry timestamp (after fixtures, before Client A's event)
    from datetime import timezone, timedelta
    earliest_log = await clean_database_real["change_log"].find_one(sort=[("changed_at", 1)])
    # Use the timestamp AS-IS (not minus 1 second) to avoid triggering stale client detection
    earliest_ts = datetime.fromisoformat(earliest_log["changed_at"])

    sync_b1 = {
        "client_id": "client-b",
        "last_sync_at": earliest_ts.isoformat(),
        "changes": []
    }

    response_b1 = await async_client_real.post("/api/sync", json=sync_b1, headers=auth_headers_real)
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

    response_b2 = await async_client_real.post("/api/sync", json=sync_b2, headers=auth_headers_real)
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

    response_a2 = await async_client_real.post("/api/sync", json=sync_a2, headers=auth_headers_real)
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
    async_client_real,
    auth_headers_real,
    event_repo_real,
    sample_event_with_user,
    clean_database_real
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
    base_timestamp = sample_event_with_user.updated_at

    # Client A: Edit event (succeeds)
    sync_a = {
        "client_id": "client-a",
        "last_sync_at": None,
        "changes": [{
            "entity_type": "event",
            "entity_id": str(sample_event_with_user.id),
            "action": "update",
            "data": {
                "description": "Updated by Client A",
                "amount": -100.00
            },
            "base_updated_at": base_timestamp.isoformat()
        }]
    }

    response_a = await async_client_real.post("/api/sync", json=sync_a, headers=auth_headers_real)
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
            "entity_id": str(sample_event_with_user.id),
            "action": "update",
            "data": {
                "description": "Updated by Client B",
                "amount": -200.00
            },
            "base_updated_at": base_timestamp.isoformat()  # Old timestamp
        }]
    }

    response_b = await async_client_real.post("/api/sync", json=sync_b, headers=auth_headers_real)
    assert response_b.status_code == 200
    data_b = response_b.json()
    assert len(data_b["applied"]) == 0
    assert len(data_b["conflicts"]) == 1

    conflict = data_b["conflicts"][0]
    assert conflict["entity_type"] == "event"
    assert conflict["entity_id"] == str(sample_event_with_user.id)
    assert conflict["conflict_type"] == "edit_edit"
    assert conflict["client_version"]["description"] == "Updated by Client B"
    assert conflict["server_version"]["description"] == "Updated by Client A"


# ============================================================================
# Task 23: Delete/Edit Conflict Detection
# ============================================================================

@pytest.mark.asyncio
async def test_delete_edit_conflict_detection(
    async_client_real,
    auth_headers_real,
    event_repo_real,
    sample_event_with_user,
    clean_database_real
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
    base_timestamp = sample_event_with_user.updated_at

    # Client A: Edit event (succeeds)
    sync_a = {
        "client_id": "client-a",
        "last_sync_at": None,
        "changes": [{
            "entity_type": "event",
            "entity_id": str(sample_event_with_user.id),
            "action": "update",
            "data": {"description": "Modified before delete attempt"},
            "base_updated_at": base_timestamp.isoformat()
        }]
    }

    response_a = await async_client_real.post("/api/sync", json=sync_a, headers=auth_headers_real)
    assert response_a.status_code == 200
    data_a = response_a.json()
    assert len(data_a["applied"]) == 1

    # Client B: Delete event with old timestamp (conflict)
    sync_b = {
        "client_id": "client-b",
        "last_sync_at": None,
        "changes": [{
            "entity_type": "event",
            "entity_id": str(sample_event_with_user.id),
            "action": "delete",
            "data": None,
            "base_updated_at": base_timestamp.isoformat()
        }]
    }

    response_b = await async_client_real.post("/api/sync", json=sync_b, headers=auth_headers_real)
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
    existing = await event_repo_real.get(sample_event_with_user.id)
    assert existing.description == "Modified before delete attempt"


# ============================================================================
# Task 24: Stale Client Recovery
# ============================================================================

@pytest.mark.integration
@pytest.mark.asyncio
async def test_stale_client_full_sync_required(
    async_client_real,
    auth_headers_real,
    sample_account_with_user,
    sample_event_with_user,
    sample_settings_real,
    clean_database_real
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
    await clean_database_real["change_log"].insert_one({
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

    response = await async_client_real.post("/api/sync", json=sync_request, headers=auth_headers_real)
    assert response.status_code == 200
    data = response.json()
    assert data["full_sync_required"] is True
    assert len(data["server_changes"]) == 0  # Empty when full sync required

    # Test full sync endpoint
    full_sync_response = await async_client_real.get("/api/sync/full", headers=auth_headers_real)
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

@pytest.mark.integration
@pytest.mark.asyncio
async def test_recurring_event_generation_on_sync(
    async_client_real,
    auth_headers_real,
    sample_account_with_user,
    sample_recurring_rule_with_user,
    sample_settings_real,
    event_repo_real,
    sample_user_real,
    clean_database_real
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

    response_a1 = await async_client_real.post("/api/sync", json=sync_a1, headers=auth_headers_real)
    assert response_a1.status_code == 200
    data_a1 = response_a1.json()

    # Verify events generated
    generated_events = await clean_database_real["events"].find({
        "recurring_rule_id": str(sample_recurring_rule_with_user.id)
    }).to_list(length=100)
    assert len(generated_events) > 0, "Should generate recurring events in ±1 month window"

    # Edit one generated event
    edited_event_id = generated_events[0]["id"]
    edited_event = await event_repo_real.get(UUID(edited_event_id))

    await event_repo_real.update(
        UUID(edited_event_id),
        EventUpdate(description="EDITED: Custom description"),
        current_user={"id": str(sample_user_real.id)},
        client_id="client-a"
    )

    # Client A: Second sync (should NOT regenerate edited event)
    sync_a2 = {
        "client_id": "client-a",
        "last_sync_at": data_a1["sync_timestamp"],
        "changes": []
    }

    response_a2 = await async_client_real.post("/api/sync", json=sync_a2, headers=auth_headers_real)
    assert response_a2.status_code == 200

    # Verify edited event preserved
    edited_event_after = await event_repo_real.get(UUID(edited_event_id))
    assert "EDITED" in edited_event_after.description, "Edited event should be preserved"
    assert edited_event_after.updated_at != edited_event_after.created_at, "Edited event should have different timestamps"

    # Client B: Sync (should receive generated events in server_changes)
    # Use timestamp at (or slightly after) earliest change_log entry
    # This ensures we're not marked as stale, but still receive all changes
    earliest_log = await clean_database_real["change_log"].find_one(sort=[("changed_at", 1)])
    earliest_ts = datetime.fromisoformat(earliest_log["changed_at"])

    sync_b1 = {
        "client_id": "client-b",
        "last_sync_at": earliest_ts.isoformat(),
        "changes": []
    }

    response_b1 = await async_client_real.post("/api/sync", json=sync_b1, headers=auth_headers_real)
    assert response_b1.status_code == 200
    data_b1 = response_b1.json()

    # Verify change_log includes generated events
    event_changes = [c for c in data_b1["server_changes"] if c["entity_type"] == "event"]
    assert len(event_changes) > 0, "Generated events should be in server_changes"

    # Check for recurring events
    recurring_events = [c for c in event_changes
                       if c.get("data") and c["data"].get("recurring_rule_id") == str(sample_recurring_rule_with_user.id)]
    assert len(recurring_events) > 0, "Client B should receive generated recurring events"


# ============================================================================
# Reconciliation Integration Tests - Display-only drift architecture
# ============================================================================

@pytest.mark.integration
@pytest.mark.asyncio
async def test_sync_triggers_reconciliation_creates_auto_events(
    async_client_real,
    auth_headers_real,
    account_repo_real,
    event_repo_real,
    sample_user_real,
    sample_settings_real,
    clean_database_real
):
    """
    Test that sync endpoint triggers reconciliation and creates [auto] events.

    Scenario:
    1. Client A updates account balance (sets pending_reconciliation=True)
    2. Client A syncs
    3. Server creates [auto] adjustment event
    4. Client A receives [auto] event in server_changes

    Validates:
    - Sync triggers reconciliation phase
    - [auto] event created with correct drift
    - [auto] event included in server_changes
    - pending_reconciliation flag cleared
    """
    from api.models import AccountCreate, EventCreate

    # Create account with current_balance=1000
    account_data = AccountCreate(
        name="Monzo",
        currency="GBP",
        current_balance=Decimal("1000.00"),
        is_default=True
    )
    account = await account_repo_real.create(
        account_data,
        current_user={"id": str(sample_user_real.id)},
        client_id=None
    )

    # Create event that makes projected balance = 500
    event = EventCreate(
        date="2025-01-10",
        description="Salary",
        amount=Decimal("500.00"),
        account_id=account.id,
        currency="GBP",
        rate_to_base=Decimal("1.0"),
        is_baseline=True
    )
    await event_repo_real.create(
        event,
        current_user={"id": str(sample_user_real.id)},
        client_id=None
    )

    # Client A: Update account balance to 1000 with pending_reconciliation=True
    sync_a1 = {
        "client_id": "client-a",
        "last_sync_at": None,
        "changes": [{
            "entity_type": "account",
            "entity_id": str(account.id),
            "action": "update",
            "data": {
                "name": "Monzo",
                "currency": "GBP",
                "current_balance": "1000.00",
                "is_default": True,
                "pending_reconciliation": True,  # Mark for reconciliation
                "updated_at": datetime.utcnow().isoformat()
            },
            "base_updated_at": account.updated_at.isoformat()
        }]
    }

    response_a1 = await async_client_real.post("/api/sync", json=sync_a1, headers=auth_headers_real)
    assert response_a1.status_code == 200
    data_a1 = response_a1.json()

    # Verify reconciliation triggered and [auto] event created
    auto_events = await event_repo_real.collection.find({
        "account_id": str(account.id),
        "is_auto_adjustment": True
    }).to_list(length=None)

    assert len(auto_events) == 1, "Should create 1 [auto] adjustment event"

    auto_event = auto_events[0]
    # Drift = actual (1000) - projected (500) = 500
    assert Decimal(str(auto_event["amount"])) == Decimal("500.00"), "Should have correct drift amount"
    assert auto_event["description"] == "balance adjustment"
    assert auto_event["is_auto_adjustment"] is True

    # Verify [auto] event included in server_changes
    auto_changes = [c for c in data_a1["server_changes"]
                   if c["entity_type"] == "event" and
                   c.get("data", {}).get("is_auto_adjustment") is True]

    assert len(auto_changes) == 1, "[auto] event should be in server_changes"
    assert auto_changes[0]["action"] == "create"

    # Verify pending_reconciliation flag cleared
    account_doc = await account_repo_real.collection.find_one({"id": str(account.id)})
    assert account_doc["pending_reconciliation"] is False, "Should clear pending flag after reconciliation"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_sync_reconciliation_multi_client_propagation(
    async_client_real,
    auth_headers_real,
    account_repo_real,
    event_repo_real,
    sample_user_real,
    sample_settings_real,
    clean_database_real
):
    """
    Test that [auto] events propagate to other clients via sync.

    Scenario:
    1. Client A updates account balance (pending_reconciliation=True)
    2. Client A syncs (triggers reconciliation, creates [auto] event)
    3. Client B syncs
    4. Client B receives [auto] event in server_changes

    Validates:
    - [auto] events propagate like normal events
    - Other clients receive reconciliation adjustments
    - Change log includes [auto] event creation
    """
    from api.models import AccountCreate, EventCreate

    # Create account
    account_data = AccountCreate(
        name="HSBC",
        currency="GBP",
        current_balance=Decimal("2000.00"),
        is_default=False
    )
    account = await account_repo_real.create(
        account_data,
        current_user={"id": str(sample_user_real.id)},
        client_id=None
    )

    # Create event (projected balance = 1000)
    event = EventCreate(
        date="2025-01-10",
        description="Initial",
        amount=Decimal("1000.00"),
        account_id=account.id,
        currency="GBP",
        rate_to_base=Decimal("1.0"),
        is_baseline=True
    )
    await event_repo_real.create(
        event,
        current_user={"id": str(sample_user_real.id)},
        client_id=None
    )

    # Client A: Update balance with pending_reconciliation
    sync_a1 = {
        "client_id": "client-a",
        "last_sync_at": None,
        "changes": [{
            "entity_type": "account",
            "entity_id": str(account.id),
            "action": "update",
            "data": {
                "name": "HSBC",
                "currency": "GBP",
                "current_balance": "2000.00",
                "is_default": False,
                "pending_reconciliation": True,
                "updated_at": datetime.utcnow().isoformat()
            },
            "base_updated_at": account.updated_at.isoformat()
        }]
    }

    response_a1 = await async_client_real.post("/api/sync", json=sync_a1, headers=auth_headers_real)
    assert response_a1.status_code == 200
    data_a1 = response_a1.json()

    sync_ts_a1 = data_a1["sync_timestamp"]

    # Client B: Sync to receive [auto] event
    sync_b1 = {
        "client_id": "client-b",
        "last_sync_at": None,  # First sync
        "changes": []
    }

    response_b1 = await async_client_real.post("/api/sync", json=sync_b1, headers=auth_headers_real)
    assert response_b1.status_code == 200
    data_b1 = response_b1.json()

    # Verify Client B receives [auto] event in server_changes
    auto_changes = [c for c in data_b1["server_changes"]
                   if c["entity_type"] == "event" and
                   c.get("data", {}).get("is_auto_adjustment") is True]

    assert len(auto_changes) == 1, "Client B should receive [auto] event"
    assert auto_changes[0]["action"] == "create"
    # Drift = 2000 - 1000 = 1000
    assert Decimal(auto_changes[0]["data"]["amount"]) == Decimal("1000.00")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_sync_reconciliation_removes_old_auto_adjustments(
    async_client_real,
    auth_headers_real,
    account_repo_real,
    event_repo_real,
    sample_user_real,
    sample_settings_real,
    clean_database_real
):
    """
    Test that sync reconciliation removes old [auto] adjustments before creating new ones.

    Scenario:
    1. Account has old [auto] adjustment
    2. Client updates balance (different drift)
    3. Client syncs
    4. Old [auto] removed, new one created

    Validates:
    - Old [auto] adjustments deleted
    - New [auto] adjustment created with updated drift
    - No accumulation of stale adjustments
    """
    from api.models import AccountCreate, EventCreate

    # Create account
    account_data = AccountCreate(
        name="Revolut",
        currency="GBP",
        current_balance=Decimal("1500.00"),
        is_default=False
    )
    account = await account_repo_real.create(
        account_data,
        current_user={"id": str(sample_user_real.id)},
        client_id=None
    )

    # Create baseline event (projected = 500)
    event = EventCreate(
        date="2025-01-10",
        description="Starting",
        amount=Decimal("500.00"),
        account_id=account.id,
        currency="GBP",
        rate_to_base=Decimal("1.0"),
        is_baseline=True
    )
    await event_repo_real.create(
        event,
        current_user={"id": str(sample_user_real.id)},
        client_id=None
    )

    # Create OLD [auto] adjustment (drift=500, stale)
    old_auto = EventCreate(
        date="2025-01-15",
        description="balance adjustment",
        amount=Decimal("500.00"),
        account_id=account.id,
        currency="GBP",
        rate_to_base=Decimal("1.0"),
        is_auto_adjustment=True
    )
    await event_repo_real.create(
        old_auto,
        current_user={"id": str(sample_user_real.id)},
        client_id=None
    )

    # Client: Update balance to 1500 (new drift = 1000)
    sync_1 = {
        "client_id": "client-a",
        "last_sync_at": None,
        "changes": [{
            "entity_type": "account",
            "entity_id": str(account.id),
            "action": "update",
            "data": {
                "name": "Revolut",
                "currency": "GBP",
                "current_balance": "1500.00",
                "is_default": False,
                "pending_reconciliation": True,
                "updated_at": datetime.utcnow().isoformat()
            },
            "base_updated_at": account.updated_at.isoformat()
        }]
    }

    response_1 = await async_client_real.post("/api/sync", json=sync_1, headers=auth_headers_real)
    if response_1.status_code != 200:
        print(f"Sync failed with status {response_1.status_code}: {response_1.json()}")
    assert response_1.status_code == 200

    # Verify old [auto] removed and new one created
    auto_events = await event_repo_real.collection.find({
        "account_id": str(account.id),
        "is_auto_adjustment": True
    }).to_list(length=None)

    assert len(auto_events) == 1, "Should have exactly 1 [auto] adjustment (old removed, new created)"

    # Verify new adjustment has updated drift (1500 - 500 = 1000)
    new_auto = auto_events[0]
    assert Decimal(str(new_auto["amount"])) == Decimal("1000.00"), "Should have updated drift"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_reconciliation_trigger_endpoint(
    async_client_real,
    auth_headers_real,
    sample_user_real,
    account_repo_real,
    event_repo_real
):
    """
    Test POST /api/reconciliation/trigger endpoint (Task 120).

    Verifies:
    - Endpoint requires authentication
    - Triggers reconciliation for all pending accounts
    - Returns proper response format
    - Creates auto-adjustment events when needed
    """
    # Create account with drift (needs reconciliation)
    account = await account_repo_real.create(
        {
            "name": "Test Account",
            "currency": "GBP",
            "current_balance": Decimal("1000.00"),
            "is_default": True,
            "pending_reconciliation": True
        },
        current_user={"id": str(sample_user_real.id)},
        client_id=None
    )

    # Create baseline event (projected balance = 500)
    await event_repo_real.create(
        {
            "date": "2025-01-10",
            "description": "salary",
            "amount": Decimal("500.00"),
            "account_id": account.id,
            "currency": "GBP",
            "rate_to_base": Decimal("1.0"),
            "is_baseline": True
        },
        current_user={"id": str(sample_user_real.id)},
        client_id=None
    )

    # Trigger reconciliation via endpoint
    response = await async_client_real.post(
        "/api/reconciliation/trigger",
        headers=auth_headers_real
    )

    assert response.status_code == 200
    data = response.json()

    # Verify response format
    assert "reconciled" in data
    assert "message" in data
    assert data["reconciled"] is True
    assert "complete" in data["message"].lower()

    # Verify auto-adjustment event was created
    auto_events = await event_repo_real.collection.find({
        "account_id": str(account.id),
        "is_auto_adjustment": True
    }).to_list(length=None)

    assert len(auto_events) == 1, "Should create auto-adjustment event"
    assert Decimal(str(auto_events[0]["amount"])) == Decimal("500.00"), "Drift should be 1000 - 500 = 500"


# ============================================================================
# Sync Endpoint High Limits Test
# ============================================================================

@pytest.mark.integration
@pytest.mark.asyncio
async def test_full_sync_returns_all_events_beyond_default_limit(
    async_client_real,
    auth_headers_real,
    sample_account_with_user,
    sample_user_real,
    event_repo_real,
    clean_database_real
):
    """
    Test that GET /api/sync/full returns all events, not just default 100 limit.

    Scenario:
    1. Create 123 events in database (matching fixture data)
    2. Call GET /api/sync/full
    3. Verify all 123 events returned

    Validates:
    - Full sync endpoint uses explicit high limit (10,000)
    - Not limited by base repository default limit (100)
    - All user events returned regardless of count

    Related to: sync.py:468 - explicit limit=10000 for events
    """
    # Create 123 events (matching populate_test_data.py fixture count)
    created_event_ids = []

    for i in range(123):
        event_data = EventCreate(
            date=f"2026-{(i % 12) + 1:02d}-{(i % 28) + 1:02d}",  # Spread across 2026
            description=f"Test Event {i+1}",
            amount=Decimal("-50.00"),
            currency="GBP",
            account_id=sample_account_with_user.id,
            rate_to_base=Decimal("1.0"),
            is_baseline=True
        )
        event = await event_repo_real.create(
            event_data,
            current_user={"id": str(sample_user_real.id)},
            client_id=None
        )
        created_event_ids.append(str(event.id))

    # Call full sync endpoint
    response = await async_client_real.get("/api/sync/full", headers=auth_headers_real)
    assert response.status_code == 200
    data = response.json()

    # Verify structure
    assert "events" in data
    assert "accounts" in data
    assert "stories" in data
    assert "recurring_rules" in data
    assert "settings" in data
    assert "sync_timestamp" in data

    # CRITICAL: Verify all 123 events returned (not just 100)
    events = data["events"]
    assert len(events) >= 123, f"Expected at least 123 events, got {len(events)}"

    # Verify created events are in response
    returned_event_ids = {e["id"] for e in events}
    for event_id in created_event_ids:
        assert event_id in returned_event_ids, f"Event {event_id} missing from full sync response"
