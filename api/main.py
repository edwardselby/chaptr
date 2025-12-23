"""
CHAPTR API - Personal Finance Projection System

FastAPI application providing REST API for CHAPTR projection system.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging
from datetime import datetime

from api.config import settings, MongoDB
from api.utils.indexes import create_change_log_indexes

# Configure logging
logging.basicConfig(
    level=logging.INFO if not settings.debug else logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan context manager.

    Handles startup and shutdown events for the FastAPI application.
    Modern pattern replacing deprecated @app.on_event decorators.
    """
    # Startup
    logger.info("Starting CHAPTR API...")

    # Validate SECRET_KEY in production
    if settings.environment == "production" and settings.secret_key == "dev-secret-key-change-in-production":
        logger.critical("❌ CRITICAL: Using default SECRET_KEY in production environment!")
        logger.critical("   Set SECRET_KEY environment variable with secure random value")
        logger.critical("   Generate with: openssl rand -hex 32")
        raise RuntimeError(
            "Cannot start in production with default SECRET_KEY. "
            "Set SECRET_KEY environment variable with secure random value."
        )

    if settings.secret_key == "dev-secret-key-change-in-production":
        logger.warning("⚠️  WARNING: Using default SECRET_KEY in development")
        logger.warning("   This is acceptable for development but NEVER for production")

    MongoDB.connect()

    if await MongoDB.ping():
        logger.info("✓ MongoDB connected successfully")

        # Create database indexes for query performance
        db = MongoDB.get_database()
        try:
            # Event date index for projection queries (sort and filter)
            await db.events.create_index([("event_date", 1)])
            logger.info("✓ Created index on events.event_date")

            # Composite indexes for filtering by story/account + date range
            await db.events.create_index([("story_id", 1), ("event_date", 1)])
            logger.info("✓ Created composite index on events (story_id, event_date)")

            await db.events.create_index([("account_id", 1), ("event_date", 1)])
            logger.info("✓ Created composite index on events (account_id, event_date)")

            # Unique index on username for authentication performance + uniqueness enforcement
            await db.users.create_index([("username", 1)], unique=True)
            logger.info("✓ Created unique index on users.username")

            # Create change_log indexes for sync protocol
            await create_change_log_indexes(db)
        except Exception as e:
            logger.warning(f"⚠ Failed to create indexes: {e}")
    else:
        logger.warning("✗ MongoDB connection failed")

    yield

    # Shutdown
    logger.info("Shutting down CHAPTR API...")
    MongoDB.close()


# Initialize FastAPI application
app = FastAPI(
    title="CHAPTR API",
    description="Personal Finance Projection System - Project events across stories and accounts",
    version="0.1.0",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check():
    """
    Health check endpoint.

    Returns application health status and MongoDB connection status.
    Used by monitoring tools and container orchestration.

    Returns:
        dict: Health status information

    Status Codes:
        200: Healthy (MongoDB connected)
        503: Unhealthy (MongoDB disconnected) - TODO: Implement in Phase 1.4
    """
    db_connected = await MongoDB.ping()

    return {
        "status": "healthy" if db_connected else "unhealthy",
        "database": "connected" if db_connected else "disconnected",
        "version": "0.1.0",
        "environment": settings.environment,
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }


@app.get("/")
async def root():
    """
    Root endpoint.

    Returns basic API information and documentation link.
    """
    return {
        "name": "CHAPTR API",
        "version": "0.1.0",
        "description": "Personal Finance Projection System",
        "docs": "/docs",
        "health": "/health"
    }


# Register route modules
from api.routes import accounts, stories, events, sync, recurring_rules, auth, projection
from api.routes import settings as settings_routes

app.include_router(auth.router, prefix="/api", tags=["authentication"])
app.include_router(accounts.router, prefix="/api", tags=["accounts"])
app.include_router(stories.router, prefix="/api", tags=["stories"])
app.include_router(events.router, prefix="/api", tags=["events"])
app.include_router(settings_routes.router, prefix="/api", tags=["settings"])
app.include_router(recurring_rules.router, prefix="/api", tags=["recurring-rules"])
app.include_router(sync.router, prefix="/api", tags=["sync"])
app.include_router(projection.router, prefix="/api", tags=["projection"])
