"""
Utility functions and helpers for CHAPTR API.

Provides common utilities for database operations, error handling,
and business logic helpers.
"""

from api.utils.errors import (
    ResourceNotFoundError,
    ResourceConflictError,
    ValidationError,
)
from api.utils.db import (
    to_uuid,
    to_str,
    utc_now,
    generate_id,
    get_or_404,
    resolve_account_id,
    get_rate_to_base,
)

__all__ = [
    # Errors
    "ResourceNotFoundError",
    "ResourceConflictError",
    "ValidationError",
    # Database helpers
    "to_uuid",
    "to_str",
    "utc_now",
    "generate_id",
    "get_or_404",
    "resolve_account_id",
    "get_rate_to_base",
]
