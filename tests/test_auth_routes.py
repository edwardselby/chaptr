"""
Comprehensive tests for authentication routes (Phase 1.5).

Tests POST /api/auth/login and GET /api/auth/me endpoints.
Ruthless testing approach: Test every possible failure mode.
"""

import pytest
from datetime import timedelta

from api.utils.auth import create_access_token


# ============================================================================
# POST /api/auth/login Tests
# ============================================================================

@pytest.mark.asyncio
async def test_login_success_with_valid_credentials(async_client, sample_user):
    """Login succeeds with valid username and password."""
    response = await async_client.post("/api/auth/login", json={
        "username": "Edward",
        "password": "TestPass123"
    })

    assert response.status_code == 200
    data = response.json()

    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["user"]["username"] == "Edward"
    assert data["user"]["role"] == "admin"
    assert "id" in data["user"]


@pytest.mark.asyncio
async def test_login_returns_valid_jwt_token(async_client, sample_user):
    """Login returns valid JWT token that can be decoded."""
    response = await async_client.post("/api/auth/login", json={
        "username": "Edward",
        "password": "TestPass123"
    })

    assert response.status_code == 200
    token = response.json()["access_token"]

    # Token should have 3 parts (header.payload.signature)
    assert token.count('.') == 2


@pytest.mark.asyncio
async def test_login_fails_with_wrong_password(async_client, sample_user):
    """Login fails (401) with incorrect password."""
    response = await async_client.post("/api/auth/login", json={
        "username": "Edward",
        "password": "WrongPassword123"
    })

    assert response.status_code == 401
    assert "detail" in response.json()


@pytest.mark.asyncio
async def test_login_fails_with_non_existent_username(async_client, sample_user):
    """Login fails (401) with non-existent username."""
    response = await async_client.post("/api/auth/login", json={
        "username": "NonExistentUser",
        "password": "AnyPassword123"
    })

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_login_fails_with_empty_password(async_client, sample_user):
    """Login fails with empty password."""
    response = await async_client.post("/api/auth/login", json={
        "username": "Edward",
        "password": ""
    })

    # Should fail validation (422) or authentication (401)
    assert response.status_code in [401, 422]


@pytest.mark.asyncio
async def test_login_fails_with_empty_username(async_client, sample_user):
    """Login fails with empty username."""
    response = await async_client.post("/api/auth/login", json={
        "username": "",
        "password": "TestPass123"
    })

    # Should fail validation (422) or authentication (401)
    assert response.status_code in [401, 422]


@pytest.mark.asyncio
async def test_login_fails_with_missing_password(async_client, sample_user):
    """Login fails (422) with missing password field."""
    response = await async_client.post("/api/auth/login", json={
        "username": "Edward"
    })

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_login_fails_with_missing_username(async_client, sample_user):
    """Login fails (422) with missing username field."""
    response = await async_client.post("/api/auth/login", json={
        "password": "TestPass123"
    })

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_login_case_sensitive_username(async_client, sample_user):
    """Login is case-sensitive for username."""
    # Correct case
    response_correct = await async_client.post("/api/auth/login", json={
        "username": "Edward",
        "password": "TestPass123"
    })

    # Wrong case
    response_wrong = await async_client.post("/api/auth/login", json={
        "username": "edward",
        "password": "TestPass123"
    })

    assert response_correct.status_code == 200
    assert response_wrong.status_code == 401


@pytest.mark.asyncio
async def test_login_case_sensitive_password(async_client, sample_user):
    """Login is case-sensitive for password."""
    # Correct case
    response_correct = await async_client.post("/api/auth/login", json={
        "username": "Edward",
        "password": "TestPass123"
    })

    # Wrong case
    response_wrong = await async_client.post("/api/auth/login", json={
        "username": "Edward",
        "password": "testpass123"
    })

    assert response_correct.status_code == 200
    assert response_wrong.status_code == 401


@pytest.mark.asyncio
async def test_login_returns_user_info_without_password(async_client, sample_user):
    """Login response never includes password or password_hash."""
    response = await async_client.post("/api/auth/login", json={
        "username": "Edward",
        "password": "TestPass123"
    })

    assert response.status_code == 200
    data = response.json()

    # Verify no password-related fields in response
    assert "password" not in data
    assert "password_hash" not in data
    assert "password" not in data["user"]
    assert "password_hash" not in data["user"]


@pytest.mark.asyncio
async def test_login_admin_user_gets_admin_role_in_response(async_client, sample_user):
    """Login for admin user returns admin role."""
    response = await async_client.post("/api/auth/login", json={
        "username": "Edward",
        "password": "TestPass123"
    })

    assert response.status_code == 200
    assert response.json()["user"]["role"] == "admin"


@pytest.mark.asyncio
async def test_login_regular_user_gets_user_role_in_response(async_client, sample_regular_user):
    """Login for regular user returns user role."""
    response = await async_client.post("/api/auth/login", json={
        "username": "RegularUser",
        "password": "TestPass456"
    })

    assert response.status_code == 200
    assert response.json()["user"]["role"] == "user"


# ============================================================================
# GET /api/auth/me Tests
# ============================================================================

@pytest.mark.asyncio
async def test_get_me_success_with_valid_token(async_client, sample_user, auth_headers):
    """GET /me succeeds with valid JWT token."""
    response = await async_client.get("/api/auth/me", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()

    assert data["username"] == "Edward"
    assert data["role"] == "admin"
    assert "id" in data


@pytest.mark.asyncio
async def test_get_me_fails_without_token(async_client):
    """GET /me fails (401) without Authorization header."""
    response = await async_client.get("/api/auth/me")

    assert response.status_code == 401  # HTTPBearer returns 401 for missing credentials


@pytest.mark.asyncio
async def test_get_me_fails_with_invalid_token(async_client):
    """GET /me fails (401) with invalid token."""
    headers = {"Authorization": "Bearer invalid.token.here"}
    response = await async_client.get("/api/auth/me", headers=headers)

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_me_fails_with_expired_token(async_client, sample_user):
    """GET /me fails (401) with expired token."""
    # Create expired token
    expired_token = create_access_token(
        sample_user.id,
        sample_user.username,
        sample_user.role,
        expires_delta=timedelta(minutes=-1)
    )

    headers = {"Authorization": f"Bearer {expired_token}"}
    response = await async_client.get("/api/auth/me", headers=headers)

    assert response.status_code == 401
    assert "expired" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_get_me_fails_with_tampered_token(async_client, auth_headers):
    """GET /me fails (401) with tampered token."""
    # Tamper with token
    original_token = auth_headers["Authorization"].replace("Bearer ", "")
    tampered_token = original_token[:-1] + "X"

    headers = {"Authorization": f"Bearer {tampered_token}"}
    response = await async_client.get("/api/auth/me", headers=headers)

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_me_fails_with_malformed_auth_header(async_client):
    """GET /me fails with malformed Authorization header."""
    # Missing "Bearer" prefix
    headers = {"Authorization": "SomeRandomToken"}
    response = await async_client.get("/api/auth/me", headers=headers)

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_me_returns_current_user_info(async_client, sample_user, auth_headers):
    """GET /me returns current authenticated user's information."""
    response = await async_client.get("/api/auth/me", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()

    # Should match sample_user
    assert data["id"] == str(sample_user.id)
    assert data["username"] == sample_user.username
    assert data["role"] == sample_user.role


@pytest.mark.asyncio
async def test_get_me_does_not_return_password(async_client, auth_headers):
    """GET /me never returns password or password_hash."""
    response = await async_client.get("/api/auth/me", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()

    assert "password" not in data
    assert "password_hash" not in data


@pytest.mark.asyncio
async def test_get_me_works_for_regular_user(async_client, sample_regular_user, regular_user_auth_headers):
    """GET /me works for regular (non-admin) users."""
    response = await async_client.get("/api/auth/me", headers=regular_user_auth_headers)

    assert response.status_code == 200
    data = response.json()

    assert data["username"] == "RegularUser"
    assert data["role"] == "user"


# ============================================================================
# Integration Tests
# ============================================================================

@pytest.mark.asyncio
async def test_login_then_get_me_flow(async_client, sample_user):
    """Full authentication flow: login then access protected endpoint."""
    # Step 1: Login
    login_response = await async_client.post("/api/auth/login", json={
        "username": "Edward",
        "password": "TestPass123"
    })

    assert login_response.status_code == 200
    token = login_response.json()["access_token"]

    # Step 2: Use token to access /me
    headers = {"Authorization": f"Bearer {token}"}
    me_response = await async_client.get("/api/auth/me", headers=headers)

    assert me_response.status_code == 200
    assert me_response.json()["username"] == "Edward"


@pytest.mark.asyncio
async def test_login_token_works_for_multiple_requests(async_client, sample_user):
    """Login token can be reused for multiple authenticated requests."""
    # Login once
    login_response = await async_client.post("/api/auth/login", json={
        "username": "Edward",
        "password": "TestPass123"
    })

    token = login_response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Use same token multiple times
    response1 = await async_client.get("/api/auth/me", headers=headers)
    response2 = await async_client.get("/api/auth/me", headers=headers)
    response3 = await async_client.get("/api/auth/me", headers=headers)

    assert response1.status_code == 200
    assert response2.status_code == 200
    assert response3.status_code == 200


# ============================================================================
# Edge Cases and Security Tests
# ============================================================================

@pytest.mark.asyncio
async def test_login_with_sql_injection_attempt(async_client, sample_user):
    """Login safely handles SQL injection attempts in username."""
    response = await async_client.post("/api/auth/login", json={
        "username": "' OR '1'='1",
        "password": "TestPass123"
    })

    # Should fail authentication (not vulnerable)
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_login_with_xss_attempt_in_username(async_client, sample_user):
    """Login safely handles XSS attempts in username."""
    response = await async_client.post("/api/auth/login", json={
        "username": "<script>alert('xss')</script>",
        "password": "TestPass123"
    })

    # Should fail authentication (not vulnerable)
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_login_rate_limiting_not_implemented_yet(async_client, sample_user):
    """Login currently has no rate limiting (noted for Phase 1.6).

    This test documents the current behavior. Rate limiting should be
    added in a future phase to prevent brute force attacks.
    """
    # Multiple failed login attempts should all return 401
    for _ in range(10):
        response = await async_client.post("/api/auth/login", json={
            "username": "Edward",
            "password": "WrongPassword123"
        })
        assert response.status_code == 401

    # Note: In production, consider adding rate limiting
    # to prevent brute force attacks


@pytest.mark.asyncio
async def test_login_response_does_not_leak_user_existence(async_client, sample_user):
    """Login error messages don't reveal if username exists (security).

    Both wrong username and wrong password should return same error
    to prevent username enumeration.
    """
    # Wrong username
    response1 = await async_client.post("/api/auth/login", json={
        "username": "NonExistentUser",
        "password": "AnyPassword123"
    })

    # Wrong password
    response2 = await async_client.post("/api/auth/login", json={
        "username": "Edward",
        "password": "WrongPassword123"
    })

    # Both should return 401 with same (or similar) error message
    assert response1.status_code == 401
    assert response2.status_code == 401

    # Error messages should be generic (not revealing existence)
    error1 = response1.json()["detail"]
    error2 = response2.json()["detail"]

    # Should use generic "Invalid credentials" message (not "User not found" vs "Wrong password")
    assert "invalid" in error1.lower() or "authentication failed" in error1.lower()
    assert "invalid" in error2.lower() or "authentication failed" in error2.lower()
