"""
Comprehensive tests for create_first_user.py script (Task 233).

Tests the first user initialization CLI command that solves
the authentication bootstrap problem.

Test Categories:
- User creation with valid credentials
- Password validation (strength requirements)
- Duplicate prevention (no users must exist)
- Environment variable mode
- Username validation
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

# Import the functions we want to test
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from scripts.create_first_user import check_existing_users, get_credentials
from api.models import UserCreate, UserRole
from api.repositories.users import UserRepository
from pydantic import ValidationError


# ============================================================================
# Helper Functions Tests
# ============================================================================

@pytest.mark.asyncio
async def test_check_existing_users_returns_false_when_no_users():
    """check_existing_users returns False when database is empty."""
    # Mock repository with no users
    mock_repo = AsyncMock(spec=UserRepository)
    mock_repo.count = AsyncMock(return_value=0)

    result = await check_existing_users(mock_repo)

    assert result is False
    mock_repo.count.assert_called_once()


@pytest.mark.asyncio
async def test_check_existing_users_returns_true_when_users_exist():
    """check_existing_users returns True when any users exist."""
    # Mock repository with 1 user
    mock_repo = AsyncMock(spec=UserRepository)
    mock_repo.count = AsyncMock(return_value=1)

    result = await check_existing_users(mock_repo)

    assert result is True
    mock_repo.count.assert_called_once()


@pytest.mark.asyncio
async def test_check_existing_users_returns_true_with_multiple_users():
    """check_existing_users returns True when multiple users exist."""
    # Mock repository with 5 users
    mock_repo = AsyncMock(spec=UserRepository)
    mock_repo.count = AsyncMock(return_value=5)

    result = await check_existing_users(mock_repo)

    assert result is True
    mock_repo.count.assert_called_once()


# ============================================================================
# Environment Variable Mode Tests
# ============================================================================

@pytest.mark.asyncio
async def test_get_credentials_from_env_vars():
    """get_credentials uses environment variables when available."""
    with patch.dict(os.environ, {
        'ADMIN_USERNAME': 'TestAdmin',
        'ADMIN_PASSWORD': 'TestPass123'
    }):
        with patch('builtins.print'):  # Suppress print output
            username, password = await get_credentials()

    assert username == 'TestAdmin'
    assert password == 'TestPass123'


@pytest.mark.asyncio
async def test_get_credentials_strips_whitespace_from_env_username():
    """get_credentials strips whitespace from ADMIN_USERNAME."""
    with patch.dict(os.environ, {
        'ADMIN_USERNAME': '  TestAdmin  ',
        'ADMIN_PASSWORD': 'TestPass123'
    }):
        with patch('builtins.print'):
            username, password = await get_credentials()

    assert username == 'TestAdmin'
    assert password == 'TestPass123'


@pytest.mark.asyncio
async def test_get_credentials_rejects_empty_username_from_env():
    """get_credentials exits if ADMIN_USERNAME is empty."""
    with patch.dict(os.environ, {
        'ADMIN_USERNAME': '   ',  # Only whitespace
        'ADMIN_PASSWORD': 'TestPass123'
    }):
        with patch('builtins.print'), \
             pytest.raises(SystemExit) as exc_info:
            await get_credentials()

    assert exc_info.value.code == 1


@pytest.mark.asyncio
async def test_get_credentials_falls_back_to_interactive_when_env_incomplete():
    """get_credentials uses interactive mode if env vars incomplete."""
    # Only username set, password missing
    with patch.dict(os.environ, {'ADMIN_USERNAME': 'TestAdmin'}):
        with patch('scripts.create_first_user.input', return_value='InteractiveUser'), \
             patch('scripts.create_first_user.getpass', side_effect=['Pass123', 'Pass123']), \
             patch('builtins.print'):
            username, password = await get_credentials()

    assert username == 'InteractiveUser'
    assert password == 'Pass123'


# ============================================================================
# Interactive Mode Tests
# ============================================================================

@pytest.mark.asyncio
async def test_get_credentials_interactive_mode_success():
    """get_credentials prompts user in interactive mode."""
    with patch.dict(os.environ, {}, clear=True):  # No env vars
        with patch('scripts.create_first_user.input', return_value='InteractiveAdmin'), \
             patch('scripts.create_first_user.getpass', side_effect=['SecurePass123', 'SecurePass123']), \
             patch('builtins.print'):
            username, password = await get_credentials()

    assert username == 'InteractiveAdmin'
    assert password == 'SecurePass123'


@pytest.mark.asyncio
async def test_get_credentials_interactive_rejects_empty_username():
    """get_credentials exits if interactive username is empty."""
    with patch.dict(os.environ, {}, clear=True):
        with patch('scripts.create_first_user.input', return_value=''), \
             patch('builtins.print'), \
             pytest.raises(SystemExit) as exc_info:
            await get_credentials()

    assert exc_info.value.code == 1


@pytest.mark.asyncio
async def test_get_credentials_interactive_rejects_mismatched_passwords():
    """get_credentials exits if password confirmation doesn't match."""
    with patch.dict(os.environ, {}, clear=True):
        with patch('scripts.create_first_user.input', return_value='TestUser'), \
             patch('scripts.create_first_user.getpass', side_effect=['Pass123', 'Different456']), \
             patch('builtins.print'), \
             pytest.raises(SystemExit) as exc_info:
            await get_credentials()

    assert exc_info.value.code == 1


# ============================================================================
# Password Validation Tests
# ============================================================================

def test_password_validation_rejects_too_short():
    """UserCreate rejects passwords shorter than 8 characters."""
    with pytest.raises(ValidationError) as exc_info:
        UserCreate(
            username="TestUser",
            password="Short1",  # Only 6 chars
            role=UserRole.ADMIN
        )

    errors = exc_info.value.errors()
    assert any("at least 8 characters" in str(error) for error in errors)


def test_password_validation_rejects_no_uppercase():
    """UserCreate rejects passwords without uppercase letters."""
    with pytest.raises(ValidationError) as exc_info:
        UserCreate(
            username="TestUser",
            password="lowercase123",
            role=UserRole.ADMIN
        )

    errors = exc_info.value.errors()
    assert any("uppercase" in str(error).lower() for error in errors)


def test_password_validation_rejects_no_lowercase():
    """UserCreate rejects passwords without lowercase letters."""
    with pytest.raises(ValidationError) as exc_info:
        UserCreate(
            username="TestUser",
            password="UPPERCASE123",
            role=UserRole.ADMIN
        )

    errors = exc_info.value.errors()
    assert any("lowercase" in str(error).lower() for error in errors)


def test_password_validation_rejects_no_digit():
    """UserCreate rejects passwords without digits."""
    with pytest.raises(ValidationError) as exc_info:
        UserCreate(
            username="TestUser",
            password="NoDigitsHere",
            role=UserRole.ADMIN
        )

    errors = exc_info.value.errors()
    assert any("digit" in str(error).lower() for error in errors)


def test_password_validation_accepts_valid_password():
    """UserCreate accepts passwords meeting all requirements."""
    # Should not raise
    user_data = UserCreate(
        username="TestUser",
        password="ValidPass123",
        role=UserRole.ADMIN
    )

    assert user_data.username == "TestUser"
    assert user_data.password == "ValidPass123"
    assert user_data.role == UserRole.ADMIN


# ============================================================================
# Integration Tests (Mocked)
# ============================================================================

@pytest.mark.asyncio
async def test_script_prevents_duplicate_user_creation():
    """Script exits if any users already exist in database."""
    from scripts.create_first_user import create_admin_user

    # Mock MongoDB and repository
    with patch('scripts.create_first_user.MongoDB') as mock_mongodb, \
         patch('scripts.create_first_user.UserRepository') as mock_repo_class, \
         patch('builtins.print'), \
         pytest.raises(SystemExit) as exc_info:

        mock_db = MagicMock()
        mock_mongodb.get_database.return_value = mock_db

        mock_repo = AsyncMock()
        mock_repo.count = AsyncMock(return_value=1)  # Users exist
        mock_repo_class.return_value = mock_repo

        await create_admin_user("TestUser", "TestPass123")

    assert exc_info.value.code == 1
    mock_repo.count.assert_called_once()


@pytest.mark.asyncio
async def test_script_creates_user_when_database_empty():
    """Script creates super_admin user when no users exist (multi-tenancy bootstrap)."""
    from scripts.create_first_user import create_admin_user
    from api.models import User

    # Mock MongoDB and repository
    with patch('scripts.create_first_user.MongoDB') as mock_mongodb, \
         patch('scripts.create_first_user.UserRepository') as mock_repo_class, \
         patch('builtins.print'):

        mock_db = MagicMock()
        mock_mongodb.get_database.return_value = mock_db

        # Create mock user to return (super_admin with tenant_id = user_id)
        user_id = uuid4()
        mock_user = User(
            id=user_id,
            username="TestAdmin",
            password_hash="$2b$12$fake_hash",
            role=UserRole.SUPER_ADMIN,
            tenant_id=user_id,  # Multi-tenancy: super_admin is self-anchored
            created_at=MagicMock(),
            updated_at=MagicMock()
        )

        mock_repo = AsyncMock()
        mock_repo.count = AsyncMock(return_value=0)  # No users
        mock_repo.create = AsyncMock(return_value=mock_user)
        mock_repo_class.return_value = mock_repo

        await create_admin_user("TestAdmin", "ValidPass123")

        # Verify user was created as super_admin
        mock_repo.create.assert_called_once()
        call_args = mock_repo.create.call_args[0][0]
        assert call_args.username == "TestAdmin"
        assert call_args.password == "ValidPass123"
        assert call_args.role == UserRole.SUPER_ADMIN


@pytest.mark.asyncio
async def test_script_rejects_invalid_password():
    """Script exits if password validation fails."""
    from scripts.create_first_user import create_admin_user

    # Mock MongoDB and repository
    with patch('scripts.create_first_user.MongoDB') as mock_mongodb, \
         patch('scripts.create_first_user.UserRepository') as mock_repo_class, \
         patch('builtins.print'), \
         pytest.raises(SystemExit) as exc_info:

        mock_db = MagicMock()
        mock_mongodb.get_database.return_value = mock_db

        mock_repo = AsyncMock()
        mock_repo.count = AsyncMock(return_value=0)  # No users
        mock_repo_class.return_value = mock_repo

        # Try to create with weak password
        await create_admin_user("TestAdmin", "weak")

    assert exc_info.value.code == 1


# ============================================================================
# Edge Cases and Security Tests
# ============================================================================

@pytest.mark.asyncio
async def test_script_handles_database_connection_failure():
    """Script handles MongoDB connection failures with user-friendly error."""
    from scripts.create_first_user import create_admin_user

    with patch('scripts.create_first_user.MongoDB') as mock_mongodb, \
         patch('builtins.print'):

        # Simulate connection failure
        mock_mongodb.connect.side_effect = Exception("Connection refused")

        # Script catches connection errors and exits with code 3
        with pytest.raises(SystemExit) as exc_info:
            await create_admin_user("TestAdmin", "ValidPass123")

        assert exc_info.value.code == 3


@pytest.mark.asyncio
async def test_check_existing_users_handles_count_error():
    """check_existing_users handles database errors gracefully."""
    mock_repo = AsyncMock(spec=UserRepository)
    mock_repo.count = AsyncMock(side_effect=Exception("Database error"))

    with pytest.raises(Exception) as exc_info:
        await check_existing_users(mock_repo)

    assert "Database error" in str(exc_info.value)


def test_username_sanitization_in_user_create():
    """UserCreate accepts valid usernames."""
    # Valid username
    user_data = UserCreate(
        username="ValidUser123",
        password="SecurePass123",
        role=UserRole.ADMIN
    )

    assert user_data.username == "ValidUser123"


# ============================================================================
# Script Execution Tests (Argument Parsing)
# ============================================================================

def test_script_requires_confirm_flag():
    """Script requires --confirm flag to execute."""
    import argparse
    from scripts.create_first_user import main

    with patch('sys.argv', ['create_first_user.py']):  # No --confirm
        with pytest.raises(SystemExit) as exc_info:
            # ArgumentParser raises SystemExit(2) for missing required args
            main()

        # Exit code 2 indicates argument parsing error
        assert exc_info.value.code == 2


def test_script_help_flag_works():
    """Script displays help with -h flag."""
    from scripts.create_first_user import main

    with patch('sys.argv', ['create_first_user.py', '-h']):
        with pytest.raises(SystemExit) as exc_info:
            main()

        # Exit code 0 indicates successful help display
        assert exc_info.value.code == 0
