"""
Unit tests for Story CRUD endpoints.

Tests all story endpoints including:
- GET /api/stories (list with sorting)
- GET /api/stories/{id} (single story)
- POST /api/stories (create)
- PUT /api/stories/{id} (update)
- DELETE /api/stories/{id} (delete with cascade)

Business logic tested:
- Funding mode validation (PROJECTED, FIXED, PROJECTED_PLUS)
- Goal type validation
- Start date DESC sorting
- Cascade delete to events
"""

import pytest
from datetime import date
from decimal import Decimal


# ============================================================================
# GET /api/stories - List Stories
# ============================================================================

class TestStoryList:
    """Tests for GET /api/stories endpoint."""

    @pytest.mark.asyncio
    async def test_list_stories_empty(self, async_client):
        """Empty database returns empty list."""
        response = await async_client.get("/api/stories")

        assert response.status_code == 200
        data = response.json()
        assert data == []

    @pytest.mark.asyncio
    async def test_list_stories_returns_stories(self, async_client, sample_story):
        """List returns created stories."""
        response = await async_client.get("/api/stories")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["name"] == "Test Story"
        assert data[0]["funding_mode"] == "projected"

    @pytest.mark.asyncio
    async def test_list_stories_sorted_by_start_date_desc(
        self, async_client, sample_account
    ):
        """Stories sorted by start_date descending."""
        # Create stories with different start dates
        story1_payload = {
            "name": "Story 1",
            "start_date": "2024-12-01",
            "end_date": "2024-12-31",
            "default_account_id": str(sample_account.id),
            "funding_mode": "projected",
            "goal_type": "none",
            "display_currency": "GBP"
        }
        story2_payload = {
            "name": "Story 2",
            "start_date": "2025-01-01",
            "end_date": "2025-01-31",
            "default_account_id": str(sample_account.id),
            "funding_mode": "projected",
            "goal_type": "none",
            "display_currency": "GBP"
        }
        story3_payload = {
            "name": "Story 3",
            "start_date": "2024-11-01",
            "end_date": "2024-11-30",
            "default_account_id": str(sample_account.id),
            "funding_mode": "projected",
            "goal_type": "none",
            "display_currency": "GBP"
        }

        await async_client.post("/api/stories", json=story1_payload)
        await async_client.post("/api/stories", json=story2_payload)
        await async_client.post("/api/stories", json=story3_payload)

        # List stories
        response = await async_client.get("/api/stories")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 3

        # Verify sorted by start_date DESC
        assert data[0]["name"] == "Story 2"  # 2025-01-01
        assert data[1]["name"] == "Story 1"  # 2024-12-01
        assert data[2]["name"] == "Story 3"  # 2024-11-01


# ============================================================================
# GET /api/stories/{id} - Get Single Story
# ============================================================================

class TestStoryGet:
    """Tests for GET /api/stories/{id} endpoint."""

    @pytest.mark.asyncio
    async def test_get_story_success(self, async_client, sample_story):
        """Get existing story returns 200 with story data."""
        response = await async_client.get(f"/api/stories/{sample_story.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(sample_story.id)
        assert data["name"] == "Test Story"
        assert data["funding_mode"] == "projected"
        assert data["goal_type"] == "none"

    @pytest.mark.asyncio
    async def test_get_story_not_found(self, async_client):
        """Get non-existent story returns 404."""
        from uuid import uuid4
        fake_id = uuid4()

        response = await async_client.get(f"/api/stories/{fake_id}")

        assert response.status_code == 404
        data = response.json()
        assert "detail" in data


# ============================================================================
# POST /api/stories - Create Story
# ============================================================================

class TestStoryCreate:
    """Tests for POST /api/stories endpoint."""

    @pytest.mark.asyncio
    async def test_create_story_funding_mode_projected(self, async_client, sample_account):
        """Create story with PROJECTED funding mode."""
        payload = {
            "name": "Trip to Japan",
            "start_date": "2025-03-01",
            "end_date": "2025-03-31",
            "default_account_id": str(sample_account.id),
            "funding_mode": "projected",
            "funding_amount": None,
            "goal_type": "none",
            "goal_amount": None,
            "display_currency": "GBP"
        }

        response = await async_client.post("/api/stories", json=payload)

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Trip to Japan"
        assert data["funding_mode"] == "projected"
        assert data["funding_amount"] is None
        assert data["id"] is not None
        assert data["created_at"] is not None

    @pytest.mark.asyncio
    async def test_create_story_funding_mode_fixed(self, async_client, sample_account):
        """Create story with FIXED funding mode requires funding_amount."""
        payload = {
            "name": "Fixed Budget Trip",
            "start_date": "2025-04-01",
            "end_date": "2025-04-30",
            "default_account_id": str(sample_account.id),
            "funding_mode": "fixed",
            "funding_amount": 5000.00,
            "goal_type": "end_with_at_least",
            "goal_amount": 1000.00,
            "display_currency": "GBP"
        }

        response = await async_client.post("/api/stories", json=payload)

        assert response.status_code == 201
        data = response.json()
        assert data["funding_mode"] == "fixed"
        assert data["funding_amount"] == "5000.0"

    @pytest.mark.asyncio
    async def test_create_story_funding_mode_projected_plus(
        self, async_client, sample_account
    ):
        """Create story with PROJECTED_PLUS funding mode."""
        payload = {
            "name": "Trip with Loan",
            "start_date": "2025-05-01",
            "end_date": "2025-05-31",
            "default_account_id": str(sample_account.id),
            "funding_mode": "projected_plus",
            "funding_amount": 2000.00,
            "goal_type": "none",
            "goal_amount": None,
            "display_currency": "GBP"
        }

        response = await async_client.post("/api/stories", json=payload)

        assert response.status_code == 201
        data = response.json()
        assert data["funding_mode"] == "projected_plus"
        assert data["funding_amount"] == "2000.0"

    @pytest.mark.asyncio
    async def test_create_story_goal_type_spend_up_to(self, async_client, sample_account):
        """Create story with SPEND_UP_TO goal type requires goal_amount."""
        payload = {
            "name": "Budget Challenge",
            "start_date": "2025-06-01",
            "end_date": "2025-06-30",
            "default_account_id": str(sample_account.id),
            "funding_mode": "projected",
            "funding_amount": None,
            "goal_type": "spend_up_to",
            "goal_amount": 500.00,
            "display_currency": "GBP"
        }

        response = await async_client.post("/api/stories", json=payload)

        assert response.status_code == 201
        data = response.json()
        assert data["goal_type"] == "spend_up_to"
        assert data["goal_amount"] == "500.0"

    @pytest.mark.asyncio
    async def test_create_story_validation_error_missing_name(self, async_client, sample_account):
        """Create story without name returns 422."""
        payload = {
            "start_date": "2025-01-01",
            "end_date": "2025-01-31",
            "default_account_id": str(sample_account.id),
            "funding_mode": "projected",
            "goal_type": "none",
            "display_currency": "GBP"
        }

        response = await async_client.post("/api/stories", json=payload)

        assert response.status_code == 422
        data = response.json()
        assert "detail" in data

    @pytest.mark.asyncio
    async def test_create_story_validation_error_invalid_funding_mode(
        self, async_client, sample_account
    ):
        """Create story with invalid funding_mode returns 422."""
        payload = {
            "name": "Invalid Story",
            "start_date": "2025-01-01",
            "end_date": "2025-01-31",
            "default_account_id": str(sample_account.id),
            "funding_mode": "invalid_mode",
            "goal_type": "none",
            "display_currency": "GBP"
        }

        response = await async_client.post("/api/stories", json=payload)

        assert response.status_code == 422
        data = response.json()
        assert "detail" in data


# ============================================================================
# PUT /api/stories/{id} - Update Story
# ============================================================================

class TestStoryUpdate:
    """Tests for PUT /api/stories/{id} endpoint."""

    @pytest.mark.asyncio
    async def test_update_story_name_success(self, async_client, sample_story):
        """Update story name returns updated data."""
        payload = {"name": "Updated Story Name"}

        response = await async_client.put(
            f"/api/stories/{sample_story.id}",
            json=payload
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Story Name"
        assert data["id"] == str(sample_story.id)

    @pytest.mark.asyncio
    async def test_update_story_dates_success(
        self, async_client, sample_story
    ):
        """Update story dates."""
        payload = {
            "name": "Test Story",
            "start_date": "2025-01-01",  # Changed
            "end_date": "2025-02-28",    # Changed
            "default_account_id": str(sample_story.default_account_id),
            "funding_mode": "projected",
            "funding_amount": None,
            "goal_type": "none",
            "goal_amount": None,
            "display_currency": "GBP"
        }

        response = await async_client.put(
            f"/api/stories/{sample_story.id}",
            json=payload
        )

        assert response.status_code == 200
        data = response.json()
        assert data["start_date"] == "2025-01-01"
        assert data["end_date"] == "2025-02-28"

    @pytest.mark.asyncio
    async def test_update_story_not_found(self, async_client):
        """Update non-existent story returns 404."""
        from uuid import uuid4
        fake_id = uuid4()

        payload = {"name": "New Name"}
        response = await async_client.put(
            f"/api/stories/{fake_id}",
            json=payload
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_story_validation_error(self, async_client, sample_story):
        """Update with invalid data returns 422."""
        payload = {"funding_mode": "invalid"}

        response = await async_client.put(
            f"/api/stories/{sample_story.id}",
            json=payload
        )

        assert response.status_code == 422


# ============================================================================
# DELETE /api/stories/{id} - Delete Story (with cascade)
# ============================================================================

class TestStoryDelete:
    """Tests for DELETE /api/stories/{id} endpoint (with cascade to events)."""

    @pytest.mark.asyncio
    async def test_delete_story_success(self, async_client, sample_story):
        """DELETE story returns 204."""
        response = await async_client.delete(f"/api/stories/{sample_story.id}")

        assert response.status_code == 204
        assert response.text == ""

        # Verify story is deleted
        get_response = await async_client.get(f"/api/stories/{sample_story.id}")
        assert get_response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_story_cascades_to_events(
        self, async_client, sample_account, sample_story, sample_settings
    ):
        """Deleting story removes associated events."""
        # Create event associated with story
        # NOTE: story_id is a QUERY PARAMETER, not in JSON body!
        event_payload = {
            "event_date": "2024-12-15",
            "description": "Story Event",
            "amount": -100.00,
            "currency": "GBP",
            "account_id": str(sample_account.id),
            "is_baseline": False,
            "is_hypothetical": False,
            "is_auto_adjustment": False
        }
        event_response = await async_client.post(
            f"/api/events?story_id={sample_story.id}",  # Query parameter!
            json=event_payload
        )
        assert event_response.status_code == 201
        event_id = event_response.json()["id"]

        # Delete story
        delete_response = await async_client.delete(f"/api/stories/{sample_story.id}")
        assert delete_response.status_code == 204

        # Verify event is also deleted (cascade)
        event_get_response = await async_client.get(f"/api/events/{event_id}")
        assert event_get_response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_story_preserves_baseline_events(
        self, async_client, sample_account, sample_story, sample_settings
    ):
        """Deleting story preserves baseline events (story_id=null)."""
        # Create baseline event (not associated with story)
        # NOTE: story_id omitted from query params = baseline event
        baseline_event_payload = {
            "event_date": "2024-12-10",
            "description": "Baseline Event",
            "amount": -50.00,
            "currency": "GBP",
            "account_id": str(sample_account.id),
            "is_baseline": True,
            "is_hypothetical": False,
            "is_auto_adjustment": False
        }
        baseline_response = await async_client.post(
            "/api/events",  # No story_id query param = baseline
            json=baseline_event_payload
        )
        assert baseline_response.status_code == 201
        baseline_id = baseline_response.json()["id"]

        # Delete story
        delete_response = await async_client.delete(f"/api/stories/{sample_story.id}")
        assert delete_response.status_code == 204

        # Verify baseline event still exists
        baseline_get_response = await async_client.get(f"/api/events/{baseline_id}")
        assert baseline_get_response.status_code == 200

    @pytest.mark.asyncio
    async def test_delete_story_not_found(self, async_client):
        """DELETE non-existent story returns 404."""
        from uuid import uuid4
        fake_id = uuid4()

        response = await async_client.delete(f"/api/stories/{fake_id}")

        assert response.status_code == 404
