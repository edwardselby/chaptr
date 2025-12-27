"""
Projection engine for calculating balance trajectories.

Calculates running balances across different views (ALL, story, account).

Implementation:
- Phase 2.1: Core projection foundation
- Phase 2.2: Multi-currency conversion

See spec: Projection Engine
"""

from typing import List, Dict, Optional
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID


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
        # Convert MongoDB Decimal128 to Python Decimal
        balance = Decimal(str(acc.get("current_balance", "0")))
        rate_to_base = Decimal(str(acc.get("rate_to_base", "1")))

        # Convert to base currency
        base_balance = convert_to_base_currency(balance, rate_to_base)
        starting_balance += base_balance

    # Step 2: Fetch events in date range
    # Phase 2.2: Filter at database level for performance (Task 255)
    # MongoDB stores dates as strings (YYYY-MM-DD format)
    query_filter = {
        "event_date": {
            "$gte": start_date.isoformat(),
            "$lte": end_date.isoformat()
        }
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
        # Convert MongoDB Decimal128 to Python Decimal
        amount = Decimal(str(event.get("amount", "0")))
        rate_to_base = Decimal(str(event.get("rate_to_base", "1")))
        base_amount = convert_to_base_currency(amount, rate_to_base)

        events_with_base.append({
            **event,
            "base_amount": base_amount
        })

    events_with_base.sort(
        key=lambda e: (
            e.get("event_date"),
            -e.get("base_amount", Decimal("0")),  # Sort by base amount DESC
            e.get("created_at")
        )
    )

    # Step 4: Calculate running balance for each event
    running_balance = starting_balance
    results = []

    for event in events_with_base:
        # Add event base_amount to running balance
        # base_amount is already a Decimal from conversion above
        base_amount = event["base_amount"]
        running_balance += base_amount

        # Create result dict with running_balance
        result_event = {**event, "running_balance": running_balance}

        # Convert MongoDB _id to JSON-serializable id field
        # TODO: Consider whitelist pattern instead of blacklist (pop)
        #       Create explicit field list to return for better robustness
        if "_id" in result_event and "id" not in result_event:
            result_event["id"] = str(result_event["_id"])
        result_event.pop("_id", None)

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

        # Query for earliest event to ensure we capture all historical data
        # Handles accounts with events spanning decades
        earliest_event = await db.events.find_one(
            sort=[("event_date", 1)]  # Ascending by date
        )

        if earliest_event:
            early_date = earliest_event["event_date"]
        else:
            # No events exist, use story start date
            early_date = story.get("start_date")

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
        # Unknown funding mode - fail fast with clear error
        raise ValueError(
            f"Unknown funding_mode: '{funding_mode}'. "
            f"Expected 'projected', 'fixed', or 'projected_plus'"
        )


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
           - projected: calc balance on story.start_date (no funding event)
           - fixed: starting_balance = 0, funding event adds amount
           - projected_plus: starting_balance = projected, funding event adds amount
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
    # Per spec lines 163-182: Funding adjustments create a funding event
    funding_mode = story.get("funding_mode", "projected")
    events_list = []

    if funding_mode in ("fixed", "projected_plus"):
        # Get settings to determine rate_to_base for funding currency
        settings = await db.settings.find_one()
        if not settings:
            raise ValueError(
                "Settings document not found. Database may not be initialized. "
                "Run setup to create settings with base_currency and rates."
            )

        base_currency = settings.get("base_currency", "GBP")
        rates = settings.get("rates", {})

        funding_currency = story.get("display_currency", base_currency)
        # Convert MongoDB Decimal128 to Python Decimal
        funding_amount = Decimal(str(story.get("funding_amount", "0")))

        # Calculate rate_to_base for funding currency
        if funding_currency == base_currency:
            rate_to_base = Decimal("1")
        else:
            # Rate from settings: 1 display_currency = X base_currency
            # Convert rate from MongoDB Decimal128 to Python Decimal
            rate_to_base = Decimal(str(rates.get(funding_currency, "1")))

        # Convert funding amount to base currency
        base_amount = convert_to_base_currency(funding_amount, rate_to_base)

        # Create hypothetical funding event at story start
        # Use deterministic UUID based on story_id for consistent identification
        from uuid import uuid5, NAMESPACE_OID
        funding_event_id = uuid5(NAMESPACE_OID, f"funding-{story_id}")

        funding_event = {
            "_id": funding_event_id,
            "id": str(funding_event_id),
            "event_date": story.get("start_date"),
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
    # MongoDB stores dates as strings (YYYY-MM-DD format)
    all_events_query = {
        "event_date": {
            "$gte": start_date.isoformat(),
            "$lte": end_date.isoformat()
        }
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
            e.get("event_date"),
            -e.get("base_amount", Decimal("0")),
            e.get("created_at")
        )
    )

    # Convert MongoDB _id to JSON-serializable id field
    # This prevents ObjectId from appearing in results and provides consistent id field
    # TODO: Consider whitelist pattern instead of blacklist (pop)
    #       Create explicit field list to return for better robustness
    #       (prevents future MongoDB fields from leaking if non-serializable)
    for event in all_events_with_funding:
        if "_id" in event and "id" not in event:
            event["id"] = str(event["_id"])
        event.pop("_id", None)

    # Step 6: Calculate running balance using ALL events, but only display visible ones
    # Visible events: baseline OR this story
    # Hidden events: other stories (not baseline, not this story)
    running_balance = starting_balance
    results = []
    visible_event_ids = set()  # Track using UUID 'id' field, not ObjectId '_id'

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
            # Track visible event IDs using UUID 'id' field
            visible_event_ids.add(event.get("id"))

    # Step 7: Add gap indicators (Phase 2.4 - Tasks 2, 3, 4)
    # Get settings for currency conversion
    settings = await db.settings.find_one()
    if not settings:
        raise ValueError(
            "Settings document not found. Database may not be initialized. "
            "Run setup to create settings with base_currency and rates."
        )

    base_currency = settings.get("base_currency", "GBP")
    rates = settings.get("rates", {})
    story_display_currency = story.get("display_currency", base_currency)

    # Detect gaps between visible events (Task 2)
    gaps = detect_gaps_between_visible_events(
        all_events_sorted=all_events_with_funding,
        visible_event_ids=visible_event_ids
    )

    # Step 8: Attach gap metadata to visible events
    # Build index of visible events by ID for fast lookup (using UUID 'id' field)
    visible_events_by_id = {e["id"]: e for e in results}

    for gap in gaps:
        after_event_id = gap["after_event_id"]
        if after_event_id in visible_events_by_id:
            # Convert delta from base currency to display currency (Task 4)
            delta_display = convert_from_base_currency(
                gap["delta_base"],
                story_display_currency,
                base_currency,
                rates
            )

            # Attach gap indicator metadata to visible event
            visible_events_by_id[after_event_id]["gap_indicator"] = {
                "type": "gap",
                "delta_base": gap["delta_base"],
                "delta_display": delta_display,
                "display_currency": story_display_currency,
                "hidden_event_count": gap["hidden_event_count"],
                "date_range": {
                    "start": gap["start_date"],
                    "end": gap["end_date"]
                },
                # Include hidden events for frontend expansion
                "hidden_events": gap["hidden_events"]
            }

    return results


async def calculate_account_projection(
    account_id: str,
    start_date: date,
    end_date: date,
    db = None
) -> List[Dict]:
    """
    Calculate per-account projection.

    Algorithm (Phase 2.1 Implementation):
        1. Query account by account_id
        2. Get current_balance and rate_to_base
        3. Convert balance to base currency (starting point)
        4. Query events WHERE account_id == target AND date in range
        5. Add base_amount to each event (amount × rate_to_base)
        6. Sort by: date ASC, base_amount DESC, created_at ASC
        7. Calculate running_balance accumulation
        8. Return events with running_balance

    Args:
        account_id: Account UUID
        start_date: Projection start date
        end_date: Projection end date
        db: MongoDB database instance

    Returns:
        List of events with running_balance for this account

    See spec: Account-Level Projection (lines 281-323)
    """
    from uuid import UUID

    # Step 1: Get account
    account = await db.accounts.find_one({"_id": UUID(account_id)})
    if not account:
        return []

    # Step 2: Starting balance (convert to base currency)
    # Convert MongoDB Decimal128 to Python Decimal
    starting_balance = convert_to_base_currency(
        Decimal(str(account.get("current_balance", "0"))),
        Decimal(str(account.get("rate_to_base", "1")))
    )

    # Step 3: Query events assigned to this account
    # MongoDB stores dates as strings (YYYY-MM-DD format)
    events = await db.events.find({
        "account_id": UUID(account_id),
        "event_date": {
            "$gte": start_date.isoformat(),
            "$lte": end_date.isoformat()
        }
    }).to_list()

    # Step 4: Convert to base currency and add base_amount field
    events_with_base = []
    for event in events:
        # Convert MongoDB Decimal128 to Python Decimal
        amount = Decimal(str(event.get("amount", "0")))
        rate_to_base = Decimal(str(event.get("rate_to_base", "1")))
        base_amount = convert_to_base_currency(amount, rate_to_base)

        events_with_base.append({
            **event,
            "base_amount": base_amount
        })

    # Step 5: Apply same-day ordering per spec
    # Sort by: date ASC, base_amount DESC (income first), created_at ASC (tie-breaker)
    events_with_base.sort(
        key=lambda e: (
            e.get("event_date"),
            -e.get("base_amount", Decimal("0")),  # Negative for DESC
            e.get("created_at")
        )
    )

    # Step 6: Calculate running balance for each event
    running_balance = starting_balance
    results = []

    for event in events_with_base:
        # Add event base_amount to running balance
        # base_amount is already a Decimal from conversion above
        base_amount = event["base_amount"]
        running_balance += base_amount

        # Create result dict with running_balance
        result_event = {**event, "running_balance": running_balance}
        # Convert MongoDB _id to JSON-serializable id field
        # TODO: Consider whitelist pattern instead of blacklist (pop)
        #       Create explicit field list to return for better robustness
        if "_id" in result_event and "id" not in result_event:
            result_event["id"] = str(result_event["_id"])
        result_event.pop("_id", None)
        results.append(result_event)

    return results


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


def detect_gaps_between_visible_events(
    all_events_sorted: List[Dict],
    visible_event_ids: set
) -> List[Dict]:
    """
    Identify gaps where hidden events affect running balance.

    A gap exists when consecutive visible events have hidden events between them
    that caused a net balance change.

    Algorithm:
    1. Iterate through ALL events (sorted by date, amount DESC, created_at)
    2. Track last visible event and accumulate hidden events
    3. When hitting next visible event, calculate delta from hidden events
    4. Create gap metadata if delta != 0

    Args:
        all_events_sorted: ALL events sorted by date, amount DESC, created_at
        visible_event_ids: Set of event IDs that are visible (baseline OR this story)

    Returns:
        List of gap metadata dicts with structure:
        {
            "type": "gap_indicator",
            "after_event_id": UUID,           # Event preceding the gap
            "before_event_id": UUID or None,  # Event following the gap (None if trailing)
            "hidden_event_count": int,        # Number of hidden events in gap
            "hidden_events": List[Dict],      # Full event details for expansion
            "delta_base": Decimal,            # Net change in base currency
            "start_date": date,               # Date of first hidden event
            "end_date": date                  # Date of last hidden event
        }

    Example:
        >>> visible_ids = {car_rental_id, gifts_id}
        >>> all_events = [
        ...     {"_id": car_rental_id, "event_date": date(2024, 12, 20), "base_amount": Decimal("-320")},
        ...     {"_id": parts_id, "event_date": date(2024, 12, 22), "base_amount": Decimal("-180")},
        ...     {"_id": gifts_id, "event_date": date(2024, 12, 25), "base_amount": Decimal("-150")}
        ... ]
        >>> gaps = detect_gaps_between_visible_events(all_events, visible_ids)
        >>> len(gaps)
        1
        >>> gaps[0]["delta_base"]
        Decimal('-180.00')

    See spec: Projection Engine > Gap Indicators (lines 490-510)
    """
    gaps = []

    # Track state as we iterate through ALL events
    last_visible_event = None
    hidden_events_accumulator = []

    for event in all_events_sorted:
        # Use UUID 'id' field instead of ObjectId '_id' (which was removed)
        event_id = event.get("id")
        is_visible = event_id in visible_event_ids

        if is_visible:
            # We've hit a visible event
            # Check if we accumulated hidden events since last visible event
            if last_visible_event is not None and hidden_events_accumulator:
                # Calculate net delta from hidden events (in base currency)
                delta_base = sum(e["base_amount"] for e in hidden_events_accumulator)

                # Only create gap if delta != 0 (meaningful change)
                if delta_base != Decimal("0"):
                    # Record gap metadata
                    gaps.append({
                        "type": "gap_indicator",
                        "after_event_id": last_visible_event.get("id"),
                        "before_event_id": event_id,
                        "hidden_event_count": len(hidden_events_accumulator),
                        "hidden_events": list(hidden_events_accumulator),
                        "delta_base": delta_base,
                        "start_date": hidden_events_accumulator[0]["event_date"],
                        "end_date": hidden_events_accumulator[-1]["event_date"]
                    })

                # Reset accumulator
                hidden_events_accumulator = []

            # Update last visible event
            last_visible_event = event
        else:
            # Hidden event - accumulate it
            hidden_events_accumulator.append(event)

    # Handle trailing hidden events after last visible event
    if last_visible_event is not None and hidden_events_accumulator:
        delta_base = sum(e["base_amount"] for e in hidden_events_accumulator)
        if delta_base != Decimal("0"):
            gaps.append({
                "type": "gap_indicator",
                "after_event_id": last_visible_event.get("id"),
                "before_event_id": None,  # No next visible event
                "hidden_event_count": len(hidden_events_accumulator),
                "hidden_events": list(hidden_events_accumulator),
                "delta_base": delta_base,
                "start_date": hidden_events_accumulator[0]["event_date"],
                "end_date": hidden_events_accumulator[-1]["event_date"]
            })

    return gaps


# Warning Detection Functions (Phase 2.5)


def detect_global_negative_warnings(projection_result: List[Dict]) -> List[Dict]:
    """
    Scan projection for negative running_balance.

    Task 9: Detect when global balance goes negative.

    Args:
        projection_result: List of events with running_balance (in base currency)

    Returns:
        List of warning dicts for negative balances

    Note:
        running_balance is always in base currency (from settings.base_currency).
        Warning amounts reflect base currency values.

    See spec: Warning System (lines 620-643)
    """
    warnings = []

    for event in projection_result:
        balance = event.get("running_balance", Decimal("0"))
        if balance < 0:
            # Warning objects use "date" field (distinct from event.event_date)
            # This is the warning's date field, populated FROM event's event_date
            warnings.append({
                "type": "negative_balance",
                "severity": "critical",
                "date": event.get("event_date"),
                "amount": balance,
                "threshold": Decimal("0"),
                "account_id": None,
                "account_name": None,
                "story_id": None,
                "story_name": None,
                "message": f"Global balance goes negative: {balance} on {event['event_date']}"
            })

    return warnings


def detect_account_negative_warnings(
    account_id: str,
    account_name: str,
    projection_result: List[Dict]
) -> List[Dict]:
    """
    Scan account projection for negative running_balance.

    Task 10: Detect when per-account balance goes negative.

    Args:
        account_id: Account UUID string
        account_name: Account name for display
        projection_result: List of events with running_balance

    Returns:
        List of warning dicts for account negative balances

    See spec: Warning System (lines 620-643)
    """
    from uuid import UUID

    warnings = []

    for event in projection_result:
        balance = event.get("running_balance", Decimal("0"))
        if balance < 0:
            warnings.append({
                "type": "account_negative",
                "severity": "critical",
                "date": event.get("event_date"),
                "amount": balance,
                "threshold": Decimal("0"),
                "account_id": UUID(account_id),
                "account_name": account_name,
                "story_id": None,
                "story_name": None,
                "message": f"{account_name} will go negative: {balance} on {event['event_date']}"
            })

    return warnings


def detect_story_goal_warnings(story: Dict, projection_result: List[Dict]) -> List[Dict]:
    """
    Check if story violates goal (spend_up_to or end_with_at_least).

    Tasks 11 & 12:
    - Task 11: Detect story exceeds spend_up_to goal
    - Task 12: Detect story misses end_with_at_least goal

    Args:
        story: Story document with goal_type and goal_amount
        projection_result: List of events with running_balance

    Returns:
        List of warning dicts for goal violations

    See spec: Warning System (lines 620-643)
    """
    warnings = []

    goal_type = story.get("goal_type")
    if not goal_type or goal_type == "none":
        return []

    goal_amount = story.get("goal_amount", Decimal("0"))

    # Task 11: spend_up_to - check cumulative spend
    if goal_type == "spend_up_to":
        # Calculate total spend (negative amounts only, exclude baseline)
        total_spend = Decimal("0")
        for event in projection_result:
            # Skip baseline events
            if event.get("is_baseline", False):
                continue
            # Only count expenses (negative amounts)
            amount = event.get("amount", Decimal("0"))
            if amount < 0:
                total_spend += abs(amount)

        # Check if exceeded goal
        if total_spend > goal_amount:
            overspent = total_spend - goal_amount
            currency = story.get("display_currency", "GBP")
            warnings.append({
                "type": "goal_exceeded",
                "severity": "warning",
                "date": story.get("end_date") or (projection_result[-1]["event_date"] if projection_result else None),
                "amount": total_spend,
                "threshold": goal_amount,
                "account_id": None,
                "account_name": None,
                "story_id": story.get("_id"),
                "story_name": story.get("name"),
                "message": f"{story['name']}: {currency} {overspent:.2f} over budget (spent {total_spend:.2f}, goal {goal_amount:.2f})"
            })

    # Task 12: end_with_at_least - check final balance
    elif goal_type == "end_with_at_least":
        if projection_result:
            final_balance = projection_result[-1].get("running_balance", Decimal("0"))
            if final_balance < goal_amount:
                shortfall = goal_amount - final_balance
                currency = story.get("display_currency", "GBP")
                warnings.append({
                    "type": "goal_missed",
                    "severity": "warning",
                    "date": story.get("end_date") or projection_result[-1]["event_date"],
                    "amount": final_balance,
                    "threshold": goal_amount,
                    "account_id": None,
                    "account_name": None,
                    "story_id": story.get("_id"),
                    "story_name": story.get("name"),
                    "message": f"{story['name']}: {currency} {shortfall:.2f} short of goal (projected {final_balance:.2f}, goal {goal_amount:.2f})"
                })

    return warnings
