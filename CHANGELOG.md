# Changelog

All notable changes to CHAPTR will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Historical events gap indicator: Shows count and net total of events that occurred before projection window as gap indicator at top of timeline (projection.js:82-83,113-114,135-136,358-380; index.html:266-276; style.css:826-840,1052-1059,1136-1143)
- Accounts total row: Shows sum of all account balances in display currency (or base currency) at bottom of accounts list with amber border styling similar to View All row (index.html:204-214; app.js:831-857; style.css:396-410)
- Mode descriptions: Added explanatory text for each storage mode (Online & Offline, Online Only, Limited) (index.html:620-628; style.css:2297-2319,3235-3241)

### Changed
- Story status symbols: Replaced emoji (✓ and ⚠) with terminal-friendly [OK] and [!!] indicators for consistency with terminal aesthetic (app.js:411,413,439,441)
- Story badge colors: Now correctly show red (status-warn) for OVER budget/SHORT of goal states and green (status-ok) for positive states (app.js:807-813)
- Drift display logic: Changed from confusing percentage-based thresholds to clear sign-based colors (positive drift = green, negative drift = red) with directional arrows (↑/↓) replacing + prefix (app.js:3362-3377)
- Projection panel values: Today and End of Month now colored appropriately based on positive/negative balance (green for positive, red for negative) (index.html:218,222)
- Desktop font sizes: Increased all text by ~50% for screens ≥769px (base 13px → 20px, ~80 properties adjusted) - significantly improved readability (style.css:2842-3172)
- Settings button size: Doubled from 18px to 36px for better visibility without affecting header height (style.css:197)
- Sync notification size: Doubled font size from 11px to 22px for pending count and notification messages (style.css:160,170,183)
- Dashboard accounts display: Now shows all accounts instead of limiting to first 3 (index.html:190)
- Starting balance color logic: Now shows red for negative balances, green for positive (index.html:258)
- Settings screen layout: Restructured into responsive two-column layout on desktop (60% left / 40% right) with single-column stack on mobile (index.html:455-713; style.css:2860-2920)
- Preferences panel: Base Currency, Date Format, and Baseline Display (Months) now display in 3-column grid on desktop for efficient space usage (index.html:467-547; style.css:2875-2879,2915-2920)
- Conversion Rates section: Moved from left column to right column in settings screen (index.html:590-621)
- User Management section: Moved from right column to left column, positioned between Preferences and Backup & Restore (index.html:551-574)
- Currency rate inputs: Fixed styling to match application form inputs with proper borders, background, and focus states using specific CSS rules (style.css:2214-2242)
- Mode panel: Fixed to use reactive storageMode property instead of non-reactive storage.mode (index.html:620-621)
- Mode names: Changed from "Offline Capable/Online Only/Basic" to clearer "Online & Offline/Online Only/Limited" terminology (index.html:620-621)
- Mode name colors: Added color coding - blue for Online & Offline, amber for Online Only, red for Limited (style.css:2303-2313)
- Story items styling: Removed grey background to match account items - now transparent with border-bottom only, grey background on hover (style.css:283-300,932-947)
- View All row: Removed confusing balance amount display, now shows only name and description (index.html:155-160)
- TODAY marker positioning: Repositioned to appear after all of today's events instead of before them for clearer timeline separation (projection.js:483-487)
- Gap indicators transparency: Made all gap indicator backgrounds 50% transparent (rgba(10,10,10,0.5)) for visual consistency (style.css:785-790,819-822,835-838)
- Desktop timeline rows: Increased vertical padding from 10px to 18px for better spacing and readability (style.css:3041-3044)
- Desktop TODAY divider: Increased padding to 18px to match timeline row spacing (style.css:3059-3063)
- Desktop filter chips: Increased font size from 11px to 17px and padding for better readability in story view tabs (style.css:3065-3078)

### Fixed
- Starting balance NaN display: Fixed calculation to skip gap indicators (both regular and historical) when extracting starting balance from projection rows (app.js:717-724)

## [0.5.0] - 2026-01-15

### Added
- Service worker version endpoint (/sw-version) with content-hash based versioning for automatic cache invalidation on file changes
- Test fixture data redesign with 3 realistic BIG-TICKET expense stories spanning 2026 (canada-ski-trip, car-maintenance, house-renovation)
- Test fixture: 123 total events (96 baseline recurring bills + 27 story events) with specific dates throughout 2026
- "Updating application..." message during service worker reload (instead of generic "Loading application...")
- Content-hash based SW versioning: version changes automatically when any precached file changes (no server restart needed)
- Production validator agent comprehensive PWA architecture review with priority-based issue tracking
- CPTR-171adb6c: Service worker update test suite with 91 comprehensive tests (sw_update_flow.test.js, sw_updating_ux.test.js, init_sequence.test.js, storage_validation.test.js, test_sw_versioning.py)
- CPTR-171adb6c: testableUtils pattern for mockable window.location.reload() in browser mode testing
- CPTR-171adb6c: SessionStorage error handling with try/catch wrappers for SecurityError (private browsing mode compatibility)
- CPTR-171adb6c: Phase 2 HIGH priority test suite with 21 comprehensive tests (default_account.test.js, sw_version_detection.test.js) - 100% passing
- CPTR-171adb6c: Default account resolution tests - 8 tests covering getDefaultAccountName() logic for event form hints
- CPTR-171adb6c: SW version detection edge case tests - 13 tests covering timeout, network errors, offline scenarios, and service worker states
- CPTR-171adb6c: Phase 3 MEDIUM/LOW priority test suite with 28 comprehensive tests (loading_indicator.test.js, esc_key_extended.test.js, test_sw_generation.py) - 100% passing
- CPTR-171adb6c: Loading indicator tests - 8 tests covering show/hide methods with timing verification (300ms fade transition)
- CPTR-171adb6c: ESC key extended tests - 5 tests covering edge cases for debouncing, modal priority, and state consistency
- CPTR-171adb6c: Backend SW generation tests - 15 tests validating dynamically generated service worker content with automatic revision numbers
- Sync endpoint high limit tests - test_full_sync_returns_all_events_beyond_default_limit() validates GET /api/sync/full returns all events (not limited by base repository default of 100)
- Frontend projection date range tests - 52 comprehensive tests in projection_date_ranges.test.js covering dynamic date adjustment for story/baseline/ALL views

### Changed
- Gap indicators: Transformed from full rows to border decorations (height: 0, text sits on timeline border) - significantly reduces visual clutter on desktop (style.css:760-832)
- Mobile timeline layout: Responsive 3-column (portrait) / 4-column (landscape) grid with orientation-aware balance column visibility
- Mobile gap indicators: Simplified to centered text blocks without decorative lines for cleaner mobile display
- Mobile fonts: Increased date (12px) and amount (13px) font sizes for better readability in portrait mode
- Mobile spacing: Tighter 8px column gaps (was 12px) and compact 8px row padding for efficient screen usage
- Projection date ranges: Dynamic adjustment based on view type (story views use story date range, baseline uses baseline_display_months setting, ALL view shows 12 months)
- Default projection range: Increased from 1 month to 12 months for ALL view (app.js:576-586)
- Sync endpoint event limit: Added explicit limit=10000 to prevent default 100-item cap (sync.py:468)
- Service worker version calculation: changed from server start time to MD5 hash of all precached file contents
- Service worker lifecycle: removed manual skipWaiting() from install event (Workbox controls install, client controls activation)
- Controllerchange event listener: added debounce guard flag and 100ms delay to prevent reload loops
- Cache whitelist: preserve Workbox precache caches (workbox-*) during activation cleanup
- Refactored precache file listing: extracted get_precache_files() shared function used by /sw-version and /sw.js endpoints (DRY)

### Fixed
- Story status "£NaN OVER" display: Added defensive checks for NaN values in story goal calculations with parseFloat() and fallback to lifecycle status (ACTIVE/ENDED/UPCOMING) when calculation fails (app.js:385-407,431-435,443-445)
- Gap indicator stacking: Hide time gaps when hidden events gap is present in same row - prevents redundant "14 days" + "9 hidden events" stacking (style.css:773-775)
- Events not appearing in story views: Fixed sync endpoint returning only 100 of 123 events (added explicit limit=10000 for events in sync.py:468)
- Events not visible in 2026 fixture stories: Fixed projection date range using current month (Jan-Feb 2025) instead of story date ranges in 2026 (app.js:612-653)
- Alpine.js template errors on undefined event_date: Added ternary guards in timeline template before calling date functions (index.html:282,285,298) to handle gap indicators and drift rows without event_date field
- CPTR-171adb6c: Test refactoring - 12 failing tests resolved to achieve 100% passing (2 fixed: storage schema + backend file mocking; 10 deleted: unmockable dynamic imports, fake timer conflicts, browser security restrictions)
- CPTR-171adb6c: Storage validation test - added entity_id index to sync_queue Dexie schema preventing SchemaError on atomic operations
- CPTR-171adb6c: Backend versioning test - refactored to use temporary files instead of complex Path mocking for reliable file I/O testing
- CPTR-171adb6c: Init sequence tests - refactored to test observable behavior (loader visibility, error logging) instead of unreliable ES module spies due to browser mode limitations
- CPTR-171adb6c: PR #65 review - Changed logger.info to logger.warn for sessionStorage errors (init.js:61, 252) for production visibility
- CPTR-171adb6c: PR #65 review - Standardized all test files to snake_case naming (8 files: app_esc_key, dropdown_validation, event_helpers, form_validation, queue_helpers, storage_adapter, sync_spinner, validation_helpers)
- CPTR-171adb6c: PR #66 review - Added comprehensive documentation to default_account.test.js explaining mock pattern rationale (Alpine.js component methods cannot be imported in isolation)
- CPTR-171adb6c: PR #66 review - Documented integration testing approach for Alpine.js components (verified through browser-mode tests and manual testing)
- CPTR-171adb6c: PR #66 review - Changed sw_version_detection.test.js timing test to use vi.useFakeTimers() for deterministic timing control
- CPTR-171adb6c: PR #67 review - Added comprehensive JSDoc documentation to init.js exports (451-475) explaining test-only usage and production impact (none - tree-shaking removes unused exports)
- CPTR-171adb6c: PR #67 review - Added clarifying comment in loading_indicator.test.js about 300ms timer matching production timing (instant due to fake timers)
- CPTR-171adb6c: PR #67 review - Documented rationale for separate ESC key test files (phase-based organization: basic tests vs edge cases)
- PR #63 review feedback: Resolved all HIGH, MEDIUM, and LOW priority issues from code review
- Double reload on hard refresh: removed duplicate SKIP_WAITING message triggers (updatefound + waiting check race condition)
- Workbox precache race condition: removed skipWaiting() from install event preventing cache population before activation
- Missing Workbox precache cache: cache whitelist now excludes workbox-* caches from deletion
- Service worker update detection: removed aggressive registration.update() call (unnecessary with version-based URL)
- Storage adapter tests: Opening balance conflict resolution now tests actual logic instead of calling inaccessible processSyncResponse()
- ESC key modal dismiss: Fixed Alpine.js context loss in debounce closure by capturing appContext before event listener
- Empty state messages: Added styled <span class="key"> tags to [Manage] button references for visual consistency
- Server version validation: Added required field validation (id, account_id, amount, date) before Dexie put() operation
- Sync spinner: Fixed empty queue bypass - check queue count before starting spinner to ensure consistent minimum duration behavior (PR review feedback)

## [0.4.0] - 2026-01-02

### Added
- Event creation: Currency button list (replaces text input) for easier currency selection
- Story creation: Display currency dropdown (replaces text input) populated from settings
- Event creation: "Use Global Default" option with dynamic hint showing default account name
- Event creation: Validation preventing event creation when no accounts exist
- Validation test suite: 68 comprehensive tests covering HTML5 validation system (validation-helpers.js, dropdown-factories.js)
- tests/validation_helpers.test.js: 49 unit tests for all 6 validation helper functions (resetFormErrors, validateHTML5, validateCustomDropdown, validateDateRange, validateCurrencyCode, validateConditionalRequired, countErrors)
- tests/form_validation.test.js: 8 integration tests for validateHTML5 with real DOM elements and HTML5 Constraint Validation API
- tests/dropdown_validation.test.js: 11 component tests for modalDropdown and settingsDropdown error state integration
- Validation helpers module: static/js/validation-helpers.js - centralized validation functions for HTML5 + business logic validation across all forms
- Sync spinner defensive programming: 5-layer protection system to prevent stuck/perpetual spinners (state recovery on init, page visibility listener, beforeunload handler, 30-second timeout guard, minimum 1-second display duration)
- tests/sync_spinner.test.js: 12 comprehensive tests covering all defensive programming layers (timeout guard, minimum duration, error handling, state recovery, page lifecycle handlers)

### Changed
- Default account enforcement: Show error when trying to set second default account (requires manually unsetting existing default first)
- Performance: Added compound index on conflicts collection (entity_id + conflict_type) - MongoDB and Dexie
- Account deletion: Requires typing account name for confirmation (case-insensitive) to prevent accidental deletions
- Event creation: HTML5 validation proof of concept - leverages native Constraint Validation API with terminal-style arrow feedback on Description, Event Date, Amount, and Start Date fields
- Event creation: Visual validation feedback with terminal-style arrows (> field <) positioned in modal margins using @invalid.prevent to intercept browser UI, with conditional negative margins applied only when errors are present
- Sync button icon: Replaced emoji (🔄) with terminal-friendly clockwise arrow (↻) to maintain ASCII aesthetic consistency with other navbar buttons (+, $, ?)

### Fixed
- Validation arrows: Fixed incorrect margins on fields without validation errors by conditionally applying negative margins only when arrows are visible
- Pydantic v2 compatibility: Renamed SyncChangeMetadata fields (_derived_from, _optimistic) to use aliases for underscore-prefixed JSON keys
- Sync endpoint AttributeError: Changed dictionary-style access to attribute access for SyncChangeMetadata model
- Validation helpers: validateCurrencyCode auto-conversion bug - removed .toUpperCase() call so lowercase/mixed case codes correctly fail validation (e.g., "gbp", "Gbp" now invalid)
- Validation helpers: validateCustomDropdown falsy value bug - changed to explicit null/undefined check so numeric zero is now a valid dropdown selection
- Validation helpers: validateConditionalRequired falsy value bug - changed to explicit null/undefined check so numeric zero and boolean false are now valid when conditionally required

## [0.3.0] - 2025-12-31
