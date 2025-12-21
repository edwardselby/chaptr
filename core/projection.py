"""
Projection engine for calculating balance trajectories.

Calculates running balances across different views (ALL, story, account).

Implementation: Phase 2.1 - Core projection foundation
See spec: Projection Engine
"""

from typing import List, Dict, Optional
from datetime import date
from decimal import Decimal


async def calculate_global_projection(
    start_date: date,
    end_date: date,
    view: str = "all",
    include_hypothetical: bool = False,
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

    Phase 2.1 Implementation:
    - ✅ Query all accounts, sum current_balance
    - ✅ Query events in range
    - ✅ Apply same-day ordering per spec
    - ✅ Calculate running balance
    - ✅ Filter hypothetical if view='all'

    Args:
        start_date: Projection start date
        end_date: Projection end date
        view: 'all', 'all_what_if', or story filter
        include_hypothetical: Include hypothetical funding events
        db: MongoDB database instance

    Returns:
        List of events with running_balance calculated

    See spec: Projection Engine > Global Calculation
    """
    # Step 1: Sum all account current_balance as starting point
    # Phase 2.1: Only include GBP accounts (multi-currency in Phase 2.2)
    accounts = await db.accounts.find({"is_archived": False}).to_list()
    starting_balance = sum(
        acc.get("current_balance", Decimal("0"))
        for acc in accounts
        if acc.get("currency") == "GBP"  # Phase 2.1 simplification
    )

    # Step 2: Fetch events in date range
    # For ALL view, exclude hypothetical unless include_hypothetical=True
    all_events = await db.events.find().to_list()

    # Filter events by date range and hypothetical flag
    events = [
        event for event in all_events
        if start_date <= event.get("event_date") <= end_date
        and (include_hypothetical or not event.get("is_hypothetical", False))
    ]

    # Step 3: Apply same-day ordering per spec
    # Sort by: date ASC, amount DESC (income first), created_at ASC (tie-breaker)
    events.sort(
        key=lambda e: (
            e.get("event_date"),
            -e.get("amount", Decimal("0")),  # Negative for DESC (larger positive first)
            e.get("created_at")
        )
    )

    # Step 4: Calculate running balance for each event
    running_balance = starting_balance
    results = []

    for event in events:
        # Add event amount to running balance
        running_balance += event.get("amount", Decimal("0"))

        # Create result dict with running_balance added
        result_event = {**event, "running_balance": running_balance}
        results.append(result_event)

    return results


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
        3. Fetch events (baseline + this story only)
        4. Calculate running balance (includes hidden story events)
        5. Generate gap indicators for hidden events

    TODO Phase 2:
    - Implement all three funding modes
    - Calculate gap indicators
    - Convert amounts to story.display_currency

    Args:
        story_id: Story UUID
        start_date: Projection start date
        end_date: Projection end date
        db: MongoDB database instance

    Returns:
        List of events with running_balance and gap indicators

    See spec: Projection Engine > Filtered Calculation
    """
    # STUB: Returns empty list until Phase 2
    return []


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
