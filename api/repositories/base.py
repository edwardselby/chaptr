"""
Base repository class for CHAPTR API.

Provides generic CRUD operations for all entity repositories
using the Repository Pattern for separation of concerns.
"""

from typing import Generic, TypeVar, Type, Optional
from uuid import UUID
from motor.motor_asyncio import AsyncIOMotorDatabase

from api.utils.db import generate_id, utc_now, get_or_404, to_str
from api.utils.errors import ResourceNotFoundError

# Generic type variable for entity model
T = TypeVar('T')


class BaseRepository(Generic[T]):
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

    async def delete(self, resource_id: UUID) -> bool:
        """
        Hard delete entity by ID.

        Permanently removes document from MongoDB.
        Use with caution - for soft deletes, override in subclass.

        :param resource_id: UUID of resource to delete
        :type resource_id: UUID
        :return: True if deleted successfully
        :rtype: bool
        :raises ResourceNotFoundError: If entity not found

        :Example:

        >>> await story_repo.delete(story_id)
        True
        """
        result = await self.collection.delete_one({"id": to_str(resource_id)})

        if result.deleted_count == 0:
            raise ResourceNotFoundError(
                f"{self.model_class.__name__} not found"
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
