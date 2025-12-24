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
        client_id: Optional[str] = None
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
        ...     client_id=None  # Direct API call
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

        # Only include non-None values for user and client
        if user_id is not None:
            entry["changed_by_user"] = str(user_id)
        if client_id is not None:
            entry["changed_by_client"] = client_id

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
        client_id: Optional[str] = None
    ) -> bool:
        """
        Hard delete entity by ID with change logging.

        Permanently removes document from MongoDB and logs the change
        to change_log for sync protocol.

        :param resource_id: UUID of resource to delete
        :type resource_id: UUID
        :param current_user: Current authenticated user (optional)
        :type current_user: Optional[dict]
        :param client_id: Client identifier for sync protocol (optional)
        :type client_id: Optional[str]
        :return: True if deleted successfully
        :rtype: bool
        :raises ResourceNotFoundError: If entity not found

        :Example:

        >>> await story_repo.delete(story_id, current_user=user, client_id="client-a")
        True
        """
        result = await self.collection.delete_one({"id": to_str(resource_id)})

        if result.deleted_count == 0:
            raise ResourceNotFoundError(
                f"{self.model_class.__name__} not found"
            )

        # Log change for sync protocol
        await self.log_change(
            self.collection_name,
            resource_id,
            "delete",
            None,  # data=None for deletes (entity no longer exists)
            self._get_user_id(current_user),
            client_id
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
