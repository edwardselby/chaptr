"""
Comprehensive tests for UserRepository (Phase 1.5).

Tests user CRUD operations, authentication logic, and admin protection.
Ruthless testing approach: Test every possible failure mode.
"""

import pytest
from uuid import uuid4

from api.models import UserCreate
from api.utils.errors import ResourceNotFoundError, ResourceConflictError
from api.utils.auth import verify_password


# ============================================================================
# User Creation Tests
# ============================================================================

@pytest.mark.asyncio
async def test_create_user_success(user_repo):
    """User creation succeeds with valid data."""
    user_data = UserCreate(
        username="TestUser",
        password="ValidPass123",
        role="user"
    )

    user = await user_repo.create(user_data)

    assert user.username == "TestUser"
    assert user.role == "user"
    assert user.id is not None
    assert user.created_at is not None
    assert user.updated_at is not None


@pytest.mark.asyncio
async def test_create_user_hashes_password(user_repo):
    """User creation hashes password with bcrypt."""
    user_data = UserCreate(
        username="TestUser",
        password="PlainPassword123",
        role="user"
    )

    user = await user_repo.create(user_data)

    # Password should be hashed (bcrypt format)
    assert user.password_hash.startswith("$2b$")
    assert user.password_hash != "PlainPassword123"
    assert len(user.password_hash) == 60


@pytest.mark.asyncio
async def test_create_user_password_hash_verifiable(user_repo):
    """Created user's password hash can be verified."""
    password = "TestPassword123"
    user_data = UserCreate(
        username="TestUser",
        password=password,
        role="user"
    )

    user = await user_repo.create(user_data)

    # Password hash should verify correctly
    assert verify_password(password, user.password_hash) is True
    assert verify_password("WrongPassword123", user.password_hash) is False


@pytest.mark.asyncio
async def test_create_user_enforces_unique_username(user_repo):
    """User creation fails if username already exists (uniqueness)."""
    user_data = UserCreate(
        username="DuplicateUser",
        password="Password123",
        role="user"
    )

    # Create first user
    await user_repo.create(user_data)

    # Attempt to create second user with same username
    with pytest.raises(ResourceConflictError) as exc_info:
        await user_repo.create(user_data)

    assert "already exists" in str(exc_info.value.detail).lower()


@pytest.mark.asyncio
async def test_create_user_username_case_sensitive(user_repo):
    """Username uniqueness is case-sensitive."""
    user_data_lower = UserCreate(
        username="testuser",
        password="Password123",
        role="user"
    )
    user_data_upper = UserCreate(
        username="TestUser",
        password="Password123",
        role="user"
    )

    # Both should succeed (different usernames)
    user1 = await user_repo.create(user_data_lower)
    user2 = await user_repo.create(user_data_upper)

    assert user1.username == "testuser"
    assert user2.username == "TestUser"


@pytest.mark.asyncio
async def test_create_admin_user(user_repo):
    """Admin user creation succeeds."""
    user_data = UserCreate(
        username="AdminUser",
        password="AdminPass123",
        role="admin"
    )

    user = await user_repo.create(user_data)

    assert user.role == "admin"


# ============================================================================
# Get User Tests
# ============================================================================

@pytest.mark.asyncio
async def test_get_user_by_id_success(user_repo, sample_user):
    """Get user by ID returns correct user."""
    user = await user_repo.get(sample_user.id)

    assert user.id == sample_user.id
    assert user.username == sample_user.username
    assert user.role == sample_user.role


@pytest.mark.asyncio
async def test_get_user_by_id_not_found(user_repo):
    """Get user by non-existent ID raises ResourceNotFoundError."""
    non_existent_id = uuid4()

    with pytest.raises(ResourceNotFoundError):
        await user_repo.get(non_existent_id)


@pytest.mark.asyncio
async def test_get_user_by_username_success(user_repo, sample_user):
    """Get user by username returns correct user."""
    user = await user_repo.get_by_username(sample_user.username)

    assert user.id == sample_user.id
    assert user.username == sample_user.username


@pytest.mark.asyncio
async def test_get_user_by_username_not_found(user_repo):
    """Get user by non-existent username returns None."""
    user = await user_repo.get_by_username("NonExistentUser")

    assert user is None


@pytest.mark.asyncio
async def test_get_user_by_username_case_sensitive(user_repo, sample_user):
    """Get user by username is case-sensitive."""
    # sample_user has username "Edward"
    user_correct = await user_repo.get_by_username("Edward")
    user_wrong_case = await user_repo.get_by_username("edward")

    assert user_correct is not None
    assert user_wrong_case is None


# ============================================================================
# List Users Tests
# ============================================================================

@pytest.mark.asyncio
async def test_list_users_empty(user_repo):
    """List users returns empty list when no users exist."""
    users = await user_repo.list()

    assert users == []


@pytest.mark.asyncio
async def test_list_users_returns_all_users(user_repo, sample_user, sample_regular_user):
    """List users returns all created users."""
    users = await user_repo.list()

    assert len(users) == 2
    usernames = {user.username for user in users}
    assert "Edward" in usernames
    assert "RegularUser" in usernames


# ============================================================================
# Authentication Tests
# ============================================================================

@pytest.mark.asyncio
async def test_authenticate_success_with_valid_credentials(user_repo, sample_user):
    """Authenticate returns user with valid credentials."""
    user = await user_repo.authenticate("Edward", "TestPass123")

    assert user is not None
    assert user.id == sample_user.id
    assert user.username == "Edward"


@pytest.mark.asyncio
async def test_authenticate_fails_with_wrong_password(user_repo, sample_user):
    """Authenticate returns None with wrong password."""
    user = await user_repo.authenticate("Edward", "WrongPassword123")

    assert user is None


@pytest.mark.asyncio
async def test_authenticate_fails_with_non_existent_username(user_repo):
    """Authenticate returns None with non-existent username."""
    user = await user_repo.authenticate("NonExistentUser", "AnyPassword123")

    assert user is None


@pytest.mark.asyncio
async def test_authenticate_case_sensitive_username(user_repo, sample_user):
    """Authenticate is case-sensitive for username."""
    # Correct username
    user_correct = await user_repo.authenticate("Edward", "TestPass123")
    # Wrong case
    user_wrong = await user_repo.authenticate("edward", "TestPass123")

    assert user_correct is not None
    assert user_wrong is None


@pytest.mark.asyncio
async def test_authenticate_case_sensitive_password(user_repo, sample_user):
    """Authenticate is case-sensitive for password."""
    # sample_user password is "TestPass123"
    user_correct = await user_repo.authenticate("Edward", "TestPass123")
    user_lowercase = await user_repo.authenticate("Edward", "testpass123")
    user_uppercase = await user_repo.authenticate("Edward", "TESTPASS123")

    assert user_correct is not None
    assert user_lowercase is None
    assert user_uppercase is None


@pytest.mark.asyncio
async def test_authenticate_fails_with_empty_password(user_repo, sample_user):
    """Authenticate fails with empty password."""
    user = await user_repo.authenticate("Edward", "")

    assert user is None


# ============================================================================
# Delete User Tests
# ============================================================================

@pytest.mark.asyncio
async def test_delete_user_success(user_repo, sample_regular_user):
    """Delete user succeeds for non-admin user."""
    result = await user_repo.delete(sample_regular_user.id)

    assert result is True

    # Verify user is deleted
    with pytest.raises(ResourceNotFoundError):
        await user_repo.get(sample_regular_user.id)


@pytest.mark.asyncio
async def test_delete_user_not_found(user_repo):
    """Delete non-existent user returns False."""
    non_existent_id = uuid4()

    result = await user_repo.delete(non_existent_id)

    assert result is False


@pytest.mark.asyncio
async def test_delete_admin_when_multiple_admins_exist(user_repo, sample_user):
    """Delete super_admin succeeds when multiple super_admins exist."""
    # Create second super_admin (sample_user is super_admin in multi-tenancy)
    admin_data = UserCreate(
        username="SecondSuperAdmin",
        password="AdminPass123",
        role="super_admin"
    )
    second_admin = await user_repo.create(admin_data)

    # Delete first super_admin (should succeed - second super_admin exists)
    result = await user_repo.delete(sample_user.id)

    assert result is True


@pytest.mark.asyncio
async def test_delete_last_admin_fails(user_repo, sample_user):
    """Delete fails when trying to delete last admin (protection)."""
    # sample_user is the only admin
    with pytest.raises(ResourceConflictError) as exc_info:
        await user_repo.delete(sample_user.id)

    assert "last admin" in str(exc_info.value.detail).lower()


@pytest.mark.asyncio
async def test_delete_last_admin_with_regular_users_fails(user_repo, sample_user, sample_regular_user):
    """Delete last admin fails even when regular users exist."""
    # sample_user is admin, sample_regular_user is regular user
    # Should still fail (must have at least one admin)
    with pytest.raises(ResourceConflictError) as exc_info:
        await user_repo.delete(sample_user.id)

    assert "last admin" in str(exc_info.value.detail).lower()


@pytest.mark.asyncio
async def test_delete_regular_user_when_only_admin_exists(user_repo, sample_user, sample_regular_user):
    """Delete regular user succeeds even if only one admin exists."""
    # sample_user is admin, sample_regular_user is regular user
    result = await user_repo.delete(sample_regular_user.id)

    assert result is True


# ============================================================================
# Count Users Tests
# ============================================================================

@pytest.mark.asyncio
async def test_count_users_empty(user_repo):
    """Count users returns 0 when no users exist."""
    count = await user_repo.count()

    assert count == 0


@pytest.mark.asyncio
async def test_count_users_with_data(user_repo, sample_user, sample_regular_user):
    """Count users returns correct count."""
    count = await user_repo.count()

    assert count == 2


@pytest.mark.asyncio
async def test_count_users_with_role_filter(user_repo, sample_user, sample_regular_user):
    """Count users with role filter returns correct count."""
    # sample_user is super_admin (multi-tenancy), sample_regular_user is user
    super_admin_count = await user_repo.count(filters={"role": "super_admin"})
    user_count = await user_repo.count(filters={"role": "user"})

    assert super_admin_count == 1
    assert user_count == 1


# ============================================================================
# Edge Cases and Security Tests
# ============================================================================

@pytest.mark.asyncio
async def test_create_user_with_unicode_username(user_repo):
    """User creation handles unicode characters in username."""
    user_data = UserCreate(
        username="用户名",
        password="Password123",
        role="user"
    )

    user = await user_repo.create(user_data)

    assert user.username == "用户名"


@pytest.mark.asyncio
async def test_create_user_with_special_characters_in_username(user_repo):
    """User creation handles special characters in username."""
    user_data = UserCreate(
        username="User_Name-2024",
        password="Password123",
        role="user"
    )

    user = await user_repo.create(user_data)

    assert user.username == "User_Name-2024"


@pytest.mark.asyncio
async def test_password_never_stored_in_plain_text(user_repo):
    """Verify password is never stored in plain text in database."""
    password = "PlainTextPassword123"
    user_data = UserCreate(
        username="SecurityTest",
        password=password,
        role="user"
    )

    user = await user_repo.create(user_data)

    # Retrieve directly from database to verify
    db_user = await user_repo.get(user.id)

    # Password should be hashed, not plain text
    assert db_user.password_hash != password
    assert db_user.password_hash.startswith("$2b$")


@pytest.mark.asyncio
async def test_admin_count_accurate_for_protection(user_repo):
    """Admin count used for deletion protection is accurate."""
    # Create multiple admins
    admin1 = await user_repo.create(UserCreate(username="Admin1", password="Pass1234", role="admin"))
    admin2 = await user_repo.create(UserCreate(username="Admin2", password="Pass1234", role="admin"))
    await user_repo.create(UserCreate(username="User1", password="Pass1234", role="user"))

    # Should have 2 admins
    admin_count = await user_repo.count(filters={"role": "admin"})
    assert admin_count == 2

    # Can delete one admin
    await user_repo.delete(admin1.id)

    # Now should have 1 admin
    admin_count_after = await user_repo.count(filters={"role": "admin"})
    assert admin_count_after == 1

    # Cannot delete last admin
    with pytest.raises(ResourceConflictError):
        await user_repo.delete(admin2.id)
