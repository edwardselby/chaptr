# CHAPTR Spec Addendum: Sync Implementation

**Version:** 2.8.1  
**Date:** December 2024  
**Status:** Implementation guidance for sync system

This addendum clarifies the sync implementation approach, building on the existing repository pattern rather than introducing a separate service layer.

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
    conflict_type: str                  # edit_edit | delete_edit | edit_delete
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
    # PUSH PHASE: Process client changes
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
    
    Used when client is too stale (missed pruned changes).
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

---

## Summary of Changes to Repositories

| Repository | Method | Changes Required |
|------------|--------|------------------|
| All | - | Add `ChangeLogMixin` |
| All | `create()` | Add `client_id` param, call `log_change()` |
| All | `update()` | Add `client_id` param, call `log_change()` |
| All | `delete()` | Add `current_user` + `client_id` params, snapshot before delete, call `log_change()` |

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 2.8.1 | Dec 2024 | Sync implementation addendum - repository pattern integration, change logging details, sync endpoint implementation |
