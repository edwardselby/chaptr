# Changelog

All notable changes to CHAPTR will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Phase 1.5: JWT authentication system with HS256 algorithm and 24-hour token expiration
- Phase 1.5: User authentication endpoints (POST /auth/login, GET /auth/me)
- Phase 1.5: Password hashing with bcrypt via passlib
- Phase 1.5: Role-based authorization with admin/user roles
- Phase 1.5: User tracking auto-population (created_by/updated_by) from JWT tokens
- Phase 1.5: UserRepository with authenticate() method and admin deletion protection
- Phase 1.5: Authentication error classes (AuthenticationError 401, AuthorizationError 403)
- Phase 1.5: LoginRequest and LoginResponse models for authentication flow
- Phase 1.5: api/utils/auth.py with password hashing and JWT utilities
- Phase 1.5: api/repositories/users.py with user CRUD and authentication
- Phase 1.5: api/routes/auth.py with login and current user endpoints

### Changed
- Phase 1.5: User model extended with password_hash and updated_at fields
- Phase 1.5: Token expiration increased from 30 to 1440 minutes (24 hours) per spec v3.0
- Phase 1.5: Settings PUT endpoint protected with admin-only authorization
- Phase 1.5: Event endpoints (POST, PUT) integrate user tracking via get_current_user dependency
- Phase 1.5: Story endpoints (POST, PUT) integrate user tracking via get_current_user dependency
- Phase 1.5: Recurring rule endpoints (POST, PUT) integrate user tracking via get_current_user dependency
- Phase 1.5: All repositories accept current_user parameter instead of created_by/updated_by UUIDs
- Phase 1.5: Repository methods extract user_id from current_user dict for backward compatibility
- Phase 1.5: RecurringRule model extended with created_by/updated_by fields for consistency
- Phase 1.5: Role-based token expiration (admin: 7 days, user: 24 hours)

### Fixed
- Phase 1.5: Added SECRET_KEY validation at startup (fails if using default key in production)
- Phase 1.5: Password strength validation (requires uppercase, lowercase, and digit)
- Phase 1.5: Unique index on users.username for performance and uniqueness enforcement


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
