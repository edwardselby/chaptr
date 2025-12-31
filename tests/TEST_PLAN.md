# CHAPTR Frontend Test Plan

**Purpose:** Comprehensive testing of all "low hanging fruit" - fundamental functions with simple, testable logic.

**Status:** 55/55 base tests passing ✅

---

## ✅ Already Tested

### `tests/utils.test.js` (32 tests)
- ✅ `formatCurrency()` - 7 tests (positive, negative, symbols, rounding, edge cases)
- ✅ `toLocalISODate()` - 3 tests (format, padding, leap years)
- ✅ `formatDate()` - 4 tests (formatting, Date objects, null handling, invalid dates)
- ✅ `formatDateRange()` - 2 tests (ranges, empty strings)
- ✅ `daysBetween()` - 6 tests (calculations, boundaries, edge cases)
- ✅ `colorForAmount()` - 3 tests (positive, zero, negative)
- ✅ `generateUUID()` - 4 tests (format, uniqueness, length, bulk generation)
- ✅ `parseISODate()` - 2 tests (parsing, midnight handling)

### `tests/db.test.js` (23 tests)
- ✅ Database initialization
- ✅ CRUD operations (accounts, events, stories)
- ✅ Sync queue operations
- ✅ Complex transactions
- ✅ Helper functions (getStoryEvents, queueChange)
- ✅ IndexedDB features (bulk operations, atomic transactions)

---

## 🎯 High Priority - Add Tests

### `tests/event-helpers.test.js` (NEW FILE - 0 tests)

**Pure functions for event data creation:**

1. **`calculateRateToBase(currency, settings)`**
   - ✅ Same currency as base → returns 1.0
   - ✅ Currency with rate in settings → returns correct rate
   - ✅ Currency without rate → returns 1.0 fallback
   - ✅ Null/undefined settings → returns 1.0 fallback

2. **`createOpeningBalanceEventData(account, settings)`**
   - ✅ Creates event with correct fields
   - ✅ Zero balance → returns null
   - ✅ Negative balance allowed
   - ✅ Sets is_opening_balance = true
   - ✅ Sets is_transfer = false
   - ✅ Inherits is_baseline from account

3. **`createRecurringInstanceData(rule, date, settings, isBaseline)`**
   - ✅ Creates event with correct fields
   - ✅ Links to recurring_rule_id
   - ✅ Sets story_id = null
   - ✅ Respects isBaseline parameter
   - ✅ Sets is_transfer = false

4. **`generateInstancesForWindow(rule, windowDays, settings, isBaseline)`**
   - ✅ Weekly rule generates correct dates (Monday = 1, Sunday = 7)
   - ✅ Monthly rule generates correct dates (day of month)
   - ✅ Annual rule generates correct dates (month + day)
   - ✅ Respects rule start_date
   - ✅ Respects rule end_date
   - ✅ Returns empty array if rule outside window
   - ✅ Generates 4-5 instances for weekly rule in 30-day window
   - ✅ Generates 1 instance for monthly rule in 30-day window

---

## 🎯 Medium Priority - Add Tests

### `tests/projection.test.js` (NEW FILE - 0 tests)

**Pure calculation functions:**

1. **`convertToBaseCurrency(amount, rateToBase)`** (internal function - export for testing)
   - ✅ Amount * rate calculation
   - ✅ Rounds to 2 decimal places
   - ✅ Negative amounts
   - ✅ Rate = 1.0 (no conversion)

2. **`convertFromBaseCurrency(baseAmount, displayCurrency, baseCurrency, rates)`** (internal - export)
   - ✅ Same currency → returns baseAmount
   - ✅ Different currency → applies rate
   - ✅ Missing rate → uses 1.0 fallback
   - ✅ Rounds to 2 decimal places

---

## 🎯 Low Priority - Add Tests

### `tests/utils.test.js` (ADD 3 MORE TESTS)

**Untested utils.js functions:**

1. **`isToday(dateStr)`**
   - ✅ Today's date → true
   - ✅ Yesterday → false
   - ✅ Tomorrow → false
   - ✅ Invalid date → false

2. **`isPast(dateStr)`**
   - ✅ Yesterday → true
   - ✅ Today → false (boundary case)
   - ✅ Tomorrow → false
   - ✅ Last year → true

3. **`getModeAwareErrorMessage(mode, operation)`**
   - ✅ 'full' mode → "Failed to X. Changes queued for sync."
   - ✅ 'sync-only' mode → "Failed to X. Please check connection and try again."
   - ✅ 'basic' mode → "Failed to X. Refresh and retry."
   - ✅ Unknown mode → "Failed to X."

---

## ⏭️ Skip Testing (Side Effects or Trivial)

**Not worth testing:**
- `getClientId()` - async localStorage, tested in integration
- `apiRequest()` - HTTP requests, tested in integration
- `storeToken()` / `getToken()` / `clearAuth()` - localStorage side effects
- `isAuthenticated()` - trivial wrapper
- `showToast()` - DOM manipulation
- `formatRelativeTime()` - uses timestamps with time component (already correct)

---

## 📊 Test Coverage Goals

**Current Coverage:**
- utils.js: ~70% (32/45 functions tested)
- db.js: ~85% (23 tests covering most operations)
- event-helpers.js: 0% (NEW - needs tests)
- projection.js: 0% (pure functions need extraction + tests)

**Target Coverage:**
- utils.js: 85%+ (add 3 more test suites)
- db.js: 85%+ (current coverage good)
- event-helpers.js: 90%+ (test all 4 exported functions)
- projection.js: 60%+ (test 2 pure calculation functions)

---

## 🚀 Implementation Order

1. **High Priority:** `tests/event-helpers.test.js` (~25 tests)
   - Core business logic for event creation
   - Pure functions - easy to test
   - Recurring event logic needs validation

2. **Medium Priority:** `tests/projection.test.js` (~8 tests)
   - Currency conversion accuracy critical
   - Need to export internal functions for testing

3. **Low Priority:** Expand `tests/utils.test.js` (~10 more tests)
   - Fill gaps in existing coverage
   - Nice-to-have sanity checks

---

## ✅ Success Criteria

- All new tests passing
- No regression in existing tests
- Test suite runs in <5 seconds
- Clear test descriptions
- Edge cases covered (null, undefined, invalid input)
- 100% of exported pure functions tested
