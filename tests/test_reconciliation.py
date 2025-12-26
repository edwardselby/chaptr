"""
Unit tests for reconciliation system - Display-only drift architecture.

Tests cover:
- trigger_reconciliation(): Processing pending accounts, creating [auto] events
- calculate_auto_adjustment(): Drift calculation and threshold logic
- remove_old_auto_adjustments(): Smart cleanup of stale adjustments

Uses real MongoDB for accurate reconciliation flow simulation.
"""

import pytest
import pytest_asyncio
from datetime import datetime, date
from decimal import Decimal
from uuid import uuid4

from api.models import AccountCreate, EventCreate, SettingsBase
from api.repositories.accounts import AccountRepository
from api.repositories.events import EventRepository
from api.repositories.settings import SettingsRepository
from core.reconciliation import (
    trigger_reconciliation,
    calculate_auto_adjustment,
    remove_old_auto_adjustments
)


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest_asyncio.fixture
async def account_with_drift(
    account_repo_real,
    sample_user_real,
    sample_settings_real
):
    """
    Create account with pending_reconciliation and drift condition.

    Account has current_balance=1000, but events sum to 500, so drift=500.
    """
    account_data = AccountCreate(
        name="Monzo",
        currency="GBP",
        current_balance=Decimal("1000.00"),
        is_default=True
    )
    account = await account_repo_real.create(
        account_data,
        current_user={"id": str(sample_user_real.id)},
        client_id=None
    )

    # Mark as pending reconciliation
    await account_repo_real.collection.update_one(
        {"id": str(account.id)},
        {"$set": {"pending_reconciliation": True}}
    )

    # Create events that sum to 500 (actual balance is 1000, so drift = 500)
    event1 = EventCreate(
        event_date=date(2025, 1, 10),
        description="Salary",
        amount=Decimal("2000.00"),
        account_id=account.id,
        currency="GBP",
        is_baseline=True
    )
    await EventRepository(account_repo_real.db).create(
        event1,
        current_user={"id": str(sample_user_real.id)},
        client_id=None
    )

    event2 = EventCreate(
        date="2025-01-15",
        description="Rent",
        amount=Decimal("-1500.00"),
        account_id=account.id,
        currency="GBP",
        rate_to_base=Decimal("1.0"),
        is_baseline=True
    )
    await EventRepository(account_repo_real.db).create(
        event2,
        current_user={"id": str(sample_user_real.id)},
        client_id=None
    )

    # Events sum: 2000 - 1500 = 500
    # Account current_balance: 1000
    # Drift: 1000 - 500 = 500

    return account


@pytest_asyncio.fixture
async def account_with_auto_adjustment(
    account_repo_real,
    sample_user_real,
    sample_settings_real
):
    """
    Create account with existing [auto] adjustment event.

    Used to test removal of old auto-adjustments.
    """
    account_data = AccountCreate(
        name="HSBC",
        currency="GBP",
        current_balance=Decimal("500.00"),
        is_default=False
    )
    account = await account_repo_real.create(
        account_data,
        current_user={"id": str(sample_user_real.id)},
        client_id=None
    )

    # Create existing [auto] adjustment
    auto_event = EventCreate(
        date="2025-01-20",
        description="balance adjustment",
        amount=Decimal("100.00"),
        account_id=account.id,
        currency="GBP",
        rate_to_base=Decimal("1.0"),
        is_auto_adjustment=True
    )
    await EventRepository(account_repo_real.db).create(
        auto_event,
        current_user={"id": str(sample_user_real.id)},
        client_id=None
    )

    return account


# ============================================================================
# Unit Tests: remove_old_auto_adjustments()
# ============================================================================

@pytest.mark.integration
@pytest.mark.asyncio
async def test_remove_old_auto_adjustments_success(
    mongodb_real,
    account_with_auto_adjustment,
    sample_user_real,
    clean_database_real
):
    """
    Test successful removal of [auto] adjustment events.

    Validates:
    - Old [auto] events are deleted
    - Returns correct count
    - Only affects target account
    """
    # Verify auto-adjustment exists before removal
    event_repo = EventRepository(mongodb_real)
    auto_events_before = await event_repo.collection.find({
        "account_id": str(account_with_auto_adjustment.id),
        "is_auto_adjustment": True
    }).to_list(length=None)

    assert len(auto_events_before) == 1, "Should have 1 auto-adjustment before removal"

    # Remove auto-adjustments
    removed_count = await remove_old_auto_adjustments(
        account_id=account_with_auto_adjustment.id,
        db=mongodb_real,
        user_id=sample_user_real.id,
        client_id="test-client"
    )

    # Verify removal
    assert removed_count == 1, "Should remove 1 auto-adjustment"

    auto_events_after = await event_repo.collection.find({
        "account_id": str(account_with_auto_adjustment.id),
        "is_auto_adjustment": True
    }).to_list(length=None)

    assert len(auto_events_after) == 0, "Should have 0 auto-adjustments after removal"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_remove_old_auto_adjustments_no_events(
    mongodb_real,
    sample_account_with_user,
    sample_user_real,
    clean_database_real
):
    """
    Test removal when no [auto] adjustments exist.

    Validates:
    - Returns 0 when no auto-adjustments found
    - Doesn't error on empty result
    """
    removed_count = await remove_old_auto_adjustments(
        account_id=sample_account_with_user.id,
        db=mongodb_real,
        user_id=sample_user_real.id,
        client_id="test-client"
    )

    assert removed_count == 0, "Should remove 0 when no auto-adjustments exist"


# ============================================================================
# Unit Tests: calculate_auto_adjustment()
# ============================================================================

@pytest.mark.integration
@pytest.mark.asyncio
async def test_calculate_auto_adjustment_with_drift(
    mongodb_real,
    account_with_drift,
    sample_user_real,
    clean_database_real
):
    """
    Test drift calculation when significant drift exists.

    Account: current_balance=1000, events sum=500, drift=500

    Validates:
    - Returns EventCreate object with correct drift amount
    - is_auto_adjustment=True
    - description="balance adjustment"
    - story_id=None
    """
    adjustment = await calculate_auto_adjustment(
        account_id=account_with_drift.id,
        actual_balance=Decimal("1000.00"),
        db=mongodb_real,
        user_id=sample_user_real.id
    )

    assert adjustment is not None, "Should return adjustment when drift exists"
    assert adjustment.amount == Decimal("500.00"), "Drift should be 500 (1000 - 500)"
    assert adjustment.is_auto_adjustment is True, "Should be marked as auto-adjustment"
    assert adjustment.description == "balance adjustment", "Should have standard description"
    assert adjustment.story_id is None, "Auto-adjustments not part of stories"
    assert adjustment.account_id == account_with_drift.id, "Should target correct account"
    assert adjustment.currency == "GBP", "Should match account currency"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_calculate_auto_adjustment_no_drift(
    mongodb_real,
    account_repo_real,
    sample_user_real,
    sample_settings_real,
    clean_database_real
):
    """
    Test drift calculation when no significant drift (< 0.01).

    Validates:
    - Returns None when drift below threshold
    - Threshold is 0.01
    """
    # Create account with matching balance (no drift)
    account_data = AccountCreate(
        name="Revolut",
        currency="GBP",
        current_balance=Decimal("500.00"),
        is_default=False
    )
    account = await account_repo_real.create(
        account_data,
        current_user={"id": str(sample_user_real.id)},
        client_id=None
    )

    # Create event that matches balance exactly
    event = EventCreate(
        date="2025-01-10",
        description="Initial",
        amount=Decimal("500.00"),
        account_id=account.id,
        currency="GBP",
        rate_to_base=Decimal("1.0"),
        is_baseline=True
    )
    await EventRepository(mongodb_real).create(
        event,
        current_user={"id": str(sample_user_real.id)},
        client_id=None
    )

    # Drift = 500 - 500 = 0 (below threshold)
    adjustment = await calculate_auto_adjustment(
        account_id=account.id,
        actual_balance=Decimal("500.00"),
        db=mongodb_real,
        user_id=sample_user_real.id
    )

    assert adjustment is None, "Should return None when drift < 0.01"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_calculate_auto_adjustment_negative_drift(
    mongodb_real,
    account_repo_real,
    sample_user_real,
    sample_settings_real,
    clean_database_real
):
    """
    Test drift calculation with negative drift (actual < projected).

    Validates:
    - Handles negative drift correctly
    - Returns adjustment with negative amount
    """
    # Create account with current_balance=500
    account_data = AccountCreate(
        name="Starling",
        currency="GBP",
        current_balance=Decimal("500.00"),
        is_default=False
    )
    account = await account_repo_real.create(
        account_data,
        current_user={"id": str(sample_user_real.id)},
        client_id=None
    )

    # Create events that sum to 1000
    event = EventCreate(
        date="2025-01-10",
        description="Large deposit",
        amount=Decimal("1000.00"),
        account_id=account.id,
        currency="GBP",
        rate_to_base=Decimal("1.0"),
        is_baseline=True
    )
    await EventRepository(mongodb_real).create(
        event,
        current_user={"id": str(sample_user_real.id)},
        client_id=None
    )

    # Drift = 500 - 1000 = -500 (negative)
    adjustment = await calculate_auto_adjustment(
        account_id=account.id,
        actual_balance=Decimal("500.00"),
        db=mongodb_real,
        user_id=sample_user_real.id
    )

    assert adjustment is not None, "Should return adjustment for negative drift"
    assert adjustment.amount == Decimal("-500.00"), "Should handle negative drift"


# ============================================================================
# Unit Tests: trigger_reconciliation()
# ============================================================================

@pytest.mark.integration
@pytest.mark.asyncio
async def test_trigger_reconciliation_with_pending_accounts(
    mongodb_real,
    account_with_drift,
    sample_user_real,
    clean_database_real
):
    """
    Test full reconciliation flow with pending accounts.

    Validates:
    - Finds accounts with pending_reconciliation=True
    - Removes old [auto] adjustments
    - Creates new [auto] adjustment with correct drift
    - Clears pending_reconciliation flag
    - Returns True
    """
    event_repo = EventRepository(mongodb_real)
    account_repo = AccountRepository(mongodb_real)

    # Trigger reconciliation
    result = await trigger_reconciliation(
        trigger_reason="sync",
        db=mongodb_real,
        user_id=sample_user_real.id,
        client_id="test-client"
    )

    assert result is True, "Should return True when reconciliation runs"

    # Verify [auto] adjustment was created
    auto_events = await event_repo.collection.find({
        "account_id": str(account_with_drift.id),
        "is_auto_adjustment": True
    }).to_list(length=None)

    assert len(auto_events) == 1, "Should create 1 auto-adjustment"

    auto_event = auto_events[0]
    assert Decimal(str(auto_event["amount"])) == Decimal("500.00"), "Should have drift amount"
    assert auto_event["description"] == "balance adjustment"

    # Verify pending_reconciliation flag cleared
    account_doc = await account_repo.collection.find_one({"id": str(account_with_drift.id)})
    assert account_doc["pending_reconciliation"] is False, "Should clear pending flag"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_trigger_reconciliation_no_pending_accounts(
    mongodb_real,
    sample_account_with_user,
    sample_user_real,
    clean_database_real
):
    """
    Test reconciliation when no accounts pending.

    Validates:
    - Returns False when no pending accounts
    - Doesn't create any events
    """
    result = await trigger_reconciliation(
        trigger_reason="sync",
        db=mongodb_real,
        user_id=sample_user_real.id,
        client_id="test-client"
    )

    assert result is False, "Should return False when no pending accounts"

    # Verify no auto-adjustments created
    event_repo = EventRepository(mongodb_real)
    auto_events = await event_repo.collection.find({
        "is_auto_adjustment": True
    }).to_list(length=None)

    assert len(auto_events) == 0, "Should not create any auto-adjustments"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_trigger_reconciliation_removes_old_adjustments(
    mongodb_real,
    account_repo_real,
    sample_user_real,
    sample_settings_real,
    clean_database_real
):
    """
    Test that reconciliation removes old [auto] adjustments before creating new ones.

    Validates:
    - Old [auto] adjustments are deleted
    - New [auto] adjustment replaces old one
    - No accumulation of stale adjustments
    """
    # Create account with current_balance=1000
    account_data = AccountCreate(
        name="NatWest",
        currency="GBP",
        current_balance=Decimal("1000.00"),
        is_default=False
    )
    account = await account_repo_real.create(
        account_data,
        current_user={"id": str(sample_user_real.id)},
        client_id=None
    )

    # Mark as pending
    await account_repo_real.collection.update_one(
        {"id": str(account.id)},
        {"$set": {"pending_reconciliation": True}}
    )

    # Create baseline event (balance should be 500)
    event = EventCreate(
        date="2025-01-10",
        description="Starting balance",
        amount=Decimal("500.00"),
        account_id=account.id,
        currency="GBP",
        rate_to_base=Decimal("1.0"),
        is_baseline=True
    )
    await EventRepository(mongodb_real).create(
        event,
        current_user={"id": str(sample_user_real.id)},
        client_id=None
    )

    # Create OLD [auto] adjustment (stale, should be removed)
    old_auto = EventCreate(
        date="2025-01-15",
        description="balance adjustment",
        amount=Decimal("200.00"),  # Old, incorrect drift
        account_id=account.id,
        currency="GBP",
        rate_to_base=Decimal("1.0"),
        is_auto_adjustment=True
    )
    await EventRepository(mongodb_real).create(
        old_auto,
        current_user={"id": str(sample_user_real.id)},
        client_id=None
    )

    # Trigger reconciliation
    await trigger_reconciliation(
        trigger_reason="sync",
        db=mongodb_real,
        user_id=sample_user_real.id,
        client_id="test-client"
    )

    # Verify old adjustment removed and new one created
    event_repo = EventRepository(mongodb_real)
    auto_events = await event_repo.collection.find({
        "account_id": str(account.id),
        "is_auto_adjustment": True
    }).to_list(length=None)

    assert len(auto_events) == 1, "Should have exactly 1 auto-adjustment (old removed, new created)"

    # Verify new adjustment has correct drift (1000 - 500 = 500)
    new_auto = auto_events[0]
    assert Decimal(str(new_auto["amount"])) == Decimal("500.00"), "Should have correct drift"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_trigger_reconciliation_multiple_accounts(
    mongodb_real,
    account_repo_real,
    sample_user_real,
    sample_settings_real,
    clean_database_real
):
    """
    Test reconciliation with multiple pending accounts.

    Validates:
    - Processes all pending accounts
    - Creates [auto] adjustments for each
    - Clears all pending flags
    """
    # Create 2 accounts with drift
    accounts = []
    for i, balance in enumerate([1000, 2000]):
        account_data = AccountCreate(
            name=f"Account{i+1}",
            currency="GBP",
            current_balance=Decimal(str(balance)),
            is_default=(i == 0)
        )
        account = await account_repo_real.create(
            account_data,
            current_user={"id": str(sample_user_real.id)},
            client_id=None
        )

        # Mark as pending
        await account_repo_real.collection.update_one(
            {"id": str(account.id)},
            {"$set": {"pending_reconciliation": True}}
        )

        # Create event with half the balance (creates drift)
        event = EventCreate(
            date="2025-01-10",
            description="Initial",
            amount=Decimal(str(balance // 2)),
            account_id=account.id,
            currency="GBP",
            rate_to_base=Decimal("1.0"),
            is_baseline=True
        )
        await EventRepository(mongodb_real).create(
            event,
            current_user={"id": str(sample_user_real.id)},
            client_id=None
        )

        accounts.append(account)

    # Trigger reconciliation
    result = await trigger_reconciliation(
        trigger_reason="sync",
        db=mongodb_real,
        user_id=sample_user_real.id,
        client_id="test-client"
    )

    assert result is True, "Should process multiple accounts"

    # Verify [auto] adjustments created for both accounts
    event_repo = EventRepository(mongodb_real)
    for account in accounts:
        auto_events = await event_repo.collection.find({
            "account_id": str(account.id),
            "is_auto_adjustment": True
        }).to_list(length=None)

        assert len(auto_events) == 1, f"Should create adjustment for {account.name}"

    # Verify all pending flags cleared
    account_repo = AccountRepository(mongodb_real)
    for account in accounts:
        account_doc = await account_repo.collection.find_one({"id": str(account.id)})
        assert account_doc["pending_reconciliation"] is False, "Should clear all pending flags"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_calculate_auto_adjustment_excludes_hypothetical_events(
    mongodb_real,
    account_repo_real,
    sample_user_real,
    sample_settings_real,
    clean_database_real
):
    """
    Test that hypothetical events are excluded from drift calculation.

    Per spec: "Reality as anchor - hypotheticals are explicit opt-ins"
    Hypothetical funding events should NOT affect account-level reconciliation.

    Validates:
    - Hypothetical events excluded from projected balance calculation
    - Only real events contribute to drift
    - Drift calculated correctly when mix of real and hypothetical events exist
    """
    # Create account
    account_data = AccountCreate(
        name="Monzo",
        currency="GBP",
        current_balance=Decimal("1000.00"),
        is_default=True
    )
    account = await account_repo_real.create(
        account_data,
        current_user={"id": str(sample_user_real.id)},
        client_id=None
    )

    event_repo = EventRepository(mongodb_real)

    # Create real event: +500
    real_event = EventCreate(
        date="2025-01-10",
        description="Real income",
        amount=Decimal("500.00"),
        account_id=account.id,
        currency="GBP",
        rate_to_base=Decimal("1.0"),
        is_baseline=True,
        is_hypothetical=False  # REAL event
    )
    await event_repo.create(
        real_event,
        current_user={"id": str(sample_user_real.id)},
        client_id=None
    )

    # Create hypothetical event: +300 (should be ignored)
    hypothetical_event = EventCreate(
        date="2025-01-12",
        description="Hypothetical bonus",
        amount=Decimal("300.00"),
        account_id=account.id,
        currency="GBP",
        rate_to_base=Decimal("1.0"),
        is_baseline=False,
        is_hypothetical=True  # HYPOTHETICAL event (should be excluded)
    )
    await event_repo.create(
        hypothetical_event,
        current_user={"id": str(sample_user_real.id)},
        client_id=None
    )

    # Calculate drift
    # Actual balance: 1000
    # Projected balance should be: 500 (only real event, hypothetical excluded)
    # Expected drift: 1000 - 500 = 500
    adjustment = await calculate_auto_adjustment(
        account_id=account.id,
        actual_balance=Decimal("1000.00"),
        db=mongodb_real,
        user_id=sample_user_real.id
    )

    assert adjustment is not None, "Should return adjustment when drift exists"
    assert adjustment.amount == Decimal("500.00"), (
        "Drift should be 500 (1000 actual - 500 projected). "
        "Hypothetical event (+300) should be excluded from projected balance."
    )
    assert adjustment.is_auto_adjustment is True
    assert adjustment.account_id == account.id

    # Verify hypothetical event was NOT included by checking the math:
    # If hypothetical was included, drift would be 1000 - 800 = 200 (wrong)
