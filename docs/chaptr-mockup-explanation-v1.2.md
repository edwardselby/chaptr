# CHAPTR Mockup Explanation

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
