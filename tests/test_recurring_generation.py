"""
Tests for recurring event generation within sync protocol.

Tests the generate_recurring_events utility function that materializes
recurring rules as actual event instances within a ±1 month window.
"""

import pytest
import pytest_asyncio
from datetime import date, timedelta
from uuid import uuid4, UUID
from decimal import Decimal

from api.utils.recurring import generate_recurring_events
from api.models import RecurringRule, Event, Frequency, Settings
from api.utils.db import generate_id, utc_now


@pytest_asyncio.fixture(scope="function")
async def settings_with_rates(mongodb_test):
    """
    Create default settings with currency rates for recurring event tests.

    Required by generate_recurring_events for rate_to_base calculations.
    """
    settings = Settings(
        id=generate_id(),
        base_currency="GBP",
        default_currency="GBP",
        rates={"GBP": Decimal("1.0"), "USD": Decimal("1.27"), "EUR": Decimal("1.17")},
        created_at=utc_now(),
        updated_at=utc_now()
    )
    await mongodb_test["settings"].insert_one(settings.model_dump(mode="json"))
    return settings


@pytest.mark.asyncio
async def test_generate_monthly_recurring_events(mongodb_test, clean_database, settings_with_rates):
    """
    Test generation of monthly recurring events within window.

    **Scenario**: Monthly salary rule (day 25) with ±1 month window
    **Expected**: Generates instances for months within window
    """
    # Arrange: Create monthly recurring rule
    today = date.today()
    account_id = generate_id()
    user_id = uuid4()

    # Create rule: Monthly on day 25
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
        updated_by=user_id
    )

    await mongodb_test["recurring_rules"].insert_one(rule.model_dump(mode="json"))

    # Act: Generate recurring events
    generated = await generate_recurring_events(mongodb_test, user_id, "client-a")

    # Assert: Should generate ~2-3 instances (±1 month window)
    assert len(generated) >= 1, "Should generate at least 1 monthly instance"
    assert len(generated) <= 4, "Should not generate more than 4 instances for ±1 month"

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
    db_events = await mongodb_test["events"].find({"recurring_rule_id": str(rule.id)}).to_list(length=None)
    assert len(db_events) == len(generated)

    # Verify change log entries were created
    change_logs = await mongodb_test["change_log"].find({
        "entity_type": "event",
        "action": "create",
        "changed_by_client": "client-a"
    }).to_list(length=None)
    assert len(change_logs) == len(generated)


@pytest.mark.asyncio
async def test_generate_weekly_recurring_events(mongodb_test, clean_database, settings_with_rates):
    """
    Test generation of weekly recurring events.

    **Scenario**: Weekly coffee expense (every Monday) with ±1 month window
    **Expected**: Generates ~4-9 instances (4-9 Mondays in ±1 month)
    """
    # Arrange: Create weekly recurring rule
    today = date.today()
    account_id = generate_id()
    user_id = uuid4()

    # Create rule: Weekly on Monday (day 1)
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
        updated_by=user_id
    )

    await mongodb_test["recurring_rules"].insert_one(rule.model_dump(mode="json"))

    # Act: Generate recurring events
    generated = await generate_recurring_events(mongodb_test, user_id, "client-b")

    # Assert: Should generate 4-9 weekly instances
    assert len(generated) >= 4, "Should generate at least 4 weekly instances"
    assert len(generated) <= 10, "Should not generate more than 10 weekly instances"

    # Verify all events are on Mondays
    for event in generated:
        assert event.event_date.weekday() == 0, f"Event {event.event_date} should be Monday"
        assert event.amount == Decimal("-25")
        assert event.recurring_rule_id == rule.id


@pytest.mark.asyncio
async def test_generate_annual_recurring_events(mongodb_test, clean_database, settings_with_rates):
    """
    Test generation of annual recurring events.

    **Scenario**: Annual insurance payment with ±1 month window
    **Expected**: Generates 0-1 instances (only if anniversary within window)
    """
    # Arrange: Create annual recurring rule
    today = date.today()
    account_id = generate_id()
    user_id = uuid4()

    # Create rule: Annual on day 15 of current month (likely within window)
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
        updated_by=user_id
    )

    await mongodb_test["recurring_rules"].insert_one(rule.model_dump(mode="json"))

    # Act: Generate recurring events
    generated = await generate_recurring_events(mongodb_test, user_id, None)

    # Assert: Should generate 0-1 annual instances
    assert len(generated) <= 1, "Should generate at most 1 annual instance in ±1 month"

    if len(generated) == 1:
        event = generated[0]
        assert event.event_date.day == 15
        assert event.event_date.month == rule.start_date.month
        assert event.recurring_rule_id == rule.id


@pytest.mark.asyncio
async def test_generate_recurring_events_avoids_duplicates(mongodb_test, clean_database, settings_with_rates):
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
        updated_by=user_id
    )

    await mongodb_test["recurring_rules"].insert_one(rule.model_dump(mode="json"))

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
        updated_by=user_id
    )

    await mongodb_test["events"].insert_one(existing_event.model_dump(mode="json"))

    # Act: Generate recurring events
    generated = await generate_recurring_events(mongodb_test, user_id, "client-a")

    # Assert: Should NOT regenerate the existing instance
    total_events = await mongodb_test["events"].count_documents({"recurring_rule_id": str(rule_id)})

    # Original event + newly generated events
    assert len(generated) >= 0  # May generate 0-2 additional instances
    assert total_events == 1 + len(generated)

    # Verify existing event was not modified
    db_existing = await mongodb_test["events"].find_one({"id": str(existing_event.id)})
    assert db_existing is not None
    assert db_existing["description"] == "Monthly Rent"


@pytest.mark.asyncio
async def test_generate_recurring_events_preserves_edited_instances(mongodb_test, clean_database, settings_with_rates):
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
        updated_by=user_id
    )

    await mongodb_test["recurring_rules"].insert_one(rule.model_dump(mode="json"))

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
        updated_by=user_id
    )

    await mongodb_test["events"].insert_one(edited_event.model_dump(mode="json"))

    # Act: Generate recurring events
    generated = await generate_recurring_events(mongodb_test, user_id, "client-a")

    # Assert: Edited event should NOT be in generated list
    generated_dates = [e.event_date for e in generated]
    assert edited_event.event_date not in generated_dates, "Should not regenerate edited instance"

    # Verify edited event still exists with modifications intact
    db_edited = await mongodb_test["events"].find_one({"id": str(edited_event.id)})
    assert db_edited is not None
    assert db_edited["description"] == "Monthly Subscription (Edited)"
    assert db_edited["amount"] == "-20"


@pytest.mark.asyncio
async def test_generate_recurring_events_respects_end_date(mongodb_test, clean_database, settings_with_rates):
    """
    Test that generation respects rule end_date.

    **Scenario**: Rule with end_date in the past
    **Expected**: No events generated (rule expired)
    """
    # Arrange: Create rule that ended 3 months ago
    today = date.today()
    account_id = generate_id()
    user_id = uuid4()

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
        updated_by=user_id
    )

    await mongodb_test["recurring_rules"].insert_one(rule.model_dump(mode="json"))

    # Act: Generate recurring events
    generated = await generate_recurring_events(mongodb_test, user_id, "client-a")

    # Assert: Should NOT generate any events (rule expired)
    assert len(generated) == 0, "Should not generate events for expired rule"


@pytest.mark.asyncio
async def test_generate_recurring_events_multiple_rules(mongodb_test, clean_database, settings_with_rates):
    """
    Test generation with multiple active recurring rules.

    **Scenario**: 3 different recurring rules (monthly, weekly, annual)
    **Expected**: Generates instances for all active rules
    """
    # Arrange: Create 3 different recurring rules
    today = date.today()
    account_id = generate_id()
    user_id = uuid4()

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
            updated_by=user_id
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
            updated_by=user_id
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
            updated_by=user_id
        )
    ]

    for rule in rules:
        await mongodb_test["recurring_rules"].insert_one(rule.model_dump(mode="json"))

    # Act: Generate recurring events
    generated = await generate_recurring_events(mongodb_test, user_id, "client-a")

    # Assert: Should generate instances for all 3 rules
    # Monthly: 2-3, Weekly: 4-9, Annual: 0-1 = total 6-13
    assert len(generated) >= 5, "Should generate instances for all rules"

    # Verify instances for each rule exist
    for rule in rules:
        rule_events = [e for e in generated if e.recurring_rule_id == rule.id]
        assert len(rule_events) > 0, f"Should generate at least 1 instance for {rule.description}"


@pytest.mark.asyncio
async def test_generate_recurring_events_empty_rules(mongodb_test, clean_database, settings_with_rates):
    """
    Test generation with no recurring rules.

    **Scenario**: No recurring rules exist
    **Expected**: Returns empty list, no errors
    """
    # Act: Generate recurring events (no rules in database)
    user_id = uuid4()
    generated = await generate_recurring_events(mongodb_test, user_id, "client-a")

    # Assert: Should return empty list
    assert generated == []
    assert len(generated) == 0
