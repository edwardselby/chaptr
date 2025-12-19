"""
Event management endpoints.

Provides CRUD operations for financial events (income, expenses).

TODO Phase 1.4: Implement full CRUD logic
See spec: Core Concepts > Events
"""

from fastapi import APIRouter, HTTPException

router = APIRouter()


@router.get("/events")
async def list_events():
    """
    List events with optional filtering.

    TODO Phase 1.4:
    - Query MongoDB events collection
    - Support query params: story_id, account_id, date_from, date_to
    - Apply same-day ordering: date ASC, amount DESC, created_at ASC
    - Return array of Event models

    Query Parameters:
        story_id: Filter by story (optional)
        account_id: Filter by account (optional)
        date_from: Start date filter (optional)
        date_to: End date filter (optional)

    Returns:
        list: Array of event objects
    """
    return []


@router.get("/events/{id}")
async def get_event(id: str):
    """
    Get single event by ID.

    TODO Phase 1.4:
    - Query MongoDB by id
    - Return 404 if not found
    - Return Event model

    Args:
        id: Event UUID

    Returns:
        dict: Event object
    """
    raise HTTPException(status_code=404, detail="Event not found")


@router.post("/events")
async def create_event():
    """
    Create new event with account resolution.

    TODO Phase 1.4:
    - Validate EventCreate model
    - Resolve account_id via hierarchy (see spec)
    - Lock rate_to_base from current settings rates
    - Set created_by from auth token
    - Insert into MongoDB
    - Return created Event

    Account Resolution Hierarchy:
    1. Event's explicit account_id → use it
    2. Story's default_account_id → use it
    3. Global default account → fallback

    Business Rules:
    - account_id is REQUIRED (resolved at creation, stored permanently)
    - rate_to_base locked at creation from settings
    - currency must be 3-char ISO code
    - amount can be positive (income) or negative (expense)

    See spec: Events > Account Resolution at Creation

    Returns:
        dict: Created event object
    """
    raise HTTPException(status_code=501, detail="Not implemented")


@router.put("/events/{id}")
async def update_event(id: str):
    """
    Update existing event.

    TODO Phase 1.4:
    - Validate EventUpdate model
    - Check if event exists
    - Prompt for rate_to_base update (keep existing or use current)
    - Update in MongoDB
    - Trigger snapshot invalidation if date changed
    - Return updated Event

    Business Rules:
    - Past events CAN be edited (users may need to correct mistakes)
    - Editing triggers recalculation of all subsequent balances
    - Cannot modify is_auto_adjustment events directly
    - If currency changed, prompt to update rate_to_base

    Args:
        id: Event UUID

    Returns:
        dict: Updated event object
    """
    raise HTTPException(status_code=501, detail="Not implemented")


@router.delete("/events/{id}")
async def delete_event(id: str):
    """
    Delete event.

    TODO Phase 1.4:
    - Check if event exists
    - Prevent deletion of is_auto_adjustment events
    - Delete from MongoDB (hard delete)
    - Trigger snapshot invalidation
    - Return success status

    Args:
        id: Event UUID

    Returns:
        dict: Success message
    """
    raise HTTPException(status_code=501, detail="Not implemented")
