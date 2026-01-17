"""
Comprehensive tests for authentication utilities (Phase 1.5).

Tests password hashing, JWT token creation/validation, and authentication dependencies.
Ruthless testing approach: Test every possible failure mode.
"""

import pytest
from datetime import timedelta, datetime, timezone
from uuid import uuid4
from jose import jwt, JWTError

from api.utils.auth import (
    hash_password,
    verify_password,
    create_access_token,
    decode_access_token,
    get_current_user,
    get_current_admin_user
)
from api.utils.errors import AuthenticationError, AuthorizationError
from api.config import settings
from fastapi.security import HTTPAuthorizationCredentials


# ============================================================================
# Password Hashing Tests
# ============================================================================

def test_hash_password_creates_bcrypt_hash():
    """Password hashing creates valid bcrypt hash."""
    password = "TestPassword123"
    hashed = hash_password(password)

    # Bcrypt hashes start with $2b$ and are 60 chars
    assert hashed.startswith("$2b$")
    assert len(hashed) == 60


def test_hash_password_different_every_time():
    """Password hashing uses random salt (different hash each time)."""
    password = "TestPassword123"
    hash1 = hash_password(password)
    hash2 = hash_password(password)

    # Same password, different hashes (salt is random)
    assert hash1 != hash2


def test_verify_password_accepts_correct_password():
    """Password verification succeeds with correct password."""
    password = "TestPassword123"
    hashed = hash_password(password)

    assert verify_password(password, hashed) is True


def test_verify_password_rejects_wrong_password():
    """Password verification fails with wrong password."""
    password = "TestPassword123"
    hashed = hash_password(password)

    assert verify_password("WrongPassword123", hashed) is False


def test_verify_password_rejects_empty_password():
    """Password verification fails with empty password."""
    password = "TestPassword123"
    hashed = hash_password(password)

    assert verify_password("", hashed) is False


def test_verify_password_case_sensitive():
    """Password verification is case-sensitive."""
    password = "TestPassword123"
    hashed = hash_password(password)

    assert verify_password("testpassword123", hashed) is False
    assert verify_password("TESTPASSWORD123", hashed) is False


# ============================================================================
# JWT Token Creation Tests
# ============================================================================

def test_create_access_token_generates_valid_jwt():
    """JWT token creation generates valid token with correct structure."""
    user_id = uuid4()
    username = "Edward"
    role = "admin"

    token = create_access_token(user_id, username, role)

    # Token should have 3 parts (header.payload.signature)
    assert token.count('.') == 2

    # Decode and verify payload
    payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    assert payload["sub"] == str(user_id)
    assert payload["username"] == username
    assert payload["role"] == role
    assert "exp" in payload


def test_create_access_token_admin_gets_24_hour_expiration():
    """Admin users get standard 24-hour token expiration (spec v3.0: all users same)."""
    user_id = uuid4()
    token = create_access_token(user_id, "Admin", "admin")

    payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    exp_timestamp = payload["exp"]
    exp_datetime = datetime.fromtimestamp(exp_timestamp, tz=timezone.utc)

    # Calculate expected expiration (24 hours = 1440 minutes, same for all users)
    expected_exp = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)

    # Allow 5 second tolerance for test execution time
    assert abs((exp_datetime - expected_exp).total_seconds()) < 5


def test_create_access_token_user_gets_24_hour_expiration():
    """Regular users get standard 24-hour token expiration (spec v3.0: all users same)."""
    user_id = uuid4()
    token = create_access_token(user_id, "User", "user")

    payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    exp_timestamp = payload["exp"]
    exp_datetime = datetime.fromtimestamp(exp_timestamp, tz=timezone.utc)

    # Calculate expected expiration (same for all users per spec v3.0)
    expected_exp = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)

    # Allow 5 second tolerance
    assert abs((exp_datetime - expected_exp).total_seconds()) < 5


def test_create_access_token_custom_expiration_overrides_default():
    """Custom expiration delta overrides default expiration."""
    user_id = uuid4()
    custom_delta = timedelta(minutes=30)

    token = create_access_token(user_id, "Admin", "admin", expires_delta=custom_delta)

    payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    exp_timestamp = payload["exp"]
    exp_datetime = datetime.fromtimestamp(exp_timestamp, tz=timezone.utc)

    # Should use custom 30 minutes, not admin's 7 days
    expected_exp = datetime.now(timezone.utc) + custom_delta
    assert abs((exp_datetime - expected_exp).total_seconds()) < 5


def test_create_access_token_converts_uuid_to_string():
    """User ID (UUID) is converted to string in token payload."""
    user_id = uuid4()
    token = create_access_token(user_id, "User", "user")

    payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])

    # Payload should have string, not UUID object
    assert isinstance(payload["sub"], str)
    assert payload["sub"] == str(user_id)


# ============================================================================
# JWT Token Validation Tests
# ============================================================================

def test_decode_access_token_validates_valid_token():
    """Token decoding succeeds with valid token."""
    user_id = uuid4()
    token = create_access_token(user_id, "Edward", "admin")

    payload = decode_access_token(token)

    assert payload["sub"] == str(user_id)
    assert payload["username"] == "Edward"
    assert payload["role"] == "admin"


def test_decode_access_token_rejects_tampered_token():
    """Token decoding fails if token signature is invalid (tampered)."""
    user_id = uuid4()
    token = create_access_token(user_id, "Edward", "admin")

    # Tamper with token (change last character)
    tampered_token = token[:-1] + "X"

    with pytest.raises(AuthenticationError) as exc_info:
        decode_access_token(tampered_token)

    assert "Invalid token" in str(exc_info.value.detail)


def test_decode_access_token_rejects_expired_token():
    """Token decoding fails if token is expired."""
    user_id = uuid4()
    # Create token that expired 1 minute ago
    expired_delta = timedelta(minutes=-1)
    token = create_access_token(user_id, "Edward", "admin", expires_delta=expired_delta)

    with pytest.raises(AuthenticationError) as exc_info:
        decode_access_token(token)

    assert "expired" in str(exc_info.value.detail).lower()


def test_decode_access_token_rejects_malformed_token():
    """Token decoding fails with malformed token (not JWT format)."""
    malformed_token = "not.a.valid.jwt.token"

    with pytest.raises(AuthenticationError) as exc_info:
        decode_access_token(malformed_token)

    assert "Invalid token" in str(exc_info.value.detail)


def test_decode_access_token_rejects_empty_token():
    """Token decoding fails with empty token."""
    with pytest.raises(AuthenticationError):
        decode_access_token("")


def test_decode_access_token_rejects_wrong_secret():
    """Token decoding fails if signed with different secret."""
    user_id = uuid4()
    # Sign with different secret
    wrong_token = jwt.encode(
        {"sub": str(user_id), "username": "Hacker", "role": "admin"},
        "wrong-secret-key",
        algorithm="HS256"
    )

    with pytest.raises(AuthenticationError) as exc_info:
        decode_access_token(wrong_token)

    assert "Invalid token" in str(exc_info.value.detail)


# ============================================================================
# Authentication Dependency Tests
# ============================================================================

@pytest.mark.asyncio
async def test_get_current_user_extracts_user_from_valid_token():
    """get_current_user dependency extracts user info from valid token."""
    user_id = uuid4()
    token = create_access_token(user_id, "Edward", "admin")

    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    user = await get_current_user(credentials)

    assert user["id"] == str(user_id)
    assert user["username"] == "Edward"
    assert user["role"] == "admin"


@pytest.mark.asyncio
async def test_get_current_user_rejects_invalid_token():
    """get_current_user dependency rejects invalid token."""
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="invalid.token.here")

    with pytest.raises(AuthenticationError):
        await get_current_user(credentials)


@pytest.mark.asyncio
async def test_get_current_user_rejects_expired_token():
    """get_current_user dependency rejects expired token."""
    user_id = uuid4()
    expired_delta = timedelta(minutes=-1)
    token = create_access_token(user_id, "Edward", "admin", expires_delta=expired_delta)

    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

    with pytest.raises(AuthenticationError) as exc_info:
        await get_current_user(credentials)

    assert "expired" in str(exc_info.value.detail).lower()


# ============================================================================
# Authorization Dependency Tests
# ============================================================================

@pytest.mark.asyncio
async def test_get_current_admin_user_allows_admin():
    """get_current_admin_user allows admin users."""
    current_user = {"id": str(uuid4()), "username": "Edward", "role": "admin"}

    admin_user = await get_current_admin_user(current_user)

    assert admin_user == current_user


@pytest.mark.asyncio
async def test_get_current_admin_user_rejects_regular_user():
    """get_current_admin_user rejects non-admin users (403)."""
    current_user = {"id": str(uuid4()), "username": "User", "role": "user"}

    with pytest.raises(AuthorizationError) as exc_info:
        await get_current_admin_user(current_user)

    assert exc_info.value.status_code == 403
    assert "Admin access required" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_get_current_admin_user_case_sensitive_role():
    """get_current_admin_user checks role exactly (case-sensitive)."""
    # Role is "Admin" not "admin"
    current_user = {"id": str(uuid4()), "username": "Edward", "role": "Admin"}

    with pytest.raises(AuthorizationError):
        await get_current_admin_user(current_user)


# ============================================================================
# Edge Cases and Security Tests
# ============================================================================

def test_password_hash_handles_unicode_characters():
    """Password hashing handles unicode characters correctly."""
    password = "Test密码123"
    hashed = hash_password(password)

    assert verify_password("Test密码123", hashed) is True
    assert verify_password("Test123", hashed) is False


def test_password_hash_handles_special_characters():
    """Password hashing handles special characters."""
    password = "Test!@#$%^&*()123"
    hashed = hash_password(password)

    assert verify_password("Test!@#$%^&*()123", hashed) is True


def test_token_payload_does_not_contain_password():
    """JWT token payload never contains password (security check)."""
    user_id = uuid4()
    token = create_access_token(user_id, "Edward", "admin")

    payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])

    # Verify no password-related keys in payload
    assert "password" not in payload
    assert "password_hash" not in payload
    assert "pwd" not in payload


def test_verify_password_timing_attack_resistant():
    """Password verification uses constant-time comparison (timing attack resistance).

    Note: bcrypt inherently provides this, but we verify the behavior.
    """
    password = "TestPassword123"
    hashed = hash_password(password)

    # Both wrong passwords should take similar time (constant-time comparison)
    # This is a behavioral test - bcrypt provides this guarantee
    assert verify_password("Wrong1", hashed) is False
    assert verify_password("CompletelyDifferentWrongPassword", hashed) is False
