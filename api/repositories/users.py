"""
User repository for CHAPTR API.

Provides data access layer for user management with authentication logic.
Handles user CRUD operations, username uniqueness, password hashing,
and admin deletion protection.
"""

from typing import Optional
from uuid import UUID

from api.models import User, UserCreate
from api.repositories.base import BaseRepository
from api.utils.auth import hash_password, verify_password
from api.utils.db import generate_id, utc_now
from api.utils.errors import ResourceConflictError, ResourceNotFoundError


class UserRepository(BaseRepository[User]):
    """
    Repository for managing users with authentication logic.

    Extends BaseRepository with custom methods for:
    - Username uniqueness enforcement
    - Password hashing during creation
    - Authentication (username/password verification)
    - Admin deletion protection (cannot delete last admin)

    :Example:

    >>> repo = UserRepository(db)
    >>> user = await repo.create(UserCreate(
    ...     username="Edward",
    ...     password="securepassword123",
    ...     role="admin"
    ... ))
    >>> authenticated = await repo.authenticate("Edward", "securepassword123")
    >>> authenticated.id == user.id
    True
    """

    def __init__(self, db):
        """
        Initialize UserRepository.

        :param db: Motor AsyncIOMotorDatabase instance
        :type db: AsyncIOMotorDatabase
        """
        super().__init__(db, "users", User)

    async def create(self, data: UserCreate) -> User:
        """
        Create a new user with password hashing and username uniqueness check.

        Business Logic:
        - Username must be unique across all users
        - Password is hashed using bcrypt before storage
        - Never stores plain text passwords
        - Auto-generates UUID and timestamps

        :param data: User creation data with plain text password
        :type data: UserCreate
        :return: Created user with hashed password
        :rtype: User
        :raises ResourceConflictError: If username already exists

        :Example:

        >>> user_data = UserCreate(
        ...     username="Edward",
        ...     password="password123",
        ...     role="admin"
        ... )
        >>> user = await repo.create(user_data)
        >>> user.password_hash.startswith("$2b$")  # Bcrypt hash
        True
        """
        # Check username uniqueness
        existing = await self.get_by_username(data.username)
        if existing:
            raise ResourceConflictError(
                f"Username '{data.username}' already exists"
            )

        # Hash password
        password_hash = hash_password(data.password)

        # Create user with hashed password
        user = User(
            id=generate_id(),
            username=data.username,
            role=data.role,
            password_hash=password_hash,
            created_at=utc_now(),
            updated_at=utc_now()
        )

        # Insert into database
        await self.collection.insert_one(user.model_dump(mode="json"))

        return user

    async def get_by_username(self, username: str) -> Optional[User]:
        """
        Get user by username (case-sensitive).

        Used for login lookups and username uniqueness checks.

        :param username: Username to search for
        :type username: str
        :return: User if found, None otherwise
        :rtype: Optional[User]

        :Example:

        >>> user = await repo.get_by_username("Edward")
        >>> if user:
        ...     print(f"Found user: {user.username}")
        """
        doc = await self.collection.find_one({"username": username})
        return User(**doc) if doc else None

    async def authenticate(
        self,
        username: str,
        password: str
    ) -> Optional[User]:
        """
        Authenticate user by username and password.

        Verifies:
        1. User exists
        2. Password matches hashed password

        Uses constant-time comparison to prevent timing attacks.

        :param username: Username for authentication
        :type username: str
        :param password: Plain text password
        :type password: str
        :return: User if authentication successful, None otherwise
        :rtype: Optional[User]

        :Example:

        >>> # Successful authentication
        >>> user = await repo.authenticate("Edward", "correctpassword")
        >>> user.username
        'Edward'
        >>>
        >>> # Failed authentication (wrong password)
        >>> user = await repo.authenticate("Edward", "wrongpassword")
        >>> user is None
        True
        >>>
        >>> # Failed authentication (user doesn't exist)
        >>> user = await repo.authenticate("NonExistent", "anypassword")
        >>> user is None
        True
        """
        # Get user by username
        user = await self.get_by_username(username)

        # User not found
        if not user:
            return None

        # Verify password against hash
        if not verify_password(password, user.password_hash):
            return None

        return user

    async def delete(self, user_id: UUID) -> bool:
        """
        Delete user with admin protection.

        Business Logic:
        - Cannot delete last admin user (prevents lockout)
        - Checks admin count before deletion
        - Hard delete (permanent removal)

        :param user_id: ID of user to delete
        :type user_id: UUID
        :return: True if deleted, False if not found
        :rtype: bool
        :raises ResourceConflictError: If trying to delete last admin

        :Example:

        >>> # Delete regular user (allowed)
        >>> await repo.delete(user_id)
        True
        >>>
        >>> # Try to delete last admin (prevented)
        >>> await repo.delete(last_admin_id)
        ResourceConflictError: Cannot delete last admin user
        """
        # Get user to check role
        try:
            user = await self.get(user_id)
        except ResourceNotFoundError:
            # User not found
            return False

        # Check if admin and if last admin
        if user.role == "admin":
            admin_count = await self.count(filters={"role": "admin"})

            if admin_count <= 1:
                raise ResourceConflictError(
                    "Cannot delete last admin user"
                )

        # Proceed with deletion
        result = await self.collection.delete_one({"id": str(user_id)})

        return result.deleted_count > 0

    async def count(self, filters: Optional[dict] = None) -> int:
        """
        Count users matching filters.

        Used for admin count check in delete operation.

        :param filters: Optional MongoDB filter dict
        :type filters: Optional[dict]
        :return: Number of matching users
        :rtype: int

        :Example:

        >>> # Count all admin users
        >>> admin_count = await repo.count(filters={"role": "admin"})
        >>> admin_count
        3
        """
        if filters is None:
            filters = {}

        return await self.collection.count_documents(filters)
