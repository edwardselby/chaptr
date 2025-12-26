"""
Reconciliation system for auto-adjustments.

Keeps projections aligned with reality through automatic adjustment events.

Refactored: Display-only drift on frontend, server creates authoritative [auto] events.
See spec: Reconciliation System
"""

from typing import Dict, List, Optional
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID
from motor.motor_asyncio import AsyncIOMotorDatabase
import logging

logger = logging.getLogger(__name__)


async def trigger_reconciliation(
    trigger_reason: str,
    db: AsyncIOMotorDatabase,
    user_id: UUID,
    client_id: Optional[str] = None
) -> bool:
    """
    Trigger reconciliation for all accounts with pending_reconciliation = true.

    Creates [auto] adjustment events to align projected vs actual balances.

    :param trigger_reason: "sync" | "manual" | "scheduled"
    :param db: MongoDB database instance
    :param user_id: User UUID (from JWT)
    :param client_id: Client identifier for change log
    :return: True if reconciliation ran, False if no pending accounts
    """
    from api.repositories.accounts import AccountRepository
    from api.repositories.events import EventRepository

    account_repo = AccountRepository(db)
    event_repo = EventRepository(db)

    # 1. Find all accounts with pending_reconciliation = true
    # NOTE: Accounts don't have created_by field (shared resource in Phase 1)
    pending_accounts = await account_repo.collection.find({
        "pending_reconciliation": True
    }).to_list(length=None)

    if not pending_accounts:
        return False

    today = datetime.now(timezone.utc).date().isoformat()

    for account_doc in pending_accounts:
        account_id = UUID(account_doc["id"])

        # 2. Remove old [auto] adjustments for this account
        await remove_old_auto_adjustments(account_id, db, user_id, client_id)

        # 3. Calculate drift (actual vs projected)
        drift_event = await calculate_auto_adjustment(account_id, Decimal(str(account_doc["current_balance"])), db, user_id)

        if drift_event:
            # 4. Create [auto] adjustment event
            await event_repo.create(
                drift_event,
                current_user={"id": str(user_id)},
                client_id=client_id
            )

        # 5. Clear pending_reconciliation flag
        await account_repo.collection.update_one(
            {"id": str(account_id)},
            {
                "$set": {
                    "pending_reconciliation": False,
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }
            }
        )

    return True


async def calculate_auto_adjustment(
    account_id: UUID,
    actual_balance: Decimal,
    db: AsyncIOMotorDatabase,
    user_id: UUID
) -> Optional[Dict]:
    """
    Calculate drift and return EventCreate if adjustment needed.

    Uses projection engine to calculate projected balance up to today,
    compares with actual balance, returns event if drift > 0.01.

    :param account_id: Account UUID
    :param actual_balance: User-entered actual balance
    :param db: MongoDB database instance
    :param user_id: User UUID
    :return: EventCreate object or None
    """
    from core.projection import calculate_global_projection
    from api.repositories.accounts import AccountRepository
    from api.models import EventCreate

    account_repo = AccountRepository(db)

    # Get account details
    try:
        account = await account_repo.get(account_id)
    except Exception as e:
        return None

    # Calculate projected balance up to today using projection engine
    today = datetime.now(timezone.utc).date()
    today_str = today.isoformat()

    # Get earliest event date for this account to set projection start
    # NOTE: Events store date as "event_date" in MongoDB (date is JSON alias)
    earliest_event = await db.events.find_one(
        {"account_id": str(account_id), "created_by": str(user_id)},
        sort=[("event_date", 1)]
    )

    # Convert dates: MongoDB stores as ISO strings, projection engine needs date objects
    if earliest_event:
        start_date = datetime.fromisoformat(earliest_event["event_date"]).date()
    else:
        start_date = today

    # Calculate projection to get projected balance at today
    projection = await calculate_global_projection(
        start_date=start_date,
        end_date=today,
        view="all",
        db=db
    )

    # Find projected balance for this account in projection results
    # Projection engine returns account-specific balances per day
    projected_balance = Decimal('0')

    # Sum all events for this account up to today to get projected balance
    # NOTE: Events store date as "event_date" in MongoDB (date is JSON alias)
    account_events = await db.events.find({
        "account_id": str(account_id),
        "created_by": str(user_id),
        "event_date": {"$lte": today_str}
    }).to_list(length=None)

    # Start with initial balance (0 by convention) and add all events
    for event in account_events:
        amount = Decimal(str(event.get("amount", 0)))
        projected_balance += amount

    # Calculate drift
    drift = actual_balance - projected_balance

    # Only create adjustment if drift is significant (> 0.01)
    if abs(drift) <= Decimal('0.01'):
        return None
    # Create EventCreate object for [auto] adjustment
    return EventCreate(
        date=today_str,  # EventCreate expects ISO string for date field
        description="balance adjustment",
        amount=drift,
        account_id=account_id,
        currency=account.currency,
        rate_to_base=Decimal('1.0'),  # Will be set by EventRepository
        story_id=None,  # Auto-adjustments are not part of any story
        is_baseline=False,
        is_hypothetical=False,
        is_auto_adjustment=True  # Mark as [auto]
    )


async def remove_old_auto_adjustments(
    account_id: UUID,
    db: AsyncIOMotorDatabase,
    user_id: UUID,
    client_id: Optional[str] = None
) -> int:
    """
    Remove all existing [auto] adjustment events for this account.

    Smart cleanup: Allows users to fix root causes (e.g., assign event to correct account)
    and re-reconcile to automatically clean up stale adjustments.

    :param account_id: Account UUID
    :param db: MongoDB database instance
    :param user_id: User UUID
    :param client_id: Client identifier for change log
    :return: Number of events deleted
    """
    from api.repositories.events import EventRepository

    event_repo = EventRepository(db)

    # Find all [auto] adjustment events for this account
    auto_events = await event_repo.collection.find({
        "account_id": str(account_id),
        "created_by": str(user_id),
        "is_auto_adjustment": True
    }).to_list(length=None)

    deleted_count = 0

    for event_doc in auto_events:
        event_id = UUID(event_doc["id"])

        # Delete directly from collection (bypass repository business rule)
        # Reconciliation system is allowed to delete its own auto-adjustments
        await event_repo.collection.delete_one({"id": str(event_id)})

        # Manually log the deletion to change_log
        # Remove MongoDB-specific _id field before logging
        event_snapshot = {k: v for k, v in event_doc.items() if k != "_id"}
        await event_repo.log_change(
            "event",
            event_id,
            "delete",
            event_snapshot,  # Snapshot before deletion (without _id)
            user_id,
            client_id
        )

        deleted_count += 1

    return deleted_count


async def detect_implicit_transfer(
    account_drifts: List[Dict],
    db = None
) -> Optional[Dict]:
    """
    Detect if multiple account drifts represent an implicit transfer.

    Pattern:
        - Two accounts with equal and opposite drifts (±£320)
        - Indicates money moved between accounts without tracking

    TODO Phase 6:
    - Check if drifts sum to zero
    - Group related adjustments
    - Create paired adjustment events

    Args:
        account_drifts: List of {account_id, drift_amount}
        db: MongoDB database instance

    Returns:
        Dict with transfer details, or None if not a transfer

    See spec: Reconciliation System > Example - Multi-account drift
    """
    # STUB: Returns None until Phase 6
    return None
