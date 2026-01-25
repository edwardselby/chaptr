#!/usr/bin/env python
"""
Regression tests for projection endpoint bugs discovered during manual testing.

This test suite ensures that critical bugs related to:
1. MongoDB Decimal128 to Python Decimal conversion
2. MongoDB date storage format (string vs datetime)

...remain fixed and do not regress in future development.

Test coverage:
- Decimal type conversion from MongoDB Decimal128
- Date query format (ISO string vs datetime)
- End-to-end projection with real MongoDB data
"""

import pytest
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from core.projection import (
    calculate_global_projection,
    calculate_story_projection,
    calculate_account_projection
)


class TestDecimalConversion:
    """
    Test MongoDB Decimal128 to Python Decimal conversion.

    Bug: MongoDB returns Decimal128 values as strings/objects,
    causing TypeError when attempting arithmetic operations.
    """

    @pytest.mark.asyncio
    async def test_account_balance_decimal_conversion(self):
        """Account balance from MongoDB Decimal128 should work in calculations."""
        mock_db = MagicMock()

        # Mock account with MongoDB-style Decimal128 as string
        mock_cursor_accounts = MagicMock()
        mock_cursor_accounts.to_list = AsyncMock(return_value=[
            {
                "_id": "account-1",
                "name": "Test Account",
                "currency": "GBP",
                "current_balance": "2500.00",  # MongoDB Decimal128 as string
                "rate_to_base": "1.0",
                "is_baseline": True
            }
        ])
        mock_db.accounts.find.return_value = mock_cursor_accounts

        # Mock empty events
        mock_cursor_events = MagicMock()
        mock_cursor_events.to_list = AsyncMock(return_value=[])
        mock_db.events.find.return_value = mock_cursor_events

        # This should NOT raise TypeError when converting Decimal128 to Python Decimal
        events = await calculate_global_projection(
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 31),
            db=mock_db
        )

        # Should return list of events
        assert isinstance(events, list)
        assert len(events) == 0  # Empty events in this test

    @pytest.mark.asyncio
    async def test_event_amount_decimal_conversion(self):
        """Event amounts from MongoDB Decimal128 should work in calculations."""
        mock_db = MagicMock()

        # Mock account
        mock_cursor_accounts = MagicMock()
        mock_cursor_accounts.to_list = AsyncMock(return_value=[
            {
                "_id": "account-1",
                "current_balance": "1000.00",
                "rate_to_base": "1.0",
                "is_baseline": True
            }
        ])
        mock_db.accounts.find.return_value = mock_cursor_accounts

        # Mock event with MongoDB-style Decimal128 as string
        mock_cursor_events = MagicMock()
        mock_cursor_events.to_list = AsyncMock(return_value=[
            {
                "_id": "event-1",
                "event_date": "2025-01-15",
                "description": "Salary",
                "amount": "3000.00",  # MongoDB Decimal128 as string
                "rate_to_base": "1.0",
                "currency": "GBP",
                "is_baseline": True,
                "is_hypothetical": False,
                "created_at": "2025-01-01T00:00:00"
            }
        ])
        mock_db.events.find.return_value = mock_cursor_events

        # This should NOT raise TypeError when converting Decimal128 amounts
        events = await calculate_global_projection(
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 31),
            db=mock_db
        )

        # Should have 1 event
        assert len(events) == 1

        # Event should have base_amount calculated from Decimal128 string
        event = events[0]
        assert "base_amount" in event
        assert event["base_amount"] == Decimal("3000.00")


class TestDateQueryFormat:
    """
    Test MongoDB date query format (ISO string vs datetime).

    Bug: MongoDB stores dates as ISO strings (YYYY-MM-DD), but queries
    used datetime.combine(), causing 0 results returned.
    """

    @pytest.mark.asyncio
    async def test_date_query_uses_iso_format(self):
        """Date queries should use .isoformat() for string comparison."""
        mock_db = MagicMock()

        # Mock empty accounts
        mock_cursor_accounts = MagicMock()
        mock_cursor_accounts.to_list = AsyncMock(return_value=[])
        mock_db.accounts.find.return_value = mock_cursor_accounts

        # Mock events find to capture query
        captured_query = None
        def capture_query(query):
            nonlocal captured_query
            captured_query = query
            mock_cursor = MagicMock()
            mock_cursor.to_list = AsyncMock(return_value=[])
            return mock_cursor

        mock_db.events.find = capture_query

        # Execute projection
        await calculate_global_projection(
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 31),
            view="all",
            db=mock_db
        )

        # Verify query uses ISO format strings, not datetime objects
        assert "event_date" in captured_query
        assert "$gte" in captured_query["event_date"]
        assert "$lte" in captured_query["event_date"]

        # Should be strings in ISO format
        assert captured_query["event_date"]["$gte"] == "2025-01-01"
        assert captured_query["event_date"]["$lte"] == "2025-01-31"

    @pytest.mark.asyncio
    async def test_story_projection_date_query_format(self):
        """Story projection should use ISO format for date queries."""
        mock_db = MagicMock()

        story_uuid = "550e8400-e29b-41d4-a716-446655440000"

        # Mock story with fixed funding (simpler than projected)
        mock_db.stories.find_one = AsyncMock(return_value={
            "_id": story_uuid,
            "name": "Test Story",
            "start_date": "2025-01-01",
            "end_date": "2025-12-31",
            "funding_mode": "fixed",  # Use fixed to avoid complex projected balance calculation
            "funding_amount": "1000.00",
            "funding_currency": "GBP",
            "display_currency": "GBP"
        })

        # Mock settings for currency conversion
        mock_db.settings.find_one = AsyncMock(return_value={
            "base_currency": "GBP",
            "rates": {"GBP": "1.0"}
        })

        # Mock events find to capture query
        captured_query = None
        def capture_query(query):
            nonlocal captured_query
            captured_query = query
            mock_cursor = MagicMock()
            mock_cursor.to_list = AsyncMock(return_value=[])
            return mock_cursor

        mock_db.events.find = capture_query

        # Execute story projection
        await calculate_story_projection(
            story_id=story_uuid,
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 31),
            db=mock_db
        )

        # Verify query uses ISO format
        assert captured_query["event_date"]["$gte"] == "2025-01-01"
        assert captured_query["event_date"]["$lte"] == "2025-01-31"

    @pytest.mark.asyncio
    async def test_account_projection_date_query_format(self):
        """Account projection should use ISO format for date queries."""
        mock_db = MagicMock()

        account_uuid = "660e8400-e29b-41d4-a716-446655440001"

        # Mock account
        mock_db.accounts.find_one = AsyncMock(return_value={
            "_id": account_uuid,
            "name": "Test Account",
            "current_balance": "1000.00",
            "rate_to_base": "1.0",
            "currency": "GBP"
        })

        # Mock events find to capture query
        captured_query = None
        def capture_query(query):
            nonlocal captured_query
            captured_query = query
            mock_cursor = MagicMock()
            mock_cursor.to_list = AsyncMock(return_value=[])
            return mock_cursor

        mock_db.events.find = capture_query

        # Execute account projection
        await calculate_account_projection(
            account_id=account_uuid,
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 31),
            db=mock_db
        )

        # Verify query uses ISO format
        assert captured_query["event_date"]["$gte"] == "2025-01-01"
        assert captured_query["event_date"]["$lte"] == "2025-01-31"


class TestEndToEndProjection:
    """
    End-to-end integration tests with realistic MongoDB data.

    These tests verify the entire projection flow works correctly
    with data structures matching actual MongoDB documents.
    """

    @pytest.mark.asyncio
    async def test_projection_with_realistic_mongodb_data(self):
        """Test projection with data structures matching real MongoDB."""
        mock_db = MagicMock()

        # Mock accounts with MongoDB-style data
        mock_cursor_accounts = MagicMock()
        mock_cursor_accounts.to_list = AsyncMock(return_value=[
            {
                "_id": "account-1",
                "name": "Barclays",
                "currency": "EUR",
                "current_balance": "1234.56",  # Decimal128 as string
                "rate_to_base": "0.85",
                "is_baseline": True
            }
        ])
        mock_db.accounts.find.return_value = mock_cursor_accounts

        # Mock events with MongoDB-style data
        mock_cursor_events = MagicMock()
        mock_cursor_events.to_list = AsyncMock(return_value=[
            {
                "_id": "event-1",
                "event_date": "2025-01-15",  # ISO string
                "description": "Salary",
                "amount": "3000.00",  # Decimal128 as string
                "rate_to_base": "0.85",
                "currency": "EUR",
                "account_id": "account-1",
                "is_baseline": True,
                "is_hypothetical": False,
                "created_at": "2025-01-01T00:00:00"
            },
            {
                "_id": "event-2",
                "event_date": "2025-01-20",
                "description": "Rent",
                "amount": "-800.00",
                "rate_to_base": "0.85",
                "currency": "EUR",
                "account_id": "account-1",
                "is_baseline": True,
                "is_hypothetical": False,
                "created_at": "2025-01-02T00:00:00"
            }
        ])
        mock_db.events.find.return_value = mock_cursor_events

        # Execute projection - should NOT raise any errors
        events = await calculate_global_projection(
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 31),
            db=mock_db
        )

        # Verify results structure (list of events)
        assert isinstance(events, list)

        # Verify events retrieved
        assert len(events) == 2

        # Verify events have base_amount calculated correctly
        # Event 1: 3000.00 EUR * 0.85 = 2550.00 GBP
        # Event 2: -800.00 EUR * 0.85 = -680.00 GBP
        assert events[0]["base_amount"] == Decimal("2550.00")
        assert events[1]["base_amount"] == Decimal("-680.00")

        # Verify all events have base_amount field
        for event in events:
            assert "base_amount" in event
            assert isinstance(event["base_amount"], Decimal)


class TestMongoDBIntegration:
    """
    Integration tests with real MongoDB connection.

    These tests require a running MongoDB instance and are marked
    with @pytest.mark.integration to allow selective execution.

    Run with: pytest -m integration
    Skip with: pytest -m "not integration"
    """

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_projection_with_real_mongodb(self):
        """Integration test: Verify projection works with actual MongoDB."""
        from motor.motor_asyncio import AsyncIOMotorClient
        from api.config import settings

        # Get MongoDB connection from settings
        client = AsyncIOMotorClient(settings.mongodb_url)
        db = client[settings.mongodb_db_name]

        try:
            # Verify MongoDB is accessible
            await db.command("ping")

            # Get actual settings document
            settings_doc = await db.settings.find_one()
            assert settings_doc is not None, "Settings document not found in MongoDB"

            # Get actual accounts
            accounts = await db.accounts.find({"is_archived": False}).to_list(None)
            if len(accounts) == 0:
                pytest.skip("No accounts found in MongoDB - skipping integration test")

            # Get actual events
            events = await db.events.find().limit(10).to_list(10)

            # Run projection with real data
            from core.projection import calculate_global_projection
            projection_results = await calculate_global_projection(
                start_date=date(2025, 1, 1),
                end_date=date(2025, 12, 31),
                db=db
            )

            # Verify results structure
            assert isinstance(projection_results, list)

            # Verify no ObjectId leaks in results
            for event in projection_results:
                # Check all fields are JSON serializable
                import json
                try:
                    json.dumps(event, default=str)
                except (TypeError, ValueError) as e:
                    pytest.fail(f"Event contains non-serializable data: {e}")

                # Verify _id field was removed
                assert "_id" not in event, f"ObjectId '_id' leaked in event: {event.get('description')}"

                # Verify required fields present
                assert "id" in event or "event_date" in event

        finally:
            client.close()
