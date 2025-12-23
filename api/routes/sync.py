"""
Sync protocol endpoints.

Provides sync operations for offline-first PWA with conflict detection.

TODO Phase 3: Implement full sync protocol
See spec: Sync Protocol
"""

from fastapi import APIRouter, HTTPException

router = APIRouter()


@router.post("/sync")
async def sync():
    """
    Main sync endpoint (push and pull).

    TODO Phase 2-3:
    - Receive client changes (creates, updates, deletes)
    - Process each change with conflict detection
    - Generate recurring events within window (Phase 4: use api.utils.recurring.generate_recurring_events)
    - Query change_log for server changes since last_sync_at
    - Return applied changes, conflicts, and server changes

    Phase 4 Integration Point:
        from api.utils.recurring import generate_recurring_events
        # Call after push phase, before pull phase:
        user_id = UUID(current_user["id"])
        await generate_recurring_events(db, user_id, request.client_id)

    Request Body:
        client_id: Device UUID
        last_sync_at: ISO timestamp
        changes: Array of change objects

    Response:
        applied: Array of successfully applied change IDs
        conflicts: Array of conflict objects
        server_changes: Array of changes from other clients
        sync_timestamp: Current server timestamp
        full_sync_required: Boolean (if client too far behind)

    Conflict Detection:
    - Compare base_updated_at with server's updated_at
    - If mismatch, create conflict record
    - Return both versions to client

    See spec: Sync Protocol > Push Phase and Pull Phase

    Returns:
        dict: Sync response with applied, conflicts, server_changes
    """
    raise HTTPException(status_code=501, detail="Not implemented")


@router.get("/conflicts")
async def list_conflicts():
    """
    List unresolved conflicts for current user.

    TODO Phase 6:
    - Query conflicts collection
    - Filter by current user
    - Filter resolved_at IS NULL
    - Return array of Conflict models

    Returns:
        list: Array of unresolved conflict objects
    """
    return []


@router.post("/conflicts/{id}/resolve")
async def resolve_conflict(id: str):
    """
    Resolve a conflict.

    TODO Phase 6:
    - Get conflict by id
    - Apply chosen version (local or server)
    - Mark conflict as resolved
    - Set resolved_by and resolved_at
    - Return success status

    Request Body:
        resolution: 'kept_local' or 'kept_server'

    Args:
        id: Conflict UUID

    Returns:
        dict: Success message
    """
    raise HTTPException(status_code=501, detail="Not implemented")


@router.get("/full-sync")
async def full_sync():
    """
    Full sync for stale clients.

    TODO Phase 3:
    - Return complete dataset for user
    - Accounts, stories, events, recurring_rules, settings
    - Client clears local data and repopulates

    Used when:
    - Client's last_sync_at is older than oldest change_log entry
    - Server returns full_sync_required: true

    See spec: Sync Protocol > Stale Client Handling

    Returns:
        dict: Complete dataset
    """
    raise HTTPException(status_code=501, detail="Not implemented")
