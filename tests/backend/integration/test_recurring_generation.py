"""
Tests for recurring event generation within sync protocol.

Tests the generate_recurring_events utility function that materializes
recurring rules as actual event instances within a ±1 month window.

**Uses real MongoDB** for accurate change_log behavior simulation.
Mark tests with @pytest.mark.integration for selective execution.
"""

import pytest
import pytest_asyncio
from datetime import date, timedelta
from uuid import uuid4, UUID
from decimal import Decimal

from api.utils.recurring import generate_recurring_events
from api.models import RecurringRule, Event, Frequency, Settings
from api.utils.db import generate_id, utc_now


@pytest.mark.integration
@pytest.mark.asyncio
async def test_generate_monthly_recurring_events(mongodb_real, clean_database_real, settings_with_rates_real):
    """
    Test generation of monthly recurring events within window.

    **Scenario**: Monthly salary rule (day 25) with 12-month forward window
    **Expected**: Generates ~13 instances (12 months forward + 1 back)
    """
    # Arrange: Create monthly recurring rule
    today = date.today()
    account_id = generate_id()
    user_id = uuid4()

    # Create rule: Monthly on day 25
    tenant_id = settings_with_rates_real.tenant_id
    rule = RecurringRule(
        id=generate_id(),
        description="Monthly Salary",
        amount=Decimal("3000"),
        currency="GBP",
        account_id=account_id,
        frequency=Frequency.MONTHLY,
        day=25,
        start_date=today - timedelta(days=90),  # Started 3 months ago
        end_date=None,  # Ongoing
        created_at=utc_now(),
        created_by=user_id,
        updated_at=utc_now(),
        updated_by=user_id,
        tenant_id=tenant_id
    )

    await mongodb_real["recurring_rules"].insert_one(rule.model_dump(mode="json"))

    # Act: Generate recurring events
    generated = await generate_recurring_events(mongodb_real, user_id, "client-a", tenant_id)

    # Assert: Should generate ~13 instances (30 days back + 365 days forward = ~13 months)
    assert len(generated) >= 10, "Should generate at least 10 monthly instances for 12-month window"
    assert len(generated) <= 15, "Should not generate more than 15 monthly instances"

    # Verify all generated events have correct properties
    for event in generated:
        assert event.description == "Monthly Salary"
        assert event.amount == Decimal("3000")
        assert event.currency == "GBP"
        assert event.account_id == account_id
        assert event.recurring_rule_id == rule.id
        assert event.story_id is None
        assert event.is_baseline is False
        assert event.created_by == user_id

    # Verify events were inserted into database
    db_events = await mongodb_real["events"].find({"recurring_rule_id": str(rule.id)}).to_list(length=None)
    assert len(db_events) == len(generated)

    # Verify change log entries were created
    change_logs = await mongodb_real["change_log"].find({
        "entity_type": "event",
        "action": "create",
        "changed_by_client": "client-a"
    }).to_list(length=None)
    assert len(change_logs) == len(generated)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_generate_weekly_recurring_events(mongodb_real, clean_database_real, settings_with_rates_real):
    """
    Test generation of weekly recurring events.

    **Scenario**: Weekly coffee expense (every Monday) with 12-month forward window
    **Expected**: Generates ~52-57 instances (52 weeks/year + few extra from 30-day back window)
    """
    # Arrange: Create weekly recurring rule
    today = date.today()
    account_id = generate_id()
    user_id = uuid4()

    # Create rule: Weekly on Monday (day 1)
    tenant_id = settings_with_rates_real.tenant_id
    rule = RecurringRule(
        id=generate_id(),
        description="Weekly Coffee",
        amount=Decimal("-25"),
        currency="GBP",
        account_id=account_id,
        frequency=Frequency.WEEKLY,
        day=1,  # Monday
        start_date=today - timedelta(days=60),
        end_date=None,
        created_at=utc_now(),
        created_by=user_id,
        updated_at=utc_now(),
        updated_by=user_id,
        tenant_id=tenant_id
    )

    await mongodb_real["recurring_rules"].insert_one(rule.model_dump(mode="json"))

    # Act: Generate recurring events
    generated = await generate_recurring_events(mongodb_real, user_id, "client-b", tenant_id)

    # Assert: Should generate ~52-57 weekly instances (30 days back + 365 days forward)
    assert len(generated) >= 50, "Should generate at least 50 weekly instances for 12-month window"
    assert len(generated) <= 60, "Should not generate more than 60 weekly instances"

    # Verify all events are on Mondays
    for event in generated:
        assert event.event_date.weekday() == 0, f"Event {event.event_date} should be Monday"
        assert event.amount == Decimal("-25")
        assert event.recurring_rule_id == rule.id


@pytest.mark.integration
@pytest.mark.asyncio
async def test_generate_annual_recurring_events(mongodb_real, clean_database_real, settings_with_rates_real):
    """
    Test generation of annual recurring events.

    **Scenario**: Annual insurance payment with 12-month forward window
    **Expected**: Generates 1-2 instances (anniversary guaranteed within 12-month window)
    """
    # Arrange: Create annual recurring rule
    today = date.today()
    account_id = generate_id()
    user_id = uuid4()

    # Create rule: Annual on day 15 of current month (will be within window)
    tenant_id = settings_with_rates_real.tenant_id
    rule = RecurringRule(
        id=generate_id(),
        description="Annual Insurance",
        amount=Decimal("-500"),
        currency="GBP",
        account_id=account_id,
        frequency=Frequency.ANNUAL,
        day=15,
        start_date=date(today.year - 2, today.month, 15),  # Started 2 years ago
        end_date=None,
        created_at=utc_now(),
        created_by=user_id,
        updated_at=utc_now(),
        updated_by=user_id,
        tenant_id=tenant_id
    )

    await mongodb_real["recurring_rules"].insert_one(rule.model_dump(mode="json"))

    # Act: Generate recurring events
    generated = await generate_recurring_events(mongodb_real, user_id, None, tenant_id)

    # Assert: Should generate 1-2 annual instances (12-month window guarantees at least 1)
    assert len(generated) >= 1, "Should generate at least 1 annual instance in 12-month window"
    assert len(generated) <= 2, "Should generate at most 2 annual instances"

    for event in generated:
        assert event.event_date.day == 15
        assert event.event_date.month == rule.start_date.month
        assert event.recurring_rule_id == rule.id


@pytest.mark.integration
@pytest.mark.asyncio
async def test_generate_recurring_events_avoids_duplicates(mongodb_real, clean_database_real, settings_with_rates_real):
    """
    Test that generation skips existing instances to avoid duplicates.

    **Scenario**: Rule with some instances already generated
    **Expected**: Only creates missing instances, preserves existing
    """
    # Arrange: Create recurring rule and one existing instance
    today = date.today()
    account_id = generate_id()
    user_id = uuid4()
    rule_id = generate_id()

    tenant_id = settings_with_rates_real.tenant_id
    rule = RecurringRule(
        id=rule_id,
        description="Monthly Rent",
        amount=Decimal("-1200"),
        currency="GBP",
        account_id=account_id,
        frequency=Frequency.MONTHLY,
        day=1,
        start_date=today - timedelta(days=60),
        end_date=None,
        created_at=utc_now(),
        created_by=user_id,
        updated_at=utc_now(),
        updated_by=user_id,
        tenant_id=tenant_id
    )

    await mongodb_real["recurring_rules"].insert_one(rule.model_dump(mode="json"))

    # Create one existing event instance manually
    existing_event = Event(
        id=generate_id(),
        event_date=date(today.year, today.month, 1),
        description="Monthly Rent",
        amount=Decimal("-1200"),
        currency="GBP",
        rate_to_base=Decimal("1.0"),
        account_id=account_id,
        story_id=None,
        is_baseline=False,
        recurring_rule_id=rule_id,
        created_at=utc_now(),
        created_by=user_id,
        updated_at=utc_now(),
        updated_by=user_id,
        tenant_id=tenant_id
    )

    await mongodb_real["events"].insert_one(existing_event.model_dump(mode="json"))

    # Act: Generate recurring events
    generated = await generate_recurring_events(mongodb_real, user_id, "client-a", tenant_id)

    # Assert: Should NOT regenerate the existing instance
    total_events = await mongodb_real["events"].count_documents({"recurring_rule_id": str(rule_id)})

    # Original event + newly generated events
    assert len(generated) >= 0  # May generate 0-2 additional instances
    assert total_events == 1 + len(generated)

    # Verify existing event was not modified
    db_existing = await mongodb_real["events"].find_one({"id": str(existing_event.id)})
    assert db_existing is not None
    assert db_existing["description"] == "Monthly Rent"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_generate_recurring_events_preserves_edited_instances(mongodb_real, clean_database_real, settings_with_rates_real):
    """
    Test that generation preserves manually edited instances.

    **Scenario**: User edited a recurring instance (updated_at != created_at)
    **Expected**: Edited instance is never regenerated
    """
    # Arrange: Create rule and edited instance
    today = date.today()
    account_id = generate_id()
    user_id = uuid4()
    rule_id = generate_id()

    tenant_id = settings_with_rates_real.tenant_id
    rule = RecurringRule(
        id=rule_id,
        description="Monthly Subscription",
        amount=Decimal("-15"),
        currency="GBP",
        account_id=account_id,
        frequency=Frequency.MONTHLY,
        day=10,
        start_date=today - timedelta(days=60),
        end_date=None,
        created_at=utc_now(),
        created_by=user_id,
        updated_at=utc_now(),
        updated_by=user_id,
        tenant_id=tenant_id
    )

    await mongodb_real["recurring_rules"].insert_one(rule.model_dump(mode="json"))

    # Create edited event instance (updated_at different from created_at)
    created_time = utc_now() - timedelta(hours=2)
    edited_time = utc_now()

    edited_event = Event(
        id=generate_id(),
        event_date=date(today.year, today.month, 10),
        description="Monthly Subscription (Edited)",  # User changed description
        amount=Decimal("-20"),  # User changed amount
        currency="GBP",
        rate_to_base=Decimal("1.0"),
        account_id=account_id,
        story_id=None,
        is_baseline=False,
        recurring_rule_id=rule_id,
        created_at=created_time,
        created_by=user_id,
        updated_at=edited_time,  # Different from created_at
        updated_by=user_id,
        tenant_id=tenant_id
    )

    await mongodb_real["events"].insert_one(edited_event.model_dump(mode="json"))

    # Act: Generate recurring events
    generated = await generate_recurring_events(mongodb_real, user_id, "client-a", tenant_id)

    # Assert: Edited event should NOT be in generated list
    generated_dates = [e.event_date for e in generated]
    assert edited_event.event_date not in generated_dates, "Should not regenerate edited instance"

    # Verify edited event still exists with modifications intact
    db_edited = await mongodb_real["events"].find_one({"id": str(edited_event.id)})
    assert db_edited is not None
    assert db_edited["description"] == "Monthly Subscription (Edited)"
    assert db_edited["amount"] == "-20"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_generate_recurring_events_respects_end_date(mongodb_real, clean_database_real, settings_with_rates_real):
    """
    Test that generation respects rule end_date.

    **Scenario**: Rule with end_date in the past
    **Expected**: No events generated (rule expired)
    """
    # Arrange: Create rule that ended 3 months ago
    today = date.today()
    account_id = generate_id()
    user_id = uuid4()

    tenant_id = settings_with_rates_real.tenant_id
    rule = RecurringRule(
        id=generate_id(),
        description="Expired Subscription",
        amount=Decimal("-10"),
        currency="GBP",
        account_id=account_id,
        frequency=Frequency.MONTHLY,
        day=1,
        start_date=today - timedelta(days=180),
        end_date=today - timedelta(days=90),  # Ended 3 months ago
        created_at=utc_now(),
        created_by=user_id,
        updated_at=utc_now(),
        updated_by=user_id,
        tenant_id=tenant_id
    )

    await mongodb_real["recurring_rules"].insert_one(rule.model_dump(mode="json"))

    # Act: Generate recurring events
    generated = await generate_recurring_events(mongodb_real, user_id, "client-a", tenant_id)

    # Assert: Should NOT generate any events (rule expired)
    assert len(generated) == 0, "Should not generate events for expired rule"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_generate_recurring_events_multiple_rules(mongodb_real, clean_database_real, settings_with_rates_real):
    """
    Test generation with multiple active recurring rules.

    **Scenario**: 3 different recurring rules (monthly, weekly, annual)
    **Expected**: Generates instances for all active rules
    """
    # Arrange: Create 3 different recurring rules
    today = date.today()
    account_id = generate_id()
    user_id = uuid4()

    tenant_id = settings_with_rates_real.tenant_id
    rules = [
        RecurringRule(
            id=generate_id(),
            description="Monthly Salary",
            amount=Decimal("3000"),
            currency="GBP",
            account_id=account_id,
            frequency=Frequency.MONTHLY,
            day=25,
            start_date=today - timedelta(days=60),
            end_date=None,
            created_at=utc_now(),
            created_by=user_id,
            updated_at=utc_now(),
            updated_by=user_id,
            tenant_id=tenant_id
        ),
        RecurringRule(
            id=generate_id(),
            description="Weekly Coffee",
            amount=Decimal("-25"),
            currency="GBP",
            account_id=account_id,
            frequency=Frequency.WEEKLY,
            day=1,
            start_date=today - timedelta(days=60),
            end_date=None,
            created_at=utc_now(),
            created_by=user_id,
            updated_at=utc_now(),
            updated_by=user_id,
            tenant_id=tenant_id
        ),
        RecurringRule(
            id=generate_id(),
            description="Annual Insurance",
            amount=Decimal("-500"),
            currency="GBP",
            account_id=account_id,
            frequency=Frequency.ANNUAL,
            day=15,
            start_date=date(today.year - 1, today.month, 15),
            end_date=None,
            created_at=utc_now(),
            created_by=user_id,
            updated_at=utc_now(),
            updated_by=user_id,
            tenant_id=tenant_id
        )
    ]

    for rule in rules:
        await mongodb_real["recurring_rules"].insert_one(rule.model_dump(mode="json"))

    # Act: Generate recurring events
    generated = await generate_recurring_events(mongodb_real, user_id, "client-a", tenant_id)

    # Assert: Should generate instances for all 3 rules
    # Monthly: 2-3, Weekly: 4-9, Annual: 0-1 = total 6-13
    assert len(generated) >= 5, "Should generate instances for all rules"

    # Verify instances for each rule exist
    for rule in rules:
        rule_events = [e for e in generated if e.recurring_rule_id == rule.id]
        assert len(rule_events) > 0, f"Should generate at least 1 instance for {rule.description}"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_generate_recurring_events_empty_rules(mongodb_real, clean_database_real, settings_with_rates_real):
    """
    Test generation with no recurring rules.

    **Scenario**: No recurring rules exist
    **Expected**: Returns empty list, no errors
    """
    # Act: Generate recurring events (no rules in database)
    user_id = uuid4()
    generated = await generate_recurring_events(mongodb_real, user_id, "client-a")

    # Assert: Should return empty list
    assert generated == []
    assert len(generated) == 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_generate_recurring_events_skips_excluded_dates(mongodb_real, clean_database_real, settings_with_rates_real):
    """
    Test that generation skips dates in excluded_dates list.

    **Scenario**: Rule with excluded_dates for single-instance deletion
    **Expected**: Skips excluded dates, generates others
    """
    # Arrange: Create monthly recurring rule with excluded dates
    today = date.today()
    account_id = generate_id()
    user_id = uuid4()

    # Calculate dates that will be in the window
    next_month = today.replace(day=15) + timedelta(days=30)
    excluded_date = next_month.replace(day=15)  # Exclude the 15th of next month

    tenant_id = settings_with_rates_real.tenant_id
    rule = RecurringRule(
        id=generate_id(),
        description="Monthly with Exclusion",
        amount=Decimal("-100"),
        currency="GBP",
        account_id=account_id,
        frequency=Frequency.MONTHLY,
        day=15,
        start_date=today - timedelta(days=60),
        end_date=None,
        excluded_dates=[excluded_date],  # Exclude one specific date
        created_at=utc_now(),
        created_by=user_id,
        updated_at=utc_now(),
        updated_by=user_id,
        tenant_id=tenant_id
    )

    await mongodb_real["recurring_rules"].insert_one(rule.model_dump(mode="json"))

    # Act: Generate recurring events
    generated = await generate_recurring_events(mongodb_real, user_id, "client-a", tenant_id)

    # Assert: The excluded date should not be in generated events
    generated_dates = [e.event_date for e in generated]
    assert excluded_date not in generated_dates, f"Excluded date {excluded_date} should not be generated"

    # Should still generate other months
    assert len(generated) >= 10, "Should generate at least 10 monthly instances (excluding 1)"
