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
from api.utils.db import utc_now

# Enable pytest-asyncio
pytest_plugins = ("pytest_asyncio",)


# ============================================================================
# Database Fixtures
# ============================================================================

@pytest_asyncio.fixture(scope="function")
async def mongodb_test():
    """
    Test MongoDB connection using mongomock for isolated testing.

    Function-scoped for pytest-asyncio compatibility.
    Mongomock is fast enough that function scope has minimal overhead.
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
async def sample_account(account_repo, sample_user):
    """
    Pre-created test account.

    Creates a default account named "Test Account" with GBP currency.
    Belongs to sample_user's tenant.
    """
    account_data = AccountCreate(
        name="Test Account",
        currency="GBP",
        current_balance=Decimal("1000.00"),
        balance_updated_at=utc_now(),
        is_default=True,
        is_archived=False,
        pending_reconciliation=False
    )
    account = await account_repo.create(
        account_data,
        tenant_id=sample_user.tenant_id,
        current_user={"id": str(sample_user.id), "tenant_id": str(sample_user.tenant_id)}
    )
    return account


@pytest_asyncio.fixture
async def sample_account_usd(account_repo, sample_user):
    """
    Second test account in USD (not default).

    Useful for testing multi-account scenarios.
    Belongs to sample_user's tenant.
    """
    account_data = AccountCreate(
        name="USD Account",
        currency="USD",
        current_balance=Decimal("2000.00"),
        balance_updated_at=utc_now(),
        is_default=False,
        is_archived=False,
        pending_reconciliation=False
    )
    account = await account_repo.create(
        account_data,
        tenant_id=sample_user.tenant_id,
        current_user={"id": str(sample_user.id), "tenant_id": str(sample_user.tenant_id)}
    )
    return account


@pytest_asyncio.fixture
async def sample_archived_account(account_repo, sample_user):
    """
    Archived test account.

    Useful for testing archived account filtering.
    Creates account first (non-archived), then archives it.
    This is realistic - accounts are archived after creation, not created archived.
    Belongs to sample_user's tenant.
    """
    # First create as non-archived (required for opening balance event)
    account_data = AccountCreate(
        name="Archived Account",
        currency="GBP",
        current_balance=Decimal("0.00"),
        balance_updated_at=utc_now(),
        is_default=False,
        is_archived=False,
        pending_reconciliation=False
    )
    account = await account_repo.create(
        account_data,
        tenant_id=sample_user.tenant_id,
        current_user={"id": str(sample_user.id), "tenant_id": str(sample_user.tenant_id)}
    )

    # Then archive the account
    from api.models import AccountUpdate
    archived_account = await account_repo.update(
        account.id,
        AccountUpdate(is_archived=True)
    )
    return archived_account


@pytest_asyncio.fixture
async def sample_story(story_repo, sample_account, sample_user):
    """
    Pre-created test story with PROJECTED funding mode.

    Depends on sample_account for default_account_id.
    Belongs to sample_user's tenant.
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
    story = await story_repo.create(
        story_data,
        tenant_id=sample_user.tenant_id,
        current_user={"id": str(sample_user.id), "tenant_id": str(sample_user.tenant_id)}
    )
    return story


@pytest_asyncio.fixture
async def sample_story_fixed_funding(story_repo, sample_account, sample_user):
    """
    Test story with FIXED funding mode.

    Includes funding_amount for testing funding mode validation.
    Belongs to sample_user's tenant.
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
    story = await story_repo.create(
        story_data,
        tenant_id=sample_user.tenant_id,
        current_user={"id": str(sample_user.id), "tenant_id": str(sample_user.tenant_id)}
    )
    return story


@pytest_asyncio.fixture
async def sample_event(event_repo, sample_account, sample_settings, sample_user):
    """
    Pre-created test event.

    Depends on sample_account and sample_settings for account_id and rate_to_base.
    Belongs to sample_user's tenant.
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
    event = await event_repo.create(
        event_data,
        tenant_id=sample_user.tenant_id,
        current_user={"id": str(sample_user.id), "tenant_id": str(sample_user.tenant_id)}
    )
    return event


@pytest_asyncio.fixture
async def sample_baseline_event(event_repo, sample_account, sample_settings, sample_user):
    """
    Baseline event (no story_id).

    Useful for testing baseline-only filtering.
    Belongs to sample_user's tenant.
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
    event = await event_repo.create(
        event_data,
        tenant_id=sample_user.tenant_id,
        current_user={"id": str(sample_user.id), "tenant_id": str(sample_user.tenant_id)}
    )
    return event


@pytest_asyncio.fixture
async def sample_story_event(event_repo, sample_account, sample_story, sample_user):
    """
    Event associated with a story.

    Useful for testing story filtering and cascade delete.
    Belongs to sample_user's tenant.
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
    event = await event_repo.create(
        event_data,
        tenant_id=sample_user.tenant_id,
        current_user={"id": str(sample_user.id), "tenant_id": str(sample_user.tenant_id)}
    )
    return event


@pytest_asyncio.fixture
async def sample_recurring_rule(recurring_rule_repo, sample_account, sample_user):
    """
    Pre-created monthly recurring rule.
    Belongs to sample_user's tenant.
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
    rule = await recurring_rule_repo.create(
        rule_data,
        tenant_id=sample_user.tenant_id,
        current_user={"id": str(sample_user.id), "tenant_id": str(sample_user.tenant_id)}
    )
    return rule


@pytest_asyncio.fixture
async def sample_settings(settings_repo, sample_user):
    """
    Pre-created per-tenant settings.

    Creates default settings with GBP base currency for sample_user's tenant.
    Note: Settings is now per-tenant, using get_or_create_for_tenant.
    """
    # Get or create settings for the tenant
    settings = await settings_repo.get_or_create_for_tenant(sample_user.tenant_id)
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
        "balance_updated_at": utc_now().isoformat(),
        "is_default": True,
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
    Pre-created super_admin user for authentication testing.

    Username: Edward
    Password: TestPass123
    Role: super_admin

    Note: Created without a creator, so acts as "first user" (bootstrap).
    This user is the tenant anchor (tenant_id = user_id).
    """
    user_data = UserCreate(
        username="Edward",
        password="TestPass123",  # Meets strength requirements
        role="super_admin"  # Changed from admin to super_admin for multi-tenancy
    )
    user = await user_repo.create(user_data)  # No creator = bootstrap mode
    return user


@pytest_asyncio.fixture
async def sample_user_real(user_repo_real):
    """
    Pre-created super_admin user for integration testing with real MongoDB.

    Username: Edward
    Password: TestPass123
    Role: super_admin

    Note: Created without a creator, so acts as "first user" (bootstrap).
    This user is the tenant anchor (tenant_id = user_id).
    """
    user_data = UserCreate(
        username="Edward",
        password="TestPass123",
        role="super_admin"  # Changed from admin to super_admin for multi-tenancy
    )
    user = await user_repo_real.create(user_data)  # No creator = bootstrap mode
    return user


@pytest_asyncio.fixture
async def sample_settings_real(settings_repo_real, sample_user_real):
    """
    Pre-created per-tenant settings for integration testing with real MongoDB.

    Creates default settings with GBP base currency for sample_user_real's tenant.
    Note: Settings is now per-tenant, using get_or_create_for_tenant.
    """
    # Get or create settings for the tenant
    settings = await settings_repo_real.get_or_create_for_tenant(sample_user_real.tenant_id)
    return settings


@pytest_asyncio.fixture
async def auth_headers_real(sample_user_real):
    """
    Generate Authorization headers with super_admin JWT token for real MongoDB integration tests.

    Creates valid JWT token for sample_user_real and returns headers dict
    ready to use with async_client_real requests.

    :Example:

    >>> response = await async_client_real.post("/api/events", headers=auth_headers_real, json=event_data)
    """
    token = create_access_token(
        user_id=sample_user_real.id,
        username=sample_user_real.username,
        role=sample_user_real.role,
        tenant_id=sample_user_real.tenant_id  # Include tenant_id for multi-tenancy
    )
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def settings_with_rates_real(mongodb_real, sample_user_real):
    """
    Create default settings with currency rates for recurring event tests (real MongoDB).

    Required by generate_recurring_events for rate_to_base calculations.
    Belongs to sample_user_real's tenant.
    """
    from api.models import Settings
    from api.utils.db import generate_id, utc_now

    settings = Settings(
        id=generate_id(),
        base_currency="GBP",
        default_currency="GBP",
        rates={"GBP": Decimal("1.0"), "USD": Decimal("1.27"), "EUR": Decimal("1.17")},
        tenant_id=sample_user_real.tenant_id,  # Include tenant_id for multi-tenancy
        created_at=utc_now(),
        updated_at=utc_now()
    )
    await mongodb_real["settings"].insert_one(settings.model_dump(mode="json"))
    return settings


@pytest_asyncio.fixture
async def sample_account_with_user(account_repo_real, sample_user_real):
    """
    Pre-created account for integration testing with real MongoDB and user context.

    Created with sample_user_real as the owner (created_by field).
    Used for sync tests that need accounts owned by a specific user.
    Belongs to sample_user_real's tenant.
    """
    from api.models import AccountCreate

    account_data = AccountCreate(
        name="Test Account",
        currency="GBP",
        current_balance=Decimal("1000.00"),
        is_default=True
    )
    account = await account_repo_real.create(
        account_data,
        tenant_id=sample_user_real.tenant_id,  # Include tenant_id for multi-tenancy
        current_user={"id": str(sample_user_real.id), "tenant_id": str(sample_user_real.tenant_id)},
        client_id=None  # No client_id = created via REST API
    )
    return account


@pytest_asyncio.fixture
async def sample_story_with_user(story_repo_real, sample_user_real, sample_account_with_user):
    """
    Pre-created story for integration testing with real MongoDB and user context.

    Created with sample_user_real as the owner (created_by field).
    Used for sync tests that need stories owned by a specific user.
    Belongs to sample_user_real's tenant.
    """
    from api.models import StoryCreate

    story_data = StoryCreate(
        name="Test Story",
        funding_mode="projected",
        start_date="2025-01-01",
        display_currency="GBP"  # Required field for StoryCreate
    )
    story = await story_repo_real.create(
        story_data,
        tenant_id=sample_user_real.tenant_id,  # Include tenant_id for multi-tenancy
        current_user={"id": str(sample_user_real.id), "tenant_id": str(sample_user_real.tenant_id)},
        client_id=None  # No client_id = created via REST API
    )
    return story


@pytest_asyncio.fixture
async def sample_event_with_user(event_repo_real, sample_account_with_user, sample_story_with_user, sample_user_real, sample_settings_real):
    """
    Pre-created event for integration testing with real MongoDB and user context.

    Created with sample_user_real as the owner (created_by field).
    Used for sync tests that need events owned by a specific user.
    Requires sample_settings_real for currency rate lookup.
    Belongs to sample_user_real's tenant.
    """
    from api.models import EventCreate
    from decimal import Decimal
    from datetime import date

    event_data = EventCreate(
        event_date=date(2025, 1, 15),
        description="Test Event",
        amount=Decimal("-50.00"),
        currency="GBP",
        account_id=sample_account_with_user.id,
        story_id=sample_story_with_user.id
    )
    event = await event_repo_real.create(
        event_data,
        tenant_id=sample_user_real.tenant_id,  # Include tenant_id for multi-tenancy
        current_user={"id": str(sample_user_real.id), "tenant_id": str(sample_user_real.tenant_id)},
        client_id=None  # No client_id = created via REST API, not sync
    )
    return event


@pytest_asyncio.fixture
async def sample_regular_user(user_repo, sample_user):
    """
    Pre-created regular (non-admin) user for authorization testing.

    Username: RegularUser
    Password: TestPass456
    Role: user

    Note: Created by sample_user (super_admin), inherits same tenant_id.
    """
    user_data = UserCreate(
        username="RegularUser",
        password="TestPass456",  # Meets strength requirements
        role="user"
    )
    # Create with sample_user as creator - inherits their tenant_id
    creator = {
        "id": str(sample_user.id),
        "role": sample_user.role,
        "tenant_id": str(sample_user.tenant_id)
    }
    user = await user_repo.create(user_data, creator=creator)
    return user


@pytest_asyncio.fixture
async def auth_headers(sample_user):
    """
    Generate Authorization headers with super_admin JWT token.

    Creates valid JWT token for sample_user and returns headers dict
    ready to use with async_client requests.

    :Example:

    >>> response = await async_client.post("/api/events", headers=auth_headers, json=event_data)
    """
    token = create_access_token(
        user_id=sample_user.id,
        username=sample_user.username,
        role=sample_user.role,
        tenant_id=sample_user.tenant_id  # Include tenant_id for multi-tenancy
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
        role=sample_regular_user.role,
        tenant_id=sample_regular_user.tenant_id  # Include tenant_id for multi-tenancy
    )
    return {"Authorization": f"Bearer {token}"}
