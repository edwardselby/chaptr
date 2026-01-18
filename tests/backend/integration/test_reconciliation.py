"""
Unit tests for reconciliation system - Display-only drift architecture.

Tests cover:
- trigger_reconciliation(): Processing pending accounts, creating [auto] events
- calculate_auto_adjustment(): Drift calculation and threshold logic
- remove_old_auto_adjustments(): Smart cleanup of stale adjustments
- Change log integration: Verify reconciliation logs changes properly
- Timestamp synchronization: Verify updated_at is properly set

Uses real MongoDB for accurate reconciliation flow simulation.
"""

import pytest
import pytest_asyncio
from datetime import datetime, date, timezone, timedelta
from decimal import Decimal
from uuid import uuid4, UUID

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
        current_user={"id": str(sample_user_real.id), "tenant_id": str(sample_user_real.tenant_id)},
        client_id=None
    )

    # Mark as pending reconciliation
    await account_repo_real.collection.update_one(
        {"id": str(account.id)},
        {"$set": {"pending_reconciliation": True}}
    )

    # Create events that add to the opening balance event
    # Note: Account creation automatically adds opening balance event of +1000
    # So we need events that, combined with opening balance, give us a drift scenario
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
        current_user={"id": str(sample_user_real.id), "tenant_id": str(sample_user_real.tenant_id)},
        client_id=None
    )

    event2 = EventCreate(
        event_date="2025-01-15",
        description="Rent",
        amount=Decimal("-1500.00"),
        account_id=account.id,
        currency="GBP",
        rate_to_base=Decimal("1.0"),
        is_baseline=True
    )
    await EventRepository(account_repo_real.db).create(
        event2,
        current_user={"id": str(sample_user_real.id), "tenant_id": str(sample_user_real.tenant_id)},
        client_id=None
    )

    # Projected balance: opening_balance(1000) + 2000 - 1500 = 1500
    # Account current_balance: 1000 (actual)
    # Drift: 1000 - 1500 = -500 (need to subtract 500 to match reality)

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
        current_user={"id": str(sample_user_real.id), "tenant_id": str(sample_user_real.tenant_id)},
        client_id=None
    )

    # Create existing [auto] adjustment
    auto_event = EventCreate(
        event_date="2025-01-20",
        description="balance adjustment",
        amount=Decimal("100.00"),
        account_id=account.id,
        currency="GBP",
        rate_to_base=Decimal("1.0"),
        is_auto_adjustment=True
    )
    await EventRepository(account_repo_real.db).create(
        auto_event,
        current_user={"id": str(sample_user_real.id), "tenant_id": str(sample_user_real.tenant_id)},
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
        client_id="test-client",
        tenant_id=sample_user_real.tenant_id
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
        client_id="test-client",
        tenant_id=sample_user_real.tenant_id
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
    # Drift = actual - projected = 1000 - 1500 = -500
    # (opening_balance 1000 + salary 2000 - rent 1500 = 1500 projected)
    assert adjustment.amount == Decimal("-500.00"), "Drift should be -500 (1000 actual - 1500 projected)"
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
    # Create account with balance (opening balance event created automatically)
    account_data = AccountCreate(
        name="Revolut",
        currency="GBP",
        current_balance=Decimal("500.00"),
        is_default=False
    )
    account = await account_repo_real.create(
        account_data,
        current_user={"id": str(sample_user_real.id), "tenant_id": str(sample_user_real.tenant_id)},
        client_id=None
    )

    # No additional events needed - opening balance event (500) matches actual balance (500)
    # Projected = opening_balance(500) = 500
    # Actual = 500
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
    # Create account with current_balance=500 (opening balance event +500 created automatically)
    account_data = AccountCreate(
        name="Starling",
        currency="GBP",
        current_balance=Decimal("500.00"),
        is_default=False
    )
    account = await account_repo_real.create(
        account_data,
        current_user={"id": str(sample_user_real.id), "tenant_id": str(sample_user_real.tenant_id)},
        client_id=None
    )

    # Create additional event that increases projected balance
    event = EventCreate(
        event_date="2025-01-10",
        description="Large deposit",
        amount=Decimal("1000.00"),
        account_id=account.id,
        currency="GBP",
        rate_to_base=Decimal("1.0"),
        is_baseline=True
    )
    await EventRepository(mongodb_real).create(
        event,
        current_user={"id": str(sample_user_real.id), "tenant_id": str(sample_user_real.tenant_id)},
        client_id=None
    )

    # Projected = opening_balance(500) + 1000 = 1500
    # Actual = 500
    # Drift = 500 - 1500 = -1000 (negative)
    adjustment = await calculate_auto_adjustment(
        account_id=account.id,
        actual_balance=Decimal("500.00"),
        db=mongodb_real,
        user_id=sample_user_real.id
    )

    assert adjustment is not None, "Should return adjustment for negative drift"
    assert adjustment.amount == Decimal("-1000.00"), "Should handle negative drift"


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
    reconciled_ids = await trigger_reconciliation(
        trigger_reason="sync",
        db=mongodb_real,
        user_id=sample_user_real.id,
        client_id="test-client",
        tenant_id=sample_user_real.tenant_id
    )

    assert len(reconciled_ids) > 0, "Should return non-empty list when reconciliation runs"
    assert account_with_drift.id in reconciled_ids, "Should include the pending account"

    # Verify [auto] adjustment was created
    auto_events = await event_repo.collection.find({
        "account_id": str(account_with_drift.id),
        "is_auto_adjustment": True
    }).to_list(length=None)

    assert len(auto_events) == 1, "Should create 1 auto-adjustment"

    auto_event = auto_events[0]
    # Drift = actual - projected = 1000 - 1500 = -500
    assert Decimal(str(auto_event["amount"])) == Decimal("-500.00"), "Should have drift amount (-500)"
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
    reconciled_ids = await trigger_reconciliation(
        trigger_reason="sync",
        db=mongodb_real,
        user_id=sample_user_real.id,
        client_id="test-client",
        tenant_id=sample_user_real.tenant_id
    )

    assert reconciled_ids == [], "Should return empty list when no pending accounts"

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
        current_user={"id": str(sample_user_real.id), "tenant_id": str(sample_user_real.tenant_id)},
        client_id=None
    )

    # Mark as pending
    await account_repo_real.collection.update_one(
        {"id": str(account.id)},
        {"$set": {"pending_reconciliation": True}}
    )

    # No additional events needed - opening balance already created with +1000
    # Projected = opening_balance(1000) = 1000
    # Actual = 1000
    # Drift = 0 (no adjustment needed without additional events)

    # Create additional event that creates drift
    event = EventCreate(
        event_date="2025-01-10",
        description="Spending",
        amount=Decimal("-500.00"),  # This creates drift: projected becomes 500
        account_id=account.id,
        currency="GBP",
        rate_to_base=Decimal("1.0"),
        is_baseline=True
    )
    await EventRepository(mongodb_real).create(
        event,
        current_user={"id": str(sample_user_real.id), "tenant_id": str(sample_user_real.tenant_id)},
        client_id=None
    )

    # Create OLD [auto] adjustment (stale, should be removed)
    old_auto = EventCreate(
        event_date="2025-01-15",
        description="balance adjustment",
        amount=Decimal("200.00"),  # Old, incorrect drift
        account_id=account.id,
        currency="GBP",
        rate_to_base=Decimal("1.0"),
        is_auto_adjustment=True
    )
    await EventRepository(mongodb_real).create(
        old_auto,
        current_user={"id": str(sample_user_real.id), "tenant_id": str(sample_user_real.tenant_id)},
        client_id=None
    )

    # Trigger reconciliation
    await trigger_reconciliation(
        trigger_reason="sync",
        db=mongodb_real,
        user_id=sample_user_real.id,
        client_id="test-client",
        tenant_id=sample_user_real.tenant_id
    )

    # Verify old adjustment removed and new one created
    event_repo = EventRepository(mongodb_real)
    auto_events = await event_repo.collection.find({
        "account_id": str(account.id),
        "is_auto_adjustment": True
    }).to_list(length=None)

    assert len(auto_events) == 1, "Should have exactly 1 auto-adjustment (old removed, new created)"

    # Verify new adjustment has correct drift
    # Projected = opening_balance(1000) - 500 = 500
    # Actual = 1000
    # Drift = 1000 - 500 = +500
    new_auto = auto_events[0]
    assert Decimal(str(new_auto["amount"])) == Decimal("500.00"), "Should have correct drift (+500)"


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
            current_user={"id": str(sample_user_real.id), "tenant_id": str(sample_user_real.tenant_id)},
            client_id=None
        )

        # Mark as pending
        await account_repo_real.collection.update_one(
            {"id": str(account.id)},
            {"$set": {"pending_reconciliation": True}}
        )

        # Create spending event that reduces projected balance (creates positive drift)
        # Opening balance = balance (1000 or 2000)
        # Spending = -balance/2
        # Projected = balance - balance/2 = balance/2
        # Drift = actual(balance) - projected(balance/2) = balance/2 (positive)
        event = EventCreate(
            event_date="2025-01-10",
            description="Spending",
            amount=Decimal(str(-(balance // 2))),  # Negative spending
            account_id=account.id,
            currency="GBP",
            rate_to_base=Decimal("1.0"),
            is_baseline=True
        )
        await EventRepository(mongodb_real).create(
            event,
            current_user={"id": str(sample_user_real.id), "tenant_id": str(sample_user_real.tenant_id)},
            client_id=None
        )

        accounts.append(account)

    # Trigger reconciliation
    reconciled_ids = await trigger_reconciliation(
        trigger_reason="sync",
        db=mongodb_real,
        user_id=sample_user_real.id,
        client_id="test-client",
        tenant_id=sample_user_real.tenant_id
    )

    assert len(reconciled_ids) == 2, "Should process both pending accounts"
    for account in accounts:
        assert account.id in reconciled_ids, f"Should include {account.name} in reconciled list"

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
        current_user={"id": str(sample_user_real.id), "tenant_id": str(sample_user_real.tenant_id)},
        client_id=None
    )

    event_repo = EventRepository(mongodb_real)

    # Create real event: +500
    real_event = EventCreate(
        event_date="2025-01-10",
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
        current_user={"id": str(sample_user_real.id), "tenant_id": str(sample_user_real.tenant_id)},
        client_id=None
    )

    # Create hypothetical event: +300 (should be ignored)
    hypothetical_event = EventCreate(
        event_date="2025-01-12",
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
        current_user={"id": str(sample_user_real.id), "tenant_id": str(sample_user_real.tenant_id)},
        client_id=None
    )

    # Calculate drift
    # Opening balance (auto-created): +1000
    # Real event: +500
    # Hypothetical event: +300 (EXCLUDED from calculation)
    # Projected balance = 1000 + 500 = 1500 (hypothetical excluded)
    # Actual balance: 1000
    # Expected drift: 1000 - 1500 = -500
    adjustment = await calculate_auto_adjustment(
        account_id=account.id,
        actual_balance=Decimal("1000.00"),
        db=mongodb_real,
        user_id=sample_user_real.id
    )

    assert adjustment is not None, "Should return adjustment when drift exists"
    assert adjustment.amount == Decimal("-500.00"), (
        "Drift should be -500 (1000 actual - 1500 projected). "
        "Hypothetical event (+300) should be excluded from projected balance."
    )
    assert adjustment.is_auto_adjustment is True
    assert adjustment.account_id == account.id

    # Verify hypothetical event was NOT included by checking the math:
    # If hypothetical was included: projected = 1000 + 500 + 300 = 1800
    # drift would be 1000 - 1800 = -800 (wrong)


# ============================================================================
# Unit Tests: Change Log Integration
# ============================================================================

@pytest.mark.integration
@pytest.mark.asyncio
async def test_reconciliation_logs_account_update_to_change_log(
    mongodb_real,
    account_repo_real,
    sample_user_real,
    sample_settings_real,
    clean_database_real
):
    """
    Test that reconciliation properly logs account updates to change_log.

    When reconciliation clears pending_reconciliation flag, it should:
    1. Use AccountRepository.update() (not direct MongoDB update)
    2. Log the change to change_log
    3. Other clients can see the update in their server_changes

    This is critical for multi-client sync - without logging, other
    clients won't know about the account's updated_at change.
    """
    # Create account with pending reconciliation
    account_data = AccountCreate(
        name="LogTestAccount",
        currency="GBP",
        current_balance=Decimal("1000.00"),
        is_default=False
    )
    account = await account_repo_real.create(
        account_data,
        current_user={"id": str(sample_user_real.id), "tenant_id": str(sample_user_real.tenant_id)},
        client_id=None
    )

    # Mark as pending
    await account_repo_real.collection.update_one(
        {"id": str(account.id)},
        {"$set": {"pending_reconciliation": True}}
    )

    # Count change_log entries before reconciliation
    change_log_before = await mongodb_real["change_log"].count_documents({
        "entity_type": "account",
        "entity_id": str(account.id)
    })

    # Trigger reconciliation
    await trigger_reconciliation(
        trigger_reason="sync",
        db=mongodb_real,
        user_id=sample_user_real.id,
        client_id="test-client",
        tenant_id=sample_user_real.tenant_id
    )

    # Verify change_log entry was created for account update
    change_log_after = await mongodb_real["change_log"].count_documents({
        "entity_type": "account",
        "entity_id": str(account.id)
    })

    assert change_log_after > change_log_before, (
        "Reconciliation should log account update to change_log. "
        "This ensures other clients see the pending_reconciliation change."
    )

    # Verify the logged change is an update with correct data
    latest_log = await mongodb_real["change_log"].find_one(
        {"entity_type": "account", "entity_id": str(account.id)},
        sort=[("changed_at", -1)]
    )

    assert latest_log is not None, "Should have change_log entry"
    assert latest_log["action"] == "update", "Should be an update action"
    assert latest_log["data"]["pending_reconciliation"] is False, (
        "Change log should show pending_reconciliation = False"
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_reconciliation_returns_correct_account_ids(
    mongodb_real,
    account_repo_real,
    sample_user_real,
    sample_settings_real,
    clean_database_real
):
    """
    Test that trigger_reconciliation returns the exact account IDs that were reconciled.

    Validates:
    - Returns List[UUID] (not bool)
    - List contains all processed account IDs
    - List is empty when no accounts pending
    - IDs match the accounts that had pending_reconciliation=True
    """
    # Create 3 accounts - only 2 will be pending
    pending_accounts = []
    non_pending_account = None

    for i in range(3):
        account_data = AccountCreate(
            name=f"TestAccount{i+1}",
            currency="GBP",
            current_balance=Decimal("1000.00"),
            is_default=(i == 0)
        )
        account = await account_repo_real.create(
            account_data,
            current_user={"id": str(sample_user_real.id), "tenant_id": str(sample_user_real.tenant_id)},
            client_id=None
        )

        if i < 2:
            # Mark first 2 as pending
            await account_repo_real.collection.update_one(
                {"id": str(account.id)},
                {"$set": {"pending_reconciliation": True}}
            )
            pending_accounts.append(account)
        else:
            non_pending_account = account

    # Trigger reconciliation
    reconciled_ids = await trigger_reconciliation(
        trigger_reason="sync",
        db=mongodb_real,
        user_id=sample_user_real.id,
        client_id="test-client",
        tenant_id=sample_user_real.tenant_id
    )

    # Verify return type and content
    assert isinstance(reconciled_ids, list), "Should return a list"
    assert len(reconciled_ids) == 2, "Should return exactly 2 account IDs"

    # Verify correct accounts were reconciled
    for pending_account in pending_accounts:
        assert pending_account.id in reconciled_ids, (
            f"Should include pending account {pending_account.name}"
        )

    # Verify non-pending account was NOT reconciled
    assert non_pending_account.id not in reconciled_ids, (
        "Should NOT include non-pending account"
    )


# ============================================================================
# Unit Tests: Timestamp Synchronization
# ============================================================================

@pytest.mark.integration
@pytest.mark.asyncio
async def test_reconciliation_updates_account_timestamp(
    mongodb_real,
    account_repo_real,
    sample_user_real,
    sample_settings_real,
    clean_database_real
):
    """
    Test that reconciliation properly updates account's updated_at timestamp.

    This is critical for conflict detection:
    1. Reconciliation clears pending_reconciliation flag
    2. This updates the account's updated_at
    3. Client must receive this new timestamp
    4. Without it, next sync will falsely detect a conflict

    Validates:
    - Account's updated_at changes after reconciliation
    - The new timestamp is more recent than before
    """
    # Create account
    account_data = AccountCreate(
        name="TimestampTestAccount",
        currency="GBP",
        current_balance=Decimal("500.00"),
        is_default=False
    )
    account = await account_repo_real.create(
        account_data,
        current_user={"id": str(sample_user_real.id), "tenant_id": str(sample_user_real.tenant_id)},
        client_id=None
    )

    # Record timestamp before reconciliation
    account_before = await account_repo_real.get(account.id)
    timestamp_before = account_before.updated_at

    # Mark as pending
    await account_repo_real.collection.update_one(
        {"id": str(account.id)},
        {"$set": {"pending_reconciliation": True}}
    )

    # Trigger reconciliation
    await trigger_reconciliation(
        trigger_reason="sync",
        db=mongodb_real,
        user_id=sample_user_real.id,
        client_id="test-client",
        tenant_id=sample_user_real.tenant_id
    )

    # Verify timestamp was updated
    account_after = await account_repo_real.get(account.id)
    timestamp_after = account_after.updated_at

    assert timestamp_after > timestamp_before, (
        "Account updated_at should be more recent after reconciliation. "
        "This is critical for conflict detection."
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_reconciliation_timestamp_matches_returned_id(
    mongodb_real,
    account_repo_real,
    sample_user_real,
    sample_settings_real,
    clean_database_real
):
    """
    Test that returned account ID can be used to fetch the correct updated_at.

    This ensures the sync endpoint can:
    1. Call trigger_reconciliation()
    2. Use returned IDs to fetch fresh timestamps
    3. Include those timestamps in AppliedChange response
    4. Client receives correct timestamps for all reconciled accounts

    Validates:
    - Returned account ID is valid UUID
    - Can fetch account using returned ID
    - Fetched account has updated pending_reconciliation=False
    """
    # Create account with drift
    account_data = AccountCreate(
        name="IdMatchTestAccount",
        currency="GBP",
        current_balance=Decimal("1000.00"),
        is_default=False
    )
    account = await account_repo_real.create(
        account_data,
        current_user={"id": str(sample_user_real.id), "tenant_id": str(sample_user_real.tenant_id)},
        client_id=None
    )

    # Mark as pending
    await account_repo_real.collection.update_one(
        {"id": str(account.id)},
        {"$set": {"pending_reconciliation": True}}
    )

    # Create event with drift
    event = EventCreate(
        event_date="2025-01-10",
        description="Initial",
        amount=Decimal("500.00"),
        account_id=account.id,
        currency="GBP",
        rate_to_base=Decimal("1.0"),
        is_baseline=True
    )
    await EventRepository(mongodb_real).create(
        event,
        current_user={"id": str(sample_user_real.id), "tenant_id": str(sample_user_real.tenant_id)},
        client_id=None
    )

    # Trigger reconciliation
    reconciled_ids = await trigger_reconciliation(
        trigger_reason="sync",
        db=mongodb_real,
        user_id=sample_user_real.id,
        client_id="test-client",
        tenant_id=sample_user_real.tenant_id
    )

    # Verify we can use the returned ID
    assert len(reconciled_ids) == 1
    returned_id = reconciled_ids[0]

    # Verify it's a valid UUID
    assert isinstance(returned_id, UUID), "Returned ID should be UUID type"
    assert returned_id == account.id, "Returned ID should match account ID"

    # Fetch account using returned ID
    fetched_account = await account_repo_real.get(returned_id)

    # Verify account state
    assert fetched_account is not None, "Should be able to fetch account by returned ID"
    assert fetched_account.pending_reconciliation is False, (
        "Fetched account should have pending_reconciliation=False"
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_reconciliation_creates_events_logged_to_change_log(
    mongodb_real,
    account_repo_real,
    sample_user_real,
    sample_settings_real,
    clean_database_real
):
    """
    Test that [auto] adjustment events created by reconciliation are logged.

    Validates:
    - New [auto] events are logged to change_log
    - Deleted old [auto] events are logged to change_log
    - Other clients can receive these changes via server_changes
    """
    # Create account with drift
    account_data = AccountCreate(
        name="EventLogTestAccount",
        currency="GBP",
        current_balance=Decimal("1000.00"),
        is_default=False
    )
    account = await account_repo_real.create(
        account_data,
        current_user={"id": str(sample_user_real.id), "tenant_id": str(sample_user_real.tenant_id)},
        client_id=None
    )

    # Mark as pending
    await account_repo_real.collection.update_one(
        {"id": str(account.id)},
        {"$set": {"pending_reconciliation": True}}
    )

    # Create event with drift
    event = EventCreate(
        event_date="2025-01-10",
        description="Initial",
        amount=Decimal("500.00"),
        account_id=account.id,
        currency="GBP",
        rate_to_base=Decimal("1.0"),
        is_baseline=True
    )
    await EventRepository(mongodb_real).create(
        event,
        current_user={"id": str(sample_user_real.id), "tenant_id": str(sample_user_real.tenant_id)},
        client_id=None
    )

    # Count event change_log entries before reconciliation
    event_logs_before = await mongodb_real["change_log"].count_documents({
        "entity_type": "event"
    })

    # Trigger reconciliation
    await trigger_reconciliation(
        trigger_reason="sync",
        db=mongodb_real,
        user_id=sample_user_real.id,
        client_id="test-client",
        tenant_id=sample_user_real.tenant_id
    )

    # Count event change_log entries after reconciliation
    event_logs_after = await mongodb_real["change_log"].count_documents({
        "entity_type": "event"
    })

    # Verify new event was logged (the [auto] adjustment)
    assert event_logs_after > event_logs_before, (
        "Reconciliation should log [auto] adjustment event creation to change_log"
    )

    # Verify the logged event is the [auto] adjustment
    event_repo = EventRepository(mongodb_real)
    auto_events = await event_repo.collection.find({
        "account_id": str(account.id),
        "is_auto_adjustment": True
    }).to_list(length=None)

    assert len(auto_events) == 1, "Should create one [auto] adjustment"

    # Check change_log has create entry for this event
    auto_event_id = auto_events[0]["id"]
    create_log = await mongodb_real["change_log"].find_one({
        "entity_type": "event",
        "entity_id": auto_event_id,
        "action": "create"
    })

    assert create_log is not None, (
        "[auto] adjustment event creation should be logged to change_log"
    )


# ============================================================================
# Unit Tests: Future Event Filtering
# ============================================================================

@pytest.mark.integration
@pytest.mark.asyncio
async def test_calculate_auto_adjustment_excludes_future_events(
    mongodb_real,
    account_repo_real,
    sample_user_real,
    sample_settings_real,
    clean_database_real
):
    """
    Test that events with future dates are excluded from drift calculation.

    Per spec: Reconciliation calculates projected balance at CURRENT date.
    Future events should NOT affect the drift calculation.

    Validates:
    - Events with event_date > today are excluded
    - Only past and today events contribute to projected balance
    - Drift is calculated correctly ignoring future events
    """
    # Create account with current_balance=1000 (opening balance +1000 auto-created)
    account_data = AccountCreate(
        name="FutureDateTest",
        currency="GBP",
        current_balance=Decimal("1000.00"),
        is_default=False
    )
    account = await account_repo_real.create(
        account_data,
        current_user={"id": str(sample_user_real.id), "tenant_id": str(sample_user_real.tenant_id)},
        client_id=None
    )

    event_repo = EventRepository(mongodb_real)

    # Create PAST event: +500 (should be included)
    past_event = EventCreate(
        event_date="2025-01-10",
        description="Past income",
        amount=Decimal("500.00"),
        account_id=account.id,
        currency="GBP",
        rate_to_base=Decimal("1.0"),
        is_baseline=True,
        is_hypothetical=False
    )
    await event_repo.create(
        past_event,
        current_user={"id": str(sample_user_real.id), "tenant_id": str(sample_user_real.tenant_id)},
        client_id=None
    )

    # Create FUTURE event: +2000 (should be EXCLUDED)
    future_date = (datetime.now(timezone.utc) + timedelta(days=30)).date().isoformat()
    future_event = EventCreate(
        event_date=future_date,
        description="Future salary",
        amount=Decimal("2000.00"),
        account_id=account.id,
        currency="GBP",
        rate_to_base=Decimal("1.0"),
        is_baseline=True,
        is_hypothetical=False
    )
    await event_repo.create(
        future_event,
        current_user={"id": str(sample_user_real.id), "tenant_id": str(sample_user_real.tenant_id)},
        client_id=None
    )

    # Calculate drift
    # Opening balance (auto-created): +1000
    # Past event: +500
    # Future event: +2000 (EXCLUDED - in the future)
    # Projected balance = 1000 + 500 = 1500
    # Actual balance: 1000
    # Expected drift: 1000 - 1500 = -500
    adjustment = await calculate_auto_adjustment(
        account_id=account.id,
        actual_balance=Decimal("1000.00"),
        db=mongodb_real,
        user_id=sample_user_real.id
    )

    assert adjustment is not None, "Should return adjustment when drift exists"
    assert adjustment.amount == Decimal("-500.00"), (
        "Drift should be -500 (1000 actual - 1500 projected). "
        "Future event (+2000) should be excluded from projected balance. "
        "If future event was included, drift would be -2500."
    )


# ============================================================================
# Unit Tests: Tenant Isolation
# ============================================================================

@pytest.mark.integration
@pytest.mark.asyncio
async def test_calculate_auto_adjustment_excludes_other_tenants_events(
    mongodb_real,
    account_repo_real,
    sample_user_real,
    sample_settings_real,
    clean_database_real
):
    """
    Test that events from different tenants are excluded from drift calculation.

    Multi-tenancy security: Each tenant's drift should only consider events
    within that tenant. This is critical for data isolation.

    Note: Within a tenant, ALL users share data. Multiple users in the same
    tenant see and affect the same drift calculation. Isolation is at the
    tenant level, not user level.

    Validates:
    - Events with different tenant_id are excluded
    - Events from same-tenant users ARE included (multi-user tenants share data)
    - Drift is calculated correctly for the specific tenant
    """
    from uuid import uuid4

    # Create account for sample_user_real's tenant
    account_data = AccountCreate(
        name="TenantIsolationTest",
        currency="GBP",
        current_balance=Decimal("1000.00"),
        is_default=False
    )
    account = await account_repo_real.create(
        account_data,
        current_user={"id": str(sample_user_real.id), "tenant_id": str(sample_user_real.tenant_id)},
        client_id=None
    )

    event_repo = EventRepository(mongodb_real)

    # Create event as CURRENT TENANT USER: +500
    tenant1_event = EventCreate(
        event_date="2025-01-10",
        description="Tenant1 income",
        amount=Decimal("500.00"),
        account_id=account.id,
        currency="GBP",
        rate_to_base=Decimal("1.0"),
        is_baseline=True,
        is_hypothetical=False
    )
    await event_repo.create(
        tenant1_event,
        current_user={"id": str(sample_user_real.id), "tenant_id": str(sample_user_real.tenant_id)},
        client_id=None
    )

    # Create event from DIFFERENT TENANT: +3000 (should be EXCLUDED)
    # This simulates data leakage attempt - event inserted directly with wrong tenant_id
    other_tenant_id = uuid4()
    other_tenant_event_doc = {
        "id": str(uuid4()),
        "event_date": "2025-01-12",
        "description": "OtherTenant income",
        "amount": "3000.00",
        "account_id": str(account.id),  # Same account, different tenant
        "currency": "GBP",
        "rate_to_base": "1.0",
        "is_baseline": True,
        "is_hypothetical": False,
        "is_auto_adjustment": False,
        "is_opening_balance": False,
        "tenant_id": str(other_tenant_id),  # DIFFERENT TENANT
        "created_by": str(uuid4()),
        "updated_by": str(uuid4()),
        "created_at": "2025-01-12T00:00:00+00:00",
        "updated_at": "2025-01-12T00:00:00+00:00",
        "story_id": None,
        "recurring_rule_id": None
    }
    await mongodb_real["events"].insert_one(other_tenant_event_doc)

    # Calculate drift FOR CURRENT TENANT
    # Opening balance (tenant1): +1000
    # Tenant1 event: +500
    # OtherTenant event: +3000 (EXCLUDED - different tenant_id)
    # Projected balance = 1000 + 500 = 1500
    # Actual balance: 1000
    # Expected drift: 1000 - 1500 = -500
    adjustment = await calculate_auto_adjustment(
        account_id=account.id,
        actual_balance=Decimal("1000.00"),
        db=mongodb_real,
        user_id=sample_user_real.id,
        tenant_id=sample_user_real.tenant_id
    )

    assert adjustment is not None, "Should return adjustment when drift exists"
    assert adjustment.amount == Decimal("-500.00"), (
        "Drift should be -500 (1000 actual - 1500 projected). "
        "Other tenant's event (+3000) should be excluded from projected balance. "
        "If other tenant's event was included, drift would be -3500."
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_calculate_auto_adjustment_includes_same_tenant_different_user_events(
    mongodb_real,
    account_repo_real,
    sample_user_real,
    sample_settings_real,
    clean_database_real
):
    """
    Test that events from different users WITHIN THE SAME TENANT are included.

    Multi-tenancy: Users in the same tenant share data. All events within
    a tenant contribute to drift calculation, regardless of which user
    created them.

    Validates:
    - Events with same tenant_id but different created_by ARE included
    - Multi-user tenants correctly share reconciliation data
    """
    from uuid import uuid4

    # Create account for sample_user_real's tenant
    account_data = AccountCreate(
        name="SameTenantDiffUserTest",
        currency="GBP",
        current_balance=Decimal("1000.00"),
        is_default=False
    )
    account = await account_repo_real.create(
        account_data,
        current_user={"id": str(sample_user_real.id), "tenant_id": str(sample_user_real.tenant_id)},
        client_id=None
    )

    event_repo = EventRepository(mongodb_real)

    # Create event as USER 1 (sample_user_real): +500
    user1_event = EventCreate(
        event_date="2025-01-10",
        description="User1 income",
        amount=Decimal("500.00"),
        account_id=account.id,
        currency="GBP",
        rate_to_base=Decimal("1.0"),
        is_baseline=True,
        is_hypothetical=False
    )
    await event_repo.create(
        user1_event,
        current_user={"id": str(sample_user_real.id), "tenant_id": str(sample_user_real.tenant_id)},
        client_id=None
    )

    # Create event as USER 2 (DIFFERENT user, SAME tenant): +300
    # This should be INCLUDED because they're in the same tenant
    other_user_id = uuid4()
    user2_event = EventCreate(
        event_date="2025-01-12",
        description="User2 income (same tenant)",
        amount=Decimal("300.00"),
        account_id=account.id,
        currency="GBP",
        rate_to_base=Decimal("1.0"),
        is_baseline=True,
        is_hypothetical=False
    )
    # Pass same tenant_id but different user_id
    await event_repo.create(
        user2_event,
        current_user={"id": str(other_user_id), "tenant_id": str(sample_user_real.tenant_id)},
        client_id=None
    )

    # Calculate drift FOR CURRENT TENANT
    # Opening balance: +1000
    # User1 event: +500
    # User2 event: +300 (INCLUDED - same tenant)
    # Projected balance = 1000 + 500 + 300 = 1800
    # Actual balance: 1000
    # Expected drift: 1000 - 1800 = -800
    adjustment = await calculate_auto_adjustment(
        account_id=account.id,
        actual_balance=Decimal("1000.00"),
        db=mongodb_real,
        user_id=sample_user_real.id,
        tenant_id=sample_user_real.tenant_id
    )

    assert adjustment is not None, "Should return adjustment when drift exists"
    assert adjustment.amount == Decimal("-800.00"), (
        "Drift should be -800 (1000 actual - 1800 projected). "
        "User2's event (+300) from same tenant should be INCLUDED. "
        "Multi-user tenants share data for reconciliation."
    )


# ============================================================================
# Unit Tests: Drift Threshold Boundary
# ============================================================================

@pytest.mark.integration
@pytest.mark.asyncio
async def test_calculate_auto_adjustment_drift_exactly_at_threshold(
    mongodb_real,
    account_repo_real,
    sample_user_real,
    sample_settings_real,
    clean_database_real
):
    """
    Test that drift exactly at 0.01 threshold returns None.

    The threshold check is: abs(drift) <= 0.01 returns None
    So drift of exactly 0.01 should NOT create an adjustment.

    Validates:
    - Boundary condition: drift == 0.01 returns None
    """
    # Create account with current_balance that will result in exactly 0.01 drift
    # Opening balance = 100.00
    # Actual balance = 100.01
    # Drift = 100.01 - 100.00 = 0.01
    account_data = AccountCreate(
        name="ThresholdBoundaryTest",
        currency="GBP",
        current_balance=Decimal("100.00"),
        is_default=False
    )
    account = await account_repo_real.create(
        account_data,
        current_user={"id": str(sample_user_real.id), "tenant_id": str(sample_user_real.tenant_id)},
        client_id=None
    )

    # No additional events - just opening balance of 100.00
    # Calculate with actual = 100.01 (drift exactly 0.01)
    adjustment = await calculate_auto_adjustment(
        account_id=account.id,
        actual_balance=Decimal("100.01"),
        db=mongodb_real,
        user_id=sample_user_real.id
    )

    assert adjustment is None, (
        "Drift exactly at threshold (0.01) should return None. "
        "Threshold check is: abs(drift) <= 0.01"
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_calculate_auto_adjustment_drift_just_above_threshold(
    mongodb_real,
    account_repo_real,
    sample_user_real,
    sample_settings_real,
    clean_database_real
):
    """
    Test that drift just above 0.01 threshold creates adjustment.

    The threshold check is: abs(drift) <= 0.01 returns None
    So drift of 0.02 should create an adjustment.

    Validates:
    - Boundary condition: drift > 0.01 creates adjustment
    """
    # Create account
    account_data = AccountCreate(
        name="AboveThresholdTest",
        currency="GBP",
        current_balance=Decimal("100.00"),
        is_default=False
    )
    account = await account_repo_real.create(
        account_data,
        current_user={"id": str(sample_user_real.id), "tenant_id": str(sample_user_real.tenant_id)},
        client_id=None
    )

    # No additional events - just opening balance of 100.00
    # Calculate with actual = 100.02 (drift 0.02, just above threshold)
    adjustment = await calculate_auto_adjustment(
        account_id=account.id,
        actual_balance=Decimal("100.02"),
        db=mongodb_real,
        user_id=sample_user_real.id
    )

    assert adjustment is not None, (
        "Drift above threshold (0.02) should create adjustment"
    )
    assert adjustment.amount == Decimal("0.02"), (
        "Drift amount should be 0.02 (100.02 actual - 100.00 projected)"
    )


# ============================================================================
# Unit Tests: Idempotency
# ============================================================================

@pytest.mark.integration
@pytest.mark.asyncio
async def test_reconciliation_idempotency_second_run_no_change(
    mongodb_real,
    account_repo_real,
    sample_user_real,
    sample_settings_real,
    clean_database_real
):
    """
    Test that running reconciliation twice produces same result.

    Idempotency is critical for reliability - repeated calls should not
    accumulate adjustments or cause data corruption.

    Validates:
    - First reconciliation creates [auto] adjustment
    - Second reconciliation produces same result (no additional adjustments)
    - Total [auto] adjustments remains 1
    """
    event_repo = EventRepository(mongodb_real)

    # Create account with drift
    account_data = AccountCreate(
        name="IdempotencyTest",
        currency="GBP",
        current_balance=Decimal("1000.00"),
        is_default=False
    )
    account = await account_repo_real.create(
        account_data,
        current_user={"id": str(sample_user_real.id), "tenant_id": str(sample_user_real.tenant_id)},
        client_id=None
    )

    # Create event to cause drift
    drift_event = EventCreate(
        event_date="2025-01-10",
        description="Spending",
        amount=Decimal("-200.00"),
        account_id=account.id,
        currency="GBP",
        rate_to_base=Decimal("1.0"),
        is_baseline=True,
        is_hypothetical=False
    )
    await event_repo.create(
        drift_event,
        current_user={"id": str(sample_user_real.id), "tenant_id": str(sample_user_real.tenant_id)},
        client_id=None
    )

    # Mark as pending
    await account_repo_real.collection.update_one(
        {"id": str(account.id)},
        {"$set": {"pending_reconciliation": True}}
    )

    # FIRST reconciliation
    first_result = await trigger_reconciliation(
        trigger_reason="sync",
        db=mongodb_real,
        user_id=sample_user_real.id,
        client_id="test-client",
        tenant_id=sample_user_real.tenant_id
    )

    # Count [auto] adjustments after first run
    auto_events_after_first = await event_repo.collection.find({
        "account_id": str(account.id),
        "is_auto_adjustment": True
    }).to_list(length=None)

    assert len(first_result) == 1, "First run should reconcile account"
    assert len(auto_events_after_first) == 1, "Should have 1 auto-adjustment after first run"

    # Get the adjustment amount from first run
    first_adjustment_amount = Decimal(str(auto_events_after_first[0]["amount"]))

    # Mark as pending again to simulate another reconciliation trigger
    await account_repo_real.collection.update_one(
        {"id": str(account.id)},
        {"$set": {"pending_reconciliation": True}}
    )

    # SECOND reconciliation
    second_result = await trigger_reconciliation(
        trigger_reason="sync",
        db=mongodb_real,
        user_id=sample_user_real.id,
        client_id="test-client",
        tenant_id=sample_user_real.tenant_id
    )

    # Count [auto] adjustments after second run
    auto_events_after_second = await event_repo.collection.find({
        "account_id": str(account.id),
        "is_auto_adjustment": True
    }).to_list(length=None)

    # VERIFY IDEMPOTENCY
    assert len(second_result) == 1, "Second run should also reconcile account"
    assert len(auto_events_after_second) == 1, (
        "Should still have exactly 1 auto-adjustment after second run. "
        "Reconciliation should be idempotent - old adjustment removed, new one created."
    )

    # The second adjustment should be the same amount (since projected = actual now)
    # Actually, after first reconciliation, projected = actual, so second should create 0 drift
    # But the old adjustment is removed first, so we need to recalculate...
    # Let me think about this more carefully:
    # After first run: projected includes the new [auto] adjustment
    # When second run starts, it REMOVES old [auto] adjustments BEFORE calculating drift
    # So the drift calculation sees: opening(1000) + spending(-200) = 800 projected
    # Actual = 1000, so drift = 1000 - 800 = +200 (same as first time)
    second_adjustment_amount = Decimal(str(auto_events_after_second[0]["amount"]))
    assert second_adjustment_amount == first_adjustment_amount, (
        "Second reconciliation should produce same adjustment amount as first. "
        f"First: {first_adjustment_amount}, Second: {second_adjustment_amount}"
    )


# ============================================================================
# Unit Tests: Delete Logging
# ============================================================================

@pytest.mark.integration
@pytest.mark.asyncio
async def test_remove_old_auto_adjustments_logs_deletion(
    mongodb_real,
    account_with_auto_adjustment,
    sample_user_real,
    clean_database_real
):
    """
    Test that removing old [auto] adjustments logs the deletion to change_log.

    This is critical for sync: other clients need to see that the event was deleted.

    Validates:
    - Deleted [auto] events are logged to change_log
    - Log entry has action="delete"
    - Log entry contains event snapshot
    """
    # Count change_log delete entries before
    delete_logs_before = await mongodb_real["change_log"].count_documents({
        "entity_type": "event",
        "action": "delete"
    })

    # Get the auto-adjustment event ID before deletion
    event_repo = EventRepository(mongodb_real)
    auto_events = await event_repo.collection.find({
        "account_id": str(account_with_auto_adjustment.id),
        "is_auto_adjustment": True
    }).to_list(length=None)
    assert len(auto_events) == 1, "Should have 1 auto-adjustment before removal"
    auto_event_id = auto_events[0]["id"]

    # Remove auto-adjustments
    removed_count = await remove_old_auto_adjustments(
        account_id=account_with_auto_adjustment.id,
        db=mongodb_real,
        user_id=sample_user_real.id,
        client_id="test-client",
        tenant_id=sample_user_real.tenant_id
    )

    assert removed_count == 1, "Should remove 1 auto-adjustment"

    # Count change_log delete entries after
    delete_logs_after = await mongodb_real["change_log"].count_documents({
        "entity_type": "event",
        "action": "delete"
    })

    assert delete_logs_after > delete_logs_before, (
        "Deletion should be logged to change_log"
    )

    # Verify the specific deletion was logged
    delete_log = await mongodb_real["change_log"].find_one({
        "entity_type": "event",
        "entity_id": auto_event_id,
        "action": "delete"
    })

    assert delete_log is not None, (
        "Should have change_log entry for deleted [auto] adjustment"
    )
    assert "data" in delete_log, "Delete log should contain event snapshot"
    assert delete_log["data"]["is_auto_adjustment"] is True, (
        "Snapshot should show this was an auto-adjustment event"
    )


# ============================================================================
# Unit Tests: Story Events Inclusion
# ============================================================================

@pytest.mark.integration
@pytest.mark.asyncio
async def test_calculate_auto_adjustment_includes_story_events(
    mongodb_real,
    account_repo_real,
    sample_user_real,
    sample_settings_real,
    clean_database_real
):
    """
    Test that story events (non-hypothetical) are included in drift calculation.

    Story events represent real financial events grouped under a story.
    They should be included in drift calculation when:
    - is_hypothetical=False (real events)

    Validates:
    - Story events with story_id and is_hypothetical=False ARE included
    - Drift is calculated correctly including story events
    """
    from api.models import StoryCreate
    from api.repositories.stories import StoryRepository

    # Create account
    account_data = AccountCreate(
        name="StoryEventsTest",
        currency="GBP",
        current_balance=Decimal("1000.00"),
        is_default=False
    )
    account = await account_repo_real.create(
        account_data,
        current_user={"id": str(sample_user_real.id), "tenant_id": str(sample_user_real.tenant_id)},
        client_id=None
    )

    # Create a story
    story_repo = StoryRepository(mongodb_real)
    story_data = StoryCreate(
        name="Test Trip",
        start_date="2025-01-01",
        end_date="2025-12-31",
        funding_mode="projected",
        display_currency="GBP"
    )
    story = await story_repo.create(
        story_data,
        current_user={"id": str(sample_user_real.id), "tenant_id": str(sample_user_real.tenant_id)},
        client_id=None
    )

    event_repo = EventRepository(mongodb_real)

    # Create REAL story event (should be INCLUDED): -300
    story_event = EventCreate(
        event_date="2025-01-15",
        description="Trip expense",
        amount=Decimal("-300.00"),
        account_id=account.id,
        currency="GBP",
        rate_to_base=Decimal("1.0"),
        story_id=story.id,
        is_baseline=False,  # Story event, not baseline
        is_hypothetical=False  # REAL event - should be included
    )
    await event_repo.create(
        story_event,
        current_user={"id": str(sample_user_real.id), "tenant_id": str(sample_user_real.tenant_id)},
        client_id=None
    )

    # Calculate drift
    # Opening balance: +1000
    # Story event (real): -300 (INCLUDED)
    # Projected balance = 1000 - 300 = 700
    # Actual balance: 1000
    # Expected drift: 1000 - 700 = +300
    adjustment = await calculate_auto_adjustment(
        account_id=account.id,
        actual_balance=Decimal("1000.00"),
        db=mongodb_real,
        user_id=sample_user_real.id
    )

    assert adjustment is not None, "Should return adjustment when drift exists"
    assert adjustment.amount == Decimal("300.00"), (
        "Drift should be +300 (1000 actual - 700 projected). "
        "Real story event (-300) should be included in projected balance."
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_calculate_auto_adjustment_excludes_hypothetical_story_events(
    mongodb_real,
    account_repo_real,
    sample_user_real,
    sample_settings_real,
    clean_database_real
):
    """
    Test that hypothetical story events are excluded from drift calculation.

    Hypothetical events represent planned/potential funding that hasn't happened.
    They should NOT affect account reconciliation.

    Validates:
    - Story events with is_hypothetical=True are EXCLUDED
    - Only real events contribute to drift
    """
    from api.models import StoryCreate
    from api.repositories.stories import StoryRepository

    # Create account
    account_data = AccountCreate(
        name="HypotheticalStoryTest",
        currency="GBP",
        current_balance=Decimal("1000.00"),
        is_default=False
    )
    account = await account_repo_real.create(
        account_data,
        current_user={"id": str(sample_user_real.id), "tenant_id": str(sample_user_real.tenant_id)},
        client_id=None
    )

    # Create a story
    story_repo = StoryRepository(mongodb_real)
    story_data = StoryCreate(
        name="Future Project",
        start_date="2025-01-01",
        end_date="2025-12-31",
        funding_mode="fixed",
        funding_amount=Decimal("5000.00"),
        display_currency="GBP"
    )
    story = await story_repo.create(
        story_data,
        current_user={"id": str(sample_user_real.id), "tenant_id": str(sample_user_real.tenant_id)},
        client_id=None
    )

    event_repo = EventRepository(mongodb_real)

    # Create REAL event: +500
    real_event = EventCreate(
        event_date="2025-01-10",
        description="Real income",
        amount=Decimal("500.00"),
        account_id=account.id,
        currency="GBP",
        rate_to_base=Decimal("1.0"),
        is_baseline=True,
        is_hypothetical=False
    )
    await event_repo.create(
        real_event,
        current_user={"id": str(sample_user_real.id), "tenant_id": str(sample_user_real.tenant_id)},
        client_id=None
    )

    # Create HYPOTHETICAL story event: +2000 (should be EXCLUDED)
    hypothetical_event = EventCreate(
        event_date="2025-01-12",
        description="Hypothetical project funding",
        amount=Decimal("2000.00"),
        account_id=account.id,
        currency="GBP",
        rate_to_base=Decimal("1.0"),
        story_id=story.id,
        is_baseline=False,
        is_hypothetical=True  # HYPOTHETICAL - should be excluded
    )
    await event_repo.create(
        hypothetical_event,
        current_user={"id": str(sample_user_real.id), "tenant_id": str(sample_user_real.tenant_id)},
        client_id=None
    )

    # Calculate drift
    # Opening balance: +1000
    # Real event: +500
    # Hypothetical story event: +2000 (EXCLUDED)
    # Projected balance = 1000 + 500 = 1500
    # Actual balance: 1000
    # Expected drift: 1000 - 1500 = -500
    adjustment = await calculate_auto_adjustment(
        account_id=account.id,
        actual_balance=Decimal("1000.00"),
        db=mongodb_real,
        user_id=sample_user_real.id
    )

    assert adjustment is not None, "Should return adjustment when drift exists"
    assert adjustment.amount == Decimal("-500.00"), (
        "Drift should be -500 (1000 actual - 1500 projected). "
        "Hypothetical story event (+2000) should be excluded. "
        "If included, drift would be -2500."
    )
