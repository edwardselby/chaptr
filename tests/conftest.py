"""
Pytest configuration and fixtures for CHAPTR API tests.

Provides test infrastructure for Phase 1.4 endpoint testing:
- MongoDB test database (mongomock for simple tests)
- Real MongoDB (localhost:63000 for complex integration tests)
- FastAPI test client (both mongomock and real MongoDB variants)
- Repository fixtures
- Sample data generators

## Fixture Selection Guide

**Use mongomock fixtures** (mongodb_test, clean_database, async_client):
- Simple CRUD tests (accounts, events, stories, recurring_rules, settings)
- Business logic validation
- Authentication/authorization tests
- Fast unit tests

**Use real MongoDB fixtures** (mongodb_real, clean_database_real, async_client_real):
- Complex integration tests (sync, recurring generation, pruning)
- Tests requiring accurate change_log queries
- Tests with timestamp-based filtering
- Tests that mongomock can't simulate properly

Mark integration tests with `@pytest.mark.integration` decorator.
Run with: `pytest -m integration` or exclude with: `pytest -m "not integration"`
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
    SettingsBase, FundingMode, GoalType, Frequency, UserCreate
)
from api.repositories.accounts import AccountRepository
from api.repositories.stories import StoryRepository
from api.repositories.events import EventRepository
from api.repositories.recurring_rules import RecurringRuleRepository
from api.repositories.settings import SettingsRepository
from api.repositories.users import UserRepository
from api.utils.auth import create_access_token

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
# Real MongoDB Fixtures (for complex integration tests)
# ============================================================================

@pytest_asyncio.fixture(scope="function")
async def mongodb_real():
    """
    Real MongoDB connection for complex integration tests.

    Connects to MongoDB on localhost:63000 (configured instance).
    Uses worker-based database naming for parallel test isolation.

    **Usage**: For tests requiring accurate change_log queries,
    timestamp filtering, or complex async/motor behavior that
    mongomock doesn't simulate properly.

    **Note**: Function-scoped for pytest-asyncio compatibility.
    Database cleanup happens in clean_database_real fixture.
    """
    import os

    # Get worker ID for parallel test isolation
    worker_id = os.environ.get("PYTEST_XDIST_WORKER", "master")
    db_name = f"chaptr_test_integration_{worker_id}"

    # Connect to real MongoDB
    client = AsyncIOMotorClient("mongodb://localhost:63000")
    db = client[db_name]

    yield db

    # Cleanup: Drop entire test database
    await client.drop_database(db_name)
    client.close()


@pytest_asyncio.fixture(scope="function")
async def clean_database_real(mongodb_real):
    """
    Clean real MongoDB database before each test.

    Drops all collections to start with fresh state.
    Ensures test isolation even when using real MongoDB.
    """
    # Drop all collections before test
    collections = await mongodb_real.list_collection_names()
    for collection in collections:
        await mongodb_real[collection].drop()

    yield mongodb_real

    # Cleanup after test
    collections = await mongodb_real.list_collection_names()
    for collection in collections:
        await mongodb_real[collection].drop()


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


@pytest_asyncio.fixture(scope="function")
async def test_app_real(clean_database_real):
    """
    FastAPI test application with real MongoDB.

    Overrides MongoDB.get_database() to use real MongoDB instance.
    Use for integration tests requiring accurate database behavior.
    """
    # Mock MongoDB.get_database to return real test database
    original_get_db = MongoDB.get_database
    MongoDB.get_database = lambda: clean_database_real

    yield app

    # Restore original
    MongoDB.get_database = original_get_db


@pytest_asyncio.fixture(scope="function")
async def async_client_real(test_app_real):
    """
    HTTP client for integration testing with real MongoDB.

    Uses httpx AsyncClient with ASGI transport for FastAPI.
    Use for complex integration tests (sync, recurring, pruning).
    """
    transport = ASGITransport(app=test_app_real)
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


@pytest.fixture
def user_repo(clean_database):
    """UserRepository instance for testing."""
    return UserRepository(clean_database)


# Real MongoDB Repository Fixtures (for integration tests)
@pytest.fixture
def account_repo_real(clean_database_real):
    """AccountRepository instance for integration testing with real MongoDB."""
    return AccountRepository(clean_database_real)


@pytest.fixture
def story_repo_real(clean_database_real):
    """StoryRepository instance for integration testing with real MongoDB."""
    return StoryRepository(clean_database_real)


@pytest.fixture
def event_repo_real(clean_database_real):
    """EventRepository instance for integration testing with real MongoDB."""
    return EventRepository(clean_database_real)


@pytest.fixture
def recurring_rule_repo_real(clean_database_real):
    """RecurringRuleRepository instance for integration testing with real MongoDB."""
    return RecurringRuleRepository(clean_database_real)


@pytest.fixture
def settings_repo_real(clean_database_real):
    """SettingsRepository instance for integration testing with real MongoDB."""
    return SettingsRepository(clean_database_real)


@pytest.fixture
def user_repo_real(clean_database_real):
    """UserRepository instance for integration testing with real MongoDB."""
    return UserRepository(clean_database_real)


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
async def sample_baseline_event(event_repo, sample_account, sample_settings):
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
        rates={},  # Empty rates - tests don't need currency conversion
        server_url="",
        last_backup_date=None,
        version="1.0.0"
    )
    # Settings is singleton - use update_singleton to initialize
    settings = await settings_repo.update_singleton(settings_data)
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


# ============================================================================
# Authentication Fixtures (Phase 1.5)
# ============================================================================

@pytest_asyncio.fixture
async def sample_user(user_repo):
    """
    Pre-created admin user for authentication testing.

    Username: Edward
    Password: TestPass123
    Role: admin
    """
    user_data = UserCreate(
        username="Edward",
        password="TestPass123",  # Meets strength requirements
        role="admin"
    )
    user = await user_repo.create(user_data)
    return user


@pytest_asyncio.fixture
async def sample_user_real(user_repo_real):
    """
    Pre-created admin user for integration testing with real MongoDB.

    Username: Edward
    Password: TestPass123
    Role: admin
    """
    user_data = UserCreate(
        username="Edward",
        password="TestPass123",
        role="admin"
    )
    user = await user_repo_real.create(user_data)
    return user


@pytest_asyncio.fixture
async def sample_settings_real(settings_repo_real):
    """
    Pre-created global settings for integration testing with real MongoDB.

    Creates default settings with GBP base currency.
    Note: Settings is a singleton, so we use update_singleton() to initialize it.
    """
    settings_data = SettingsBase(
        base_currency="GBP",
        default_currency="GBP",
        date_format="DD/MM/YYYY",
        baseline_display_months=1,
        rates={},  # Empty rates - tests don't need currency conversion
        server_url="",
        last_backup_date=None,
        version="1.0.0"
    )
    # Settings is singleton - use update_singleton to initialize
    settings = await settings_repo_real.update_singleton(settings_data)
    return settings


@pytest_asyncio.fixture
async def auth_headers_real(sample_user_real):
    """
    Generate Authorization headers with admin JWT token for real MongoDB integration tests.

    Creates valid JWT token for sample_user_real and returns headers dict
    ready to use with async_client_real requests.

    :Example:

    >>> response = await async_client_real.post("/api/events", headers=auth_headers_real, json=event_data)
    """
    token = create_access_token(
        user_id=sample_user_real.id,
        username=sample_user_real.username,
        role=sample_user_real.role
    )
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def settings_with_rates_real(mongodb_real):
    """
    Create default settings with currency rates for recurring event tests (real MongoDB).

    Required by generate_recurring_events for rate_to_base calculations.
    """
    from api.models import Settings
    from api.utils.db import generate_id, utc_now

    settings = Settings(
        id=generate_id(),
        base_currency="GBP",
        default_currency="GBP",
        rates={"GBP": Decimal("1.0"), "USD": Decimal("1.27"), "EUR": Decimal("1.17")},
        created_at=utc_now(),
        updated_at=utc_now()
    )
    await mongodb_real["settings"].insert_one(settings.model_dump(mode="json"))
    return settings


@pytest_asyncio.fixture
async def sample_regular_user(user_repo):
    """
    Pre-created regular (non-admin) user for authorization testing.

    Username: RegularUser
    Password: TestPass456
    Role: user
    """
    user_data = UserCreate(
        username="RegularUser",
        password="TestPass456",  # Meets strength requirements
        role="user"
    )
    user = await user_repo.create(user_data)
    return user


@pytest_asyncio.fixture
async def auth_headers(sample_user):
    """
    Generate Authorization headers with admin JWT token.

    Creates valid JWT token for sample_user and returns headers dict
    ready to use with async_client requests.

    :Example:

    >>> response = await async_client.post("/api/events", headers=auth_headers, json=event_data)
    """
    token = create_access_token(
        user_id=sample_user.id,
        username=sample_user.username,
        role=sample_user.role
    )
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def regular_user_auth_headers(sample_regular_user):
    """
    Generate Authorization headers with regular user JWT token.

    Used for testing authorization (non-admin access).
    """
    token = create_access_token(
        user_id=sample_regular_user.id,
        username=sample_regular_user.username,
        role=sample_regular_user.role
    )
    return {"Authorization": f"Bearer {token}"}
