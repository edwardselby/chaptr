"""
Custom exceptions for CHAPTR API.

Provides domain-specific exceptions that map to appropriate HTTP status codes
for consistent error handling across the application.
"""

from fastapi import HTTPException
from typing import Any


class ResourceNotFoundError(HTTPException):
    """
    Raised when a requested resource does not exist.

    Maps to HTTP 404 Not Found.

    :Example:

    >>> raise ResourceNotFoundError("Account not found")
    """

    def __init__(self, detail: str = "Resource not found"):
        """
        Initialize ResourceNotFoundError.

        :param detail: Error message describing what was not found
        :type detail: str
        """
        super().__init__(status_code=404, detail=detail)


class ResourceConflictError(HTTPException):
    """
    Raised when a request conflicts with current resource state.

    Maps to HTTP 409 Conflict.

    :Example:

    >>> raise ResourceConflictError("Cannot archive default account")
    """

    def __init__(self, detail: str = "Resource conflict"):
        """
        Initialize ResourceConflictError.

        :param detail: Error message describing the conflict
        :type detail: str
        """
        super().__init__(status_code=409, detail=detail)


class ValidationError(HTTPException):
    """
    Raised when request data fails business logic validation.

    Maps to HTTP 422 Unprocessable Entity.
    Distinct from Pydantic validation (which returns 422 automatically).
    Used for business rule violations (e.g., no account available for event).

    :Example:

    >>> raise ValidationError("No account could be resolved for event")
    """

    def __init__(self, detail: str = "Validation error"):
        """
        Initialize ValidationError.

        :param detail: Error message describing validation failure
        :type detail: str
        """
        super().__init__(status_code=422, detail=detail)
