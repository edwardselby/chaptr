# Phase 5 - Offline Capability Testing Guide

**Phase:** 5 of 7 - Offline Capability
**Status:** Implementation Complete - Manual Testing Required
**Date:** December 23, 2024

---

## Testing Overview

This guide covers manual testing for Phase 5's three-tier progressive enhancement architecture. All implementation is complete - these tests validate the system works correctly across all modes and network conditions.

**7 Remaining Tasks:**
- Task 106: Test app functionality in airplane mode
- Task 107: Make changes offline and verify queuing
- Task 108: Restore connection and verify sync completes
- Task 109: Verify offline/online indicators work correctly
- Task 220: Test Mode 1 Full with offline/online switching
- Task 221: Test Mode 2 Sync-Only in private browsing
- Task 222: Test Mode 3 Basic in HTTP environment

---

## Prerequisites

### Environment Setup

**Mode 1 (Full) Testing:**
- HTTPS environment (required for service worker)
- Modern browser with IndexedDB support
- Network toggle capability (Chrome DevTools or Firefox DevTools)

**Mode 2 (Sync-Only) Testing:**
- Private browsing mode OR
- Browser with IndexedDB disabled

**Mode 3 (Basic) Testing:**
- HTTP environment (not HTTPS) OR
- Force mode with `?mode=basic` query parameter

### Starting the Application

```bash
# Start backend API
cd /Users/edward/PycharmProjects/Chaptr
python api/main.py

# Access frontend
# Mode 1: https://localhost:8000/static/index.html
# Mode 3: http://localhost:8000/static/index.html (HTTP, not HTTPS)
```

### Checking Current Mode

**In Browser Console:**
```javascript
// Check current mode
console.log('Current Mode:', window.storage?.mode);

// Check capabilities
console.log('Capabilities:', {
    offline: window.storage?.mode === 'full',
    sync: window.storage?.mode !== 'basic',
    storage: window.storage?.mode === 'full' ? 'IndexedDB' : 'Memory'
});
```

**In Settings Screen:**
- Navigate to Settings (⚙ icon)
- Check "Runtime Info" section:
  - **Mode**: Should show "Full (Offline-capable)", "Sync-Only (Online required)", or "Basic (Limited)"
  - **Capabilities**: Checkmarks for offline sync and conflict detection
  - **Storage**: IndexedDB or Memory

---

## Test Suite

### Task 106 & 220: Mode 1 Full - Offline Functionality

**Objective:** Verify app works completely offline with queue and sync on reconnect.

#### Test 1.1: Initial Setup (Online)

**Steps:**
1. Open app in HTTPS environment: `https://localhost:8000/static/index.html`
2. Open browser console (F12)
3. Verify service worker registration:
   ```
   [CHAPTR] Service Worker registered: https://localhost:8000/static/
   ```
4. Navigate to Settings screen
5. Verify **Runtime Info**:
   - Mode: "Full (Offline-capable)"
   - Capabilities: ✓ Offline sync, ✓ Conflict detection
   - Storage: "IndexedDB (Dexie 3.2.4)"
6. Create 2 test accounts:
   - Name: "Test Account 1", Currency: GBP, Balance: 1000
   - Name: "Test Account 2", Currency: USD, Balance: 500
7. Verify sync queue count shows **0**

**Expected Result:** ✅
- Mode detected as "Full"
- Service worker registered successfully
- Accounts created and visible
- Sync queue empty (0)

---

#### Test 1.2: Go Offline (Airplane Mode)

**Steps:**
1. **Chrome:** DevTools → Network tab → Throttling dropdown → "Offline"
2. **Firefox:** DevTools → Network tab → Throttling → "Offline"
3. **Alternative:** Turn on actual airplane mode
4. Verify offline indicator appears in UI (connection status badge)
5. Reload the page (Ctrl+R or Cmd+R)

**Expected Result:** ✅
- App loads from service worker cache
- All previously created accounts still visible
- Offline indicator shows "Offline" or similar status
- No errors in console

---

#### Test 1.3: Create Changes Offline (Task 107)

**Steps:**
1. **Still offline** - Create new account:
   - Name: "Offline Account", Currency: EUR, Balance: 750
2. **Still offline** - Update existing account:
   - Edit "Test Account 1" → Change balance to 1200
3. **Still offline** - Delete account:
   - Delete "Test Account 2"
4. Check sync queue count in UI (should increment)
5. Open browser console and verify queued changes:
   ```javascript
   db.sync_queue.toArray().then(q => console.table(q));
   ```

**Expected Result:** ✅
- All changes succeed immediately (optimistic update)
- UI updates instantly
- Sync queue count shows **3** (create + update + delete)
- Console shows 3 items in sync_queue table
- No network errors (changes queued locally)

---

#### Test 1.4: Verify Queuing Details

**Steps:**
1. In console, inspect queued changes:
   ```javascript
   db.sync_queue.toArray().then(changes => {
       changes.forEach(c => {
           console.log(`Action: ${c.action}, Entity: ${c.entity_type}, ID: ${c.entity_id}`);
       });
   });
   ```

**Expected Result:** ✅
- 3 changes in queue:
  1. `action: "create", entity_type: "account"` (Offline Account)
  2. `action: "update", entity_type: "account"` (Test Account 1)
  3. `action: "delete", entity_type: "account"` (Test Account 2)
- Each change has `entity_id`, `data`, `base_updated_at`

---

#### Test 1.5: Restore Connection and Auto-Sync (Task 108)

**Steps:**
1. Re-enable network connection:
   - **Chrome/Firefox:** DevTools → Network → "Online" or "No throttling"
   - **Airplane mode:** Turn off airplane mode
2. Wait 2-3 seconds for auto-sync to trigger
3. Check browser console for sync logs:
   ```
   [CHAPTR] Network restored - auto-syncing...
   [CHAPTR] Starting manual sync...
   [CHAPTR] Syncing 3 pending changes...
   [CHAPTR] Sync complete: 3 applied, 0 conflicts
   ```
4. Verify sync queue count returns to **0**
5. Verify all changes persisted:
   - "Offline Account" exists
   - "Test Account 1" balance is 1200
   - "Test Account 2" is deleted

**Expected Result:** ✅
- Auto-sync triggers automatically on reconnect
- Sync completes successfully (3 applied, 0 conflicts)
- Sync queue count returns to 0
- All offline changes persisted to server
- Toast notification: "Synced 3 changes"

---

#### Test 1.6: Manual Sync Button

**Steps:**
1. **While online**, create another account:
   - Name: "Manual Sync Test", Currency: GBP, Balance: 300
2. Verify sync queue count shows **1**
3. Click the **Sync** button in UI (manual sync)
4. Verify sync queue count returns to **0**
5. Check console for sync logs

**Expected Result:** ✅
- Manual sync button triggers sync
- Sync completes successfully
- Sync queue cleared
- Toast notification confirms sync

---

#### Test 1.7: Offline/Online Indicator (Task 109)

**Steps:**
1. **Online:** Verify connection status badge shows "Online" or green indicator
2. **Go offline:** Change to offline mode
3. Verify connection status badge shows "Offline" or red indicator
4. **Go online:** Restore connection
5. Verify connection status badge shows "Online" again

**Expected Result:** ✅
- Indicator accurately reflects network status
- Visual change on offline → online transition
- No lag in indicator update

---

### Task 221: Mode 2 Sync-Only - Private Browsing

**Objective:** Verify Mode 2 works in private browsing (no IndexedDB, immediate sync required).

#### Test 2.1: Open in Private Browsing

**Steps:**
1. Open **private/incognito window**:
   - Chrome: Ctrl+Shift+N (Windows) or Cmd+Shift+N (Mac)
   - Firefox: Ctrl+Shift+P (Windows) or Cmd+Shift+P (Mac)
2. Navigate to: `https://localhost:8000/static/index.html`
3. Open browser console
4. Check mode detection:
   ```javascript
   console.log('Mode:', window.storage?.mode);
   ```
5. Navigate to Settings → Runtime Info

**Expected Result:** ✅
- Mode detected as "Sync-Only (Online required)"
- Capabilities: ✗ Offline sync, ✓ Conflict detection
- Storage: "Memory (cleared on refresh)"
- Console shows: `[CHAPTR] Dexie unavailable, using Mode 2 (Sync-Only)`

---

#### Test 2.2: Create Account (Immediate Sync)

**Steps:**
1. **While online**, create account:
   - Name: "Sync Only Account", Currency: GBP, Balance: 500
2. Check browser console for immediate sync:
   ```
   [CHAPTR] Mode 2 - Creating account with immediate sync
   [CHAPTR] POST /api/accounts
   ```
3. Verify account appears in UI
4. Check sync queue count (should be **0** - no queue in Mode 2)

**Expected Result:** ✅
- Account created immediately via API call
- No queuing (sync queue count always 0)
- Account visible in UI
- No Dexie storage used

---

#### Test 2.3: Update and Delete (Immediate Sync)

**Steps:**
1. **While online**, update the account:
   - Change balance to 600
2. Check console for immediate PATCH request
3. **While online**, delete the account
4. Check console for immediate DELETE request

**Expected Result:** ✅
- All operations trigger immediate API calls
- No queuing behavior
- Changes reflected immediately in UI

---

#### Test 2.4: Offline Behavior (Should Fail)

**Steps:**
1. **Go offline** (DevTools → Network → Offline)
2. Try to create account:
   - Name: "Offline Test", Currency: USD, Balance: 100
3. Check for error message

**Expected Result:** ✅
- Operation **fails** with error
- Toast notification: "Network error - cannot create account offline"
- No optimistic update (account not visible in UI)
- Mode 2 requires network connection for all operations

---

#### Test 2.5: Refresh Clears Data

**Steps:**
1. **Go back online**
2. Create 2 accounts
3. Verify accounts visible
4. **Refresh page** (Ctrl+R or Cmd+R)
5. Check if accounts still visible

**Expected Result:** ✅
- After refresh, accounts are **re-fetched from server**
- Data not stored locally (memory cleared on refresh)
- Accounts re-appear after fetch completes

---

### Task 222: Mode 3 Basic - HTTP Environment

**Objective:** Verify Mode 3 works in HTTP (no service worker, no sync protocol, direct REST).

#### Test 3.1: Open in HTTP Environment

**Steps:**
1. Access app via **HTTP** (not HTTPS):
   - `http://localhost:8000/static/index.html`
2. Open browser console
3. Check mode detection:
   ```javascript
   console.log('Mode:', window.storage?.mode);
   ```
4. Navigate to Settings → Runtime Info
5. Check for **warning banner** at top of page

**Expected Result:** ✅
- Mode detected as "Basic (Limited)"
- Capabilities: ✗ Offline sync, ✗ Conflict detection
- Storage: "Memory (cleared on refresh)"
- **Warning banner visible**: "⚠ Limited mode - offline sync unavailable. Use HTTPS for full functionality."
- Console shows: `[CHAPTR] Service Worker not supported - using Mode 3 (Basic)`

---

#### Test 3.2: Create Account (Direct REST)

**Steps:**
1. **While online**, create account:
   - Name: "Basic Account", Currency: EUR, Balance: 250
2. Check browser console for direct API call:
   ```
   [CHAPTR] Mode 3 - Creating account via direct REST
   [CHAPTR] POST /api/accounts
   ```
3. Verify account appears in UI
4. Check sync queue count (should be **N/A** or hidden in Mode 3)

**Expected Result:** ✅
- Account created via direct REST call
- No queuing, no sync protocol
- Account visible immediately
- No service worker, no Dexie

---

#### Test 3.3: Update and Delete (Direct REST)

**Steps:**
1. Update the account → Change balance to 300
2. Check console for `PATCH /api/accounts/:id`
3. Delete the account
4. Check console for `DELETE /api/accounts/:id`

**Expected Result:** ✅
- All operations use direct REST endpoints
- No sync protocol involved
- Changes reflected immediately

---

#### Test 3.4: Offline Behavior (Should Fail)

**Steps:**
1. **Go offline**
2. Try to create account
3. Check for error

**Expected Result:** ✅
- Operation **fails** immediately
- Error toast: "Network error - operation failed"
- No offline capability
- No queuing

---

#### Test 3.5: Conflict Handling (Last Write Wins)

**Steps:**
1. **Go back online**
2. Open app in **two different browser tabs** (both HTTP)
3. In **Tab 1**: Create account "Conflict Test", balance 100
4. In **Tab 2**: Refresh page, then edit "Conflict Test" → balance 200
5. In **Tab 1**: Edit "Conflict Test" → balance 300
6. Refresh both tabs

**Expected Result:** ✅
- **Last write wins** (no conflict detection)
- Final balance is whichever tab saved last (likely 300)
- No conflict notification
- Mode 3 does not track conflicts

---

## Edge Cases and Advanced Tests

### Edge Case 1: Queue Limit Warning (400 changes)

**Mode:** Mode 1 Full
**Objective:** Verify warning toast at 400 pending changes.

**Steps:**
1. Go offline
2. Create a script to queue 400 changes:
   ```javascript
   async function create400Accounts() {
       for (let i = 1; i <= 400; i++) {
           await db.queueChange('account', `test-${i}`, 'create', {
               name: `Test ${i}`,
               currency: 'GBP',
               current_balance: 100
           });
       }
       console.log('Queued 400 changes');
   }
   create400Accounts();
   ```
3. Check for warning toast
4. Verify sync queue count shows **400**

**Expected Result:** ✅
- Warning toast appears: "⚠ 400+ pending changes. Sync recommended."
- Sync queue count shows 400
- Operations still allowed

---

### Edge Case 2: Queue Limit Block (500 changes)

**Mode:** Mode 1 Full
**Objective:** Verify hard block at 500 pending changes.

**Steps:**
1. Continue from Edge Case 1 (400 changes queued)
2. Go offline
3. Try to create 100 more accounts (should hit 500 limit)
4. Check for block modal

**Expected Result:** ✅
- At 500th change, **modal appears**: "Queue limit reached. Please sync before making more changes."
- Modal shows **Sync Now** button
- Further operations blocked until sync
- User must sync or go online to continue

---

### Edge Case 3: Full Sync Requirement (Stale Client)

**Mode:** Mode 1 Full
**Objective:** Test server-triggered full sync for stale clients.

**Steps:**
1. This requires **backend modification** to simulate stale client
2. Modify `/api/sync` endpoint to return:
   ```json
   {
       "applied": [],
       "conflicts": [],
       "server_changes": [],
       "full_sync_required": true,
       "sync_timestamp": "2024-12-23T20:00:00Z"
   }
   ```
3. Trigger manual sync
4. Verify full sync behavior

**Expected Result:** ✅
- Toast: "Updating to latest data..."
- Dexie cleared
- All data re-downloaded from server via `GET /api/sync/full`
- Toast: "Data updated successfully"
- No data loss

---

## Test Matrix Summary

| Test Scenario | Mode 1 (Full) | Mode 2 (Sync) | Mode 3 (Basic) |
|--------------|---------------|---------------|----------------|
| **Offline Create** | ✅ Queued | ❌ Fails | ❌ Fails |
| **Offline Update** | ✅ Queued | ❌ Fails | ❌ Fails |
| **Offline Delete** | ✅ Queued | ❌ Fails | ❌ Fails |
| **Auto-sync on Reconnect** | ✅ Yes | N/A | N/A |
| **Manual Sync** | ✅ Yes | N/A | N/A |
| **Conflict Detection** | ✅ Yes | ✅ Yes | ❌ No |
| **Refresh Persistence** | ✅ Yes (Dexie) | ❌ No (memory) | ❌ No (memory) |
| **Service Worker** | ✅ Yes | ✅ Yes | ❌ No |
| **Queue Limits** | ✅ 400/500 | N/A | N/A |
| **Full Sync** | ✅ Yes | N/A | N/A |

---

## Completion Checklist

### Task 106: Airplane Mode Testing
- [ ] App loads offline from service worker cache
- [ ] Previously loaded data visible
- [ ] Offline indicator shows correct status
- [ ] No console errors

### Task 107: Offline Changes and Queuing
- [ ] Create account offline → queued
- [ ] Update account offline → queued
- [ ] Delete account offline → queued
- [ ] Sync queue count increments correctly
- [ ] Optimistic UI updates work

### Task 108: Connection Restore and Sync
- [ ] Auto-sync triggers on reconnect
- [ ] All queued changes synced successfully
- [ ] Sync queue count returns to 0
- [ ] Toast notification confirms sync

### Task 109: Offline/Online Indicators
- [ ] Indicator shows "Online" when connected
- [ ] Indicator shows "Offline" when disconnected
- [ ] Indicator updates immediately on status change

### Task 220: Mode 1 Full Testing
- [ ] Mode detected correctly in HTTPS
- [ ] Service worker registers successfully
- [ ] Offline CRUD operations work
- [ ] Queue and sync work correctly
- [ ] Mode display in Settings accurate

### Task 221: Mode 2 Sync-Only Testing
- [ ] Mode detected in private browsing
- [ ] Immediate sync on all operations
- [ ] No queuing behavior
- [ ] Offline operations fail gracefully
- [ ] Refresh re-fetches data

### Task 222: Mode 3 Basic Testing
- [ ] Mode detected in HTTP environment
- [ ] Warning banner visible
- [ ] Direct REST calls for all operations
- [ ] No conflict detection
- [ ] Last write wins on conflicts

---

## Known Issues and Limitations

### Mode 1 (Full)
- Requires HTTPS for service worker
- Browser must support IndexedDB
- Queue limited to 500 changes

### Mode 2 (Sync-Only)
- No offline capability
- Data cleared on refresh
- Requires constant network connection

### Mode 3 (Basic)
- No service worker (no asset caching)
- No conflict detection
- Last write wins on simultaneous edits
- Data cleared on refresh

---

## Troubleshooting

### Service Worker Not Registering

**Symptom:** Console error: "Service Worker registration failed"

**Solutions:**
1. Ensure using HTTPS (not HTTP)
2. Check for browser support: `'serviceWorker' in navigator`
3. Clear browser cache and reload
4. Check for existing service workers: Chrome DevTools → Application → Service Workers

---

### Mode Detection Incorrect

**Symptom:** Wrong mode detected (e.g., expecting Full but got Sync-Only)

**Solutions:**
1. Check browser environment (HTTPS vs HTTP)
2. Check IndexedDB availability: Open DevTools → Application → IndexedDB
3. Force mode with query parameter: `?mode=full` or `?mode=basic`
4. Clear IndexedDB and reload
5. Check localStorage: `localStorage.getItem('FORCE_MODE')`

---

### Sync Not Triggering

**Symptom:** Queued changes not syncing on reconnect

**Solutions:**
1. Check network connection (DevTools → Network tab)
2. Verify backend API is running: `curl http://localhost:8000/api/health`
3. Check console for sync errors
4. Try manual sync button
5. Verify sync endpoint: `POST http://localhost:8000/api/sync`

---

### Queue Limit Not Enforcing

**Symptom:** Can create more than 500 changes

**Solutions:**
1. Check `queueChange()` implementation in storage-adapter.js
2. Verify `db.sync_queue.count()` working correctly
3. Check console for queue limit logs
4. Clear sync queue and retry: `db.sync_queue.clear()`

---

## Test Completion Report Template

```markdown
# Phase 5 Testing Report

**Date:** YYYY-MM-DD
**Tester:** [Name]
**Environment:** [Browser, OS]

## Mode 1 (Full) - HTTPS
- [ ] Task 106: Airplane mode - ✅ PASS / ❌ FAIL
- [ ] Task 107: Offline queuing - ✅ PASS / ❌ FAIL
- [ ] Task 108: Sync on reconnect - ✅ PASS / ❌ FAIL
- [ ] Task 109: Indicators - ✅ PASS / ❌ FAIL
- [ ] Task 220: Full mode testing - ✅ PASS / ❌ FAIL

## Mode 2 (Sync-Only) - Private Browsing
- [ ] Task 221: Sync-Only testing - ✅ PASS / ❌ FAIL

## Mode 3 (Basic) - HTTP
- [ ] Task 222: Basic mode testing - ✅ PASS / ❌ FAIL

## Edge Cases
- [ ] Queue warning (400) - ✅ PASS / ❌ FAIL
- [ ] Queue block (500) - ✅ PASS / ❌ FAIL
- [ ] Full sync requirement - ✅ PASS / ❌ FAIL

## Issues Found
[List any bugs or unexpected behavior]

## Notes
[Additional observations]

**Overall Status:** ✅ ALL PASS / ⚠️ SOME FAILURES / ❌ BLOCKED
```

---

## Next Steps After Testing

Once all tests pass:

1. **Mark tasks complete:**
   ```bash
   task 106 done
   task 107 done
   task 108 done
   task 109 done
   task 220 done
   task 221 done
   task 222 done
   ```

2. **Update CHANGELOG.md** with Phase 5 tasks

3. **Create feature branch and PR:**
   ```bash
   git checkout dev
   git checkout -b feature/phase5-offline-capability
   git add -A
   git commit -m "CPTR-[uuids]: Complete Phase 5 - Offline capability with three-tier progressive enhancement"
   git push -u origin feature/phase5-offline-capability
   gh pr create --base dev --title "Phase 5: Offline Capability" --body "Complete implementation of three-tier offline system"
   ```

4. **Proceed to Phase 6: Reconciliation** (33 tasks)

---

**Testing Guide Complete**
