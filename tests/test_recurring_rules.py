"""
Unit tests for RecurringRule CRUD endpoints.

Tests all recurring rule endpoints including:
- GET /api/recurring-rules (list)
- GET /api/recurring-rules/{id} (single rule)
- POST /api/recurring-rules (create)
- PUT /api/recurring-rules/{id} (update)
- DELETE /api/recurring-rules/{id} (delete)

Business logic tested:
- Frequency validation (MONTHLY, WEEKLY, ANNUALLY)
- Day validation (1-31 for monthly, 1-7 for weekly)
- Date range validation (start_date, optional end_date)
"""

import pytest
from datetime import date
from decimal import Decimal


# ============================================================================
# GET /api/recurring-rules - List Recurring Rules
# ============================================================================

class TestRecurringRuleList:
    """Tests for GET /api/recurring-rules endpoint."""

    @pytest.mark.asyncio
    async def test_list_recurring_rules_empty(self, async_client):
        """Empty database returns empty list."""
        response = await async_client.get("/api/recurring-rules")

        assert response.status_code == 200
        data = response.json()
        assert data == []

    @pytest.mark.asyncio
    async def test_list_recurring_rules_returns_rules(self, async_client, sample_recurring_rule):
        """List returns created recurring rules."""
        response = await async_client.get("/api/recurring-rules")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["description"] == "Monthly Rent"
        assert data[0]["frequency"] == "monthly"


# ============================================================================
# GET /api/recurring-rules/{id} - Get Single Recurring Rule
# ============================================================================

class TestRecurringRuleGet:
    """Tests for GET /api/recurring-rules/{id} endpoint."""

    @pytest.mark.asyncio
    async def test_get_recurring_rule_success(self, async_client, sample_recurring_rule):
        """Get existing recurring rule returns 200 with rule data."""
        response = await async_client.get(f"/api/recurring-rules/{sample_recurring_rule.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(sample_recurring_rule.id)
        assert data["description"] == "Monthly Rent"
        assert data["amount"] == "-1500.00"
        assert data["frequency"] == "monthly"
        assert data["day"] == 28

    @pytest.mark.asyncio
    async def test_get_recurring_rule_not_found(self, async_client):
        """Get non-existent recurring rule returns 404."""
        from uuid import uuid4
        fake_id = uuid4()

        response = await async_client.get(f"/api/recurring-rules/{fake_id}")

        assert response.status_code == 404
        data = response.json()
        assert "detail" in data


# ============================================================================
# POST /api/recurring-rules - Create Recurring Rule
# ============================================================================

class TestRecurringRuleCreate:
    """Tests for POST /api/recurring-rules endpoint."""

    @pytest.mark.asyncio
    async def test_create_monthly_recurring_rule(self, async_client, sample_account):
        """Create monthly recurring rule."""
        payload = {
            "description": "Salary",
            "amount": 3000.00,
            "currency": "GBP",
            "account_id": str(sample_account.id),
            "frequency": "monthly",
            "day": 1,
            "start_date": "2025-01-01",
            "end_date": None
        }

        response = await async_client.post("/api/recurring-rules", json=payload)

        assert response.status_code == 201
        data = response.json()
        assert data["description"] == "Salary"
        assert data["amount"] == "3000.0"  # Single trailing zero
        assert data["frequency"] == "monthly"
        assert data["day"] == 1
        assert data["id"] is not None
        assert data["created_at"] is not None

    @pytest.mark.asyncio
    async def test_create_weekly_recurring_rule(self, async_client, sample_account):
        """Create weekly recurring rule."""
        payload = {
            "description": "Gym Membership",
            "amount": -50.00,
            "currency": "GBP",
            "account_id": str(sample_account.id),
            "frequency": "weekly",
            "day": 1,  # Monday
            "start_date": "2025-01-06",
            "end_date": "2025-12-31"
        }

        response = await async_client.post("/api/recurring-rules", json=payload)

        assert response.status_code == 201
        data = response.json()
        assert data["frequency"] == "weekly"
        assert data["day"] == 1

    @pytest.mark.asyncio
    async def test_create_annually_recurring_rule(self, async_client, sample_account):
        """Create annually recurring rule.

        Note: Annual rules use start_date to determine month (June 15 = day 15, start on June 15).
        The day field (1-31) specifies the day of month for recurrence.
        """
        payload = {
            "description": "Insurance Premium",
            "amount": -1200.00,
            "currency": "GBP",
            "account_id": str(sample_account.id),
            "frequency": "annual",  # annual, not annually!
            "day": 15,  # 15th of the month (determined by start_date)
            "start_date": "2025-06-15",  # Recurs annually on June 15th
            "end_date": None
        }

        response = await async_client.post("/api/recurring-rules", json=payload)

        assert response.status_code == 201
        data = response.json()
        assert data["frequency"] == "annual"
        assert data["day"] == 15
        assert data["start_date"] == "2025-06-15"

    @pytest.mark.asyncio
    async def test_create_recurring_rule_validation_error_invalid_day(
        self, async_client, sample_account
    ):
        """Create monthly rule with invalid day (>31) returns 422."""
        payload = {
            "description": "Invalid Rule",
            "amount": -100.00,
            "currency": "GBP",
            "account_id": str(sample_account.id),
            "frequency": "monthly",
            "day": 32,  # Invalid
            "start_date": "2025-01-01"
        }

        response = await async_client.post("/api/recurring-rules", json=payload)

        assert response.status_code == 422
        data = response.json()
        assert "detail" in data

    @pytest.mark.asyncio
    async def test_create_recurring_rule_validation_error_missing_description(
        self, async_client, sample_account
    ):
        """Create rule without description returns 422."""
        payload = {
            "amount": -100.00,
            "currency": "GBP",
            "account_id": str(sample_account.id),
            "frequency": "monthly",
            "day": 1,
            "start_date": "2025-01-01"
        }

        response = await async_client.post("/api/recurring-rules", json=payload)

        assert response.status_code == 422
        data = response.json()
        assert "detail" in data

    @pytest.mark.asyncio
    async def test_create_monthly_rule_validates_day_range_upper_bound(
        self, async_client, sample_account
    ):
        """Monthly rule day must be 1-31 (test upper bound)."""
        payload = {
            "description": "Test Rule",
            "amount": -100.00,
            "currency": "GBP",
            "account_id": str(sample_account.id),
            "frequency": "monthly",
            "day": 32,  # Invalid: > 31
            "start_date": "2025-01-01"
        }

        response = await async_client.post("/api/recurring-rules", json=payload)

        assert response.status_code == 422
        data = response.json()
        assert "detail" in data

    @pytest.mark.asyncio
    async def test_create_monthly_rule_validates_day_range_lower_bound(
        self, async_client, sample_account
    ):
        """Monthly rule day must be 1-31 (test lower bound)."""
        payload = {
            "description": "Test Rule",
            "amount": -100.00,
            "currency": "GBP",
            "account_id": str(sample_account.id),
            "frequency": "monthly",
            "day": 0,  # Invalid: < 1
            "start_date": "2025-01-01"
        }

        response = await async_client.post("/api/recurring-rules", json=payload)

        assert response.status_code == 422
        data = response.json()
        assert "detail" in data

    @pytest.mark.asyncio
    async def test_create_weekly_rule_validates_day_range_upper_bound(
        self, async_client, sample_account
    ):
        """Weekly rule day must be 1-7 (test upper bound)."""
        payload = {
            "description": "Test Rule",
            "amount": -50.00,
            "currency": "GBP",
            "account_id": str(sample_account.id),
            "frequency": "weekly",
            "day": 8,  # Invalid: > 7 (1=Monday, 7=Sunday)
            "start_date": "2025-01-06"
        }

        response = await async_client.post("/api/recurring-rules", json=payload)

        assert response.status_code == 422
        data = response.json()
        assert "detail" in data

    @pytest.mark.asyncio
    async def test_create_weekly_rule_validates_day_range_lower_bound(
        self, async_client, sample_account
    ):
        """Weekly rule day must be 1-7 (test lower bound)."""
        payload = {
            "description": "Test Rule",
            "amount": -50.00,
            "currency": "GBP",
            "account_id": str(sample_account.id),
            "frequency": "weekly",
            "day": 0,  # Invalid: < 1
            "start_date": "2025-01-06"
        }

        response = await async_client.post("/api/recurring-rules", json=payload)

        assert response.status_code == 422
        data = response.json()
        assert "detail" in data

    @pytest.mark.asyncio
    async def test_create_recurring_rule_validates_end_date_after_start_date(
        self, async_client, sample_account
    ):
        """end_date must be after start_date (422 if invalid)."""
        payload = {
            "description": "Test Rule",
            "amount": -100.00,
            "currency": "GBP",
            "account_id": str(sample_account.id),
            "frequency": "monthly",
            "day": 15,
            "start_date": "2025-06-01",
            "end_date": "2025-05-31"  # Invalid: before start_date
        }

        response = await async_client.post("/api/recurring-rules", json=payload)

        assert response.status_code == 422
        data = response.json()
        assert "detail" in data

    @pytest.mark.asyncio
    async def test_create_recurring_rule_accepts_same_start_and_end_date(
        self, async_client, sample_account
    ):
        """end_date can equal start_date (single occurrence)."""
        payload = {
            "description": "One-time Rule",
            "amount": -100.00,
            "currency": "GBP",
            "account_id": str(sample_account.id),
            "frequency": "monthly",
            "day": 15,
            "start_date": "2025-06-15",
            "end_date": "2025-06-15"  # Same as start: single occurrence
        }

        response = await async_client.post("/api/recurring-rules", json=payload)

        # Should succeed (edge case: single occurrence)
        assert response.status_code == 201
        data = response.json()
        assert data["start_date"] == "2025-06-15"
        assert data["end_date"] == "2025-06-15"


# ============================================================================
# PUT /api/recurring-rules/{id} - Update Recurring Rule
# ============================================================================

class TestRecurringRuleUpdate:
    """Tests for PUT /api/recurring-rules/{id} endpoint."""

    @pytest.mark.asyncio
    async def test_update_recurring_rule_description_success(
        self, async_client, sample_recurring_rule
    ):
        """Update recurring rule description returns updated data."""
        payload = {"description": "Updated Rent"}

        response = await async_client.put(
            f"/api/recurring-rules/{sample_recurring_rule.id}",
            json=payload
        )

        assert response.status_code == 200
        data = response.json()
        assert data["description"] == "Updated Rent"
        assert data["id"] == str(sample_recurring_rule.id)

    @pytest.mark.asyncio
    async def test_update_recurring_rule_amount_success(
        self, async_client, sample_recurring_rule
    ):
        """Update recurring rule amount."""
        payload = {
            "description": "Monthly Rent",
            "amount": -1600.00,  # Changed from -1500.00
            "currency": "GBP",
            "account_id": str(sample_recurring_rule.account_id),
            "frequency": "monthly",
            "day": 28,
            "start_date": "2024-01-01",
            "end_date": None
        }

        response = await async_client.put(
            f"/api/recurring-rules/{sample_recurring_rule.id}",
            json=payload
        )

        assert response.status_code == 200
        data = response.json()
        assert data["amount"] == "-1600.0"  # Single trailing zero (Decimal formatting)

    @pytest.mark.asyncio
    async def test_update_recurring_rule_not_found(self, async_client):
        """Update non-existent recurring rule returns 404."""
        from uuid import uuid4
        fake_id = uuid4()

        payload = {"description": "New Description"}
        response = await async_client.put(
            f"/api/recurring-rules/{fake_id}",
            json=payload
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_recurring_rule_validation_error(
        self, async_client, sample_recurring_rule
    ):
        """Update with invalid data returns 422."""
        payload = {"frequency": "invalid"}  # Invalid frequency

        response = await async_client.put(
            f"/api/recurring-rules/{sample_recurring_rule.id}",
            json=payload
        )

        assert response.status_code == 422



# ============================================================================
# DELETE /api/recurring-rules/{id} - Delete Recurring Rule
# ============================================================================

class TestRecurringRuleDelete:
    """Tests for DELETE /api/recurring-rules/{id} endpoint."""

    @pytest.mark.asyncio
    async def test_delete_recurring_rule_success(self, async_client, sample_recurring_rule):
        """DELETE recurring rule returns 204."""
        response = await async_client.delete(f"/api/recurring-rules/{sample_recurring_rule.id}")

        assert response.status_code == 204
        assert response.text == ""

        # Verify rule is deleted
        get_response = await async_client.get(f"/api/recurring-rules/{sample_recurring_rule.id}")
        assert get_response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_recurring_rule_not_found(self, async_client):
        """DELETE non-existent recurring rule returns 404."""
        from uuid import uuid4
        fake_id = uuid4()

        response = await async_client.delete(f"/api/recurring-rules/{fake_id}")

        assert response.status_code == 404


# ============================================================================
# Integration Tests - Recurring Rule Regeneration
# ============================================================================

@pytest.mark.integration
@pytest.mark.asyncio
async def test_update_recurring_rule_regenerates_future_events(
    async_client_real, recurring_rule_repo_real, account_repo_real, mongodb_real, sample_user_real, sample_settings_real, auth_headers_real
):
    """
    Update recurring rule regenerates future unedited events with new values.

    Integration test for Task 147 (spec line 1347):
    "Modification: Future generated events updated, past events unchanged"

    Test scenario:
    1. Create recurring rule with amount £1500
    2. Generate future events (Feb, Mar)
    3. Update rule amount to £1600
    4. Verify future unedited events now have £1600
    5. Manually edit one event to £1700
    6. Update rule amount to £1800
    7. Verify unedited events have £1800, edited event stays £1700
    """
    from datetime import date, timedelta
    from api.utils.recurring import generate_recurring_events
    from api.models import RecurringRuleCreate, Frequency, AccountCreate
    from uuid import UUID

    # Create an account for the test
    account_data = AccountCreate(
        name="Test Account",
        currency="GBP",
        current_balance=Decimal("1000.00"),
        is_default=True
    )

    test_account = await account_repo_real.create(
        account_data,
        current_user={"id": str(sample_user_real.id)},
        client_id="test-client"
    )

    # Create a recurring rule
    rule_data = RecurringRuleCreate(
        description="Monthly Rent",
        amount=Decimal("-1500.00"),
        currency="GBP",
        account_id=test_account.id,
        frequency=Frequency.MONTHLY,
        day=28,
        start_date=date(2024, 1, 1),
        end_date=None
    )

    sample_recurring_rule = await recurring_rule_repo_real.create(
        rule_data,
        current_user={"id": str(sample_user_real.id)},
        client_id="test-client"
    )

    # Generate future events for the rule (within ±1 month window)
    user_id = sample_recurring_rule.created_by
    generated_events = await generate_recurring_events(
        mongodb_real,
        user_id,
        client_id="test-client"
    )

    # Verify events were generated
    assert len(generated_events) > 0, "Should generate at least 1 future event"

    # Verify initial amount is £1500
    for event in generated_events:
        assert event.amount == Decimal("-1500.00"), "Initial amount should be £1500"

    # Update rule amount to £1600
    update_payload = {
        "amount": -1600.00
    }

    update_response = await async_client_real.put(
        f"/api/recurring-rules/{sample_recurring_rule.id}",
        json=update_payload,
        headers=auth_headers_real
    )

    assert update_response.status_code == 200

    # Fetch events again and verify they were regenerated with new amount
    regenerated_events = await mongodb_real["events"].find({
        "recurring_rule_id": str(sample_recurring_rule.id),
        "event_date": {"$gt": date.today().isoformat()}
    }).to_list(length=None)

    assert len(regenerated_events) > 0, "Should have regenerated future events"

    # All regenerated events should have new amount
    for event in regenerated_events:
        assert Decimal(str(event["amount"])) == Decimal("-1600.00"), \
            f"Event {event['id']} should have new amount £1600"

    # Manually edit one event to £1700
    if regenerated_events:
        edited_event_id = regenerated_events[0]["id"]

        await mongodb_real["events"].update_one(
            {"id": edited_event_id},
            {"$set": {
                "amount": "-1700.00",
                "updated_at": (date.today() + timedelta(seconds=10)).isoformat()  # Make updated_at != created_at
            }}
        )

        # Update rule amount to £1800
        update_payload_2 = {
            "amount": -1800.00
        }

        update_response_2 = await async_client_real.put(
            f"/api/recurring-rules/{sample_recurring_rule.id}",
            json=update_payload_2,
            headers=auth_headers_real
        )

        assert update_response_2.status_code == 200

        # Fetch all events again
        final_events = await mongodb_real["events"].find({
            "recurring_rule_id": str(sample_recurring_rule.id),
            "event_date": {"$gt": date.today().isoformat()}
        }).to_list(length=None)

        # Check edited event is preserved
        edited_event = next((e for e in final_events if e["id"] == edited_event_id), None)
        assert edited_event is not None, "Edited event should still exist"
        assert Decimal(str(edited_event["amount"])) == Decimal("-1700.00"), \
            "Edited event should preserve custom amount £1700"

        # Check unedited events have new amount
        unedited_events = [e for e in final_events if e["id"] != edited_event_id]
        for event in unedited_events:
            assert Decimal(str(event["amount"])) == Decimal("-1800.00"), \
                f"Unedited event {event['id']} should have latest amount £1800"
