"""
CHAPTR API - Personal Finance Projection System

FastAPI application providing REST API for CHAPTR projection system.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response
from contextlib import asynccontextmanager
import logging
from datetime import datetime
import hashlib
from pathlib import Path

from api.config import settings, MongoDB
from api.utils.indexes import create_change_log_indexes, create_conflicts_indexes
from api.utils.db import utc_now

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

    # Start background scheduler for maintenance jobs
    from api.scheduler import start_scheduler
    start_scheduler()

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

            # Create conflicts indexes for sync conflict queries
            await create_conflicts_indexes(db)
        except Exception as e:
            logger.warning(f"⚠ Failed to create indexes: {e}")
    else:
        logger.warning("✗ MongoDB connection failed")

    yield

    # Shutdown
    logger.info("Shutting down CHAPTR API...")

    # Shutdown background scheduler
    from api.scheduler import shutdown_scheduler
    shutdown_scheduler()

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


# ==================== Exception Handlers ====================

from fastapi import Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """
    Enhanced validation error handler for better debugging.

    Logs detailed validation errors when request data doesn't match Pydantic models.
    Returns 422 with detailed error information.
    """
    # Log detailed error for debugging
    logger.error(f"Validation error on {request.method} {request.url.path}")
    logger.error(f"Errors: {exc.errors()}")

    # Try to log request body (if JSON)
    try:
        body = await request.json()
        logger.error(f"Request body: {body}")
    except Exception:
        logger.error("Could not parse request body")

    # Convert errors to serializable format (remove 'ctx' which may contain non-serializable objects)
    serializable_errors = []
    for error in exc.errors():
        serializable_error = {
            "type": error["type"],
            "loc": error["loc"],
            "msg": error["msg"],
            "input": str(error.get("input", ""))  # Convert to string for safety
        }
        serializable_errors.append(serializable_error)

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": serializable_errors}
    )


@app.exception_handler(ValidationError)
async def pydantic_validation_exception_handler(request: Request, exc: ValidationError):
    """
    Handle Pydantic validation errors (raised during model instantiation).

    These can occur when creating models from dictionaries in the sync endpoint.
    """
    logger.error(f"Pydantic validation error on {request.method} {request.url.path}")
    logger.error(f"Errors: {exc.errors()}")

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "detail": exc.errors()
        }
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
        "timestamp": utc_now().isoformat()
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
from api.routes import accounts, stories, events, sync, recurring_rules, auth, projection, admin
from api.routes import settings as settings_routes

app.include_router(auth.router, prefix="/api", tags=["authentication"])
app.include_router(accounts.router, prefix="/api", tags=["accounts"])
app.include_router(stories.router, prefix="/api", tags=["stories"])
app.include_router(events.router, prefix="/api", tags=["events"])
app.include_router(settings_routes.router, prefix="/api", tags=["settings"])
app.include_router(recurring_rules.router, prefix="/api", tags=["recurring-rules"])
app.include_router(sync.router, prefix="/api", tags=["sync"])
app.include_router(projection.router, prefix="/api", tags=["projection"])
app.include_router(admin.router, prefix="/api", tags=["admin"])

# Mount static files for frontend
app.mount("/static", StaticFiles(directory="static"), name="static")


def generate_file_hash(file_path: Path) -> str:
    """
    Generate MD5 hash of file contents for cache busting.

    Args:
        file_path: Path to file to hash

    Returns:
        str: First 8 characters of MD5 hash
    """
    try:
        with open(file_path, 'rb') as f:
            content = f.read()
            return hashlib.md5(content).hexdigest()[:8]
    except FileNotFoundError:
        logger.warning(f"File not found for hashing: {file_path}")
        return "00000000"


@app.get("/sw.js")
async def serve_service_worker():
    """
    Dynamically generate service worker with automatic revision numbers.

    Generates content-based MD5 hashes for each precached file to enable
    automatic cache invalidation when files change. This eliminates the need
    for manual revision bumping or cache clearing during development.

    Returns:
        Response: Service worker JavaScript with hashed revisions
    """
    static_dir = Path("static")

    # Files to precache with automatic revision hashing
    # Automatically discover all JavaScript files
    js_files = sorted([str(p) for p in static_dir.glob("js/*.js")])

    precache_files = [
        "static/index.html",
        "static/css/style.css",
    ] + js_files

    # Generate revision hashes for each file
    precache_entries = []
    for file_path in precache_files:
        full_path = Path(file_path)
        revision = generate_file_hash(full_path)
        url = f"/{file_path}"
        precache_entries.append(f"    {{ url: '{url}', revision: '{revision}' }}")

    precache_list = ",\n".join(precache_entries)

    # Generate service worker content with dynamic revisions
    sw_content = f"""/**
 * CHAPTR Service Worker (Dynamically Generated)
 *
 * Uses Workbox for caching strategies:
 * - Cache-First: Static assets (HTML, CSS, JS, images)
 * - Network-First: API calls (with offline fallback)
 *
 * ⚡ AUTOMATIC REVISION NUMBERS:
 * Revisions are MD5 hashes of file contents, generated on-the-fly.
 * Cache automatically invalidates when files change - no manual intervention needed.
 */

// Import Workbox from CDN
importScripts('https://storage.googleapis.com/workbox-cdn/releases/7.0.0/workbox-sw.js');

const {{ registerRoute }} = workbox.routing;
const {{ CacheFirst, NetworkFirst }} = workbox.strategies;
const {{ ExpirationPlugin }} = workbox.expiration;
const {{ CacheableResponsePlugin }} = workbox.cacheableResponse;

// ==================== APP SHELL PRECACHING ====================

/**
 * Precache critical app shell files with automatic revisions
 *
 * Revision hashes are generated from file contents (MD5).
 * When a file changes, its hash changes, triggering cache update.
 */
workbox.precaching.precacheAndRoute([
{precache_list}
]);

// ==================== STATIC ASSETS: CACHE-FIRST ====================

/**
 * Cache-First strategy for static assets
 *
 * Priority: Cache → Network
 * - Faster loads on repeat visits
 * - 7-day cache expiration
 * - Max 60 entries to prevent unbounded growth
 */
registerRoute(
    ({{ request }}) => ['style', 'script', 'image', 'font'].includes(request.destination),
    new CacheFirst({{
        cacheName: 'static-assets-v1',
        plugins: [
            new CacheableResponsePlugin({{
                statuses: [0, 200] // Cache successful responses
            }}),
            new ExpirationPlugin({{
                maxEntries: 60,
                maxAgeSeconds: 7 * 24 * 60 * 60 // 7 days
            }})
        ]
    }})
);

// ==================== API CALLS: NETWORK-FIRST ====================

/**
 * Network-First strategy for API calls
 *
 * Priority: Network → Cache
 * - Always try network first for fresh data
 * - 5-second timeout before falling back to cache
 * - Cache as offline fallback
 */
registerRoute(
    ({{ url }}) => url.pathname.startsWith('/api/'),
    new NetworkFirst({{
        cacheName: 'api-cache-v1',
        networkTimeoutSeconds: 5,
        plugins: [
            new CacheableResponsePlugin({{
                statuses: [0, 200]
            }}),
            new ExpirationPlugin({{
                maxEntries: 50,
                maxAgeSeconds: 24 * 60 * 60 // 1 day
            }})
        ]
    }})
);

// ==================== BACKGROUND SYNC ====================

/**
 * Background sync listener
 *
 * Triggered when:
 * - App calls registration.sync.register('chaptr-sync')
 * - Browser detects connectivity restored
 *
 * Notifies app to process sync queue.
 */
self.addEventListener('sync', (event) => {{
    if (event.tag === 'chaptr-sync') {{
        event.waitUntil(notifyClientsToSync());
    }}
}});

/**
 * Notify all clients to trigger sync
 */
async function notifyClientsToSync() {{
    const clients = await self.clients.matchAll({{ type: 'window' }});

    clients.forEach(client => {{
        client.postMessage({{
            type: 'BACKGROUND_SYNC',
            timestamp: new Date().toISOString()
        }});
    }});
}}

// ==================== SERVICE WORKER LIFECYCLE ====================

/**
 * Install event - precache app shell
 */
self.addEventListener('install', (event) => {{
    console.log('[SW] Service worker installing...');
    self.skipWaiting(); // Activate immediately
}});

/**
 * Message event - handle SKIP_WAITING command
 */
self.addEventListener('message', (event) => {{
    if (event.data?.type === 'SKIP_WAITING') {{
        console.log('[SW] Received SKIP_WAITING message, activating new service worker...');
        self.skipWaiting();
    }}
}});

/**
 * Activate event - clean old caches
 */
self.addEventListener('activate', (event) => {{
    console.log('[SW] Service worker activating...');

    const cacheWhitelist = ['static-assets-v1', 'api-cache-v1'];

    event.waitUntil(
        caches.keys().then((cacheNames) => {{
            return Promise.all(
                cacheNames.map((cacheName) => {{
                    if (!cacheWhitelist.includes(cacheName)) {{
                        console.log('[SW] Deleting old cache:', cacheName);
                        return caches.delete(cacheName);
                    }}
                }})
            );
        }}).then(() => {{
            return self.clients.claim(); // Take control immediately
        }})
    );
}});

// ==================== FETCH EVENT ====================

/**
 * Fetch event - handled by Workbox strategies above
 *
 * Routes:
 * - Static assets (CSS, JS, images) → Cache-First
 * - API calls (/api/*) → Network-First
 * - Everything else → Network-only
 */
self.addEventListener('fetch', (event) => {{
    // Workbox handles routing via registerRoute() calls above
    // This listener is just for logging/debugging
    if (event.request.url.includes('/api/')) {{
        console.log('[SW] API request:', event.request.url);
    }}
}});
"""

    return Response(
        content=sw_content,
        media_type="application/javascript",
        headers={
            "Service-Worker-Allowed": "/",
            "Cache-Control": "no-cache"  # Don't cache the SW itself
        }
    )


@app.get("/app")
async def serve_app():
    """
    Serve the frontend application.

    Returns the main index.html for the CHAPTR PWA.
    """
    return FileResponse("static/index.html")
