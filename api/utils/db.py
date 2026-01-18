"""
Database utility functions for CHAPTR API.

Provides helper functions for common database operations including
UUID conversion, timestamp generation, account resolution, and
currency rate locking.
"""

from uuid import UUID, uuid4
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, Any
from motor.motor_asyncio import AsyncIOMotorCollection

from api.utils.errors import ResourceNotFoundError, ValidationError


def to_uuid(value: str | UUID) -> UUID:
    """
    Convert string to UUID.

    Handles both UUID objects (pass-through) and string UUIDs.

    :param value: UUID string or UUID object
    :type value: str | UUID
    :return: UUID object
    :rtype: UUID
    :raises ValueError: If string is not valid UUID format

    :Example:

    >>> to_uuid("123e4567-e89b-12d3-a456-426614174000")
    UUID('123e4567-e89b-12d3-a456-426614174000')
    """
    if isinstance(value, UUID):
        return value
    return UUID(value)


def to_str(value: UUID | str) -> str:
    """
    Convert UUID to string.

    Handles both UUID objects and string UUIDs (pass-through).

    :param value: UUID object or string
    :type value: UUID | str
    :return: UUID as string
    :rtype: str

    :Example:

    >>> uuid_obj = UUID('123e4567-e89b-12d3-a456-426614174000')
    >>> to_str(uuid_obj)
    '123e4567-e89b-12d3-a456-426614174000'
    """
    if isinstance(value, str):
        return value
    return str(value)


def utc_now() -> datetime:
    """
    Get current UTC datetime with timezone info.

    Always returns timezone-aware datetime in UTC.
    Used for created_at and updated_at timestamps.

    :return: Current UTC datetime with timezone
    :rtype: datetime

    :Example:

    >>> now = utc_now()
    >>> now.tzinfo
    datetime.timezone.utc
    """
    return datetime.now(timezone.utc)


def generate_id() -> UUID:
    """
    Generate new UUID v4.

    Used for creating unique identifiers for all entities.

    :return: Random UUID v4
    :rtype: UUID

    :Example:

    >>> account_id = generate_id()
    >>> isinstance(account_id, UUID)
    True
    """
    return uuid4()


async def get_or_404(
    collection: AsyncIOMotorCollection,
    resource_id: UUID | str,
    resource_name: str,
    tenant_id: Optional[UUID] = None
) -> dict[str, Any]:
    """
    Fetch document by ID or raise 404 with tenant isolation.

    Queries MongoDB collection for document with given ID.
    Raises ResourceNotFoundError if document doesn't exist or belongs to different tenant.

    Multi-tenancy: If tenant_id is provided, document must belong to that tenant.
    This prevents cross-tenant data access.

    :param collection: MongoDB collection to query
    :type collection: AsyncIOMotorCollection
    :param resource_id: UUID or string ID of resource
    :type resource_id: UUID | str
    :param resource_name: Human-readable name for error message (e.g., "Account")
    :type resource_name: str
    :param tenant_id: Tenant UUID for multi-tenancy isolation (optional)
    :type tenant_id: Optional[UUID]
    :return: Document dictionary from MongoDB
    :rtype: dict[str, Any]
    :raises ResourceNotFoundError: If document not found or belongs to different tenant

    :Example:

    >>> doc = await get_or_404(db['accounts'], account_id, "Account", tenant_id=tenant_id)
    >>> # Raises ResourceNotFoundError("Account not found") if missing or wrong tenant
    """
    id_str = to_str(resource_id)
    query = {"id": id_str}

    # Multi-tenancy: Add tenant filter if provided
    if tenant_id:
        query["tenant_id"] = str(tenant_id)

    doc = await collection.find_one(query)

    if not doc:
        raise ResourceNotFoundError(f"{resource_name} not found")

    return doc


async def resolve_account_id(
    db,
    story_id: Optional[UUID] = None,
    explicit_account_id: Optional[UUID] = None,
    tenant_id: Optional[UUID] = None
) -> UUID:
    """
    Resolve account_id using 3-level hierarchy with tenant isolation.

    Critical business logic for event creation.
    Resolves which account an event should be assigned to.

    Resolution Hierarchy:
    1. User explicit account_id → use it (verify exists, not archived, belongs to tenant)
    2. Story's default_account_id → use it (verify belongs to tenant)
    3. Tenant default account (is_default=true) → use it (fallback)
    4. No account found → ERROR

    :param db: MongoDB database instance
    :type db: AsyncIOMotorDatabase
    :param story_id: Optional story ID to check for default account
    :type story_id: Optional[UUID]
    :param explicit_account_id: Optional explicit account ID from request
    :type explicit_account_id: Optional[UUID]
    :param tenant_id: Tenant UUID for multi-tenancy isolation
    :type tenant_id: Optional[UUID]
    :return: Resolved account UUID
    :rtype: UUID
    :raises ValidationError: If no account could be resolved
    :raises ValidationError: If explicit account not found or archived

    :Example:

    >>> # Event with explicit account_id
    >>> account_id = await resolve_account_id(db, explicit_account_id=acc_id, tenant_id=tenant_id)
    >>>
    >>> # Event in story with default account
    >>> account_id = await resolve_account_id(db, story_id=story_id, tenant_id=tenant_id)
    >>>
    >>> # Event with no context (uses tenant default)
    >>> account_id = await resolve_account_id(db, tenant_id=tenant_id)
    """
    # Build tenant filter for all queries
    tenant_filter = {"tenant_id": str(tenant_id)} if tenant_id else {}

    # Level 1: Explicit account_id provided
    if explicit_account_id:
        query = {
            "id": to_str(explicit_account_id),
            "is_archived": False,
            **tenant_filter
        }
        account = await db['accounts'].find_one(query)
        if account:
            return explicit_account_id
        raise ValidationError(
            f"Account {explicit_account_id} not found or archived"
        )

    # Level 2: Story's default_account_id
    if story_id:
        story_query = {"id": to_str(story_id), **tenant_filter}
        story = await db['stories'].find_one(story_query)
        if story and story.get('default_account_id'):
            account_id = UUID(story['default_account_id'])
            # Verify account exists, not archived, and belongs to tenant
            account_query = {
                "id": to_str(account_id),
                "is_archived": False,
                **tenant_filter
            }
            account = await db['accounts'].find_one(account_query)
            if account:
                return account_id
            # Note: If story's default_account_id is archived, we fall through
            # to global default (Level 3) rather than failing. This allows events
            # to continue being created even if the story's account is archived.

    # Level 3: Tenant default account
    default_query = {
        "is_default": True,
        "is_archived": False,
        **tenant_filter
    }
    default = await db['accounts'].find_one(default_query)
    if default:
        return UUID(default['id'])

    # Level 4: No account available
    raise ValidationError(
        "No account available for event. Create an account first."
    )


async def get_rate_to_base(db, currency: str, tenant_id: Optional[UUID] = None) -> Decimal:
    """
    Get conversion rate to base currency from tenant settings.

    Locks the current conversion rate for an event.
    Rate is stored permanently on the event and never auto-updates.

    :param db: MongoDB database instance
    :type db: AsyncIOMotorDatabase
    :param currency: Currency code (e.g., "GBP", "CAD", "USD")
    :type currency: str
    :param tenant_id: Tenant UUID for multi-tenancy isolation
    :type tenant_id: Optional[UUID]
    :return: Conversion rate to base currency
    :rtype: Decimal
    :raises ValidationError: If settings not found or rate missing

    :Example:

    >>> # Lock CAD to GBP rate at event creation
    >>> rate = await get_rate_to_base(db, "CAD", tenant_id=tenant_id)
    >>> # Returns Decimal("0.58") if that's the current CAD rate
    """
    # Query settings with tenant filter
    query = {"tenant_id": str(tenant_id)} if tenant_id else {}
    settings = await db['settings'].find_one(query)

    if not settings:
        raise ValidationError("Settings not configured. Initialize settings first.")

    # Base currency has rate of 1.0
    base_currency = settings.get('base_currency', 'GBP')
    if currency == base_currency:
        return Decimal("1.0")

    # Get rate from settings
    rates = settings.get('rates', {})
    rate = rates.get(currency)

    if not rate:
        raise ValidationError(
            f"Conversion rate for {currency} not found in settings. "
            f"Add rate in settings or use base currency ({base_currency})."
        )

    return Decimal(str(rate))
