"""
Event repository for CHAPTR API.

Provides data access layer for financial events (income, expenses) with
critical business logic for account resolution, rate locking, and same-day ordering.
"""

from uuid import UUID
from typing import Optional
from datetime import date

from api.repositories.base import BaseRepository
from api.models import Event, EventCreate, EventUpdate
from api.utils.db import generate_id, utc_now, to_str, resolve_account_id, get_rate_to_base
from api.utils.errors import ResourceConflictError


class EventRepository(BaseRepository[Event]):
    """
    Repository for managing financial events.

    Implements critical business rules:
    - 3-level account resolution hierarchy
    - Currency rate locking at creation
    - Same-day ordering: event_date ASC, amount DESC, created_at ASC
    - Prevent editing/deleting is_auto_adjustment events
    - Event filtering by story, account, date range

    :Example:

    >>> repo = EventRepository(db)
    >>> event = await repo.create(
    ...     EventCreate(
    ...         event_date=date(2025, 1, 15),
    ...         description="Salary",
    ...         amount=Decimal("3000"),
    ...         currency="GBP"
    ...     ),
    ...     story_id=None  # Baseline event
    ... )
    """

    def __init__(self, db):
        """
        Initialize event repository.

        :param db: MongoDB database instance
        :type db: AsyncIOMotorDatabase
        """
        super().__init__(db, "events", Event)

    async def create(
        self,
        data: EventCreate,
        story_id: Optional[UUID] = None,
        created_by: Optional[UUID] = None
    ) -> Event:
        """
        Create new event with account resolution and rate locking.

        Critical Business Rules:
        - Resolve account_id using 3-level hierarchy:
          1. User explicit account_id → use it
          2. Story's default_account_id → use it
          3. Global default account → use it (fallback)
          4. No account → ERROR
        - Lock rate_to_base from current settings (immutable unless event edited)
        - created_at used for same-day ordering

        :param data: Event creation data
        :type data: EventCreate
        :param story_id: Optional story UUID this event belongs to
        :type story_id: Optional[UUID]
        :param created_by: User ID creating the event (Phase 1.5)
        :type created_by: Optional[UUID]
        :return: Created event
        :rtype: Event
        :raises ValidationError: If no account could be resolved
        :raises ValidationError: If currency rate not found

        :Example:

        >>> # Event with explicit account_id
        >>> event = await repo.create(
        ...     EventCreate(
        ...         event_date=date(2025, 1, 15),
        ...         description="Car rental",
        ...         amount=Decimal("-320"),
        ...         currency="CAD",
        ...         account_id=account_id
        ...     )
        ... )
        >>>
        >>> # Event using story default account
        >>> event = await repo.create(
        ...     EventCreate(
        ...         event_date=date(2025, 6, 5),
        ...         description="Hotel deposit",
        ...         amount=Decimal("-500"),
        ...         currency="CAD"
        ...     ),
        ...     story_id=story_id
        ... )
        """
        # Resolve account_id using 3-level hierarchy
        account_id = await resolve_account_id(
            self.db,
            story_id=story_id,
            explicit_account_id=data.account_id
        )

        # Lock rate_to_base from current settings if not provided
        # If provided explicitly, use that rate (for manual corrections)
        # Rate is stored permanently and never auto-updates
        if data.rate_to_base is None:
            rate = await get_rate_to_base(self.db, data.currency)
        else:
            rate = data.rate_to_base

        # Create event with resolved account and locked rate
        event = Event(
            id=generate_id(),
            event_date=data.event_date,
            description=data.description,
            amount=data.amount,
            currency=data.currency,
            rate_to_base=rate,
            account_id=account_id,
            story_id=story_id,
            is_baseline=data.is_baseline,
            is_hypothetical=data.is_hypothetical,
            is_auto_adjustment=False,  # Only reconciliation creates auto-adjustments
            created_at=utc_now(),
            created_by=created_by,
            updated_at=utc_now(),
            updated_by=created_by,
            recurring_rule_id=None  # Set by recurring rule generator
        )

        # Insert into MongoDB
        await self.collection.insert_one(event.model_dump(mode="json"))

        return event

    async def update(
        self,
        event_id: UUID,
        data: EventUpdate,
        updated_by: Optional[UUID] = None
    ) -> Event:
        """
        Update existing event.

        Business Rules:
        - Cannot edit is_auto_adjustment events (created by reconciliation system)
        - If currency changed, can optionally update rate_to_base
        - Always update timestamp and user

        :param event_id: Event UUID to update
        :type event_id: UUID
        :param data: Update data (partial)
        :type data: EventUpdate
        :param updated_by: User ID updating the event (Phase 1.5)
        :type updated_by: Optional[UUID]
        :return: Updated event
        :rtype: Event
        :raises ResourceNotFoundError: If event not found
        :raises ResourceConflictError: If trying to edit auto-adjustment event

        :Example:

        >>> event = await repo.update(
        ...     event_id,
        ...     EventUpdate(amount=Decimal("-350"))
        ... )
        """
        # Get existing event
        existing = await self.get(event_id)

        # Prevent editing auto-adjustment events
        if existing.is_auto_adjustment:
            raise ResourceConflictError(
                "Cannot edit auto-adjustment event. "
                "These are managed by the reconciliation system."
            )

        # Prepare update dictionary
        update_dict = data.model_dump(exclude_unset=True)

        # Always update timestamp and user
        update_dict['updated_at'] = utc_now()
        if updated_by:
            update_dict['updated_by'] = updated_by

        # Apply update
        await self.collection.update_one(
            {"id": to_str(event_id)},
            {"$set": {k: v.isoformat() if hasattr(v, 'isoformat') else
                      str(v) if isinstance(v, UUID) else v
                      for k, v in update_dict.items()}}
        )

        # Return updated event
        return await self.get(event_id)

    async def delete(self, event_id: UUID) -> bool:
        """
        Hard delete event.

        Business Rules:
        - Cannot delete is_auto_adjustment events (managed by reconciliation)
        - Permanent deletion

        :param event_id: Event UUID to delete
        :type event_id: UUID
        :return: True if deleted successfully
        :rtype: bool
        :raises ResourceNotFoundError: If event not found
        :raises ResourceConflictError: If trying to delete auto-adjustment event

        :Example:

        >>> await repo.delete(event_id)
        True
        """
        # Get event to check if it's auto-adjustment
        event = await self.get(event_id)

        # Prevent deleting auto-adjustment events
        if event.is_auto_adjustment:
            raise ResourceConflictError(
                "Cannot delete auto-adjustment event. "
                "These are managed by the reconciliation system."
            )

        # Hard delete
        await self.collection.delete_one({"id": to_str(event_id)})

        return True

    async def list_with_ordering(
        self,
        story_id: Optional[UUID] = None,
        account_id: Optional[UUID] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        skip: int = 0,
        limit: int = 100
    ) -> list[Event]:
        """
        List events with same-day ordering.

        Critical Ordering for Balance Projections:
        - event_date ASC (chronological)
        - amount DESC (income first, positive > negative)
        - created_at ASC (creation order)

        This ordering minimizes balance dips by processing income before expenses.

        :param story_id: Filter by story (None = include all)
        :type story_id: Optional[UUID]
        :param account_id: Filter by account
        :type account_id: Optional[UUID]
        :param date_from: Filter events >= this date
        :type date_from: Optional[date]
        :param date_to: Filter events <= this date
        :type date_to: Optional[date]
        :param skip: Number of records to skip
        :type skip: int
        :param limit: Maximum records to return
        :type limit: int
        :return: List of events with proper ordering
        :rtype: list[Event]

        :Example:

        >>> # Get all events for a story
        >>> events = await repo.list_with_ordering(story_id=story_id)
        >>>
        >>> # Get events in date range for an account
        >>> events = await repo.list_with_ordering(
        ...     account_id=account_id,
        ...     date_from=date(2025, 1, 1),
        ...     date_to=date(2025, 12, 31)
        ... )
        """
        # Build filter query
        filters = {}
        if story_id:
            filters['story_id'] = to_str(story_id)
        if account_id:
            filters['account_id'] = to_str(account_id)
        if date_from or date_to:
            filters['event_date'] = {}
            if date_from:
                filters['event_date']['$gte'] = date_from.isoformat()
            if date_to:
                filters['event_date']['$lte'] = date_to.isoformat()

        # Critical ordering for balance projections
        sort = [
            ('event_date', 1),   # Chronological
            ('amount', -1),      # Income first (income is positive)
            ('created_at', 1)    # Creation order
        ]

        return await self.list(
            filters=filters,
            skip=skip,
            limit=limit,
            sort=sort
        )
