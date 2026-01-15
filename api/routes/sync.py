"""
Sync endpoint for multi-device synchronization.

Implements bidirectional sync protocol:
1. Push Phase: Apply client changes to server with conflict detection
2. Pull Phase: Return changes from other clients since last_sync_at

POST /api/sync - Bidirectional sync with conflict detection
GET /api/sync/full - Full dataset download for stale clients

See docs/chaptr-spec-sync-addendum.md for architecture details.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends
from motor.motor_asyncio import AsyncIOMotorDatabase

from api.config import MongoDB
from api.repositories.base import BaseRepository
from api.models import (
    SyncRequest,
    SyncResponse,
    SyncConflict,
    SyncServerChange,
    FullSyncResponse,
    EntityType,
    ChangeAction,
    # Create models
    EventCreate,
    StoryCreate,
    AccountCreate,
    RecurringRuleCreate,
    # Update models
    EventUpdate,
    StoryUpdate,
    AccountUpdate,
    RecurringRuleUpdate,
    SettingsUpdate,
)
from api.repositories.events import EventRepository
from api.repositories.stories import StoryRepository
from api.repositories.accounts import AccountRepository
from api.repositories.recurring_rules import RecurringRuleRepository
from api.repositories.settings import SettingsRepository
from api.utils.auth import get_current_user
from api.utils.db import utc_now
from api.utils.errors import ResourceNotFoundError, ResourceConflictError


router = APIRouter()


# ==================== Model Mapping Helpers ====================

def get_create_model(entity_type: str):
    """
    Map entity_type to corresponding Create Pydantic model.

    Note: Settings are not included - they use singleton pattern (update-only).
    Settings are initialized on startup and can only be updated via SettingsUpdate.
    """
    mapping = {
        "event": EventCreate,
        "story": StoryCreate,
        "account": AccountCreate,
        "recurring_rule": RecurringRuleCreate,
    }
    return mapping.get(entity_type)

def get_update_model(entity_type: str):
    """Map entity_type to corresponding Update Pydantic model."""
    mapping = {
        "event": EventUpdate,
        "story": StoryUpdate,
        "account": AccountUpdate,
        "recurring_rule": RecurringRuleUpdate,
        "settings": SettingsUpdate,
    }
    return mapping.get(entity_type)


# ==================== Repository Dispatcher Helpers ====================

def get_repository(db: AsyncIOMotorDatabase, entity_type: str) -> Optional[BaseRepository]:
    """Get repository instance for entity type."""
    mapping = {
        "event": EventRepository(db),
        "story": StoryRepository(db),
        "account": AccountRepository(db),
        "recurring_rule": RecurringRuleRepository(db),
        "settings": SettingsRepository(db),
    }
    return mapping.get(entity_type)


# ==================== Change Handlers ====================

async def handle_create(
    repo: BaseRepository,
    change,
    current_user: dict,
    client_id: str
) -> None:
    """
    Dispatch create operation to appropriate repository.

    For sync protocol, the client specifies entity_id which MUST be used
    instead of server-generated ID. We add the ID to the data dict before
    creating the model.

    Raises:
        ResourceConflictError: If creation violates business rules
        ValidationError: If data doesn't match Create model schema
    """
    create_model_class = get_create_model(change.entity_type.value)
    if not create_model_class:
        return  # Unknown entity type - skip silently

    create_data = create_model_class(**change.data)
    # Pass entity_id to repository - sync protocol requires using client-specified IDs
    await repo.create(create_data, current_user=current_user, client_id=client_id, entity_id=change.entity_id)


async def handle_update(
    repo: BaseRepository,
    change,
    current_user: dict,
    client_id: str
) -> Optional[SyncConflict]:
    """
    Dispatch update operation with conflict detection.

    Conflict Detection:
        Compare client's base_updated_at with server's current updated_at.
        If different, server was modified after client's last sync -> conflict.

    Returns:
        SyncConflict if edit/edit or delete/edit conflict detected, None if successfully applied.

    Raises:
        ResourceNotFoundError: If entity doesn't exist (handled by caller)
    """
    # Get current server version
    try:
        existing = await repo.get(change.entity_id)
    except ResourceNotFoundError:
        # Entity was deleted by another client - idempotent, no conflict
        # Client tried to update something that's already gone, skip silently
        return None

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
    update_model_class = get_update_model(change.entity_type.value)
    if not update_model_class:
        return None  # Unknown entity type

    update_data = update_model_class(**change.data)
    await repo.update(change.entity_id, update_data, current_user=current_user, client_id=client_id)
    return None


async def handle_delete(
    repo: BaseRepository,
    change,
    current_user: dict,
    client_id: str
) -> Optional[SyncConflict]:
    """
    Dispatch delete operation with conflict detection.

    Conflict Detection:
        If server version was modified after client's base_updated_at, someone
        else edited it -> delete/edit conflict.

    Returns:
        SyncConflict if delete/edit conflict detected, None if successfully applied.

    Raises:
        ResourceNotFoundError: If entity doesn't exist (handled by caller)
    """
    # Get current server version
    try:
        existing = await repo.get(change.entity_id)
    except ResourceNotFoundError:
        # Already deleted by another client - not a conflict, skip
        return None

    # Conflict detection: compare timestamps
    if change.base_updated_at and existing.updated_at != change.base_updated_at:
        return SyncConflict(
            entity_type=change.entity_type,
            entity_id=change.entity_id,
            conflict_type="delete_edit",
            client_version=None,  # Client wants to delete
            server_version=existing.model_dump(mode="json")
        )

    # No conflict - apply delete
    await repo.delete(change.entity_id, current_user=current_user, client_id=client_id)
    return None


# ==================== Sync Endpoint ====================

@router.post("/sync", response_model=SyncResponse)
async def sync(
    request: SyncRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Bidirectional sync endpoint.

    Protocol:
    1. PUSH PHASE: Apply client changes to server
       - Creates: Insert new entities
       - Updates: Modify existing entities (with conflict detection)
       - Deletes: Remove entities (with conflict detection)
       - Returns conflicts for manual resolution

    2. PULL PHASE: Get changes from other clients
       - Query change_log since last_sync_at
       - Exclude changes made by this client_id
       - Return server_changes array

    Conflict Types:
    - edit_edit: Both client and server modified same entity
    - delete_edit: Client deleted, server modified (or vice versa)
    - business_rule: Change violates business logic (e.g., cascade constraints)
    - derived_event_overridden: Client's optimistic derived event replaced by server's authoritative version (auto-resolved by frontend)

    Stale Client Handling:
        If last_sync_at is older than oldest change_log entry, returns
        full_sync_required=true. Client should call GET /api/sync/full.

    Returns:
        SyncResponse with applied changes, conflicts, and server changes.
    """
    db = MongoDB.get_database()

    # Capture sync start time - used to include changes created during this sync (e.g., reconciliation)
    sync_start_time = utc_now()

    applied: list[UUID] = []
    conflicts: list[SyncConflict] = []

    # Track entities created in this batch to skip conflict detection on immediate updates
    created_in_batch: set[UUID] = set()

    # ========== PUSH PHASE: Process client changes ==========
    for change in request.changes:
        repo = get_repository(db, change.entity_type.value)
        if not repo:
            # Unknown entity type - skip
            continue

        # Skip client-created derived events (server creates authoritative versions)
        # Derived events have metadata._derived_from set by queue-as-state architecture
        # If _derived_from is present, client marked this as a derived event that server will recreate
        if (change.action == ChangeAction.CREATE and
            change.metadata and
            change.metadata.derived_from):

            # Return conflict to notify frontend to delete its optimistic version
            # Frontend will silently resolve by removing from IndexedDB
            conflicts.append(SyncConflict(
                entity_type=change.entity_type,
                entity_id=change.entity_id,
                conflict_type="derived_event_overridden",
                client_version=change.data,
                server_version=None  # Server will create its own version
            ))

            # Skip processing this change - server creates authoritative version
            continue

        try:
            if change.action == ChangeAction.CREATE:
                await handle_create(repo, change, current_user, request.client_id)
                applied.append(change.entity_id)
                created_in_batch.add(change.entity_id)  # Track for conflict-free updates

            elif change.action == ChangeAction.UPDATE:
                # Skip conflict detection if entity was just created in this batch
                # This allows CREATE → UPDATE in same sync (e.g., account creation + immediate balance update)
                skip_conflict_check = change.entity_id in created_in_batch

                if skip_conflict_check:
                    # SECURITY: Validate entity was actually created recently (within 5 seconds)
                    # This prevents exploiting same-batch bypass if timing is off
                    entity = await repo.get(change.entity_id)
                    if entity:
                        time_since_create = (sync_start_time - entity.created_at).total_seconds()
                        if time_since_create > 5:  # More than 5 seconds old - shouldn't happen in same batch
                            # Fall back to normal conflict detection
                            skip_conflict_check = False

                    if skip_conflict_check:
                        # Apply update without conflict detection
                        update_model_class = get_update_model(change.entity_type.value)
                        if update_model_class:
                            update_data = update_model_class(**change.data)
                            await repo.update(change.entity_id, update_data, current_user=current_user, client_id=request.client_id)
                            applied.append(change.entity_id)
                    else:
                        # Entity too old - use normal conflict detection
                        conflict = await handle_update(repo, change, current_user, request.client_id)
                        if conflict:
                            conflicts.append(conflict)
                        else:
                            applied.append(change.entity_id)
                else:
                    # Normal conflict detection
                    conflict = await handle_update(repo, change, current_user, request.client_id)
                    if conflict:
                        conflicts.append(conflict)
                    else:
                        applied.append(change.entity_id)

            elif change.action == ChangeAction.DELETE:
                conflict = await handle_delete(repo, change, current_user, request.client_id)
                if conflict:
                    conflicts.append(conflict)
                else:
                    applied.append(change.entity_id)

        except ResourceNotFoundError:
            # Entity was already deleted by another client - not an error
            pass
        except ResourceConflictError as e:
            # Business rule violation (e.g., deleting account with events)
            conflicts.append(SyncConflict(
                entity_type=change.entity_type,
                entity_id=change.entity_id,
                conflict_type="business_rule",
                client_version=change.data,
                server_version={"error": str(e)}
            ))

    # ========== RECONCILIATION PHASE: Create [auto] adjustment events ==========
    # Trigger reconciliation after all client changes are applied
    # Creates [auto] adjustment events for accounts with pending_reconciliation = true
    from core.reconciliation import trigger_reconciliation

    user_id = UUID(current_user["id"])

    await trigger_reconciliation(
        trigger_reason="sync",
        db=db,
        user_id=user_id,
        client_id=None  # Server-side change - must appear in all clients' server_changes
    )

    # ========== PULL PHASE: Get changes from other clients ==========
    server_changes: list[SyncServerChange] = []
    full_sync_required = False

    # Check staleness BEFORE generating recurring events
    # Otherwise newly generated events might change the oldest timestamp
    if request.last_sync_at:
        # Check if client is stale (last_sync_at older than oldest change_log entry)
        oldest_log = await db["change_log"].find_one(sort=[("changed_at", 1)])

        if oldest_log:
            # Parse ISO string to datetime for comparison
            oldest_changed_at = datetime.fromisoformat(oldest_log["changed_at"])

            if request.last_sync_at < oldest_changed_at:
                # Client is stale - change log was pruned
                full_sync_required = True

    # ========== RECURRING EVENT GENERATION ==========
    # Generate recurring events before querying change_log (per spec line 1558)
    # This ensures newly generated events are included in server_changes
    # IMPORTANT: Do this AFTER staleness check to avoid creating new "oldest" entries
    from api.utils.recurring import generate_recurring_events

    user_id = UUID(current_user["id"])
    await generate_recurring_events(db, user_id, request.client_id)

    if not full_sync_required:
        # Query changes since last_sync_at (or all changes for first sync)
        # Include: REST API changes (client_id=None or missing) and other clients' changes
        # Exclude: Only this client's own changes
        query = {
            "$or": [
                {"changed_by_client": {"$in": [None]}},  # REST API changes (field is null)
                {"changed_by_client": {"$exists": False}},  # Field not present (old fixtures)
                {"changed_by_client": {"$ne": request.client_id}}  # Other clients
            ]
        }

        # If last_sync_at provided, only get changes since then
        # If None (first sync), get all changes
        if request.last_sync_at:
            query["changed_at"] = {"$gt": request.last_sync_at.isoformat()}

        cursor = db["change_log"].find(query).sort("changed_at", 1)

        async for log_entry in cursor:
            server_changes.append(SyncServerChange(
                entity_type=EntityType(log_entry["entity_type"]),
                entity_id=UUID(log_entry["entity_id"]),
                action=ChangeAction(log_entry["action"]),
                data=log_entry.get("data")  # None for deletes
            ))

    return SyncResponse(
        applied=applied,
        conflicts=conflicts,
        server_changes=server_changes,
        sync_timestamp=utc_now(),
        full_sync_required=full_sync_required
    )


@router.get("/sync/full", response_model=FullSyncResponse)
async def full_sync(current_user: dict = Depends(get_current_user)):
    """
    Full dataset download for stale clients.

    Called when:
    - First sync (no last_sync_at)
    - Stale client (last_sync_at older than oldest change_log entry)
    - Client requests full refresh

    Returns complete dataset:
    - All accounts
    - All stories
    - All events
    - All recurring rules
    - Global settings
    - Current sync_timestamp

    Client should:
    1. Clear local database
    2. Insert all returned entities
    3. Store sync_timestamp for next incremental sync
    """
    db = MongoDB.get_database()
    user_id = current_user["id"]

    # Get all entities for this user
    account_repo = AccountRepository(db)
    story_repo = StoryRepository(db)
    event_repo = EventRepository(db)
    recurring_rule_repo = RecurringRuleRepository(db)
    settings_repo = SettingsRepository(db)

    # Filter by created_by to ensure user only gets their own data
    # Note: Accounts don't have created_by field (shared resource in Phase 1)
    user_filter = {"created_by": user_id}

    return {
        "accounts": [a.model_dump(mode="json") for a in await account_repo.list(limit=1000)],  # All accounts (no user filter)
        "stories": [s.model_dump(mode="json") for s in await story_repo.list(filters=user_filter, limit=1000)],
        "events": [e.model_dump(mode="json") for e in await event_repo.list(filters=user_filter, limit=10000)],  # High limit for events
        "recurring_rules": [r.model_dump(mode="json") for r in await recurring_rule_repo.list(filters=user_filter, limit=1000)],
        "settings": (await settings_repo.get_or_create_default()).model_dump(mode="json"),  # Settings are global
        "sync_timestamp": utc_now()
    }


@router.post("/reconciliation/trigger")
async def trigger_reconciliation_endpoint(
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(MongoDB.get_database)
):
    """
    Manually trigger reconciliation for all pending accounts.

    Creates [auto] adjustment events to align projected vs actual balances.
    Triggered by: balance updates, projection views, or manual user action.

    Returns:
        {"reconciled": bool, "message": str}
    """
    from core.reconciliation import trigger_reconciliation

    user_id = UUID(current_user["id"])

    result = await trigger_reconciliation(
        trigger_reason="manual",
        db=db,
        user_id=user_id,
        client_id=None
    )

    return {
        "reconciled": result,
        "message": "Reconciliation complete" if result else "No pending accounts"
    }
