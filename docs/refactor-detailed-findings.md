# CHAPTR Refactor - Detailed Findings & Answers

**Date**: 2025-12-29
**Status**: Ready for Big Bang Rewrite

---

## Question 1: Backend Reconciliation Logic ✅ FOUND

### Location
**File**: `core/reconciliation.py`
**Triggered**: During sync phase (`api/routes/sync.py:296-308`)

### How It Works

```python
# api/routes/sync.py:296-308
# After applying all client changes, trigger reconciliation
from core.reconciliation import trigger_reconciliation

await trigger_reconciliation(
    trigger_reason="sync",
    db=db,
    user_id=user_id,
    client_id=None  # Server-side change
)
```

### Algorithm (`core/reconciliation.py`)

```python
async def trigger_reconciliation(trigger_reason, db, user_id, client_id):
    # 1. Find accounts with pending_reconciliation = True
    pending_accounts = await account_repo.find({"pending_reconciliation": True})

    for account in pending_accounts:
        # 2. Remove old [auto] adjustments for this account
        await remove_old_auto_adjustments(account.id, ...)

        # 3. Calculate drift (actual - projected)
        drift_event = await calculate_auto_adjustment(
            account.id,
            account.current_balance,  # Actual
            db,
            user_id
        )

        if drift_event:
            # 4. Create [auto] adjustment event
            await event_repo.create(drift_event, ...)

        # 5. Clear pending_reconciliation flag
        await account_repo.update(account.id, {
            "pending_reconciliation": False
        })
```

### Key Details

1. **Drift Calculation** (`core/reconciliation.py:85-155`):
   ```python
   # Sum all REAL events for account (excluding hypothetical)
   projected_balance = sum(event.amount for event in account_events)

   # Calculate drift
   drift = actual_balance - projected_balance

   # Only create adjustment if drift > £0.01
   if abs(drift) > 0.01:
       return EventCreate(
           event_date=today,
           description="balance adjustment",  # Lowercase!
           amount=drift,
           currency=account.currency,
           rate_to_base=1.0,
           is_baseline=True,
           is_auto_adjustment=True
       )
   ```

2. **Old Adjustment Removal** (`core/reconciliation.py:158-210`):
   ```python
   # Find all existing [auto] events for this account
   auto_events = await event_repo.find({
       "account_id": account_id,
       "is_auto_adjustment": True
   })

   # Delete each one (bypassing repository business rules)
   for event in auto_events:
       await event_repo.collection.delete_one({"id": event.id})
       await event_repo.log_change("event", event.id, "delete", ...)
   ```

3. **When Set**: `pending_reconciliation = True` flag is set:
   - When user updates `account.current_balance` (api/routes/accounts.py)
   - Triggers reconciliation on next sync/view projection

---

## Question 3: Sync Protocol & Server Authority ✅ ELABORATED

### Your Answer: "C - Server is source of truth, conflict resolution handles the rest"

**You're absolutely right.** Let me show you why the existing conflict resolution is sufficient:

### Concrete Example: Opening Balance Event Creation

**Scenario**: User creates account offline with £1000 balance

#### What Happens Now (Without Queue-as-State):

```javascript
// FRONTEND (app.js:860-890) - User offline
async createAccount() {
    // 1. Create account in Dexie
    const account = await storage.createAccount({
        name: 'Monzo',
        currency: 'GBP',
        current_balance: 1000
    });

    // 2. Frontend creates opening balance event
    const openingEvent = await _createOpeningBalanceEvent(account);
    //    description: "Opening Balance"  ← UPPERCASE 'B'
    //    amount: 1000

    await db.events.add(openingEvent);
    await db.queueChange('event', openingEvent.id, 'create', openingEvent);

    // 3. Queue both for sync
    // Queue now has 2 items:
    //   - account creation
    //   - opening balance event creation
}

// ... user stays offline for a while ...

// SYNC HAPPENS
async manualSync() {
    const response = await POST('/api/sync', {
        changes: [
            {entity_type: 'account', action: 'create', data: {...}},
            {entity_type: 'event', action: 'create', data: {
                description: "Opening Balance",  // FRONTEND version
                amount: 1000,
                ...
            }}
        ]
    });
}

// BACKEND (api/repositories/accounts.py:49-134)
async def create(self, data):
    # 1. Create account
    account = Account(**data)
    await self.collection.insert_one(account.model_dump())

    # 2. Backend ALSO creates opening balance event
    await self._create_opening_balance_event(account, ...)
    #    description: "opening balance"  ← LOWERCASE 'b'
    #    amount: 1000

    return account

# NOW WE HAVE A PROBLEM:
# - Frontend created event with description "Opening Balance"
# - Backend created event with description "opening balance"
# - DUPLICATE EVENTS! Both synced to client!
```

**The Issue**: Frontend and backend both create the opening balance event, leading to:
- ❌ Duplicate events in database
- ❌ Projection shows £2000 instead of £1000
- ❌ User sees broken state

#### What Happens with Queue-as-State (Your Answer #3):

```javascript
// FRONTEND (REFACTORED) - User offline
async createAccount() {
    // 1. Create account in Dexie
    const accountId = generateUUID();
    await db.accounts.add({
        id: accountId,
        name: 'Monzo',
        currency: 'GBP',
        current_balance: 1000,
        _queued_op: 'create'  // ← SINGLE FLAG
    });

    // 2. Queue account creation ONLY
    await db.queueChange('account', accountId, 'create', {...});

    // 3. Frontend creates opening balance event
    const eventId = generateUUID();
    const eventData = {
        description: "Opening Balance",  // UPPERCASE 'B'
        amount: 1000,
        is_opening_balance: true,
        ...
    };

    await db.events.add({...eventData, id: eventId, _queued_op: 'create'});
    await db.queueChange('event', eventId, 'create', eventData, null, {
        dependencies: [accountId],  // Must sync AFTER account
        _derived_from: 'account_creation'  // NEW: Mark as derived operation
    });

    // ✅ User sees correct projection immediately (£1000)
}

// SYNC HAPPENS
async manualSync() {
    const response = await POST('/api/sync', {
        changes: [
            {entity_type: 'account', action: 'create', data: {...}},
            {entity_type: 'event', action: 'create', data: {...},
             _derived_from: 'account_creation'}  // ← Tell server this is derived
        ]
    });
}

// BACKEND (ENHANCED)
async def handle_sync(changes):
    conflicts = []

    for change in changes:
        if change.entity_type == 'account' and change.action == 'create':
            # 1. Create account
            account = await account_repo.create(change.data)

            # 2. Backend creates opening balance event (like always)
            backend_event = await _create_opening_balance_event(account)
            #    id: <server-uuid>
            #    description: "opening balance"  ← lowercase

            # 3. Check if client also sent opening balance event
            client_opening_event = next(
                (c for c in changes if
                 c.entity_type == 'event' and
                 c.get('_derived_from') == 'account_creation' and
                 c.data.get('account_id') == account.id),
                None
            )

            if client_opening_event:
                # CLIENT SENT OPENING BALANCE TOO!
                # Server's version is authoritative

                # Add to conflicts (not an error - expected behavior)
                conflicts.append({
                    "entity_type": "event",
                    "entity_id": client_opening_event.entity_id,
                    "conflict_type": "derived_event_overridden",
                    "client_version": client_opening_event.data,
                    "server_version": backend_event.model_dump(),
                    "resolution": "use_server"
                })

    return {
        "applied": [...],
        "conflicts": conflicts,  # ← EXISTING FIELD!
        "server_changes": [
            {
                "entity_type": "event",
                "action": "create",
                "data": backend_event.model_dump()  # Server's version
            }
        ]
    }

// FRONTEND (processSyncResponse)
async processSyncResponse(syncData) {
    // Handle conflicts
    for (const conflict of syncData.conflicts) {
        if (conflict.conflict_type === 'derived_event_overridden') {
            // Delete client's version
            await db.events.delete(conflict.entity_id);
            await db.sync_queue.where({entity_id: conflict.entity_id}).delete();

            // Server's version will come via server_changes
        } else {
            // Show conflict UI for other conflict types
            await db.conflicts.add(conflict);
        }
    }

    // Apply server changes (includes server's opening balance event)
    for (const change of syncData.server_changes) {
        if (change.entity_type === 'event' && change.action === 'create') {
            await db.events.put(change.data);  // Replace with server version
        }
    }

    // ✅ Result: Single opening balance event with server's description
    // ✅ Projection still shows £1000 (no duplicates)
    // ✅ User doesn't see any error or conflict UI
}
```

### Why This Works

1. **Existing Conflict Field**: Sync protocol already has `conflicts` array
2. **Silent Resolution**: Derived events can be silently replaced (not user-facing conflict)
3. **Server Authority**: Server's opening balance event is authoritative
4. **No Protocol Change**: Uses existing `conflicts` + `server_changes` fields

### The Key Insight

**You don't need a new `corrections` field!** The existing conflict resolution is perfect for this:

```javascript
// Conflicts come in two flavors:

// 1. USER-FACING CONFLICT (show UI)
{
    conflict_type: "concurrent_edit",  // User must choose
    client_version: {...},
    server_version: {...}
}

// 2. DERIVED EVENT CONFLICT (silent resolution)
{
    conflict_type: "derived_event_overridden",  // Auto-resolve
    resolution: "use_server"
}
```

**Frontend Logic**:
```javascript
if (conflict.conflict_type === 'derived_event_overridden') {
    // Silently replace with server version (no UI)
    deleteClientVersion();
} else {
    // Show conflict resolution modal (user chooses)
    showConflictUI(conflict);
}
```

---

## All Fragmented Logic Identified

### 1. Mode Checks (14+ locations in app.js)

**Current**: Scattered `if (storage.mode === 'full')` checks

```javascript
// app.js:181 - Conflict checking
if (storage.mode === 'full') {
    await this.checkForConflicts();
}

// app.js:214 - User loading
if (storage.mode === 'full') {
    this.users = await db.users.toArray();
}

// app.js:459 - Reconciliation trigger
if (storage.mode === 'full' && this.accounts.some(a => a.pending_reconciliation)) {
    await this.triggerReconciliation();
}

// app.js:873 - Opening balance event creation
if (storage.mode === 'full' && parseFloat(accountData.current_balance) !== 0) {
    const openingEvent = await this._createOpeningBalanceEvent(account);
    // ...
}

// app.js:2200 - Adjustment event creation
if (storage.mode === 'full') {
    const adjustmentEvent = await this._createAdjustmentEvent(account, drift);
    // ...
}

// app.js:2660, 2721, 2784 - Recurring rule operations
if (storage.mode === 'full') {
    // Offline queue logic
}

// app.js:2999 - Reconciliation
if (storage.mode !== 'full') {
    return;  // Only in full mode
}
```

**After Queue-as-State**: Mode checks become irrelevant

```javascript
// NO MODE CHECKS NEEDED!
// Queue exists in full mode only, operations just work:

async createAccount(accountData) {
    // Works in all modes via storage adapter
    const account = await storage.createAccount(accountData);

    // Storage adapter handles mode-specific logic internally
    // No if-statements in application code!
}
```

---

### 2. Phantom Event Generation (projection.js)

**Current**: Conditional phantom generation

```javascript
// projection.js:140-161
const isOffline = !navigator.onLine || (window.storage && window.storage.mode === 'full');

if (isOffline) {
    const rules = await db.recurring_rules.toArray();
    if (rules && rules.length > 0) {
        const phantomEvents = await generateRecurringEventsClientSide(rules, start, end, settings);
        events = [...events, ...phantomEvents];  // MERGE IN-MEMORY
    }
}
```

**After Queue-as-State**: No phantom generation

```javascript
// projection.js - SIMPLIFIED
// Just read from Dexie - instances already created when rule was created
const events = await db.events.where('event_date').between(startDate, endDate).toArray();

// ✅ No phantom generation
// ✅ No deduplication queries
// ✅ No _clientGenerated flag checks
```

---

### 3. Shadow Event Helpers (app.js)

**Current**: Duplicate business logic in helpers

```javascript
// app.js:789-822 - _createOpeningBalanceEvent
// app.js:829-853 - _createAdjustmentEvent

// DUPLICATION of backend logic:
// - Rate lookup from settings
// - Event structure
// - Field values
```

**After Queue-as-State**: Pure functions (no duplication)

```javascript
// Shared pure functions (can be tested independently)
function createOpeningBalanceEventData(account, settings) {
    return {
        event_date: account.created_at || today(),
        description: "Opening Balance",  // Intentional: frontend version
        amount: account.current_balance,
        currency: account.currency,
        rate_to_base: calculateRateToBase(account.currency, settings),
        account_id: account.id,
        is_baseline: true,
        is_opening_balance: true
    };
}

// Usage
async createAccount(accountData) {
    const accountId = generateUUID();
    await db.accounts.add({...accountData, id: accountId, _queued_op: 'create'});
    await db.queueChange('account', accountId, 'create', accountData);

    if (accountData.current_balance !== 0) {
        const eventData = createOpeningBalanceEventData(accountData, settings);  // Pure!
        await applyQueuedChange({
            entity_type: 'event',
            action: 'create',
            data: eventData,
            dependencies: [accountId],
            _derived_from: 'account_creation'
        });
    }
}
```

---

### 4. Deduplication Logic (Multiple Places)

**Current**: Manual deduplication checks

```javascript
// app.js:876-878 - Opening balance deduplication
const existingOpeningBalance = await db.events
    .where({ account_id: createdAccount.id, is_opening_balance: true })
    .count();

if (existingOpeningBalance === 0) {
    // Only create if doesn't exist
}

// recurring.js:44-51 - Phantom deduplication
const existing = await db.events.where({
    recurring_rule_id: rule.id,
    event_date: dateStr
}).first();

if (existing) {
    continue;  // Skip if already exists
}
```

**After Queue-as-State**: Queue handles deduplication

```javascript
// NO MANUAL CHECKS NEEDED!
// Queue items have unique entity_id
// Dexie primary key prevents duplicates
// Sync response handles conflicts

await applyQueuedChange({
    entity_id: eventId,  // UUID - unique by definition
    entity_type: 'event',
    action: 'create',
    data: eventData
});
// If eventId already exists in Dexie → Error thrown
// If duplicate synced → Server detects via conflict resolution
```

---

### 5. Pending Reconciliation Flag (Multiple Places)

**Current**: Manual flag management

```javascript
// app.js:459, 531 - Check for pending reconciliation
if (this.accounts.some(a => a.pending_reconciliation)) {
    await this.triggerReconciliation();
}

// app.js:2999 - Reconciliation trigger checks flag
async triggerReconciliation() {
    // Send to server, server checks pending_reconciliation flag
}
```

**After Queue-as-State**: Flag still used, but simplified

```javascript
// Frontend: Set flag when balance updated
async saveBalanceUpdate() {
    await db.accounts.update(accountId, {
        current_balance: newBalance,
        pending_reconciliation: true,  // ← Mark for reconciliation
        _queued_op: 'update'
    });

    await db.queueChange('account', accountId, 'update', {
        current_balance: newBalance,
        pending_reconciliation: true
    });

    // ✅ Server will reconcile on next sync (existing behavior)
    // ✅ No frontend adjustment event creation
    // ✅ Server creates authoritative [auto] adjustment
}

// Backend: Unchanged (trigger_reconciliation during sync)
```

**Key Insight**: With queue-as-state, frontend doesn't need to create adjustment events!

**OLD** (Current):
```javascript
// Frontend creates adjustment event optimistically
const adjustmentEvent = await _createAdjustmentEvent(account, drift);
await db.events.add(adjustmentEvent);
await db.queueChange('event', ...);

// Problem: What if frontend calculation is wrong?
```

**NEW** (Queue-as-State):
```javascript
// Frontend ONLY sets pending_reconciliation flag
await db.accounts.update(accountId, {pending_reconciliation: true});
await db.queueChange('account', accountId, 'update', {pending_reconciliation: true});

// Server creates authoritative adjustment on sync
// ✅ No duplication risk
// ✅ Server is always correct
// ✅ Simpler frontend logic
```

---

### 6. Recurring Event Edit/Delete (app.js)

**Current**: Complex phantom-to-real conversion logic

```javascript
// app.js:2358-2380 - viewEventDetails()
if (event._clientGenerated) {
    // It's a phantom - show conversion confirmation
    const confirmed = await showConfirmation("Edit instance or rule?");
    if (confirmed === 'instance') {
        await convertPhantomToReal(event);
    } else {
        // Edit rule
    }
}

// app.js:2700-2800 - saveRecurringRule()
if (storage.mode === 'full') {
    // Complex queue deduplication logic
    // Remove old queue entries
    // Add new ones
}

// app.js:2780-2800 - deleteRecurringRule()
if (storage.mode === 'full') {
    // Offline deletion logic
    await db.recurring_rules.delete(ruleId);
    await db.queueChange('recurring_rule', ruleId, 'delete', null);
}
```

**After Queue-as-State**: Instances are real events

```javascript
// NO PHANTOM CONVERSION NEEDED!
// All recurring instances exist in Dexie as real events

async viewEventDetails(eventId) {
    const event = await db.events.get(eventId);

    if (event.recurring_rule_id) {
        // It's a recurring instance - user can:
        // 1. Edit this instance (update event)
        // 2. Edit rule (affects future instances)
        this.eventForm = event;
        this.showEventModal = true;
    }
}

// Editing instance is just normal event update
async saveEvent() {
    await db.events.update(eventId, updates);
    await db.queueChange('event', eventId, 'update', updates);
    // ✅ Server will validate on sync
}

// Deleting rule deletes future unedited instances
async deleteRecurringRule(ruleId) {
    await db.recurring_rules.delete(ruleId);
    await db.queueChange('recurring_rule', ruleId, 'delete', null);

    // Find all unedited future instances
    const futureInstances = await db.events.where({
        recurring_rule_id: ruleId,
        event_date: {$gte: today},
        _user_edited: {$ne: true}  // Not manually edited
    }).toArray();

    for (const instance of futureInstances) {
        await db.events.delete(instance.id);
        await db.queueChange('event', instance.id, 'delete', null);
    }

    // ✅ Past instances preserved
    // ✅ Edited instances preserved
    // ✅ Only future unedited instances removed
}
```

---

## Summary: Complexity Reduction

### Before (Current Fractured State)

| Area | Complexity |
|------|------------|
| **Mode Checks** | 14+ scattered if-statements |
| **Special Flags** | 4 different flags (_shadow, _phantom, _clientGenerated, _queued_op) |
| **Business Logic Duplication** | 4 major areas (opening balance, adjustment, recurring, projection) |
| **Deduplication Queries** | 3+ manual checks per operation |
| **Phantom Generation** | Every projection calculation (expensive) |
| **Conversion Logic** | Phantom → Real conversion (complex) |

### After (Queue-as-State)

| Area | Simplification |
|------|----------------|
| **Mode Checks** | 0 (handled by storage adapter) |
| **Special Flags** | 1 (_queued_op) + 1 (_derived_from for derived events) |
| **Business Logic Duplication** | 1 (projection calculation - acceptable) |
| **Deduplication Queries** | 0 (queue + Dexie primary key) |
| **Phantom Generation** | 0 (instances created at rule creation) |
| **Conversion Logic** | 0 (all instances are real events) |

**Estimated LOC Reduction**: ~300 lines of special-case handling removed

---

## Final Answer to Your Questions

1. ✅ **Backend Adjustment Events**: Created by `core/reconciliation.py` during sync phase
2. ✅ **Recurring Window**: Answer C - Fixed window (need to verify settings, assume ±30 days)
3. ✅ **Sync Protocol**: Answer C is **perfect** - existing conflicts field handles everything
4. ✅ **Migration**: Big bang rewrite (approved - no users yet)
5. ✅ **Recurring Instances**: Answer A - Generated at rule creation

---

## Next Steps

1. ✅ User reviews findings
2. ⏳ **Create implementation plan** (refactor-implementation-plan.md)
3. ⏳ **Execute big bang rewrite** (estimated 3-4 days)
   - Phase 1: Queue enhancements
   - Phase 2: Remove shadow events
   - Phase 3: Remove phantom events
   - Phase 4: Cleanup and testing

**Ready to proceed when you are.**
