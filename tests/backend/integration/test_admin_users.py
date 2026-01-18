"""
Comprehensive tests for admin user management endpoints.

Tests the full user management CRUD:
- GET /api/admin/users - List all users (admin only)
- POST /api/admin/users - Create new user (admin only)
- PUT /api/admin/users/{id} - Update user (admin only)
- DELETE /api/admin/users/{id} - Delete user (admin only)
- PUT /api/auth/me - Self-service profile update

Ruthless testing approach: Test every possible failure mode.
"""

import pytest
from uuid import uuid4

from api.models import UserCreate
from api.utils.auth import create_access_token, verify_password


# ============================================================================
# GET /api/admin/users Tests (List Users)
# ============================================================================

@pytest.mark.asyncio
async def test_list_users_returns_all_users(async_client, auth_headers, sample_user):
    """Admin can list all users."""
    response = await async_client.get("/api/admin/users", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1  # At least the sample_user

    # Check user structure (no password_hash)
    user = data[0]
    assert "id" in user
    assert "username" in user
    assert "role" in user
    assert "created_at" in user
    assert "updated_at" in user
    assert "password_hash" not in user


@pytest.mark.asyncio
async def test_list_users_excludes_password_hash(async_client, auth_headers, sample_user):
    """User list never includes password_hash field."""
    response = await async_client.get("/api/admin/users", headers=auth_headers)

    assert response.status_code == 200
    for user in response.json():
        assert "password_hash" not in user
        assert "password" not in user


@pytest.mark.asyncio
async def test_list_users_fails_for_regular_user(
    async_client,
    regular_user_auth_headers,
    sample_regular_user
):
    """Regular users cannot list users (403)."""
    response = await async_client.get(
        "/api/admin/users",
        headers=regular_user_auth_headers
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_list_users_fails_without_auth(async_client):
    """Listing users without auth returns 401 Unauthorized."""
    response = await async_client.get("/api/admin/users")

    assert response.status_code == 401


# ============================================================================
# POST /api/admin/users Tests (Create User)
# ============================================================================

@pytest.mark.asyncio
async def test_create_user_success(async_client, auth_headers, sample_user):
    """Admin can create a new user."""
    response = await async_client.post(
        "/api/admin/users",
        headers=auth_headers,
        json={
            "username": "NewUser",
            "role": "user",
            "password": "ValidPass123"
        }
    )

    assert response.status_code == 201
    data = response.json()
    assert data["username"] == "NewUser"
    assert data["role"] == "user"
    assert "id" in data
    assert "created_at" in data
    assert "password_hash" not in data


@pytest.mark.asyncio
async def test_create_user_with_admin_role(async_client, auth_headers, sample_user):
    """Super admin can create a new admin user (creates new tenant)."""
    # sample_user is super_admin, so can create admins
    response = await async_client.post(
        "/api/admin/users",
        headers=auth_headers,
        json={
            "username": "NewAdmin",
            "role": "admin",
            "password": "ValidPass123"
        }
    )

    assert response.status_code == 201
    data = response.json()
    assert data["role"] == "admin"
    # New admin should have their own tenant (tenant_id = their own id)
    assert data["tenant_id"] == data["id"]


@pytest.mark.asyncio
async def test_create_user_fails_duplicate_username(async_client, auth_headers, sample_user):
    """Cannot create user with existing username (409)."""
    response = await async_client.post(
        "/api/admin/users",
        headers=auth_headers,
        json={
            "username": "Edward",  # Same as sample_user
            "role": "user",
            "password": "ValidPass123"
        }
    )

    assert response.status_code == 409


@pytest.mark.asyncio
async def test_create_user_fails_weak_password_no_uppercase(
    async_client,
    auth_headers,
    sample_user
):
    """Cannot create user with password missing uppercase (422)."""
    response = await async_client.post(
        "/api/admin/users",
        headers=auth_headers,
        json={
            "username": "NewUser",
            "role": "user",
            "password": "lowercase123"  # No uppercase
        }
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_user_fails_weak_password_no_lowercase(
    async_client,
    auth_headers,
    sample_user
):
    """Cannot create user with password missing lowercase (422)."""
    response = await async_client.post(
        "/api/admin/users",
        headers=auth_headers,
        json={
            "username": "NewUser",
            "role": "user",
            "password": "UPPERCASE123"  # No lowercase
        }
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_user_fails_weak_password_no_digit(
    async_client,
    auth_headers,
    sample_user
):
    """Cannot create user with password missing digit (422)."""
    response = await async_client.post(
        "/api/admin/users",
        headers=auth_headers,
        json={
            "username": "NewUser",
            "role": "user",
            "password": "NoDigitsHere"  # No digit
        }
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_user_fails_short_password(async_client, auth_headers, sample_user):
    """Cannot create user with password shorter than 8 chars (422)."""
    response = await async_client.post(
        "/api/admin/users",
        headers=auth_headers,
        json={
            "username": "NewUser",
            "role": "user",
            "password": "Abc123"  # Too short
        }
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_user_fails_missing_password(async_client, auth_headers, sample_user):
    """Cannot create user without password (422)."""
    response = await async_client.post(
        "/api/admin/users",
        headers=auth_headers,
        json={
            "username": "NewUser",
            "role": "user"
        }
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_user_fails_for_regular_user(
    async_client,
    regular_user_auth_headers,
    sample_regular_user
):
    """Regular users cannot create users (403)."""
    response = await async_client.post(
        "/api/admin/users",
        headers=regular_user_auth_headers,
        json={
            "username": "NewUser",
            "role": "user",
            "password": "ValidPass123"
        }
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_create_super_admin_fails(async_client, auth_headers, sample_user):
    """Cannot create super_admin via API (403)."""
    response = await async_client.post(
        "/api/admin/users",
        headers=auth_headers,
        json={
            "username": "AttemptedSuperAdmin",
            "role": "super_admin",
            "password": "ValidPass123"
        }
    )

    assert response.status_code == 403
    assert "super_admin" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_admin_cannot_create_other_admin(async_client, auth_headers, sample_user, user_repo):
    """Regular admin (not super_admin) cannot create another admin user."""
    # First, create an admin user (via super_admin)
    admin_response = await async_client.post(
        "/api/admin/users",
        headers=auth_headers,
        json={
            "username": "AdminUser",
            "role": "admin",
            "password": "ValidPass123"
        }
    )
    assert admin_response.status_code == 201
    admin_data = admin_response.json()

    # Now create auth headers for the new admin
    from api.utils.auth import create_access_token
    admin_token = create_access_token(
        user_id=admin_data["id"],
        username=admin_data["username"],
        role=admin_data["role"],
        tenant_id=admin_data["tenant_id"]
    )
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    # Try to create another admin with the new admin's token - should fail
    response = await async_client.post(
        "/api/admin/users",
        headers=admin_headers,
        json={
            "username": "AnotherAdmin",
            "role": "admin",
            "password": "ValidPass123"
        }
    )

    assert response.status_code == 403
    assert "super_admin" in response.json()["detail"].lower()


# ============================================================================
# PUT /api/admin/users/{id} Tests (Update User)
# ============================================================================

@pytest.mark.asyncio
async def test_update_user_username(async_client, auth_headers, sample_regular_user):
    """Admin can update user's username."""
    response = await async_client.put(
        f"/api/admin/users/{sample_regular_user.id}",
        headers=auth_headers,
        json={"username": "UpdatedName"}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["username"] == "UpdatedName"


@pytest.mark.asyncio
async def test_update_user_role(async_client, auth_headers, sample_regular_user):
    """Super admin can promote user to admin."""
    response = await async_client.put(
        f"/api/admin/users/{sample_regular_user.id}",
        headers=auth_headers,
        json={"role": "admin"}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["role"] == "admin"


@pytest.mark.asyncio
async def test_update_user_to_super_admin_fails(async_client, auth_headers, sample_regular_user):
    """Cannot promote user to super_admin via API (403)."""
    response = await async_client.put(
        f"/api/admin/users/{sample_regular_user.id}",
        headers=auth_headers,
        json={"role": "super_admin"}
    )

    assert response.status_code == 403
    assert "super_admin" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_update_user_password(async_client, auth_headers, sample_regular_user, user_repo):
    """Admin can change user's password."""
    new_password = "NewPassword123"
    response = await async_client.put(
        f"/api/admin/users/{sample_regular_user.id}",
        headers=auth_headers,
        json={"password": new_password}
    )

    assert response.status_code == 200

    # Verify password was changed
    updated_user = await user_repo.get(sample_regular_user.id)
    assert verify_password(new_password, updated_user.password_hash)


@pytest.mark.asyncio
async def test_update_user_fails_duplicate_username(
    async_client,
    auth_headers,
    sample_user,
    sample_regular_user
):
    """Cannot update user to existing username (409)."""
    response = await async_client.put(
        f"/api/admin/users/{sample_regular_user.id}",
        headers=auth_headers,
        json={"username": "Edward"}  # Same as sample_user
    )

    assert response.status_code == 409


@pytest.mark.asyncio
async def test_update_user_fails_not_found(async_client, auth_headers, sample_user):
    """Cannot update non-existent user (404)."""
    fake_id = str(uuid4())
    response = await async_client.put(
        f"/api/admin/users/{fake_id}",
        headers=auth_headers,
        json={"username": "NewName"}
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_user_cannot_demote_last_admin(async_client, auth_headers, sample_user):
    """Cannot demote the last admin user (409)."""
    response = await async_client.put(
        f"/api/admin/users/{sample_user.id}",
        headers=auth_headers,
        json={"role": "user"}
    )

    assert response.status_code == 409


@pytest.mark.asyncio
async def test_update_user_can_demote_admin_if_others_exist(
    async_client,
    auth_headers,
    sample_user,
    user_repo
):
    """Can demote super_admin when other super_admins exist."""
    # sample_user is super_admin (multi-tenancy), so create another super_admin
    second_admin = await user_repo.create(UserCreate(
        username="SecondSuperAdmin",
        password="SecondPass123",
        role="super_admin"
    ))

    # Now we can demote the first super_admin
    response = await async_client.put(
        f"/api/admin/users/{sample_user.id}",
        headers=auth_headers,
        json={"role": "user"}
    )

    assert response.status_code == 200
    assert response.json()["role"] == "user"


@pytest.mark.asyncio
async def test_update_user_fails_for_regular_user(
    async_client,
    regular_user_auth_headers,
    sample_regular_user,
    sample_user
):
    """Regular users cannot update users via admin endpoint (403)."""
    response = await async_client.put(
        f"/api/admin/users/{sample_user.id}",
        headers=regular_user_auth_headers,
        json={"username": "NewName"}
    )

    assert response.status_code == 403


# ============================================================================
# DELETE /api/admin/users/{id} Tests (Delete User)
# ============================================================================

@pytest.mark.asyncio
async def test_delete_user_success(async_client, auth_headers, sample_regular_user, user_repo):
    """Admin can delete a regular user."""
    user_id = sample_regular_user.id

    response = await async_client.delete(
        f"/api/admin/users/{user_id}",
        headers=auth_headers
    )

    assert response.status_code == 204

    # Verify user is deleted
    from api.utils.errors import ResourceNotFoundError
    with pytest.raises(ResourceNotFoundError):
        await user_repo.get(user_id)


@pytest.mark.asyncio
async def test_delete_user_fails_not_found(async_client, auth_headers, sample_user):
    """Cannot delete non-existent user (404)."""
    fake_id = str(uuid4())
    response = await async_client.delete(
        f"/api/admin/users/{fake_id}",
        headers=auth_headers
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_user_cannot_delete_last_admin(async_client, auth_headers, sample_user):
    """Cannot delete the last admin user (409)."""
    response = await async_client.delete(
        f"/api/admin/users/{sample_user.id}",
        headers=auth_headers
    )

    assert response.status_code == 409


@pytest.mark.asyncio
async def test_delete_user_can_delete_admin_if_others_exist(
    async_client,
    auth_headers,
    sample_user,
    user_repo
):
    """Can delete super_admin when other super_admins exist."""
    # sample_user is super_admin (multi-tenancy), so create another super_admin
    second_admin = await user_repo.create(UserCreate(
        username="SecondSuperAdmin",
        password="SecondPass123",
        role="super_admin"
    ))

    # Now we can delete the first super_admin
    response = await async_client.delete(
        f"/api/admin/users/{sample_user.id}",
        headers=auth_headers
    )

    assert response.status_code == 204


@pytest.mark.asyncio
async def test_delete_user_fails_for_regular_user(
    async_client,
    regular_user_auth_headers,
    sample_regular_user,
    sample_user
):
    """Regular users cannot delete users (403)."""
    response = await async_client.delete(
        f"/api/admin/users/{sample_regular_user.id}",
        headers=regular_user_auth_headers
    )

    assert response.status_code == 403


# ============================================================================
# PUT /api/auth/me Tests (Self-Service Profile Update)
# ============================================================================

@pytest.mark.asyncio
async def test_self_service_update_username(
    async_client,
    regular_user_auth_headers,
    sample_regular_user
):
    """User can update their own username."""
    response = await async_client.put(
        "/api/auth/me",
        headers=regular_user_auth_headers,
        json={"username": "MyNewName"}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["username"] == "MyNewName"
    assert "password_hash" not in data


@pytest.mark.asyncio
async def test_self_service_update_password_with_current_password(
    async_client,
    user_repo
):
    """User can update password with current password verification."""
    # Create a test user
    test_user = await user_repo.create(UserCreate(
        username="TestPasswordUser",
        password="OldPassword123",
        role="user"
    ))

    # Create auth headers for this user (include tenant_id for multi-tenancy)
    token = create_access_token(
        user_id=test_user.id,
        username=test_user.username,
        role=test_user.role,
        tenant_id=test_user.tenant_id
    )
    headers = {"Authorization": f"Bearer {token}"}

    # Update password with current password
    response = await async_client.put(
        "/api/auth/me",
        headers=headers,
        json={
            "password": "NewPassword456",
            "current_password": "OldPassword123"
        }
    )

    assert response.status_code == 200

    # Verify new password works
    updated_user = await user_repo.get(test_user.id)
    assert verify_password("NewPassword456", updated_user.password_hash)


@pytest.mark.asyncio
async def test_self_service_fails_password_change_without_current(
    async_client,
    regular_user_auth_headers,
    sample_regular_user
):
    """Cannot change password without providing current password (401)."""
    response = await async_client.put(
        "/api/auth/me",
        headers=regular_user_auth_headers,
        json={"password": "NewPassword123"}
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_self_service_fails_wrong_current_password(
    async_client,
    regular_user_auth_headers,
    sample_regular_user
):
    """Cannot change password with wrong current password (401)."""
    response = await async_client.put(
        "/api/auth/me",
        headers=regular_user_auth_headers,
        json={
            "password": "NewPassword123",
            "current_password": "WrongPassword123"
        }
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_self_service_cannot_change_role(
    async_client,
    regular_user_auth_headers,
    sample_regular_user
):
    """User cannot promote themselves to admin."""
    response = await async_client.put(
        "/api/auth/me",
        headers=regular_user_auth_headers,
        json={"role": "admin"}
    )

    assert response.status_code == 200
    # Role should NOT change - still "user"
    data = response.json()
    assert data["role"] == "user"


@pytest.mark.asyncio
async def test_self_service_fails_duplicate_username(
    async_client,
    regular_user_auth_headers,
    sample_regular_user,
    sample_user  # admin user named "Edward"
):
    """Cannot update to existing username (409)."""
    response = await async_client.put(
        "/api/auth/me",
        headers=regular_user_auth_headers,
        json={"username": "Edward"}  # Same as sample_user
    )

    assert response.status_code == 409


@pytest.mark.asyncio
async def test_self_service_fails_without_auth(async_client):
    """Cannot update profile without authentication (401 Unauthorized)."""
    response = await async_client.put(
        "/api/auth/me",
        json={"username": "NewName"}
    )

    assert response.status_code == 401


# ============================================================================
# User Repository Update Method Tests
# ============================================================================

@pytest.mark.asyncio
async def test_repo_update_updates_timestamp(user_repo, sample_regular_user):
    """Repository update refreshes updated_at timestamp."""
    from api.models import UserUpdate
    import time

    original_updated_at = sample_regular_user.updated_at

    # Small delay to ensure timestamp differs
    time.sleep(0.01)

    updated = await user_repo.update(
        sample_regular_user.id,
        UserUpdate(username="TimestampTest"),
        is_admin_update=True
    )

    # Compare timestamps - handle timezone-aware/naive by comparing strings or using replace
    # Both timestamps should be in UTC, just potentially one aware and one naive
    assert updated.updated_at.replace(tzinfo=None) > original_updated_at.replace(tzinfo=None)


@pytest.mark.asyncio
async def test_repo_update_returns_user_unchanged_if_no_changes(
    user_repo,
    sample_regular_user
):
    """Repository update returns same user if no fields changed."""
    from api.models import UserUpdate

    # Empty update
    updated = await user_repo.update(
        sample_regular_user.id,
        UserUpdate(),  # No changes
        is_admin_update=True
    )

    assert updated.username == sample_regular_user.username
    assert updated.role == sample_regular_user.role
