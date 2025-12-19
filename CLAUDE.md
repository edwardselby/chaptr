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

### ⚠️ CRITICAL: Task Status Workflow

**MANDATORY WORKFLOW - NO EXCEPTIONS:**

When working on tasks, you MUST follow this exact sequence:

1. **SELECT** task(s) to work on: `task project:chaptr.backend-api next`
2. **START** the task BEFORE beginning work: `task <id> start`
3. **IMPLEMENT** the task (code, test, document)
4. **COMPLETE** the task when finished: `task <id> done`

**❌ NEVER skip the START step** - The user relies on task status in their graphical UI to track progress.

**Workflow Diagram:**
```
┌─────────────┐    task <id> start    ┌─────────────┐    Implement     ┌─────────────┐    task <id> done    ┌─────────────┐
│   Pending   │ ──────────────────────>│  Started    │ ───────────────>│ In Progress │ ──────────────────>│  Completed  │
│  (status)   │   REQUIRED FIRST STEP  │  (visible   │  (working on    │  (testing   │   FINAL STEP        │  (done)     │
└─────────────┘                        │   in UI)    │     code)       │   & docs)   │                     └─────────────┘
                                       └─────────────┘                  └─────────────┘
```

**Example:**
```bash
# ✅ CORRECT workflow
task project:chaptr.backend-api next    # Find next task (e.g., task 5)
task 5 start                            # MUST mark as started FIRST
# ... implement the task ...
task 5 done                             # Mark complete when finished

# ❌ WRONG workflow (DO NOT DO THIS)
task project:chaptr.backend-api next    # Find task
# ... implement without starting ...
task 5 done                             # Skipped the start step!
```

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

# Add annotation to track implementation notes
task <id> annotate "Note text here"

# View task details including annotations
task <id> info

# Remove specific annotation
task <id> denotate "Text to match"
```

### 📝 Task Annotations - Tracking Implementation Notes

**Use annotations to track adjustments, discoveries, and implementation notes as you work.**

Annotations are timestamped notes attached to tasks that help track:
- Implementation decisions made during work
- Issues discovered that need addressing
- Dependencies or blockers encountered
- Adjustments needed to the original plan
- Technical debt or follow-up items

**Adding Annotations:**
```bash
# Add a note about an implementation decision
task 5 annotate "Using Pydantic validators instead of manual validation"

# Track a discovered issue
task 5 annotate "TODO: Add index on account_id field for performance"

# Note a dependency
task 5 annotate "Blocked: Waiting for MongoDB schema design in task 4"

# Multiple annotations can be added to track progress
task 5 annotate "Added basic CRUD endpoints"
task 5 annotate "Still need to implement cascade delete logic"
```

**Reading Annotations:**
```bash
# View full task details with all annotations
task 5 info

# Annotations appear under the description with timestamps:
# Description: Implement account endpoints
#               2025-12-19 10:30:00 Using Pydantic validators
#               2025-12-19 11:45:00 TODO: Add index on account_id
```

**Removing Annotations:**
```bash
# Remove a specific annotation by matching text
task 5 denotate "Blocked: Waiting"

# Or remove by partial match
task 5 denotate "TODO"
```

**Best Practices:**
- **Annotate during work** - Add notes as you discover issues or make decisions
- **Be specific** - Include enough detail to understand the note later
- **Use prefixes** - `TODO:`, `BLOCKED:`, `DECISION:`, `BUG:` for clarity
- **Read before starting** - Check `task <id> info` for existing annotations before starting work
- **Clean up when done** - Remove obsolete annotations when completing tasks

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

## Changelog Standards

### Format

This project follows a **concise, ticket-based changelog format** to prevent excessive growth while maintaining clear release history.

**File:** `CHANGELOG.md`

**Structure:**
```markdown
# Changelog

## [Unreleased]

### Added
- Description of addition (Task #XXX)

### Changed
- Description of change (Task #XXX)

### Fixed
- Description of fix (Task #XXX)

### Removed
- Description of removal (Task #XXX)

## [X.Y.Z] - YYYY-MM-DD

### Added
- One line per modification (Task #XXX)
```

**Rules:**
1. **One line per modification** - Keep entries brief and focused
2. **Task number prefix** - Start each line with project key and task ID: `CPTR-1:`
3. **Use categories** - Only Added, Changed, Fixed, Removed
4. **Version format** - Semantic versioning: MAJOR.MINOR.PATCH
5. **Date format** - ISO 8601: YYYY-MM-DD
6. **Group related tasks** - Multiple task IDs comma-separated: `CPTR-3, CPTR-4:`
7. **Unreleased work** - All unreleased changes go under `[Unreleased]` section until release

**Project Key:** `CPTR` (CHAPTR)

**Workflow:**
- During development: Add entries under `[Unreleased]`
- When releasing: Move `[Unreleased]` entries to new `[X.Y.Z] - YYYY-MM-DD` section

**Example (Unreleased):**
```markdown
## [Unreleased]

### Added
- CPTR-1: Project directory structure with api, routes, core, tests
- CPTR-2: Python dependencies: FastAPI, Motor, Pydantic, Pytest
- CPTR-3, CPTR-4: MongoDB connection configuration and health check
```

**Example (Released):**
```markdown
## [0.1.0] - 2024-12-19

### Added
- CPTR-1: Project directory structure with api, routes, core, tests
- CPTR-2: Python dependencies: FastAPI, Motor, Pydantic, Pytest
- CPTR-3, CPTR-4: MongoDB connection configuration and health check
- CPTR-291: Route stubs for accounts, stories, events, sync endpoints
- CPTR-290: Core module stubs for projection and reconciliation
```

**What NOT to include:**
- Implementation details (save for commit messages)
- Code examples
- Verbose descriptions
- Internal refactoring unless user-visible

**Version Numbering:**
- **MAJOR (X.0.0)** - Breaking changes, major features
- **MINOR (0.X.0)** - New features, backward compatible
- **PATCH (0.0.X)** - Bug fixes, minor improvements

---

## Getting Started

### For Development Sessions

**⚠️ ALWAYS follow this workflow - NO EXCEPTIONS:**

1. **Check task status**: `task project:chaptr summary`
2. **Review current phase**: Check which phase you're working on
3. **Pick next task**: `task project:chaptr.backend-api next`
4. **Read task details**: `task <id> info` ← Check for existing annotations/notes
5. **Reference docs**: Open relevant spec sections
6. **🚨 START TASK FIRST**: `task <id> start` ← **MANDATORY BEFORE ANY WORK**
7. **Implement & test**: Follow spec and plan
   - **Add annotations** as you work: `task <id> annotate "Implementation note"`
   - Track decisions, issues, TODOs discovered during implementation
8. **Complete task**: `task <id> done`
9. **After PR creation**: Check for review feedback (see PR Review Workflow below)

**CRITICAL REMINDERS:**
- Step 6 is NOT optional. You MUST run `task <id> start` before beginning implementation. This updates the user's graphical UI to show the task as "in progress".
- Step 7: Use annotations liberally to track implementation adjustments, decisions, and follow-up items discovered during work.
- Step 9: After creating a PR, another agent may add review comments. Always check and address feedback.

### Pull Request Review Workflow

**After creating a pull request, another agent reviews your code and adds detailed feedback as PR comments. You MUST check for and address this feedback.**

#### Finding the Current PR

```bash
# Get PR number for current branch
gh pr view --json number,title

# Example output:
# {"number":4,"title":"Feature/phase1.3 pydantic models"}
```

#### Viewing PR Review Comments

```bash
# View complete PR details including comments and reviews
gh pr view --json title,body,reviews,comments

# Or view in readable format
gh pr view

# For specific PR number
gh pr view 4 --json title,body,reviews,comments
```

#### When to Check PR Comments

**ALWAYS check for PR comments in these situations:**
1. **After creating a PR** - Wait 2-5 minutes for automated review agent to comment
2. **When user mentions PR feedback** - If user says "address the PR feedback"
3. **Before merging** - Always review comments before merge
4. **During task work** - If working on PR-related tasks

#### Understanding PR Review Comments

Review comments typically include:

**Priority Levels:**
- 🚨 **CRITICAL** - Must fix before merge (security, bugs, breaking changes)
- ⚠️ **HIGH** - Should fix before merge (spec violations, major issues)
- 🔍 **MEDIUM** - Should fix soon (validation gaps, missing patterns)
- 💡 **LOW** - Consider for future (suggestions, enhancements)

**Comment Structure:**
```json
{
  "comments": [
    {
      "author": {"login": "claude"},
      "body": "## Pull Request Review...\n### Issues Found\n#### 1. Field Name Inconsistency...",
      "createdAt": "2025-12-19T19:26:21Z"
    }
  ]
}
```

#### Addressing PR Feedback

**Workflow for handling review comments:**

1. **Read the full review**:
   ```bash
   gh pr view --json comments | jq -r '.comments[].body'
   ```

2. **Identify action items**:
   - Note all CRITICAL and HIGH priority issues
   - List MEDIUM priority issues for follow-up
   - Consider LOW priority suggestions

3. **Create task annotations** for each issue:
   ```bash
   task <current_task_id> annotate "PR FEEDBACK: Fix date vs event_date field name (HIGH)"
   task <current_task_id> annotate "PR FEEDBACK: Add StoryUpdate validators (MEDIUM)"
   ```

4. **Fix issues** based on priority:
   - Fix CRITICAL/HIGH issues immediately
   - Create new tasks for MEDIUM issues if needed
   - Note LOW suggestions in task annotations

5. **Commit fixes** with clear reference to PR feedback:
   ```bash
   git add -A
   git commit -m "Fix: Address PR #4 feedback - resolve date field inconsistency"
   git push
   ```

6. **Verify fixes** by re-reading PR comments and confirming all HIGH/CRITICAL items addressed

#### Example: Reading and Acting on PR Feedback

```bash
# Step 1: Check PR for current branch
gh pr view --json number,title
# Output: {"number":4,"title":"Feature/phase1.3 pydantic models"}

# Step 2: View detailed comments
gh pr view --json comments | jq -r '.comments[].body' | head -100

# Step 3: Identify issues from review
# Example found: "HIGH: Field Name Inconsistency: date vs event_date"

# Step 4: Annotate current task
task 12 annotate "PR #4 FEEDBACK (HIGH): Change event_date to date per spec"

# Step 5: Implement fix
# ... make code changes ...

# Step 6: Commit with PR reference
git add api/models.py
git commit -m "Fix: Rename event_date to date field per spec (PR #4 feedback)"
git push
```

#### Tips for Efficient PR Review Processing

- **Parse JSON with jq** for easier reading: `gh pr view --json comments | jq`
- **Search for priority keywords**: Look for "CRITICAL", "HIGH", "MEDIUM" in comments
- **Create GitHub issues** for MEDIUM/LOW items if not addressing immediately
- **Re-request review** after fixes: The review agent may re-check your changes

### Key Principles

- **Don't skip phases** - Each phase depends on previous ones
- **Test before moving on** - Each phase has validation criteria
- **Reference the spec** - Don't guess at business logic
- **Follow the mockup** - UI should match the visual design
- **Keep it simple** - Avoid over-engineering beyond spec requirements
- **Address PR feedback** - Always check for and fix review comments before merge

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
