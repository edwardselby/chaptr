# CHAPTR Implementation Plan

## Overview

This document outlines the back-to-front implementation approach for CHAPTR. Each phase builds on tested foundations, ensuring the complex parts (sync, projection) are solid before UI work begins.

**Estimated total time:** 7-8 weeks

---

## Phase 1: Database & API Foundation
**Duration:** 1 week

### Goals
- MongoDB collections established with all fields per spec
- Basic CRUD endpoints working
- Testable with curl/Postman

### Tasks

#### 1.1 Project Setup
- [ ] Create project structure
- [ ] Set up Python virtual environment
- [ ] Install dependencies (FastAPI, Motor/PyMongo, Pydantic)
- [ ] Configure MongoDB connection
- [ ] Basic FastAPI app with health check endpoint

```
/chaptr
├── /api
│   ├── __init__.py
│   ├── main.py              # FastAPI app
│   ├── config.py            # Settings, DB connection
│   ├── models.py            # Pydantic models
│   └── /routes
│       ├── accounts.py
│       ├── stories.py
│       ├── events.py
│       └── sync.py
├── /core
│   ├── __init__.py
│   ├── projection.py        # Projection engine
│   └── reconciliation.py    # Reconciliation logic
├── /tests
│   ├── test_accounts.py
│   ├── test_events.py
│   └── test_projection.py
└── requirements.txt
```

#### 1.2 MongoDB Collections
All field definitions per spec sections "Core Concepts" and "Technical Architecture":
- [ ] accounts (including is_default, is_archived, pending_reconciliation)
- [ ] stories (including funding_mode, goal_type, display_currency)
- [ ] events (including is_hypothetical, is_auto_adjustment, created_by, updated_by)
- [ ] recurring_rules
- [ ] users (admin/user roles)
- [ ] settings (base_currency, rates, preferences)
- [ ] change_log
- [ ] conflicts
- [ ] snapshots (optional, can defer)

#### 1.3 Pydantic Models
- [ ] All models with complete field validation per spec
- [ ] Enum types for funding_mode, goal_type, frequency
- [ ] Sync request/response models

#### 1.4 CRUD Endpoints

**Accounts:**
- [ ] GET /api/accounts (filter out archived by default)
- [ ] GET /api/accounts/{id}
- [ ] POST /api/accounts (enforce one is_default = true)
- [ ] PUT /api/accounts/{id}
- [ ] DELETE /api/accounts/{id} (archive, not hard delete)

**Stories:**
- [ ] GET /api/stories
- [ ] GET /api/stories/{id}
- [ ] POST /api/stories
- [ ] PUT /api/stories/{id}
- [ ] DELETE /api/stories/{id} (cascades to events per spec)

**Events:**
- [ ] GET /api/events
- [ ] GET /api/events/{id}
- [ ] POST /api/events (resolve account_id per hierarchy)
- [ ] PUT /api/events/{id}
- [ ] DELETE /api/events/{id}

**Settings:**
- [ ] GET /api/settings
- [ ] PUT /api/settings (admin only)

#### 1.5 Authentication
- [ ] Simple token-based auth
- [ ] User identification for created_by/updated_by
- [ ] Admin role check for settings endpoints

### Deliverables
- Running FastAPI server
- All CRUD endpoints testable via curl
- MongoDB populated with test data

### Validation
```bash
# Test account creation
curl -X POST http://localhost:8000/api/accounts \
  -H "Content-Type: application/json" \
  -d '{"name": "Monzo", "currency": "GBP", "current_balance": 2500, "is_default": true}'

# Test event creation with account resolution
curl -X POST http://localhost:8000/api/events \
  -H "Content-Type: application/json" \
  -d '{"date": "2024-12-20", "description": "Car rental", "amount": -320, "currency": "GBP", "story_id": "..."}'
```

---

## Phase 2: Projection Engine
**Duration:** 1 week

### Goals
- Core projection logic working per spec "Projection Engine" section
- Unit tested with various scenarios
- Handles all funding modes and hypothetical logic

### Tasks

#### 2.1 Basic Projection
- [ ] Calculate running balance from events
- [ ] Same-day ordering per spec (amount DESC, created_at ASC)
- [ ] Start from account balances ("now" = start of today)

#### 2.2 Filtered Projections
- [ ] ALL view (baseline + all stories, excludes hypothetical funding)
- [ ] ALL (what-if) view (includes hypothetical funding)
- [ ] Story view per spec "Filtered Calculation" logic
- [ ] Baseline-only view
- [ ] Per-account view

#### 2.3 Funding Mode Handling
- [ ] `projected` - start with calculated balance on story.start_date
- [ ] `fixed` - start with story.funding_amount
- [ ] `projected_plus` - projected + story.funding_amount
- [ ] Hypothetical funding event creation for fixed/projected_plus
- [ ] Hypothetical → real transition when story.start_date passes

#### 2.4 Gap Calculation
- [ ] Identify hidden events between visible events in filtered views
- [ ] Calculate delta amount for gap indicators
- [ ] Convert gap amounts to story's display_currency

#### 2.5 Multi-Currency
- [ ] Convert events to base currency using stored rate_to_base
- [ ] Convert to display currency using settings rates
- [ ] Handle mixed-currency projections

#### 2.6 Warnings Detection
- [ ] Global balance goes negative (date and amount)
- [ ] Per-account balance goes negative (date and amount)
- [ ] Story exceeds spend_up_to goal
- [ ] Story misses end_with_at_least goal
- [ ] Significant drift (>10%)

#### 2.7 Story Spend Calculation
- [ ] Sum of negative amounts within story (for goal tracking)
- [ ] Exclude baseline events from story spend

#### 2.8 Unit Tests
- [ ] Test basic projection calculation
- [ ] Test same-day ordering
- [ ] Test each funding mode
- [ ] Test hypothetical exclusion from ALL view
- [ ] Test story filtering with gaps
- [ ] Test multi-currency conversion
- [ ] Test warning detection
- [ ] Test edge cases (empty accounts, no events, etc.)

### Deliverables
- `/core/projection.py` module
- Comprehensive test suite
- Projection endpoint: GET /api/projection?view=all&start=...&end=...

### Validation
```bash
# Get ALL projection
curl "http://localhost:8000/api/projection?view=all&start=2024-12-18&end=2025-01-18"

# Get story projection (should include funding mode calculation)
curl "http://localhost:8000/api/projection?view=story&story_id=...&start=2024-12-18&end=2025-01-18"

# Get projection with warnings
curl "http://localhost:8000/api/projection?view=all&include_warnings=true"
```

---

## Phase 3: Sync Protocol
**Duration:** 1.5 weeks

### Goals
- Full sync protocol working per spec "Sync Protocol" section
- Change log tracking all mutations
- Conflict detection functional
- Testable with simulated multi-client scenarios

### Tasks

#### 3.1 Change Log
- [ ] Append to change_log on every create/update/delete
- [ ] Store entity snapshot (null for deletes)
- [ ] Track changed_by_user and changed_by_client
- [ ] Pruning job (delete entries older than 31 days)

#### 3.2 Sync Endpoint - Push Phase
- [ ] POST /api/sync receives changes array per spec format
- [ ] Process creates (insert + log)
- [ ] Process updates (conflict check + update + log)
- [ ] Process deletes (conflict check + hard delete + log)

#### 3.3 Sync Endpoint - Pull Phase
- [ ] Query change_log since last_sync_at
- [ ] Exclude changes from requesting client
- [ ] Return server_changes array per spec format

#### 3.4 Conflict Detection
- [ ] Compare base_updated_at with server's updated_at
- [ ] Detect edit/edit conflicts
- [ ] Detect delete/edit conflicts
- [ ] Return conflicts in response with both versions

#### 3.5 Stale Client Handling
- [ ] Check if last_sync_at is older than oldest change_log entry
- [ ] Return full_sync_required: true if stale
- [ ] GET /api/full-sync endpoint for complete data download

#### 3.6 Recurring Event Generation
- [ ] Generate events within ±1 month window on sync
- [ ] Set recurring_rule_id on generated events
- [ ] Instance edits don't affect rule (independent after generation)
- [ ] Rule deletion removes future generated events only
- [ ] Include generated events in pull response

#### 3.7 Integration Tests
- [ ] Simulate two clients making changes
- [ ] Test conflict scenarios (edit/edit, delete/edit)
- [ ] Test stale client recovery
- [ ] Test recurring event generation and editing

### Deliverables
- POST /api/sync endpoint
- GET /api/full-sync endpoint
- Change log with pruning
- Conflict detection working

### Validation
```bash
# Simulate sync from client A
curl -X POST http://localhost:8000/api/sync \
  -H "Content-Type: application/json" \
  -d '{
    "client_id": "client-a",
    "last_sync_at": "2024-12-17T00:00:00Z",
    "changes": [...]
  }'

# Simulate sync from client B (should get A's changes)
curl -X POST http://localhost:8000/api/sync \
  -H "Content-Type: application/json" \
  -d '{
    "client_id": "client-b",
    "last_sync_at": "2024-12-17T00:00:00Z",
    "changes": []
  }'

# Test conflict detection
# 1. Create event from client-a
# 2. Update same event from client-b with old base_updated_at
# 3. Verify conflict returned
```

---

## Phase 4: Frontend Foundation
**Duration:** 1.5 weeks

### Goals
- Alpine.js app structure per spec "Technical Architecture"
- Dexie.js local database
- All screens rendering from local data per mockup
- Connected to real API (online mode)

### Tasks

#### 4.1 Project Setup
- [ ] HTML shell (index.html)
- [ ] Alpine.js integration
- [ ] Dexie.js schema per spec
- [ ] CSS (terminal aesthetic from mockup)
- [ ] PWA manifest

```
/static
├── /js
│   ├── app.js           # Alpine components
│   ├── db.js            # Dexie schema
│   ├── sync.js          # Sync logic (placeholder)
│   ├── projection.js    # Client-side projection
│   └── utils.js         # Helpers (formatting, etc.)
├── /css
│   └── style.css
└── sw.js                # Service worker (placeholder)
```

#### 4.2 Dexie Schema
Per spec "Sync Protocol" section:
- [ ] accounts, stories, events, recurring_rules tables
- [ ] conflicts table
- [ ] sync_queue, sync_meta tables

#### 4.3 Screen Components
Per mockup and spec "Views" section:

**Dashboard:**
- [ ] Stories list with status indicators (✓ LEFT / ⚠ OVER)
- [ ] Story lifecycle display (active, ended, ongoing per spec)
- [ ] Accounts quick view with balances
- [ ] Projection summary (today, end of month, future)
- [ ] Drift indicator (accounts vs projected)

**Projection View:**
- [ ] Filter chips (ALL, individual stories, baseline)
- [ ] ALL view currency toggle (switch display currency)
- [ ] Projection header (title, dates, current balance, goal progress)
- [ ] Hypothetical/real funding notices (amber/blue per spec)
- [ ] TODAY divider
- [ ] Event rows with source tags [baseline], [story-name], [auto]
- [ ] Running balance column
- [ ] Gap indicators (expandable)
- [ ] End summary with goal status

**Accounts Screen:**
- [ ] Account list with currency and last updated
- [ ] Per-account projected balances (future dates)
- [ ] Total by currency summary
- [ ] Add/edit account modal
- [ ] Balance update with pending indicator

**Settings Screen (admin only):**
- [ ] User management
- [ ] Preferences (currency, date format)
- [ ] Conversion rates
- [ ] Backup/restore
- [ ] Sync settings

#### 4.4 Command Bar
Per spec "Command Bar" section (context-sensitive):
- [ ] Dashboard: + = add event (auto-assign), $ = update balance
- [ ] Projection/Story: + = add event to story, $ = edit story funding
- [ ] Accounts: + = add account, $ = update balance
- [ ] All screens: ↻ = sync, ? = help

#### 4.5 Client-Side Projection
- [ ] Port projection logic from Phase 2 to JavaScript
- [ ] Same calculations, same ordering
- [ ] Gap calculation for filtered views

#### 4.6 Initial Data Load
- [ ] On app start, check for local data
- [ ] If empty, fetch from /api/full-sync
- [ ] Populate Dexie, render from local data

#### 4.7 CRUD Operations (Online)
- [ ] Create/edit/delete for accounts, stories, events
- [ ] Write to Dexie + call API directly
- [ ] Account resolution hierarchy on event create

### Deliverables
- Fully functional UI (online mode)
- All screens matching mockup
- Local data in Dexie

### Validation
- Navigate all screens, compare to mockup
- Create accounts, stories, events
- Verify projection calculations match server
- Verify filter chips work correctly
- Verify gap indicators expand/collapse

---

## Phase 5: Offline Capability
**Duration:** 1 week

### Goals
- App works fully offline
- Changes queued and synced when online
- Background sync via Workbox

### Tasks

#### 5.1 Service Worker (Workbox)
- [ ] Cache static assets (HTML, CSS, JS)
- [ ] Cache-first strategy for app shell
- [ ] Network-first for API (with offline fallback)

#### 5.2 Sync Queue
- [ ] Queue all local changes to sync_queue table
- [ ] Store: entity_type, entity_id, action, data, base_updated_at
- [ ] Track queued_at timestamp

#### 5.3 Manual Sync
- [ ] Sync button triggers push/pull
- [ ] Read from sync_queue
- [ ] POST to /api/sync
- [ ] Process response (clear queue, apply server changes)

#### 5.4 Background Sync
- [ ] Register sync event with Workbox
- [ ] Retry failed syncs when connection restored
- [ ] Update UI after background sync

#### 5.5 Offline Indicators
- [ ] Show sync status in header
- [ ] Indicate when offline
- [ ] Show pending changes count

#### 5.6 Full Sync Recovery
- [ ] Handle full_sync_required response
- [ ] Clear Dexie, re-download all data
- [ ] User notification

### Deliverables
- App works offline
- Changes sync when connection restored
- Clear offline/online indicators

### Validation
- Enable airplane mode
- Make changes
- Disable airplane mode
- Verify sync completes

---

## Phase 6: Conflicts & Reconciliation
**Duration:** 1 week

### Goals
- Conflict resolution UI working per spec "Multi-User Conflict Resolution"
- Reconciliation system functional per spec "Reconciliation System"
- Auto-adjustments created correctly

### Tasks

#### 6.1 Conflict Resolution UI
- [ ] Detect unresolved conflicts on app load
- [ ] Show conflict resolution screen (modal or dedicated)
- [ ] Display both versions per spec format
- [ ] "Keep Mine" / "Keep Theirs" buttons
- [ ] Handle delete/edit conflicts ("Keep Deleted" / "Restore")

#### 6.2 Conflict Resolution Flow
- [ ] User selects version
- [ ] Update local Dexie
- [ ] Queue resolution for sync
- [ ] Mark conflict as resolved
- [ ] Process next conflict if any

#### 6.3 Reconciliation Triggers
Per spec "Reconciliation System":
- [ ] On exit from accounts screen
- [ ] On sync
- [ ] On viewing any projection screen

#### 6.4 pending_reconciliation Flag
- [ ] Set flag when account balance updated
- [ ] Allow multiple account updates before reconciliation
- [ ] Clear flag after reconciliation runs
- [ ] Show pending indicator in UI

#### 6.5 Reconciliation Logic
Per spec process:
- [ ] Identify accounts with pending_reconciliation = true
- [ ] Remove existing auto-adjustments for those accounts
- [ ] Calculate projected vs actual balance
- [ ] Create new auto-adjustment events if drift exists
- [ ] Clear pending flags

#### 6.6 Auto-Adjustment Display
- [ ] Tag as [auto] in timeline
- [ ] Style subtly (dim/grey)
- [ ] Show in ALL view only (exclude from story views per spec)

#### 6.7 Drift Indicator
- [ ] Calculate on dashboard load
- [ ] Show accounts total vs projected now
- [ ] Color coding: green (<5%), amber (5-10%), red (>10%)

### Deliverables
- Conflict resolution working end-to-end
- Reconciliation creates appropriate adjustments
- Drift visible to user

### Validation
- Simulate conflict (edit same event offline from two clients)
- Verify resolution UI appears on sync
- Update account balance, verify pending indicator
- Exit accounts screen, verify auto-adjustment created
- Verify auto-adjustments hidden in story views

---

## Phase 7: Polish & Remaining Features
**Duration:** 1-2 weeks

### Goals
- All features complete per spec
- Edge cases handled
- Production ready

### Tasks

#### 7.1 Recurring Events UI
- [ ] Create/edit/delete recurring rules
- [ ] Dedicated creation screen per spec
- [ ] Show generated events in timeline
- [ ] Handle rule modification (future events only)

#### 7.2 Story Features
- [ ] Funding mode selection on create/edit
- [ ] Hypothetical funding display (amber notice, [planned] tag)
- [ ] Real funding display (blue info notice)
- [ ] Goal selection (spend_up_to, end_with_at_least, none)
- [ ] Goal progress bar
- [ ] Story status in dashboard list

#### 7.3 Story Assignment Rules
Per spec "Story Assignment Rules":
- [ ] Auto-assign when adding from dashboard/ALL view
- [ ] Find stories covering event date
- [ ] Assign to shortest duration story
- [ ] Prompt if equal duration
- [ ] Assign to baseline if no story covers date

#### 7.4 Event Editing
- [ ] Currency rate prompt on edit (update to current or keep)
- [ ] Archived account restriction (cannot select for new events)

#### 7.5 Warnings Display
Per spec "Warning System":
- [ ] Global balance negative warning
- [ ] Per-account negative warning
- [ ] Story over budget warning
- [ ] Story misses goal warning
- [ ] Hypothetical funding reminder
- [ ] Significant drift warning

#### 7.6 Settings (Admin)
- [ ] User management (add/remove, roles)
- [ ] Currency rate editing
- [ ] Preferences (date format, baseline display months)
- [ ] Backup export (JSON download)
- [ ] Backup import (JSON upload with validation)
- [ ] Clear local data option

#### 7.7 Snapshots (Optional)
- [ ] Server-side snapshot creation
- [ ] Triggers: story end, month boundary, post-reconciliation, manual (admin)
- [ ] Snapshot invalidation when events modified (per spec)
- [ ] Historical query support

#### 7.8 Testing & Bug Fixes
- [ ] End-to-end testing all flows
- [ ] Edge case testing (empty states, boundaries)
- [ ] Offline/online transition testing
- [ ] Multi-user scenario testing
- [ ] Performance testing with larger datasets
- [ ] Bug fixes

#### 7.9 Deployment
- [ ] Docker setup (optional)
- [ ] HTTPS configuration
- [ ] Home server deployment
- [ ] PWA installation testing

### Deliverables
- Feature complete application
- All edge cases handled
- Deployed and accessible

### Validation
- Full walkthrough matching mockup and spec
- Test with real data scenarios
- Test offline usage for extended period
- Test sync between multiple devices

---

## Summary

| Phase | Focus | Duration | Cumulative |
|-------|-------|----------|------------|
| 1 | Database & API | 1 week | 1 week |
| 2 | Projection Engine | 1 week | 2 weeks |
| 3 | Sync Protocol | 1.5 weeks | 3.5 weeks |
| 4 | Frontend Foundation | 1.5 weeks | 5 weeks |
| 5 | Offline Capability | 1 week | 6 weeks |
| 6 | Conflicts & Reconciliation | 1 week | 7 weeks |
| 7 | Polish & Features | 1-2 weeks | 8-9 weeks |

---

## Reference Documents

This plan should be used alongside:
- **chaptr-spec-v2.8.md** - Full technical specification (data models, business logic, architecture)
- **chaptr-v3-mockup.html** - Visual reference for all screens and UI patterns
- **chaptr-mockup-explanation.md** - Walkthrough of mockup scenarios and calculations

---

## Dependencies

```
Phase 1 ─────► Phase 2 ─────► Phase 3
                                 │
                                 ▼
              Phase 4 ◄──────────┘
                 │
                 ▼
              Phase 5 ─────► Phase 6 ─────► Phase 7
```

- Phase 2 depends on Phase 1 (needs data model)
- Phase 3 depends on Phase 2 (sync includes projection data)
- Phase 4 depends on Phase 3 (frontend consumes sync API)
- Phase 5 depends on Phase 4 (offline adds to working UI)
- Phase 6 depends on Phase 5 (conflicts emerge from offline use)
- Phase 7 depends on Phase 6 (polish after core complete)

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Sync complexity underestimated | Phase 3 is longest; add buffer if needed |
| Projection edge cases | Extensive unit tests in Phase 2 |
| Offline bugs hard to debug | Thorough logging, manual test scenarios |
| Scope creep | Defer nice-to-haves to post-v1 |

---

## Post-v1 Enhancements (Future)

- Bank feed integration (read-only)
- Charts and trends
- Export to CSV/PDF
- Mobile app (if PWA insufficient)
- Shared household view

---

*Document created: December 2024*
*Status: Ready for implementation*
