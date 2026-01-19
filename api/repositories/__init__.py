"""
Repository layer for CHAPTR API.

Provides data access layer with separation of concerns between
database operations and HTTP request handling.
"""

from api.repositories.base import BaseRepository
from api.repositories.global_config import GlobalConfigRepository

__all__ = [
    "BaseRepository",
    "GlobalConfigRepository",
]
