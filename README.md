# CHAPTR

**Personal Finance Projection System**

> *"What will my balance be on date X, given everything I know about?"*

A mobile-first Progressive Web App for projecting financial futures through contextual "stories" rather than rigid budgets. Built with offline-first architecture, multi-tenancy, and automatic reconciliation - no bank integrations required.

![Version](https://img.shields.io/badge/version-0.18.1-brightgreen)
![Python](https://img.shields.io/badge/python-3.11+-blue)
![Status](https://img.shields.io/badge/status-active_development-yellow)

---

## 🚧 Status

**Active Development** - Core features functional, but expect rough edges. Most notably, historical events (past dates) are currently hidden with no UI to access them yet.

**Test Coverage:** 113/113 frontend tests passing | Comprehensive backend suite (14.5K lines)

---

## Overview

CHAPTR solves forward-looking financial planning without transaction tracking or bank integrations. Instead of "where did my money go?", it answers "where is my money going?"

**The Problem:** Planning a Japan trip (£3,000 in 6 months) and kitchen renovation (£8,000 in 8 months) while maintaining rent, subscriptions, groceries. Can you afford both? What about that expected bonus?

**The Solution:** Project forward by creating isolated "stories" - contextual financial scenarios. No transaction tracking, no bank OAuth, no data sharing. Just manual balance updates with automatic reconciliation.

**Philosophy:**
- **Projection over Tracking** - Care about future, not past pennies
- **Stories as Layers** - Views on shared reality, not separate pots
- **Reality as Anchor** - Accounts are truth, system auto-corrects projections
- **Automatic-First** - System handles drift, users only intervene for conflicts

---

## Key Features

- **Automatic Reconciliation** - Update balances manually, system eliminates projection drift with immutable adjustments
- **Multi-Tenancy** - Super Admin → Admin (tenant) → Users with JWT security context
- **Story-Based Planning** - Baseline drumbeat + isolated scenarios (trips, projects, hypotheticals) with sharing
- **Offline-First** - Three-tier progressive enhancement (full PWA → offline-capable → server-only)
- **Multi-Currency** - Locked historical rates for accurate past projections
- **Projection Engine** - Timeline with running balance, gap indicators, per-account and global views
- **Queue-as-State** - All writes queued locally, synced to server, server returns authoritative state
- **Change Log Sync** - Conflict detection via base timestamp comparison, no version vectors required

---

## How It Works

### Data Model
```
Accounts (reality anchor)
  ├─ Baseline (recurring drumbeat)
  │   ├─ Salary: +£3,500/month
  │   ├─ Rent: -£1,200/month
  │   └─ Netflix: -£15.99/month
  │
  └─ Stories (contextual scenarios)
      ├─ "Japan Trip 2026" (shared with partner)
      │   ├─ Flights: -£800 (Jun 1)
      │   └─ Hotels: -£600 (Sep 1)
      │
      └─ "What if: New Car?" (hypothetical)
          └─ Tesla Model 3: -£35,000 (Aug 15)
```

### Usage Flow
1. **Setup accounts** - Add banks with balances and currencies
2. **Define baseline** - Recurring income/expenses (salary, rent, subscriptions)
3. **Create stories** - Trips, projects, hypotheticals (shared or private)
4. **View projections** - Timeline showing balance over time (global, per-account, per-story)
5. **Stay aligned** - Update balances when checking bank, system auto-reconciles

### Reconciliation Example
```
Last Update: Jan 1 - £2,500
Expected Today: £2,300 (based on projected events)
Actual Balance: £2,100 (spent more than planned)

→ System creates -£200 adjustment event
→ Future projections now accurate
→ Historical queries include all adjustments up to date (accuracy preserved)
```

---

## Architecture

### 1. Progressive Enhancement (3-Tier)

Client adapts to browser capabilities:

**Mode 3 (Offline-First):** Service Worker + IndexedDB + queue sync. Full offline functionality.

**Mode 2 (Offline-Capable):** IndexedDB + queue sync (no service worker). Handles intermittent connectivity.

**Mode 1 (Server-Only):** Direct API calls (no IndexedDB). Private browsing or old browsers.

**Implementation:** Storage adapter detects capabilities at runtime, provides unified interface. No feature detection fragility, no scattered mode-specific code.

*Files: `storage-adapter.js:1-49054`, `app.js:2405-2414`*

### 2. Queue-as-State Pattern

**Traditional:** Optimistic update → API call → Replace with server response → Handle conflicts.

**CHAPTR:** All mutations are queue operations:
1. User action → Queue operation (e.g., createAccount)
2. UI updates optimistically from queue state
3. Queue syncs to server
4. Server returns authoritative state
5. Queue resolves, derived state updates UI

**Benefits:** Single source of truth (queue + server), network resilience (queue persists), conflict resolution isolated from UI, testable sync logic.

*Files: `storage-adapter.js:2801-2950`, `app.js:2405-2414`*

### 3. Change Log Sync (Multi-User Conflict Detection)

**Problem:** Detect concurrent modifications without version vectors or CRDTs.

**Solution:** Immutable change log with base timestamp comparison:
```
Client A reads: { id: 123, updated_at: T1 }
Client B reads: { id: 123, updated_at: T1 }

Client A pushes: { id: 123, base_updated_at: T1, new_data }
→ Server: base (T1) == current (T1) → Accept, set updated_at = T2

Client B pushes: { id: 123, base_updated_at: T1, new_data }
→ Server: base (T1) != current (T2) → CONFLICT! Return both versions
```

Works with MongoDB single-document atomicity. Scales to multiple tenants without cross-tenant coordination.

*Files: `api/routes/sync.py:89-156`, `docs/chaptr-spec.md:1840-1950`*

### 4. Automatic Reconciliation (Immutable Adjustments)

**Problem:** Projected balances drift from reality. Traditional solution: re-fetch and recalculate. Bad UX, doesn't explain drift.

**CHAPTR:**
```
User updates: "Monzo now £2,100"
System calculates: Expected £2,300 (from last update + events)
Drift: -£200 (spent more than projected)

Action: Create adjustment event for -£200 on today
Result: Projection matches reality, adjustment explains drift
```

**Key innovation:** Adjustments are incremental, not cumulative. Each adjustment only corrects drift since last reconciliation. Historical queries include all adjustments up to date, so past projections remain accurate.

*Files: `core/reconciliation.py:67-179` (incremental logic), `core/reconciliation.py:243-302` (same-day consolidation)*

### 5. Multi-Tenancy (JWT Security Context)

**Hierarchy:**
```
Super Admin → Creates Admins (tenants)
  └─ Admin → Owns isolated data space
      └─ Creates Users within tenant
          └─ Access only tenant data
```

**Security:** JWT token includes `tenant_id` claim. All API endpoints extract tenant from token (no client trust). Repository layer enforces tenant scoping on all queries. MongoDB queries include `{ tenant_id: <from_token> }`. No cross-tenant leakage possible.

**Trade-off:** Simpler than row-level security or separate databases. Sufficient for personal/small-team use. Scales to hundreds of tenants before database sharding needed.

*Files: `api/routes/*.py` (JWT dependency), `api/repositories/*.py` (tenant-scoped queries)*

### 6. Sync Endpoint Hijacking (No Background Scheduler)

**Traditional:** Background scheduler (Celery, APScheduler) for periodic tasks.

**CHAPTR:** Execute global logic on sync endpoint requests:
```python
@router.post("/sync")
async def sync_endpoint(tenant_id: str):
    # Execute reconciliation triggers
    # Clean up stale data
    # Generate recurring instances
    # Then handle sync
```

**Why:** Simpler infrastructure (no scheduler, no workers), sufficient for non-time-critical operations, sync happens when user active (perfect timing), minimal deployment (single Uvicorn process).

**Trade-off:** Not for time-critical tasks. Fine for CHAPTR (reconciliation, cleanup can be lazy).

### 7. Multi-Currency (Locked Historical Rates)

**Problem:** Financial projections need historical accuracy. If rates change, past projections become wrong.

**Solution:** Lock exchange rates at event creation:
```javascript
Event {
  amount: 5000,
  currency: "CAD",
  rate_to_base: 0.58  // Locked at creation (1 CAD = 0.58 GBP)
}
```

Historical queries use locked `rate_to_base`. Display conversion uses current settings rates. Balance at past date X uses rates from date X.

*Files: `event-helpers.js:75-120`, `projection.js:226-280`*

---

## Technology Stack

### Backend
- **FastAPI** - Async Python with auto-generated OpenAPI docs
- **MongoDB + Motor** - Document database with async driver
- **Pydantic v2** - Data validation and serialization
- **JWT (python-jose)** - Stateless auth with tenant context
- **Passlib + bcrypt** - Secure password hashing

### Frontend
- **Alpine.js** - Lightweight (15KB) reactive framework, no build step
- **Dexie.js** - Promise-based IndexedDB wrapper with rich queries
- **Workbox** - Service worker for PWA offline capabilities
- **Vanilla JS** - Minimal dependencies, fast load
- **Terminal Aesthetic** - JetBrains Mono, #4af626 on black, ASCII UI

### Testing
- **Pytest** - Async test suite (14.5K lines, fixtures, mocks, coverage)
- **Vitest** - Browser-based frontend tests with Playwright (113/113 passing)
- **Black + Ruff** - Formatting and linting

### Infrastructure
- **Docker + Docker Compose** - Containerized deployment with MongoDB
- **Uvicorn** - ASGI server

### Why These Choices?

**MongoDB:** Flexible schema, nested documents (events, recurrence), efficient change log, horizontal scaling ready.

**FastAPI:** Modern async, built-in validation, auto-generated docs, high performance.

**Alpine.js:** Lightweight, reactive without build step, perfect for PWA, maintainable.

**IndexedDB:** Browser-native, 50MB+ capacity, structured data with indexes, full offline queries.

**JWT:** Simple, stateless, tenant context in token, horizontal scaling without session stores.

**No Scheduler:** Hijack sync endpoint for periodic logic. Simpler, sufficient for non-time-critical ops.

---

## Project Structure

```
chaptr/
├── api/                      # FastAPI backend
│   ├── main.py              # Application entry + SW versioning
│   ├── models.py            # Pydantic models (53K lines)
│   ├── config.py            # Settings, DB connection
│   ├── routes/              # API endpoints
│   │   ├── accounts.py
│   │   ├── stories.py
│   │   ├── events.py
│   │   ├── recurring.py
│   │   └── sync.py
│   ├── repositories/        # Database layer (tenant-scoped)
│   └── services/            # Business logic
├── core/                    # Core business logic
│   ├── projection.py        # Projection engine
│   └── reconciliation.py    # Auto-adjustment logic
├── static/                  # Frontend PWA
│   ├── index.html          # Single-page app (163K lines)
│   ├── js/
│   │   ├── app.js          # Main application (177K)
│   │   ├── db.js           # Dexie IndexedDB
│   │   ├── projection.js   # Projection calculations
│   │   └── storage-adapter.js  # Progressive enhancement (49K)
│   └── css/
│       └── style.css       # Terminal aesthetic
├── tests/                   # Test suites
│   ├── backend/            # Python tests
│   └── frontend/           # JavaScript tests
├── docs/                    # Comprehensive documentation
│   ├── chaptr-spec.md      # Technical spec (2,922 lines)
│   ├── chaptr-implementation-guide.md
│   ├── testing-guide.md
│   └── chaptr-mockup.html
├── pyproject.toml           # Python dependencies (source of truth)
├── uv.lock                 # Locked dependency versions
├── .python-version         # Python version pin for uv
├── package.json            # Node.js dependencies
└── docker-compose.yml      # Container orchestration
```

---

## Installation & Setup

### Prerequisites
- [uv](https://docs.astral.sh/uv/) (Python toolchain manager — replaces pyenv, pip, venv)
- MongoDB 4.4+
- Node.js 18+ (for frontend tests)
- Docker (optional)

### Quick Start

```bash
# Clone and setup
git clone <repository-url>
cd Chaptr

# Install Python and dependencies via uv (creates .venv automatically)
uv sync
uv sync --group dev  # include dev dependencies

# Install frontend test dependencies
npm install

# Configure environment
cp .env.example .env
# Edit .env:
# - MONGODB_URI (connection string)
# - SECRET_KEY (for JWT tokens)
# - SUPER_ADMIN_USERNAME, SUPER_ADMIN_PASSWORD

# Start MongoDB
mongod --dbpath /path/to/data
# Or: docker-compose up -d mongodb

# Run application
uvicorn api.main:app --reload
# Access at http://localhost:8000
```

### Docker Deployment
```bash
docker-compose up -d
# Access at http://localhost:8000
# Includes MongoDB, API server, volume persistence
```

### Multi-Tenancy Setup

1. Super Admin creates Admin users (tenants)
2. Each Admin logs in to isolated tenant
3. Admin creates Users within tenant
4. Users access only their tenant's data

Configure super admin in `.env`: `SUPER_ADMIN_USERNAME`, `SUPER_ADMIN_PASSWORD`

---

## Development

### Running Tests
```bash
# Backend (Pytest)
pytest                              # All tests
pytest --cov=api --cov=core        # With coverage
pytest tests/backend/unit/test_projection.py  # Specific file

# Frontend (Vitest)
npm test                            # All tests
npm run test:ui                     # Interactive UI
npm run test:coverage              # With coverage
```

### Code Quality
```bash
black api/ core/                   # Format
ruff check api/ core/              # Lint
```

### Documentation
- **`docs/chaptr-spec.md`** (2,922 lines) - Complete technical specification (data models, business logic, sync protocol)
- **`docs/chaptr-implementation-guide.md`** - 7-phase implementation roadmap + UI/UX walkthrough
- **`docs/testing-guide.md`** - Manual testing procedures (API, sync, offline, conflicts)
- **`docs/chaptr-mockup.html`** - Interactive visual reference (terminal aesthetic)
- **`CLAUDE.md`** - Development workflow, conventions, Taskwarrior integration
- **`CHANGELOG.md`** - Version history (ticket-based format)
- **API Docs (auto-generated):**
  - Swagger UI: http://localhost:8000/docs
  - ReDoc: http://localhost:8000/redoc

---

## Implementation Status

### Completed ✅
- Multi-tenancy (Super Admin → Admin → Users)
- JWT authentication with tenant context
- Backend API with full CRUD + validation
- Projection engine (global + per-account)
- Multi-currency with locked historical rates
- Recurring events (daily, weekly, monthly, yearly)
- Story-based planning with funding modes
- Shared stories (multi-user collaboration)
- Offline-first PWA (3-tier progressive enhancement)
- Change log sync with conflict resolution
- Automatic reconciliation with immutable adjustments
- Account archiving and deletion
- Per-view account filtering (localStorage persistence)
- Recurring event deletion UX (instance vs rule)
- Comprehensive test suites (14.5K lines, 113 passing)

### Known Issues 🚧
- **Historical event viewing** - Past events auto-hidden, no UI to access (highest priority)
- **Feature polish** - Many features have rough edges or incomplete flows
- **Goal tracking UI** - Backend exists, frontend incomplete
- **Intent Documentation Testing** - Validating spec alignment

### Planned 📋
- Advanced reporting (spending trends, category breakdowns)
- Export to CSV/PDF
- Snapshot system for point-in-time restoration
- Mobile app wrapper (React Native or Capacitor)

---

## About This Project

Personal project built to solve a real problem: planning finances for trips, projects, and life events without transaction tracking or bank integrations.

Demonstrates architectural problem-solving:
- Progressive enhancement patterns
- Offline-first architecture
- Multi-tenancy with security context
- Queue-based sync protocols
- Automatic reconciliation without integrations
- Test-driven development
- Solo project ownership (spec to implementation)

Built in spare time for household financial planning. Source code visible for educational purposes.

---

## License

Personal project - All rights reserved.

Not intended for commercial use or public distribution.

---

**Version:** 0.18.1 | **Last Updated:** February 2026

*"CHAPTR - Because life is about stories, not spreadsheets."*
