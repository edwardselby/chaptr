"""
Comprehensive tests for user tracking integration (Phase 1.5).

Tests created_by/updated_by auto-population across events, stories, and recurring rules.
Ruthless testing approach: Test every entity CRUD operation.
"""

import pytest
from uuid import UUID


# ============================================================================
# Event User Tracking Tests
# ============================================================================

@pytest.mark.asyncio
async def test_create_event_populates_created_by(async_client, auth_headers, sample_user, sample_account, sample_settings):
    """Creating event with authentication populates created_by."""
    response = await async_client.post("/api/events", headers=auth_headers, json={
        "event_date": "2024-12-25",
        "description": "Test Event",
        "amount": -50,
        "currency": "GBP",
        "account_id": str(sample_account.id),
        "is_baseline": True,
        "is_hypothetical": False
    })

    assert response.status_code == 201
    event = response.json()

    # created_by should be populated with sample_user's ID
    assert event["created_by"] == str(sample_user.id)


@pytest.mark.asyncio
async def test_create_event_populates_updated_by(async_client, auth_headers, sample_user, sample_account, sample_settings):
    """Creating event with authentication populates updated_by."""
    response = await async_client.post("/api/events", headers=auth_headers, json={
        "event_date": "2024-12-25",
        "description": "Test Event",
        "amount": -50,
        "currency": "GBP",
        "account_id": str(sample_account.id),
        "is_baseline": True,
        "is_hypothetical": False
    })

    assert response.status_code == 201
    event = response.json()

    # updated_by should be populated with sample_user's ID (same as created_by on creation)
    assert event["updated_by"] == str(sample_user.id)


@pytest.mark.asyncio
async def test_update_event_populates_updated_by(async_client, auth_headers, sample_user, sample_account, sample_baseline_event):
    """Updating event with authentication populates updated_by."""
    response = await async_client.put(f"/api/events/{sample_baseline_event.id}", headers=auth_headers, json={
        "amount": -75
    })

    assert response.status_code == 200
    event = response.json()

    # updated_by should be populated with sample_user's ID
    assert event["updated_by"] == str(sample_user.id)


@pytest.mark.asyncio
async def test_update_event_preserves_created_by(async_client, auth_headers, sample_user, sample_baseline_event):
    """Updating event preserves original created_by."""
    # Store original created_by
    original_created_by = sample_baseline_event.created_by

    response = await async_client.put(f"/api/events/{sample_baseline_event.id}", headers=auth_headers, json={
        "amount": -100
    })

    assert response.status_code == 200
    event = response.json()

    # created_by should remain unchanged
    if original_created_by:
        assert event["created_by"] == str(original_created_by)


@pytest.mark.asyncio
async def test_different_users_tracked_separately_for_events(async_client, auth_headers, regular_user_auth_headers, sample_user, sample_regular_user, sample_account, sample_settings, sample_baseline_event):
    """Different users creating/updating events are tracked separately."""
    # Admin creates event
    create_response = await async_client.post("/api/events", headers=auth_headers, json={
        "event_date": "2024-12-26",
        "description": "Admin Event",
        "amount": -50,
        "currency": "GBP",
        "account_id": str(sample_account.id),
        "is_baseline": True,
        "is_hypothetical": False
    })

    assert create_response.status_code == 201
    admin_event = create_response.json()
    assert admin_event["created_by"] == str(sample_user.id)

    # Regular user updates it
    update_response = await async_client.put(f"/api/events/{admin_event['id']}", headers=regular_user_auth_headers, json={
        "amount": -75
    })

    assert update_response.status_code == 200
    updated_event = update_response.json()

    # created_by should still be admin
    assert updated_event["created_by"] == str(sample_user.id)
    # updated_by should be regular user
    assert updated_event["updated_by"] == str(sample_regular_user.id)


# ============================================================================
# Story User Tracking Tests
# ============================================================================

@pytest.mark.asyncio
async def test_create_story_populates_created_by(async_client, auth_headers, sample_user, sample_account):
    """Creating story with authentication populates created_by."""
    response = await async_client.post("/api/stories", headers=auth_headers, json={
        "name": "Test Story",
        "start_date": "2025-01-01",
        "end_date": "2025-03-31",
        "default_account_id": str(sample_account.id),
        "funding_mode": "projected",
        "goal_type": "none",
        "display_currency": "GBP"
    })

    assert response.status_code == 201
    story = response.json()

    assert story["created_by"] == str(sample_user.id)


@pytest.mark.asyncio
async def test_create_story_populates_updated_by(async_client, auth_headers, sample_user, sample_account):
    """Creating story with authentication populates updated_by."""
    response = await async_client.post("/api/stories", headers=auth_headers, json={
        "name": "Test Story",
        "start_date": "2025-01-01",
        "end_date": "2025-03-31",
        "default_account_id": str(sample_account.id),
        "funding_mode": "projected",
        "goal_type": "none",
        "display_currency": "GBP"
    })

    assert response.status_code == 201
    story = response.json()

    assert story["updated_by"] == str(sample_user.id)


@pytest.mark.asyncio
async def test_update_story_populates_updated_by(async_client, auth_headers, sample_user, sample_story):
    """Updating story with authentication populates updated_by."""
    response = await async_client.put(f"/api/stories/{sample_story.id}", headers=auth_headers, json={
        "name": "Updated Story Name"
    })

    assert response.status_code == 200
    story = response.json()

    assert story["updated_by"] == str(sample_user.id)


@pytest.mark.asyncio
async def test_update_story_preserves_created_by(async_client, auth_headers, sample_story):
    """Updating story preserves original created_by."""
    original_created_by = sample_story.created_by

    response = await async_client.put(f"/api/stories/{sample_story.id}", headers=auth_headers, json={
        "name": "Modified Name"
    })

    assert response.status_code == 200
    story = response.json()

    if original_created_by:
        assert story["created_by"] == str(original_created_by)


# ============================================================================
# Recurring Rule User Tracking Tests
# ============================================================================

@pytest.mark.asyncio
async def test_create_recurring_rule_populates_created_by(async_client, auth_headers, sample_user, sample_account):
    """Creating recurring rule with authentication populates created_by."""
    response = await async_client.post("/api/recurring-rules", headers=auth_headers, json={
        "description": "Monthly Rent",
        "amount": -1500,
        "currency": "GBP",
        "account_id": str(sample_account.id),
        "frequency": "monthly",
        "day": 1,
        "start_date": "2025-01-01"
    })

    assert response.status_code == 201
    rule = response.json()

    assert rule["created_by"] == str(sample_user.id)


@pytest.mark.asyncio
async def test_create_recurring_rule_populates_updated_by(async_client, auth_headers, sample_user, sample_account):
    """Creating recurring rule with authentication populates updated_by."""
    response = await async_client.post("/api/recurring-rules", headers=auth_headers, json={
        "description": "Monthly Rent",
        "amount": -1500,
        "currency": "GBP",
        "account_id": str(sample_account.id),
        "frequency": "monthly",
        "day": 1,
        "start_date": "2025-01-01"
    })

    assert response.status_code == 201
    rule = response.json()

    assert rule["updated_by"] == str(sample_user.id)


@pytest.mark.asyncio
async def test_update_recurring_rule_populates_updated_by(async_client, auth_headers, sample_user, sample_recurring_rule):
    """Updating recurring rule with authentication populates updated_by."""
    response = await async_client.put(f"/api/recurring-rules/{sample_recurring_rule.id}", headers=auth_headers, json={
        "amount": -1600
    })

    assert response.status_code == 200
    rule = response.json()

    assert rule["updated_by"] == str(sample_user.id)


@pytest.mark.asyncio
async def test_update_recurring_rule_preserves_created_by(async_client, auth_headers, sample_recurring_rule):
    """Updating recurring rule preserves original created_by."""
    original_created_by = sample_recurring_rule.created_by

    response = await async_client.put(f"/api/recurring-rules/{sample_recurring_rule.id}", headers=auth_headers, json={
        "amount": -1700
    })

    assert response.status_code == 200
    rule = response.json()

    if original_created_by:
        assert rule["created_by"] == str(original_created_by)


# ============================================================================
# Backward Compatibility Tests
# ============================================================================

@pytest.mark.asyncio
async def test_event_created_without_auth_has_null_user_fields(event_repo, sample_account, sample_settings):
    """Events created without authentication have null created_by/updated_by (backward compatible)."""
    from api.models import EventCreate
    from datetime import date
    from decimal import Decimal

    event_data = EventCreate(
        event_date=date(2024, 12, 25),
        description="No Auth Event",
        amount=Decimal("-50"),
        currency="GBP",
        account_id=sample_account.id,
        is_baseline=True,
        is_hypothetical=False
    )

    # Create without current_user
    event = await event_repo.create(event_data, current_user=None)

    assert event.created_by is None
    assert event.updated_by is None


@pytest.mark.asyncio
async def test_story_created_without_auth_has_null_user_fields(story_repo, sample_account):
    """Stories created without authentication have null created_by/updated_by (backward compatible)."""
    from api.models import StoryCreate, FundingMode, GoalType
    from datetime import date

    story_data = StoryCreate(
        name="No Auth Story",
        start_date=date(2025, 1, 1),
        end_date=date(2025, 3, 31),
        default_account_id=sample_account.id,
        funding_mode=FundingMode.PROJECTED,
        goal_type=GoalType.NONE,
        display_currency="GBP"
    )

    # Create without current_user
    story = await story_repo.create(story_data, current_user=None)

    assert story.created_by is None
    assert story.updated_by is None


@pytest.mark.asyncio
async def test_recurring_rule_created_without_auth_has_null_user_fields(recurring_rule_repo, sample_account):
    """Recurring rules created without authentication have null created_by/updated_by (backward compatible)."""
    from api.models import RecurringRuleCreate, Frequency
    from datetime import date
    from decimal import Decimal

    rule_data = RecurringRuleCreate(
        description="No Auth Rule",
        amount=Decimal("-1000"),
        currency="GBP",
        account_id=sample_account.id,
        frequency=Frequency.MONTHLY,
        day=1,
        start_date=date(2025, 1, 1)
    )

    # Create without current_user
    rule = await recurring_rule_repo.create(rule_data, current_user=None)

    assert rule.created_by is None
    assert rule.updated_by is None


# ============================================================================
# User ID Format Tests
# ============================================================================

@pytest.mark.asyncio
async def test_created_by_is_valid_uuid(async_client, auth_headers, sample_account, sample_settings):
    """created_by field contains valid UUID format."""
    response = await async_client.post("/api/events", headers=auth_headers, json={
        "event_date": "2024-12-25",
        "description": "UUID Test",
        "amount": -50,
        "currency": "GBP",
        "account_id": str(sample_account.id),
        "is_baseline": True,
        "is_hypothetical": False
    })

    assert response.status_code == 201
    event = response.json()

    # Should be able to parse as UUID
    try:
        UUID(event["created_by"])
        assert True
    except (ValueError, TypeError):
        pytest.fail("created_by is not a valid UUID")


@pytest.mark.asyncio
async def test_updated_by_is_valid_uuid(async_client, auth_headers, sample_account, sample_baseline_event):
    """updated_by field contains valid UUID format."""
    response = await async_client.put(f"/api/events/{sample_baseline_event.id}", headers=auth_headers, json={
        "amount": -100
    })

    assert response.status_code == 200
    event = response.json()

    # Should be able to parse as UUID
    try:
        UUID(event["updated_by"])
        assert True
    except (ValueError, TypeError):
        pytest.fail("updated_by is not a valid UUID")


# ============================================================================
# Cross-Entity User Tracking Consistency Tests
# ============================================================================

@pytest.mark.asyncio
async def test_same_user_tracked_consistently_across_entities(async_client, auth_headers, sample_user, sample_account, sample_settings):
    """Same user creating different entities has consistent user ID in created_by."""
    # Create event
    event_response = await async_client.post("/api/events", headers=auth_headers, json={
        "event_date": "2024-12-25",
        "description": "Test",
        "amount": -50,
        "currency": "GBP",
        "account_id": str(sample_account.id),
        "is_baseline": True,
        "is_hypothetical": False
    })

    # Create story
    story_response = await async_client.post("/api/stories", headers=auth_headers, json={
        "name": "Test Story",
        "start_date": "2025-01-01",
        "end_date": "2025-03-31",
        "default_account_id": str(sample_account.id),
        "funding_mode": "projected",
        "goal_type": "none",
        "display_currency": "GBP"
    })

    # Create recurring rule
    rule_response = await async_client.post("/api/recurring-rules", headers=auth_headers, json={
        "description": "Test Rule",
        "amount": -100,
        "currency": "GBP",
        "account_id": str(sample_account.id),
        "frequency": "monthly",
        "day": 1,
        "start_date": "2025-01-01"
    })

    event = event_response.json()
    story = story_response.json()
    rule = rule_response.json()

    # All should have same created_by (sample_user.id)
    assert event["created_by"] == str(sample_user.id)
    assert story["created_by"] == str(sample_user.id)
    assert rule["created_by"] == str(sample_user.id)


# ============================================================================
# Edge Cases and Security Tests
# ============================================================================

@pytest.mark.asyncio
async def test_cannot_manually_set_created_by_in_request(async_client, auth_headers, sample_user, sample_account, sample_settings):
    """created_by cannot be overridden by client (security).

    Even if client sends created_by in request body, it should be ignored
    and populated from JWT token.
    """
    from uuid import uuid4
    fake_user_id = str(uuid4())

    response = await async_client.post("/api/events", headers=auth_headers, json={
        "event_date": "2024-12-25",
        "description": "Test",
        "amount": -50,
        "currency": "GBP",
        "account_id": str(sample_account.id),
        "is_baseline": True,
        "is_hypothetical": False,
        "created_by": fake_user_id  # Attempting to inject fake user ID
    })

    assert response.status_code == 201
    event = response.json()

    # created_by should be from token, not from request body
    assert event["created_by"] == str(sample_user.id)
    assert event["created_by"] != fake_user_id


@pytest.mark.asyncio
async def test_cannot_manually_set_updated_by_in_request(async_client, auth_headers, sample_user, sample_baseline_event):
    """updated_by cannot be overridden by client (security)."""
    from uuid import uuid4
    fake_user_id = str(uuid4())

    response = await async_client.put(f"/api/events/{sample_baseline_event.id}", headers=auth_headers, json={
        "amount": -100,
        "updated_by": fake_user_id  # Attempting to inject fake user ID
    })

    assert response.status_code == 200
    event = response.json()

    # updated_by should be from token, not from request body
    assert event["updated_by"] == str(sample_user.id)
    assert event["updated_by"] != fake_user_id


@pytest.mark.asyncio
async def test_user_tracking_works_with_role_based_token_expiration(async_client, sample_user, sample_regular_user, sample_account, sample_settings):
    """User tracking works correctly with different token expiration times (admin vs user)."""
    # Admin creates event (7-day token)
    from api.utils.auth import create_access_token

    admin_token = create_access_token(sample_user.id, sample_user.username, sample_user.role)
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    admin_response = await async_client.post("/api/events", headers=admin_headers, json={
        "event_date": "2024-12-25",
        "description": "Admin Event",
        "amount": -50,
        "currency": "GBP",
        "account_id": str(sample_account.id),
        "is_baseline": True,
        "is_hypothetical": False
    })

    # Regular user creates event (24-hour token)
    user_token = create_access_token(sample_regular_user.id, sample_regular_user.username, sample_regular_user.role)
    user_headers = {"Authorization": f"Bearer {user_token}"}

    user_response = await async_client.post("/api/events", headers=user_headers, json={
        "event_date": "2024-12-26",
        "description": "User Event",
        "amount": -75,
        "currency": "GBP",
        "account_id": str(sample_account.id),
        "is_baseline": True,
        "is_hypothetical": False
    })

    admin_event = admin_response.json()
    user_event = user_response.json()

    # Both should have correct created_by
    assert admin_event["created_by"] == str(sample_user.id)
    assert user_event["created_by"] == str(sample_regular_user.id)
