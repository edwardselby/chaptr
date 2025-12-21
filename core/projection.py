"""
Projection engine for calculating balance trajectories.

Calculates running balances across different views (ALL, story, account).

Implementation:
- Phase 2.1: Core projection foundation
- Phase 2.2: Multi-currency conversion

See spec: Projection Engine
"""

from typing import List, Dict, Optional
from datetime import date
from decimal import Decimal, ROUND_HALF_UP


def convert_to_base_currency(amount: Decimal, rate_to_base: Decimal) -> Decimal:
    """
    Convert an amount from its native currency to base currency.

    Uses the locked rate_to_base from event/account creation.

    Args:
        amount: Amount in native currency
        rate_to_base: Conversion rate (1 native = X base), locked at creation

    Returns:
        Amount in base currency, rounded to 2 decimal places

    Example:
        >>> convert_to_base_currency(Decimal("-349"), Decimal("0.58"))
        Decimal('-202.42')
    """
    base_amount = amount * rate_to_base
    return base_amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def convert_from_base_currency(
    base_amount: Decimal,
    display_currency: str,
    base_currency: str,
    rates: Dict[str, Decimal]
) -> Decimal:
    """
    Convert an amount from base currency to display currency.

    Uses current rates from settings (not locked rates).

    Args:
        base_amount: Amount in base currency
        display_currency: Target currency code (e.g., "CAD")
        base_currency: Base currency code (e.g., "GBP")
        rates: Current conversion rates from settings

    Returns:
        Amount in display currency, rounded to 2 decimal places

    Example:
        >>> convert_from_base_currency(
        ...     Decimal("-202.42"),
        ...     "CAD",
        ...     "GBP",
        ...     {"CAD": Decimal("1.72")}
        ... )
        Decimal('-348.16')
    """
    if display_currency == base_currency:
        return base_amount

    display_rate = rates.get(display_currency, Decimal("1"))
    display_amount = base_amount * display_rate
    return display_amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


async def calculate_global_projection(
    start_date: date,
    end_date: date,
    view: str = "all",
    include_hypothetical: bool = False,
    display_currency: Optional[str] = None,
    db = None
) -> List[Dict]:
    """
    Calculate global balance projection across all accounts and stories.

    Algorithm (from spec: Projection Engine > Global Calculation):
        1. Sum all account.current_balance as starting point
        2. Fetch events in date range (baseline + all stories)
        3. Apply same-day ordering: amount DESC, created_at ASC
        4. Calculate running balance for each event
        5. Handle hypothetical funding exclusion (if view='all')
        6. Convert to display currency if requested

    Phase 2.1 Implementation:
    - ✅ Query all accounts, sum current_balance
    - ✅ Query events in range
    - ✅ Apply same-day ordering per spec
    - ✅ Calculate running balance
    - ✅ Filter hypothetical if view='all'

    Phase 2.2 Implementation:
    - ✅ Multi-currency starting balance (convert all to base)
    - ✅ Event → base currency conversion
    - ✅ Base → display currency conversion
    - ✅ Optimized database queries (filter at DB level)

    Args:
        start_date: Projection start date
        end_date: Projection end date
        view: 'all', 'all_what_if', or story filter
        include_hypothetical: Include hypothetical funding events
        display_currency: Optional currency for display conversion
        db: MongoDB database instance

    Returns:
        List of events with running_balance and optional display amounts

    See spec: Projection Engine > Global Calculation
    """
    # Get settings for currency conversion (if needed)
    settings = None
    if display_currency:
        settings = await db.settings.find_one()

    # Step 1: Sum all account current_balance as starting point
    # Phase 2.2: Include ALL currencies, convert to base
    accounts = await db.accounts.find({"is_archived": False}).to_list()
    starting_balance = Decimal("0")

    for acc in accounts:
        balance = acc.get("current_balance", Decimal("0"))
        rate_to_base = acc.get("rate_to_base", Decimal("1"))

        # Convert to base currency
        base_balance = convert_to_base_currency(balance, rate_to_base)
        starting_balance += base_balance

    # Step 2: Fetch events in date range
    # Phase 2.2: Filter at database level for performance (Task 255)
    query_filter = {
        "date": {"$gte": start_date, "$lte": end_date}
    }

    # For ALL view, exclude hypothetical unless include_hypothetical=True
    if not include_hypothetical:
        query_filter["$or"] = [
            {"is_hypothetical": {"$exists": False}},
            {"is_hypothetical": False}
        ]

    events = await db.events.find(query_filter).to_list()

    # Step 3: Apply same-day ordering per spec
    # Sort by: date ASC, amount DESC (income first), created_at ASC (tie-breaker)
    # Use base_amount for sorting to handle mixed currencies correctly
    events_with_base = []
    for event in events:
        amount = event.get("amount", Decimal("0"))
        rate_to_base = event.get("rate_to_base", Decimal("1"))
        base_amount = convert_to_base_currency(amount, rate_to_base)

        events_with_base.append({
            **event,
            "base_amount": base_amount
        })

    events_with_base.sort(
        key=lambda e: (
            e.get("date"),
            -e.get("base_amount", Decimal("0")),  # Sort by base amount DESC
            e.get("created_at")
        )
    )

    # Step 4: Calculate running balance for each event
    running_balance = starting_balance
    results = []

    for event in events_with_base:
        # Add event base_amount to running balance
        base_amount = event.get("base_amount", Decimal("0"))
        running_balance += base_amount

        # Create result dict with running_balance
        result_event = {**event, "running_balance": running_balance}

        # Step 5: Add display currency conversion if requested
        if display_currency and settings:
            display_amount = convert_from_base_currency(
                base_amount,
                display_currency,
                settings.get("base_currency", "GBP"),
                settings.get("rates", {})
            )
            result_event["display_amount"] = display_amount
            result_event["display_currency"] = display_currency

        results.append(result_event)

    return results


async def calculate_story_starting_balance(
    story: Dict,
    db
) -> Decimal:
    """
    Calculate starting balance for story based on funding mode.

    Three modes:
    - projected: Calculate projected balance on story.start_date
    - fixed: Use story.funding_amount
    - projected_plus: Projected + story.funding_amount

    Args:
        story: Story document with funding_mode, funding_amount, start_date
        db: MongoDB database instance

    Returns:
        Starting balance for story projection

    See spec: Stories > Funding Modes
    """
    funding_mode = story.get("funding_mode", "projected")

    if funding_mode == "projected":
        # Calculate projected balance on story start date
        # Uses global projection to include ALL events (baseline + story events)
        # This gives the real projected balance at that point in time
        from datetime import timedelta

        # Use a date far in the past to ensure we capture all events
        # This handles both future story dates (normal) and past dates (testing)
        early_date = story.get("start_date") - timedelta(days=365*5)

        # Calculate global projection up to DAY BEFORE story start
        # We want the balance at the START of the story date, not after events on that date
        day_before_story = story.get("start_date") - timedelta(days=1)

        projection = await calculate_global_projection(
            start_date=early_date,
            end_date=day_before_story,
            include_hypothetical=False,  # Don't include hypothetical events
            db=db
        )

        # Return final balance if events exist
        if projection:
            return projection[-1]["running_balance"]
        else:
            # No events before story start, return sum of account balances
            accounts = await db.accounts.find({"is_archived": False}).to_list()
            return sum(
                convert_to_base_currency(
                    acc.get("current_balance", Decimal("0")),
                    acc.get("rate_to_base", Decimal("1"))
                )
                for acc in accounts
            )

    elif funding_mode == "fixed":
        # Fixed mode: Start at 0, funding event will add the money
        return Decimal("0")

    elif funding_mode == "projected_plus":
        # Projected_plus mode: Start at projected balance, funding event adds adjustment
        # Recursively calculate projected mode (without the funding adjustment)
        projected_story = {**story, "funding_mode": "projected"}
        projected_balance = await calculate_story_starting_balance(projected_story, db)
        return projected_balance

    else:
        # Default to projected mode
        return Decimal("0")


async def calculate_story_projection(
    story_id: str,
    start_date: date,
    end_date: date,
    db = None
) -> List[Dict]:
    """
    Calculate story-filtered projection with funding modes.

    Algorithm (from spec: Projection Engine > Filtered Calculation):
        1. Get story funding_mode
        2. Calculate starting_balance based on mode:
           - projected: calc balance on story.start_date
           - fixed: use story.funding_amount
           - projected_plus: projected + story.funding_amount
        3. Fetch ALL events in date range (not just baseline + this story)
        4. Calculate running_balance using ALL events (including hidden stories)
        5. Display only visible events (baseline OR this story)
        6. Generate gap indicators for hidden events (Phase 2.4)

    Key Insight (Spec Line 485):
    - Display: baseline + this story events only
    - Calculate balance: ALL events (including hidden story events)
    - Hidden events affect balance but aren't shown (gap indicators show delta)

    Phase 2.3 Implementation:
    - ✅ All three funding modes
    - ✅ Fetch ALL events, display filtered
    - ✅ Running balance includes hidden story events
    - ✅ Hypothetical funding event creation
    - TODO Phase 2.4: Gap indicators with delta
    - TODO Phase 2.4: Convert to display_currency

    Args:
        story_id: Story UUID
        start_date: Projection start date
        end_date: Projection end date
        db: MongoDB database instance

    Returns:
        List of VISIBLE events with running_balance (balance includes hidden events)

    See spec: Projection Engine > Filtered Calculation
    """
    from uuid import UUID

    # Step 1: Get story
    story = await db.stories.find_one({"_id": UUID(story_id)})
    if not story:
        return []

    # Step 2: Calculate starting balance based on funding mode
    starting_balance = await calculate_story_starting_balance(story, db)

    # Step 3: Create hypothetical funding event if needed
    funding_mode = story.get("funding_mode", "projected")
    events_list = []

    if funding_mode in ("fixed", "projected_plus"):
        # Get settings to determine rate_to_base for funding currency
        settings = await db.settings.find_one()
        base_currency = settings.get("base_currency", "GBP") if settings else "GBP"
        rates = settings.get("rates", {}) if settings else {}

        funding_currency = story.get("display_currency", base_currency)
        funding_amount = story.get("funding_amount", Decimal("0"))

        # Calculate rate_to_base for funding currency
        if funding_currency == base_currency:
            rate_to_base = Decimal("1")
        else:
            # Rate from settings: 1 display_currency = X base_currency
            rate_to_base = rates.get(funding_currency, Decimal("1"))

        # Convert funding amount to base currency
        base_amount = convert_to_base_currency(funding_amount, rate_to_base)

        # Create hypothetical funding event at story start
        funding_event = {
            "_id": UUID(int=0),  # Placeholder ID for synthetic event
            "date": story.get("start_date"),
            "description": f"Story funding: {story.get('name')}",
            "amount": funding_amount,
            "currency": funding_currency,
            "rate_to_base": rate_to_base,
            "account_id": story.get("default_account_id"),
            "story_id": UUID(story_id),
            "is_baseline": False,
            "is_hypothetical": True,
            "is_auto_adjustment": False,
            "created_at": story.get("created_at"),
            "base_amount": base_amount
        }
        events_list.append(funding_event)

    # Step 4: Fetch ALL events in date range (not just baseline + this story)
    # Per spec: "running_balance += ALL events (including hidden stories)"
    all_events_query = {
        "date": {"$gte": start_date, "$lte": end_date}
    }
    all_events = await db.events.find(all_events_query).to_list()

    # Convert all events to base currency and add base_amount field
    for event in all_events:
        amount = event.get("amount", Decimal("0"))
        rate_to_base = event.get("rate_to_base", Decimal("1"))
        base_amount = convert_to_base_currency(amount, rate_to_base)
        event["base_amount"] = base_amount

    # Combine funding event (if any) with all events
    all_events_with_funding = events_list + all_events

    # Step 5: Apply same-day ordering to ALL events
    all_events_with_funding.sort(
        key=lambda e: (
            e.get("date"),
            -e.get("base_amount", Decimal("0")),
            e.get("created_at")
        )
    )

    # Step 6: Calculate running balance using ALL events, but only display visible ones
    # Visible events: baseline OR this story
    # Hidden events: other stories (not baseline, not this story)
    running_balance = starting_balance
    results = []

    for event in all_events_with_funding:
        # Add event to running balance (ALL events affect balance)
        base_amount = event.get("base_amount", Decimal("0"))
        running_balance += base_amount

        # Determine if this event should be displayed
        event_story_id = event.get("story_id")
        is_baseline = event.get("is_baseline", False)
        is_this_story = event_story_id == UUID(story_id)
        is_visible = is_baseline or is_this_story

        # Only include visible events in results
        # Hidden events still affect running_balance but aren't displayed
        if is_visible:
            result_event = {**event, "running_balance": running_balance}
            results.append(result_event)
        # TODO Phase 2.4: Track hidden events for gap indicators

    return results


async def calculate_account_projection(
    account_id: str,
    start_date: date,
    end_date: date,
    db = None
) -> List[Dict]:
    """
    Calculate per-account projection.

    Algorithm:
        1. Start with account.current_balance
        2. Fetch events assigned to this account
        3. Calculate running balance

    TODO Phase 2:
    - Query events by account_id
    - Calculate running balance

    Args:
        account_id: Account UUID
        start_date: Projection start date
        end_date: Projection end date
        db: MongoDB database instance

    Returns:
        List of events with running_balance for this account

    See spec: Account-Level Projection
    """
    # STUB: Returns empty list until Phase 2
    return []


def calculate_gap_indicators(
    visible_events: List[Dict],
    all_events: List[Dict],
    display_currency: str
) -> List[Dict]:
    """
    Add gap indicator metadata for hidden events in filtered views.

    Gap indicators show:
    - Delta amount (net change from hidden events)
    - Currency converted to display_currency
    - Tappable to expand and show hidden events

    TODO Phase 2:
    - Identify gaps between visible events
    - Calculate delta from hidden events
    - Convert to display_currency
    - Add gap metadata

    Args:
        visible_events: Events shown in filtered view
        all_events: All events (including hidden)
        display_currency: Currency for gap amounts

    Returns:
        visible_events with gap indicators added

    See spec: Projection Engine > Gap Indicators
    """
    # STUB: Returns events unchanged until Phase 2
    return visible_events
