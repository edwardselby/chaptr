"""
Unit tests for api/utils/errors.py

Tests custom exception classes and their HTTP status code mappings.

CRITICAL: Incorrect status codes could confuse client error handling
and break the API contract.
"""

import pytest
from fastapi import HTTPException

from api.utils.errors import (
    ResourceNotFoundError,
    ResourceConflictError,
    ValidationError,
    AuthenticationError,
    AuthorizationError
)


# ============================================================================
# ResourceNotFoundError Tests
# ============================================================================

class TestResourceNotFoundError:
    """Tests for 404 Not Found exception."""

    def test_is_http_exception(self):
        """Verify it's an HTTPException subclass."""
        error = ResourceNotFoundError()
        assert isinstance(error, HTTPException)

    def test_status_code_is_404(self):
        """Verify status code is 404."""
        error = ResourceNotFoundError()
        assert error.status_code == 404

    def test_default_detail_message(self):
        """Verify default message is sensible."""
        error = ResourceNotFoundError()
        assert "not found" in error.detail.lower()

    def test_custom_detail_message(self):
        """Verify custom message is used."""
        error = ResourceNotFoundError("Account not found")
        assert error.detail == "Account not found"

    def test_can_be_raised_and_caught(self):
        """Verify exception can be raised and caught properly."""
        with pytest.raises(HTTPException) as exc_info:
            raise ResourceNotFoundError("Event not found")

        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == "Event not found"


# ============================================================================
# ResourceConflictError Tests
# ============================================================================

class TestResourceConflictError:
    """Tests for 409 Conflict exception."""

    def test_is_http_exception(self):
        """Verify it's an HTTPException subclass."""
        error = ResourceConflictError()
        assert isinstance(error, HTTPException)

    def test_status_code_is_409(self):
        """Verify status code is 409."""
        error = ResourceConflictError()
        assert error.status_code == 409

    def test_default_detail_message(self):
        """Verify default message indicates conflict."""
        error = ResourceConflictError()
        assert "conflict" in error.detail.lower()

    def test_custom_detail_message(self):
        """Verify custom message is used."""
        error = ResourceConflictError("Cannot archive default account")
        assert error.detail == "Cannot archive default account"

    def test_used_for_business_rule_violations(self):
        """Verify appropriate for business logic conflicts."""
        error = ResourceConflictError("Cannot delete account with events")
        assert error.status_code == 409
        assert "Cannot delete" in error.detail


# ============================================================================
# ValidationError Tests
# ============================================================================

class TestValidationError:
    """Tests for 422 Unprocessable Entity exception."""

    def test_is_http_exception(self):
        """Verify it's an HTTPException subclass."""
        error = ValidationError()
        assert isinstance(error, HTTPException)

    def test_status_code_is_422(self):
        """
        Verify status code is 422.

        CRITICAL: Must be 422 (not 400) to match FastAPI's Pydantic validation.
        """
        error = ValidationError()
        assert error.status_code == 422

    def test_default_detail_message(self):
        """Verify default message indicates validation issue."""
        error = ValidationError()
        assert "validation" in error.detail.lower() or "error" in error.detail.lower()

    def test_custom_detail_message(self):
        """Verify custom message is used."""
        error = ValidationError("No account could be resolved for event")
        assert error.detail == "No account could be resolved for event"

    def test_distinct_from_pydantic_validation(self):
        """
        Document that this is for business logic validation, not schema validation.

        Pydantic handles schema validation automatically (field types, required fields).
        This exception is for business rules (e.g., "account must exist for event").
        """
        error = ValidationError("Story end_date must be after start_date")
        assert error.status_code == 422


# ============================================================================
# AuthenticationError Tests
# ============================================================================

class TestAuthenticationError:
    """Tests for 401 Unauthorized exception."""

    def test_is_http_exception(self):
        """Verify it's an HTTPException subclass."""
        error = AuthenticationError()
        assert isinstance(error, HTTPException)

    def test_status_code_is_401(self):
        """
        Verify status code is 401.

        CRITICAL: Must be 401 (not 403) for authentication failures.
        401 = "Who are you?" (not authenticated)
        403 = "I know who you are but you're not allowed" (not authorized)
        """
        error = AuthenticationError()
        assert error.status_code == 401

    def test_default_detail_message(self):
        """Verify default message indicates auth failure."""
        error = AuthenticationError()
        assert "authentication" in error.detail.lower() or "failed" in error.detail.lower()

    def test_custom_detail_for_invalid_credentials(self):
        """Verify works for invalid login."""
        error = AuthenticationError("Invalid credentials")
        assert error.detail == "Invalid credentials"

    def test_custom_detail_for_expired_token(self):
        """Verify works for expired JWT."""
        error = AuthenticationError("Token has expired")
        assert error.detail == "Token has expired"

    def test_custom_detail_for_missing_token(self):
        """Verify works for missing auth header."""
        error = AuthenticationError("Authorization header required")
        assert error.detail == "Authorization header required"


# ============================================================================
# AuthorizationError Tests
# ============================================================================

class TestAuthorizationError:
    """Tests for 403 Forbidden exception."""

    def test_is_http_exception(self):
        """Verify it's an HTTPException subclass."""
        error = AuthorizationError()
        assert isinstance(error, HTTPException)

    def test_status_code_is_403(self):
        """
        Verify status code is 403.

        CRITICAL: Must be 403 (not 401) for authorization failures.
        User is authenticated but lacks permission.
        """
        error = AuthorizationError()
        assert error.status_code == 403

    def test_default_detail_message(self):
        """Verify default message indicates permission issue."""
        error = AuthorizationError()
        assert "permission" in error.detail.lower() or "insufficient" in error.detail.lower()

    def test_custom_detail_for_admin_required(self):
        """Verify works for admin-only endpoints."""
        error = AuthorizationError("Admin access required")
        assert error.detail == "Admin access required"

    def test_custom_detail_for_role_violation(self):
        """Verify works for RBAC violations."""
        error = AuthorizationError("Insufficient permissions for this operation")
        assert "Insufficient permissions" in error.detail


# ============================================================================
# Cross-Cutting Tests
# ============================================================================

class TestExceptionHierarchy:
    """Tests verifying exception hierarchy and behavior."""

    def test_all_exceptions_are_http_exceptions(self):
        """All custom exceptions should inherit from HTTPException."""
        exceptions = [
            ResourceNotFoundError(),
            ResourceConflictError(),
            ValidationError(),
            AuthenticationError(),
            AuthorizationError()
        ]

        for exc in exceptions:
            assert isinstance(exc, HTTPException), f"{type(exc).__name__} should be HTTPException"

    def test_all_exceptions_have_distinct_status_codes(self):
        """Each exception should have a unique status code."""
        status_codes = {
            ResourceNotFoundError: 404,
            ResourceConflictError: 409,
            ValidationError: 422,
            AuthenticationError: 401,
            AuthorizationError: 403
        }

        seen_codes = set()
        for exc_class, expected_code in status_codes.items():
            exc = exc_class()
            assert exc.status_code == expected_code
            assert exc.status_code not in seen_codes, f"Duplicate status code: {exc.status_code}"
            seen_codes.add(exc.status_code)

    def test_exceptions_can_be_caught_by_base_class(self):
        """All exceptions can be caught as HTTPException."""
        def raise_not_found():
            raise ResourceNotFoundError("test")

        def raise_conflict():
            raise ResourceConflictError("test")

        def raise_validation():
            raise ValidationError("test")

        def raise_auth():
            raise AuthenticationError("test")

        def raise_authz():
            raise AuthorizationError("test")

        for func in [raise_not_found, raise_conflict, raise_validation, raise_auth, raise_authz]:
            with pytest.raises(HTTPException):
                func()


class TestExceptionUsagePatterns:
    """Tests demonstrating correct usage patterns."""

    def test_not_found_for_missing_entity(self):
        """ResourceNotFoundError for GET/PUT/DELETE on missing entity."""
        error = ResourceNotFoundError("Account abc-123 not found")
        assert error.status_code == 404

    def test_conflict_for_delete_with_references(self):
        """ResourceConflictError when deleting entity with references."""
        error = ResourceConflictError("Cannot delete account: 5 events reference it")
        assert error.status_code == 409

    def test_conflict_for_duplicate_default(self):
        """ResourceConflictError for business rule violation."""
        error = ResourceConflictError("Only one account can be default")
        assert error.status_code == 409

    def test_validation_for_business_rule(self):
        """ValidationError for business logic validation failure."""
        error = ValidationError("event_date cannot be before story start_date")
        assert error.status_code == 422

    def test_authentication_for_login_failure(self):
        """AuthenticationError for failed login attempt."""
        error = AuthenticationError("Invalid email or password")
        assert error.status_code == 401

    def test_authorization_for_admin_only(self):
        """AuthorizationError for non-admin accessing admin endpoint."""
        error = AuthorizationError("This endpoint requires admin privileges")
        assert error.status_code == 403
