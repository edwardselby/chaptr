# Queue-as-State Refactor - Testing Guide

**Version**: 1.0
**Date**: 2025-12-29
**Refactor Branch**: `refactor/queue-as-state`

---

## Overview

This document outlines comprehensive testing scenarios for the queue-as-state refactor. The refactor eliminates fragmented patterns (shadow events, phantom events, mode checks) in favor of a unified queue-as-state architecture.

**Core Principle**: `IndexedDB State = Last Server State + Applied Sync Queue`

---

## Architecture Changes Summary

### What Changed:

1. **Queue Schema Enhanced** - db.js schema v3 with metadata tracking
2. **Pure Helper Functions** - event-helpers.js, queue-helpers.js created
3. **Account Creation** - Uses queue-first pattern with derived events
4. **Recurring Rules** - Generate real instances (no more phantoms)
5. **Adjustment Events** - Frontend sets flag, server creates event
6. **Mode Checks Removed** - Business logic works uniformly across modes
7. **Storage Adapter Complete** - Recurring rule methods added

### What to Test:

- ✅ Derived events created with proper metadata
- ✅ Server corrections applied silently
- ✅ Recurring instances are real events
- ✅ Projection simplified (no phantom generation)
- ✅ Reconciliation triggered by flag
- ✅ Queue metadata preserved through sync

---

## Test Scenario 1: Account Creation Offline

**Objective**: Verify account creation generates opening balance event with proper queue metadata.

### Prerequisites:
- CHAPTR running in full offline mode
- Clean IndexedDB (or known state)

### Steps:

1. **Create Account**:
   - Navigate to Accounts screen
   - Click "Add Account"
   - Name: "Test Account"
   - Currency: GBP
   - Current Balance: £1000
   - Is Default: Yes
   - Click "Create"

2. **Verify Local State**:
   - Open browser DevTools → Application → IndexedDB → CHAPTR
   - Check `accounts` table:
     - ✅ Account exists with id, £1000 balance
     - ✅ Has `_queued_op: 'create'` flag
   - Check `events` table:
     - ✅ Opening balance event exists
     - ✅ Description: "opening balance" (lowercase)
     - ✅ Amount: 1000
     - ✅ `is_opening_balance: true`
     - ✅ `is_baseline: true`
     - ✅ Has `_queued_op: 'create'` flag
   - Check `sync_queue` table:
     - ✅ 2 entries (account + event)
     - ✅ Event entry has `_derived_from: 'account_creation'`
     - ✅ Event entry has `dependencies: [account_id]`

3. **Sync to Server**:
   - Click sync button
   - Wait for sync to complete

4. **Verify Server Acceptance**:
   - Check `sync_queue` table:
     - ✅ Empty (both changes applied)
   - Check `accounts` table:
     - ✅ Account still exists
     - ✅ NO `_queued_op` flag
     - ✅ Has `updated_at` from server
   - Check `events` table:
     - ✅ Opening balance event still exists
     - ✅ NO `_queued_op` flag
     - ✅ May have server-corrected fields (server version wins)

### Expected Outcome:
- ✅ Single opening balance event (no duplicates)
- ✅ Projection shows £1000 balance
- ✅ No conflicts generated

---

## Test Scenario 2: Recurring Rule Creation

**Objective**: Verify recurring rules generate real instances (no phantoms).

### Prerequisites:
- CHAPTR running in full offline mode
- At least one account exists

### Steps:

1. **Create Recurring Rule**:
   - Navigate to Events/Projection screen
   - Click "Add Event"
   - Check "Recurring" checkbox
   - Description: "Weekly Coffee"
   - Amount: -£15
   - Account: (select existing)
   - Frequency: Weekly
   - Day: Monday (1)
   - Start Date: (today's date)
   - End Date: (leave empty for ongoing)
   - Click "Create"

2. **Verify Instances Generated**:
   - Open DevTools → IndexedDB → events table
   - ✅ Multiple event entries exist (±30 days from today)
   - ✅ Each has `recurring_rule_id` = rule UUID
   - ✅ Each has `_queued_op: 'create'` flag
   - Check `sync_queue` table:
     - ✅ 1 entry for rule + N entries for instances
     - ✅ Each instance has `_derived_from: 'recurring_rule_creation'`
     - ✅ Each instance has `dependencies: [rule_id]`

3. **Verify Projection**:
   - View projection
   - ✅ Instances appear on correct dates
   - ✅ No duplicate events
   - ✅ NO phantom generation logic running (check console logs)

4. **Edit Instance**:
   - Click on one recurring instance
   - Change amount to -£20
   - Save
   - ✅ Instance updated (it's a real event, not phantom)
   - ✅ Future instances unaffected

5. **Sync to Server**:
   - Click sync
   - ✅ All instances synced
   - ✅ Server may override with authoritative versions

### Expected Outcome:
- ✅ Real instances in Dexie (not ephemeral phantoms)
- ✅ Instances can be edited directly
- ✅ Projection is fast (no generation loop)

---

## Test Scenario 3: Recurring Rule Update

**Objective**: Verify rule updates regenerate future instances.

### Prerequisites:
- Recurring rule exists with instances
- Some instances are in the future

### Steps:

1. **Update Recurring Rule**:
   - Navigate to recurring rule
   - Click edit
   - Change amount from -£15 to -£20
   - Save

2. **Verify Instance Regeneration**:
   - Check `events` table:
     - ✅ Future unedited instances deleted
     - ✅ New instances created with -£20
   - Check `sync_queue`:
     - ✅ Delete entries for old instances
     - ✅ Create entries for new instances

3. **Verify Edited Instances Preserved**:
   - Edited instances (created_at ≠ updated_at) should remain unchanged

### Expected Outcome:
- ✅ Future instances reflect new amount
- ✅ Edited instances preserved
- ✅ Past instances unchanged

---

## Test Scenario 4: Recurring Rule Deletion

**Objective**: Verify rule deletion preserves past instances.

### Prerequisites:
- Recurring rule with past and future instances

### Steps:

1. **Delete Recurring Rule**:
   - Click delete on recurring rule
   - Confirm deletion

2. **Verify Instance Handling**:
   - Check `events` table:
     - ✅ Past instances preserved
     - ✅ Future unedited instances deleted
     - ✅ Manually edited instances preserved
   - Check `recurring_rules` table:
     - ✅ Rule deleted

### Expected Outcome:
- ✅ Past events remain (historical record)
- ✅ Future auto-generated events removed
- ✅ Manually edited future events preserved

---

## Test Scenario 5: Balance Reconciliation

**Objective**: Verify balance updates set flag, server creates adjustment.

### Prerequisites:
- Account with known balance
- Projection visible

### Steps:

1. **Trigger Drift**:
   - Note current projected balance (e.g., £500)
   - Click "Update Balance" on account
   - Enter actual balance: £550 (£50 drift)
   - Save

2. **Verify Local State**:
   - Check `accounts` table:
     - ✅ `current_balance: 550`
     - ✅ `pending_reconciliation: true`
     - ✅ `balance_updated_at` updated
   - Check `events` table:
     - ✅ NO frontend adjustment event created
   - Check projection:
     - ✅ Virtual drift row displayed (£50 difference)

3. **Sync to Server**:
   - Click sync
   - Server triggers reconciliation

4. **Verify Server Adjustment**:
   - Check `events` table after sync:
     - ✅ NEW adjustment event from server
     - ✅ Description: "balance adjustment" (lowercase)
     - ✅ Amount: 50 (drift amount)
     - ✅ `is_auto_adjustment: true`
     - ✅ `is_baseline: true`
   - Check `accounts` table:
     - ✅ `pending_reconciliation: false` (cleared by server)

### Expected Outcome:
- ✅ Frontend sets flag only
- ✅ Server creates authoritative adjustment
- ✅ Single adjustment event (no duplicates)
- ✅ Projection now accurate

---

## Test Scenario 6: Derived Event Conflict Resolution

**Objective**: Verify server corrections silently override client-generated derived events.

### Prerequisites:
- Offline mode with queued changes

### Steps:

1. **Create Conflict Scenario**:
   - Create account offline (£1000 balance)
   - Opening balance event queued
   - Simulate server correction (server decides balance was actually £950)

2. **Sync and Verify**:
   - Click sync
   - Check `conflicts` table:
     - ✅ Conflict entry with `conflict_type: 'derived_event_overridden'`
     - ✅ `resolved_at` is set (auto-resolved)
   - Check `events` table:
     - ✅ Server's opening balance (£950) exists
     - ✅ Client's opening balance (£1000) deleted
   - ✅ NO user notification (silent resolution)

### Expected Outcome:
- ✅ Server version wins automatically
- ✅ No user intervention required
- ✅ Conflict logged but resolved

---

## Test Scenario 7: Queue Metadata Preservation

**Objective**: Verify queue metadata (_derived_from, dependencies) preserved through sync.

### Prerequisites:
- Offline mode

### Steps:

1. **Create Queued Changes**:
   - Create account → opening balance queued
   - Create recurring rule → instances queued

2. **Verify Queue Metadata**:
   - Check `sync_queue` entries:
     - Opening balance: `_derived_from: 'account_creation'`, `dependencies: [account_id]`
     - Instances: `_derived_from: 'recurring_rule_creation'`, `dependencies: [rule_id]`

3. **Sync and Verify**:
   - Sync completes successfully
   - ✅ Metadata used by server for intelligent processing

### Expected Outcome:
- ✅ Queue carries rich metadata
- ✅ Server can make smart decisions

---

## Test Scenario 8: Edge Cases

### 8.1: £0 Balance Account

1. Create account with £0 balance
2. ✅ NO opening balance event created
3. ✅ Account created successfully

### 8.2: Queue Limit (500 changes)

1. Queue 500+ changes (create many events)
2. ✅ Hard block modal shown at 500
3. ✅ User forced to sync before continuing

### 8.3: Sync Conflicts (Non-Derived)

1. Edit same event offline and online
2. ✅ Conflict detected
3. ✅ Conflict UI shown (user resolves manually)

### 8.4: Network Interruption During Sync

1. Start sync
2. Disconnect network mid-sync
3. ✅ Partial changes handled gracefully
4. ✅ Queue items remain for retry

---

## Test Scenario 9: Mode Independence

**Objective**: Verify business logic works in all 3 modes.

### Test in Each Mode:

**Mode 1 (Full Offline)**:
- ✅ Account creation → opening balance queued
- ✅ Recurring rule → instances generated
- ✅ Balance update → pending_reconciliation set

**Mode 2 (Sync-Only)**:
- ✅ Account creation → direct API + Dexie update
- ✅ Recurring rule → direct API + instances in Dexie
- ✅ Balance update → pending_reconciliation set + API call

**Mode 3 (Basic)**:
- ✅ Account creation → direct API (no Dexie)
- ✅ Recurring rule → direct API
- ✅ Balance update → direct API

### Expected Outcome:
- ✅ NO mode checks in app.js business logic
- ✅ Storage adapter handles mode routing internally

---

## Test Scenario 10: Projection Performance

**Objective**: Verify projection is faster without phantom generation.

### Steps:

1. **Create Recurring Rules**:
   - Create 5 weekly recurring rules
   - Create 3 monthly recurring rules

2. **Measure Projection Time**:
   - Open DevTools → Performance tab
   - Record projection calculation
   - ✅ No `generateRecurringEventsClientSide` calls in profile
   - ✅ Simple Dexie query for events

3. **Compare Before/After**:
   - Old: Regenerates phantoms on every projection
   - New: Single Dexie query

### Expected Outcome:
- ✅ Projection 2-5x faster
- ✅ Fewer Dexie queries
- ✅ Simpler call stack

---

## Regression Testing

### Critical Flows to Verify:

1. **Account Management**:
   - ✅ Create, update, delete accounts
   - ✅ Opening balance created/deleted with account
   - ✅ Default account toggle works

2. **Event Management**:
   - ✅ Create, update, delete one-time events
   - ✅ Recurring instances editable as normal events
   - ✅ Story assignment works

3. **Projection Calculation**:
   - ✅ Baseline view correct
   - ✅ Story views correct
   - ✅ All view correct
   - ✅ Gap indicators still work

4. **Sync Protocol**:
   - ✅ Full sync works
   - ✅ Incremental sync works
   - ✅ Conflict detection works
   - ✅ Stale client handled (full sync required)

---

## Success Criteria

### Functional:
- ✅ All 10 test scenarios pass
- ✅ No duplicate events
- ✅ No phantom generation
- ✅ Reconciliation works correctly
- ✅ Sync completes without errors

### Code Quality:
- ✅ 0 mode checks in business logic
- ✅ 1 special flag (_queued_op) instead of 4
- ✅ ~400 lines removed
- ✅ No business logic duplication

### Performance:
- ✅ Projection faster (no phantom loop)
- ✅ Fewer Dexie queries
- ✅ Simpler sync handling

---

## Known Issues / Limitations

*None identified as of 2025-12-29*

---

## Next Steps After Testing

1. Merge `refactor/queue-as-state` branch to `dev`
2. Deploy to staging environment
3. Monitor for edge cases in production
4. Update user documentation (if applicable)

---

## Appendix: Quick Checklist

Use this checklist for rapid manual testing:

- [ ] Create account offline → opening balance exists
- [ ] Sync account → single event, no duplicates
- [ ] Create weekly recurring rule → instances exist
- [ ] View projection → instances visible (no phantom generation)
- [ ] Edit recurring instance → edits work
- [ ] Update balance → pending_reconciliation flag set
- [ ] Sync balance update → server adjustment created
- [ ] Delete recurring rule → past instances preserved
- [ ] Check queue metadata → _derived_from fields present
- [ ] Test all 3 modes → consistent behavior

---

**End of Testing Guide**
