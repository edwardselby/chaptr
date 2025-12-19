# Changelog

All notable changes to CHAPTR will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Phase 1.4 Foundation: Repository pattern and utilities
  - Custom exceptions: ResourceNotFoundError, ResourceConflictError, ValidationError
  - Database helpers: UUID conversion, timestamps, account resolution, rate locking
  - BaseRepository with generic CRUD operations
- CPTR-284: GET /api/accounts endpoint with include_archived query parameter
- CPTR-283: GET /api/accounts/{id} endpoint
- CPTR-282: POST /api/accounts with is_default enforcement (first account auto-sets default)
- CPTR-281: PUT /api/accounts/{id} with pending_reconciliation on balance update
- CPTR-280: DELETE /api/accounts/{id} as soft delete (archive) with default account protection
- AccountRepository with business logic for is_default enforcement and archiving
- CPTR-278: GET /api/stories endpoint with sort by start_date DESC
- CPTR-277: GET /api/stories/{id} endpoint
- CPTR-276: POST /api/stories with funding/goal validation and default_account_id verification
- CPTR-275: PUT /api/stories/{id} with merge-then-validate pattern for cross-field validation
- DELETE /api/stories/{id} with CASCADE delete to events (destructive, permanent)
- StoryRepository with merge-then-validate for partial updates and cascade delete
- GET /api/events endpoint with filtering (story_id, account_id, date_from, date_to) and same-day ordering
- GET /api/events/{id} endpoint
- POST /api/events with 3-level account resolution hierarchy and currency rate locking
- PUT /api/events/{id} with auto-adjustment protection
- DELETE /api/events/{id} with auto-adjustment protection
- EventRepository with account resolution, rate locking, and same-day ordering (date ASC, amount DESC, created_at ASC)
- CPTR-6: GET /api/settings endpoint with singleton pattern (creates defaults if none exist)
- PUT /api/settings endpoint for admin-only configuration updates
- SettingsRepository with get_or_create_default and update_singleton methods
- CPTR-256: GET /api/recurring-rules endpoint
- CPTR-257: POST /api/recurring-rules with account validation and frequency/day relationship validation
- CPTR-258: PUT /api/recurring-rules/{id} for partial updates (note: affects future events only per spec, event generation deferred to Phase 7)
- CPTR-259: DELETE /api/recurring-rules/{id} (note: removes future events per spec, event generation deferred to Phase 7)
- RecurringRuleRepository with account validation and CRUD operations (event generation ±1 month window deferred to Phase 7)
- Database indexes on events collection for query performance (event_date, story_id+event_date, account_id+event_date)

### Changed
- PR#5 Review Fixes Round 1: EventCreate model - account_id and rate_to_base now optional (auto-resolved if not provided)
- PR#5 Review Fixes Round 1: EventRepository.create() - only locks rate_to_base from settings if not explicitly provided
- PR#5 Review Fixes Round 1: Added database index creation on startup for events.event_date and composite indexes for filtering
- PR#5 Review Fixes Round 1: Verified RecurringRuleBase has frequency/day validation (already implemented)
- PR#5 Review Fixes Round 1: Verified StoryRepository has default_account_id validation (already implemented)
- PR#5 Review Fixes Round 2: Added account_id validation to EventRepository.update() - prevents reassigning to non-existent accounts
- PR#5 Review Fixes Round 2: Event date field uses Pydantic aliases (alias='date', serialization_alias='date') for spec compliance
- PR#5 Review Fixes Round 2: Rate locking behavior clarified in EventCreate docstring - auto-locks if not provided, uses explicit if provided
- PR#5 Review Fixes Round 3: Fixed missing ValidationError import in EventRepository (critical bug fix)
- PR#5 Review Fixes Round 3: Clarified same-day ordering documentation - event_date ASC for projection iteration, amount DESC + created_at ASC for same-day ordering
- PR#5 Review Fixes Round 3: Documented account resolution fallback behavior - archived story default_account_id falls through to global default

### Planned
- CPTR-22 to CPTR-47: Stories, Events, Settings, Recurring Rules CRUD endpoints
- Phase 2: Projection engine
- Phase 3: Sync protocol



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
