# CHAPTR Documentation

**Last Updated:** January 2025

This directory contains all planning, specification, and testing documentation for the CHAPTR personal finance projection system.

---

## 📚 Core Documents (5)

### 1. **chaptr-spec.md** (2,922 lines)
**Complete Technical Specification**

The authoritative reference for CHAPTR's business logic, data models, and architecture.

**Contents:**
- **Part I: Core Specification**
  - Overview & Philosophy
  - Core Concepts (Accounts, Baseline, Stories, Events)
  - Account-Level Projection
  - Reconciliation System
  - Multi-Currency Handling
  - Multi-User Conflict Resolution

- **Part II: Sync Implementation & Progressive Enhancement**
  - Change Logging & Sync Protocol
  - Conflict Detection
  - Full Sync Handling
  - Progressive Enhancement Architecture (3-tier)
  - Storage Adapter Implementation
  - Mode Detection & Error Handling

**When to reference:**
- Understanding business logic
- Implementing features
- Resolving design questions
- Understanding data models and algorithms

---

### 2. **chaptr-implementation-guide.md** (1,226 lines)
**Implementation Roadmap & UI/UX Walkthrough**

Step-by-step guide for building CHAPTR from backend to deployment.

**Contents:**
- **Part I: Implementation Roadmap**
  - 7-phase back-to-front approach
  - Phase 1: Backend API & Database Foundation
  - Phase 2: Core Projection Engine
  - Phase 3: Sync Protocol
  - Phase 4: Frontend Foundation
  - Phase 5: Offline Capability
  - Phase 6: Conflicts & Reconciliation
  - Phase 7: Polish & Deployment

- **Part II: UI/UX Walkthrough**
  - Detailed mockup explanation with scenarios
  - Screen-by-screen walkthrough
  - User flows and interactions
  - Visual design specifications

**When to reference:**
- Planning implementation work
- Understanding development sequence
- UI/UX implementation
- Understanding user flows

---

### 3. **chaptr-mockup.html** (94KB)
**Interactive Visual Reference**

HTML mockup showing all screens, layouts, and visual design.

**Contents:**
- Complete UI mockup with navigation
- Terminal aesthetic (#4af626 on black)
- All screens: Dashboard, Projection, Accounts, Settings, etc.
- Component examples and patterns

**When to reference:**
- Implementing frontend components
- Verifying visual design
- Understanding screen layouts
- Component structure reference

---

### 4. **testing-guide.md** (4,105 lines)
**Comprehensive Testing Documentation**

All manual testing procedures for validating CHAPTR functionality.

**Contents:**
- **Part I: Backend API Testing**
  - Manual testing scenarios with curl commands
  - Account, Story, Event, Recurring Rule endpoints
  - Settings and validation testing

- **Part II: Sync Protocol Testing**
  - Multi-client sync scenarios
  - Conflict detection validation
  - Change log testing

- **Part III: Offline & Progressive Enhancement Testing**
  - Mode 1/2/3 testing procedures
  - Airplane mode and network toggling
  - Service worker validation

- **Part IV: Queue-as-State Architecture Testing**
  - Queue-first pattern validation
  - Derived event testing
  - Account creation offline scenarios

**When to reference:**
- Validating features manually
- Testing sync behavior
- Verifying offline functionality
- Testing edge cases

**Related Automated Tests:**
- `/tests/*.py` - Backend pytest suite
- `/tests/*.test.js` - Frontend Vitest suite
- `/tests/TEST_PLAN.md` - Automated test coverage map

---

### 5. **README.md** (this file)
**Documentation Index**

Navigation guide for all CHAPTR documentation.

---

## 📊 Quick Reference

### Finding Information

| Need | See Document | Section |
|------|--------------|---------|
| **Data models** | chaptr-spec.md | Core Concepts |
| **Business logic** | chaptr-spec.md | Part I sections |
| **Sync protocol** | chaptr-spec.md | Part II: Sync Implementation |
| **Progressive enhancement** | chaptr-spec.md | Part II: Frontend Progressive Enhancement |
| **Implementation order** | chaptr-implementation-guide.md | Part I: Roadmap |
| **UI/UX design** | chaptr-implementation-guide.md | Part II: Walkthrough |
| **Visual reference** | chaptr-mockup.html | All screens |
| **API testing** | testing-guide.md | Part I: Backend API |
| **Sync testing** | testing-guide.md | Part II: Sync Protocol |
| **Offline testing** | testing-guide.md | Part III: Offline |

### Spec Quick Lookups

| Topic | Location |
|-------|----------|
| Account fields | chaptr-spec.md → Core Concepts → Accounts |
| Story funding modes | chaptr-spec.md → Core Concepts → Stories → Funding Modes |
| Event fields | chaptr-spec.md → Core Concepts → Events |
| Projection calculation | chaptr-spec.md → Account-Level Projection |
| Reconciliation algorithm | chaptr-spec.md → Reconciliation System |
| Currency conversion | chaptr-spec.md → Multi-Currency Handling |
| Conflict resolution | chaptr-spec.md → Multi-User Conflict Resolution |
| Sync endpoint | chaptr-spec.md → Part II → Sync Endpoint |
| Storage modes | chaptr-spec.md → Part II → Mode Definitions |

---

## 🏗️ Project Status

**Overall Progress:** 80% complete (81 tasks remaining)

**Current Focus:**
- IDT (Intent Documentation Testing) - 16 tasks
- Polish phase - 48 tasks

**Testing Status:**
- ✅ 113/113 automated frontend tests passing
- ✅ 14,537 lines of test code (Python + JavaScript)
- ⏳ Manual testing via testing-guide.md for integration scenarios

---

## 📝 Document Maintenance

**These documents are the source of truth.** Keep them updated as:
- Features are implemented or changed
- Business logic evolves
- New testing procedures are added
- UI/UX decisions are made

**Update frequency:**
- chaptr-spec.md: When business logic or data models change
- chaptr-implementation-guide.md: When development approach changes
- testing-guide.md: When new testing procedures are needed
- chaptr-mockup.html: When visual design changes

---

## 🔗 Related Documentation

- `/CLAUDE.md` - Project configuration for Claude Code
- `/CHANGELOG.md` - Version history and release notes
- `/tests/TEST_PLAN.md` - Automated test coverage plan
- `/README.md` (root) - Project README

---

**For questions about documentation:** See `/CLAUDE.md` → Support section
