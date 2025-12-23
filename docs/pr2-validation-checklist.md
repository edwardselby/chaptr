# Frontend PR2 Validation Checklist

**Purpose**: Verify all PR2 features work correctly and match mockup specifications

**How to test**: Open `http://localhost:5000` in browser after starting Flask server

---

## Task 82: Visual Regression Testing

Compare each screen against mockup (`docs/chaptr-v4-mockup.html`)

### Dashboard Screen
- [ ] Stories list displays correctly
  - [ ] Story name, date range, status visible
  - [ ] ✓/⚠ goal status indicators correct
  - [ ] Tap story opens projection view
- [ ] Accounts section shows all accounts
  - [ ] Currency, balance visible
  - [ ] [default] tag on default account
- [ ] Projection summary shows Today and End of Month
- [ ] Drift indicator visible and colored correctly
- [ ] Terminal aesthetic maintained (#4af626 on #000)

### Projection Screen
- [ ] Filter chips visible at top
  - [ ] ALL, Baseline, Story filters
  - [ ] Active filter highlighted in green
- [ ] Currency toggle visible (ALL view only)
  - [ ] Cycles through available currencies
- [ ] Projection header shows:
  - [ ] Title (view name)
  - [ ] Date range
  - [ ] Starting balance
- [ ] Timeline displays events correctly:
  - [ ] Date, description, amount, balance columns
  - [ ] Source tags: [baseline], [story name]
  - [ ] Positive amounts green, negative red
  - [ ] TODAY divider appears correctly
- [ ] Gap indicators show between events
  - [ ] "X days" text visible
  - [ ] Tap to expand shows date range
- [ ] End summary (if story with goal)

### Accounts Screen
- [ ] Account list shows all accounts
  - [ ] Name, currency, last updated, balance
  - [ ] [default] tag on default
  - [ ] ⚠ Pending reconciliation indicator (if applicable)
  - [ ] Tap card opens edit modal
- [ ] Projection vs Reality panel:
  - [ ] Accounts Total calculated correctly
  - [ ] Projected NOW from projection engine
  - [ ] Drift with color (green/amber/red)
  - [ ] Explanatory note when drift exists
- [ ] Projected Balances section:
  - [ ] Shows +1 week, +2 weeks, +1 month
  - [ ] Per-account cards
- [ ] + Add button opens modal

### Settings Screen
- [ ] Access denied for non-admin users
- [ ] Admin users see all sections:
  - [ ] User Management with user list
  - [ ] Preferences (currency, date format, baseline months)
  - [ ] Conversion Rates table with inline editing
  - [ ] Backup/Restore buttons
  - [ ] Sync Settings with last sync time

### Command Bar
- [ ] Context-sensitive labels:
  - [ ] Dashboard: + Event, $ Balance
  - [ ] Projection: + To Story, $ Funding
  - [ ] Accounts: + Account, $ Balance
  - [ ] Settings: + User, $ Settings
- [ ] 🔄 Sync button shows ⏳ when syncing
- [ ] ? Help button opens modal

### Tab Navigation
- [ ] 4 tabs at bottom (Dashboard, Projection, Accounts, Settings)
- [ ] Active tab highlighted green
- [ ] Tapping tab switches screen

---

## Task 83: Projection Calculation Accuracy

Verify client-side projection matches server-side results

### Test Setup
1. Create test data via API:
   - 2 accounts (GBP and USD)
   - 1 baseline story with 5 events
   - 1 active story with 3 events
2. Note server projection result: `GET /api/projection?view=all&start=YYYY-MM-DD&end=YYYY-MM-DD`
3. Note client projection result: Dashboard > Projection view

### Checks
- [ ] Starting balance matches (sum of account balances)
- [ ] Event order matches (date ASC, amount DESC, created_at ASC)
- [ ] Running balance calculation matches at each step
- [ ] Final balance matches server result (within 0.01 tolerance)
- [ ] Currency conversion correct when display currency changed
- [ ] Baseline-only filter shows correct events
- [ ] Story filter shows story + baseline events

### Test Case: Same-Day Ordering
Create 3 events on same date:
- Event A: +£1000 (income)
- Event B: -£50 (expense)
- Event C: +£500 (income)

Expected order: A, C, B (income first, then by created_at)

- [ ] Client projection shows correct order
- [ ] Server projection shows correct order
- [ ] Orders match

---

## Task 84: Filter Chips Functionality

Test all projection view filters

### Filter: ALL
- [ ] Tap ALL chip highlights it green
- [ ] Shows all non-hypothetical events (baseline + stories)
- [ ] Currency toggle visible
- [ ] Changing currency updates all amounts

### Filter: Baseline
- [ ] Tap Baseline chip highlights it
- [ ] Shows only is_baseline=true events
- [ ] Currency toggle hidden
- [ ] Timeline title shows "Baseline"

### Filter: Story (e.g., "Canada Trip")
- [ ] Tap story chip highlights it
- [ ] Shows story events + baseline events
- [ ] Currency toggle hidden
- [ ] Timeline title shows story name
- [ ] Starting balance reflects story funding mode:
  - [ ] projected: Uses calculated balance on start date
  - [ ] fixed: Uses funding_amount
  - [ ] projected_plus: Uses calculated + adjustment

### Filter Switching
- [ ] Switching between filters updates timeline immediately
- [ ] No console errors during filter changes
- [ ] Projection rows recalculate correctly
- [ ] Gap indicators update for new timeline

---

## Task 85: Gap Indicators Expand/Collapse

Test gap indicator interaction

### Setup
Create timeline with gaps:
- Event on Jan 1
- Event on Jan 15 (14 day gap - should show indicator)
- Event on Jan 17 (2 day gap - should NOT show)
- Event on Feb 1 (15 day gap - should show indicator)

### Collapsed State (default)
- [ ] Gap row appears between Jan 1 and Jan 15
- [ ] Shows "14 days" text
- [ ] Dotted line separator visible
- [ ] Gap row appears between Jan 17 and Feb 1
- [ ] Shows "15 days" text

### Expanded State
- [ ] Tap first gap row
- [ ] Expands to show: "Jan 01 → Jan 15"
- [ ] Date range format matches mockup
- [ ] Tap again collapses back to "14 days"
- [ ] Other gaps remain in collapsed state

### Multiple Gaps
- [ ] Can expand multiple gaps simultaneously
- [ ] Each gap tracks its own state independently
- [ ] Switching filters resets all gaps to collapsed

### Threshold
- [ ] Gaps ≤ 7 days: No indicator shown
- [ ] Gaps > 7 days: Indicator shown
- [ ] Threshold constant: 7 days (from projection.js:190)

---

## Additional Validation

### Modal Interactions
- [ ] Account modal: Add account works
- [ ] Account modal: Edit account works
- [ ] Account modal: Delete account shows confirmation
- [ ] Account modal: Form validation (3-letter currency)
- [ ] Help modal: Opens and closes correctly
- [ ] Settings modals: User management (if admin)

### CRUD Operations (Online Mode)
- [ ] Create account: Shows immediately in list
- [ ] Edit account: Changes persist after reload
- [ ] Delete account: Removed from list (archived)
- [ ] Network tab shows API calls: POST/PUT/DELETE

### CRUD Operations (Offline Mode)
1. Disconnect network (browser dev tools)
2. [ ] Create account: Still works (queued)
3. [ ] Edit account: Still works (queued)
4. [ ] Check Dexie sync_queue table: Changes queued
5. Reconnect network
6. [ ] Trigger sync: Queue processes
7. [ ] Changes appear on server

### Error Handling
- [ ] Create account without name: Form validation prevents
- [ ] Delete story with events: Confirmation shows count
- [ ] Offline API failure: Graceful degradation (no crashes)
- [ ] Console shows "queued for sync" messages when offline

### Performance
- [ ] Dashboard loads quickly (< 500ms)
- [ ] Projection timeline renders smoothly
- [ ] Filter switching is instantaneous
- [ ] No janky animations or lag

---

## Browser Compatibility

Test in multiple browsers:
- [ ] Chrome/Edge (latest)
- [ ] Firefox (latest)
- [ ] Safari (if available)
- [ ] Mobile Chrome (iPhone/Android)

---

## Regression Checks

Ensure PR1 features still work:
- [ ] Dashboard displays correctly
- [ ] Projection view renders
- [ ] Command bar navigation works
- [ ] No JavaScript console errors
- [ ] Dexie database loads
- [ ] Settings initialized correctly

---

## Pass Criteria

**PR2 is ready for merge when:**
1. ✅ All visual regression checks pass
2. ✅ Projection calculations match server (within 0.01)
3. ✅ All filter chips work correctly
4. ✅ Gap indicators expand/collapse properly
5. ✅ CRUD operations work online and offline
6. ✅ No console errors in any view
7. ✅ Modals open/close correctly
8. ✅ Tested in at least 2 browsers

---

**Validation Date**: _____________
**Tester**: _____________
**Result**: ☐ PASS  ☐ FAIL (see notes below)

**Notes**:
