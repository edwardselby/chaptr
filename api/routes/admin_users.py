"""
Admin user management routes for CHAPTR API.

Provides admin-only endpoints for user CRUD operations:
- GET /api/admin/users - List users in current tenant
- POST /api/admin/users - Create new user (within tenant or new tenant if super_admin)
- PUT /api/admin/users/{id} - Update user (within tenant only)
- DELETE /api/admin/users/{id} - Delete user (within tenant only)

Security:
- All endpoints require admin or super_admin role
- Password hashes never exposed in responses
- Cannot delete/demote last admin
- super_admin can create new admins (new tenants)
- admin can only create users within their tenant

Multi-tenancy:
- Users can only see/manage users within their own tenant
- Creating a user with role=admin (when creator is super_admin) creates a new tenant
"""

from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends

from api.config import MongoDB
from api.models import UserCreate, UserUpdate, UserResponse
from api.repositories.users import UserRepository
from api.utils.auth import get_current_admin_user
from api.utils.errors import ResourceNotFoundError, AuthorizationError


router = APIRouter()


def get_user_repo() -> UserRepository:
    """
    Dependency: Get UserRepository instance.

    :return: UserRepository with database connection
    :rtype: UserRepository
    """
    db = MongoDB.get_database()
    return UserRepository(db)


def get_tenant_id(current_user: dict) -> UUID:
    """
    Extract tenant_id from current user for multi-tenancy filtering.

    :param current_user: Current user dict from JWT token
    :type current_user: dict
    :return: Tenant UUID
    :rtype: UUID
    """
    return UUID(current_user["tenant_id"])


@router.get("/admin/users", response_model=List[UserResponse])
async def list_users(
    repo: UserRepository = Depends(get_user_repo),
    current_user: dict = Depends(get_current_admin_user)
):
    """
    List users in current tenant (admin only).

    Returns users within the admin's tenant without password hashes.

    Multi-tenancy: Only returns users belonging to the current user's tenant.

    :param repo: User repository (injected)
    :type repo: UserRepository
    :param current_user: Current admin user (injected for authorization)
    :type current_user: dict
    :return: List of users in tenant (without password hashes)
    :rtype: List[UserResponse]

    :Example:

    Request:
    >>> GET /api/admin/users
    >>> Headers: Authorization: Bearer <admin_token>

    Success Response (200):
    >>> [
    ...     {
    ...         "id": "550e8400-e29b-41d4-a716-446655440000",
    ...         "username": "Edward",
    ...         "role": "admin",
    ...         "tenant_id": "550e8400-e29b-41d4-a716-446655440000",
    ...         "created_at": "2024-12-19T10:00:00Z",
    ...         "updated_at": "2024-12-19T10:00:00Z"
    ...     },
    ...     {
    ...         "id": "550e8400-e29b-41d4-a716-446655440001",
    ...         "username": "Kat",
    ...         "role": "user",
    ...         "tenant_id": "550e8400-e29b-41d4-a716-446655440000",
    ...         "created_at": "2024-12-19T11:00:00Z",
    ...         "updated_at": "2024-12-19T11:00:00Z"
    ...     }
    ... ]

    Failure Response (403 - not admin):
    >>> {"detail": "Admin access required"}
    """
    tenant_id = get_tenant_id(current_user)
    users = await repo.list_for_tenant(tenant_id)
    return [UserResponse.from_user(user) for user in users]


@router.post("/admin/users", response_model=UserResponse, status_code=201)
async def create_user(
    data: UserCreate,
    repo: UserRepository = Depends(get_user_repo),
    current_user: dict = Depends(get_current_admin_user)
):
    """
    Create a new user (admin only).

    Creates user with hashed password. Username must be unique.

    Multi-tenancy and Role Validation:
    - super_admin cannot be created via API (system-level only)
    - super_admin can create admin (creates new tenant) or user (joins super_admin's tenant)
    - admin can only create user (joins admin's tenant)
    - New admin becomes anchor of their own tenant (tenant_id = their user_id)

    :param data: User creation data
    :type data: UserCreate
    :param repo: User repository (injected)
    :type repo: UserRepository
    :param current_user: Current admin user (injected for authorization)
    :type current_user: dict
    :return: Created user (without password hash)
    :rtype: UserResponse
    :raises AuthorizationError: If trying to create super_admin or admin without permission
    :raises ResourceConflictError: If username already exists (409)

    :Example:

    Request:
    >>> POST /api/admin/users
    >>> Headers: Authorization: Bearer <admin_token>
    >>> {
    ...     "username": "NewUser",
    ...     "role": "user",
    ...     "password": "SecurePass123"
    ... }

    Success Response (201):
    >>> {
    ...     "id": "550e8400-e29b-41d4-a716-446655440002",
    ...     "username": "NewUser",
    ...     "role": "user",
    ...     "tenant_id": "550e8400-e29b-41d4-a716-446655440000",
    ...     "created_at": "2024-12-19T12:00:00Z",
    ...     "updated_at": "2024-12-19T12:00:00Z"
    ... }

    Failure Response (403 - invalid role creation):
    >>> {"detail": "Cannot create super_admin via API"}

    Failure Response (409 - username exists):
    >>> {"detail": "Username 'NewUser' already exists"}

    Failure Response (422 - weak password):
    >>> {"detail": [{"msg": "Password must contain at least one uppercase letter"}]}
    """
    # Role validation based on creator's role
    if data.role == "super_admin":
        raise AuthorizationError("Cannot create super_admin via API")

    if data.role == "admin" and current_user["role"] != "super_admin":
        raise AuthorizationError("Only super_admin can create new tenants (admin users)")

    # Pass creator for tenant assignment logic
    user = await repo.create(data, creator=current_user)
    return UserResponse.from_user(user)


@router.put("/admin/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: UUID,
    data: UserUpdate,
    repo: UserRepository = Depends(get_user_repo),
    current_user: dict = Depends(get_current_admin_user)
):
    """
    Update a user (admin only).

    Allows admin to update username, role, and password.
    Cannot demote the last admin user.

    Multi-tenancy: Can only update users within the same tenant.
    Role changes to super_admin are not permitted via API.

    :param user_id: ID of user to update
    :type user_id: UUID
    :param data: Update data (partial - only provided fields updated)
    :type data: UserUpdate
    :param repo: User repository (injected)
    :type repo: UserRepository
    :param current_user: Current admin user (injected for authorization)
    :type current_user: dict
    :return: Updated user (without password hash)
    :rtype: UserResponse
    :raises ResourceNotFoundError: If user not found in tenant (404)
    :raises AuthorizationError: If trying to set role to super_admin (403)
    :raises ResourceConflictError: If username exists or last admin demotion (409)

    :Example:

    Request (change username):
    >>> PUT /api/admin/users/550e8400-e29b-41d4-a716-446655440001
    >>> Headers: Authorization: Bearer <admin_token>
    >>> {"username": "UpdatedName"}

    Request (change role):
    >>> PUT /api/admin/users/550e8400-e29b-41d4-a716-446655440001
    >>> {"role": "admin"}

    Request (change password):
    >>> PUT /api/admin/users/550e8400-e29b-41d4-a716-446655440001
    >>> {"password": "NewSecure123"}

    Success Response (200):
    >>> {
    ...     "id": "550e8400-e29b-41d4-a716-446655440001",
    ...     "username": "UpdatedName",
    ...     "role": "admin",
    ...     "tenant_id": "550e8400-e29b-41d4-a716-446655440000",
    ...     "created_at": "2024-12-19T11:00:00Z",
    ...     "updated_at": "2024-12-19T13:00:00Z"
    ... }

    Failure Response (404 - not found):
    >>> {"detail": "User 550e8400-... not found"}

    Failure Response (403 - invalid role):
    >>> {"detail": "Cannot promote user to super_admin via API"}

    Failure Response (409 - last admin demotion):
    >>> {"detail": "Cannot demote last admin user"}
    """
    # Prevent promotion to super_admin
    if data.role == "super_admin":
        raise AuthorizationError("Cannot promote user to super_admin via API")

    # Verify user belongs to same tenant
    tenant_id = get_tenant_id(current_user)
    target_user = await repo.get_for_tenant(user_id, tenant_id)

    user = await repo.update(user_id, data, is_admin_update=True)
    return UserResponse.from_user(user)


@router.delete("/admin/users/{user_id}", status_code=204)
async def delete_user(
    user_id: UUID,
    repo: UserRepository = Depends(get_user_repo),
    current_user: dict = Depends(get_current_admin_user)
):
    """
    Delete a user (admin only).

    Permanently removes user from the system.
    Cannot delete the last admin user.

    Multi-tenancy: Can only delete users within the same tenant.

    :param user_id: ID of user to delete
    :type user_id: UUID
    :param repo: User repository (injected)
    :type repo: UserRepository
    :param current_user: Current admin user (injected for authorization)
    :type current_user: dict
    :return: No content on success
    :raises ResourceNotFoundError: If user not found in tenant (404)
    :raises ResourceConflictError: If trying to delete last admin (409)

    :Example:

    Request:
    >>> DELETE /api/admin/users/550e8400-e29b-41d4-a716-446655440001
    >>> Headers: Authorization: Bearer <admin_token>

    Success Response (204): No content

    Failure Response (404 - not found):
    >>> {"detail": "Resource not found"}

    Failure Response (409 - last admin):
    >>> {"detail": "Cannot delete last admin user"}
    """
    # Verify user belongs to same tenant
    tenant_id = get_tenant_id(current_user)
    await repo.get_for_tenant(user_id, tenant_id)

    deleted = await repo.delete(user_id)
    if not deleted:
        raise ResourceNotFoundError("User not found")
    # Return None with 204 status
    return None
