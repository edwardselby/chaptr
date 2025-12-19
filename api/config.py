"""
Application configuration and MongoDB connection management.

Provides centralized settings management and singleton MongoDB client for the application.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from motor.motor_asyncio import AsyncIOMotorClient
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.

    Uses Pydantic Settings for type-safe configuration management.
    Reads from .env file if present.
    """

    # MongoDB Configuration
    mongodb_url: str = "mongodb://localhost:27017"
    mongodb_db_name: str = "chaptr"

    # Application Settings
    debug: bool = True
    environment: str = "development"

    # Security
    secret_key: str = "dev-secret-key-change-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30

    # Multi-Currency
    base_currency: str = "GBP"

    # CORS
    allowed_origins: str = "http://localhost:3000,http://localhost:8080"

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False
    )

    @property
    def cors_origins(self) -> list[str]:
        """Parse CORS origins from comma-separated string."""
        return [origin.strip() for origin in self.allowed_origins.split(",")]


# Global settings instance
settings = Settings()


class MongoDB:
    """
    MongoDB connection manager using singleton pattern.

    Ensures one MongoDB client for the entire application, providing
    connection pooling and efficient resource management.
    """

    client: Optional[AsyncIOMotorClient] = None

    @classmethod
    def connect(cls):
        """
        Initialize MongoDB connection.

        Called during application startup.
        """
        try:
            cls.client = AsyncIOMotorClient(settings.mongodb_url)
            logger.info(f"MongoDB client initialized for {settings.mongodb_url}")
        except Exception as e:
            logger.error(f"Failed to initialize MongoDB client: {e}")
            raise

    @classmethod
    def close(cls):
        """
        Close MongoDB connection.

        Called during application shutdown.
        """
        if cls.client:
            cls.client.close()
            logger.info("MongoDB connection closed")

    @classmethod
    def get_database(cls):
        """
        Get the application database instance.

        Returns:
            AsyncIOMotorDatabase: The configured database

        Raises:
            RuntimeError: If client not initialized
        """
        if not cls.client:
            raise RuntimeError("MongoDB client not initialized. Call MongoDB.connect() first.")
        return cls.client[settings.mongodb_db_name]

    @classmethod
    async def ping(cls) -> bool:
        """
        Test MongoDB connection health.

        Returns:
            bool: True if connection successful, False otherwise
        """
        try:
            if not cls.client:
                return False
            await cls.client.admin.command('ping')
            return True
        except Exception as e:
            logger.warning(f"MongoDB ping failed: {e}")
            return False
