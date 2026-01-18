"""
Event management endpoints.

Provides CRUD operations for financial events (income, expenses) with
account resolution, rate locking, and same-day ordering.
"""

from fastapi import APIRouter, Depends, Query
from uuid import UUID
from typing import Optional, Annotated
from datetime import date

from api.config import MongoDB
from api.models import Event, EventCreate, EventUpdate
from api.repositories.events import EventRepository
from api.utils.auth import get_current_user

router = APIRouter()


def get_event_repo() -> EventRepository:
    """
    Dependency injection for EventRepository.

    :return: Initialized EventRepository
    :rtype: EventRepository
    """
    db = MongoDB.get_database()
    return EventRepository(db)


def get_tenant_id(current_user: dict) -> UUID:
    """
    Extract tenant_id from current user for multi-tenancy filtering.

    :param current_user: Current user dict from JWT token
    :type current_user: dict
    :return: Tenant UUID
    :rtype: UUID
    """
    return UUID(current_user["tenant_id"])


@router.get("/events", response_model=list[Event])
async def list_events(
    current_user: dict = Depends(get_current_user),
    story_id: Annotated[Optional[UUID], Query(
        description="Filter by story UUID"
    )] = None,
    account_id: Annotated[Optional[UUID], Query(
        description="Filter by account UUID"
    )] = None,
    date_from: Annotated[Optional[date], Query(
        description="Filter events from this date (inclusive)"
    )] = None,
    date_to: Annotated[Optional[date], Query(
        description="Filter events to this date (inclusive)"
    )] = None,
    skip: Annotated[int, Query(
        description="Number of records to skip (pagination)",
        ge=0
    )] = 0,
    limit: Annotated[int, Query(
        description="Maximum records to return",
        ge=1,
        le=1000
    )] = 100,
    repo: EventRepository = Depends(get_event_repo)
):
    """
    List events with filtering and same-day ordering.

    Events are returned with critical ordering for balance projections:
    - event_date ASC (chronological)
    - amount DESC (income first - positive amounts before negative)
    - created_at ASC (creation order)

    This ordering minimizes balance dips by processing income before expenses
    on the same day.

    :param story_id: Filter by story UUID
    :type story_id: Optional[UUID]
    :param account_id: Filter by account UUID
    :type account_id: Optional[UUID]
    :param date_from: Start date (inclusive)
    :type date_from: Optional[date]
    :param date_to: End date (inclusive)
    :type date_to: Optional[date]
    :param skip: Records to skip (pagination)
    :type skip: int
    :param limit: Max records to return
    :type limit: int
    :param repo: Injected EventRepository
    :type repo: EventRepository
    :return: List of events
    :rtype: list[Event]

    :Example:

    Multi-tenancy: Only returns events belonging to the current user's tenant.

    ```bash
    # List all events
    curl http://localhost:8000/api/events

    # List events for specific story
    curl "http://localhost:8000/api/events?story_id={story-id}"

    # List events for account in date range
    curl "http://localhost:8000/api/events?account_id={account-id}&date_from=2025-01-01&date_to=2025-12-31"
    ```
    """
    tenant_id = get_tenant_id(current_user)
    return await repo.list_with_ordering(
        story_id=story_id,
        account_id=account_id,
        date_from=date_from,
        date_to=date_to,
        skip=skip,
        limit=limit,
        tenant_id=tenant_id
    )


@router.get("/events/{event_id}", response_model=Event)
async def get_event(
    event_id: UUID,
    current_user: dict = Depends(get_current_user),
    repo: EventRepository = Depends(get_event_repo)
):
    """
    Get single event by ID.

    Multi-tenancy: Only returns event if it belongs to the current user's tenant.

    :param event_id: Event UUID
    :type event_id: UUID
    :param repo: Injected EventRepository
    :type repo: EventRepository
    :return: Event details
    :rtype: Event
    :raises ResourceNotFoundError: If event not found (404)

    :Example:

    ```bash
    curl http://localhost:8000/api/events/{event-id}
    ```
    """
    tenant_id = get_tenant_id(current_user)
    return await repo.get_for_tenant(event_id, tenant_id)


@router.post("/events", response_model=Event, status_code=201)
async def create_event(
    data: EventCreate,
    current_user: dict = Depends(get_current_user),
    story_id: Annotated[Optional[UUID], Query(
        description="Story UUID this event belongs to (null = baseline)"
    )] = None,
    repo: EventRepository = Depends(get_event_repo)
):
    """
    Create new event with account resolution and rate locking.

    Critical Business Rules:
    - Account resolution uses 3-level hierarchy:
      1. User explicit account_id → use it (verify exists and not archived)
      2. Story's default_account_id → use it
      3. Global default account (is_default=true) → use it (fallback)
      4. No account → ERROR
    - Currency rate is locked from current settings (immutable unless event edited)
    - Resolved account_id is stored permanently

    :param data: Event creation data
    :type data: EventCreate
    :param story_id: Story UUID (null = baseline event)
    :type story_id: Optional[UUID]
    :param repo: Injected EventRepository
    :type repo: EventRepository
    :return: Created event
    :rtype: Event
    :raises ValidationError: If no account could be resolved (422)
    :raises ValidationError: If currency rate not found (422)

    :Example:

    ```bash
    # Create baseline event (no story_id)
    curl -X POST http://localhost:8000/api/events \\
      -H "Content-Type: application/json" \\
      -d '{
        "event_date": "2025-01-15",
        "description": "Salary",
        "amount": 3000,
        "currency": "GBP",
        "is_baseline": true
      }'

    # Create event in story with explicit account
    curl -X POST "http://localhost:8000/api/events?story_id={story-id}" \\
      -H "Content-Type: application/json" \\
      -d '{
        "event_date": "2025-06-05",
        "description": "Hotel deposit",
        "amount": -500,
        "currency": "CAD",
        "account_id": "{account-id}"
      }'

    # Create event in story (uses story default account)
    curl -X POST "http://localhost:8000/api/events?story_id={story-id}" \\
      -H "Content-Type: application/json" \\
      -d '{
        "event_date": "2025-06-10",
        "description": "Car rental",
        "amount": -320,
        "currency": "CAD"
      }'
    ```

    Multi-tenancy: Event is created in the current user's tenant.
    """
    tenant_id = get_tenant_id(current_user)
    return await repo.create(data, story_id=story_id, current_user=current_user, client_id=None, tenant_id=tenant_id)


@router.put("/events/{event_id}", response_model=Event)
async def update_event(
    event_id: UUID,
    data: EventUpdate,
    current_user: dict = Depends(get_current_user),
    repo: EventRepository = Depends(get_event_repo)
):
    """
    Update existing event.

    Supports partial updates - only provided fields are updated.

    Business Rules:
    - Cannot edit is_auto_adjustment events (managed by reconciliation system)
    - If currency changed, rate_to_base can be optionally updated
    - Past events CAN be edited (users may need to correct mistakes)

    :param event_id: Event UUID
    :type event_id: UUID
    :param data: Update data (partial)
    :type data: EventUpdate
    :param repo: Injected EventRepository
    :type repo: EventRepository
    :return: Updated event
    :rtype: Event
    :raises ResourceNotFoundError: If event not found (404)
    :raises ResourceConflictError: If trying to edit auto-adjustment event (409)

    Multi-tenancy: Only updates event if it belongs to the current user's tenant.

    :Example:

    ```bash
    # Update event amount
    curl -X PUT http://localhost:8000/api/events/{event-id} \\
      -H "Content-Type: application/json" \\
      -d '{"amount": -350}'

    # Update event date
    curl -X PUT http://localhost:8000/api/events/{event-id} \\
      -H "Content-Type: application/json" \\
      -d '{"event_date": "2025-06-12"}'
    ```
    """
    # Verify event belongs to tenant before update
    tenant_id = get_tenant_id(current_user)
    await repo.get_for_tenant(event_id, tenant_id)
    return await repo.update(event_id, data, current_user=current_user, client_id=None)


@router.delete("/events/{event_id}", status_code=204)
async def delete_event(
    event_id: UUID,
    current_user: dict = Depends(get_current_user),
    repo: EventRepository = Depends(get_event_repo)
):
    """
    Delete event (hard delete).

    Business Rules:
    - Cannot delete is_auto_adjustment events (managed by reconciliation system)
    - Permanent deletion

    Multi-tenancy: Only deletes event if it belongs to the current user's tenant.

    :param event_id: Event UUID
    :type event_id: UUID
    :param repo: Injected EventRepository
    :type repo: EventRepository
    :return: No content (204)
    :raises ResourceNotFoundError: If event not found (404)
    :raises ResourceConflictError: If trying to delete auto-adjustment event (409)

    :Example:

    ```bash
    curl -X DELETE http://localhost:8000/api/events/{event-id}
    ```
    """
    # Verify event belongs to tenant before delete
    tenant_id = get_tenant_id(current_user)
    await repo.get_for_tenant(event_id, tenant_id)
    await repo.delete(event_id, current_user=current_user, client_id=None)
    return None
