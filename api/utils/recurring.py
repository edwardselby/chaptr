"""
Recurring event generation utilities for sync protocol.

Generates event instances from recurring rules within a time window (±1 month).
Generated events are materialized as real rows and included in sync operations.
"""

from datetime import date, timedelta
from typing import Optional
from uuid import UUID
from decimal import Decimal

from dateutil.rrule import rrule, WEEKLY, MONTHLY, YEARLY
from motor.motor_asyncio import AsyncIOMotorDatabase

from api.models import RecurringRule, Event, Frequency, Settings
from api.utils.db import generate_id, utc_now


async def generate_recurring_events(
    db: AsyncIOMotorDatabase,
    user_id: Optional[UUID] = None,
    client_id: Optional[str] = None
) -> list[Event]:
    """
    Generate event instances from recurring rules within ±1 month window.

    Materializes recurring rules as actual event rows within the generation window.
    Checks for existing instances to avoid duplicates. Preserves manually edited
    instances (where updated_at != created_at).

    :param db: MongoDB database instance
    :type db: AsyncIOMotorDatabase
    :param user_id: User ID for created_by/updated_by fields
    :type user_id: Optional[UUID]
    :param client_id: Client ID for change_log tracking (None for server)
    :type client_id: Optional[str]
    :return: List of newly generated events
    :rtype: list[Event]

    **Business Rules**:
    - Window: ±1 month from today
    - Duplicate check: Query by recurring_rule_id + event_date
    - Edited instances: Preserved (updated_at != created_at means user edited)
    - Change logging: All generated events logged for sync distribution
    - Rule lifecycle: Generated events independent of rule after creation

    **See Spec**: Recurring Rules > Event Generation

    :Example:

    >>> from api.config import MongoDB
    >>> db = MongoDB.get_database()
    >>> user_id = UUID("...")
    >>> events = await generate_recurring_events(db, user_id, "client-a")
    >>> print(f"Generated {len(events)} recurring event instances")
    """
    today = date.today()
    window_start = today - timedelta(days=30)
    window_end = today + timedelta(days=30)

    generated = []

    # Fetch settings for currency conversion rates
    settings_doc = await db["settings"].find_one({})
    if not settings_doc:
        # Settings should exist before recurring events are generated
        # This should be initialized during app startup or first-time setup
        raise ValueError(
            "Settings document not found. Initialize settings before generating recurring events."
        )

    settings = Settings(**settings_doc)

    # Fetch all active recurring rules for this user
    cursor = db["recurring_rules"].find({"created_by": str(user_id)})

    async for rule_doc in cursor:
        rule = RecurringRule(**rule_doc)

        # Map frequency to dateutil rrule frequency
        freq_map = {
            Frequency.WEEKLY: WEEKLY,
            Frequency.MONTHLY: MONTHLY,
            Frequency.ANNUAL: YEARLY
        }

        # Determine effective start and end dates for generation
        gen_start = max(rule.start_date, window_start)
        gen_end = min(rule.end_date, window_end) if rule.end_date else window_end

        # Skip if rule doesn't overlap with window
        if gen_start > window_end or gen_end < window_start:
            continue

        # Generate dates using dateutil.rrule
        try:
            # For weekly rules, use byweekday; for monthly/annual, use bymonthday
            if rule.frequency == Frequency.WEEKLY:
                # day 1-7 (Monday=1, Sunday=7) -> dateutil uses Monday=0, Sunday=6
                weekday_index = rule.day - 1
                dates = rrule(
                    freq=freq_map[rule.frequency],
                    dtstart=gen_start,
                    until=gen_end,
                    byweekday=weekday_index
                )
            elif rule.frequency == Frequency.MONTHLY:
                dates = rrule(
                    freq=freq_map[rule.frequency],
                    dtstart=gen_start,
                    until=gen_end,
                    bymonthday=rule.day
                )
            elif rule.frequency == Frequency.ANNUAL:
                # Annual: use both month (from start_date) and day
                dates = rrule(
                    freq=freq_map[rule.frequency],
                    dtstart=gen_start,
                    until=gen_end,
                    bymonth=rule.start_date.month,
                    bymonthday=rule.day
                )
            else:
                continue  # Unknown frequency

        except Exception:
            # Skip invalid rule configurations (e.g., day 31 in February)
            continue

        # Generate event instances for each date
        for dt in dates:
            event_date = dt.date()

            # Check if instance already exists
            existing = await db["events"].find_one({
                "recurring_rule_id": str(rule.id),
                "event_date": event_date.isoformat()
            })

            if existing:
                # Instance already exists, skip (preserves edits)
                continue

            # Calculate rate_to_base from settings
            # If currency not in rates, default to 1.0
            rate_to_base = settings.rates.get(rule.currency, Decimal("1.0"))

            # Create new event instance
            now = utc_now()  # Single timestamp for both created_at and updated_at
            event = Event(
                id=generate_id(),
                event_date=event_date,
                description=rule.description,
                amount=rule.amount,
                currency=rule.currency,
                rate_to_base=rate_to_base,
                account_id=rule.account_id,
                story_id=None,  # Recurring events not tied to stories by default
                is_baseline=False,  # Recurring events are not baseline
                recurring_rule_id=rule.id,  # Link to parent rule
                created_at=now,
                created_by=user_id,
                updated_at=now,
                updated_by=user_id
            )

            # Insert into events collection
            await db["events"].insert_one(event.model_dump(mode="json"))

            # Log change for sync distribution
            change_entry = {
                "id": str(generate_id()),
                "entity_type": "event",
                "entity_id": str(event.id),
                "action": "create",
                "data": event.model_dump(mode="json"),
                "changed_by_user": str(user_id) if user_id else None,
                "changed_by_client": client_id,
                "changed_at": utc_now().isoformat()
            }

            # Omit None values per MongoDB best practice
            change_entry = {k: v for k, v in change_entry.items() if v is not None}

            await db["change_log"].insert_one(change_entry)

            generated.append(event)

    return generated
