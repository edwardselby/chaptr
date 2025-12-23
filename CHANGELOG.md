# Changelog

All notable changes to CHAPTR will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- CPTR-6969cf85: Accounts screen with CRUD operations (create, edit, delete accounts with validation)
- CPTR-6969cf85: Settings screen with admin-only access (user management, preferences, conversion rates, backup/restore)
- CPTR-6969cf85: Command bar with context-sensitive actions (+ Event/Account, $ Balance/Funding, 🔄 Sync, ? Help)
- CPTR-6969cf85: Account modal with validation (name, currency, balance, default flag)
- CPTR-6969cf85: User management modal for admin users (username, admin flag editing)
- CPTR-6969cf85: Backup/restore functionality with JSON download/upload and validation
- CPTR-6969cf85: Pending sync UI indicator (amber badge in header showing queued changes count, clickable to trigger sync)
- CPTR-6969cf85: Auto-retry on network reconnection (window 'online' event listener triggers sync if queue not empty)
- CPTR-817e6e17, CPTR-3e40d90a, CPTR-30f74f13, CPTR-bbb22028, CPTR-58ee8f5e: Comprehensive sync integration test suite (test_sync_integration.py) with 5 tests covering multi-client sync, conflict detection, stale client recovery, and recurring events
- CPTR-2c99cc6d, CPTR-2b2f2374: Manual sync testing guide (docs/sync-manual-testing-guide.md) with curl commands for validation
- Taskwarrior tasks for real MongoDB integration test suite upgrade (Tasks 223-226)
- Task 223 (CPTR-298): Real MongoDB fixtures (mongodb_real, clean_database_real, test_app_real, async_client_real) for complex integration tests
- Task 223: Worker-based database naming (chaptr_test_integration_{worker_id}) for parallel test isolation
- Task 223: pytest.ini integration marker for separating integration tests from unit tests
- Task 223: Comprehensive fixture selection guide in conftest.py documenting when to use mongomock vs real MongoDB

### Changed
- CPTR-cfce2518, CPTR-57034d01, CPTR-5c895d99 (Tasks 224-226): Migrate integration tests to real MongoDB - 17/17 passing (all tests migrated successfully)
- CPTR-6969cf85: Navigation aligned with mockup design (removed icon-based tab bar, added MANAGE and VIEW ALL action buttons)
- CPTR-6969cf85: Command bar styling updated to match mockup (grid layout, background/borders on buttons, proper spacing)
- CPTR-6969cf85: Account resolution hierarchy implemented (user-selected → story default → global default)
- CPTR-6969cf85: Event rate_to_base calculation changed to lookup from settings.rates[currency] instead of account field
- CPTR-6969cf85: Account update changed from partial db.update() to full db.put() to preserve all server fields
- CPTR-6969cf85: Removed last_updated field from accounts (using only updated_at per spec)
- CPTR-6969cf85: Alpine.js initialization fixed (removed explicit x-init to prevent double initialization)
- CPTR-817e6e17, CPTR-3e40d90a, CPTR-30f74f13, CPTR-bbb22028, CPTR-58ee8f5e: User-aware test fixtures (sample_account_with_user, sample_story_with_user, etc.) to match JWT authentication context
- CPTR-817e6e17, CPTR-bbb22028, CPTR-58ee8f5e: Three complex integration tests marked as skipped pending real MongoDB migration (Tasks 223-226)
- CPTR-817e6e17 to CPTR-2b2f2374: Deprecated datetime.utcnow() replaced with timezone-aware datetime.now(timezone.utc) in all tests
- Test suite documentation updated to indicate mongomock limitations for change_log query simulation

### Fixed
- CPTR-6969cf85: JavaScript syntax error (missing comma after editFunding method)
- CPTR-6969cf85: Command bar class name mismatch (HTML used .cmd-btn, CSS expected .command-btn - reverted to .cmd-btn per mockup)
- CPTR-6969cf85: Backup restore validation added (10MB file size limit, comprehensive schema validation for version, arrays, field types)
- CPTR-6969cf85: Currency input auto-uppercase (added text-transform: uppercase CSS)
- CPTR-6969cf85: Sync queue count tracking (updates after CRUD operations and successful API syncs)
- CPTR-817e6e17: User context mismatch resolved (created_by=None vs JWT user) via user-aware fixtures
- CPTR-817e6e17: Stale client false positive resolved (timestamp strategy changed from "very old" to "before earliest change_log entry")

## [0.0.6] - 2025-12-22

### Added
- CPTR-6969cf85: Frontend foundation - HTML shell with Alpine.js structure (Dashboard, Projection, Accounts, Settings screens)
- CPTR-6969cf85: Terminal aesthetic CSS with #4af626 green on #000 black, JetBrains Mono font, scanline overlay effect
- CPTR-6969cf85: PWA manifest.json for mobile installation
- CPTR-6969cf85: Utility functions (formatCurrency, formatDate, API request wrapper with JWT auth)
- CPTR-6969cf85: Alpine.js reactive state management (navigation, data loading, projection state)
- CPTR-6969cf85: Dexie.js IndexedDB schema (9 tables: accounts, stories, events, recurring_rules, users, settings, conflicts, sync_queue, sync_meta)
- CPTR-6969cf85: Dashboard screen (stories list with status, accounts quick view, projection summary)
- CPTR-6969cf85: Projection screen (filter chips, timeline, gap indicators, TODAY divider, currency toggle)
- CPTR-6969cf85: Client-side projection logic ported from Python (running balance calculation, gap detection, multi-currency conversion)
- CPTR-6969cf85: Data loading from backend (/api/sync integration, Dexie population, auto-sync on first load)
- CPTR-4ab09b87: Regression test suite for projection MongoDB bugs (6 tests: Decimal conversion, date queries, end-to-end integration)
- CPTR-b5002098, CPTR-22072224, CPTR-251d2d7e: Change logging foundation for sync - ChangeLogMixin in BaseRepository
- CPTR-b5002098, CPTR-22072224, CPTR-251d2d7e: Database indexes for change_log collection (sync_pull_idx, pruning_idx, client_filter_idx)
- CPTR-b5002098, CPTR-22072224, CPTR-251d2d7e: client_id parameter on all repository mutation methods
- CPTR-b5002098, CPTR-22072224, CPTR-251d2d7e: _get_user_id() helper in BaseRepository for DRY user extraction
- CPTR-b5002098: Change log pruning infrastructure (configurable retention via CHANGE_LOG_RETENTION_DAYS, default 31 days)
- CPTR-b5002098: APScheduler background scheduler with daily 2AM pruning job, graceful shutdown, and timeout protection
- CPTR-b5002098: Database index on change_log.changed_at for efficient pruning queries
- CPTR-3735f384, CPTR-0b7b3ed8, CPTR-b6c582ef: Recurring event generation utility (api/utils/recurring.py) with ±1 month window
- CPTR-3735f384: Recurring event generation uses dateutil.rrule for WEEKLY, MONTHLY, YEARLY frequencies
- CPTR-0b7b3ed8: Generated events include recurring_rule_id link to parent rule
- CPTR-b6c582ef: All generated events logged to change_log for sync distribution
- CPTR-2bd3eea9, CPTR-739bf665: Recurring rules repository client_id parameter and change logging
- CPTR-739bf665: Smart deletion logic removes only future unedited instances (MongoDB $expr query)
- CPTR-3735f384: Test suite for recurring event generation (8 tests: monthly, weekly, annual, duplicates, edited instances, end dates, multiple rules, empty rules)
- CPTR-e6875013, CPTR-59348847: Sync protocol models (SyncChange, SyncRequest, SyncConflict, SyncServerChange, SyncResponse, FullSyncResponse)
- CPTR-e6875013, CPTR-59348847: POST /api/sync endpoint with bidirectional push/pull phases and conflict detection
- CPTR-e6875013, CPTR-59348847: GET /api/sync/full endpoint for stale client recovery with user-filtered dataset
- CPTR-e6875013, CPTR-59348847: Conflict detection (edit_edit, delete_edit, business_rule) with base_updated_at timestamp comparison
- CPTR-e6875013, CPTR-59348847: Stale client detection with full_sync_required flag when last_sync_at older than oldest change_log entry

### Changed
- CPTR-b5002098, CPTR-22072224, CPTR-251d2d7e: All repositories log changes to change_log collection after create/update/delete operations
- CPTR-b5002098, CPTR-22072224, CPTR-251d2d7e: All route handlers pass client_id=None for backward compatibility with REST API
- CPTR-b5002098, CPTR-22072224, CPTR-251d2d7e: log_change() omits None values per MongoDB best practice (reduces document size)
- CPTR-b5002098: Main application startup integrates scheduler initialization and creates change_log indexes
- CPTR-b5002098: Pruning job uses configurable retention period from Settings
- CPTR-2bd3eea9, CPTR-739bf665: Recurring rules routes pass client_id=None to repository methods
- CPTR-3735f384: Recurring event generation fetches currency rates from settings for rate_to_base field
- CPTR-2bd3eea9: Edited instance preservation via existing instance check (updated_at != created_at detection)
- CPTR-e6875013, CPTR-59348847: Pull phase explicitly includes REST API changes (client_id=None) and other clients' changes via $or query
- CPTR-e6875013, CPTR-59348847: Full sync endpoint filters all entities by created_by field to prevent cross-user data leakage

### Fixed
- CPTR-4ab09b87: MongoDB Decimal128 to Python Decimal conversion in projection functions (7 locations) and API route (2 locations)
- CPTR-4ab09b87: MongoDB date query format changed from datetime.combine() to .isoformat() for string comparison (3 locations)
- CPTR-4ab09b87: MongoDB ObjectId serialization error by removing _id field from projection results (3 locations)
- CPTR-b5002098, CPTR-22072224, CPTR-251d2d7e: Replaced deprecated datetime.utcnow() with utc_now() for timezone-aware timestamps
- CPTR-e6875013, CPTR-59348847: Settings access in full sync uses get_or_create_default() singleton pattern
- CPTR-e6875013, CPTR-59348847: handle_update returns None for idempotency when entity already deleted by another client
- CPTR-e6875013, CPTR-59348847: FullSyncResponse.sync_timestamp type changed to datetime for consistency with SyncResponse


## [0.0.5] - 2025-12-22

### Added
- CPTR-10c5f82a: First user initialization CLI command (scripts/create_first_user.py) for production deployment
- CPTR-b0aa0ce, CPTR-08f102b, CPTR-43c55d2: Projection API endpoint (GET /api/projection) with view/date/warnings parameters and ProjectionResponse model
- CPTR-c289e6e8, CPTR-35bdc365, CPTR-e94133dc: Gap indicators for story projections showing hidden events between visible events
- CPTR-c289e6e8: Gap detection algorithm (O(n) single-pass) identifies hidden events between consecutive visible events
- CPTR-35bdc365: Cumulative delta calculation from hidden events with zero-delta skip logic
- CPTR-e94133dc: Currency conversion for gap deltas to story display_currency using current rates
- CPTR-c289e6e8: Gap metadata includes delta amounts, date range, hidden event count, and full event details for frontend expansion
- CPTR-c289e6e8: Trailing gap support for hidden events after last visible event (before_event_id = None)
- CPTR-6c1c33b5: Comprehensive warning detection tests (boundary cases, recovery scenarios, message validation, multi-warnings, first/last event edge cases, baseline exclusion)
- CPTR-9e215810: Story filtering with gap indicators tests (all funding modes, only hypothetical events, currency conversion, multiple gaps)
- CPTR-810f2678: Projection edge case tests (empty data, zero balance, date ranges, missing fields, extreme values, graceful degradation)

### Fixed
- CPTR-43c55d2: Projection API type mismatch resolved (core returns list, endpoint now wraps in ProjectionResponse)
- CPTR-43c55d2: Projection API starting_balance calculation (sum of account balances in base currency)
- CPTR-43c55d2: Story not found handling returns 404 instead of empty response


## [0.0.4] - 2025-12-22

### Added
- CPTR-b51e353d, CPTR-12cbb670: User authentication endpoints (POST /auth/login, GET /auth/me)
- CPTR-eb629103: Role-based authorization (admin/user) with get_current_user and get_current_admin_user dependencies
- CPTR-eb629103: Authentication required for 13 GET/DELETE endpoints (accounts, stories, events, recurring-rules, settings)
- CPTR-9f154e89: ChangeLogEntry model with EntityType and ChangeAction enums for sync protocol
- CPTR-b51e353d: JWT authentication with HS256, bcrypt password hashing, 24-hour token expiration
- CPTR-b51e353d: AuthenticationError (401) and AuthorizationError (403) exception classes
- CPTR-eb629103: User tracking (created_by/updated_by) auto-populated from JWT tokens

### Changed
- CPTR-b51e353d: User model extended with password_hash and updated_at fields
- CPTR-eb629103: Settings PUT endpoint protected with admin-only authorization
- CPTR-eb629103: Event, Story, and RecurringRule endpoints integrate user tracking via current_user dependency
- CPTR-eb629103: All repositories accept current_user dict parameter for backward compatibility
- CPTR-eb629103: RecurringRule model extended with created_by/updated_by fields

### Fixed
- CPTR-b51e353d: SECRET_KEY validation at startup prevents production deployment with default key
- CPTR-b51e353d: Password strength validation requires uppercase, lowercase, and digit
- CPTR-b51e353d: Unique index on users.username enforces uniqueness and improves login performance
- CPTR-9f154e89: ChangeLogEntry.changed_by_client uses UUID type per spec v3.0 (was string)


## [0.0.3] - 2025-12-22

### Added
- CPTR-234: Account projection calculation with per-account running balance
- CPTR-5: Global balance negative warning detection (critical severity)
- CPTR-9: Per-account balance negative warning detection with account context
- CPTR-10, CPTR-11: Story goal warning detection (spend_up_to exceeded, end_with_at_least missed)

### Changed
- Warning messages now use story display_currency instead of hardcoded currency symbols
- Warning messages include detailed context (overspent/shortfall amounts with full breakdown)

### Fixed
- MockDB test fixture to support account_id filtering and _id lookups for account projection tests


## [0.0.2] - 2025-12-21

### Added
- CPTR-21, CPTR-47: Core projection foundation with global balance calculation and same-day event ordering
- CPTR-31, CPTR-32, CPTR-33, CPTR-44, CPTR-255, CPTR-257: Multi-currency conversion with locked rates and database query optimization
- CPTR-23, CPTR-24, CPTR-25: Story projections with three funding modes (projected, fixed, projected_plus) and hypothetical events
- CPTR-280 to CPTR-284: Account CRUD endpoints with is_default enforcement and soft delete
- CPTR-275 to CPTR-278: Story CRUD endpoints with cascade delete and validation
- CPTR-256 to CPTR-259: Recurring rules CRUD endpoints (event generation deferred to Phase 7)
- Event CRUD endpoints with 3-level account resolution and rate locking
- Repository pattern with BaseRepository and entity-specific repositories
- Database indexes on events collection for query performance
- Verification script for funding event architecture (scripts/verify_funding_logic.py)

### Changed
- CPTR-21, CPTR-47: Spec documentation - funding event architecture as single source of truth (lines 163-197, 488-507)
- CPTR-21, CPTR-47: Story projection uses earliest event query instead of hardcoded 5-year lookback
- CPTR-10: EventCreate model - account_id and rate_to_base optional (auto-resolved if not provided)
- CPTR-10: Event date field uses Pydantic aliases for spec compliance (alias='date')
- CPTR-11, CPTR-13: StoryUpdate and RecurringRuleUpdate models with cross-field validators
- CPTR-15: Settings.rates validator enforces precision (8 decimal places) and currency code format
- CPTR-10: Account balance_updated_at changed to optional for new accounts
- CPTR-14: User model extended with username and created_at fields
- CPTR-10 to CPTR-15: All Decimal fields add precision constraints (max_digits=19, decimal_places=4/8)

### Fixed
- CPTR-23, CPTR-24, CPTR-25: ValueError for unknown funding modes (fail-fast validation)
- CPTR-21, CPTR-47: Decimal encoding for JSON serialization in test suite
- CPTR-23, CPTR-24, CPTR-25: UUID string handling in story projection queries
- CPTR-23, CPTR-24, CPTR-25: Settings document validation (requires base_currency and rates)
- CPTR-23, CPTR-24, CPTR-25: Restored funding event creation per spec lines 163-182
- CPTR-23, CPTR-24, CPTR-25: Story filtering alignment with spec (visible vs hidden events)
- CPTR-31, CPTR-32, CPTR-33: Test assertions for multi-currency conversion accuracy
- CPTR-12: Missing ValidationError import in EventRepository


## [0.0.1] - 2025-12-19

### Added
- CPTR-1: Project directory structure: api, routes, core, tests
- CPTR-2: Python virtual environment with FastAPI, Motor, Pydantic, Pytest dependencies
- CPTR-3, CPTR-4: MongoDB connection configuration and health check endpoint
- CPTR-4: FastAPI application with CORS, lifespan management, OpenAPI docs
- CPTR-2, CPTR-3: Environment-based configuration with .env.example template
- CPTR-291: Route stubs for accounts, stories, events, sync (19 endpoints total)
- CPTR-290: Core module stubs for projection engine and reconciliation system
- CPTR-20: Pydantic model enums: FundingMode, GoalType, Frequency, UserRole, ConflictType
- CPTR-15: Settings Pydantic model with currency rates and preferences validation
- CPTR-14: User Pydantic model with role enum validation (minimal per spec, external auth assumed)
- CPTR-10: Account Pydantic model with three-tier pattern and field validation
- CPTR-13: RecurringRule Pydantic model with frequency and date validation (includes RecurringRuleUpdate)
- CPTR-11: Story Pydantic model with funding mode and goal validation (includes StoryUpdate validators)
- CPTR-12: Event Pydantic model with Pydantic alias for spec-compliant date field
- CPTR-42 to CPTR-44: Test framework stubs with pytest-asyncio

### Changed
- CPTR-12: Event model date field uses Pydantic alias to maintain spec compliance while avoiding type shadowing
- CPTR-12: Event models add ConfigDict for proper alias/serialization behavior
- CPTR-13: Added RecurringRuleUpdate model for partial updates with validators
- CPTR-11: Added business logic validators to StoryUpdate model (date range, funding, goal)
- CPTR-11: StoryUpdate documentation clarifies API-level validation requirements for partial updates
- CPTR-15: Added rate validation to SettingsUpdate model for consistency
- CPTR-15: Settings.rates validator enforces decimal precision (8 decimal places maximum)
- CPTR-10: Account balance_updated_at changed to optional (new accounts may not have initial timestamp)
- CPTR-14: User model extended with username and created_at for UI identity and proper user tracking
- CPTR-10 to CPTR-15: All Decimal fields add precision constraints (max_digits=19, decimal_places=4 for amounts, 8 for rates)
- CPTR-10 to CPTR-15: All full models define id/created_at/updated_at as required fields (generated by API layer in Phase 1.4)
- CPTR-11, CPTR-12: Story and Event created_by/updated_by fields changed to Optional (auth not implemented until Phase 1.5)
- CPTR-11: Removed StoryUpdate.validate_funding and validate_goal validators (cannot work in partial update context, validation moved to API layer)
- CPTR-12: Added Event baseline/story exclusivity validator (baseline events cannot have story_id)
- CPTR-15: Settings.rates validator now validates currency code format in dictionary keys (3 uppercase letters)
