# Progressive Enhancement Strategy - Architecture Decisions

## Response to Design Agent Review

Thank you for the thorough review! We've worked through all 12 questions systematically. Here are our decisions for the progressive enhancement architecture.

---

## Detailed Responses

### 1. Mode 2 State Management

**Q: On page load in Mode 2, where does initial data come from? If user refreshes, what's the expected UX? Should Mode 2 use sessionStorage?**

**Decision:**
- Mode 2 always fetches from `/api/sync/full` on page load (same as Mode 1 when Dexie is empty)
- On refresh, user sees loading spinner while data fetches - acceptable for online-only mode
- **No sessionStorage** - adds complexity without much benefit. Mode 2 is designed for environments where offline isn't expected

---

### 2. Mode Detection Timing

**Q: When does init() run? What does user see during detection? Is 2-3 second detection acceptable?**

**Decision:**
- `init()` runs during Alpine component initialization (after mount)
- User sees: "Loading CHAPTR..." spinner with app skeleton visible
- Mode detection must complete in **<500ms** - `testSyncEndpoint()` has 500ms timeout
- If detection times out, fall back to Mode 3 (Basic)

---

### 3. Mode Transitions

**Q: Can mode change mid-session? What if user goes offline in Mode 2? Should there be "retry upgrade" button?**

**Decision:**
- **Mode is locked at initialization** - cannot change mid-session
- If Mode 2 user goes offline: operations fail with error toast "Connection required. Please check your internet."
- **No retry upgrade button** - user can refresh page to re-detect mode if connectivity improves
- This keeps implementation simple and predictable

---

### 4. Mode 3 Conflict Handling

**Q: Is "last write wins" acceptable? Should Mode 3 show warning banner? Could Mode 3 use optimistic locking?**

**Decision:**
- **Last write wins is acceptable** - Mode 3 is emergency fallback (<1% of users)
- **YES to persistent warning banner**: `⚠ Limited mode - offline sync unavailable`
- **No optimistic locking in Mode 3** - keeps it simple. Users in Mode 3 should upgrade browser/use HTTPS
- For our use case (you + Katrina), Mode 3 usage should be rare/temporary

---

### 5. Sync Queue Edge Cases

**Q: Max queue size before warning? Conflicting local changes handling? Show pending count in UI?**

**Decision:**
- **Max queue: 500 changes** (warn at 400, block at 500)
- **Conflicting local changes** (edit then delete): Sync protocol handles via timestamps - last action wins
- **Pending changes UI: Already implemented!** - amber badge in header shows count, clickable to sync
- No additional UI needed beyond existing implementation

---

### 6. Error Handling Consistency

**Q: Unified error handling strategy or independent per mode? UI for failed network requests? Should failed operations be retryable?**

**Decision:**
- **Unified error handling** via `showToast()` helper (already in utils.js)
- All network failures show toast: `"Failed to save account. [Mode-specific message]"`
  - **Mode 1**: "Changes queued for sync" (auto-retry on reconnect - already implemented)
  - **Mode 2**: "Please check connection and try again"
  - **Mode 3**: "Operation failed. Refresh and retry"
- **No explicit "Retry" button** - keeps UI clean. Mode 1 handles automatically, Mode 2/3 users refresh

---

### 7. Authentication Across Modes

**Q: How does each mode handle JWT expiry? Does Mode 3 use same auth? Auth failure: redirect or error?**

**Decision:**
- **All modes use same JWT authentication** via `apiRequest()` wrapper (utils.js)
- JWT expiry handling: 401 response triggers:
  1. `localStorage.removeItem('jwt_token')`
  2. `window.location.href = '/login'`
  3. User sees login screen
- **No mode-specific auth logic** - authentication is orthogonal to sync capability
- Existing `apiRequest()` implementation handles this correctly for all modes

---

### 8. Initial Load Flow

**Q: Brand new user flow for each mode? Unified bootstrap or per-mode?**

**Decision:**
- **Unified bootstrap flow** (all modes):
  1. `init()` runs → detect mode
  2. Check for local data (Dexie count for Mode 1, memory check for Mode 2/3)
  3. If empty → fetch initial data
     - **Mode 1 & 2**: `POST /api/sync/full` (efficient single request)
     - **Mode 3**: Sequential `GET /api/accounts`, `/api/stories`, `/api/events`
  4. Populate storage (Dexie/memory)
  5. Render UI
- Mode 3 is slower (multiple requests) but simpler - acceptable for fallback mode

---

### 9. Testing & Development

**Q: How to force specific mode for testing? Simulate Mode 2/3 in normal browser? Log mode to console?**

**Decision:**
- **Developer mode forcing**:
  - `localStorage.setItem('FORCE_MODE', 'sync-only')` forces Mode 2
  - Query param: `?mode=basic` forces Mode 3
  - Useful for QA and debugging
- **Simulation in DevTools**:
  - Mode 2: Settings → Privacy → Block IndexedDB for site
  - Mode 3: Serve via `http://localhost` (not `https://`)
- **Console logging on init**:
  ```javascript
  console.log('[CHAPTR] Running in mode:', this.mode);
  console.log('[CHAPTR] Mode capabilities:', {
    offline: mode === 'full',
    sync: mode !== 'basic'
  });
  ```
- Mode also visible in UI: **Settings screen shows current mode + capabilities**

---

### 10. Service Worker Interaction

**Q: Mode 1 if Service Worker fails? Does Mode 2 benefit from SW? Is SW required for "Full" mode?**

**Decision:**
- **Service Worker is independent of mode detection** (Phase 5 feature)
- **Mode 1 without SW**: Still "Full" mode - Dexie works, data syncs. Only loses static asset caching
- **Mode 2 + SW**: Benefits from HTML/CSS/JS caching → faster loads
- **Mode 3 + SW**: Same static caching benefit
- **SW is NOT required for any mode** - it's a performance enhancement
- SW registration failure logged but doesn't affect mode: `"Service Worker unavailable - static assets won't cache"`
- **This separation keeps concerns orthogonal**: Mode = data strategy, SW = asset strategy

---

### 11. Data Consistency Between Modes

**Q: User with pending Mode 1 changes opens Mode 3 - expected behavior? Warning needed? Realistic scenario?**

**Decision:**
- **Scenario**: User in Mode 1 (laptop, offline) makes changes → opens app in Mode 3 (old phone, HTTP)
- **Expected**: Mode 3 shows server state (doesn't see laptop's pending changes)
- **This is acceptable because**:
  1. Extremely rare scenario (<0.1% of sessions)
  2. When laptop reconnects + syncs, phone can refresh to see changes
  3. No data loss - changes preserved in Mode 1 queue
- **No warning** - adds complexity for negligible benefit
- Real conflict detection happens server-side when Mode 1 syncs
- **Our use case**: You and Katrina both use modern browsers → always Mode 1 → server handles conflicts properly

---

### 12. Sync Endpoint Dependency

**Q: Sync endpoint 500 errors - keep retrying or fallback? Timeout for testSyncEndpoint()? Monitor health during session?**

**Decision:**
- **testSyncEndpoint() implementation**:
  - Timeout: **500ms**
  - Success (200): Use Mode 2
  - Failure (4xx/5xx/timeout): Fall back to Mode 3
  - Show console warning: `"Sync endpoint unavailable - using Basic mode"`
- **No mid-session health monitoring**:
  - Simpler implementation
  - If sync fails during operation, Mode 1 queues (auto-retry), Mode 2 shows error toast
  - User can refresh to re-detect if endpoint recovers
- **Sync endpoint 500 treated same as network failure**:
  - Mode 1: Queue and retry later ✓
  - Mode 2: Error toast, user refreshes
  - Mode 3: N/A (doesn't use sync)
- This keeps init logic simple while handling degradation gracefully

---

## Summary of Key Decisions

| Area | Decision |
|------|----------|
| **Mode 2 init** | `/api/sync/full` on every load, no sessionStorage |
| **Mode detection** | <500ms timeout, locked at init, no mid-session changes |
| **Mode transitions** | None - mode locked for entire session |
| **Mode 3 conflicts** | Last write wins + persistent warning banner |
| **Queue limits** | 500 max changes (warn at 400, block at 500) |
| **Error handling** | Unified toast system, mode-aware messages |
| **Authentication** | Same JWT for all modes via apiRequest() |
| **Bootstrap flow** | Unified for all modes (Mode 3 uses sequential REST) |
| **Testing** | localStorage + query param forcing, console logging |
| **Service Worker** | Independent feature, optional for all modes |
| **Cross-device consistency** | No special handling (extremely rare scenario) |
| **Sync health** | Check at init only (500ms timeout), no monitoring |

---

## Additional Specifications

### Mode Indicator in Settings Screen

Add to Settings screen (admin section):

```
Runtime Information
├─ Mode: Full (Offline-capable)
├─ Capabilities: ✓ Offline sync  ✓ Conflict detection
└─ Storage: IndexedDB (Dexie 3.2.4)
```

Or for degraded modes:

```
Runtime Information
├─ Mode: Sync-Only (Online required)
├─ Capabilities: ✗ Offline sync  ✓ Conflict detection
└─ Storage: Memory (cleared on refresh)
```

### Mode 3 Warning Banner

Persistent banner at top of app (below header):

```html
<div class="warning-banner mode-3-warning">
  <span class="warning-icon">⚠</span>
  <span>Limited mode - offline sync unavailable. Use HTTPS for full functionality.</span>
</div>
```

Styling:
- Background: `rgba(255, 170, 0, 0.1)` (amber)
- Border: `1px solid var(--amber)`
- Always visible, non-dismissible in Mode 3

### Console Logging Format

```javascript
// On successful init
console.log('[CHAPTR] Initialized in mode:', this.mode);
console.log('[CHAPTR] Capabilities:', {
  offline: this.mode === 'full',
  sync: this.mode !== 'basic',
  storage: this.mode === 'full' ? 'IndexedDB' : 'Memory'
});

// On mode detection failure
console.warn('[CHAPTR] Mode detection timeout - falling back to Basic mode');

// On Service Worker failure
console.warn('[CHAPTR] Service Worker unavailable - static assets won\'t cache');
```

---

## Implementation Priority

**Phase 5 (Offline)**:
1. Implement storage adapter with mode detection (Tasks 213-214)
2. Extract Mode 1 (Full) from existing CRUD (Task 215) ← **Most work already done in PR2!**
3. Implement Mode 2 (Sync-Only) (Task 216)
4. Implement Mode 3 (Basic) fallback (Task 217)
5. Add mode indicator UI (Task 218)
6. Add Mode 3 warning banner
7. Refactor app.js to use storage adapter (Task 219)
8. Testing for each mode (Tasks 220-222)

**Phase 5 (Service Worker)**: Independent track, can be implemented in parallel

---

## Ready for Spec Update

We've answered all 12 questions with clear decisions. The design agent can now:

1. Update `docs/chaptr-spec-sync-addendum.md` with these clarifications
2. Add the new sections (Mode indicator UI, warning banner, console logging)
3. Confirm implementation approach for Phase 5

**All architectural decisions are locked in and ready for implementation.**

---

**Document Status**: ✅ Complete - All questions answered
**Next Step**: Design agent updates spec addendum with these decisions
**Implementation**: Phase 5 tasks (213-222) can proceed after spec update
