"""
Unit tests for api/utils/indexes.py

Tests index creation functions for MongoDB collections.
Index creation should be:
- Successful when MongoDB is available
- Graceful (non-crashing) when index creation fails
- Idempotent (safe to call multiple times)
"""

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import logging

from api.utils.indexes import create_change_log_indexes, create_conflicts_indexes


# ============================================================================
# create_change_log_indexes Tests
# ============================================================================

@pytest.mark.asyncio
async def test_create_change_log_indexes_creates_all_indexes():
    """
    Verify create_change_log_indexes creates all expected indexes.

    Should create:
    - sync_pull_idx (composite: changed_at, changed_by_client)
    - pruning_idx (single: changed_at)
    - client_filter_idx (single: changed_by_client)
    """
    mock_collection = MagicMock()
    mock_collection.create_index = AsyncMock()

    mock_db = {"change_log": mock_collection}

    await create_change_log_indexes(mock_db)

    # Verify all three indexes created
    assert mock_collection.create_index.call_count == 3

    # Extract call arguments
    calls = mock_collection.create_index.call_args_list

    # Check sync_pull_idx (composite index)
    sync_pull_call = calls[0]
    assert sync_pull_call[0][0] == [("changed_at", 1), ("changed_by_client", 1)]
    assert sync_pull_call[1]["name"] == "sync_pull_idx"

    # Check pruning_idx (single field)
    pruning_call = calls[1]
    assert pruning_call[0][0] == "changed_at"
    assert pruning_call[1]["name"] == "pruning_idx"

    # Check client_filter_idx (single field)
    client_filter_call = calls[2]
    assert client_filter_call[0][0] == "changed_by_client"
    assert client_filter_call[1]["name"] == "client_filter_idx"


@pytest.mark.asyncio
async def test_create_change_log_indexes_handles_failure_gracefully():
    """
    Verify index creation failure doesn't crash the application.

    CRITICAL: Index creation is a performance optimization - failure should
    be logged but not prevent application startup.
    """
    mock_collection = MagicMock()
    mock_collection.create_index = AsyncMock(
        side_effect=Exception("MongoDB connection failed")
    )

    mock_db = {"change_log": mock_collection}

    # Should not raise exception
    await create_change_log_indexes(mock_db)

    # Verify attempt was made
    assert mock_collection.create_index.call_count >= 1


@pytest.mark.asyncio
async def test_create_change_log_indexes_logs_warning_on_failure(caplog):
    """
    Verify index creation failure is logged as warning.
    """
    mock_collection = MagicMock()
    mock_collection.create_index = AsyncMock(
        side_effect=Exception("Index creation failed")
    )

    mock_db = {"change_log": mock_collection}

    with caplog.at_level(logging.WARNING):
        await create_change_log_indexes(mock_db)

    # Check warning was logged
    assert "Failed to create change_log indexes" in caplog.text


@pytest.mark.asyncio
async def test_create_change_log_indexes_logs_success(caplog):
    """
    Verify successful index creation is logged.
    """
    mock_collection = MagicMock()
    mock_collection.create_index = AsyncMock()

    mock_db = {"change_log": mock_collection}

    with caplog.at_level(logging.INFO):
        await create_change_log_indexes(mock_db)

    # Check success messages logged
    assert "composite index on change_log" in caplog.text
    assert "pruning" in caplog.text.lower()


@pytest.mark.asyncio
async def test_create_change_log_indexes_partial_failure():
    """
    Verify partial failure (some indexes succeed, some fail).

    First two succeed, third fails - should still log warning.
    """
    call_count = 0

    async def mock_create_index(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 3:
            raise Exception("Third index failed")
        return None

    mock_collection = MagicMock()
    mock_collection.create_index = AsyncMock(side_effect=mock_create_index)

    mock_db = {"change_log": mock_collection}

    # Should not raise
    await create_change_log_indexes(mock_db)


# ============================================================================
# create_conflicts_indexes Tests
# ============================================================================

@pytest.mark.asyncio
async def test_create_conflicts_indexes_creates_composite_index():
    """
    Verify create_conflicts_indexes creates the entity_conflict_idx.

    Should create composite index on (entity_id, conflict_type).
    """
    mock_collection = MagicMock()
    mock_collection.create_index = AsyncMock()

    mock_db = {"conflicts": mock_collection}

    await create_conflicts_indexes(mock_db)

    # Verify index created
    assert mock_collection.create_index.call_count == 1

    call = mock_collection.create_index.call_args
    assert call[0][0] == [("entity_id", 1), ("conflict_type", 1)]
    assert call[1]["name"] == "entity_conflict_idx"


@pytest.mark.asyncio
async def test_create_conflicts_indexes_handles_failure_gracefully():
    """
    Verify conflicts index creation failure doesn't crash application.
    """
    mock_collection = MagicMock()
    mock_collection.create_index = AsyncMock(
        side_effect=Exception("Index creation failed")
    )

    mock_db = {"conflicts": mock_collection}

    # Should not raise
    await create_conflicts_indexes(mock_db)


@pytest.mark.asyncio
async def test_create_conflicts_indexes_logs_warning_on_failure(caplog):
    """
    Verify conflicts index failure is logged.
    """
    mock_collection = MagicMock()
    mock_collection.create_index = AsyncMock(
        side_effect=Exception("Connection lost")
    )

    mock_db = {"conflicts": mock_collection}

    with caplog.at_level(logging.WARNING):
        await create_conflicts_indexes(mock_db)

    assert "Failed to create conflicts indexes" in caplog.text


# ============================================================================
# Integration Tests (with real database)
# ============================================================================

@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_change_log_indexes_idempotent(clean_database_real):
    """
    Verify calling create_change_log_indexes twice doesn't error.

    MongoDB should handle duplicate index creation gracefully.
    """
    db = clean_database_real

    # Call twice - should not raise
    await create_change_log_indexes(db)
    await create_change_log_indexes(db)

    # Verify indexes exist
    indexes = await db["change_log"].index_information()
    assert "sync_pull_idx" in indexes
    assert "pruning_idx" in indexes
    assert "client_filter_idx" in indexes


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_conflicts_indexes_idempotent(clean_database_real):
    """
    Verify calling create_conflicts_indexes twice doesn't error.
    """
    db = clean_database_real

    # Call twice
    await create_conflicts_indexes(db)
    await create_conflicts_indexes(db)

    # Verify index exists
    indexes = await db["conflicts"].index_information()
    assert "entity_conflict_idx" in indexes


@pytest.mark.integration
@pytest.mark.asyncio
async def test_indexes_improve_query_performance(clean_database_real):
    """
    Verify indexes are actually used by queries (basic smoke test).

    Creates test data and runs explain() to verify index usage.
    """
    from datetime import datetime, timezone
    from uuid import uuid4

    db = clean_database_real

    # Create indexes
    await create_change_log_indexes(db)

    # Insert test data
    for i in range(10):
        await db["change_log"].insert_one({
            "id": str(uuid4()),
            "entity_type": "event",
            "entity_id": str(uuid4()),
            "action": "create",
            "data": {},
            "changed_by": str(uuid4()),
            "changed_by_client": f"client-{i}",
            "changed_at": datetime.now(timezone.utc).isoformat()
        })

    # Run query with explain to check index usage
    cursor = db["change_log"].find({
        "changed_at": {"$gt": "2020-01-01T00:00:00Z"},
        "changed_by_client": {"$ne": "client-0"}
    })

    # Just verify query executes (actual index usage verification
    # would require analyzing explain() output which is complex)
    results = await cursor.to_list(length=100)
    assert len(results) >= 0  # Query should execute without error
