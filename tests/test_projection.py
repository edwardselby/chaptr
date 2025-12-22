"""
Tests for projection engine.

Test data based on master timeline from chaptr-mockup-explanation v1.2:
- Accounts: Monzo (£2,500), HSBC (£11,000), Kat Credit (-$500 CAD) = £13,500 total
- Timeline: Dec 18, 2024 (TODAY) → Jan 18, 2025
- Expected trajectory: £13,500 → £12,342
"""

import pytest
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from core.projection import (
    calculate_global_projection,
    calculate_story_projection,
    calculate_account_projection,
    calculate_gap_indicators
)


# ==================== Test Fixtures ====================

@pytest.fixture
def test_accounts():
    """Master timeline test accounts."""
    return [
        {
            "_id": UUID("11111111-1111-1111-1111-111111111111"),
            "name": "Monzo",
            "currency": "GBP",
            "current_balance": Decimal("2500.00"),
            "is_default": True,
            "is_archived": False
        },
        {
            "_id": UUID("22222222-2222-2222-2222-222222222222"),
            "name": "HSBC",
            "currency": "GBP",
            "current_balance": Decimal("11000.00"),
            "is_default": False,
            "is_archived": False
        },
        {
            "_id": UUID("33333333-3333-3333-3333-333333333333"),
            "name": "Kat Credit",
            "currency": "CAD",
            "current_balance": Decimal("-500.00"),  # Overdraft
            "rate_to_base": Decimal("0.58"),  # 1 CAD = 0.58 GBP
            "is_default": False,
            "is_archived": False
        }
    ]


@pytest.fixture
def test_events():
    """Master timeline test events (simplified for Phase 2.1)."""
    monzo_id = UUID("11111111-1111-1111-1111-111111111111")
    hsbc_id = UUID("22222222-2222-2222-2222-222222222222")

    return [
        # Dec 20: Car rental (canada-trip)
        {
            "_id": uuid4(),
            "date": date(2024, 12, 20),
            "description": "car rental",
            "amount": Decimal("-320.00"),
            "currency": "GBP",
            "rate_to_base": Decimal("1.0"),
            "account_id": monzo_id,
            "story_id": None,  # Simplified - will add story refs in Phase 2.3
            "is_baseline": False,
            "is_hypothetical": False,
            "is_auto_adjustment": False,
            "created_at": datetime(2024, 12, 18, 10, 0, 0)
        },
        # Dec 22: New tyres (volvo)
        {
            "_id": uuid4(),
            "date": date(2024, 12, 22),
            "description": "new tyres",
            "amount": Decimal("-380.00"),
            "currency": "GBP",
            "rate_to_base": Decimal("1.0"),
            "account_id": hsbc_id,
            "story_id": None,
            "is_baseline": False,
            "is_hypothetical": False,
            "is_auto_adjustment": False,
            "created_at": datetime(2024, 12, 18, 11, 0, 0)
        },
        # Dec 28: Salary (baseline)
        {
            "_id": uuid4(),
            "date": date(2024, 12, 28),
            "description": "salary",
            "amount": Decimal("3000.00"),
            "currency": "GBP",
            "rate_to_base": Decimal("1.0"),
            "account_id": monzo_id,
            "story_id": None,
            "is_baseline": True,
            "is_hypothetical": False,
            "is_auto_adjustment": False,
            "created_at": datetime(2024, 12, 18, 9, 0, 0)  # Earlier created_at
        },
        # Dec 28: Rent (baseline) - same day as salary, should process AFTER
        {
            "_id": uuid4(),
            "date": date(2024, 12, 28),
            "description": "rent",
            "amount": Decimal("-1200.00"),
            "currency": "GBP",
            "rate_to_base": Decimal("1.0"),
            "account_id": monzo_id,
            "story_id": None,
            "is_baseline": True,
            "is_hypothetical": False,
            "is_auto_adjustment": False,
            "created_at": datetime(2024, 12, 18, 10, 0, 0)  # Later created_at
        },
        # Jan 01: Bills (baseline)
        {
            "_id": uuid4(),
            "date": date(2025, 1, 1),
            "description": "bills",
            "amount": Decimal("-100.00"),
            "currency": "GBP",
            "rate_to_base": Decimal("1.0"),
            "account_id": monzo_id,
            "story_id": None,
            "is_baseline": True,
            "is_hypothetical": False,
            "is_auto_adjustment": False,
            "created_at": datetime(2024, 12, 18, 12, 0, 0)
        }
    ]


@pytest.fixture
def mock_db(test_accounts, test_events):
    """Mock MongoDB database for testing."""
    class MockCursor:
        """Mock cursor for chaining .find().to_list() pattern."""
        def __init__(self, data):
            self.data = data

        async def to_list(self, length=None):
            """Return data as list."""
            return self.data

    class MockCollection:
        def __init__(self, data):
            self.data = data

        def find(self, query=None):
            """Return cursor (not awaited - matches Motor pattern)."""
            # Filter data based on query
            if query is None or not query:
                return MockCursor(self.data)

            filtered_data = []
            for item in self.data:
                # Handle date range queries
                if "date" in query and "$gte" in query["date"]:
                    item_date = item.get("date")
                    start = query["date"]["$gte"]
                    end = query["date"]["$lte"]
                    if not (start <= item_date <= end):
                        continue

                # Handle $or queries (for story filtering and hypothetical filtering)
                if "$or" in query:
                    or_conditions = query["$or"]

                    # Check if it's hypothetical filtering (old pattern)
                    if any("is_hypothetical" in cond for cond in or_conditions):
                        # Check if is_hypothetical is False or doesn't exist
                        is_hyp = item.get("is_hypothetical", False)
                        if is_hyp:  # Skip hypothetical events
                            continue

                    # Check if it's story filtering (story_id based)
                    elif any("story_id" in cond for cond in or_conditions):
                        # Need to match at least one condition
                        match_found = False
                        for condition in or_conditions:
                            if "story_id" in condition:
                                expected_story_id = condition["story_id"]
                                item_story_id = item.get("story_id")

                                if expected_story_id == item_story_id:
                                    match_found = True
                                    break
                            elif "is_baseline" in condition:
                                if item.get("is_baseline") == condition["is_baseline"]:
                                    match_found = True
                                    break

                        if not match_found:
                            continue

                filtered_data.append(item)

            return MockCursor(filtered_data)

        async def find_one(self, query=None, sort=None):
            """Find single document with optional sort."""
            # If sort is provided, sort the data and return first item
            if sort:
                sorted_data = sorted(
                    self.data,
                    key=lambda item: item.get(sort[0][0])
                )
                return sorted_data[0] if sorted_data else None

            # Otherwise return None (simplified mock)
            return None

    class MockSettings:
        """Mock settings collection."""
        async def find_one(self, query=None):
            """Return mock settings document."""
            return {
                "base_currency": "GBP",
                "rates": {
                    "CAD": Decimal("0.58"),  # 1 CAD = 0.58 GBP
                    "USD": Decimal("0.79"),  # 1 USD = 0.79 GBP
                }
            }

    class MockDB:
        def __init__(self):
            self.accounts = MockCollection(test_accounts)
            self.events = MockCollection(test_events)
            self.settings = MockSettings()

    return MockDB()


# ==================== Phase 2.1: Core Projection Tests ====================

@pytest.mark.asyncio
async def test_global_projection_basic(mock_db):
    """
    Test basic projection calculation with master timeline data.

    Expected trajectory (Phase 2.2 - multi-currency):
    - Starting: £13,210 (includes CAD account: -$500 × 0.58 = -£290)
    - After Dec 20 car rental (-£320): £12,890
    - After Dec 22 tyres (-£380): £12,510
    - After Dec 28 salary (+£3000): £15,510
    - After Dec 28 rent (-£1200): £14,310
    - After Jan 01 bills (-£100): £14,210
    """
    result = await calculate_global_projection(
        start_date=date(2024, 12, 18),
        end_date=date(2025, 1, 18),
        db=mock_db
    )

    # Test should have 5 events in chronological order
    assert len(result) == 5, "Should have 5 events in projection"

    # Test first event (Dec 20 car rental)
    assert result[0]["description"] == "car rental"
    assert result[0]["running_balance"] == Decimal("12890.00"), \
        "After car rental: £13,210 - £320 = £12,890"

    # Test second event (Dec 22 tyres)
    assert result[1]["description"] == "new tyres"
    assert result[1]["running_balance"] == Decimal("12510.00"), \
        "After tyres: £12,890 - £380 = £12,510"

    # Test Dec 28 events (salary BEFORE rent due to same-day ordering)
    assert result[2]["description"] == "salary", \
        "Salary should process first (positive amount)"
    assert result[2]["running_balance"] == Decimal("15510.00"), \
        "After salary: £12,510 + £3,000 = £15,510"

    assert result[3]["description"] == "rent", \
        "Rent should process after salary"
    assert result[3]["running_balance"] == Decimal("14310.00"), \
        "After rent: £15,510 - £1,200 = £14,310"


@pytest.mark.asyncio
async def test_same_day_ordering(mock_db):
    """
    Test same-day event ordering: amount DESC, created_at ASC.

    Dec 28 has two events:
    - Salary +£3000 (created 09:00)
    - Rent -£1200 (created 10:00)

    Salary should process FIRST (positive amount > negative amount).
    This prevents false negative balance warnings.
    """
    result = await calculate_global_projection(
        start_date=date(2024, 12, 28),
        end_date=date(2024, 12, 28),
        db=mock_db
    )

    # Should have exactly 2 events on Dec 28
    assert len(result) == 2, "Should have 2 events on Dec 28"

    # First event should be salary (positive amount DESC = higher priority)
    assert result[0]["description"] == "salary", \
        "Income should process before expenses (amount DESC)"
    assert result[0]["amount"] == Decimal("3000.00")

    # Second event should be rent
    assert result[1]["description"] == "rent"
    assert result[1]["amount"] == Decimal("-1200.00")

    # Verify balances stay positive throughout
    assert result[0]["running_balance"] > 0, \
        "Balance should stay positive after income"
    assert result[1]["running_balance"] > 0, \
        "Balance should stay positive after rent (no false warning)"


@pytest.mark.asyncio
async def test_starting_balance_from_accounts(mock_db):
    """
    Test projection starts from sum of all account balances.

    Accounts (Phase 2.2 - multi-currency):
    - Monzo (GBP): £2,500 × 1.0 = £2,500
    - HSBC (GBP): £11,000 × 1.0 = £11,000
    - Kat Credit (CAD): -$500 × 0.58 = -£290

    Expected starting balance: £2,500 + £11,000 - £290 = £13,210
    """
    result = await calculate_global_projection(
        start_date=date(2024, 12, 20),  # Start from first event
        end_date=date(2024, 12, 20),
        db=mock_db
    )

    # First event should start from correct balance
    # Starting: £13,210, first event: -£320
    assert result[0]["running_balance"] == Decimal("12890.00"), \
        "Starting balance should include all currencies: £13,210"


@pytest.mark.asyncio
async def test_exclude_hypothetical_from_all_view(mock_db):
    """
    Test that hypothetical events are excluded from ALL view.

    This will be fully tested in Phase 2.3, but we verify the
    basic filtering works.
    """
    # Add a hypothetical event to test data
    hypothetical_event = {
        "_id": uuid4(),
        "date": date(2024, 12, 25),
        "description": "hypothetical funding",
        "amount": Decimal("500.00"),
        "currency": "GBP",
        "rate_to_base": Decimal("1.0"),
        "account_id": UUID("11111111-1111-1111-1111-111111111111"),
        "story_id": None,
        "is_baseline": False,
        "is_hypothetical": True,  # Hypothetical flag
        "is_auto_adjustment": False,
        "created_at": datetime(2024, 12, 18, 13, 0, 0)
    }

    # Temporarily add to mock DB
    mock_db.events.data.append(hypothetical_event)

    try:
        result = await calculate_global_projection(
            start_date=date(2024, 12, 18),
            end_date=date(2025, 1, 18),
            db=mock_db
        )

        # Hypothetical event should NOT appear in results
        descriptions = [e["description"] for e in result]
        assert "hypothetical funding" not in descriptions, \
            "Hypothetical events should be excluded from ALL view"

    finally:
        # Clean up
        mock_db.events.data.remove(hypothetical_event)


@pytest.mark.asyncio
async def test_empty_events_projection(mock_db):
    """
    Test edge case: projection with no events in date range.

    Should return empty list (no events to project).
    """
    result = await calculate_global_projection(
        start_date=date(2025, 2, 1),  # Future date with no events
        end_date=date(2025, 2, 28),
        db=mock_db
    )

    assert len(result) == 0, "Should return empty list when no events in range"


# ==================== Phase 2.3: Story Projection Tests ====================

@pytest.mark.asyncio
async def test_story_projection_projected_funding_mode(mock_db):
    """
    Test story projection with 'projected' funding mode.

    Projected mode: Starting balance = projected balance on story.start_date

    Canada trip story:
    - start_date: Dec 19, 2024
    - funding_mode: "projected"
    - Expected starting balance: £13,210 (multi-currency starting balance)

    Events in story:
    - Dec 20: car rental -£320
    """
    # Create canada-trip story
    canada_story = {
        "_id": UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        "name": "canada-trip",
        "start_date": date(2024, 12, 19),
        "end_date": date(2025, 1, 10),
        "funding_mode": "projected",
        "funding_amount": None,
        "display_currency": "CAD",
        "default_account_id": UUID("33333333-3333-3333-3333-333333333333"),
        "created_at": datetime(2024, 12, 18, 8, 0, 0)
    }

    # Add story to mock DB
    class MockStories:
        def __init__(self, stories):
            self.data = stories

        async def find_one(self, query):
            story_id = query.get("_id")
            return next((s for s in self.data if s["_id"] == story_id), None)

    mock_db.stories = MockStories([canada_story])

    # Update car rental event to belong to canada-trip story
    for event in mock_db.events.data:
        if event["description"] == "car rental":
            event["story_id"] = canada_story["_id"]
            break

    try:
        result = await calculate_story_projection(
            story_id=str(canada_story["_id"]),
            start_date=date(2024, 12, 19),
            end_date=date(2025, 1, 10),
            db=mock_db
        )

        # Should have 4 events: car rental (story) + salary, rent, bills (baseline)
        assert len(result) == 4, "Should have car rental + 3 baseline events"

        # Events should be: car rental, salary, rent, bills
        descriptions = [e["description"] for e in result]
        assert "car rental" in descriptions
        assert "salary" in descriptions
        assert "rent" in descriptions
        assert "bills" in descriptions

        # Verify starting balance (projected mode) and running balance
        car_rental = next(e for e in result if e["description"] == "car rental")
        assert car_rental["running_balance"] == Decimal("12890.00"), \
            "Projected funding: starts at £13,210, car rental -£320 = £12,890"

    finally:
        # Clean up
        for event in mock_db.events.data:
            if event["description"] == "car rental":
                event["story_id"] = None


@pytest.mark.asyncio
async def test_story_projection_fixed_funding_mode(mock_db):
    """
    Test story projection with 'fixed' funding mode.

    Fixed mode: Starting balance = story.funding_amount (hypothetical)
    Creates a hypothetical funding event at story start.

    Skiing story:
    - start_date: Dec 23, 2024
    - funding_mode: "fixed"
    - funding_amount: £500
    - Expected starting balance: £500 (hypothetical funding)
    """
    # Create skiing story
    skiing_story = {
        "_id": UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
        "name": "skiing-2025",
        "start_date": date(2024, 12, 23),
        "end_date": date(2024, 12, 30),
        "funding_mode": "fixed",
        "funding_amount": Decimal("500.00"),
        "display_currency": "GBP",
        "default_account_id": UUID("11111111-1111-1111-1111-111111111111"),
        "created_at": datetime(2024, 12, 18, 8, 0, 0)
    }

    class MockStories:
        def __init__(self, stories):
            self.data = stories

        async def find_one(self, query):
            story_id = query.get("_id")
            return next((s for s in self.data if s["_id"] == story_id), None)

    mock_db.stories = MockStories([skiing_story])

    result = await calculate_story_projection(
        story_id=str(skiing_story["_id"]),
        start_date=date(2024, 12, 23),
        end_date=date(2024, 12, 30),
        db=mock_db
    )

    # Should have 1 baseline event (salary on Dec 28)
    assert len(result) >= 1, "Should have at least salary baseline event"

    # Fixed mode: starting_balance = £500 (from story.funding_amount)
    # No funding event created - funding is baked into starting_balance per spec
    # First visible event should be salary (+£3000) on Dec 28
    # Expected: £500 + £3000 = £3500
    salary_event = next((e for e in result if e["description"] == "salary"), None)
    assert salary_event is not None, "Should have salary baseline event"
    assert salary_event["running_balance"] == Decimal("3500.00"), \
        "Fixed funding: starts at £500, salary +£3000 = £3500"


@pytest.mark.asyncio
async def test_story_projection_projected_plus_funding_mode(mock_db):
    """
    Test story projection with 'projected_plus' funding mode.

    Projected_plus mode: Starting balance = projected + funding_amount
    """
    # Create volvo story
    volvo_story = {
        "_id": UUID("cccccccc-cccc-cccc-cccc-cccccccccccc"),
        "name": "volvo",
        "start_date": date(2024, 12, 22),
        "end_date": None,  # Ongoing
        "funding_mode": "projected_plus",
        "funding_amount": Decimal("1000.00"),
        "display_currency": "GBP",
        "default_account_id": UUID("22222222-2222-2222-2222-222222222222"),
        "created_at": datetime(2024, 12, 18, 8, 0, 0)
    }

    class MockStories:
        def __init__(self, stories):
            self.data = stories

        async def find_one(self, query):
            story_id = query.get("_id")
            return next((s for s in self.data if s["_id"] == story_id), None)

    mock_db.stories = MockStories([volvo_story])

    # Add tyres event to volvo story
    for event in mock_db.events.data:
        if event["description"] == "new tyres":
            event["story_id"] = volvo_story["_id"]
            break

    try:
        result = await calculate_story_projection(
            story_id=str(volvo_story["_id"]),
            start_date=date(2024, 12, 22),
            end_date=date(2025, 1, 10),
            db=mock_db
        )

        # Should have tyres + baseline events (no funding event)
        assert len(result) >= 1, "Should have tyres + baseline events"

        # Projected_plus mode: starting_balance = projected + funding_amount
        # No funding event created - funding is baked into starting_balance per spec
        # Projected on Dec 22 (day before) = £12,890
        # Plus funding: £12,890 + £1,000 = £13,890

        # First event should be tyres on Dec 22
        tyres_event = next((e for e in result if e["description"] == "new tyres"), None)
        assert tyres_event is not None, "Should have tyres event"
        # Expected: starting £13,890 - tyres £380 = £13,510
        assert tyres_event["running_balance"] == Decimal("13510.00"), \
            "Projected_plus: (£12,890 + £1,000) - £380 tyres = £13,510"

    finally:
        # Clean up
        for event in mock_db.events.data:
            if event["description"] == "new tyres":
                event["story_id"] = None


@pytest.mark.asyncio
async def test_hidden_events_affect_balance(mock_db):
    """
    CRITICAL TEST: Verify hidden story events affect running balance.

    This test validates the core architectural requirement from spec line 485:
    "running_balance += ALL events (including hidden stories)"

    Scenario:
    - Canada story (Dec 19-Jan 10) with car rental on Dec 20
    - Volvo story (Dec 22 onwards) with tyres on Dec 22
    - When viewing Canada story: tyres should be HIDDEN but affect balance
    """
    # Create Canada story
    canada_story = {
        "_id": UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        "name": "canada-trip",
        "start_date": date(2024, 12, 19),
        "funding_mode": "projected",
        "display_currency": "CAD",
    }

    # Create Volvo story
    volvo_story = {
        "_id": UUID("cccccccc-cccc-cccc-cccc-cccccccccccc"),
        "name": "volvo",
        "start_date": date(2024, 12, 22),
        "funding_mode": "projected",
        "display_currency": "GBP",
    }

    class MockStories:
        def __init__(self, stories):
            self.data = stories

        async def find_one(self, query):
            story_id = query.get("_id")
            return next((s for s in self.data if s["_id"] == story_id), None)

    mock_db.stories = MockStories([canada_story, volvo_story])

    # Assign car rental to Canada story, tyres to Volvo story
    for event in mock_db.events.data:
        if event["description"] == "car rental":
            event["story_id"] = canada_story["_id"]
        elif event["description"] == "new tyres":
            event["story_id"] = volvo_story["_id"]

    try:
        # View Canada story projection
        result = await calculate_story_projection(
            story_id=str(canada_story["_id"]),
            start_date=date(2024, 12, 19),
            end_date=date(2025, 1, 10),
            db=mock_db
        )

        # Verify: tyres (Volvo story) should NOT be in results
        descriptions = [e["description"] for e in result]
        assert "new tyres" not in descriptions, \
            "Tyres (Volvo story) should be hidden in Canada story view"

        # Verify: car rental (Canada story) SHOULD be in results
        assert "car rental" in descriptions, \
            "Car rental (Canada story) should be visible"

        # CRITICAL: Verify running balance includes tyres even though hidden
        # Timeline:
        # - Dec 20: car rental -£320 → balance = £13,210 - £320 = £12,890
        # - Dec 22: tyres -£380 (HIDDEN) → balance = £12,890 - £380 = £12,510
        # - Dec 28: salary +£3000 → balance = £12,510 + £3000 = £15,510

        car_rental = next(e for e in result if e["description"] == "car rental")
        salary = next(e for e in result if e["description"] == "salary")

        assert car_rental["running_balance"] == Decimal("12890.00"), \
            "After car rental: £13,210 - £320 = £12,890"

        # This is the key assertion: salary balance should reflect hidden tyres event
        assert salary["running_balance"] == Decimal("15510.00"), \
            "After hidden tyres (-£380) and salary (+£3000): £12,890 - £380 + £3000 = £15,510"

        # If we were NOT including hidden events, salary balance would be £15,890
        # (£12,890 + £3000), which would be WRONG

    finally:
        # Clean up
        for event in mock_db.events.data:
            if event["description"] in ["car rental", "new tyres"]:
                event["story_id"] = None


@pytest.mark.asyncio
async def test_multi_currency_story_projection(mock_db):
    """
    Test story projection with CAD story and mixed currency events.

    Note: Per spec-compliant implementation, funding_amount is stored in
    base currency (GBP). The story.display_currency is for UI display only.

    Validates:
    - Fixed funding mode with base currency amount
    - Mixed currency events in story projection
    - Running balance calculated in base currency
    """
    # Create a story with CAD as display currency
    canada_story = {
        "_id": UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        "name": "canada-trip",
        "start_date": date(2024, 12, 19),
        "funding_mode": "fixed",
        "funding_amount": Decimal("580.00"),  # £580 GBP (base currency)
        "display_currency": "CAD",  # For UI display only
        "default_account_id": UUID("11111111-1111-1111-1111-111111111111"),
        "created_at": datetime(2024, 12, 18, 8, 0, 0)
    }

    class MockStories:
        def __init__(self, stories):
            self.data = stories

        async def find_one(self, query):
            story_id = query.get("_id")
            return next((s for s in self.data if s["_id"] == story_id), None)

    mock_db.stories = MockStories([canada_story])

    # Assign car rental to Canada story
    for event in mock_db.events.data:
        if event["description"] == "car rental":
            event["story_id"] = canada_story["_id"]
            break

    try:
        result = await calculate_story_projection(
            story_id=str(canada_story["_id"]),
            start_date=date(2024, 12, 19),
            end_date=date(2025, 1, 10),
            db=mock_db
        )

        # Should have car rental + baseline events (no funding event)
        assert len(result) >= 1, "Should have at least car rental event"

        # Fixed mode: starting_balance = £580 (funding_amount in base currency)
        # No funding event created - funding is baked into starting_balance per spec

        # Verify car rental event
        car_rental = next((e for e in result if e["description"] == "car rental"), None)
        assert car_rental is not None, "Should have car rental event"

        # Expected: starting £580 - car rental £320 = £260
        assert car_rental["running_balance"] == Decimal("260.00"), \
            "Fixed funding: starts at £580, car rental -£320 = £260"

    finally:
        # Clean up
        for event in mock_db.events.data:
            if event["description"] == "car rental":
                event["story_id"] = None


@pytest.mark.asyncio
async def test_story_projection_fixed_mode_no_events(mock_db):
    """
    Test that fixed funding mode works correctly without creating events.

    Per spec-compliant implementation, funding is baked into starting_balance,
    not created as a separate event.

    Validates:
    - Fixed mode sets starting_balance = funding_amount
    - No funding event is created
    - Running balance calculated correctly from starting_balance
    """
    # Create story with fixed funding
    skiing_story = {
        "_id": UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
        "name": "skiing-2025",
        "start_date": date(2024, 12, 23),
        "funding_mode": "fixed",
        "funding_amount": Decimal("500.00"),
        "display_currency": "GBP",
        "default_account_id": UUID("11111111-1111-1111-1111-111111111111"),
        "created_at": datetime(2024, 12, 18, 8, 0, 0)
    }

    class MockStories:
        def __init__(self, stories):
            self.data = stories

        async def find_one(self, query):
            story_id = query.get("_id")
            return next((s for s in self.data if s["_id"] == story_id), None)

    mock_db.stories = MockStories([skiing_story])

    result = await calculate_story_projection(
        story_id=str(skiing_story["_id"]),
        start_date=date(2024, 12, 23),
        end_date=date(2024, 12, 30),
        db=mock_db
    )

    # Should have 1 baseline event (salary on Dec 28)
    assert len(result) >= 1, "Should have at least salary event"

    # Verify no funding event was created
    descriptions = [e.get("description", "") for e in result]
    assert not any("funding" in d.lower() for d in descriptions), \
        "Should not create funding event - funding is baked into starting_balance"

    # Verify starting balance is correct (£500 from funding_amount)
    salary_event = next((e for e in result if e["description"] == "salary"), None)
    assert salary_event is not None, "Should have salary event"
    # Expected: starting £500 + salary £3000 = £3500
    assert salary_event["running_balance"] == Decimal("3500.00"), \
        "Fixed mode: starting_balance £500 + salary £3000 = £3500"


@pytest.mark.asyncio
async def test_story_filtered_events_only(mock_db):
    """
    Test that story projection only includes baseline + story events.

    Should filter out events from other stories.
    """
    # Create two stories
    canada_story_id = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    volvo_story_id = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")

    canada_story = {
        "_id": canada_story_id,
        "name": "canada-trip",
        "start_date": date(2024, 12, 19),
        "end_date": date(2025, 1, 10),
        "funding_mode": "projected",
        "funding_amount": None,
        "display_currency": "CAD",
        "default_account_id": UUID("33333333-3333-3333-3333-333333333333"),
        "created_at": datetime(2024, 12, 18, 8, 0, 0)
    }

    class MockStories:
        def __init__(self, stories):
            self.data = stories

        async def find_one(self, query):
            story_id = query.get("_id")
            return next((s for s in self.data if s["_id"] == story_id), None)

    mock_db.stories = MockStories([canada_story])

    # Assign events to different stories
    for event in mock_db.events.data:
        if event["description"] == "car rental":
            event["story_id"] = canada_story_id
        elif event["description"] == "new tyres":
            event["story_id"] = volvo_story_id
        # salary, rent, bills remain baseline (story_id = None)

    try:
        result = await calculate_story_projection(
            story_id=str(canada_story_id),
            start_date=date(2024, 12, 18),
            end_date=date(2025, 1, 18),
            db=mock_db
        )

        # Should include: car rental (canada) + baseline events
        # Should exclude: tyres (volvo story)
        descriptions = [e["description"] for e in result]

        assert "car rental" in descriptions, "Should include canada-trip event"
        assert "salary" in descriptions, "Should include baseline events"
        assert "rent" in descriptions, "Should include baseline events"
        assert "bills" in descriptions, "Should include baseline events"
        assert "new tyres" not in descriptions, "Should exclude other story events"

    finally:
        # Clean up
        for event in mock_db.events.data:
            event["story_id"] = None


@pytest.mark.asyncio
async def test_multi_currency_starting_balance(mock_db):
    """
    Test starting balance includes all currencies converted to base.

    Accounts (from fixtures):
    - Monzo (GBP): £2,500
    - HSBC (GBP): £11,000
    - Kat Credit (CAD): -$500 × 0.58 = -£290

    Expected starting balance: £2,500 + £11,000 - £290 = £13,210
    """
    result = await calculate_global_projection(
        start_date=date(2024, 12, 20),
        end_date=date(2024, 12, 20),
        db=mock_db
    )

    # First event running balance should reflect multi-currency starting balance
    # Starting: £13,210, car rental: -£320
    assert result[0]["running_balance"] == Decimal("12890.00"), \
        "Starting balance should include CAD account converted to GBP"


@pytest.mark.asyncio
async def test_event_to_base_currency_conversion(mock_db):
    """
    Test event amounts are converted to base currency using locked rate_to_base.

    Test with CAD event:
    - Ski passes: -349 CAD
    - rate_to_base: 0.58 (1 CAD = 0.58 GBP at creation)
    - Expected base amount: -349 × 0.58 = -£202.42
    """
    # Create CAD event
    cad_event = {
        "_id": uuid4(),
        "date": date(2024, 12, 25),
        "description": "ski passes",
        "amount": Decimal("-349.00"),
        "currency": "CAD",
        "rate_to_base": Decimal("0.58"),
        "account_id": UUID("33333333-3333-3333-3333-333333333333"),
        "story_id": None,
        "is_baseline": False,
        "is_hypothetical": False,
        "is_auto_adjustment": False,
        "created_at": datetime(2024, 12, 18, 14, 0, 0)
    }

    # Add to mock DB
    mock_db.events.data.append(cad_event)

    try:
        result = await calculate_global_projection(
            start_date=date(2024, 12, 25),
            end_date=date(2024, 12, 25),
            db=mock_db
        )

        # Find the CAD event in results
        ski_event = next(e for e in result if e["description"] == "ski passes")

        # Verify base_amount was calculated correctly
        assert "base_amount" in ski_event, "Event should have base_amount calculated"
        assert ski_event["base_amount"] == Decimal("-202.42"), \
            "CAD event should convert to GBP using rate_to_base: -349 × 0.58 = -202.42"

    finally:
        mock_db.events.data.remove(cad_event)


@pytest.mark.asyncio
async def test_mixed_currency_running_balance(mock_db):
    """
    Test running balance calculation with mixed currencies.

    Starting balance: £13,210 (including converted CAD account)
    Dec 20: Car rental -£320 (GBP) → £12,890
    Dec 22: Tyres -£380 (GBP) → £12,510
    Dec 25: Ski passes -£202.42 (349 CAD @ 0.58) → £12,307.58
    Dec 28: Salary +£3,000 (GBP) → £15,307.58
    Dec 28: Rent -£1,200 (GBP) → £14,107.58
    """
    # Add CAD ski passes event
    ski_event = {
        "_id": uuid4(),
        "date": date(2024, 12, 25),
        "description": "ski passes",
        "amount": Decimal("-349.00"),
        "currency": "CAD",
        "rate_to_base": Decimal("0.58"),
        "account_id": UUID("33333333-3333-3333-3333-333333333333"),
        "story_id": None,
        "is_baseline": False,
        "is_hypothetical": False,
        "is_auto_adjustment": False,
        "created_at": datetime(2024, 12, 18, 14, 0, 0)
    }

    mock_db.events.data.append(ski_event)

    try:
        result = await calculate_global_projection(
            start_date=date(2024, 12, 18),
            end_date=date(2025, 1, 18),
            db=mock_db
        )

        # Should have 6 events now (5 original + 1 CAD)
        assert len(result) == 6, "Should have 6 events including CAD ski passes"

        # Verify running balances at key points
        car_rental = next(e for e in result if e["description"] == "car rental")
        assert car_rental["running_balance"] == Decimal("12890.00"), \
            "After car rental: £13,210 - £320 = £12,890"

        ski_passes = next(e for e in result if e["description"] == "ski passes")
        assert ski_passes["running_balance"] == Decimal("12307.58"), \
            "After ski passes: £12,510 - £202.42 = £12,307.58"

        rent = next(e for e in result if e["description"] == "rent")
        assert rent["running_balance"] == Decimal("14107.58"), \
            "Final balance after all events: £14,107.58"

    finally:
        mock_db.events.data.remove(ski_event)


@pytest.mark.asyncio
async def test_base_to_display_currency_conversion(mock_db):
    """
    Test conversion from base currency to display currency using current settings rates.

    Example: Display £202.42 (base GBP) as CAD
    - Base amount: £202.42
    - Settings rate GBP→CAD: 1.72
    - Display amount: £202.42 × 1.72 = $348.16 CAD

    Note: This is different from original event amount due to rate changes.
    Original: -349 CAD @ 0.58, Display: -348.16 CAD @ 1.72 (current rate)
    """
    # Mock settings with current rates
    settings = {
        "base_currency": "GBP",
        "rates": {
            "CAD": Decimal("1.72"),
            "USD": Decimal("1.27"),
            "EUR": Decimal("1.17")
        }
    }

    # Add settings to mock DB
    class MockSettings:
        def __init__(self, data):
            self.data = data

        async def find_one(self, query=None):
            return self.data

    mock_db.settings = MockSettings(settings)

    # Add CAD event
    ski_event = {
        "_id": uuid4(),
        "date": date(2024, 12, 25),
        "description": "ski passes",
        "amount": Decimal("-349.00"),
        "currency": "CAD",
        "rate_to_base": Decimal("0.58"),
        "account_id": UUID("33333333-3333-3333-3333-333333333333"),
        "story_id": None,
        "is_baseline": False,
        "is_hypothetical": False,
        "is_auto_adjustment": False,
        "created_at": datetime(2024, 12, 18, 14, 0, 0)
    }

    mock_db.events.data.append(ski_event)

    try:
        # Calculate projection with display_currency parameter
        result = await calculate_global_projection(
            start_date=date(2024, 12, 25),
            end_date=date(2024, 12, 25),
            display_currency="CAD",  # Request CAD display
            db=mock_db
        )

        ski = next(e for e in result if e["description"] == "ski passes")

        # Verify display amount (base converted to CAD at current rate)
        assert "display_amount" in ski, "Event should have display_amount"
        assert "display_currency" in ski, "Event should have display_currency"
        assert ski["display_currency"] == "CAD"

        # Base: -202.42 GBP × 1.72 = -348.16 CAD (rounded)
        assert ski["display_amount"] == Decimal("-348.16"), \
            "Display amount should use current rate: -202.42 × 1.72 = -348.16"

    finally:
        mock_db.events.data.remove(ski_event)
