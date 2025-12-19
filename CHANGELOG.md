# Changelog

All notable changes to CHAPTR will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Planned
- CPTR-22 to CPTR-47: CRUD endpoint implementations
- Phase 2: Projection engine
- Phase 3: Sync protocol

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
- CPTR-13: Added RecurringRuleUpdate model for partial updates with validators
- CPTR-11: Added business logic validators to StoryUpdate model (date range, funding, goal)
- CPTR-15: Added rate validation to SettingsUpdate model for consistency
