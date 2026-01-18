"""
Base repository class for CHAPTR API.

Provides generic CRUD operations for all entity repositories
using the Repository Pattern for separation of concerns.
"""

from typing import Generic, TypeVar, Type, Optional, Dict, Any
from uuid import UUID
from motor.motor_asyncio import AsyncIOMotorDatabase

from api.utils.db import generate_id, utc_now, get_or_404, to_str
from api.utils.errors import ResourceNotFoundError

# Generic type variable for entity model
T = TypeVar('T')


class ChangeLogMixin:
    """
    Automatic change logging for sync support.

    Provides log_change() method to record all mutations (create/update/delete)
    to the change_log collection for multi-device sync distribution.

    Change log entries include full entity snapshots (not deltas) to enable
    conflict detection and resolution during sync.
    """

    async def log_change(
        self,
        entity_type: str,
        entity_id: UUID,
        action: str,  # create, update, delete
        data: Optional[dict],
        user_id: Optional[UUID] = None,
        client_id: Optional[str] = None,
        tenant_id: Optional[UUID] = None
    ) -> None:
        """
        Record change to change_log collection for sync distribution.

        Automatically called after all mutation operations (create/update/delete)
        to enable multi-device sync. Stores full entity snapshot for conflict
        detection based on updated_at comparison.

        :param entity_type: Type of entity (event, story, account, etc.)
        :type entity_type: str
        :param entity_id: UUID of the affected entity
        :type entity_id: UUID
        :param action: Type of change (create, update, delete)
        :type action: str
        :param data: Full entity snapshot as dict (None for delete)
        :type data: Optional[dict]
        :param user_id: User who made the change (from JWT token)
        :type user_id: Optional[UUID]
        :param client_id: Device/client that made the change (None for direct API)
        :type client_id: Optional[str]
        :param tenant_id: Tenant identifier for multi-tenancy isolation
        :type tenant_id: Optional[UUID]
        :return: None
        :rtype: None

        :Example:

        >>> # After creating an event
        >>> await self.log_change(
        ...     "event",
        ...     event.id,
        ...     "create",
        ...     event.model_dump(mode="json"),
        ...     user_id=UUID(current_user["id"]),
        ...     client_id=None,  # Direct API call
        ...     tenant_id=UUID(current_user["tenant_id"])
        ... )
        """
        # Build entry, omitting None values per MongoDB best practice
        entry = {
            "id": str(generate_id()),
            "entity_type": entity_type,
            "entity_id": str(entity_id),
            "action": action,
            "data": data,
            "changed_at": utc_now().isoformat()
        }

        # Only include non-None values for user, client, and tenant
        if user_id is not None:
            entry["changed_by_user"] = str(user_id)
        if client_id is not None:
            entry["changed_by_client"] = client_id
        if tenant_id is not None:
            entry["tenant_id"] = str(tenant_id)

        await self.db["change_log"].insert_one(entry)


class BaseRepository(Generic[T], ChangeLogMixin):
    """
    Generic base repository providing common CRUD operations.

    Implements the Repository Pattern to separate data access logic
    from business logic and HTTP handling.

    :param db: MongoDB database instance
    :type db: AsyncIOMotorDatabase
    :param collection_name: Name of MongoDB collection
    :type collection_name: str
    :param model_class: Pydantic model class for this entity
    :type model_class: Type[T]

    :Example:

    >>> class AccountRepository(BaseRepository[Account]):
    ...     def __init__(self, db):
    ...         super().__init__(db, "accounts", Account)
    ...
    ...     async def create(self, data: AccountCreate) -> Account:
    ...         # Custom create logic with business rules
    ...         pass
    """

    def __init__(
        self,
        db: AsyncIOMotorDatabase,
        collection_name: str,
        model_class: Type[T]
    ):
        """
        Initialize base repository.

        :param db: MongoDB database instance
        :type db: AsyncIOMotorDatabase
        :param collection_name: Collection name in MongoDB
        :type collection_name: str
        :param model_class: Pydantic model class
        :type model_class: Type[T]
        """
        self.db = db
        self.collection = db[collection_name]
        self.model_class = model_class
        self.collection_name = collection_name

    def _get_user_id(self, current_user: Optional[Dict[str, Any]]) -> Optional[UUID]:
        """
        Extract user UUID from current_user dict.

        Helper method to reduce code duplication across repositories.
        Repositories call this instead of repeating the extraction logic.

        :param current_user: Current user dict from JWT token (contains 'id' key)
        :type current_user: Optional[Dict[str, Any]]
        :return: User UUID or None
        :rtype: Optional[UUID]

        :Example:

        >>> user_id = self._get_user_id(current_user)
        >>> await self.log_change("event", event.id, "create", data, user_id, client_id)
        """
        return UUID(current_user["id"]) if current_user else None

    def _get_tenant_id(self, current_user: Optional[Dict[str, Any]]) -> Optional[UUID]:
        """
        Extract tenant UUID from current_user dict.

        Helper method for multi-tenancy support. Repositories call this
        to get the tenant_id for filtering and logging.

        :param current_user: Current user dict from JWT token (contains 'tenant_id' key)
        :type current_user: Optional[Dict[str, Any]]
        :return: Tenant UUID or None
        :rtype: Optional[UUID]

        :Example:

        >>> tenant_id = self._get_tenant_id(current_user)
        >>> await self.list_for_tenant(tenant_id)
        """
        if current_user and current_user.get("tenant_id"):
            return UUID(current_user["tenant_id"])
        return None

    def _add_tenant_filter(self, filters: Optional[dict], tenant_id: UUID) -> dict:
        """
        Add tenant filter to query for multi-tenancy isolation.

        :param filters: Existing MongoDB filter query
        :type filters: Optional[dict]
        :param tenant_id: Tenant identifier to filter by
        :type tenant_id: UUID
        :return: Filters dict with tenant_id added
        :rtype: dict

        :Example:

        >>> query = self._add_tenant_filter({"is_archived": False}, tenant_id)
        >>> # query = {"is_archived": False, "tenant_id": "uuid-string"}
        """
        filters = filters.copy() if filters else {}
        filters["tenant_id"] = str(tenant_id)
        return filters

    async def list_for_tenant(
        self,
        tenant_id: UUID,
        filters: Optional[dict] = None,
        skip: int = 0,
        limit: int = 100,
        sort: Optional[list[tuple[str, int]]] = None
    ) -> list[T]:
        """
        List entities filtered by tenant for multi-tenancy isolation.

        :param tenant_id: Tenant identifier to filter by
        :type tenant_id: UUID
        :param filters: Additional MongoDB filter query
        :type filters: Optional[dict]
        :param skip: Number of documents to skip (pagination)
        :type skip: int
        :param limit: Maximum documents to return
        :type limit: int
        :param sort: List of (field, direction) tuples for sorting
        :type sort: Optional[list[tuple[str, int]]]
        :return: List of entity model instances belonging to tenant
        :rtype: list[T]

        :Example:

        >>> accounts = await repo.list_for_tenant(
        ...     tenant_id=UUID(current_user["tenant_id"]),
        ...     filters={"is_archived": False}
        ... )
        """
        query = self._add_tenant_filter(filters, tenant_id)
        return await self.list(filters=query, skip=skip, limit=limit, sort=sort)

    async def get_for_tenant(self, resource_id: UUID, tenant_id: UUID) -> T:
        """
        Get single entity by ID only if it belongs to the specified tenant.

        :param resource_id: UUID of resource to fetch
        :type resource_id: UUID
        :param tenant_id: Tenant identifier to verify ownership
        :type tenant_id: UUID
        :return: Entity model instance
        :rtype: T
        :raises ResourceNotFoundError: If entity not found or doesn't belong to tenant

        :Example:

        >>> account = await repo.get_for_tenant(account_id, tenant_id)
        """
        doc = await self.collection.find_one({
            "id": str(resource_id),
            "tenant_id": str(tenant_id)
        })
        if not doc:
            raise ResourceNotFoundError(f"{self.model_class.__name__} not found")
        return self.model_class(**doc)

    async def count_for_tenant(self, tenant_id: UUID, filters: Optional[dict] = None) -> int:
        """
        Count documents matching filters within a tenant.

        :param tenant_id: Tenant identifier to filter by
        :type tenant_id: UUID
        :param filters: Additional MongoDB filter query
        :type filters: Optional[dict]
        :return: Count of matching documents
        :rtype: int

        :Example:

        >>> count = await repo.count_for_tenant(tenant_id, {"is_archived": False})
        """
        query = self._add_tenant_filter(filters, tenant_id)
        return await self.count(filters=query)

    async def get(self, resource_id: UUID) -> T:
        """
        Get single entity by ID.

        :param resource_id: UUID of resource to fetch
        :type resource_id: UUID
        :return: Entity model instance
        :rtype: T
        :raises ResourceNotFoundError: If entity not found

        :Example:

        >>> account = await account_repo.get(account_id)
        """
        doc = await get_or_404(
            self.collection,
            resource_id,
            self.model_class.__name__
        )
        return self.model_class(**doc)

    async def list(
        self,
        filters: Optional[dict] = None,
        skip: int = 0,
        limit: int = 100,
        sort: Optional[list[tuple[str, int]]] = None
    ) -> list[T]:
        """
        List entities with optional filtering and pagination.

        :param filters: MongoDB filter query (default: {})
        :type filters: Optional[dict]
        :param skip: Number of documents to skip (pagination)
        :type skip: int
        :param limit: Maximum documents to return (default: 100)
        :type limit: int
        :param sort: List of (field, direction) tuples for sorting
        :type sort: Optional[list[tuple[str, int]]]
        :return: List of entity model instances
        :rtype: list[T]

        :Example:

        >>> # List non-archived accounts
        >>> accounts = await account_repo.list(
        ...     filters={"is_archived": False},
        ...     limit=50
        ... )
        >>>
        >>> # List events with sorting
        >>> events = await event_repo.list(
        ...     filters={"story_id": str(story_id)},
        ...     sort=[("event_date", 1), ("amount", -1)]
        ... )
        """
        query = filters or {}
        cursor = self.collection.find(query).skip(skip).limit(limit)

        if sort:
            cursor = cursor.sort(sort)

        docs = await cursor.to_list(length=None)
        return [self.model_class(**doc) for doc in docs]

    async def delete(
        self,
        resource_id: UUID,
        current_user: Optional[dict] = None,
        client_id: Optional[str] = None,
        tenant_id: Optional[UUID] = None
    ) -> bool:
        """
        Hard delete entity by ID with change logging.

        Permanently removes document from MongoDB and logs the change
        to change_log for sync protocol.

        Multi-tenancy: If tenant_id is provided, verifies entity belongs
        to the tenant before deletion (defense-in-depth).

        :param resource_id: UUID of resource to delete
        :type resource_id: UUID
        :param current_user: Current authenticated user (optional)
        :type current_user: Optional[dict]
        :param client_id: Client identifier for sync protocol (optional)
        :type client_id: Optional[str]
        :param tenant_id: Tenant UUID for multi-tenancy verification (optional)
        :type tenant_id: Optional[UUID]
        :return: True if deleted successfully
        :rtype: bool
        :raises ResourceNotFoundError: If entity not found or doesn't belong to tenant

        :Example:

        >>> await story_repo.delete(story_id, current_user=user, client_id="client-a", tenant_id=tenant_id)
        True
        """
        # Build delete query with optional tenant filter
        delete_query = {"id": to_str(resource_id)}
        if tenant_id:
            delete_query["tenant_id"] = str(tenant_id)

        result = await self.collection.delete_one(delete_query)

        if result.deleted_count == 0:
            raise ResourceNotFoundError(
                f"{self.model_class.__name__} not found"
            )

        # Log change for sync protocol with tenant_id
        await self.log_change(
            self.collection_name,
            resource_id,
            "delete",
            None,  # data=None for deletes (entity no longer exists)
            self._get_user_id(current_user),
            client_id,
            self._get_tenant_id(current_user) if current_user else tenant_id
        )

        return True

    async def count(self, filters: Optional[dict] = None) -> int:
        """
        Count documents matching filters.

        :param filters: MongoDB filter query (default: {})
        :type filters: Optional[dict]
        :return: Count of matching documents
        :rtype: int

        :Example:

        >>> # Count active accounts
        >>> count = await account_repo.count({"is_archived": False})
        """
        query = filters or {}
        return await self.collection.count_documents(query)

    async def exists(self, resource_id: UUID) -> bool:
        """
        Check if entity exists by ID.

        :param resource_id: UUID of resource to check
        :type resource_id: UUID
        :return: True if exists, False otherwise
        :rtype: bool

        :Example:

        >>> if await account_repo.exists(account_id):
        ...     print("Account exists")
        """
        doc = await self.collection.find_one({"id": to_str(resource_id)})
        return doc is not None
