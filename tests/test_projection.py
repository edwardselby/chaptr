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
                # Handle account_id queries (exact match)
                if "account_id" in query:
                    if item.get("account_id") != query["account_id"]:
                        continue

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

            # Handle _id query (exact match)
            if query and "_id" in query:
                target_id = query["_id"]
                for item in self.data:
                    if item.get("_id") == target_id:
                        return item
                return None

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

    # Fixed mode: starting_balance = £0, funding event adds £500
    # Funding event created with is_hypothetical=true per spec lines 163-182
    # First visible event should be funding event (+£500) on Dec 23
    # Then salary (+£3000) on Dec 28
    # Expected: £0 + £500 funding + £3000 salary = £3500
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

        # Projected_plus mode: starting_balance = projected, funding event adds amount
        # Funding event created with is_hypothetical=true per spec lines 163-182
        # Projected on Dec 22 (day before) = £12,890
        # Funding event adds: £1,000
        # Total after funding: £12,890 + £1,000 = £13,890

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
        "funding_amount": Decimal("1000.00"),  # $1000 CAD
        "display_currency": "CAD",
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

        # Should have funding event + car rental + baseline events
        assert len(result) >= 2, "Should have at least funding + car rental"

        # Fixed mode: Funding event created per spec lines 163-182
        # Verify funding event
        funding = result[0]
        assert funding["description"] == "Story funding: canada-trip"
        assert funding["amount"] == Decimal("1000.00")  # $1000 CAD
        assert funding["currency"] == "CAD"
        assert funding["rate_to_base"] == Decimal("0.58")  # 1 CAD = 0.58 GBP

        # CRITICAL: Verify funding base_amount is correct
        # $1000 CAD × 0.58 = £580 GBP
        assert funding["base_amount"] == Decimal("580.00"), \
            "$1000 CAD × 0.58 = £580 GBP"

        # Verify running balance uses base currency
        # Starting: 0 (fixed mode)
        # After funding: +£580
        assert funding["running_balance"] == Decimal("580.00"), \
            "Fixed mode starts at 0, funding adds £580 (converted from CAD)"

        # Verify car rental event
        car_rental = next((e for e in result if e["description"] == "car rental"), None)
        assert car_rental is not None, "Should have car rental event"

        # Expected: starting 0 + funding £580 - car rental £320 = £260
        assert car_rental["running_balance"] == Decimal("260.00"), \
            "After £580 funding and -£320 car rental = £260"

    finally:
        # Clean up
        for event in mock_db.events.data:
            if event["description"] == "car rental":
                event["story_id"] = None


@pytest.mark.asyncio
async def test_story_projection_with_hypothetical_funding(mock_db):
    """
    Test that fixed funding mode creates hypothetical funding events.

    Per spec lines 163-182: Funding adjustments create a funding event
    that transitions from hypothetical to real.

    Validates:
    - Fixed mode creates funding event
    - Funding event marked as is_hypothetical=True
    - Running balance calculated correctly with funding event
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

    # Should have funding event + salary
    assert len(result) >= 2, "Should have at least funding event + salary"

    # Verify funding event was created
    funding_event = result[0]
    assert funding_event["description"] == "Story funding: skiing-2025"
    assert funding_event["amount"] == Decimal("500.00")
    assert funding_event["is_hypothetical"] is True, \
        "Funding event should be marked as hypothetical"
    assert funding_event["running_balance"] == Decimal("500.00"), \
        "Fixed mode: starting 0 + funding £500 = £500"

    # Verify salary event
    salary_event = next((e for e in result if e["description"] == "salary"), None)
    assert salary_event is not None, "Should have salary event"
    # Expected: starting 0 + funding £500 + salary £3000 = £3500
    assert salary_event["running_balance"] == Decimal("3500.00"), \
        "After funding £500 and salary £3000 = £3500"


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


# ==================== Phase 2: Account Projection Tests (Task 4) ====================

@pytest.mark.asyncio
async def test_account_projection_basic(mock_db):
    """
    Test basic per-account projection with multiple events.

    Setup:
    - Account: Monzo (GBP), balance £2,500
    - Events: car rental -£320 (Dec 20), salary +£3,000 (Dec 28), rent -£1,200 (Dec 28)
    - Expected: running_balance calculated correctly for Monzo account only
    """
    monzo_id = "11111111-1111-1111-1111-111111111111"

    result = await calculate_account_projection(
        account_id=monzo_id,
        start_date=date(2024, 12, 18),
        end_date=date(2024, 12, 31),
        db=mock_db
    )

    # Should have 3 events for Monzo account
    assert len(result) == 3, f"Expected 3 events for Monzo, got {len(result)}"

    # Verify events are ordered correctly
    assert result[0]["description"] == "car rental"
    assert result[1]["description"] == "salary"  # Same day as rent, but income first
    assert result[2]["description"] == "rent"

    # Verify running balances
    # Starting: £2,500
    # After car rental (-£320): £2,180
    # After salary (+£3,000): £5,180
    # After rent (-£1,200): £3,980
    assert result[0]["running_balance"] == Decimal("2180.00"), \
        f"After car rental: expected £2,180, got {result[0]['running_balance']}"
    assert result[1]["running_balance"] == Decimal("5180.00"), \
        f"After salary: expected £5,180, got {result[1]['running_balance']}"
    assert result[2]["running_balance"] == Decimal("3980.00"), \
        f"After rent: expected £3,980, got {result[2]['running_balance']}"


@pytest.mark.asyncio
async def test_account_projection_multi_currency(mock_db):
    """
    Test account projection with events in different currencies.

    Setup:
    - Account: Kat Credit (CAD), balance -$500, rate_to_base 0.58
    - Events: None in test data for Kat Credit (all go to Monzo/HSBC)
    - Expected: empty result (no events for this account)
    """
    kat_credit_id = "33333333-3333-3333-3333-333333333333"

    result = await calculate_account_projection(
        account_id=kat_credit_id,
        start_date=date(2024, 12, 18),
        end_date=date(2024, 12, 31),
        db=mock_db
    )

    # No events assigned to Kat Credit in test data
    assert len(result) == 0, \
        f"Expected no events for Kat Credit, got {len(result)}"


@pytest.mark.asyncio
async def test_account_projection_no_events(mock_db):
    """
    Test account projection with no events in date range.

    Expected: empty list returned
    """
    hsbc_id = "22222222-2222-2222-2222-222222222222"

    # Query future date range where no events exist
    result = await calculate_account_projection(
        account_id=hsbc_id,
        start_date=date(2025, 3, 1),
        end_date=date(2025, 3, 31),
        db=mock_db
    )

    assert len(result) == 0, \
        f"Expected no events in March 2025, got {len(result)}"


@pytest.mark.asyncio
async def test_account_projection_same_day_ordering(mock_db):
    """
    Test same-day event ordering (income first).

    Setup:
    - Multiple events on Dec 28: salary +£3,000, rent -£1,200
    - Expected: salary applied first (amount DESC)
    """
    monzo_id = "11111111-1111-1111-1111-111111111111"

    result = await calculate_account_projection(
        account_id=monzo_id,
        start_date=date(2024, 12, 28),
        end_date=date(2024, 12, 28),
        db=mock_db
    )

    # Should have 2 events on Dec 28
    assert len(result) == 2, f"Expected 2 events on Dec 28, got {len(result)}"

    # Verify order: salary before rent (income first per spec)
    assert result[0]["description"] == "salary", \
        "First event should be salary (positive amount first)"
    assert result[1]["description"] == "rent", \
        "Second event should be rent"

    # Verify amounts show income processed first
    assert result[0]["amount"] > 0, "Salary should be positive"
    assert result[1]["amount"] < 0, "Rent should be negative"


# ==================== Phase 2.5: Warning Detection Tests (Tasks 9-12) ====================

@pytest.mark.asyncio
async def test_global_negative_warning():
    """
    Test detection of global balance going negative.

    Setup:
    - Projection result with negative running_balance
    - Expected: warning with date, amount, severity=critical
    """
    from core.projection import detect_global_negative_warnings

    # Create test projection with negative balance
    projection_result = [
        {
            "date": date(2024, 12, 20),
            "description": "car rental",
            "amount": Decimal("-320.00"),
            "running_balance": Decimal("2180.00")  # Positive
        },
        {
            "date": date(2024, 12, 25),
            "description": "large expense",
            "amount": Decimal("-3000.00"),
            "running_balance": Decimal("-820.00")  # NEGATIVE
        }
    ]

    warnings = detect_global_negative_warnings(projection_result)

    # Should have 1 warning
    assert len(warnings) == 1, f"Expected 1 warning, got {len(warnings)}"

    warning = warnings[0]
    assert warning["type"] == "negative_balance"
    assert warning["severity"] == "critical"
    assert warning["date"] == date(2024, 12, 25)
    assert warning["amount"] == Decimal("-820.00")
    assert warning["threshold"] == Decimal("0")
    assert "negative" in warning["message"].lower()


@pytest.mark.asyncio
async def test_account_negative_warning():
    """
    Test detection of account balance going negative.

    Setup:
    - Account: Monzo with projection going negative
    - Expected: account warning with name, date, amount
    """
    from core.projection import detect_account_negative_warnings

    account_id = "11111111-1111-1111-1111-111111111111"
    account_name = "Monzo"

    # Create test projection with negative balance
    projection_result = [
        {
            "date": date(2024, 12, 20),
            "description": "small expense",
            "amount": Decimal("-100.00"),
            "running_balance": Decimal("400.00")  # Positive
        },
        {
            "date": date(2024, 12, 22),
            "description": "large expense",
            "amount": Decimal("-800.00"),
            "running_balance": Decimal("-400.00")  # NEGATIVE
        }
    ]

    warnings = detect_account_negative_warnings(
        account_id=account_id,
        account_name=account_name,
        projection_result=projection_result
    )

    # Should have 1 warning
    assert len(warnings) == 1, f"Expected 1 warning, got {len(warnings)}"

    warning = warnings[0]
    assert warning["type"] == "account_negative"
    assert warning["severity"] == "critical"
    assert warning["date"] == date(2024, 12, 22)
    assert warning["amount"] == Decimal("-400.00")
    assert warning["account_name"] == "Monzo"
    assert str(warning["account_id"]) == account_id
    assert "Monzo" in warning["message"]
    assert "negative" in warning["message"].lower()


@pytest.mark.asyncio
async def test_story_spend_up_to_exceeded():
    """
    Test story exceeds spend_up_to goal.

    Setup:
    - Story: canada-trip, goal_type=spend_up_to, goal_amount=£1,000
    - Events: -£320 rental, -£150 gifts, -£600 hotel (total £1,070)
    - Expected: warning with £70 overspent
    """
    from core.projection import detect_story_goal_warnings

    story = {
        "_id": UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        "name": "canada-trip",
        "goal_type": "spend_up_to",
        "goal_amount": Decimal("1000.00"),
        "end_date": date(2025, 1, 5)
    }

    # Projection result with expenses totaling £1,070
    projection_result = [
        {
            "date": date(2024, 12, 20),
            "description": "car rental",
            "amount": Decimal("-320.00"),
            "is_baseline": False,
            "running_balance": Decimal("12680.00")
        },
        {
            "date": date(2024, 12, 25),
            "description": "gifts",
            "amount": Decimal("-150.00"),
            "is_baseline": False,
            "running_balance": Decimal("12530.00")
        },
        {
            "date": date(2024, 12, 28),
            "description": "salary",
            "amount": Decimal("3000.00"),
            "is_baseline": True,  # Baseline - excluded from spend calculation
            "running_balance": Decimal("15530.00")
        },
        {
            "date": date(2025, 1, 1),
            "description": "hotel",
            "amount": Decimal("-600.00"),
            "is_baseline": False,
            "running_balance": Decimal("14930.00")
        }
    ]

    warnings = detect_story_goal_warnings(story, projection_result)

    # Should have 1 warning
    assert len(warnings) == 1, f"Expected 1 warning, got {len(warnings)}"

    warning = warnings[0]
    assert warning["type"] == "goal_exceeded"
    assert warning["severity"] == "warning"
    assert warning["amount"] == Decimal("1070.00"), \
        f"Total spend should be £1,070 (320+150+600), got {warning['amount']}"
    assert warning["threshold"] == Decimal("1000.00")
    assert warning["story_name"] == "canada-trip"
    assert "over budget" in warning["message"]


@pytest.mark.asyncio
async def test_story_end_with_at_least_missed():
    """
    Test story misses end_with_at_least goal.

    Setup:
    - Story: savings, goal_type=end_with_at_least, goal_amount=£3,000
    - Final balance: £2,500
    - Expected: warning with £500 shortfall
    """
    from core.projection import detect_story_goal_warnings

    story = {
        "_id": UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
        "name": "savings",
        "goal_type": "end_with_at_least",
        "goal_amount": Decimal("3000.00"),
        "end_date": date(2025, 1, 31)
    }

    # Projection result with final balance £2,500
    projection_result = [
        {
            "date": date(2024, 12, 20),
            "description": "expense",
            "amount": Decimal("-500.00"),
            "is_baseline": False,
            "running_balance": Decimal("12500.00")
        },
        {
            "date": date(2025, 1, 31),
            "description": "final event",
            "amount": Decimal("0.00"),
            "is_baseline": False,
            "running_balance": Decimal("2500.00")  # Below goal
        }
    ]

    warnings = detect_story_goal_warnings(story, projection_result)

    # Should have 1 warning
    assert len(warnings) == 1, f"Expected 1 warning, got {len(warnings)}"

    warning = warnings[0]
    assert warning["type"] == "goal_missed"
    assert warning["severity"] == "warning"
    assert warning["amount"] == Decimal("2500.00")
    assert warning["threshold"] == Decimal("3000.00")
    assert warning["story_name"] == "savings"
    assert "short of goal" in warning["message"]
    assert "500.00" in warning["message"]  # Verify shortfall amount shown


@pytest.mark.asyncio
async def test_story_goal_none_no_warnings():
    """
    Test that stories with goal_type='none' produce no warnings.

    Expected: empty warnings list
    """
    from core.projection import detect_story_goal_warnings

    story = {
        "_id": UUID("cccccccc-cccc-cccc-cccc-cccccccccccc"),
        "name": "volvo",
        "goal_type": "none",  # No goal set
        "goal_amount": Decimal("0.00")
    }

    projection_result = [
        {
            "date": date(2024, 12, 20),
            "description": "expense",
            "amount": Decimal("-500.00"),
            "is_baseline": False,
            "running_balance": Decimal("12000.00")
        }
    ]

    warnings = detect_story_goal_warnings(story, projection_result)

    # Should have no warnings
    assert len(warnings) == 0, \
        f"Expected no warnings for goal_type='none', got {len(warnings)}"


# ==================== Comprehensive Warning Detection Tests (Task 5) ====================


@pytest.mark.asyncio
async def test_global_negative_warning_boundary_zero():
    """
    Balance exactly £0.00 should NOT trigger warning.

    Boundary case: Zero balance is not negative, no warning expected.
    """
    from core.projection import detect_global_negative_warnings

    projection_result = [
        {
            "date": date(2024, 12, 20),
            "description": "expense",
            "amount": Decimal("-100.00"),
            "running_balance": Decimal("100.00")
        },
        {
            "date": date(2024, 12, 25),
            "description": "final expense",
            "amount": Decimal("-100.00"),
            "running_balance": Decimal("0.00")  # Exactly zero
        }
    ]

    warnings = detect_global_negative_warnings(projection_result)

    # No warnings for zero balance
    assert len(warnings) == 0, \
        f"Expected no warnings for £0.00 balance, got {len(warnings)}"


@pytest.mark.asyncio
async def test_global_negative_warning_boundary_negative_penny():
    """
    Balance of -£0.01 should trigger warning.

    Boundary case: Even smallest negative balance should warn.
    """
    from core.projection import detect_global_negative_warnings

    projection_result = [
        {
            "date": date(2024, 12, 20),
            "description": "expense",
            "amount": Decimal("-100.00"),
            "running_balance": Decimal("99.99")
        },
        {
            "date": date(2024, 12, 25),
            "description": "small expense",
            "amount": Decimal("-100.00"),
            "running_balance": Decimal("-0.01")  # Tiny negative
        }
    ]

    warnings = detect_global_negative_warnings(projection_result)

    # Should have 1 warning
    assert len(warnings) == 1, f"Expected 1 warning for -£0.01, got {len(warnings)}"

    warning = warnings[0]
    assert warning["type"] == "negative_balance"
    assert warning["severity"] == "critical"
    assert warning["amount"] == Decimal("-0.01")
    assert "negative" in warning["message"].lower()


@pytest.mark.asyncio
async def test_global_negative_then_recovery():
    """
    Balance goes negative then recovers to positive.

    Expected: Warning only for the event that caused negative balance.
    Recovery event should not have warning.
    """
    from core.projection import detect_global_negative_warnings

    projection_result = [
        {
            "date": date(2024, 12, 20),
            "description": "large expense",
            "amount": Decimal("-1000.00"),
            "running_balance": Decimal("-500.00")  # NEGATIVE
        },
        {
            "date": date(2024, 12, 25),
            "description": "income",
            "amount": Decimal("700.00"),
            "running_balance": Decimal("200.00")  # Recovered to positive
        },
        {
            "date": date(2024, 12, 28),
            "description": "small expense",
            "amount": Decimal("-50.00"),
            "running_balance": Decimal("150.00")  # Still positive
        }
    ]

    warnings = detect_global_negative_warnings(projection_result)

    # Should have 1 warning only for the negative event
    assert len(warnings) == 1, f"Expected 1 warning, got {len(warnings)}"

    warning = warnings[0]
    assert warning["date"] == date(2024, 12, 20), \
        "Warning should be for the event that went negative"
    assert warning["amount"] == Decimal("-500.00")


@pytest.mark.asyncio
async def test_multiple_negative_warnings_in_projection():
    """
    Multiple events cause negative balance at different points.

    Expected: Separate warnings for each negative balance event.
    """
    from core.projection import detect_global_negative_warnings

    projection_result = [
        {
            "date": date(2024, 12, 20),
            "description": "expense 1",
            "amount": Decimal("-200.00"),
            "running_balance": Decimal("-100.00")  # WARNING 1
        },
        {
            "date": date(2024, 12, 22),
            "description": "small income",
            "amount": Decimal("50.00"),
            "running_balance": Decimal("-50.00")  # Still negative, WARNING 2
        },
        {
            "date": date(2024, 12, 25),
            "description": "expense 2",
            "amount": Decimal("-200.00"),
            "running_balance": Decimal("-250.00")  # Even more negative, WARNING 3
        }
    ]

    warnings = detect_global_negative_warnings(projection_result)

    # Should have 3 warnings (all events have negative balance)
    assert len(warnings) == 3, f"Expected 3 warnings, got {len(warnings)}"

    # Verify each warning has different date
    warning_dates = [w["date"] for w in warnings]
    assert warning_dates == [date(2024, 12, 20), date(2024, 12, 22), date(2024, 12, 25)]

    # All should be critical severity
    for warning in warnings:
        assert warning["severity"] == "critical"


@pytest.mark.asyncio
async def test_warning_message_includes_currency_and_amount():
    """
    Warning messages include currency symbol and formatted amount.

    Validates that warning messages are user-friendly with proper formatting.
    """
    from core.projection import detect_global_negative_warnings

    projection_result = [
        {
            "date": date(2024, 12, 25),
            "description": "large expense",
            "amount": Decimal("-2000.00"),
            "running_balance": Decimal("-1234.56")
        }
    ]

    warnings = detect_global_negative_warnings(projection_result)

    assert len(warnings) == 1

    warning = warnings[0]
    message = warning["message"]

    # Message should include "negative" keyword
    assert "negative" in message.lower(), \
        f"Message should mention 'negative', got: {message}"

    # Message should include the amount (verify it contains the number)
    assert "1234" in message or "1,234" in message, \
        f"Message should include formatted amount, got: {message}"

    # Verify warning structure
    assert warning["amount"] == Decimal("-1234.56")
    assert warning["date"] == date(2024, 12, 25)


@pytest.mark.asyncio
async def test_story_goal_warning_message_includes_shortfall():
    """
    Story goal warnings show exact shortfall/overspend amount in message.

    Tests both spend_up_to (overspend) and end_with_at_least (shortfall).
    """
    from core.projection import detect_story_goal_warnings

    # Test 1: spend_up_to overspent by £234
    story_spend = {
        "_id": UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        "name": "canada-trip",
        "goal_type": "spend_up_to",
        "goal_amount": Decimal("1000.00"),
        "end_date": date(2025, 1, 5)
    }

    projection_spend = [
        {
            "date": date(2024, 12, 20),
            "description": "expense",
            "amount": Decimal("-1234.00"),
            "is_baseline": False,
            "running_balance": Decimal("12000.00")
        }
    ]

    warnings_spend = detect_story_goal_warnings(story_spend, projection_spend)

    assert len(warnings_spend) == 1
    assert "over budget" in warnings_spend[0]["message"]
    assert warnings_spend[0]["amount"] == Decimal("1234.00")
    assert warnings_spend[0]["threshold"] == Decimal("1000.00")

    # Test 2: end_with_at_least short by £500
    story_savings = {
        "_id": UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
        "name": "savings",
        "goal_type": "end_with_at_least",
        "goal_amount": Decimal("3000.00"),
        "end_date": date(2025, 1, 31)
    }

    projection_savings = [
        {
            "date": date(2025, 1, 31),
            "description": "final",
            "amount": Decimal("0.00"),
            "is_baseline": False,
            "running_balance": Decimal("2500.00")
        }
    ]

    warnings_savings = detect_story_goal_warnings(story_savings, projection_savings)

    assert len(warnings_savings) == 1
    assert "short of goal" in warnings_savings[0]["message"]
    assert "500" in warnings_savings[0]["message"], \
        "Message should include £500 shortfall"


@pytest.mark.asyncio
async def test_warning_on_first_event():
    """
    First event in projection causes negative balance.

    Edge case: Warning should appear even on first event.
    """
    from core.projection import detect_global_negative_warnings

    projection_result = [
        {
            "date": date(2024, 12, 20),
            "description": "large expense",
            "amount": Decimal("-500.00"),
            "running_balance": Decimal("-400.00")  # First event goes negative
        },
        {
            "date": date(2024, 12, 25),
            "description": "income",
            "amount": Decimal("500.00"),
            "running_balance": Decimal("100.00")
        }
    ]

    warnings = detect_global_negative_warnings(projection_result)

    # Should have 1 warning on first event
    assert len(warnings) == 1
    assert warnings[0]["date"] == date(2024, 12, 20), \
        "Warning should be for first event"
    assert warnings[0]["amount"] == Decimal("-400.00")


@pytest.mark.asyncio
async def test_warning_on_last_event():
    """
    Last event in projection causes negative balance.

    Edge case: Warning should appear even on last event.
    """
    from core.projection import detect_global_negative_warnings

    projection_result = [
        {
            "date": date(2024, 12, 20),
            "description": "income",
            "amount": Decimal("100.00"),
            "running_balance": Decimal("100.00")
        },
        {
            "date": date(2024, 12, 25),
            "description": "small expense",
            "amount": Decimal("-50.00"),
            "running_balance": Decimal("50.00")
        },
        {
            "date": date(2024, 12, 28),
            "description": "another expense",
            "amount": Decimal("-30.00"),
            "running_balance": Decimal("20.00")
        },
        {
            "date": date(2024, 12, 31),
            "description": "final large expense",
            "amount": Decimal("-100.00"),
            "running_balance": Decimal("-80.00")  # Last event goes negative
        }
    ]

    warnings = detect_global_negative_warnings(projection_result)

    # Should have 1 warning on last event only
    assert len(warnings) == 1
    assert warnings[0]["date"] == date(2024, 12, 31), \
        "Warning should be for last event"
    assert warnings[0]["amount"] == Decimal("-80.00")


@pytest.mark.asyncio
async def test_story_goal_with_baseline_events_excluded():
    """
    spend_up_to goal excludes baseline events from spend calculation.

    Critical test: Baseline events should NOT count toward story spend.
    """
    from core.projection import detect_story_goal_warnings

    story = {
        "_id": UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        "name": "canada-trip",
        "goal_type": "spend_up_to",
        "goal_amount": Decimal("1000.00"),
        "end_date": date(2025, 1, 5)
    }

    projection_result = [
        {
            "date": date(2024, 12, 20),
            "description": "car rental",
            "amount": Decimal("-300.00"),
            "is_baseline": False,  # Story event
            "running_balance": Decimal("12700.00")
        },
        {
            "date": date(2024, 12, 25),
            "description": "gifts",
            "amount": Decimal("-150.00"),
            "is_baseline": False,  # Story event
            "running_balance": Decimal("12550.00")
        },
        {
            "date": date(2024, 12, 28),
            "description": "salary",
            "amount": Decimal("3000.00"),
            "is_baseline": True,  # BASELINE - should be EXCLUDED
            "running_balance": Decimal("15550.00")
        },
        {
            "date": date(2024, 12, 30),
            "description": "rent",
            "amount": Decimal("-1500.00"),
            "is_baseline": True,  # BASELINE - should be EXCLUDED
            "running_balance": Decimal("14050.00")
        }
    ]

    warnings = detect_story_goal_warnings(story, projection_result)

    # Total story spend: £300 + £150 = £450 (baseline excluded)
    # Goal: £1,000
    # Should have NO warning (£450 < £1,000)
    assert len(warnings) == 0, \
        f"Expected no warning (spend £450 < goal £1,000), got {len(warnings)} warnings"


@pytest.mark.asyncio
async def test_story_goal_zero_amount():
    """
    Story with goal_amount = £0.00 edge case.

    Any expense should trigger warning when goal is zero.
    """
    from core.projection import detect_story_goal_warnings

    story = {
        "_id": UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        "name": "no-spend",
        "goal_type": "spend_up_to",
        "goal_amount": Decimal("0.00"),  # Zero budget
        "end_date": date(2025, 1, 5)
    }

    projection_result = [
        {
            "date": date(2024, 12, 20),
            "description": "tiny expense",
            "amount": Decimal("-0.01"),
            "is_baseline": False,
            "running_balance": Decimal("12999.99")
        }
    ]

    warnings = detect_story_goal_warnings(story, projection_result)

    # Should have warning (any spend > £0)
    assert len(warnings) == 1, \
        "Expected warning for any expense when goal is £0.00"

    warning = warnings[0]
    assert warning["type"] == "goal_exceeded"
    assert warning["amount"] == Decimal("0.01")  # Spent 1 penny
    assert warning["threshold"] == Decimal("0.00")


# ==================== Gap Indicators Integration Tests ====================
# Phase 2.4 - Tasks 2, 3, 4


@pytest.mark.asyncio
async def test_story_projection_includes_gap_indicators(mock_db):
    """
    Integration test: Story projection includes gap indicators for hidden events.

    Scenario:
    - Canada trip story (display_currency: CAD)
    - Volvo story with parts event -£180 on Dec 22 (hidden from canada view)
    - Expected: car rental event has gap_indicator showing -$309.60 CAD delta

    See spec: Projection Engine > Gap Indicators
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

    # Create volvo story
    volvo_story = {
        "_id": UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
        "name": "volvo",
        "start_date": date(2024, 12, 15),
        "end_date": date(2025, 1, 15),
        "funding_mode": "projected",
        "funding_amount": None,
        "display_currency": "GBP",
        "default_account_id": UUID("22222222-2222-2222-2222-222222222222"),  # HSBC
        "created_at": datetime(2024, 12, 18, 9, 0, 0)
    }

    # Add stories to mock DB
    class MockStories:
        def __init__(self, stories):
            self.data = stories

        async def find_one(self, query):
            story_id = query.get("_id")
            return next((s for s in self.data if s["_id"] == story_id), None)

    mock_db.stories = MockStories([canada_story, volvo_story])

    # Override settings with correct rate format for convert_from_base_currency
    # Rates should be "1 base = X display" (not "1 display = X base")
    class MockSettingsOverride:
        async def find_one(self, query=None):
            return {
                "base_currency": "GBP",
                "rates": {
                    "CAD": Decimal("1.72"),  # 1 GBP = 1.72 CAD (inverse of 0.58)
                    "USD": Decimal("1.27")
                }
            }

    mock_db.settings = MockSettingsOverride()

    # Update events:
    # - car rental -> canada-trip
    # - new tyres -> volvo (will be hidden when viewing canada-trip)
    for event in mock_db.events.data:
        if event["description"] == "car rental":
            event["story_id"] = canada_story["_id"]
        elif event["description"] == "new tyres":
            event["story_id"] = volvo_story["_id"]
            event["description"] = "parts [volvo]"  # Rename for clarity
            event["amount"] = Decimal("-180.00")  # Simplify amount

    try:
        # Calculate canada-trip projection
        result = await calculate_story_projection(
            story_id=str(canada_story["_id"]),
            start_date=date(2024, 12, 19),
            end_date=date(2025, 1, 10),
            db=mock_db
        )

        # Visible events: car rental (canada-trip) + salary, rent, bills (baseline)
        # Hidden events: parts (volvo) on Dec 22
        descriptions = [e["description"] for e in result]
        assert "car rental" in descriptions, "car rental should be visible (canada-trip story)"
        assert "salary" in descriptions, "salary should be visible (baseline)"
        assert "parts [volvo]" not in descriptions, "parts should be hidden (volvo story)"

        # Find car rental event
        car_rental = next(e for e in result if e["description"] == "car rental")

        # Verify gap indicator exists
        assert "gap_indicator" in car_rental, \
            "car rental should have gap_indicator (hidden volvo parts event between car rental and salary)"

        gap = car_rental["gap_indicator"]

        # Verify gap structure
        assert gap["type"] == "gap", "gap type should be 'gap'"
        assert gap["delta_base"] == Decimal("-180.00"), \
            "delta_base should be -£180 (parts event)"

        # Verify currency conversion: -£180 * 1.72 = -$309.60 CAD
        # Settings has CAD rate: 1.72 (1 GBP = 1.72 CAD)
        # So conversion from GBP to CAD: -180 * 1.72 = -309.60
        expected_delta_cad = Decimal("-180.00") * Decimal("1.72")

        assert gap["delta_display"] == expected_delta_cad, \
            f"delta_display should be {expected_delta_cad} CAD (converted from -£180)"

        assert gap["display_currency"] == "CAD", \
            "display_currency should match story's display_currency"

        assert gap["hidden_event_count"] == 1, \
            "Should show 1 hidden event (parts)"

        # Verify date range
        assert gap["date_range"]["start"] == date(2024, 12, 22), \
            "Gap start date should be Dec 22 (parts event date)"
        assert gap["date_range"]["end"] == date(2024, 12, 22), \
            "Gap end date should be Dec 22 (single event)"

        # Verify hidden events included for frontend expansion
        assert len(gap["hidden_events"]) == 1, \
            "Should include 1 hidden event for expansion"
        assert gap["hidden_events"][0]["description"] == "parts [volvo]", \
            "Hidden event should be parts event"

    finally:
        # Clean up
        for event in mock_db.events.data:
            if event["description"] == "car rental":
                event["story_id"] = None
            elif event["description"] == "parts [volvo]":
                event["story_id"] = None
                event["description"] = "new tyres"
                event["amount"] = Decimal("-380.00")


@pytest.mark.asyncio
async def test_story_projection_gap_with_multiple_hidden_stories(mock_db):
    """
    Integration test: Multiple hidden stories create cumulative gap delta.

    Scenario:
    - Canada trip story viewing
    - Volvo parts on Dec 22: -£180
    - Home improvement on Dec 23: -£150
    - Expected: car rental has gap with cumulative delta -£330

    Tests Task 3: Calculate delta amount (cumulative)
    """
    # Create stories
    canada_story = {
        "_id": UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        "name": "canada-trip",
        "start_date": date(2024, 12, 19),
        "end_date": date(2025, 1, 10),
        "funding_mode": "projected",
        "funding_amount": None,
        "display_currency": "GBP",
        "default_account_id": UUID("11111111-1111-1111-1111-111111111111"),
        "created_at": datetime(2024, 12, 18, 8, 0, 0)
    }

    volvo_story = {
        "_id": UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
        "name": "volvo",
        "start_date": date(2024, 12, 15),
        "end_date": date(2025, 1, 15),
        "funding_mode": "projected",
        "funding_amount": None,
        "display_currency": "GBP",
        "default_account_id": UUID("22222222-2222-2222-2222-222222222222"),
        "created_at": datetime(2024, 12, 18, 9, 0, 0)
    }

    home_story = {
        "_id": UUID("cccccccc-cccc-cccc-cccc-cccccccccccc"),
        "name": "home-improvement",
        "start_date": date(2024, 12, 15),
        "end_date": date(2025, 1, 15),
        "funding_mode": "projected",
        "funding_amount": None,
        "display_currency": "GBP",
        "default_account_id": UUID("22222222-2222-2222-2222-222222222222"),
        "created_at": datetime(2024, 12, 18, 10, 0, 0)
    }

    class MockStories:
        def __init__(self, stories):
            self.data = stories

        async def find_one(self, query):
            story_id = query.get("_id")
            return next((s for s in self.data if s["_id"] == story_id), None)

    mock_db.stories = MockStories([canada_story, volvo_story, home_story])

    # Add a new home-improvement event
    home_event = {
        "_id": uuid4(),
        "date": date(2024, 12, 23),
        "description": "paint supplies",
        "amount": Decimal("-150.00"),
        "currency": "GBP",
        "rate_to_base": Decimal("1.0"),
        "account_id": UUID("22222222-2222-2222-2222-222222222222"),
        "story_id": home_story["_id"],
        "is_baseline": False,
        "is_hypothetical": False,
        "is_auto_adjustment": False,
        "created_at": datetime(2024, 12, 18, 13, 0, 0)
    }

    mock_db.events.data.append(home_event)

    # Update existing events
    for event in mock_db.events.data:
        if event["description"] == "car rental":
            event["story_id"] = canada_story["_id"]
        elif event["description"] == "new tyres":
            event["story_id"] = volvo_story["_id"]
            event["description"] = "parts [volvo]"
            event["amount"] = Decimal("-180.00")

    try:
        result = await calculate_story_projection(
            story_id=str(canada_story["_id"]),
            start_date=date(2024, 12, 19),
            end_date=date(2025, 1, 10),
            db=mock_db
        )

        # Find car rental event
        car_rental = next(e for e in result if e["description"] == "car rental")

        # Verify gap indicator
        assert "gap_indicator" in car_rental, \
            "car rental should have gap_indicator"

        gap = car_rental["gap_indicator"]

        # Verify cumulative delta: -£180 (volvo) + -£150 (home) = -£330
        assert gap["delta_base"] == Decimal("-330.00"), \
            "delta_base should be cumulative: -£180 + -£150 = -£330"

        assert gap["hidden_event_count"] == 2, \
            "Should show 2 hidden events (volvo parts + home paint)"

        # Verify date range spans both events
        assert gap["date_range"]["start"] == date(2024, 12, 22), \
            "Gap start should be Dec 22 (first hidden event)"
        assert gap["date_range"]["end"] == date(2024, 12, 23), \
            "Gap end should be Dec 23 (last hidden event)"

        # Verify both hidden events included
        assert len(gap["hidden_events"]) == 2, \
            "Should include 2 hidden events"

        hidden_descriptions = [e["description"] for e in gap["hidden_events"]]
        assert "parts [volvo]" in hidden_descriptions
        assert "paint supplies" in hidden_descriptions

    finally:
        # Clean up
        mock_db.events.data = [e for e in mock_db.events.data if e["_id"] != home_event["_id"]]
        for event in mock_db.events.data:
            if event["description"] == "car rental":
                event["story_id"] = None
            elif event["description"] == "parts [volvo]":
                event["story_id"] = None
                event["description"] = "new tyres"
                event["amount"] = Decimal("-380.00")


@pytest.mark.asyncio
async def test_global_projection_no_gaps(mock_db):
    """
    Integration test: Global (ALL) projection has no gap indicators.

    Gap indicators only appear in story-filtered views.
    In ALL view, all events are visible, so no gaps exist.

    Tests: Gap detection logic correctly identifies when all events are visible
    """
    # Add stories to events (but we're viewing ALL)
    canada_story_id = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    volvo_story_id = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")

    for event in mock_db.events.data:
        if event["description"] == "car rental":
            event["story_id"] = canada_story_id
        elif event["description"] == "new tyres":
            event["story_id"] = volvo_story_id

    try:
        # Calculate global projection (ALL view)
        result = await calculate_global_projection(
            start_date=date(2024, 12, 18),
            end_date=date(2025, 1, 18),
            db=mock_db
        )

        # Verify no gap indicators in ANY event
        for event in result:
            assert "gap_indicator" not in event, \
                f"Global projection should have NO gap indicators, but {event['description']} has one"

        # Verify all events are present (no hidden events)
        descriptions = [e["description"] for e in result]
        assert "car rental" in descriptions
        assert "new tyres" in descriptions
        assert "salary" in descriptions
        assert "rent" in descriptions
        assert "bills" in descriptions

    finally:
        # Clean up
        for event in mock_db.events.data:
            if event["description"] in ["car rental", "new tyres"]:
                event["story_id"] = None
