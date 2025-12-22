# CHAPTR - Personal Finance Projection System
## Design Specification v2.8

---

## Overview

CHAPTR is a mobile-friendly PWA for projecting personal finances across multiple contexts. The core problem it solves:

> "What's my actual financial position at a future date, given everything I know about upcoming income and expenses?"

This is NOT a budgeting app. It doesn't track individual transactions or tell you where to allocate money. Instead, it provides a clear projected trajectory of your money over time through the lens of "stories" - contextual containers for related financial activity.

**Two key questions CHAPTR answers:**
1. What disposable income do I have (if any)?
2. Will any account become empty without me realising it?

---

## Core Philosophy

- **Projection over tracking** - We care about where money is going, not where every penny went
- **Stories as layers** - Stories are views on top of shared financial reality, not isolated pots
- **Reality as anchor** - Accounts and baseline form the ground truth; hypotheticals are explicit opt-ins
- **Clarity over completeness** - A clear picture of key events beats a noisy list of transactions
- **Automatic-first, manual second** - System handles reconciliation automatically; user intervenes only when needed

---

## Core Concepts

### Accounts

Reference points for sanity-checking and per-account balance tracking. Where money actually lives.

- Manually updated balances (not synced to banks)
- Each has a currency
- Used to anchor the "reality" starting point
- Enable per-account projections and warnings

| Field | Type | Description |
|-------|------|-------------|
| id | UUID | Unique identifier |
| name | String | "Monzo", "HSBC", "Kat Credit" |
| currency | String | GBP, CAD, USD, etc. |
| current_balance | Decimal | Manually updated snapshot |
| balance_updated_at | DateTime | When balance was last updated |
| is_default | Boolean | Is this the global default spending account? |
| is_archived | Boolean | Archived accounts are hidden but retained for history |
| pending_reconciliation | Boolean | True if balance updated but reconciliation not yet run |

#### Global Default Account

- One account must be marked as `is_default = true`
- Required on first account creation ("This will be your main spending account")
- Used as fallback when no story-level default is set
- Typically the daily spending account (e.g., Monzo)

#### Archived Accounts

- When an account is closed, set `is_archived = true`
- Archived accounts retain historical events
- Cannot be selected for new events or as defaults
- Hidden from active account lists

---

### Baseline

The drumbeat of your financial life. Contains:

- **Recurring events** - Salary, rent, subscriptions, groceries
- **One-off planned events** - Tax refund, bonus, one-time purchases not tied to a story

Baseline is always included in projections regardless of which story filter is active.

| Field | Type | Description |
|-------|------|-------------|
| id | UUID | Unique identifier |
| description | String | "Salary", "Rent", "Netflix" |
| amount | Decimal | Positive = income, negative = expense |
| currency | String | Native currency of this event |
| rate_to_base | Decimal | Conversion rate to base currency |
| account_id | UUID | **Required** - which account this affects |
| date | Date | For one-off events |
| is_recurring | Boolean | Does this repeat? |
| recurrence | Object | Frequency details if recurring |

#### Recurrence Object

```json
{
  "frequency": "monthly" | "weekly" | "annual",
  "day": 28,
  "end_date": null
}
```

#### Recurring Event Generation

Recurring events are generated on-the-fly within the baseline display window (default: ±1 month from today, configurable in settings).

**Server-side generation:**
- When a view is requested, the server checks if recurring events exist for the display window
- Missing recurring events are generated and persisted
- This requires sync to function (PWA must be online)

**Editing recurring events:**
- Changes to a specific instance only affect that instance
- To change the schedule (e.g., salary date changes), user must:
  1. Update the affected instance(s) manually
  2. Edit the recurrence rule for future events

**Adding recurring events:**
- Recurring events have a dedicated creation screen
- User specifies: description, amount, frequency, day of month/week, start date, optional end date
- **Account is required** for baseline events (they're recurring, worth setting up properly)

---

### Stories

A container for related financial activity within a date range. Stories are **layers** on top of shared reality - they don't hold money, they represent planned spending/income for a specific context.

| Field | Type | Description |
|-------|------|-------------|
| id | UUID | Unique identifier |
| name | String | "canada-trip", "volvo", "skiing-2025" |
| start_date | Date | When this story begins |
| end_date | Date | When this story ends (null for ongoing) |
| default_account_id | UUID | Optional - default account for events in this story |
| funding_mode | Enum | How starting balance is determined |
| funding_amount | Decimal | For fixed or adjustment modes |
| goal_type | Enum | Optional goal for this story |
| goal_amount | Decimal | Target amount if goal set |
| display_currency | String | Currency for this story's view |
| created_at | DateTime | For conflict resolution |

#### Story Default Account

Each story can have a `default_account_id`:
- Events in this story use this account unless overridden
- Natural fit for context: "Canada trip expenses go on the Canadian credit card"
- If not set, falls back to global default account

**Example configuration:**
```
canada-trip:  default_account = Kat Credit (CAD)
volvo:        default_account = HSBC
skiing:       default_account = Kat Credit (CAD)
```

#### Funding Modes

| Mode | Description |
|------|-------------|
| `projected` | Start with projected balance on start date (default) |
| `fixed` | Start with a specific amount (hypothetical) |
| `projected_plus` | Projected balance + an adjustment (e.g., expected loan) |

#### Hypothetical Funding Lifecycle

Funding adjustments (`fixed` or `projected_plus`) create a **funding event** that transitions from hypothetical to real:

**Architecture:** Funding events are the **single source of truth** for funding amounts. When a story has `fixed` or `projected_plus` funding mode:
- Starting balance does NOT include the funding_amount
- Instead, a funding event is created with `is_hypothetical=true`
- This funding event participates in the running balance calculation just like any other event
- Result: Clear audit trail showing exactly where the funding came from

**Example: Fixed mode with $2,000 funding**
```
Starting balance:        $0
+$2,000 funding [planned] → $2,000  (hypothetical event)
-$600 ski passes          → $1,400
-$450 equipment           → $950
```

**Before story starts:**
- Funding event is marked as `[planned]`
- Displayed with amber colouring
- Does NOT appear in ALL view (hypothetical events excluded from ALL view)
- Warning shown: "⚠ This story has hypothetical funding"

**When story starts (on next view load):**
- System automatically converts hypothetical funding to real
- Funding event becomes a normal event (green colouring, no `[planned]` tag)
- Now appears in ALL view
- Warning changes to: "ℹ This story includes additional funding" (blue)

**If funding doesn't materialise:**
- User must manually delete the funding event
- Deleting removes the event, warning, and recalculates all balances
- This is the user's responsibility - the system assumes planned funding happens

**Important:** This is a projection system, not an accounting system. We're not tracking "real" money - we're modelling expected cash flow. If reality differs from projection, the user updates their events accordingly.

#### Goal Types

| Type | Description |
|------|-------------|
| `end_with_at_least` | Projected final balance must stay above goal_amount |
| `spend_up_to` | Cumulative story expenses must stay below goal_amount |
| `none` | No goal, just track |

**Note:** Goals are display-only indicators. Changing a goal does not affect past calculations or the projection engine - it simply changes what status is shown. Goals have no history.

#### Story Lifecycle

**Active stories:**
- Stories with a date range that includes today (or future)
- Shown prominently on dashboard
- Can have events added

**Ended stories (fixed end date):**
- Stories whose end_date has passed
- Remain visible in dashboard until baseline window shifts them fully into the past
- Still tappable to view historical projection
- Events can still be edited but not typically added

**Ongoing stories (no end date):**
- Stories like "volvo" with end_date = null
- Run indefinitely until user sets an end date
- To close: user must input an end date

**Deleting stories:**
- Deleting a story deletes ALL events belonging to that story
- Running totals are automatically recalculated
- This is a destructive action - consider archiving instead (future feature)

---

### Events

A point in time where money moves. Belongs to either baseline or a story.

| Field | Type | Description |
|-------|------|-------------|
| id | UUID | Unique identifier |
| date | Date | When this event occurs |
| description | String | "Car rental", "Hotel deposit" |
| amount | Decimal | Positive = income, negative = expense |
| currency | String | Native currency of this event (GBP, CAD, etc.) |
| rate_to_base | Decimal | Conversion rate to base currency, locked at creation |
| account_id | UUID | **Required** - resolved at creation via hierarchy, stored permanently |
| story_id | UUID | Which story this belongs to (null for baseline) |
| is_baseline | Boolean | True if this is a baseline event |
| is_hypothetical | Boolean | True if this is a planned/hypothetical funding event |
| is_auto_adjustment | Boolean | True if created by reconciliation system |
| created_at | DateTime | When event was created (used for same-day ordering) |
| created_by | UUID | User who created the event |
| updated_at | DateTime | When event was last modified |
| updated_by | UUID | User who last modified (for conflict detection) |

#### Account Resolution at Creation

When an event is created, the account is resolved via hierarchy and **stored permanently**:

1. **User specifies account_id** → use it
2. **Story's default_account_id** → use it
3. **Global default account** → use it (fallback)

The resolved `account_id` is stored on the event. Changing a story's default account only affects future events, not existing ones.

#### Currency and Account Independence

An event's currency and account are independent:
- A GBP event can be assigned to a CAD account
- The event stores its native currency and rate_to_base
- The account determines which balance is affected
- Currency conversion happens at display time

#### Editing Events

- **Past events CAN be edited** - users may need to correct mistakes
- **Editing triggers recalculation** - all subsequent running balances are updated
- **Currency rate on edit** - user is prompted to update rate to current or keep existing
- **Changing account_id** - triggers recalculation for both old and new account projections

#### Event Overlap

- Multiple stories can have events on the same date
- No restrictions on story overlap - the system handles it via gap indicators

**Same-day ordering:**
Events on the same date are ordered to minimize balance dips:
1. Amount DESC (income first, largest amounts first)
2. created_at ASC (earlier created events first)

This ensures that if you have both income and expenses on the same day, income is applied first to avoid unnecessary negative balance warnings.

---

## Account-Level Projection

The system calculates projections at both **total level** and **per-account level**.

### Total Projection

```
starting_balance = sum of all account balances

for each date in range:
    for each event on this date:
        running_balance += event.amount (converted to base currency)
```

### Per-Account Projection

```
for each account:
    starting_balance = account.current_balance
    
    for each date in range:
        for each event assigned to this account:
            running_balance += event.amount
```

### Account Assignment

Events are assigned to accounts via the resolution hierarchy:
1. Explicit `account_id` on event
2. Story's `default_account_id`
3. Global default account

### Per-Account Warnings

The system warns when any account is projected to go negative:

```
⚠ Monzo will go negative on Dec 22
   Projected: -£320
   Consider transferring funds from HSBC
```

This catches the critical scenario: "I have money, but it's in the wrong account."

---

## Reconciliation System

Reconciliation keeps projections aligned with reality through automatic adjustments.

### Philosophy

- **Automatic-first, manual second** - System handles drift automatically
- **User updates balances, system handles the rest** - Simple UX
- **Clean up when root cause is fixed** - No accumulation of stale adjustments

### How It Works

**Triggers:** Reconciliation runs automatically at specific moments (deferred/batched approach):

1. **On exit from accounts screen** - catches all balance updates made during that session
2. **On sync** - ensures everything is reconciled before pushing to server
3. **On viewing any projection screen** - ensures projection always reflects latest reality

This batched approach allows users to update multiple account balances before reconciliation runs, resulting in cleaner adjustments (e.g., a transfer creates two related adjustments in one pass rather than separate unrelated adjustments).

**Process:**
1. Identify all accounts with `pending_balance` (updated but not yet reconciled)
2. Remove all existing `[auto]` adjustment events for those accounts
3. Calculate projected balance for each account at current date
4. Compare to actual (newly entered) balance
5. If drift detected, create adjustment event(s)
6. Clear `pending_balance` flags

**Account balance update flow:**
1. User taps account → enters new balance → saves
2. Balance is stored with `pending_reconciliation = true`
3. User can update more accounts
4. On trigger (exit/sync/view projection), reconciliation runs for all pending accounts

**Example - Single account drift:**
```
Monzo:  Actual £2,200  |  Projected £2,500  |  Diff: -£300

Creates:
Dec 18 | balance adjustment | -£300 | account: Monzo [auto]
```

**Example - Multi-account drift (implicit transfer):**
```
Monzo:  Actual £2,500  |  Projected £2,180  |  Diff: +£320
HSBC:   Actual £10,680 |  Projected £11,000 |  Diff: -£320

Creates:
Dec 18 | balance adjustment | +£320 | account: Monzo [auto]
Dec 18 | balance adjustment | -£320 | account: HSBC [auto]
```

This effectively records a transfer that happened in reality but wasn't tracked.

### Auto-Adjustment Events

| Field | Value |
|-------|-------|
| description | "balance adjustment" |
| is_auto_adjustment | true |
| account_id | The account being adjusted |
| story_id | null (not part of any story) |
| date | Current date |

**Display:**
- Tagged as `[auto]` in the UI
- Appear in ALL view
- Do NOT appear in filtered story views (they're account-level, not story-level)
- Styled subtly (grey/dim) to distinguish from real events

### Smart Cleanup

When reconciliation runs:
1. **Delete** all existing `[auto]` adjustments for affected accounts
2. **Recalculate** what adjustments are needed now
3. **Create** new adjustments only if drift exists

This means:
- Fixing the root cause (e.g., assigning correct account to an event) and re-reconciling cleans up automatically
- No accumulation of stale adjustment events
- User can always "reset" by just updating account balances

### Fixing Root Causes

**Scenario:** User realises car rental came from HSBC, not Monzo.

1. Edit the car rental event: set `account_id = HSBC`
2. Trigger reconciliation (update account balances, even to same values)
3. Old `[auto]` adjustments are deleted
4. New drift is calculated (likely zero now)
5. Result: clean timeline, no adjustment events needed

### Handling Transfers

Explicit transfers between accounts (e.g., moving £500 from HSBC to Monzo) are handled automatically:

1. User performs transfer in real bank accounts
2. User updates both account balances in CHAPTR
3. System creates two `[auto]` adjustments that net to zero
4. Projection stays accurate

For users who want explicit tracking:
- Create two manual events: `-£500 HSBC`, `+£500 Monzo`
- Or simply let auto-adjustments handle it

### Future Enhancement: Reconciliation Prompts

If the system detects frequent `[auto]` adjustments on a particular account or story, it could prompt:

> "You've had 5 adjustments on Monzo this month. Would you like to review your recent events?"

This encourages users to fix root causes rather than relying on auto-adjustment.

---

## Story Assignment Rules

When adding an event:

1. **If adding from story detail view** → Assign to that story
2. **If adding from ALL/dashboard view** → Auto-assign based on date:
   - Find all stories whose date range contains the event date
   - If one story → assign to it
   - If multiple stories → assign to **shortest duration** story (most specific)
   - If equal duration → prompt user to choose
   - If no story covers date → assign to baseline

Users can always manually navigate to a specific story to add events directly to it.

---

## Projection Engine

The projection is the heart of CHAPTR. It calculates a timeline of events with running balances.

### Global Calculation (ALL View)

```
starting_balance = sum of all account balances

for each date in range:
    for each event on this date (baseline + all stories):
        running_balance += event.amount
        record milestone
```

### Filtered Calculation (Story View)

**Architecture Note:** Funding events are the single source of truth for funding amounts. The starting_balance does NOT include `funding_amount` - instead, a hypothetical funding event is created (see lines 163-182) that adds the funding to the running balance. This ensures a clear audit trail and consistent event-based calculation.

```
if story.funding_mode == 'projected':
    starting_balance = calculate projected balance on story.start_date
    # No funding event created
else if story.funding_mode == 'fixed':
    starting_balance = 0
    # Create funding event for story.funding_amount (marked is_hypothetical=true)
else if story.funding_mode == 'projected_plus':
    starting_balance = calculate projected balance on story.start_date
    # Create funding event for story.funding_amount (marked is_hypothetical=true)

for each date in story range:
    for each event on this date (baseline + this story):
        display event if (baseline OR this story)
        running_balance += ALL events (including hidden stories and funding events)
        if balance changed by hidden events:
            record gap indicator with delta
```

### Gap Indicators

When filtered to a story, other stories' events are hidden but still affect the balance. When this happens:

- Show a subtle gap indicator between visible events
- Display the delta amount (converted to story's display currency)
- Make it tappable to reveal hidden events

```
Dec 20  car rental             -£320   £14,977
        ┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄ -£180 ┄┄┄┄┄┄┄┄┄  ← tappable
Dec 25  gifts                  -£150   £14,647
```

Expanded:

```
Dec 20  car rental             -£320   £14,977
   Dec 22  parts [volvo]       -£180   £14,797  ← revealed
Dec 25  gifts                  -£150   £14,647
```

---

## Views

### Dashboard (Home)

The entry point. Shows at a glance:

- **Stories list** - All active stories with status indicators
- **Accounts list** - Current balances for reference
- **Global projection summary** - Next key milestone, any warnings
- **Reconciliation status** - Drift indicator if accounts ≠ projected

**Drift indicator:**
```
ACCOUNTS         £13,500  (updated 2h ago)
PROJECTED NOW    £13,247
DRIFT            +£253 (1.9%)  ← green if <5%, amber if 5-10%, red if >10%
```

Navigation:
- Tap story → Projection view filtered to that story
- Tap MANAGE on accounts → Accounts screen
- Tap ⚙ → Settings (admin only visible)

### Projection View

The primary view. A timeline of events with running balance.

**Header shows:**
- Current filter (ALL or story name)
- Date range
- Funding mode indicator if hypothetical

**Filter options:**
- ALL (reality) - default
- ALL (what-if) - includes hypothetical funding
- Individual stories
- Baseline only

**Timeline shows:**
- TODAY marker
- Events in date order with source tags
- Running balance after each event
- Gap indicators for hidden activity
- Auto-adjustment events (styled subtly)
- End summary with goal status if applicable

### Accounts Screen

Manage reference accounts.

- List all accounts with balance and currency
- Per-account projected balance
- Total by currency summary
- Add/edit/delete accounts
- Update balances (triggers reconciliation)
- Archive closed accounts

**Per-account projection:**
```
Monzo (GBP)
  Current: £2,500
  Dec 31:  £1,180
  Jan 31:  £2,340
  ✓ Always positive

HSBC (GBP)
  Current: £11,000
  Dec 31:  £9,700
  Jan 31:  £12,700
  ✓ Always positive
```

Info note reminds users these are reference points for sanity-checking.

### Settings Screen (Admin only)

**Users**
- Add/remove users
- Change roles (admin/user)

**Backup & Restore**
- Export all data as JSON
- Import/restore from JSON
- Last backup date

**Preferences**
- Default currency
- Base currency (for conversions)
- Date format (DD/MM/YYYY)
- Baseline display months (how many months to show in baseline-only view)

**Conversion Rates**
- Rates from base currency to each other currency
- Manually maintained
- Only affects new/edited events

**Sync**
- Server URL
- Force sync
- Clear local data (dangerous)

**About**
- Version

---

## Warning System

Warnings trigger when:

1. **Global balance goes negative** at any point
   > "⚠ Balance goes -£340 on Jan 3rd"

2. **Account balance goes negative** at any point
   > "⚠ Monzo will go negative on Dec 22 (-£320)"

3. **Story exceeds goal** (spend_up_to type)
   > "⚠ VOLVO: £847 over budget"

4. **Story misses goal** (end_with_at_least type)
   > "⚠ CANADA: Projected £2,800, goal was £3,000"

5. **Hypothetical mode active** (subtle reminder)
   > "⚠ This story has hypothetical funding"

6. **Real funding mode** (informational)
   > "ℹ This story includes additional funding"

7. **Significant drift** (>10% difference between accounts and projection)
   > "⚠ Accounts differ from projection by £1,350 (10.2%)"

---

## Multi-Currency Handling

CHAPTR uses a **base currency model** for converting between multiple currencies (GBP, CAD, USD, EUR, etc.).

### Settings Configuration

```
base_currency: GBP
rates:
  CAD: 1.72  (1 GBP = 1.72 CAD)
  USD: 1.27  (1 GBP = 1.27 USD)
  EUR: 1.17  (1 GBP = 1.17 EUR)
```

### Event Storage

Each event stores its amount in its native currency, plus the conversion rate to base currency at time of creation:

| Field | Type | Description |
|-------|------|-------------|
| amount | Decimal | The amount in native currency |
| currency | String | The native currency (GBP, CAD, etc.) |
| rate_to_base | Decimal | Conversion rate to base currency, locked at creation |

Example:
```
Event:
  amount: 500
  currency: CAD
  rate_to_base: 0.58  (1 CAD = 0.58 GBP at time of creation)
```

### Conversion Logic

To display an event in any currency:

1. **Event → Base currency**: `amount × rate_to_base`
2. **Base → Display currency**: `base_amount × settings.rates[display_currency]`

Example: Display 500 CAD as EUR
1. 500 CAD × 0.58 = 290 GBP (using event's locked rate)
2. 290 GBP × 1.17 = 339.30 EUR (using current settings rate)

### Rate Locking Behaviour

- **At event creation**: Current rate from settings is stored as `rate_to_base`
- **Rate is permanent**: The stored rate never changes unless the event is edited
- **Editing an event**: Prompts to update rate to current, or keep existing
- **Settings rate changes**: Only affect NEW events and EDITED events
- **Historical accuracy**: Old events retain their original conversion rate

### Display Currency

- **ALL view**: Toggle to switch between any configured currency
- **Story view**: Each story has a `display_currency` setting
- **Gap indicators**: Always shown in the current view's display currency (converted)
- **Dashboard**: Shows amounts in each story's native currency
- **Accounts**: Shown in their native currency, with "Total by currency" summary

### Why This Approach?

- **Simple**: Only need to maintain rates from base currency to others
- **Flexible**: Easy to add new currencies (just add a rate)
- **Accurate enough**: Triangular conversion introduces minor inaccuracy, acceptable for projection purposes
- **Historically stable**: Events retain the rate they were created with, so projections don't shift when rates update

---

## User Roles

| Role | Capabilities |
|------|--------------|
| Admin | Full access including settings, user management, backup/restore |
| User | Everything except settings |

Both roles can:
- View all projections
- Add/edit events
- Update account balances
- Create/edit stories

---

## Technical Architecture

### Stack

| Layer | Technology | Purpose |
|-------|------------|---------|
| Backend | Python (FastAPI) | JSON API, sync endpoint, business logic |
| Server Database | MongoDB | Persistent storage, multi-device sync |
| Frontend | Alpine.js | Reactive UI, declarative HTML |
| Client Database | Dexie.js (IndexedDB) | Offline storage, source of truth for UI |
| PWA | Workbox | Service worker, caching, background sync |
| Hosting | Home server | Accessed via VPN |
| SSL | Pre-configured | Required for service workers |

### Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                      Browser                            │
│  ┌───────────────────────────────────────────────────┐  │
│  │  Alpine.js                                        │  │
│  │  - Renders UI from local data                     │  │
│  │  - Handles user interactions                      │  │
│  │  - Reads/writes to Dexie                          │  │
│  └───────────────────────────────────────────────────┘  │
│                         │                               │
│                         ▼                               │
│  ┌───────────────────────────────────────────────────┐  │
│  │  Dexie.js (IndexedDB)                             │  │
│  │  - Local database (works offline)                 │  │
│  │  - Source of truth for UI                         │  │
│  │  - Queues changes for sync                        │  │
│  └───────────────────────────────────────────────────┘  │
│                         │                               │
│                         ▼                               │
│  ┌───────────────────────────────────────────────────┐  │
│  │  Workbox (Service Worker)                         │  │
│  │  - Caches static assets (HTML, CSS, JS)           │  │
│  │  - Enables offline access                         │  │
│  │  - Background sync when online                    │  │
│  └───────────────────────────────────────────────────┘  │
└─────────────────────────│───────────────────────────────┘
                          │ (when online)
                          ▼
┌─────────────────────────────────────────────────────────┐
│  Python API (FastAPI)                                   │
│  - /api/sync endpoint                                   │
│  - Receives changes, returns updates                    │
│  - Conflict detection                                   │
│  - Snapshot management (server-side)                    │
└─────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│  MongoDB                                                │
│  - Server-side storage                                  │
│  - Multi-user data                                      │
└─────────────────────────────────────────────────────────┘
```

### Project Structure

```
/chaptr
├── /static
│   ├── /js
│   │   ├── app.js              # Alpine components & screens
│   │   ├── db.js               # Dexie schema & queries
│   │   ├── sync.js             # Sync logic & conflict handling
│   │   └── projection.js       # Balance calculation logic
│   ├── /css
│   │   └── style.css           # Terminal aesthetic styles
│   └── sw.js                   # Workbox service worker
├── /api
│   ├── sync.py                 # Main sync endpoint
│   ├── auth.py                 # User authentication
│   └── backup.py               # Export/import endpoints
├── index.html                  # Single-page app shell
├── manifest.json               # PWA manifest
└── main.py                     # FastAPI application
```

### Why This Stack?

**Alpine.js:**
- Minimal learning curve, declarative HTML
- No build step required
- Small footprint (~15kb)
- Perfect for app of this scale

**Dexie.js:**
- Makes IndexedDB pleasant to use
- Promise-based API
- Observable queries (UI updates when data changes)
- Handles schema migrations

**Workbox:**
- Google-maintained, battle-tested
- Simplifies service worker complexity
- Built-in caching strategies
- Background sync API for offline queuing

### Offline-First Data Flow

**User adds event (offline):**
```
1. User fills form, clicks save
2. Alpine calls db.events.add(newEvent)
3. Dexie writes to IndexedDB
4. Change queued in sync_queue table
5. Alpine re-renders (event appears immediately)

(Later, device comes online)

6. Workbox detects connection
7. Sync logic pushes queued changes to /api/sync
8. Server processes, returns conflicts (if any)
9. Dexie updates local data with server response
10. If conflicts exist, Alpine shows resolution UI
```

### Calculation Logic

Running balance calculations happen **client-side** in JavaScript:
- Works offline without server
- Simple logic (sum events in order)
- Server focused on storage and sync only

```javascript
// projection.js (simplified)
function calculateProjection(accounts, events, startDate, endDate) {
    let balance = accounts.reduce((sum, a) => sum + a.current_balance, 0);
    
    const results = [];
    for (const event of events) {
        balance += event.amount;
        results.push({ ...event, running_balance: balance });
    }
    return results;
}
```

### PWA Requirements

**Manifest (manifest.json):**
```json
{
    "name": "CHAPTR",
    "short_name": "CHAPTR",
    "start_url": "/",
    "display": "standalone",
    "background_color": "#0a0a0a",
    "theme_color": "#4af626",
    "icons": [...]
}
```

**Service Worker (via Workbox):**
- Cache-first for static assets (HTML, CSS, JS)
- Network-first for API calls (with offline fallback)
- Background sync for queued changes

### Data Architecture: Pseudo Event Sourcing

CHAPTR uses a **pseudo event sourcing** model where events are the source of truth but are mutable (not append-only).

#### Core Principles

- **Events are mutable rows:** Standard CRUD operations (INSERT/UPDATE/DELETE)
- **Running balance is calculated, never stored:** Derived on query from events
- **Account balances are the "now" anchor:** User-entered current state
- **Snapshots are optional performance optimization:** For historical queries only

#### Why Pseudo Event Sourcing?

| Benefit | How We Get It |
|---------|---------------|
| Single source of truth | Events ARE the data |
| Derived views | ALL, story, account views calculated from events |
| Simple implementation | Standard CRUD, no replay logic |
| Easy corrections | Just UPDATE or DELETE, then recalculate |

What we intentionally skip:
- Full audit trail (not needed for this app)
- Time travel / undo (users can manually fix mistakes)
- Event replay (snapshots handle historical queries)

#### Calculation Flow

**For future projections (most common):**
```
1. Start from account.current_balance for each account
2. "Now" = start of today
3. Load events from today onwards
4. Calculate running balance on the fly
5. Return events with calculated balances
```

**For historical queries:**
```
1. Find most recent valid snapshot before query date
2. Load events from snapshot date to query date
3. Calculate running balance starting from snapshot
4. Return result
```

#### Same-Day Event Ordering

Events on the same date are sorted to minimize balance dips:
```sql
ORDER BY date ASC, amount DESC, created_at ASC
```
This applies income before expenses, reducing unnecessary negative balance warnings.

### Snapshots

Snapshots are periodic checkpoints storing calculated balances at a point in time.

#### Snapshot Data Structure

```
snapshots collection:
  id: UUID
  date: Date                      # "Valid as of end of this date"
  total_balance: Decimal          # Total in base currency
  account_balances: {             # Per-account for future flexibility
    account_id_1: Decimal,
    account_id_2: Decimal,
    ...
  }
  created_at: DateTime
```

#### Snapshot Creation Triggers

| Trigger | Rationale |
|---------|-----------|
| Story ends | Period is closed, unlikely to change |
| Month boundary | Natural checkpoint (1st of each month) |
| After reconciliation | Accounts verified, good time to checkpoint |
| Manual (admin) | "I've verified everything up to today" |

#### Snapshot Invalidation

When an event is added, modified, or deleted:
1. Find all snapshots with date >= event date
2. Recalculate those snapshots immediately (background task if needed)
3. Keep database in valid state at all times

**Date change handling:** If an event's date moves from Dec 10 to Dec 20, invalidate all snapshots between Dec 10 and Dec 20 (inclusive).

#### Snapshots and "Now"

- **Snapshots are for the past only** - they help answer "what was my balance on Nov 15?"
- **Account balances are for "now"** - user-entered current reality
- **Future projection starts from account balances**, not snapshots

### Recurring Event Generation

Recurring events (salary, rent, etc.) are stored as rules and materialized as actual event rows.

#### Generation Window

- Default: ± 1 month from today (configurable per user)
- Events are generated as real rows within this window
- Generation happens on sync (server-side)

#### Generation Rules

```
recurring_rules collection:
  id: UUID
  description: String
  amount: Decimal
  currency: String
  account_id: UUID
  frequency: "weekly" | "monthly" | "annual"
  day: Integer                    # Day of week (1-7) or month (1-31)
  start_date: Date
  end_date: Date (nullable)       # Null = ongoing
```

#### Lifecycle

- **Creation:** Rule created, events generated within window
- **Modification:** Future generated events updated, past events unchanged
- **Deletion:** Rule deleted, all FUTURE generated events deleted, past events remain
- **End date set:** No new events generated after end date

### First Use / Opening Balance

Account balances serve as the implicit starting point:
- No "opening balance" events are created
- First event's running balance = account balance + event amount
- This keeps the event list clean and meaningful

### Initial Load

On first visit (or after cache clear):
1. Service worker caches app shell (HTML, CSS, JS)
2. App fetches all user data from /api/sync
3. Dexie populates IndexedDB with server data
4. Alpine renders UI from local data
5. App is now fully functional offline

### Sync Strategy

**Manual sync** (user taps sync button):
1. Push local changes (queued in sync_queue)
2. Pull server changes (other devices/users)
3. Detect and surface conflicts
4. Update local IndexedDB
5. Re-render UI

**Background sync** (when connection restored):
- Workbox automatically retries failed sync requests
- Non-blocking, happens in service worker

**Snapshots:** Server-side only, not synced to clients. Clients calculate projections from raw events.

### Sync Protocol

#### Client-Side Data Structures

```javascript
// Dexie schema
db.version(1).stores({
    accounts: 'id, name, currency',
    stories: 'id, name, start_date, end_date',
    events: 'id, date, story_id, account_id, [date+amount]',
    recurring_rules: 'id, frequency',
    conflicts: 'id, entity_id, resolved',
    
    // Sync tracking
    sync_queue: '++id, entity_type, entity_id, action, queued_at',
    sync_meta: 'key'  // stores last_sync_at, client_id
});
```

#### Sync Queue

Every local change gets queued for sync:

```javascript
// On local change
await db.events.add(event);
await db.sync_queue.add({
    entity_type: 'event',
    entity_id: event.id,
    action: 'create',  // or 'update' or 'delete'
    data: event,       // null for deletes
    base_updated_at: originalEvent?.updated_at,  // for conflict detection
    queued_at: new Date().toISOString()
});
```

#### Push Phase (Client → Server)

```
POST /api/sync

{
    "client_id": "device-uuid",
    "last_sync_at": "2024-12-18T10:00:00Z",
    "changes": [
        {
            "entity_type": "event",
            "entity_id": "uuid-1",
            "action": "create",
            "data": { ...event... }
        },
        {
            "entity_type": "event",
            "entity_id": "uuid-2",
            "action": "update",
            "data": { ...event... },
            "base_updated_at": "2024-12-17T09:00:00Z"
        },
        {
            "entity_type": "event",
            "entity_id": "uuid-3",
            "action": "delete",
            "base_updated_at": "2024-12-16T14:00:00Z"
        }
    ]
}
```

#### Server Processing

For each change:
- **Create:** Insert entity, append to change_log
- **Update:** Check for conflict (compare base_updated_at with server's updated_at)
  - No conflict: Update entity, append to change_log
  - Conflict: Add to conflicts response
- **Delete:** Check for conflict
  - No conflict: Hard delete entity, append to change_log with action: "delete"
  - Conflict (edited since): Add to conflicts response

#### Pull Phase (Server → Client)

Server queries change_log for changes since last_sync_at (excluding this client):

```json
{
    "applied": ["uuid-1", "uuid-2"],
    "conflicts": [
        {
            "entity_type": "event",
            "entity_id": "uuid-3",
            "conflict_type": "edit_edit",
            "client_version": { ... },
            "server_version": { ... }
        }
    ],
    "server_changes": [
        {
            "entity_type": "event",
            "entity_id": "uuid-99",
            "action": "create",
            "data": { ... }
        },
        {
            "entity_type": "event",
            "entity_id": "uuid-50",
            "action": "delete"
        }
    ],
    "sync_timestamp": "2024-12-18T10:08:00Z",
    "full_sync_required": false
}
```

#### Client Response Processing

1. Clear applied items from sync_queue
2. Store conflicts for user resolution
3. Apply server_changes to IndexedDB (create/update/delete)
4. Update last_sync_at
5. If conflicts exist, show resolution UI

### Change Log

Server maintains a change log for sync protocol:

```
change_log collection:
    id: UUID
    entity_type: String         # "event", "account", "story", etc.
    entity_id: UUID
    action: String              # "create", "update", "delete"
    data: Object                # Entity snapshot (null for deletes)
    changed_by_user: UUID
    changed_by_client: UUID     # Device that made the change
    changed_at: DateTime
```

**Hard delete everywhere:** When an entity is deleted, it's removed from its collection. The change_log records `action: "delete"` so other clients know to delete locally.

#### Change Log Pruning

To prevent unbounded growth:

```python
# Daily cleanup job
def prune_change_log():
    cutoff = today() - timedelta(days=31)
    db.change_log.delete_many({ changed_at: { $lt: cutoff } })
```

#### Stale Client Handling

If a client's last_sync_at is older than the oldest change_log entry:

```json
{
    "full_sync_required": true,
    "reason": "Client too far behind, change log pruned"
}
```

Client must clear local database and re-download all data:

```javascript
if (response.full_sync_required) {
    await db.delete();          // Clear all local data
    await db.open();            // Recreate schema
    await fullSync();           // Fetch everything from server
}
```

### Recurring Event Generation

Recurring rules sync to server. Server generates actual event rows:

1. Rules stored in recurring_rules collection
2. On sync, server generates events within window (±1 month)
3. Generated events have `recurring_rule_id` reference
4. Generated events included in pull response

### Backup

- JSON export to server filesystem
- Admin-only function via /api/backup endpoint
- Captures: accounts, stories, events, recurring_rules, change_log, snapshots, settings, users
- Import validates data before overwriting

---

## Command Bar (Context-Sensitive)

| Screen | + Button | $ Button | ↻ Button | ? Button |
|--------|----------|----------|----------|----------|
| Dashboard | Add event (auto-assign) | Update account balance | Sync | General help |
| Projection/Story | Add event to this story | Edit story funding | Sync | Story help |
| Accounts | Add account | Update balance | Sync | Accounts help |

---

## UI Design

- **Aesthetic**: Terminal/console style, green on black
- **Font**: JetBrains Mono
- **Colours**:
  - Green (#4af626) - positive, on track
  - Red (#ff4444) - negative, warnings
  - Amber (#ffaa00) - approaching limits, hypothetical
  - Blue (#6495ED) - informational
  - Dim grey (#666) - inactive, secondary info, auto-adjustments
- **Layout**: Mobile-first, single column, minimal chrome
- **Interactions**: Tap to navigate, command bar for actions

---

## Open Questions

1. **Baseline "story"** - Is baseline shown as a special story in the filter list, or a separate toggle?

2. **Story overlap visibility** - In the stories list on dashboard, should we indicate which stories overlap?

---

## Multi-User Conflict Resolution

CHAPTR uses a **detect and resolve** approach to handle conflicts from offline edits.

### Philosophy

- **Detect** conflicts rather than prevent them
- **Surface** them clearly to the user
- **Resolve** with a simple choice (no merging)
- **Reconciliation** catches any lingering issues automatically

### When Conflicts Occur

| Scenario | Conflict? | Handling |
|----------|-----------|----------|
| Both users edit same event | Yes | Flag, prompt to pick one |
| One deletes, one edits same event | Yes | Flag, prompt to keep deleted or restore |
| Both delete same event | No | Already deleted |
| Both create similar events | No | Both created (duplicates are obvious) |

### Conflict Detection

On sync, the system compares timestamps:

```python
for event in local_changes:
    server_event = db.events.find_one(event.id)
    
    if server_event is None:
        # New event, just insert
        db.events.insert(event)
    
    elif server_event.updated_at == event.base_updated_at:
        # No conflict, server unchanged since last sync
        db.events.update(event)
    
    else:
        # Conflict - server changed since we last synced
        create_conflict(event, server_event)
```

### Conflict Data Structure

```
conflicts collection:
  id: UUID
  entity_type: "event" | "story"
  entity_id: UUID
  local_version: { ...full entity data... }
  server_version: { ...full entity data... }
  local_user_id: UUID
  server_user_id: UUID
  conflict_type: "edit_edit" | "delete_edit"
  detected_at: DateTime
  resolved_at: DateTime (nullable)
  resolved_by: UUID (nullable)
  resolution: "kept_local" | "kept_server" (nullable)
```

### Resolution UI

On app load, if unresolved conflicts exist, show resolution screen:

**Edit vs Edit:**
```
CONFLICT DETECTED

"car rental" was edited by both you and Katrina.

Your version:      £350 (Dec 18, 10:00)
Katrina's version: £280 (Dec 18, 09:45)

[KEEP MINE]  [KEEP THEIRS]
```

**Delete vs Edit:**
```
CONFLICT DETECTED

"car rental" was deleted by Edward, but edited by Katrina.

Katrina's version: £280 (Dec 18, 09:45)

[KEEP DELETED]  [RESTORE WITH EDIT]
```

### Resolution Process

1. User selects which version to keep
2. System updates the event (or confirms deletion)
3. Conflict marked as resolved
4. Snapshots invalidated if needed
5. Continue to next conflict (if any)

### Required Fields on Events

To support conflict detection, events track:

| Field | Type | Description |
|-------|------|-------------|
| updated_at | DateTime | When last modified |
| updated_by | UUID | User who last modified |

### Why Not Prevent Conflicts?

- **Optimistic locking** requires real-time connection
- **Admin approval** creates bottlenecks
- **Screen locking** doesn't work offline

For a household app with 2-3 users, conflicts are rare. When they happen, a simple "pick one" resolution is sufficient. Reconciliation serves as a safety net for any data inconsistencies.

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| v1 | Dec 2024 | Initial spec - stories with starting balances |
| v2 | Dec 2024 | Revised model - stories as layers, projection-centric, funding modes |
| v2.1 | Dec 2024 | Added multi-currency model with base currency conversion and rate locking |
| v2.2 | Dec 2024 | Added: recurring event generation, story lifecycle, hypothetical funding transition, event editing rules, gap indicator currency. Resolved story assignment and overlap questions. Added discussion topics. |
| v2.3 | Dec 2024 | Added: account-level projection, per-account warnings, story default accounts, reconciliation system with auto-adjustments, smart cleanup, account archiving. Resolved reconciliation discussion. |
| v2.4 | Dec 2024 | Added: deferred/batched reconciliation triggers, pending_reconciliation flag, account detail screen with per-account projections and activity. |
| v2.5 | Dec 2024 | Added: pseudo event sourcing architecture, snapshots for historical queries, same-day ordering (income first), account_id required on events (resolved at creation), recurring event generation rules. Resolved balance calculation architecture. |
| v2.6 | Dec 2024 | Added: multi-user conflict resolution (detect and resolve), conflict data structure, resolution UI patterns, created_by/updated_by tracking. Resolved all discussion topics. |
| v2.7 | Dec 2024 | Updated stack: Alpine.js frontend, Dexie.js for IndexedDB, Workbox for service worker. Added architecture diagram, project structure, offline data flow, client-side calculation logic, initial load and sync strategy. |
| v2.8 | Dec 2024 | Added: detailed sync protocol (push/pull phases), sync queue structure, change_log collection for tracking deletes, hard delete everywhere approach, change_log pruning (31 days), stale client handling with full_sync_required flag. |

---

*Document created: December 2024*
*Status: Design complete - ready for implementation*
