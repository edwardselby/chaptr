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
    client_id: Optional[str] = None,
    tenant_id: Optional[UUID] = None
) -> List[UUID]:
    """
    Trigger reconciliation for all accounts with pending_reconciliation = true.

    Creates [auto] adjustment events to align projected vs actual balances.

    :param trigger_reason: "sync" | "manual" | "scheduled"
    :param db: MongoDB database instance
    :param user_id: User UUID (from JWT)
    :param client_id: Client identifier for change log
    :param tenant_id: Tenant UUID for multi-tenancy isolation
    :return: List of account IDs that were reconciled (empty list if none)
    """
    from api.repositories.accounts import AccountRepository
    from api.repositories.events import EventRepository
    from api.models import AccountUpdate

    account_repo = AccountRepository(db)
    event_repo = EventRepository(db)

    # 1. Find all accounts with pending_reconciliation = true
    # Multi-tenancy: Filter by tenant_id if provided
    account_query = {"pending_reconciliation": True}
    if tenant_id:
        account_query["tenant_id"] = str(tenant_id)
    pending_accounts = await account_repo.collection.find(account_query).to_list(length=None)

    if not pending_accounts:
        return []

    reconciled_account_ids: List[UUID] = []
    today = datetime.now(timezone.utc).date().isoformat()

    # Build current_user dict with tenant_id for multi-tenancy
    current_user = {"id": str(user_id)}
    if tenant_id:
        current_user["tenant_id"] = str(tenant_id)

    for account_doc in pending_accounts:
        account_id = UUID(account_doc["id"])

        # 2. Remove only TODAY's auto-adjustments for this account (consolidation)
        # Historical adjustments (from past dates) are preserved
        await remove_todays_auto_adjustments(account_id, db, user_id, client_id, tenant_id)

        # 3. Calculate incremental drift (includes historical adjustments, excludes today's)
        drift_event = await calculate_auto_adjustment(account_id, Decimal(str(account_doc["current_balance"])), db, user_id, tenant_id)

        if drift_event:
            # 4. Create [auto] adjustment event dated TODAY (replaces any previous today adjustment)
            await event_repo.create(
                drift_event,
                current_user=current_user,
                client_id=client_id,
                tenant_id=tenant_id
            )

        # 5. Clear pending_reconciliation flag using repository update
        # This properly logs to change_log so other clients see the change
        await account_repo.update(
            account_id,
            AccountUpdate(pending_reconciliation=False),
            current_user=current_user,
            client_id=client_id
        )

        reconciled_account_ids.append(account_id)

    return reconciled_account_ids


async def calculate_auto_adjustment(
    account_id: UUID,
    actual_balance: Decimal,
    db: AsyncIOMotorDatabase,
    user_id: UUID,
    tenant_id: Optional[UUID] = None
) -> Optional[Dict]:
    """
    Calculate INCREMENTAL drift and return EventCreate if adjustment needed.

    Uses event sourcing to calculate projected balance INCLUDING existing
    auto-adjustments, then compares with actual balance. Returns adjustment
    event only for NEW drift since last reconciliation.

    This ensures adjustments are immutable and incremental, preserving:
    - Historical balance accuracy
    - Planning feedback (adjustment frequency)
    - Event sourcing principles

    :param account_id: Account UUID
    :param actual_balance: User-entered actual balance
    :param db: MongoDB database instance
    :param user_id: User UUID
    :param tenant_id: Tenant UUID for multi-tenancy isolation
    :return: EventCreate object or None
    """
    from api.repositories.accounts import AccountRepository
    from api.models import EventCreate

    account_repo = AccountRepository(db)

    # Get account details
    try:
        account = await account_repo.get(account_id)
    except Exception as e:
        return None

    # Calculate projected balance using event sourcing approach:
    # Replay all events from £0 to get projected balance at today
    # (First events for each account are typically opening balance events)
    today = datetime.now(timezone.utc).date()
    today_str = today.isoformat()

    # Query all REAL events INCLUDING AUTO-ADJUSTMENTS up to today
    # Auto-adjustments ARE real events - they're part of the event history
    # Exclude hypothetical events: "Reality as anchor - hypotheticals are explicit opt-ins" (spec)
    # Events use "event_date" field consistently everywhere
    # Multi-tenancy: Filter by tenant_id (not created_by - supports multi-user tenants)
    events_query = {
        "account_id": str(account_id),
        "event_date": {"$lte": today_str},
        "is_hypothetical": False  # Includes auto-adjustments (they're real)
    }
    if tenant_id:
        events_query["tenant_id"] = str(tenant_id)
    account_events = await db.events.find(events_query).to_list(length=None)

    # Event sourcing: Sum all events INCLUDING existing adjustments from £0
    # This makes drift calculation incremental (only NEW drift since last adjustment)
    projected_balance = Decimal('0')
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
        event_date=today_str,  # EventCreate expects ISO string for event_date field
        description="balance adjustment",
        amount=drift,
        account_id=account_id,
        currency=account.currency,
        rate_to_base=Decimal('1.0'),  # Will be set by EventRepository
        story_id=None,  # Auto-adjustments are not part of any story
        is_baseline=True,  # Auto-adjustments are baseline events (part of reality)
        is_hypothetical=False,
        is_auto_adjustment=True  # Mark as [auto]
    )


async def remove_old_auto_adjustments(
    account_id: UUID,
    db: AsyncIOMotorDatabase,
    user_id: UUID,
    client_id: Optional[str] = None,
    tenant_id: Optional[UUID] = None
) -> int:
    """
    Remove all existing [auto] adjustment events for this account.

    Smart cleanup: Allows users to fix root causes (e.g., assign event to correct account)
    and re-reconcile to automatically clean up stale adjustments.

    :param account_id: Account UUID
    :param db: MongoDB database instance
    :param user_id: User UUID
    :param client_id: Client identifier for change log
    :param tenant_id: Tenant UUID for multi-tenancy isolation
    :return: Number of events deleted
    """
    from api.repositories.events import EventRepository

    event_repo = EventRepository(db)

    # Find all [auto] adjustment events for this account
    # Multi-tenancy: Filter by tenant_id (not created_by - supports multi-user tenants)
    auto_query = {
        "account_id": str(account_id),
        "is_auto_adjustment": True
    }
    if tenant_id:
        auto_query["tenant_id"] = str(tenant_id)
    auto_events = await event_repo.collection.find(auto_query).to_list(length=None)

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
            client_id,
            tenant_id  # Multi-tenancy: Include tenant_id in change_log
        )

        deleted_count += 1

    return deleted_count


async def remove_todays_auto_adjustments(
    account_id: UUID,
    db: AsyncIOMotorDatabase,
    user_id: UUID,
    client_id: Optional[str] = None,
    tenant_id: Optional[UUID] = None
) -> int:
    """
    Remove auto-adjustments dated TODAY for this account (same-day consolidation).

    This ensures only ONE adjustment per date. If reconciling multiple times on the same day,
    the old TODAY adjustment is replaced with a new one. Historical adjustments (from past
    dates) are never deleted - they remain immutable.

    :param account_id: Account UUID
    :param db: MongoDB database instance
    :param user_id: User UUID
    :param client_id: Client identifier for change log
    :param tenant_id: Tenant UUID for multi-tenancy isolation
    :return: Number of events deleted
    """
    from api.repositories.events import EventRepository

    event_repo = EventRepository(db)
    today = datetime.now(timezone.utc).date().isoformat()

    # Find auto-adjustments for this account dated TODAY only
    auto_query = {
        "account_id": str(account_id),
        "is_auto_adjustment": True,
        "event_date": today  # Only TODAY's adjustments
    }
    if tenant_id:
        auto_query["tenant_id"] = str(tenant_id)

    todays_adjustments = await event_repo.collection.find(auto_query).to_list(length=None)

    deleted_count = 0

    for event_doc in todays_adjustments:
        event_id = UUID(event_doc["id"])

        # Delete from collection
        await event_repo.collection.delete_one({"id": str(event_id)})

        # Log deletion to change_log
        event_snapshot = {k: v for k, v in event_doc.items() if k != "_id"}
        await event_repo.log_change(
            "event",
            event_id,
            "delete",
            event_snapshot,
            user_id,
            client_id,
            tenant_id
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
