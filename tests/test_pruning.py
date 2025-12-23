"""
Tests for change_log pruning functionality.

Tests the scheduled maintenance job that removes old change_log entries
to prevent unbounded database growth.
"""

import pytest
from datetime import timedelta
from uuid import uuid4

from api.utils.db import utc_now, generate_id
from api.utils.pruning import prune_change_log


@pytest.mark.asyncio
async def test_prune_change_log_removes_old_entries(mongodb_test, clean_database):
    """
    Test that prune_change_log removes entries older than retention period.

    **Scenario**: Multiple change_log entries with different ages
    **Expected**: Only entries older than 31 days are deleted
    """
    # Arrange: Create change_log entries at different ages
    now = utc_now()
    user_id = str(uuid4())
    client_id = "client-a"

    # Old entries (should be deleted)
    old_entries = [
        {
            "id": str(generate_id()),
            "entity_type": "event",
            "entity_id": str(generate_id()),
            "action": "create",
            "data": {"amount": 100},
            "changed_by_user": user_id,
            "changed_by_client": client_id,
            "changed_at": (now - timedelta(days=35)).isoformat()
        },
        {
            "id": str(generate_id()),
            "entity_type": "story",
            "entity_id": str(generate_id()),
            "action": "update",
            "data": {"name": "Updated"},
            "changed_by_user": user_id,
            "changed_by_client": client_id,
            "changed_at": (now - timedelta(days=32)).isoformat()
        }
    ]

    # Recent entries (should be kept)
    recent_entries = [
        {
            "id": str(generate_id()),
            "entity_type": "account",
            "entity_id": str(generate_id()),
            "action": "create",
            "data": {"name": "New Account"},
            "changed_by_user": user_id,
            "changed_by_client": client_id,
            "changed_at": (now - timedelta(days=30)).isoformat()
        },
        {
            "id": str(generate_id()),
            "entity_type": "event",
            "entity_id": str(generate_id()),
            "action": "delete",
            "data": {"amount": 50},
            "changed_by_user": user_id,
            "changed_by_client": client_id,
            "changed_at": (now - timedelta(days=1)).isoformat()
        }
    ]

    # Insert all entries
    await mongodb_test["change_log"].insert_many(old_entries + recent_entries)

    # Act: Run pruning with 31-day retention
    deleted_count = await prune_change_log(mongodb_test, retention_days=31)

    # Assert: Old entries deleted, recent entries kept
    assert deleted_count == 2, "Should delete 2 old entries"

    remaining = await mongodb_test["change_log"].count_documents({})
    assert remaining == 2, "Should keep 2 recent entries"

    # Verify which entries remain
    remaining_docs = await mongodb_test["change_log"].find({}).to_list(length=None)
    remaining_ids = {doc["id"] for doc in remaining_docs}

    for entry in recent_entries:
        assert entry["id"] in remaining_ids, f"Recent entry {entry['id']} should be kept"

    for entry in old_entries:
        assert entry["id"] not in remaining_ids, f"Old entry {entry['id']} should be deleted"


@pytest.mark.asyncio
async def test_prune_change_log_empty_collection(mongodb_test, clean_database):
    """
    Test that prune_change_log handles empty change_log collection.

    **Scenario**: No change_log entries exist
    **Expected**: Returns 0 deleted count, no errors
    """
    # Act: Run pruning on empty collection
    deleted_count = await prune_change_log(mongodb_test, retention_days=31)

    # Assert: No errors, zero deletions
    assert deleted_count == 0, "Should delete 0 entries from empty collection"


@pytest.mark.asyncio
async def test_prune_change_log_all_entries_recent(mongodb_test, clean_database):
    """
    Test that prune_change_log keeps all entries when none are old enough.

    **Scenario**: All change_log entries within retention period
    **Expected**: Returns 0 deleted count, all entries kept
    """
    # Arrange: Create only recent entries
    now = utc_now()
    user_id = str(uuid4())

    recent_entries = [
        {
            "id": str(generate_id()),
            "entity_type": "event",
            "entity_id": str(generate_id()),
            "action": "create",
            "data": {},
            "changed_by_user": user_id,
            "changed_by_client": "client-a",
            "changed_at": (now - timedelta(days=10)).isoformat()
        },
        {
            "id": str(generate_id()),
            "entity_type": "story",
            "entity_id": str(generate_id()),
            "action": "update",
            "data": {},
            "changed_by_user": user_id,
            "changed_by_client": "client-b",
            "changed_at": (now - timedelta(days=5)).isoformat()
        }
    ]

    await mongodb_test["change_log"].insert_many(recent_entries)

    # Act: Run pruning
    deleted_count = await prune_change_log(mongodb_test, retention_days=31)

    # Assert: No deletions
    assert deleted_count == 0, "Should delete 0 entries (all recent)"

    remaining = await mongodb_test["change_log"].count_documents({})
    assert remaining == 2, "Should keep all 2 entries"


@pytest.mark.asyncio
async def test_prune_change_log_custom_retention_period(mongodb_test, clean_database):
    """
    Test that prune_change_log respects custom retention periods.

    **Scenario**: Use 7-day retention instead of default 31 days
    **Expected**: Deletes entries older than 7 days
    """
    # Arrange: Create entries with various ages
    now = utc_now()
    user_id = str(uuid4())

    entries = [
        {
            "id": str(generate_id()),
            "entity_type": "event",
            "entity_id": str(generate_id()),
            "action": "create",
            "data": {},
            "changed_by_user": user_id,
            "changed_by_client": "client-a",
            "changed_at": (now - timedelta(days=10)).isoformat()  # Should be deleted
        },
        {
            "id": str(generate_id()),
            "entity_type": "event",
            "entity_id": str(generate_id()),
            "action": "create",
            "data": {},
            "changed_by_user": user_id,
            "changed_by_client": "client-a",
            "changed_at": (now - timedelta(days=6)).isoformat()  # Should be kept
        }
    ]

    await mongodb_test["change_log"].insert_many(entries)

    # Act: Run pruning with 7-day retention
    deleted_count = await prune_change_log(mongodb_test, retention_days=7)

    # Assert: One old entry deleted
    assert deleted_count == 1, "Should delete 1 entry older than 7 days"

    remaining = await mongodb_test["change_log"].count_documents({})
    assert remaining == 1, "Should keep 1 entry within 7 days"


@pytest.mark.asyncio
async def test_prune_change_log_boundary_case(mongodb_test, clean_database):
    """
    Test pruning behavior near retention boundary.

    **Scenario**: Entry just under 31 days old (30 days + 23 hours)
    **Expected**: Entry is NOT deleted (within retention period)
    """
    # Arrange: Create entry just under 31 days old
    now = utc_now()
    user_id = str(uuid4())

    # Entry at 30 days + 23 hours (well within 31-day retention)
    boundary_entry = {
        "id": str(generate_id()),
        "entity_type": "event",
        "entity_id": str(generate_id()),
        "action": "create",
        "data": {},
        "changed_by_user": user_id,
        "changed_by_client": "client-a",
        "changed_at": (now - timedelta(days=30, hours=23)).isoformat()
    }

    await mongodb_test["change_log"].insert_one(boundary_entry)

    # Act: Run pruning
    deleted_count = await prune_change_log(mongodb_test, retention_days=31)

    # Assert: Entry within retention period is NOT deleted
    assert deleted_count == 0, "Should NOT delete entry just under 31 days old"

    remaining = await mongodb_test["change_log"].count_documents({})
    assert remaining == 1, "Entry within retention period should be kept"


@pytest.mark.asyncio
async def test_prune_change_log_preserves_different_clients(mongodb_test, clean_database):
    """
    Test that pruning works correctly across multiple clients.

    **Scenario**: Old entries from multiple clients
    **Expected**: All old entries deleted regardless of client
    """
    # Arrange: Create old entries from different clients
    now = utc_now()
    user_id = str(uuid4())

    old_entries = [
        {
            "id": str(generate_id()),
            "entity_type": "event",
            "entity_id": str(generate_id()),
            "action": "create",
            "data": {},
            "changed_by_user": user_id,
            "changed_by_client": "client-a",
            "changed_at": (now - timedelta(days=35)).isoformat()
        },
        {
            "id": str(generate_id()),
            "entity_type": "event",
            "entity_id": str(generate_id()),
            "action": "create",
            "data": {},
            "changed_by_user": user_id,
            "changed_by_client": "client-b",
            "changed_at": (now - timedelta(days=40)).isoformat()
        },
        {
            "id": str(generate_id()),
            "entity_type": "event",
            "entity_id": str(generate_id()),
            "action": "create",
            "data": {},
            "changed_by_user": user_id,
            "changed_by_client": None,  # REST API change
            "changed_at": (now - timedelta(days=50)).isoformat()
        }
    ]

    await mongodb_test["change_log"].insert_many(old_entries)

    # Act: Run pruning
    deleted_count = await prune_change_log(mongodb_test, retention_days=31)

    # Assert: All old entries deleted regardless of client
    assert deleted_count == 3, "Should delete all 3 old entries from different clients"

    remaining = await mongodb_test["change_log"].count_documents({})
    assert remaining == 0, "No entries should remain"
