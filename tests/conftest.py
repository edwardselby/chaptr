"""
Pytest configuration and fixtures for CHAPTR API tests.

Provides test infrastructure for Phase 1.4 endpoint testing:
- MongoDB test database (mongomock)
- FastAPI test client
- Repository fixtures
- Sample data generators
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from motor.motor_asyncio import AsyncIOMotorClient
from mongomock_motor import AsyncMongoMockClient
from datetime import datetime, date
from decimal import Decimal
from uuid import uuid4

from api.main import app
from api.config import MongoDB
from api.models import (
    AccountCreate, StoryCreate, EventCreate, RecurringRuleCreate,
    SettingsBase, FundingMode, GoalType, Frequency
)
from api.repositories.accounts import AccountRepository
from api.repositories.stories import StoryRepository
from api.repositories.events import EventRepository
from api.repositories.recurring_rules import RecurringRuleRepository
from api.repositories.settings import SettingsRepository

# Enable pytest-asyncio
pytest_plugins = ("pytest_asyncio",)


# ============================================================================
# Database Fixtures
# ============================================================================

@pytest_asyncio.fixture(scope="session")
async def mongodb_test():
    """
    Test MongoDB connection using mongomock for isolated testing.

    Session-scoped to reuse connection across all tests.
    """
    # Create mongomock client (in-memory MongoDB)
    client = AsyncMongoMockClient()
    db = client.chaptr_test

    yield db

    # Cleanup
    client.close()


@pytest_asyncio.fixture(scope="function")
async def clean_database(mongodb_test):
    """
    Clean database before each test to ensure isolation.

    Drops all collections to start with fresh state.
    """
    # Drop all collections before test
    collections = await mongodb_test.list_collection_names()
    for collection in collections:
        await mongodb_test[collection].drop()

    yield mongodb_test

    # Cleanup after test (optional, but ensures clean state)
    collections = await mongodb_test.list_collection_names()
    for collection in collections:
        await mongodb_test[collection].drop()


# ============================================================================
# Application Fixtures
# ============================================================================

@pytest_asyncio.fixture(scope="function")
async def test_app(clean_database):
    """
    FastAPI test application with mocked MongoDB.

    Overrides MongoDB.get_database() to use test database.
    """
    # Mock MongoDB.get_database to return test database
    original_get_db = MongoDB.get_database
    MongoDB.get_database = lambda: clean_database

    yield app

    # Restore original
    MongoDB.get_database = original_get_db


@pytest_asyncio.fixture(scope="function")
async def async_client(test_app):
    """
    HTTP client for endpoint testing.

    Uses httpx AsyncClient with ASGI transport for FastAPI.
    """
    transport = ASGITransport(app=test_app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test"
    ) as client:
        yield client


# ============================================================================
# Repository Fixtures
# ============================================================================

@pytest.fixture
def account_repo(clean_database):
    """AccountRepository instance for testing."""
    return AccountRepository(clean_database)


@pytest.fixture
def story_repo(clean_database):
    """StoryRepository instance for testing."""
    return StoryRepository(clean_database)


@pytest.fixture
def event_repo(clean_database):
    """EventRepository instance for testing."""
    return EventRepository(clean_database)


@pytest.fixture
def recurring_rule_repo(clean_database):
    """RecurringRuleRepository instance for testing."""
    return RecurringRuleRepository(clean_database)


@pytest.fixture
def settings_repo(clean_database):
    """SettingsRepository instance for testing."""
    return SettingsRepository(clean_database)


# ============================================================================
# Sample Data Fixtures
# ============================================================================

@pytest_asyncio.fixture
async def sample_account(account_repo):
    """
    Pre-created test account.

    Creates a default account named "Test Account" with GBP currency.
    """
    account_data = AccountCreate(
        name="Test Account",
        currency="GBP",
        current_balance=Decimal("1000.00"),
        balance_updated_at=datetime.utcnow(),
        is_default=True,
        is_archived=False,
        pending_reconciliation=False
    )
    account = await account_repo.create(account_data)
    return account


@pytest_asyncio.fixture
async def sample_account_usd(account_repo):
    """
    Second test account in USD (not default).

    Useful for testing multi-account scenarios.
    """
    account_data = AccountCreate(
        name="USD Account",
        currency="USD",
        current_balance=Decimal("2000.00"),
        balance_updated_at=datetime.utcnow(),
        is_default=False,
        is_archived=False,
        pending_reconciliation=False
    )
    account = await account_repo.create(account_data)
    return account


@pytest_asyncio.fixture
async def sample_archived_account(account_repo):
    """
    Archived test account.

    Useful for testing archived account filtering.
    """
    account_data = AccountCreate(
        name="Archived Account",
        currency="GBP",
        current_balance=Decimal("0.00"),
        balance_updated_at=datetime.utcnow(),
        is_default=False,
        is_archived=True,
        pending_reconciliation=False
    )
    account = await account_repo.create(account_data)
    return account


@pytest_asyncio.fixture
async def sample_story(story_repo, sample_account):
    """
    Pre-created test story with PROJECTED funding mode.

    Depends on sample_account for default_account_id.
    """
    story_data = StoryCreate(
        name="Test Story",
        start_date=date(2024, 12, 1),
        end_date=date(2025, 1, 31),
        default_account_id=sample_account.id,
        funding_mode=FundingMode.PROJECTED,
        funding_amount=None,
        goal_type=GoalType.NONE,
        goal_amount=None,
        display_currency="GBP"
    )
    story = await story_repo.create(story_data)
    return story


@pytest_asyncio.fixture
async def sample_story_fixed_funding(story_repo, sample_account):
    """
    Test story with FIXED funding mode.

    Includes funding_amount for testing funding mode validation.
    """
    story_data = StoryCreate(
        name="Fixed Funding Story",
        start_date=date(2025, 1, 1),
        end_date=date(2025, 3, 31),
        default_account_id=sample_account.id,
        funding_mode=FundingMode.FIXED,
        funding_amount=Decimal("5000.00"),
        goal_type=GoalType.END_WITH_AT_LEAST,
        goal_amount=Decimal("1000.00"),
        display_currency="GBP"
    )
    story = await story_repo.create(story_data)
    return story


@pytest_asyncio.fixture
async def sample_event(event_repo, sample_account, sample_settings):
    """
    Pre-created test event.

    Depends on sample_account and sample_settings for account_id and rate_to_base.
    """
    event_data = EventCreate(
        event_date=date(2024, 12, 15),
        description="Test Event",
        amount=Decimal("-50.00"),
        currency="GBP",
        account_id=sample_account.id,
        story_id=None,
        is_baseline=True,
        is_hypothetical=False,
        is_auto_adjustment=False
    )
    event = await event_repo.create(event_data)
    return event


@pytest_asyncio.fixture
async def sample_baseline_event(event_repo, sample_account):
    """
    Baseline event (no story_id).

    Useful for testing baseline-only filtering.
    """
    event_data = EventCreate(
        event_date=date(2024, 12, 10),
        description="Baseline Event",
        amount=Decimal("-100.00"),
        currency="GBP",
        account_id=sample_account.id,
        story_id=None,
        is_baseline=True,
        is_hypothetical=False,
        is_auto_adjustment=False
    )
    event = await event_repo.create(event_data)
    return event


@pytest_asyncio.fixture
async def sample_story_event(event_repo, sample_account, sample_story):
    """
    Event associated with a story.

    Useful for testing story filtering and cascade delete.
    """
    event_data = EventCreate(
        event_date=date(2024, 12, 20),
        description="Story Event",
        amount=Decimal("-200.00"),
        currency="GBP",
        account_id=sample_account.id,
        story_id=sample_story.id,
        is_baseline=False,
        is_hypothetical=False,
        is_auto_adjustment=False
    )
    event = await event_repo.create(event_data)
    return event


@pytest_asyncio.fixture
async def sample_recurring_rule(recurring_rule_repo, sample_account):
    """
    Pre-created monthly recurring rule.
    """
    rule_data = RecurringRuleCreate(
        description="Monthly Rent",
        amount=Decimal("-1500.00"),
        currency="GBP",
        account_id=sample_account.id,
        frequency=Frequency.MONTHLY,
        day=28,
        start_date=date(2024, 1, 1),
        end_date=None
    )
    rule = await recurring_rule_repo.create(rule_data)
    return rule


@pytest_asyncio.fixture
async def sample_settings(settings_repo):
    """
    Pre-created global settings.

    Creates default settings with GBP base currency and sample rates.
    Note: Settings is a singleton, so we use update() to initialize it.
    """
    settings_data = SettingsBase(
        base_currency="GBP",
        default_currency="GBP",
        date_format="DD/MM/YYYY",
        baseline_display_months=1,
        rates={
            "USD": Decimal("1.28"),
            "CAD": Decimal("1.75"),
            "EUR": Decimal("1.17")
        },
        server_url="",
        last_backup_date=None,
        version="1.0.0"
    )
    # Settings is singleton - use update to initialize
    settings = await settings_repo.update(settings_data)
    return settings


# ============================================================================
# Utility Fixtures
# ============================================================================

@pytest.fixture
def valid_account_data():
    """
    Valid account creation data for testing.

    Returns dict ready for JSON payload.
    """
    return {
        "name": "Monzo",
        "currency": "GBP",
        "current_balance": 2500.00,
        "balance_updated_at": datetime.utcnow().isoformat() + "Z",
        "is_default": False,
        "is_archived": False,
        "pending_reconciliation": False
    }


@pytest.fixture
def valid_story_data(sample_account):
    """
    Valid story creation data for testing.
    """
    return {
        "name": "Trip to Japan",
        "start_date": "2025-03-01",
        "end_date": "2025-03-31",
        "default_account_id": str(sample_account.id),
        "funding_mode": "projected",
        "funding_amount": None,
        "goal_type": "none",
        "goal_amount": None,
        "display_currency": "GBP"
    }


@pytest.fixture
def valid_event_data(sample_account):
    """
    Valid event creation data for testing.
    """
    return {
        "event_date": "2024-12-25",
        "description": "Christmas Shopping",
        "amount": -320.50,
        "currency": "GBP",
        "account_id": str(sample_account.id),
        "story_id": None,
        "is_baseline": True,
        "is_hypothetical": False,
        "is_auto_adjustment": False
    }
