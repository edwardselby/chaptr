# CHAPTR Spec Addendum: Sync Implementation

**Version:** 3.0  
**Date:** December 2024  
**Status:** Implementation guidance for sync system + frontend progressive enhancement

This addendum clarifies the sync implementation approach, building on the existing repository pattern rather than introducing a separate service layer. It also defines the progressive enhancement strategy for the PWA frontend.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Change Logging](#change-logging)
3. [Sync Endpoint](#sync-endpoint)
4. [Change Log Maintenance](#change-log-maintenance)
5. [Full Sync Handling](#full-sync-handling)
6. [Repository Changes Summary](#repository-changes-summary)
7. [Frontend Progressive Enhancement](#frontend-progressive-enhancement)
8. [Storage Adapter Implementation](#storage-adapter-implementation)
9. [Mode Detection & Initialization](#mode-detection--initialization)
10. [Error Handling](#error-handling)
11. [Queue Management](#queue-management)
12. [Testing & Development](#testing--development)
13. [UI Components](#ui-components)

---

## Architecture Overview

The sync endpoint acts as a **dispatcher** to existing repository methods, adding conflict detection and change logging.

```
┌─────────────────────────────────────────────────────────────────┐
│  POST /api/sync                                                 │
│                                                                 │
│  ┌─────────────────┐       ┌─────────────────────────────────┐ │
│  │  Push Phase     │──────▶│  Existing Repository Layer      │ │
│  │                 │       │                                 │ │
│  │  for change in  │       │  EventRepository.create()       │ │
│  │    changes:     │       │  EventRepository.update()       │ │
│  │                 │       │  EventRepository.delete()       │ │
│  │  - detect       │       │  StoryRepository.create()       │ │
│  │    conflicts    │       │  AccountRepository.update()     │ │
│  │  - dispatch to  │       │  ...                            │ │
│  │    repository   │       │                                 │ │
│  └─────────────────┘       └─────────────────────────────────┘ │
│           │                              │                      │
│           │                              ▼                      │
│           │                ┌─────────────────────────────────┐ │
│           │                │  Change Log (automatic)         │ │
│           │                │                                 │ │
│           │                │  Repositories log all mutations │ │
│           │                │  via ChangeLogMixin             │ │
│           │                └─────────────────────────────────┘ │
│           │                              │                      │
│           ▼                              ▼                      │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Pull Phase                                             │   │
│  │                                                         │   │
│  │  Query change_log for entries since last_sync_at        │   │
│  │  Exclude changes made by requesting client              │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### Key Design Decisions

- **Sequential Processing:** Server processes changes in the order received (not parallel)
- **No Client-Side Compaction:** All queued changes sent to server; server handles deduplication
- **Audit Trail Preserved:** Each change creates a separate change_log entry
- **Changes Applied in Order:** Clients apply pulled changes sequentially (create → update → delete)

---

## Change Logging

### Logged Entity Types

All mutable entities must log changes:

| Entity Type | Repository | Actions Logged |
|-------------|------------|----------------|
| `event` | EventRepository | create, update, delete |
| `story` | StoryRepository | create, update, delete |
| `account` | AccountRepository | create, update, delete |
| `recurring_rule` | RecurringRuleRepository | create, update, delete |
| `settings` | SettingsRepository | update |

**Not logged:**
- `change_log` (meta, would be recursive)
- `snapshots` (server-side optimisation, not synced to clients)
- `conflicts` (client-local, resolved per-device)
- `users` (admin-only, loaded on-demand)

### Change Log Schema

```python
# MongoDB collection: change_log
{
    "id": "uuid",
    "entity_type": "event",           # event | story | account | recurring_rule | settings
    "entity_id": "uuid",              # ID of the affected entity
    "action": "create",               # create | update | delete
    "data": { ... },                  # Full entity snapshot (see below)
    "changed_by_user": "uuid",        # User who made the change
    "changed_by_client": "uuid",      # Device/client that made the change
    "changed_at": "2024-12-18T10:00:00Z"
}
```

### Snapshot Strategy

**For create and update:**
- Store the **full entity state after mutation**
- This allows clients to apply the change without needing the previous state
- Includes all fields, not just changed ones

**For delete:**
- Store the **full entity state before deletion**
- Enables conflict resolution (user can see what was deleted)
- `data` is the complete entity that was removed

```python
# Example: delete snapshot
{
    "entity_type": "event",
    "entity_id": "abc-123",
    "action": "delete",
    "data": {
        "id": "abc-123",
        "event_date": "2024-12-20",
        "description": "Car rental",
        "amount": "-320",
        # ... full entity as it was before deletion
    },
    "changed_by_user": "user-456",
    "changed_by_client": "device-789",
    "changed_at": "2024-12-18T10:30:00Z"
}
```

### ChangeLogMixin Implementation

Add to `BaseRepository` or as a mixin:

```python
class ChangeLogMixin:
    """
    Mixin providing change logging for sync support.
    
    All repository mutations should call log_change() after
    successfully completing the database operation.
    """
    
    async def log_change(
        self,
        entity_type: str,
        entity_id: UUID,
        action: str,
        data: Optional[dict],
        user_id: Optional[UUID] = None,
        client_id: Optional[str] = None
    ) -> None:
        """
        Record a change for sync distribution.
        
        :param entity_type: Type of entity (event, story, account, etc.)
        :param entity_id: UUID of the affected entity
        :param action: One of: create, update, delete
        :param data: Full entity snapshot (after mutation, or before deletion)
        :param user_id: User who made the change (from JWT)
        :param client_id: Client device ID (from sync request)
        """
        await self.db["change_log"].insert_one({
            "id": str(generate_id()),
            "entity_type": entity_type,
            "entity_id": str(entity_id),
            "action": action,
            "data": data,
            "changed_by_user": str(user_id) if user_id else None,
            "changed_by_client": client_id,
            "changed_at": utc_now().isoformat()
        })
```

### Repository Integration

Each repository method that mutates data must log the change. Add `client_id` parameter to mutation methods:

```python
class EventRepository(BaseRepository[Event], ChangeLogMixin):
    
    async def create(
        self,
        data: EventCreate,
        story_id: Optional[UUID] = None,
        current_user: Optional[dict] = None,
        client_id: Optional[str] = None          # NEW: for change logging
    ) -> Event:
        # ... existing creation logic ...
        
        await self.collection.insert_one(event.model_dump(mode="json"))
        
        # Log change for sync
        await self.log_change(
            entity_type="event",
            entity_id=event.id,
            action="create",
            data=event.model_dump(mode="json"),
            user_id=user_id,
            client_id=client_id
        )
        
        return event
    
    async def update(
        self,
        event_id: UUID,
        data: EventUpdate,
        current_user: Optional[dict] = None,
        client_id: Optional[str] = None          # NEW
    ) -> Event:
        # ... existing update logic ...
        
        updated_event = await self.get(event_id)
        
        # Log change for sync
        await self.log_change(
            entity_type="event",
            entity_id=event_id,
            action="update",
            data=updated_event.model_dump(mode="json"),
            user_id=UUID(current_user["id"]) if current_user else None,
            client_id=client_id
        )
        
        return updated_event
    
    async def delete(
        self,
        event_id: UUID,
        current_user: Optional[dict] = None,     # NEW: needed for logging
        client_id: Optional[str] = None          # NEW
    ) -> bool:
        # Get entity BEFORE deletion for snapshot
        event = await self.get(event_id)
        
        # ... existing delete logic (validation, etc.) ...
        
        await self.collection.delete_one({"id": to_str(event_id)})
        
        # Log change for sync (with pre-deletion snapshot)
        await self.log_change(
            entity_type="event",
            entity_id=event_id,
            action="delete",
            data=event.model_dump(mode="json"),
            user_id=UUID(current_user["id"]) if current_user else None,
            client_id=client_id
        )
        
        return True
```

### REST Endpoint Compatibility

Existing REST endpoints continue to work. When called directly (not via sync), pass `client_id=None`:

```python
@router.post("/events")
async def create_event(
    data: EventCreate,
    current_user: dict = Depends(get_current_user)
):
    repo = EventRepository(db)
    return await repo.create(
        data,
        current_user=current_user,
        client_id=None  # Direct API call, not from sync
    )
```

Changes made via REST endpoints will still be logged and distributed to other clients on their next sync.

---

## Sync Endpoint

### Request Schema

```python
class SyncChange(BaseModel):
    entity_type: str                    # event | story | account | recurring_rule | settings
    entity_id: UUID
    action: str                         # create | update | delete
    data: Optional[dict] = None         # Entity data (null for delete)
    base_updated_at: Optional[datetime] = None  # For conflict detection

class SyncRequest(BaseModel):
    client_id: str                      # Unique device identifier
    last_sync_at: Optional[datetime]    # Last successful sync timestamp
    changes: list[SyncChange]           # Local changes to push
```

### Response Schema

```python
class SyncConflict(BaseModel):
    entity_type: str
    entity_id: UUID
    conflict_type: str                  # edit_edit | delete_edit | edit_delete | business_rule
    client_version: dict                # What client tried to save
    server_version: dict                # Current server state

class SyncServerChange(BaseModel):
    entity_type: str
    entity_id: UUID
    action: str
    data: Optional[dict]                # Entity data (null for delete)

class SyncResponse(BaseModel):
    applied: list[UUID]                 # Successfully applied change IDs
    conflicts: list[SyncConflict]       # Conflicts requiring resolution
    server_changes: list[SyncServerChange]  # Changes from other clients
    sync_timestamp: datetime            # Use as last_sync_at for next sync
    full_sync_required: bool = False    # Client too stale, must re-download all
```

### Endpoint Implementation

```python
@router.post("/sync", response_model=SyncResponse)
async def sync(
    request: SyncRequest,
    current_user: dict = Depends(get_current_user),
    db = Depends(get_database)
):
    """
    Bidirectional sync endpoint.
    
    Push phase: Apply client changes, detect conflicts
    Pull phase: Return changes from other clients since last_sync_at
    
    Changes are processed SEQUENTIALLY in the order received.
    """
    # Initialize repositories
    repos = {
        "event": EventRepository(db),
        "story": StoryRepository(db),
        "account": AccountRepository(db),
        "recurring_rule": RecurringRuleRepository(db),
        "settings": SettingsRepository(db),
    }
    
    applied = []
    conflicts = []
    
    # ─────────────────────────────────────────────
    # PUSH PHASE: Process client changes (sequential)
    # ─────────────────────────────────────────────
    
    for change in request.changes:
        repo = repos.get(change.entity_type)
        if not repo:
            continue  # Unknown entity type, skip
        
        try:
            if change.action == "create":
                await handle_create(repo, change, current_user, request.client_id)
                
            elif change.action == "update":
                conflict = await handle_update(repo, change, current_user, request.client_id)
                if conflict:
                    conflicts.append(conflict)
                    continue
                    
            elif change.action == "delete":
                conflict = await handle_delete(repo, change, current_user, request.client_id)
                if conflict:
                    conflicts.append(conflict)
                    continue
            
            applied.append(change.entity_id)
            
        except ResourceNotFoundError:
            # Entity doesn't exist - might have been deleted by another client
            # Not a conflict, just skip
            pass
        except ResourceConflictError as e:
            # Business rule violation (e.g., editing auto-adjustment)
            # Return as a conflict so client knows it failed
            conflicts.append(SyncConflict(
                entity_type=change.entity_type,
                entity_id=change.entity_id,
                conflict_type="business_rule",
                client_version=change.data,
                server_version={"error": str(e)}
            ))
    
    # ─────────────────────────────────────────────
    # PULL PHASE: Get changes from other clients
    # ─────────────────────────────────────────────
    
    server_changes = []
    full_sync_required = False
    
    if request.last_sync_at:
        # Check if client is too stale
        oldest_log = await db["change_log"].find_one(
            sort=[("changed_at", 1)]
        )
        
        if oldest_log and request.last_sync_at < oldest_log["changed_at"]:
            # Client missed changes that have been pruned
            full_sync_required = True
        else:
            # Get changes since last sync, excluding this client's changes
            cursor = db["change_log"].find({
                "changed_at": {"$gt": request.last_sync_at.isoformat()},
                "changed_by_client": {"$ne": request.client_id}
            }).sort("changed_at", 1)
            
            async for log_entry in cursor:
                server_changes.append(SyncServerChange(
                    entity_type=log_entry["entity_type"],
                    entity_id=UUID(log_entry["entity_id"]),
                    action=log_entry["action"],
                    data=log_entry["data"]
                ))
    
    return SyncResponse(
        applied=applied,
        conflicts=conflicts,
        server_changes=server_changes,
        sync_timestamp=utc_now(),
        full_sync_required=full_sync_required
    )
```

### Conflict Detection Helpers

```python
async def handle_create(repo, change, current_user, client_id):
    """Handle create action - dispatch to repository."""
    create_model = get_create_model(change.entity_type)
    await repo.create(
        create_model(**change.data),
        current_user=current_user,
        client_id=client_id
    )

async def handle_update(repo, change, current_user, client_id) -> Optional[SyncConflict]:
    """
    Handle update action with conflict detection.
    
    Returns SyncConflict if server version changed since client's base.
    """
    existing = await repo.get(change.entity_id)
    
    # Conflict detection: compare timestamps
    if change.base_updated_at and existing.updated_at != change.base_updated_at:
        return SyncConflict(
            entity_type=change.entity_type,
            entity_id=change.entity_id,
            conflict_type="edit_edit",
            client_version=change.data,
            server_version=existing.model_dump(mode="json")
        )
    
    # No conflict - apply update
    update_model = get_update_model(change.entity_type)
    await repo.update(
        change.entity_id,
        update_model(**change.data),
        current_user=current_user,
        client_id=client_id
    )
    
    return None

async def handle_delete(repo, change, current_user, client_id) -> Optional[SyncConflict]:
    """
    Handle delete action with conflict detection.
    
    Returns SyncConflict if entity was modified since client's base.
    """
    existing = await repo.get(change.entity_id)
    
    # Conflict: entity was edited after client decided to delete
    if change.base_updated_at and existing.updated_at != change.base_updated_at:
        return SyncConflict(
            entity_type=change.entity_type,
            entity_id=change.entity_id,
            conflict_type="delete_edit",
            client_version=None,  # Client wanted to delete
            server_version=existing.model_dump(mode="json")
        )
    
    # No conflict - apply delete
    await repo.delete(
        change.entity_id,
        current_user=current_user,
        client_id=client_id
    )
    
    return None
```

---

## Change Log Maintenance

### Pruning Job

Run daily to prevent unbounded growth:

```python
async def prune_change_log(db, retention_days: int = 31):
    """
    Remove change log entries older than retention period.
    
    Default 31 days matches spec requirement.
    """
    cutoff = datetime.utcnow() - timedelta(days=retention_days)
    
    result = await db["change_log"].delete_many({
        "changed_at": {"$lt": cutoff.isoformat()}
    })
    
    return result.deleted_count
```

### Index Requirements

```python
# Ensure these indexes exist for sync performance
await db["change_log"].create_index("changed_at")
await db["change_log"].create_index("changed_by_client")
await db["change_log"].create_index([
    ("changed_at", 1),
    ("changed_by_client", 1)
])
```

---

## Full Sync Handling

When `full_sync_required: true` is returned, the client must:

1. Clear all local data (IndexedDB)
2. Request full dataset from server
3. Rebuild local database

### Full Sync Endpoint

```python
@router.get("/sync/full")
async def full_sync(
    current_user: dict = Depends(get_current_user),
    db = Depends(get_database)
):
    """
    Return complete dataset for client rebuild.
    
    Used when:
    - Client is too stale (missed pruned changes)
    - Mode 1 & 2 initial bootstrap (first visit or empty local storage)
    """
    return {
        "accounts": await AccountRepository(db).list(),
        "stories": await StoryRepository(db).list(),
        "events": await EventRepository(db).list(),
        "recurring_rules": await RecurringRuleRepository(db).list(),
        "settings": await SettingsRepository(db).get_all(),
        "sync_timestamp": utc_now()
    }
```

**Note:** Users collection is NOT included - admin-only data loaded on-demand.

---

## Repository Changes Summary

| Repository | Method | Changes Required |
|------------|--------|------------------|
| All | - | Add `ChangeLogMixin` |
| All | `create()` | Add `client_id` param, call `log_change()` |
| All | `update()` | Add `client_id` param, call `log_change()` |
| All | `delete()` | Add `current_user` + `client_id` params, snapshot before delete, call `log_change()` |

---

## Frontend Progressive Enhancement

### Overview

CHAPTR serves a single URL that adapts to browser capabilities, gracefully degrading from full PWA experience to basic web app functionality.

**Key Principle:** Same codebase supports desktop browsers, mobile browsers, PWA installations, and limited environments (private browsing, no SSL, etc.)

### Three-Tier Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  CHAPTR Web App (Single URL)                                │
│                                                             │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  Feature Detection → Storage Adapter                   │ │
│  │                                                        │ │
│  │  ┌─ Mode 1: Full (Dexie + Sync + Offline)      ⭐⭐⭐  │ │
│  │  ├─ Mode 2: Sync-Only (Sync without Dexie)      ⭐⭐   │ │
│  │  └─ Mode 3: Basic (CRUD REST endpoints)         ⭐     │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                             │
│  Backend API:                                               │
│  ├─ POST /api/sync (Modes 1 & 2)                           │
│  ├─ GET /api/sync/full (Modes 1 & 2 bootstrap)             │
│  └─ REST CRUD endpoints (Mode 3 + fallback)                │
└─────────────────────────────────────────────────────────────┘
```

### Mode Definitions

#### Mode 1: Full (Offline-First PWA) ⭐⭐⭐

**Requirements:**
- HTTPS connection
- Modern browser with IndexedDB support
- Dexie.js initialization successful

**Features:**
- ✅ Offline-first - Works without network connection
- ✅ Optimistic updates - Immediate UI response
- ✅ Sync queue - Changes queued when offline
- ✅ Conflict resolution - Full edit-edit/delete-edit detection
- ✅ Background sync - Periodic sync in background

**Data Flow:**
```
User Action → Write to Dexie (immediate) → Update UI (optimistic)
                     ↓
              Queue for sync
                     ↓
              POST /api/sync (when online)
                     ↓
              Apply server changes + handle conflicts
```

#### Mode 2: Sync-Only (No Offline Support) ⭐⭐

**Requirements:**
- Network connection (online-only)
- Sync endpoint available

**When Used:**
- Safari/Firefox private browsing (IndexedDB blocked)
- Dexie initialization failure
- Browser storage quota exceeded

**Features:**
- ✅ Sync protocol - Uses POST /api/sync
- ✅ Conflict detection - Edit-edit conflict handling
- ❌ No offline - Requires network
- ❌ No optimistic updates - UI blocks during save
- ❌ No queue - Changes sent immediately

**Data Flow:**
```
User Action → Show loading → POST /api/sync → Update UI
```

**State Management:**
- Data stored in memory only (Alpine.js reactive state)
- On page load: `GET /api/sync/full` to populate state
- On refresh: Same as first load (fetch from server)
- No sessionStorage - keeps implementation simple

#### Mode 3: Basic (CRUD REST Endpoints) ⭐

**Requirements:**
- Network connection (online-only)
- REST endpoints available

**When Used:**
- HTTP (no SSL) - IndexedDB requires HTTPS
- Very old browsers
- Sync endpoint unavailable
- Emergency fallback mode

**Features:**
- ✅ Direct REST calls - Standard CRUD
- ✅ Broadest compatibility
- ❌ No offline
- ❌ No conflict detection - Last write wins
- ❌ No optimistic updates

**Data Flow:**
```
User Action → Show loading → POST /api/accounts → Update UI
```

**Bootstrap Endpoints (5 sequential calls):**
- `GET /api/accounts`
- `GET /api/stories`
- `GET /api/events`
- `GET /api/recurring-rules`
- `GET /api/settings`

### Feature Availability Matrix

| Feature | Mode 1 (Full) | Mode 2 (Sync) | Mode 3 (Basic) |
|---------|---------------|---------------|----------------|
| Create/Edit/Delete | ✅ | ✅ | ✅ |
| Offline access | ✅ | ❌ | ❌ |
| Optimistic updates | ✅ | ❌ | ❌ |
| Conflict resolution | ✅ | ✅ | ❌ |
| Sync queue | ✅ | ❌ | ❌ |
| Service Worker caching | ✅ | ✅ | ✅ |

### Browser Compatibility

| Environment | Expected Mode | Notes |
|-------------|---------------|-------|
| Chrome/Safari/Firefox (HTTPS) | Full | Best experience |
| Mobile browsers (HTTPS) | Full | Native-like PWA |
| Private browsing | Basic | IndexedDB blocked |
| HTTP (no SSL) | Basic | IndexedDB requires HTTPS |
| IE11 / Old browsers | Basic | No IndexedDB/SW |

---

## Storage Adapter Implementation

### File: `/static/js/storage-adapter.js`

```javascript
import { db } from './db.js';
import { apiRequest, getClientId, generateUUID } from './utils.js';

/**
 * Storage adapter with progressive enhancement.
 * 
 * Automatically detects capabilities and routes to appropriate
 * storage mode (Full, Sync-Only, or Basic).
 */
export class StorageAdapter {
    constructor() {
        this.mode = null;
        this.isReady = false;
        this.lastSyncAt = null;
        this.isSyncing = false;
        
        // In-memory state for Mode 2/3
        this.accounts = [];
        this.stories = [];
        this.events = [];
        this.recurringRules = [];
        this.settings = {};
    }

    /**
     * Initialize storage adapter and detect mode.
     * Must complete in <500ms.
     * 
     * @returns {Promise<string>} Storage mode: 'full' | 'sync-only' | 'basic'
     */
    async init() {
        // Check for forced mode (query param > localStorage > auto)
        const forcedMode = this.getForcedMode();
        if (forcedMode) {
            this.mode = forcedMode;
            console.log(`[CHAPTR] Forced mode: ${this.mode}`);
        } else {
            // Auto-detect mode
            this.mode = await this.detectMode();
        }
        
        // Log mode and capabilities
        console.log('[CHAPTR] Initialized in mode:', this.mode);
        console.log('[CHAPTR] Capabilities:', {
            offline: this.mode === 'full',
            sync: this.mode !== 'basic',
            storage: this.mode === 'full' ? 'IndexedDB' : 'Memory'
        });
        
        this.isReady = true;
        return this.mode;
    }
    
    /**
     * Check for forced mode via query param or localStorage.
     * Priority: query param > localStorage > null (auto-detect)
     */
    getForcedMode() {
        // Query param takes priority
        const urlParams = new URLSearchParams(window.location.search);
        const queryMode = urlParams.get('mode');
        if (['full', 'sync-only', 'basic'].includes(queryMode)) {
            return queryMode;
        }
        
        // Then localStorage
        const storedMode = localStorage.getItem('FORCE_MODE');
        if (['full', 'sync-only', 'basic'].includes(storedMode)) {
            return storedMode;
        }
        
        return null;
    }
    
    /**
     * Auto-detect best available mode.
     */
    async detectMode() {
        // Try Mode 1 (Full) first
        try {
            await db.open();
            return 'full';
        } catch (dexieError) {
            console.warn('[CHAPTR] Dexie unavailable:', dexieError.message);
        }
        
        // Try Mode 2 (Sync-Only)
        if (navigator.onLine) {
            try {
                await this.testSyncEndpoint();
                return 'sync-only';
            } catch (syncError) {
                console.warn('[CHAPTR] Sync endpoint unavailable:', syncError.message);
            }
        }
        
        // Fall back to Mode 3 (Basic)
        console.warn('[CHAPTR] Falling back to Basic mode');
        return 'basic';
    }
    
    /**
     * Test if sync endpoint is available.
     * Times out after 500ms.
     */
    async testSyncEndpoint() {
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 500);
        
        try {
            const response = await apiRequest('/api/sync', {
                method: 'POST',
                body: JSON.stringify({
                    client_id: await getClientId(),
                    last_sync_at: null,
                    changes: []
                }),
                signal: controller.signal
            });
            
            if (!response.ok) {
                throw new Error(`Sync endpoint returned ${response.status}`);
            }
        } finally {
            clearTimeout(timeout);
        }
    }
    
    /**
     * Load initial data (bootstrap).
     * Called after init() to populate state.
     */
    async bootstrap() {
        switch (this.mode) {
            case 'full':
                return await this.bootstrap_Full();
            case 'sync-only':
                return await this.bootstrap_SyncOnly();
            case 'basic':
                return await this.bootstrap_Basic();
        }
    }
    
    async bootstrap_Full() {
        // Check if Dexie has data
        const accountCount = await db.accounts.count();
        
        if (accountCount === 0) {
            // First visit - fetch from server
            const data = await this.fetchFullSync();
            await this.populateDexie(data);
        }
        
        // Load from Dexie into memory for UI
        this.accounts = await db.accounts.toArray();
        this.stories = await db.stories.toArray();
        this.events = await db.events.toArray();
        this.recurringRules = await db.recurring_rules.toArray();
        // Settings loaded separately
    }
    
    async bootstrap_SyncOnly() {
        // Always fetch from server (no local persistence)
        const data = await this.fetchFullSync();
        this.accounts = data.accounts;
        this.stories = data.stories;
        this.events = data.events;
        this.recurringRules = data.recurring_rules;
        this.settings = data.settings;
        this.lastSyncAt = data.sync_timestamp;
    }
    
    async bootstrap_Basic() {
        // Sequential REST calls
        const [accounts, stories, events, rules, settings] = await Promise.all([
            apiRequest('/api/accounts').then(r => r.json()),
            apiRequest('/api/stories').then(r => r.json()),
            apiRequest('/api/events').then(r => r.json()),
            apiRequest('/api/recurring-rules').then(r => r.json()),
            apiRequest('/api/settings').then(r => r.json())
        ]);
        
        this.accounts = accounts;
        this.stories = stories;
        this.events = events;
        this.recurringRules = rules;
        this.settings = settings;
    }
    
    async fetchFullSync() {
        const response = await apiRequest('/api/sync/full');
        if (!response.ok) {
            throw new Error('Failed to fetch initial data');
        }
        return await response.json();
    }
    
    async populateDexie(data) {
        await db.accounts.bulkPut(data.accounts);
        await db.stories.bulkPut(data.stories);
        await db.events.bulkPut(data.events);
        await db.recurring_rules.bulkPut(data.recurring_rules);
        // Settings stored separately
    }
    
    // ... CRUD methods route to _Full, _SyncOnly, or _Basic variants
}

export const storage = new StorageAdapter();
```

---

## Mode Detection & Initialization

### Timing

- `init()` runs during Alpine component initialization (after mount)
- User sees: "Loading CHAPTR..." spinner with app skeleton visible
- Mode detection must complete in **<500ms**
- If detection times out, fall back to Mode 3 (Basic)

### Mode Locking

- **Mode is locked at initialization** - cannot change mid-session
- If Mode 2 user goes offline: operations fail with error toast
- No "retry upgrade" button - user can refresh page to re-detect
- This keeps implementation simple and predictable

### Service Worker Independence

Service Worker is independent of mode detection:

- **Mode 1 without SW:** Still "Full" mode - Dexie works, data syncs. Only loses static asset caching
- **Mode 2 + SW:** Benefits from HTML/CSS/JS caching
- **Mode 3 + SW:** Same static caching benefit
- **SW is NOT required for any mode** - it's a performance enhancement

SW registration failure is logged but doesn't affect mode:
```javascript
console.warn('[CHAPTR] Service Worker unavailable - static assets won\'t cache');
```

---

## Error Handling

### Unified Strategy

All modes use unified error handling via `showToast()` helper:

```javascript
// Network failure messages by mode
const errorMessages = {
    'full': 'Changes queued for sync',           // Auto-retry on reconnect
    'sync-only': 'Please check connection and try again',
    'basic': 'Operation failed. Refresh and retry'
};
```

### Authentication

- **All modes use same JWT authentication** via `apiRequest()` wrapper
- JWT expiry handling (401 response):
  1. `localStorage.removeItem('jwt_token')`
  2. `window.location.href = '/login'`
- No mode-specific auth logic

### Mode 2/3 Offline Handling

If user goes offline in Mode 2 or 3:
- Operations fail immediately
- Error toast: "Connection required. Please check your internet."
- No queuing - user must retry when online

---

## Queue Management

### Queue Limits (Mode 1 Only)

| Threshold | Behaviour |
|-----------|-----------|
| 0-399 | Normal operation |
| 400 | Warning toast: "⚠ 400+ pending changes. Sync recommended." |
| 500 | **Hard block** - Modal dialog blocks operation |

### Hard Block Behaviour (at 500 changes)

1. Modal dialog appears: "Too many pending changes"
2. Offers "Sync Now" button
3. If user declines: Operation fails, change not applied
4. If sync succeeds: Queue cleared, operation retried automatically

### Queue Processing

- **No client-side compaction** - all changes sent in order
- Example: create → update → delete for same entity = 3 change_log entries
- Server processes sequentially, final state is deleted
- Preserves audit trail

---

## Testing & Development

### Forcing Modes

**Priority:** Query param > localStorage > Auto-detection

```javascript
// Query param (highest priority)
?mode=basic
?mode=sync-only
?mode=full

// localStorage
localStorage.setItem('FORCE_MODE', 'basic');
localStorage.setItem('FORCE_MODE', 'sync-only');
localStorage.setItem('FORCE_MODE', 'full');

// Clear override
localStorage.removeItem('FORCE_MODE');
```

### Simulating Modes in DevTools

- **Mode 2:** Settings → Privacy → Block IndexedDB for site
- **Mode 3:** Serve via `http://localhost` (not `https://`)

### Console Logging

```javascript
// On successful init
console.log('[CHAPTR] Initialized in mode:', this.mode);
console.log('[CHAPTR] Capabilities:', {
    offline: this.mode === 'full',
    sync: this.mode !== 'basic',
    storage: this.mode === 'full' ? 'IndexedDB' : 'Memory'
});

// On forced mode
console.log('[CHAPTR] Forced mode:', this.mode);

// On mode detection failure
console.warn('[CHAPTR] Dexie unavailable:', error.message);
console.warn('[CHAPTR] Sync endpoint unavailable - using Basic mode');

// On Service Worker failure
console.warn('[CHAPTR] Service Worker unavailable - static assets won\'t cache');
```

---

## UI Components

### Mode Indicator (Settings Screen)

Add to Settings screen under "Runtime Information":

**Mode 1 (Full):**
```
Runtime Information
├─ Mode: Full (Offline-capable)
├─ Capabilities: ✓ Offline sync  ✓ Conflict detection
└─ Storage: IndexedDB (Dexie)
```

**Mode 2 (Sync-Only):**
```
Runtime Information
├─ Mode: Sync-Only (Online required)
├─ Capabilities: ✗ Offline sync  ✓ Conflict detection
└─ Storage: Memory (cleared on refresh)
```

**Mode 3 (Basic):**
```
Runtime Information
├─ Mode: Basic (Limited)
├─ Capabilities: ✗ Offline sync  ✗ Conflict detection
└─ Storage: Memory (cleared on refresh)
```

### Mode 3 Warning Banner

Persistent banner at top of app (below header), non-dismissible:

```html
<div class="warning-banner mode-3-warning">
    <span class="warning-icon">⚠</span>
    <span>Limited mode - offline sync unavailable. Use HTTPS for full functionality.</span>
</div>
```

**Styling:**
```css
.mode-3-warning {
    background: rgba(255, 170, 0, 0.1);
    border-bottom: 1px solid var(--amber);
    color: var(--amber);
    padding: 8px 16px;
    font-size: 12px;
    display: flex;
    align-items: center;
    gap: 8px;
}
```

### Pending Changes Indicator

Already implemented - amber badge in header showing count, clickable to trigger sync.

### Queue Limit Modal (500 changes)

```html
<div class="modal queue-limit-modal">
    <div class="modal-content">
        <h3>⚠ Too Many Pending Changes</h3>
        <p>You have 500+ changes waiting to sync. Please sync now to continue.</p>
        <div class="modal-actions">
            <button class="btn-primary" onclick="syncNow()">Sync Now</button>
            <button class="btn-secondary" onclick="closeModal()">Cancel</button>
        </div>
    </div>
</div>
```

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 3.0 | Dec 2024 | Major update: Added frontend progressive enhancement strategy (three-tier mode system), storage adapter pattern, mode detection, queue management, error handling, testing guidance, UI components. Clarified sequential change processing and no client-side compaction. |
| 2.8.1 | Dec 2024 | Sync implementation addendum - repository pattern integration, change logging details, sync endpoint implementation |
