# CHAPTR Project - Claude Code Configuration

## Project Overview

**CHAPTR** is a personal finance projection system - a mobile-friendly PWA that answers the question: *"What will my balance be on date X, given everything I know about?"*

### Core Philosophy
- **Projection over tracking** - Focus on where money is going, not where every penny went
- **Stories as layers** - Stories are views on shared financial reality, not isolated pots
- **Reality as anchor** - Accounts and baseline form ground truth; hypotheticals are explicit
- **Automatic-first, manual second** - System handles reconciliation; user intervenes when needed

### Key Features
- Multi-currency support with base currency model
- Story-based financial projection (trips, projects, life events)
- Offline-first PWA with sync protocol
- Per-account and global balance projections
- Automatic reconciliation system
- Multi-user conflict resolution

### Technical Stack
- **Backend**: Python (FastAPI) + MongoDB
- **Frontend**: Alpine.js + Dexie.js (IndexedDB)
- **PWA**: Workbox service worker
- **Sync**: Custom change log protocol with conflict detection

---

## Task Management System

This project uses **Taskwarrior** for comprehensive task tracking across all development phases.

### Task Structure

```
chaptr (root project)
├── backend-api (59 tasks) - Database & API Foundation
├── projection (40 tasks) - Projection Engine
├── sync (31 tasks) - Sync Protocol
├── frontend (59 tasks) - Frontend Foundation
├── offline (24 tasks) - Offline Capability
├── reconciliation (33 tasks) - Conflicts & Reconciliation
└── polish (52 tasks) - Polish & Remaining Features

Total: 298 tasks
```

### Common Taskwarrior Commands

```bash
# View all project tasks
task project:chaptr list

# View specific phase
task project:chaptr.backend-api list

# View tasks by tag
task project:chaptr +api list
task project:chaptr +testing list

# View high-priority tasks only
task project:chaptr priority:H list

# View next most urgent tasks
task project:chaptr next

# Start working on a task
task <id> start

# Mark task as done
task <id> done

# View project summary
task project:chaptr summary

# Count tasks in a phase
task project:chaptr.backend-api count
```

### Task Tags

Tasks are organized with descriptive tags:

**Phase 1 (backend-api)**: `setup`, `database`, `models`, `api`, `accounts`, `stories`, `events`, `settings`, `auth`, `testing`, `validation`, `docs`, `recurring`

**Phase 2 (projection)**: `projection`, `funding`, `gaps`, `currency`, `warnings`, `goals`, `testing`, `api`, `validation`

**Phase 3 (sync)**: `changelog`, `sync`, `conflicts`, `stale`, `recurring`, `testing`, `validation`

**Phase 4 (frontend)**: `setup`, `dexie`, `dashboard`, `projection`, `accounts`, `settings`, `commandbar`, `clientside`, `data`, `crud`, `validation`

**Phase 5 (offline)**: `serviceworker`, `syncqueue`, `manualsync`, `backgroundsync`, `offline`, `fullsync`, `validation`

**Phase 6 (reconciliation)**: `conflictui`, `conflictflow`, `reconciliation`, `pending`, `recologic`, `autoadjust`, `drift`, `validation`

**Phase 7 (polish)**: `recurring`, `story`, `assignment`, `editing`, `warnings`, `admin`, `snapshots`, `testing`, `deployment`, `validation`

---

## Documentation

### Primary Documents

All planning and specification documents are located in `/docs`:

| Document | Description | Reference |
|----------|-------------|-----------|
| `chaptr-spec-v2.8.md` | Complete technical specification including data models, business logic, and architecture | Primary spec reference |
| `chaptr-implementation-plan.md` | 7-phase back-to-front implementation approach with detailed tasks | Development roadmap |
| `chaptr-mockup-explanation-v1.2.md` | Detailed walkthrough of UI mockup with example scenarios | UX reference |
| `chaptr-v4-mockup.html` | Interactive HTML mockup showing all screens and flows | Visual reference |

### When Implementing Tasks

**Always reference the specification documents:**

1. **For data models and business logic** → See `chaptr-spec-v2.8.md`
   - Core Concepts section for entity definitions
   - Technical Architecture for implementation details
   - Projection Engine for calculation algorithms
   - Sync Protocol for change log and conflicts

2. **For implementation sequence** → See `chaptr-implementation-plan.md`
   - Phase deliverables and validation criteria
   - Project structure and file organization
   - Testing requirements per phase

3. **For UI/UX implementation** → See `chaptr-mockup-explanation-v1.2.md` and `chaptr-v4-mockup.html`
   - Screen layouts and component structure
   - User flows and interactions
   - Visual design (terminal aesthetic: #4af626 on black, JetBrains Mono)

### Task Description References

Many tasks include direct references to spec sections:
- "see spec: Core Concepts > Accounts"
- "see spec: Projection Engine > Gap Indicators"
- "see spec: Reconciliation System > Triggers"

Always consult the referenced section when implementing a task.

---

## Development Approach

### Implementation Philosophy

Follow the **back-to-front** approach outlined in the implementation plan:

1. **Phase 1**: Solid database and API foundation
2. **Phase 2**: Core projection engine (the heart of CHAPTR)
3. **Phase 3**: Sync protocol and conflict resolution
4. **Phase 4**: Frontend consuming tested APIs
5. **Phase 5**: Add offline capability
6. **Phase 6**: Conflicts and reconciliation
7. **Phase 7**: Polish and deployment

**Each phase builds on tested foundations.**

### Testing Requirements

- **Unit tests** for all business logic
- **Integration tests** for multi-component flows
- **Validation** with curl/Postman for all endpoints
- **Manual testing** against mockup for frontend

### Code Quality

- Follow SPARC methodology when appropriate
- Test-driven development for core logic
- Reference spec for field definitions and algorithms
- Keep implementation aligned with planning documents

---

## Project Structure

```
/chaptr
├── /docs                      # All planning and specification documents
│   ├── chaptr-spec-v2.8.md
│   ├── chaptr-implementation-plan.md
│   ├── chaptr-mockup-explanation-v1.2.md
│   └── chaptr-v4-mockup.html
├── /api                       # FastAPI backend (to be created)
│   ├── main.py
│   ├── config.py
│   ├── models.py
│   └── /routes
│       ├── accounts.py
│       ├── stories.py
│       ├── events.py
│       └── sync.py
├── /core                      # Core business logic (to be created)
│   ├── projection.py
│   └── reconciliation.py
├── /tests                     # Test files (to be created)
│   ├── test_accounts.py
│   ├── test_events.py
│   └── test_projection.py
├── /static                    # Frontend files (to be created)
│   ├── index.html
│   ├── /js
│   │   ├── app.js
│   │   ├── db.js
│   │   ├── sync.js
│   │   ├── projection.js
│   │   └── utils.js
│   ├── /css
│   │   └── style.css
│   └── sw.js
├── requirements.txt           # Python dependencies (to be created)
├── CLAUDE.md                  # This file
└── README.md                  # Project documentation (to be created)
```

---

## Getting Started

### For Development Sessions

1. **Check task status**: `task project:chaptr summary`
2. **Review current phase**: Check which phase you're working on
3. **Pick next task**: `task project:chaptr.backend-api next`
4. **Reference docs**: Open relevant spec sections
5. **Start task**: `task <id> start`
6. **Implement & test**: Follow spec and plan
7. **Complete task**: `task <id> done`

### Key Principles

- **Don't skip phases** - Each phase depends on previous ones
- **Test before moving on** - Each phase has validation criteria
- **Reference the spec** - Don't guess at business logic
- **Follow the mockup** - UI should match the visual design
- **Keep it simple** - Avoid over-engineering beyond spec requirements

---

## Important Notes

### Multi-Currency Model

Base currency approach with locked rates:
- Settings define base currency (e.g., GBP)
- Events store native currency + rate_to_base (locked at creation)
- Display conversion uses current settings rates
- See spec: "Multi-Currency Handling" for full algorithm

### Story Funding Modes

Three modes affect projection starting balance:
- `projected`: Use calculated balance on story start date
- `fixed`: Use specific amount (hypothetical)
- `projected_plus`: Projected + adjustment (e.g., expected loan)

See spec: "Stories > Funding Modes" for details.

### Reconciliation System

Auto-adjustments keep projections aligned with reality:
- Triggers on: exit accounts screen, sync, view projection
- Removes old `[auto]` adjustments, creates new ones
- See spec: "Reconciliation System" for complete algorithm

### Sync Protocol

Change log based with conflict detection:
- Track every create/update/delete
- Compare `base_updated_at` for conflicts
- Return conflicts with both versions
- See spec: "Sync Protocol" for full implementation

---

## Quick Reference

### Spec Section Shortcuts

| Need | See Spec Section |
|------|------------------|
| Account fields | Core Concepts > Accounts |
| Story fields | Core Concepts > Stories |
| Event fields | Core Concepts > Events |
| Projection calculation | Projection Engine > Global Calculation |
| Gap indicators | Projection Engine > Gap Indicators |
| Funding modes | Stories > Funding Modes |
| Same-day ordering | Events > Same-day ordering |
| Account resolution | Events > Account Resolution at Creation |
| Sync format | Sync Protocol > Push Phase |
| Conflict detection | Multi-User Conflict Resolution |
| Reconciliation | Reconciliation System |
| Currency conversion | Multi-Currency Handling |

### Common Validation Commands

```bash
# Test account creation
curl -X POST http://localhost:8000/api/accounts \
  -H "Content-Type: application/json" \
  -d '{"name": "Monzo", "currency": "GBP", "current_balance": 2500, "is_default": true}'

# Test projection endpoint
curl "http://localhost:8000/api/projection?view=all&start=2024-12-18&end=2025-01-18"

# Test sync endpoint
curl -X POST http://localhost:8000/api/sync \
  -H "Content-Type: application/json" \
  -d '{"client_id": "client-a", "last_sync_at": "2024-12-17T00:00:00Z", "changes": []}'
```

---

## Support

For questions about:
- **Business logic** → Check `chaptr-spec-v2.8.md`
- **Implementation order** → Check `chaptr-implementation-plan.md`
- **UI/UX** → Check `chaptr-mockup-explanation-v1.2.md` and mockup HTML
- **Task management** → Use Taskwarrior commands above

**Document version**: Created December 2024
**Task count**: 298 tasks across 7 phases
**Status**: Ready for implementation
