# CHAPTR - Personal Finance Projection System
## Complete Technical Specification

**Version:** 3.0
**Last Updated:** January 2025

> This document combines the core specification with sync implementation details and progressive enhancement architecture.

---


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

**Before story starts:**
- Funding event is marked as `[planned]`
- Displayed with amber colouring
- Does NOT appear in ALL view
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

```
if story.funding_mode == 'projected':
    starting_balance = calculate projected balance on story.start_date
else if story.funding_mode == 'fixed':
    starting_balance = story.funding_amount
else if story.funding_mode == 'projected_plus':
    starting_balance = projected balance + story.funding_amount

for each date in story range:
    for each event on this date (baseline + this story):
        display event if (baseline OR this story)
        running_balance += ALL events (including hidden stories)
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

## Authentication & User Management

CHAPTR uses **JWT (JSON Web Token) authentication** for secure, self-contained user authentication.

### Philosophy

- **Self-contained** - No external auth services required
- **Simple** - Username/password authentication for home use
- **Stateless** - JWT tokens validated locally without session storage
- **Future-ready** - Architected to support OAuth (Google) upgrade later

### User Model

Users are identified and tracked throughout the system for conflict resolution and audit trails.

| Field | Type | Description |
|-------|------|-------------|
| id | UUID | Unique user identifier |
| username | String | Display name ("Edward", "Katrina") - used in conflict UI |
| password_hash | String | Bcrypt-hashed password (never stored in plain text) |
| role | Enum | "admin" or "user" |
| created_at | DateTime | When user account was created |
| updated_at | DateTime | When user account was last modified |

**Password Security:**
- Passwords hashed with bcrypt algorithm
- Minimum 8 characters (reasonable for home use)
- Salt automatically included by bcrypt
- Never stored or logged in plain text

### Authentication Endpoints

#### POST /api/auth/login

User authentication and token issuance.

**Request:**
```json
{
    "username": "Edward",
    "password": "password123"
}
```

**Success Response (200):**
```json
{
    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "token_type": "bearer",
    "user": {
        "id": "uuid-123",
        "username": "Edward",
        "role": "admin"
    }
}
```

**Error Response (401):**
```json
{
    "detail": "Invalid credentials"
}
```

#### GET /api/auth/me

Retrieve current authenticated user information.

**Request Header:**
```
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

**Success Response (200):**
```json
{
    "id": "uuid-123",
    "username": "Edward",
    "role": "admin"
}
```

**Error Response (401):**
```json
{
    "detail": "Invalid token"
}
```

#### POST /api/auth/logout (Optional)

Client-side logout - server doesn't track sessions, so client simply discards token.

**Implementation:** Frontend clears token from localStorage.

### JWT Token Structure

**Token Payload:**
```json
{
    "sub": "uuid-123",          // User ID (subject)
    "username": "Edward",        // Display name
    "role": "admin",            // User role
    "exp": 1735689600           // Expiration timestamp
}
```

**Token Configuration:**
- **Algorithm:** HS256 (HMAC with SHA-256)
- **Secret Key:** Stored in `.env` file (generated with `openssl rand -hex 32`)
- **Expiration:** 24 hours (configurable via `ACCESS_TOKEN_EXPIRE_MINUTES`)
- **Signature:** Server validates token signature on each request

### Authorization Mechanism

**Endpoint Protection:**

Every protected endpoint uses a `get_current_user` dependency to extract and validate the JWT token:

```python
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer

security = HTTPBearer()

async def get_current_user(token: str = Depends(security)):
    """Extract and validate JWT token, return user info."""
    try:
        payload = jwt.decode(token.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        return {
            "id": payload.get("sub"),
            "username": payload.get("username"),
            "role": payload.get("role")
        }
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

# Usage in protected endpoints
@router.get("/accounts")
async def get_accounts(current_user: dict = Depends(get_current_user)):
    # current_user automatically injected with user info from token
    accounts = await db.accounts.find({}).to_list()
    return accounts
```

**Admin-Only Endpoints:**

Settings and user management endpoints require admin role:

```python
@router.put("/settings")
async def update_settings(
    settings: SettingsUpdate,
    current_user: dict = Depends(get_current_user)
):
    if current_user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    # ... update settings ...
```

### Client-Side Authentication Flow

**Login:**
```javascript
// 1. User submits login form
const response = await fetch('/api/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username: 'Edward', password: 'password123' })
});

const data = await response.json();
// { access_token: "eyJhbGc...", token_type: "bearer", user: {...} }

// 2. Store token in localStorage
localStorage.setItem('auth_token', data.access_token);
localStorage.setItem('current_user', JSON.stringify(data.user));
```

**Authenticated Requests:**
```javascript
// Include token in Authorization header for all API requests
const token = localStorage.getItem('auth_token');

const response = await fetch('/api/accounts', {
    headers: {
        'Authorization': `Bearer ${token}`
    }
});
```

**Logout:**
```javascript
// Clear token from localStorage
localStorage.removeItem('auth_token');
localStorage.removeItem('current_user');
```

### User Tracking

The authenticated user's ID is automatically used to populate audit fields:

**Event Creation:**
```python
@router.post("/events")
async def create_event(
    event: EventCreate,
    current_user: dict = Depends(get_current_user)
):
    event_data = event.model_dump()
    event_data["created_by"] = current_user["id"]  # Auto-populated
    event_data["updated_by"] = current_user["id"]

    await db.events.insert_one(event_data)
```

**Event Update:**
```python
@router.put("/events/{event_id}")
async def update_event(
    event_id: UUID,
    event: EventUpdate,
    current_user: dict = Depends(get_current_user)
):
    update_data = event.model_dump(exclude_unset=True)
    update_data["updated_by"] = current_user["id"]  # Auto-populated
    update_data["updated_at"] = datetime.now(timezone.utc)

    await db.events.update_one({"id": str(event_id)}, {"$set": update_data})
```

### First User Setup

**Bootstrap Problem:** How is the first admin user created?

**Solution:** Admin setup script run once during initial deployment:

```bash
# Run setup script to create first admin user
python scripts/create_first_user.py --username Edward --password <secure-password>
```

**Script behavior:**
1. Check if any users exist in database
2. If none exist, create admin user with provided credentials
3. If users exist, exit with error (prevents accidental admin creation)

### Security Considerations

**For Home Server (2-3 users via VPN):**

1. **HTTPS Required:**
   - JWT tokens sent in Authorization headers
   - HTTPS prevents token interception
   - SSL pre-configured on home server ✅

2. **Secret Key Management:**
   - Generated once: `openssl rand -hex 32`
   - Stored in `.env` file (not committed to git)
   - Backed up securely
   - 32-byte (256-bit) key for HS256 algorithm

3. **Token Expiration:**
   - 24-hour expiration (configurable)
   - Balance: convenience (longer) vs security (shorter)
   - Home use: 24h reasonable, less frequent re-auth needed

4. **Password Storage:**
   - Bcrypt hashing (industry standard)
   - Automatic salt generation
   - Configurable work factor (default: 12 rounds)
   - No plain-text passwords ever stored or logged

5. **Token Validation:**
   - Every request validates token signature
   - Expired tokens rejected automatically
   - Invalid signatures rejected (tampering detected)

### Future OAuth Upgrade Path

**Architecture supports future Google OAuth integration:**

**Provider Abstraction:**
```python
class AuthProvider:
    async def authenticate(self, credentials) -> User
    async def create_token(self, user: User) -> str

class LocalAuthProvider(AuthProvider):
    """Username/password auth (current)"""
    # Existing implementation

class GoogleAuthProvider(AuthProvider):
    """Google OAuth (future)"""
    async def authenticate(self, credentials):
        # Verify Google OAuth token
        google_user = await verify_google_token(credentials.oauth_token)
        # Find or create user in local database
        user = await get_or_create_user(google_user)
        return user

    async def create_token(self, user: User) -> str:
        # Still use JWT for API (same format!)
        return create_access_token(user.id, user.username, user.role)
```

**Key Points:**
- API still uses JWT tokens internally (OAuth only for initial authentication)
- User model remains unchanged (OAuth ID stored separately)
- Client flow stays the same (still receives JWT token)
- Can support both methods simultaneously (local + OAuth)
- Gradual migration possible (per-user basis)

### Dependencies

**Python Packages (already in requirements.txt):**
```python
python-jose[cryptography]>=3.3.0  # JWT creation & validation
passlib[bcrypt]>=1.7.4             # Password hashing
python-multipart>=0.0.6            # Form data handling
```

**Environment Variables (.env):**
```bash
SECRET_KEY=<generated-with-openssl-rand-hex-32>
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=1440  # 24 hours
```

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
| v2.9 | Dec 2024 | Clarified funding event architecture: funding events are the single source of truth for funding amounts. Starting balance does NOT include funding_amount; instead a hypothetical funding event is created. Fixed contradiction between "Hypothetical Funding Lifecycle" and "Filtered Calculation" sections. Updated examples to show correct calculation flow. |
| v3.0 | Dec 2024 | Added: Authentication & User Management with JWT-based authentication. User model schema (id, username, password_hash, role), authentication endpoints (POST /api/auth/login, GET /api/auth/me), authorization mechanism with get_current_user dependency, client-side auth flow, user tracking for created_by/updated_by fields, first user setup script, security considerations (bcrypt, HTTPS, token expiration), and future OAuth upgrade path with provider abstraction. Resolved all authentication gaps identified in specification. |

---

*Document created: December 2024*
*Status: Design complete - ready for implementation*

---
---

# PART II: Sync Implementation & Progressive Enhancement

> The following sections provide detailed implementation guidance for the sync protocol, change logging, conflict resolution, and progressive enhancement architecture.

---


---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Change Logging](#change-logging)
3. [Sync Endpoint](#sync-endpoint)
4. [Change Log Maintenance](#change-log-maintenance)
5. [Full Sync Handling](#full-sync-handling)
6. [Repository Changes Summary](#repository-changes-summary)
7. [Frontend Progressive Enhancement](#frontend-progressive-enhancement)
8. [Storage Adapter Implementation](#storage-adapter-implementation)
9. [Mode Detection & Initialization](#mode-detection--initialization)
10. [Error Handling](#error-handling)
11. [Queue Management](#queue-management)
12. [Testing & Development](#testing--development)
13. [UI Components](#ui-components)

---

## Architecture Overview

The sync endpoint acts as a **dispatcher** to existing repository methods, adding conflict detection and change logging.

```
┌─────────────────────────────────────────────────────────────────┐
│  POST /api/sync                                                 │
│                                                                 │
│  ┌─────────────────┐       ┌─────────────────────────────────┐ │
│  │  Push Phase     │──────▶│  Existing Repository Layer      │ │
│  │                 │       │                                 │ │
│  │  for change in  │       │  EventRepository.create()       │ │
│  │    changes:     │       │  EventRepository.update()       │ │
│  │                 │       │  EventRepository.delete()       │ │
│  │  - detect       │       │  StoryRepository.create()       │ │
│  │    conflicts    │       │  AccountRepository.update()     │ │
│  │  - dispatch to  │       │  ...                            │ │
│  │    repository   │       │                                 │ │
│  └─────────────────┘       └─────────────────────────────────┘ │
│           │                              │                      │
│           │                              ▼                      │
│           │                ┌─────────────────────────────────┐ │
│           │                │  Change Log (automatic)         │ │
│           │                │                                 │ │
│           │                │  Repositories log all mutations │ │
│           │                │  via ChangeLogMixin             │ │
│           │                └─────────────────────────────────┘ │
│           │                              │                      │
│           ▼                              ▼                      │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Pull Phase                                             │   │
│  │                                                         │   │
│  │  Query change_log for entries since last_sync_at        │   │
│  │  Exclude changes made by requesting client              │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### Key Design Decisions

- **Sequential Processing:** Server processes changes in the order received (not parallel)
- **No Client-Side Compaction:** All queued changes sent to server; server handles deduplication
- **Audit Trail Preserved:** Each change creates a separate change_log entry
- **Changes Applied in Order:** Clients apply pulled changes sequentially (create → update → delete)

---

## Change Logging

### Logged Entity Types

All mutable entities must log changes:

| Entity Type | Repository | Actions Logged |
|-------------|------------|----------------|
| `event` | EventRepository | create, update, delete |
| `story` | StoryRepository | create, update, delete |
| `account` | AccountRepository | create, update, delete |
| `recurring_rule` | RecurringRuleRepository | create, update, delete |
| `settings` | SettingsRepository | update |

**Not logged:**
- `change_log` (meta, would be recursive)
- `snapshots` (server-side optimisation, not synced to clients)
- `conflicts` (client-local, resolved per-device)
- `users` (admin-only, loaded on-demand)

### Change Log Schema

```python
# MongoDB collection: change_log
{
    "id": "uuid",
    "entity_type": "event",           # event | story | account | recurring_rule | settings
    "entity_id": "uuid",              # ID of the affected entity
    "action": "create",               # create | update | delete
    "data": { ... },                  # Full entity snapshot (see below)
    "changed_by_user": "uuid",        # User who made the change
    "changed_by_client": "uuid",      # Device/client that made the change
    "changed_at": "2024-12-18T10:00:00Z"
}
```

### Snapshot Strategy

**For create and update:**
- Store the **full entity state after mutation**
- This allows clients to apply the change without needing the previous state
- Includes all fields, not just changed ones

**For delete:**
- Store the **full entity state before deletion**
- Enables conflict resolution (user can see what was deleted)
- `data` is the complete entity that was removed

```python
# Example: delete snapshot
{
    "entity_type": "event",
    "entity_id": "abc-123",
    "action": "delete",
    "data": {
        "id": "abc-123",
        "event_date": "2024-12-20",
        "description": "Car rental",
        "amount": "-320",
        # ... full entity as it was before deletion
    },
    "changed_by_user": "user-456",
    "changed_by_client": "device-789",
    "changed_at": "2024-12-18T10:30:00Z"
}
```

### ChangeLogMixin Implementation

Add to `BaseRepository` or as a mixin:

```python
class ChangeLogMixin:
    """
    Mixin providing change logging for sync support.
    
    All repository mutations should call log_change() after
    successfully completing the database operation.
    """
    
    async def log_change(
        self,
        entity_type: str,
        entity_id: UUID,
        action: str,
        data: Optional[dict],
        user_id: Optional[UUID] = None,
        client_id: Optional[str] = None
    ) -> None:
        """
        Record a change for sync distribution.
        
        :param entity_type: Type of entity (event, story, account, etc.)
        :param entity_id: UUID of the affected entity
        :param action: One of: create, update, delete
        :param data: Full entity snapshot (after mutation, or before deletion)
        :param user_id: User who made the change (from JWT)
        :param client_id: Client device ID (from sync request)
        """
        await self.db["change_log"].insert_one({
            "id": str(generate_id()),
            "entity_type": entity_type,
            "entity_id": str(entity_id),
            "action": action,
            "data": data,
            "changed_by_user": str(user_id) if user_id else None,
            "changed_by_client": client_id,
            "changed_at": utc_now().isoformat()
        })
```

### Repository Integration

Each repository method that mutates data must log the change. Add `client_id` parameter to mutation methods:

```python
class EventRepository(BaseRepository[Event], ChangeLogMixin):
    
    async def create(
        self,
        data: EventCreate,
        story_id: Optional[UUID] = None,
        current_user: Optional[dict] = None,
        client_id: Optional[str] = None          # NEW: for change logging
    ) -> Event:
        # ... existing creation logic ...
        
        await self.collection.insert_one(event.model_dump(mode="json"))
        
        # Log change for sync
        await self.log_change(
            entity_type="event",
            entity_id=event.id,
            action="create",
            data=event.model_dump(mode="json"),
            user_id=user_id,
            client_id=client_id
        )
        
        return event
    
    async def update(
        self,
        event_id: UUID,
        data: EventUpdate,
        current_user: Optional[dict] = None,
        client_id: Optional[str] = None          # NEW
    ) -> Event:
        # ... existing update logic ...
        
        updated_event = await self.get(event_id)
        
        # Log change for sync
        await self.log_change(
            entity_type="event",
            entity_id=event_id,
            action="update",
            data=updated_event.model_dump(mode="json"),
            user_id=UUID(current_user["id"]) if current_user else None,
            client_id=client_id
        )
        
        return updated_event
    
    async def delete(
        self,
        event_id: UUID,
        current_user: Optional[dict] = None,     # NEW: needed for logging
        client_id: Optional[str] = None          # NEW
    ) -> bool:
        # Get entity BEFORE deletion for snapshot
        event = await self.get(event_id)
        
        # ... existing delete logic (validation, etc.) ...
        
        await self.collection.delete_one({"id": to_str(event_id)})
        
        # Log change for sync (with pre-deletion snapshot)
        await self.log_change(
            entity_type="event",
            entity_id=event_id,
            action="delete",
            data=event.model_dump(mode="json"),
            user_id=UUID(current_user["id"]) if current_user else None,
            client_id=client_id
        )
        
        return True
```

### REST Endpoint Compatibility

Existing REST endpoints continue to work. When called directly (not via sync), pass `client_id=None`:

```python
@router.post("/events")
async def create_event(
    data: EventCreate,
    current_user: dict = Depends(get_current_user)
):
    repo = EventRepository(db)
    return await repo.create(
        data,
        current_user=current_user,
        client_id=None  # Direct API call, not from sync
    )
```

Changes made via REST endpoints will still be logged and distributed to other clients on their next sync.

---

## Sync Endpoint

### Request Schema

```python
class SyncChange(BaseModel):
    entity_type: str                    # event | story | account | recurring_rule | settings
    entity_id: UUID
    action: str                         # create | update | delete
    data: Optional[dict] = None         # Entity data (null for delete)
    base_updated_at: Optional[datetime] = None  # For conflict detection

class SyncRequest(BaseModel):
    client_id: str                      # Unique device identifier
    last_sync_at: Optional[datetime]    # Last successful sync timestamp
    changes: list[SyncChange]           # Local changes to push
```

### Response Schema

```python
class SyncConflict(BaseModel):
    entity_type: str
    entity_id: UUID
    conflict_type: str                  # edit_edit | delete_edit | edit_delete | business_rule
    client_version: dict                # What client tried to save
    server_version: dict                # Current server state

class SyncServerChange(BaseModel):
    entity_type: str
    entity_id: UUID
    action: str
    data: Optional[dict]                # Entity data (null for delete)

class SyncResponse(BaseModel):
    applied: list[UUID]                 # Successfully applied change IDs
    conflicts: list[SyncConflict]       # Conflicts requiring resolution
    server_changes: list[SyncServerChange]  # Changes from other clients
    sync_timestamp: datetime            # Use as last_sync_at for next sync
    full_sync_required: bool = False    # Client too stale, must re-download all
```

### Endpoint Implementation

```python
@router.post("/sync", response_model=SyncResponse)
async def sync(
    request: SyncRequest,
    current_user: dict = Depends(get_current_user),
    db = Depends(get_database)
):
    """
    Bidirectional sync endpoint.
    
    Push phase: Apply client changes, detect conflicts
    Pull phase: Return changes from other clients since last_sync_at
    
    Changes are processed SEQUENTIALLY in the order received.
    """
    # Initialize repositories
    repos = {
        "event": EventRepository(db),
        "story": StoryRepository(db),
        "account": AccountRepository(db),
        "recurring_rule": RecurringRuleRepository(db),
        "settings": SettingsRepository(db),
    }
    
    applied = []
    conflicts = []
    
    # ─────────────────────────────────────────────
    # PUSH PHASE: Process client changes (sequential)
    # ─────────────────────────────────────────────
    
    for change in request.changes:
        repo = repos.get(change.entity_type)
        if not repo:
            continue  # Unknown entity type, skip
        
        try:
            if change.action == "create":
                await handle_create(repo, change, current_user, request.client_id)
                
            elif change.action == "update":
                conflict = await handle_update(repo, change, current_user, request.client_id)
                if conflict:
                    conflicts.append(conflict)
                    continue
                    
            elif change.action == "delete":
                conflict = await handle_delete(repo, change, current_user, request.client_id)
                if conflict:
                    conflicts.append(conflict)
                    continue
            
            applied.append(change.entity_id)
            
        except ResourceNotFoundError:
            # Entity doesn't exist - might have been deleted by another client
            # Not a conflict, just skip
            pass
        except ResourceConflictError as e:
            # Business rule violation (e.g., editing auto-adjustment)
            # Return as a conflict so client knows it failed
            conflicts.append(SyncConflict(
                entity_type=change.entity_type,
                entity_id=change.entity_id,
                conflict_type="business_rule",
                client_version=change.data,
                server_version={"error": str(e)}
            ))
    
    # ─────────────────────────────────────────────
    # PULL PHASE: Get changes from other clients
    # ─────────────────────────────────────────────
    
    server_changes = []
    full_sync_required = False
    
    if request.last_sync_at:
        # Check if client is too stale
        oldest_log = await db["change_log"].find_one(
            sort=[("changed_at", 1)]
        )
        
        if oldest_log and request.last_sync_at < oldest_log["changed_at"]:
            # Client missed changes that have been pruned
            full_sync_required = True
        else:
            # Get changes since last sync, excluding this client's changes
            cursor = db["change_log"].find({
                "changed_at": {"$gt": request.last_sync_at.isoformat()},
                "changed_by_client": {"$ne": request.client_id}
            }).sort("changed_at", 1)
            
            async for log_entry in cursor:
                server_changes.append(SyncServerChange(
                    entity_type=log_entry["entity_type"],
                    entity_id=UUID(log_entry["entity_id"]),
                    action=log_entry["action"],
                    data=log_entry["data"]
                ))
    
    return SyncResponse(
        applied=applied,
        conflicts=conflicts,
        server_changes=server_changes,
        sync_timestamp=utc_now(),
        full_sync_required=full_sync_required
    )
```

### Conflict Detection Helpers

```python
async def handle_create(repo, change, current_user, client_id):
    """Handle create action - dispatch to repository."""
    create_model = get_create_model(change.entity_type)
    await repo.create(
        create_model(**change.data),
        current_user=current_user,
        client_id=client_id
    )

async def handle_update(repo, change, current_user, client_id) -> Optional[SyncConflict]:
    """
    Handle update action with conflict detection.
    
    Returns SyncConflict if server version changed since client's base.
    """
    existing = await repo.get(change.entity_id)
    
    # Conflict detection: compare timestamps
    if change.base_updated_at and existing.updated_at != change.base_updated_at:
        return SyncConflict(
            entity_type=change.entity_type,
            entity_id=change.entity_id,
            conflict_type="edit_edit",
            client_version=change.data,
            server_version=existing.model_dump(mode="json")
        )
    
    # No conflict - apply update
    update_model = get_update_model(change.entity_type)
    await repo.update(
        change.entity_id,
        update_model(**change.data),
        current_user=current_user,
        client_id=client_id
    )
    
    return None

async def handle_delete(repo, change, current_user, client_id) -> Optional[SyncConflict]:
    """
    Handle delete action with conflict detection.
    
    Returns SyncConflict if entity was modified since client's base.
    """
    existing = await repo.get(change.entity_id)
    
    # Conflict: entity was edited after client decided to delete
    if change.base_updated_at and existing.updated_at != change.base_updated_at:
        return SyncConflict(
            entity_type=change.entity_type,
            entity_id=change.entity_id,
            conflict_type="delete_edit",
            client_version=None,  # Client wanted to delete
            server_version=existing.model_dump(mode="json")
        )
    
    # No conflict - apply delete
    await repo.delete(
        change.entity_id,
        current_user=current_user,
        client_id=client_id
    )
    
    return None
```

---

## Change Log Maintenance

### Pruning Job

Run daily to prevent unbounded growth:

```python
async def prune_change_log(db, retention_days: int = 31):
    """
    Remove change log entries older than retention period.
    
    Default 31 days matches spec requirement.
    """
    cutoff = datetime.utcnow() - timedelta(days=retention_days)
    
    result = await db["change_log"].delete_many({
        "changed_at": {"$lt": cutoff.isoformat()}
    })
    
    return result.deleted_count
```

### Index Requirements

```python
# Ensure these indexes exist for sync performance
await db["change_log"].create_index("changed_at")
await db["change_log"].create_index("changed_by_client")
await db["change_log"].create_index([
    ("changed_at", 1),
    ("changed_by_client", 1)
])
```

---

## Full Sync Handling

When `full_sync_required: true` is returned, the client must:

1. Clear all local data (IndexedDB)
2. Request full dataset from server
3. Rebuild local database

### Full Sync Endpoint

```python
@router.get("/sync/full")
async def full_sync(
    current_user: dict = Depends(get_current_user),
    db = Depends(get_database)
):
    """
    Return complete dataset for client rebuild.
    
    Used when:
    - Client is too stale (missed pruned changes)
    - Mode 1 & 2 initial bootstrap (first visit or empty local storage)
    """
    return {
        "accounts": await AccountRepository(db).list(),
        "stories": await StoryRepository(db).list(),
        "events": await EventRepository(db).list(),
        "recurring_rules": await RecurringRuleRepository(db).list(),
        "settings": await SettingsRepository(db).get_all(),
        "sync_timestamp": utc_now()
    }
```

**Note:** Users collection is NOT included - admin-only data loaded on-demand.

---

## Repository Changes Summary

| Repository | Method | Changes Required |
|------------|--------|------------------|
| All | - | Add `ChangeLogMixin` |
| All | `create()` | Add `client_id` param, call `log_change()` |
| All | `update()` | Add `client_id` param, call `log_change()` |
| All | `delete()` | Add `current_user` + `client_id` params, snapshot before delete, call `log_change()` |

---

## Frontend Progressive Enhancement

### Overview

CHAPTR serves a single URL that adapts to browser capabilities, gracefully degrading from full PWA experience to basic web app functionality.

**Key Principle:** Same codebase supports desktop browsers, mobile browsers, PWA installations, and limited environments (private browsing, no SSL, etc.)

### Three-Tier Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  CHAPTR Web App (Single URL)                                │
│                                                             │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  Feature Detection → Storage Adapter                   │ │
│  │                                                        │ │
│  │  ┌─ Mode 1: Full (Dexie + Sync + Offline)      ⭐⭐⭐  │ │
│  │  ├─ Mode 2: Sync-Only (Sync without Dexie)      ⭐⭐   │ │
│  │  └─ Mode 3: Basic (CRUD REST endpoints)         ⭐     │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                             │
│  Backend API:                                               │
│  ├─ POST /api/sync (Modes 1 & 2)                           │
│  ├─ GET /api/sync/full (Modes 1 & 2 bootstrap)             │
│  └─ REST CRUD endpoints (Mode 3 + fallback)                │
└─────────────────────────────────────────────────────────────┘
```

### Mode Definitions

#### Mode 1: Full (Offline-First PWA) ⭐⭐⭐

**Requirements:**
- HTTPS connection
- Modern browser with IndexedDB support
- Dexie.js initialization successful

**Features:**
- ✅ Offline-first - Works without network connection
- ✅ Optimistic updates - Immediate UI response
- ✅ Sync queue - Changes queued when offline
- ✅ Conflict resolution - Full edit-edit/delete-edit detection
- ✅ Background sync - Periodic sync in background

**Data Flow:**
```
User Action → Write to Dexie (immediate) → Update UI (optimistic)
                     ↓
              Queue for sync
                     ↓
              POST /api/sync (when online)
                     ↓
              Apply server changes + handle conflicts
```

#### Mode 2: Sync-Only (No Offline Support) ⭐⭐

**Requirements:**
- Network connection (online-only)
- Sync endpoint available

**When Used:**
- Safari/Firefox private browsing (IndexedDB blocked)
- Dexie initialization failure
- Browser storage quota exceeded

**Features:**
- ✅ Sync protocol - Uses POST /api/sync
- ✅ Conflict detection - Edit-edit conflict handling
- ❌ No offline - Requires network
- ❌ No optimistic updates - UI blocks during save
- ❌ No queue - Changes sent immediately

**Data Flow:**
```
User Action → Show loading → POST /api/sync → Update UI
```

**State Management:**
- Data stored in memory only (Alpine.js reactive state)
- On page load: `GET /api/sync/full` to populate state
- On refresh: Same as first load (fetch from server)
- No sessionStorage - keeps implementation simple

#### Mode 3: Basic (CRUD REST Endpoints) ⭐

**Requirements:**
- Network connection (online-only)
- REST endpoints available

**When Used:**
- HTTP (no SSL) - IndexedDB requires HTTPS
- Very old browsers
- Sync endpoint unavailable
- Emergency fallback mode

**Features:**
- ✅ Direct REST calls - Standard CRUD
- ✅ Broadest compatibility
- ❌ No offline
- ❌ No conflict detection - Last write wins
- ❌ No optimistic updates

**Data Flow:**
```
User Action → Show loading → POST /api/accounts → Update UI
```

**Bootstrap Endpoints (5 sequential calls):**
- `GET /api/accounts`
- `GET /api/stories`
- `GET /api/events`
- `GET /api/recurring-rules`
- `GET /api/settings`

### Feature Availability Matrix

| Feature | Mode 1 (Full) | Mode 2 (Sync) | Mode 3 (Basic) |
|---------|---------------|---------------|----------------|
| Create/Edit/Delete | ✅ | ✅ | ✅ |
| Offline access | ✅ | ❌ | ❌ |
| Optimistic updates | ✅ | ❌ | ❌ |
| Conflict resolution | ✅ | ✅ | ❌ |
| Sync queue | ✅ | ❌ | ❌ |
| Service Worker caching | ✅ | ✅ | ✅ |

### Browser Compatibility

| Environment | Expected Mode | Notes |
|-------------|---------------|-------|
| Chrome/Safari/Firefox (HTTPS) | Full | Best experience |
| Mobile browsers (HTTPS) | Full | Native-like PWA |
| Private browsing | Basic | IndexedDB blocked |
| HTTP (no SSL) | Basic | IndexedDB requires HTTPS |
| IE11 / Old browsers | Basic | No IndexedDB/SW |

---

## Storage Adapter Implementation

### File: `/static/js/storage-adapter.js`

```javascript
import { db } from './db.js';
import { apiRequest, getClientId, generateUUID } from './utils.js';

/**
 * Storage adapter with progressive enhancement.
 * 
 * Automatically detects capabilities and routes to appropriate
 * storage mode (Full, Sync-Only, or Basic).
 */
export class StorageAdapter {
    constructor() {
        this.mode = null;
        this.isReady = false;
        this.lastSyncAt = null;
        this.isSyncing = false;
        
        // In-memory state for Mode 2/3
        this.accounts = [];
        this.stories = [];
        this.events = [];
        this.recurringRules = [];
        this.settings = {};
    }

    /**
     * Initialize storage adapter and detect mode.
     * Must complete in <500ms.
     * 
     * @returns {Promise<string>} Storage mode: 'full' | 'sync-only' | 'basic'
     */
    async init() {
        // Check for forced mode (query param > localStorage > auto)
        const forcedMode = this.getForcedMode();
        if (forcedMode) {
            this.mode = forcedMode;
            console.log(`[CHAPTR] Forced mode: ${this.mode}`);
        } else {
            // Auto-detect mode
            this.mode = await this.detectMode();
        }
        
        // Log mode and capabilities
        console.log('[CHAPTR] Initialized in mode:', this.mode);
        console.log('[CHAPTR] Capabilities:', {
            offline: this.mode === 'full',
            sync: this.mode !== 'basic',
            storage: this.mode === 'full' ? 'IndexedDB' : 'Memory'
        });
        
        this.isReady = true;
        return this.mode;
    }
    
    /**
     * Check for forced mode via query param or localStorage.
     * Priority: query param > localStorage > null (auto-detect)
     */
    getForcedMode() {
        // Query param takes priority
        const urlParams = new URLSearchParams(window.location.search);
        const queryMode = urlParams.get('mode');
        if (['full', 'sync-only', 'basic'].includes(queryMode)) {
            return queryMode;
        }
        
        // Then localStorage
        const storedMode = localStorage.getItem('FORCE_MODE');
        if (['full', 'sync-only', 'basic'].includes(storedMode)) {
            return storedMode;
        }
        
        return null;
    }
    
    /**
     * Auto-detect best available mode.
     */
    async detectMode() {
        // Try Mode 1 (Full) first
        try {
            await db.open();
            return 'full';
        } catch (dexieError) {
            console.warn('[CHAPTR] Dexie unavailable:', dexieError.message);
        }
        
        // Try Mode 2 (Sync-Only)
        if (navigator.onLine) {
            try {
                await this.testSyncEndpoint();
                return 'sync-only';
            } catch (syncError) {
                console.warn('[CHAPTR] Sync endpoint unavailable:', syncError.message);
            }
        }
        
        // Fall back to Mode 3 (Basic)
        console.warn('[CHAPTR] Falling back to Basic mode');
        return 'basic';
    }
    
    /**
     * Test if sync endpoint is available.
     * Times out after 500ms.
     */
    async testSyncEndpoint() {
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 500);
        
        try {
            const response = await apiRequest('/api/sync', {
                method: 'POST',
                body: JSON.stringify({
                    client_id: await getClientId(),
                    last_sync_at: null,
                    changes: []
                }),
                signal: controller.signal
            });
            
            if (!response.ok) {
                throw new Error(`Sync endpoint returned ${response.status}`);
            }
        } finally {
            clearTimeout(timeout);
        }
    }
    
    /**
     * Load initial data (bootstrap).
     * Called after init() to populate state.
     */
    async bootstrap() {
        switch (this.mode) {
            case 'full':
                return await this.bootstrap_Full();
            case 'sync-only':
                return await this.bootstrap_SyncOnly();
            case 'basic':
                return await this.bootstrap_Basic();
        }
    }
    
    async bootstrap_Full() {
        // Check if Dexie has data
        const accountCount = await db.accounts.count();
        
        if (accountCount === 0) {
            // First visit - fetch from server
            const data = await this.fetchFullSync();
            await this.populateDexie(data);
        }
        
        // Load from Dexie into memory for UI
        this.accounts = await db.accounts.toArray();
        this.stories = await db.stories.toArray();
        this.events = await db.events.toArray();
        this.recurringRules = await db.recurring_rules.toArray();
        // Settings loaded separately
    }
    
    async bootstrap_SyncOnly() {
        // Always fetch from server (no local persistence)
        const data = await this.fetchFullSync();
        this.accounts = data.accounts;
        this.stories = data.stories;
        this.events = data.events;
        this.recurringRules = data.recurring_rules;
        this.settings = data.settings;
        this.lastSyncAt = data.sync_timestamp;
    }
    
    async bootstrap_Basic() {
        // Sequential REST calls
        const [accounts, stories, events, rules, settings] = await Promise.all([
            apiRequest('/api/accounts').then(r => r.json()),
            apiRequest('/api/stories').then(r => r.json()),
            apiRequest('/api/events').then(r => r.json()),
            apiRequest('/api/recurring-rules').then(r => r.json()),
            apiRequest('/api/settings').then(r => r.json())
        ]);
        
        this.accounts = accounts;
        this.stories = stories;
        this.events = events;
        this.recurringRules = rules;
        this.settings = settings;
    }
    
    async fetchFullSync() {
        const response = await apiRequest('/api/sync/full');
        if (!response.ok) {
            throw new Error('Failed to fetch initial data');
        }
        return await response.json();
    }
    
    async populateDexie(data) {
        await db.accounts.bulkPut(data.accounts);
        await db.stories.bulkPut(data.stories);
        await db.events.bulkPut(data.events);
        await db.recurring_rules.bulkPut(data.recurring_rules);
        // Settings stored separately
    }
    
    // ... CRUD methods route to _Full, _SyncOnly, or _Basic variants
}

export const storage = new StorageAdapter();
```

---

## Mode Detection & Initialization

### Timing

- `init()` runs during Alpine component initialization (after mount)
- User sees: "Loading CHAPTR..." spinner with app skeleton visible
- Mode detection must complete in **<500ms**
- If detection times out, fall back to Mode 3 (Basic)

### Mode Locking

- **Mode is locked at initialization** - cannot change mid-session
- If Mode 2 user goes offline: operations fail with error toast
- No "retry upgrade" button - user can refresh page to re-detect
- This keeps implementation simple and predictable

### Service Worker Independence

Service Worker is independent of mode detection:

- **Mode 1 without SW:** Still "Full" mode - Dexie works, data syncs. Only loses static asset caching
- **Mode 2 + SW:** Benefits from HTML/CSS/JS caching
- **Mode 3 + SW:** Same static caching benefit
- **SW is NOT required for any mode** - it's a performance enhancement

SW registration failure is logged but doesn't affect mode:
```javascript
console.warn('[CHAPTR] Service Worker unavailable - static assets won\'t cache');
```

---

## Error Handling

### Unified Strategy

All modes use unified error handling via `showToast()` helper:

```javascript
// Network failure messages by mode
const errorMessages = {
    'full': 'Changes queued for sync',           // Auto-retry on reconnect
    'sync-only': 'Please check connection and try again',
    'basic': 'Operation failed. Refresh and retry'
};
```

### Authentication

- **All modes use same JWT authentication** via `apiRequest()` wrapper
- JWT expiry handling (401 response):
  1. `localStorage.removeItem('jwt_token')`
  2. `window.location.href = '/login'`
- No mode-specific auth logic

### Mode 2/3 Offline Handling

If user goes offline in Mode 2 or 3:
- Operations fail immediately
- Error toast: "Connection required. Please check your internet."
- No queuing - user must retry when online

---

## Queue Management

### Queue Limits (Mode 1 Only)

| Threshold | Behaviour |
|-----------|-----------|
| 0-399 | Normal operation |
| 400 | Warning toast: "⚠ 400+ pending changes. Sync recommended." |
| 500 | **Hard block** - Modal dialog blocks operation |

### Hard Block Behaviour (at 500 changes)

1. Modal dialog appears: "Too many pending changes"
2. Offers "Sync Now" button
3. If user declines: Operation fails, change not applied
4. If sync succeeds: Queue cleared, operation retried automatically

### Queue Processing

- **No client-side compaction** - all changes sent in order
- Example: create → update → delete for same entity = 3 change_log entries
- Server processes sequentially, final state is deleted
- Preserves audit trail

---

## Testing & Development

### Forcing Modes

**Priority:** Query param > localStorage > Auto-detection

```javascript
// Query param (highest priority)
?mode=basic
?mode=sync-only
?mode=full

// localStorage
localStorage.setItem('FORCE_MODE', 'basic');
localStorage.setItem('FORCE_MODE', 'sync-only');
localStorage.setItem('FORCE_MODE', 'full');

// Clear override
localStorage.removeItem('FORCE_MODE');
```

### Simulating Modes in DevTools

- **Mode 2:** Settings → Privacy → Block IndexedDB for site
- **Mode 3:** Serve via `http://localhost` (not `https://`)

### Console Logging

```javascript
// On successful init
console.log('[CHAPTR] Initialized in mode:', this.mode);
console.log('[CHAPTR] Capabilities:', {
    offline: this.mode === 'full',
    sync: this.mode !== 'basic',
    storage: this.mode === 'full' ? 'IndexedDB' : 'Memory'
});

// On forced mode
console.log('[CHAPTR] Forced mode:', this.mode);

// On mode detection failure
console.warn('[CHAPTR] Dexie unavailable:', error.message);
console.warn('[CHAPTR] Sync endpoint unavailable - using Basic mode');

// On Service Worker failure
console.warn('[CHAPTR] Service Worker unavailable - static assets won\'t cache');
```

---

## UI Components

### Mode Indicator (Settings Screen)

Add to Settings screen under "Runtime Information":

**Mode 1 (Full):**
```
Runtime Information
├─ Mode: Full (Offline-capable)
├─ Capabilities: ✓ Offline sync  ✓ Conflict detection
└─ Storage: IndexedDB (Dexie)
```

**Mode 2 (Sync-Only):**
```
Runtime Information
├─ Mode: Sync-Only (Online required)
├─ Capabilities: ✗ Offline sync  ✓ Conflict detection
└─ Storage: Memory (cleared on refresh)
```

**Mode 3 (Basic):**
```
Runtime Information
├─ Mode: Basic (Limited)
├─ Capabilities: ✗ Offline sync  ✗ Conflict detection
└─ Storage: Memory (cleared on refresh)
```

### Mode 3 Warning Banner

Persistent banner at top of app (below header), non-dismissible:

```html
<div class="warning-banner mode-3-warning">
    <span class="warning-icon">⚠</span>
    <span>Limited mode - offline sync unavailable. Use HTTPS for full functionality.</span>
</div>
```

**Styling:**
```css
.mode-3-warning {
    background: rgba(255, 170, 0, 0.1);
    border-bottom: 1px solid var(--amber);
    color: var(--amber);
    padding: 8px 16px;
    font-size: 12px;
    display: flex;
    align-items: center;
    gap: 8px;
}
```

### Pending Changes Indicator

Already implemented - amber badge in header showing count, clickable to trigger sync.

### Queue Limit Modal (500 changes)

```html
<div class="modal queue-limit-modal">
    <div class="modal-content">
        <h3>⚠ Too Many Pending Changes</h3>
        <p>You have 500+ changes waiting to sync. Please sync now to continue.</p>
        <div class="modal-actions">
            <button class="btn-primary" onclick="syncNow()">Sync Now</button>
            <button class="btn-secondary" onclick="closeModal()">Cancel</button>
        </div>
    </div>
</div>
```

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 3.0 | Dec 2024 | Major update: Added frontend progressive enhancement strategy (three-tier mode system), storage adapter pattern, mode detection, queue management, error handling, testing guidance, UI components. Clarified sequential change processing and no client-side compaction. |
| 2.8.1 | Dec 2024 | Sync implementation addendum - repository pattern integration, change logging details, sync endpoint implementation |
