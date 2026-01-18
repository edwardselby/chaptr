"""
User repository for CHAPTR API.

Provides data access layer for user management with authentication logic.
Handles user CRUD operations, username uniqueness, password hashing,
and admin deletion protection.
"""

from typing import Optional
from uuid import UUID

from api.models import User, UserCreate, UserUpdate
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

    async def create(self, data: UserCreate, creator: Optional[dict] = None) -> User:
        """
        Create a new user with password hashing, username uniqueness check, and tenant assignment.

        Business Logic:
        - Username must be unique across all users
        - Password is hashed using bcrypt before storage
        - Never stores plain text passwords
        - Auto-generates UUID and timestamps
        - Tenant assignment based on creator's role and new user's role:
          - No creator (bootstrap): super_admin via script, self-anchored tenant
          - super_admin creating admin: New tenant (admin anchors own tenant)
          - super_admin creating user: Joins super_admin's tenant
          - admin/promoted admin creating user: Same tenant as creator

        :param data: User creation data with plain text password
        :type data: UserCreate
        :param creator: Current user dict creating this user (None for bootstrap)
        :type creator: Optional[dict]
        :return: Created user with hashed password
        :rtype: User
        :raises ResourceConflictError: If username already exists

        :Example:

        >>> user_data = UserCreate(
        ...     username="Edward",
        ...     password="password123",
        ...     role="admin"
        ... )
        >>> user = await repo.create(user_data, creator=current_user)
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

        # Generate user ID first (needed for self-anchored tenants)
        user_id = generate_id()

        # Determine tenant_id based on creator's role and new user's role
        if creator is None:
            # Bootstrap: super_admin via script - self-anchored tenant
            tenant_id = user_id
        elif creator["role"] == "super_admin":
            if data.role == "admin":
                # New tenant - admin is their own anchor
                tenant_id = user_id
            else:
                # Joins super_admin's tenant
                tenant_id = UUID(creator["tenant_id"])
        else:
            # Admin or promoted admin creating user - same tenant
            tenant_id = UUID(creator["tenant_id"])

        # Create user with hashed password and tenant assignment
        user = User(
            id=user_id,
            username=data.username,
            role=data.role,
            tenant_id=tenant_id,
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

    async def list_all(self) -> list[User]:
        """
        List all users.

        Returns all users in the system for admin management.
        Password hashes are included but should be excluded at API layer.

        :return: List of all users
        :rtype: list[User]

        :Example:

        >>> users = await repo.list_all()
        >>> for user in users:
        ...     print(user.username, user.role)
        """
        cursor = self.collection.find({})
        docs = await cursor.to_list(length=None)
        return [User(**doc) for doc in docs]

    async def list_for_tenant(self, tenant_id: UUID) -> list[User]:
        """
        List all users belonging to a specific tenant.

        Used for tenant-scoped user management - admins can only see
        users within their own tenant.

        :param tenant_id: Tenant identifier to filter by
        :type tenant_id: UUID
        :return: List of users in the tenant
        :rtype: list[User]

        :Example:

        >>> users = await repo.list_for_tenant(tenant_id)
        >>> for user in users:
        ...     print(user.username, user.role)
        """
        cursor = self.collection.find({"tenant_id": str(tenant_id)})
        docs = await cursor.to_list(length=None)
        return [User(**doc) for doc in docs]

    async def update(
        self,
        user_id: UUID,
        data: UserUpdate,
        is_admin_update: bool = False
    ) -> User:
        """
        Update user with business rule enforcement.

        Business Logic:
        - Username must be unique if changed
        - Cannot demote last admin (role protection)
        - Password is rehashed if provided
        - updated_at timestamp is refreshed
        - For self-service, role field is ignored

        :param user_id: ID of user to update
        :type user_id: UUID
        :param data: Update data (partial - only provided fields are updated)
        :type data: UserUpdate
        :param is_admin_update: Whether this is an admin update (allows role changes)
        :type is_admin_update: bool
        :return: Updated user
        :rtype: User
        :raises ResourceNotFoundError: If user not found
        :raises ResourceConflictError: If username already exists or last admin demotion

        :Example:

        >>> # Admin updating another user
        >>> updated = await repo.update(
        ...     user_id=some_uuid,
        ...     data=UserUpdate(username="NewName", role="admin"),
        ...     is_admin_update=True
        ... )

        >>> # Self-service update (role ignored)
        >>> updated = await repo.update(
        ...     user_id=own_uuid,
        ...     data=UserUpdate(username="NewName"),
        ...     is_admin_update=False
        ... )
        """
        # Get existing user
        try:
            user = await self.get(user_id)
        except ResourceNotFoundError:
            raise ResourceNotFoundError(f"User {user_id} not found")

        # Build update dict with only provided fields
        update_dict = {}

        # Handle username change (check uniqueness)
        if data.username is not None and data.username != user.username:
            existing = await self.get_by_username(data.username)
            if existing:
                raise ResourceConflictError(
                    f"Username '{data.username}' already exists"
                )
            update_dict["username"] = data.username

        # Handle role change (admin-only, with last-admin protection)
        if is_admin_update and data.role is not None and data.role != user.role:
            # Check if demoting a super_admin
            if user.role == "super_admin" and data.role != "super_admin":
                super_admin_count = await self.count(filters={"role": "super_admin"})
                if super_admin_count <= 1:
                    raise ResourceConflictError(
                        "Cannot demote last admin user"
                    )
            # Check if demoting an admin
            elif user.role == "admin" and data.role != "admin":
                admin_count = await self.count(filters={"role": "admin"})
                if admin_count <= 1:
                    raise ResourceConflictError(
                        "Cannot demote last admin user"
                    )
            update_dict["role"] = data.role.value

        # Handle password change (rehash)
        if data.password is not None:
            update_dict["password_hash"] = hash_password(data.password)

        # If no changes, return existing user
        if not update_dict:
            return user

        # Update timestamp
        update_dict["updated_at"] = utc_now()

        # Apply update to database
        await self.collection.update_one(
            {"id": str(user_id)},
            {"$set": update_dict}
        )

        # Return updated user
        return await self.get(user_id)

    async def delete(self, user_id: UUID) -> bool:
        """
        Delete user with admin protection.

        Business Logic:
        - Cannot delete last super_admin user (prevents lockout)
        - Cannot delete last admin user in tenant (tenant needs admin)
        - Checks admin count before deletion
        - Hard delete (permanent removal)

        Multi-tenancy:
        - super_admin deletion is system-wide check
        - admin deletion checks within tenant context

        :param user_id: ID of user to delete
        :type user_id: UUID
        :return: True if deleted, False if not found
        :rtype: bool
        :raises ResourceConflictError: If trying to delete last admin/super_admin

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

        # Check if super_admin and if last super_admin (system-wide protection)
        if user.role == "super_admin":
            super_admin_count = await self.count(filters={"role": "super_admin"})

            if super_admin_count <= 1:
                raise ResourceConflictError(
                    "Cannot delete last admin user"
                )

        # Check if admin and if last admin (tenant-level protection)
        elif user.role == "admin":
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
