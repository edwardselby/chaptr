# CHAPTR Implementation Guide

**Version:** 1.0
**Last Updated:** January 2025

> This guide provides the 7-phase implementation roadmap and detailed UI/UX walkthrough for building CHAPTR.

---

# PART I: Implementation Roadmap

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

---
---

# PART II: UI/UX Walkthrough

> The following section provides a detailed walkthrough of the UI mockup with example scenarios.

---

This document explains the CHAPTR mockup, walking through the example scenario and demonstrating how the key concepts work in practice.

---

## 1. Overview

### What is CHAPTR?

CHAPTR is a projection-based personal finance tool. Unlike traditional budgeting apps that focus on categorising past spending or allocating money into pots, CHAPTR answers a simple question:

> "What will my balance be on date X, given everything I know about?"

### The Core Concept: Stories

CHAPTR uses **stories** to group related financial events. A story might be:

- A trip (canada-trip, skiing)
- A project (volvo repairs)
- A life event (wedding, house move)

**The key insight:** Stories are layers on a shared reality, not separate pots of money. All stories draw from the same pool of funds, and the **baseline** (recurring income/expenses like salary and rent) weaves through everything.

---

## 2. The Example Scenario

### Who

Edward and Katrina, managing finances across UK and Canada.

### When

**Today is December 18th, 2024.**

### Accounts

| Account | Currency | Balance |
|---------|----------|---------|
| Monzo | GBP | £2,500 |
| HSBC | GBP | £11,000 |
| Kat Credit | CAD | -$500 |
| **Total (GBP)** | | **£13,500** |

### What's Happening

Three overlapping stories are in play:

1. **canada-trip** (Dec 04 - Jan 05): A month-long trip to Canada
2. **volvo** (Oct 01 - ongoing): Car repairs that keep growing
3. **skiing** (Dec 23 - Dec 28): Christmas skiing trip, nested inside the Canada trip

### Baseline (Recurring Monthly)

| Event | Amount | Day |
|-------|--------|-----|
| Salary | +£3,000 | 28th |
| Rent | -£1,200 | 1st |
| Bills | -£100 | 1st |

---

## 3. The Stories

| Story | Dates | Currency | Goal | Funding | Status |
|-------|-------|----------|------|---------|--------|
| canada-trip | Dec 04 → Jan 05 | GBP | Spend up to £1,000 | Projected | ✓ £130 left |
| volvo | Oct 01 → ongoing | GBP | Spend up to £2,500 | Projected + £500 (real) | ⚠ £217 over |
| skiing | Dec 23 → Dec 28 | CAD | Spend up to $2,000 | Projected + $500 (hypothetical) | ✓ $150 left |

### Story Overlap

The stories overlap in time:

```
October     November    December              January
|-----------|-----------|---------------------|--------->
            
[volvo ----ongoing-------------------------------------------]
                        [canada-trip ------------------]
                                    [skiing]
                                    Dec 23-28
                                        ↑
                                      TODAY
                                     Dec 18
```

This overlap is handled through **gap indicators** - when viewing one story, events from other stories appear as collapsible gaps showing how they affect the running balance.

---

## 4. Screen-by-Screen Walkthrough

### Dashboard

The home screen provides an at-a-glance view:

- **Stories list**: Each story shows its spend, date range, and status
- **Accounts**: Quick view of current balances
- **Projection summary**: Key future balance milestones

From here, tap any story to see its detailed projection.

### ALL View

The ALL view shows **ground truth** - every event from every story and baseline, in chronological order.

**Critical:** Hypothetical funding does NOT appear here. The ALL view answers "what will actually happen?" without any "what if" assumptions.

Key features:
- Events tagged with their source: `[canada]`, `[volvo]`, `[skiing]`, `[baseline]`
- Baseline events have a subtle background highlight
- Running balance updates with each event

### Canada-trip View

A filtered view showing only canada-trip events plus baseline.

**What you see:**
- Canada-trip events (car rental, gifts, hotel)
- Baseline events (salary, rent, bills)
- Gap indicators showing activity from other stories

**Gap indicators example:**
```
Dec 20 | car rental           | -£320  | £13,180
       ┄┄┄┄┄┄┄ -£380 other ┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄  ← tap to expand
Dec 25 | gifts                | -£150  | £12,039
```

Tapping the gap reveals:
```
Dec 22 | tyres [volvo]        | -£380  | £12,800
```

The gap shows that between your car rental and gifts, the volvo tyres came out - affecting your available balance even though it's not part of this story.

### Volvo View

Shows the volvo story with **real funding**.

**Notice (blue):** "ℹ This story includes additional funding"

The family loan appears as a normal event in the timeline:
```
Dec 10 | family loan          | +£500  | £13,585  ← green (real)
```

This loan:
- Appears in the volvo view ✓
- Appears in the ALL view ✓ (because the story has started, it's real)
- Is counted in the running balance everywhere

**Goal status:** Spent £2,717 against £2,500 budget = £217 over

### Skiing View

Shows the skiing story with **hypothetical funding** in CAD.

**Notice (amber):** "⚠ This story has hypothetical funding"

The expected contribution appears as a planned event:
```
Dec 23 | period start                    |   --   | $22,016
Dec 23 | expected contribution [planned] | +$500  | $22,516  ← amber (hypothetical)
Dec 23 | ski passes                      | -$600  | $21,916
```

This contribution:
- Appears in the skiing view ✓
- Does NOT appear in the ALL view (it's hypothetical)
- Uses amber colouring to indicate "not confirmed"
- Has a `[planned]` tag

**Why hypothetical?** The skiing story hasn't started yet (Dec 23 vs today Dec 18). Once the story starts and the contribution is received, it would become a real event and appear in ALL view.

**Currency:** All amounts shown in CAD with conversion rate displayed.

### Accounts Screen

The accounts screen provides account management and reconciliation:

**Accounts list shows:**
- Account name with `[default]` tag if it's the default spending account
- Currency and last updated timestamp
- Current balance
- Tap to view account details

**Projection vs Reality section shows:**
- Accounts total (sum of all account balances)
- Projected NOW (what the projection engine calculates)
- Drift indicator (difference between actual and projected)

**Drift indicator colours:**
- Green (0-5%): On track, minor variance
- Amber (5-10%): Worth investigating
- Red (>10%): Significant discrepancy

### Account Detail Screen

Tapping an account shows its detail view:

**Current Balance:**
- Large display of current balance
- [UPDATE] button to change balance
- Last updated timestamp

**Account Info:**
- Currency
- Role (default spending account, bills account, etc.)
- Story default (if this account is default for a specific story)

**Projection:**
- Per-account balance at key future dates
- Warning if account will go negative
- "✓ Always positive" if no issues

**Recent Activity:**
- Events assigned to this account
- Shows story tags for context

### Update Balance Flow

1. Tap [UPDATE] on account detail
2. Enter new balance
3. See difference displayed (e.g., "-£300")
4. Tap [SAVE]
5. Return to accounts list with "pending reconciliation" indicator

**Pending state:**
- Account row shows amber dot and "pending reconciliation"
- Info note warns changes will be applied on screen exit
- User can update more accounts before reconciliation runs

### Reconciliation Triggers

Reconciliation runs automatically when:
1. User leaves the accounts screen (back to dashboard)
2. User initiates a sync
3. User views any projection screen

This batched approach allows updating multiple accounts before reconciliation, resulting in cleaner adjustments.

### Settings Screen

Admin-only access to:
- User management
- Backup & restore (JSON export/import)
- Preferences (base currency, date format, baseline display months)
- Conversion rates
- Sync configuration

---

## 5. Key Concepts Illustrated

### Baseline

The baseline contains recurring events that happen regardless of any story:
- Salary (+£3,000 on the 28th)
- Rent (-£1,200 on the 1st)
- Bills (-£100 on the 1st)

Baseline events:
- Appear in EVERY story view (tagged as `[baseline]`)
- Have a subtle background highlight to distinguish them
- Are essential for accurate projections

### Gap Indicators

When viewing a filtered story, events from OTHER stories still affect your balance. Gap indicators show this hidden activity:

```
┄┄┄┄┄┄┄ -£1,226 other ┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄
```

- The dashed line indicates hidden events
- The amount shows the net impact
- Tap to expand and see the individual events
- Events are tagged with their source story

**Why this matters:** Without gaps, you might think you have more money available than you do. The gap reminds you that reality includes ALL your commitments.

### Funding Modes

Stories can have different funding modes:

**Projected (default)**
- Starting balance = whatever the global balance is on the story start date
- No adjustment, pure reality

**Projected + Adjustment**
- Starting balance = projected balance + additional amount
- Used for expected loans, gifts, bonuses

**Fixed (not shown in mockup)**
- Starting balance = specific amount you define
- Used for pure "what if" scenarios

### Hypothetical vs Real Funding

Funding transitions from hypothetical to real based on whether the story has started:

| Story State | Funding Status | Appears in ALL View | Visual Style |
|-------------|---------------|---------------------|--------------|
| Not started | Hypothetical | No | Amber amount, `[planned]` tag, amber warning |
| Started | Real | Yes | Green amount, normal event, blue info notice |

**Volvo example (started Oct 01):**
- Blue info notice: "ℹ This story includes additional funding"
- Loan is a real event with green +£500
- Appears in ALL view

**Skiing example (starts Dec 23, today is Dec 18):**
- Amber warning notice: "⚠ This story has hypothetical funding"
- Contribution is planned with amber +$500 and `[planned]` tag
- Does NOT appear in ALL view

**What happens when skiing starts (Dec 23)?**
On the next view load after Dec 23:
1. System detects story has started
2. Automatically converts the hypothetical funding event to real
3. Event changes from amber to green, loses `[planned]` tag
4. Now appears in ALL view
5. Warning changes from amber to blue

**If the expected contribution doesn't arrive?**
The user must manually delete the funding event. The system assumes all planned funding materialises - it's a projection tool, not an accounting system.

### Currency Conversion

CHAPTR uses a **base currency model**:

**Settings:**
```
Base currency: GBP
Rates:
  GBP → CAD: 1.72
  GBP → USD: 1.27
  GBP → EUR: 1.17
```

**Event storage:**
Each event stores:
- Amount in native currency
- Conversion rate to base currency (locked at creation)

**Conversion logic:**
1. Event amount → Base currency (using event's locked rate)
2. Base currency → Display currency (using current settings rate)

**Why lock rates at creation?**
- Preserves historical accuracy
- Projections don't shift when you update rates
- Only new/edited events use updated rates

**Example in skiing view:**
- Canada gifts: £150 × 1.72 = $258 CAD (shown in gap)
- Baseline salary: £3,000 × 1.72 = $5,160 CAD

### Goals

Each story can have a goal:

**spend_up_to** - Track cumulative expenses against a limit
- Used for trips, projects with a budget cap
- Funding doesn't affect spend calculation (spend tracks outgoings only)

**end_with_at_least** - Ensure final balance exceeds a target
- Used for savings goals, maintaining a buffer

**none** - Just track, no goal

### Account-Level Tracking

Each account can be:
- **Default spending account** - Unassigned events go here
- **Story default** - Events in that story go to this account
- **Bills account** - Just a label, no special behaviour

Events are assigned to accounts via hierarchy:
1. Event's explicit account → use it
2. Story's default account → use it
3. Global default account → fallback

### Reconciliation

Reconciliation keeps projections aligned with reality through automatic adjustments.

**Philosophy:** Automatic-first, manual second. The user just updates account balances; the system handles the rest.

**How it works:**

1. User updates one or more account balances
2. Balances are saved with "pending reconciliation" flag
3. When user leaves accounts screen (or syncs, or views projection):
   - System removes old `[auto]` adjustments for those accounts
   - Calculates projected balance vs actual balance
   - Creates new adjustment events for any drift

**Example - Transfer detected:**
```
Monzo:  Actual £2,500  |  Projected £2,180  |  Diff: +£320
HSBC:   Actual £10,680 |  Projected £11,000 |  Diff: -£320

Creates:
Dec 18 | balance adjustment | +£320 | account: Monzo [auto]
Dec 18 | balance adjustment | -£320 | account: HSBC [auto]
```

The system effectively records a transfer that happened but wasn't tracked.

**Fixing root causes:**
If the user later realises what caused the drift (e.g., an event was assigned to the wrong account), they can:
1. Edit the event to fix the account assignment
2. Re-reconcile (just update balances again, even to the same values)
3. Old `[auto]` adjustments are removed, new ones created if needed

This keeps the timeline clean over time.

---

## 6. The Numbers

### Master Timeline (Nov 18 → Jan 18)

This is the single source of truth. All views derive from this data.

| Date | Event | Source | Change | Balance |
|------|-------|--------|--------|---------|
| Nov 18 | Period start | -- | -- | £12,185 |
| Nov 28 | Salary | baseline | +£3,000 | £15,185 |
| Dec 01 | Rent | baseline | -£1,200 | £13,985 |
| Dec 01 | Bills | baseline | -£100 | £13,885 |
| Dec 05 | Labour | volvo | -£800 | £13,085 |
| Dec 10 | Family loan | volvo | +£500 | £13,585 |
| Dec 12 | Camshaft sensor | volvo | -£85 | £13,500 |
| **Dec 18** | **TODAY** | -- | -- | **£13,500** |
| Dec 20 | Car rental | canada | -£320 | £13,180 |
| Dec 22 | New tyres | volvo | -£380 | £12,800 |
| Dec 23 | Ski passes | skiing | -£349 | £12,451 |
| Dec 24 | Equipment | skiing | -£262 | £12,189 |
| Dec 25 | Gifts | canada | -£150 | £12,039 |
| Dec 26 | Lessons | skiing | -£465 | £11,574 |
| Dec 28 | Salary | baseline | +£3,000 | £14,574 |
| Jan 01 | Rent | baseline | -£1,200 | £13,374 |
| Jan 01 | Bills | baseline | -£100 | £13,274 |
| Jan 01 | Hotel | canada | -£400 | £12,874 |
| Jan 10 | MOT + service | volvo | -£350 | £12,524 |
| Jan 15 | Brake pads | volvo | -£182 | £12,342 |
| Jan 18 | Period end | -- | -- | £12,342 |

### Derived View Summaries

| View | Start Date | Start Balance | End Date | End Balance |
|------|------------|---------------|----------|-------------|
| ALL | Dec 18 | £13,500 | Jan 18 | £12,342 |
| canada-trip | Dec 04 | £13,885 | Jan 05 | £12,874 |
| volvo | Nov 18 | £12,185 | Jan 18 | £12,342 |
| skiing | Dec 23 | $22,016 ($22,516 with hypothetical) | Dec 28 | $25,068 ($25,568) |

### Story Spend Totals

| Story | Events | Total Spend |
|-------|--------|-------------|
| canada-trip | car rental, gifts, hotel | £870 |
| volvo | labour, sensor, tyres, MOT, brakes | £2,717 |
| skiing | passes, equipment, lessons | $1,850 |

Note: Volvo's £2,717 spend includes events before Nov 18 (£920 from Oct) not shown in the display window.

---

## 7. Visual Language

### Colours

| Colour | Meaning | Examples |
|--------|---------|----------|
| Green | Positive, on track, income | +£3,000, "✓ £130 LEFT", real funding amount |
| Red | Negative, over budget, expense | -£320, "⚠ £217 OVER" |
| Amber | Warning, hypothetical, planned | Hypothetical funding notice, `[planned]` amounts |
| Blue | Informational | Real funding notice |
| Grey/Dim | Inactive, past, secondary | Past events, tags, timestamps |

### Tags

| Tag | Meaning |
|-----|---------|
| `[baseline]` | Recurring event from baseline |
| `[story-name]` | Event from another story (in gaps) |
| `[planned]` | Hypothetical/planned event |

### Row Styling

| Style | Meaning |
|-------|---------|
| Dimmed (opacity) | Past event |
| Highlighted background | Baseline event |
| Indented + grey text | Revealed gap event |

### Notices

| Style | Icon | Meaning |
|-------|------|---------|
| Amber background | ⚠ | Warning - hypothetical funding |
| Blue background | ℹ | Info - real additional funding |

---

## 8. Implementation Notes

### What the Mockup Demonstrates

1. **Consistent calculations** - All views derive from the same master timeline
2. **Gap indicators** - Hidden events are visible and expandable
3. **Funding states** - Hypothetical vs real funding with distinct styling
4. **Currency conversion** - CAD story with converted amounts
5. **Goal tracking** - Spend vs budget independent of funding
6. **Baseline integration** - Recurring events appear in all story views

### What the Mockup Does NOT Demonstrate

1. Event creation/editing flows
2. Story creation with funding mode selection
3. Account balance update flow
4. Sync behaviour
5. Offline functionality
6. User authentication

These would be covered in additional mockups or the implementation phase.

---

## Document Version

| Version | Date | Changes |
|---------|------|---------|
| v1 | Dec 2024 | Initial explanation document |
| v1.1 | Dec 2024 | Added hypothetical funding lifecycle details |
| v1.2 | Dec 2024 | Added account detail screens, reconciliation workflow, account-level tracking, deferred reconciliation triggers |
