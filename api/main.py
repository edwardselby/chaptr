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
    MongoDB.connect()

    if await MongoDB.ping():
        logger.info("✓ MongoDB connected successfully")
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


# Route registration will be added in Commit 3
# TODO Phase 1 (Commit 3): Register route modules
# app.include_router(accounts.router, prefix="/api", tags=["accounts"])
# app.include_router(stories.router, prefix="/api", tags=["stories"])
# app.include_router(events.router, prefix="/api", tags=["events"])
# app.include_router(sync.router, prefix="/api", tags=["sync"])
