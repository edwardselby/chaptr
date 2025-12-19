# Changelog

All notable changes to CHAPTR will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Planned
- CPTR-14 to CPTR-21: Pydantic model field definitions
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
- CPTR-14 to CPTR-19, CPTR-21: Model skeletons for Account, Story, Event, RecurringRule, User, Settings, Sync
- CPTR-42 to CPTR-44: Test framework stubs with pytest-asyncio
