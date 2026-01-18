"""
Event repository for CHAPTR API.

Provides data access layer for financial events (income, expenses) with
critical business logic for account resolution, rate locking, and same-day ordering.
"""

from uuid import UUID
from typing import Optional
from datetime import date
from decimal import Decimal

from api.repositories.base import BaseRepository
from api.models import Event, EventCreate, EventUpdate
from api.utils.db import generate_id, utc_now, to_str, resolve_account_id, get_rate_to_base
from api.utils.errors import ResourceConflictError, ValidationError


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
        current_user: Optional[dict] = None,
        client_id: Optional[str] = None,
        entity_id: Optional[UUID] = None,  # For sync protocol - client-specified ID
        tenant_id: Optional[UUID] = None  # For multi-tenancy - from current_user
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
        - Auto-populates created_by/updated_by if user authenticated

        :param data: Event creation data
        :type data: EventCreate
        :param story_id: Optional story UUID this event belongs to
        :type story_id: Optional[UUID]
        :param current_user: Current authenticated user (from JWT token)
        :type current_user: Optional[dict]
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
        # Extract user ID and tenant_id from current_user FIRST (needed for subsequent queries)
        user_id = self._get_user_id(current_user)
        if tenant_id is None and current_user:
            tenant_id = self._get_tenant_id(current_user)

        # Resolve account_id using 3-level hierarchy (tenant-scoped)
        account_id = await resolve_account_id(
            self.db,
            story_id=story_id,
            explicit_account_id=data.account_id,
            tenant_id=tenant_id
        )

        # Lock rate_to_base from current settings if not provided (tenant-scoped)
        # If provided explicitly, use that rate (for manual corrections)
        # Rate is stored permanently and never auto-updates
        if data.rate_to_base is None:
            rate = await get_rate_to_base(self.db, data.currency, tenant_id=tenant_id)
        else:
            rate = data.rate_to_base

        # Use provided entity_id (from sync) or generate new ID
        event_id = entity_id if entity_id is not None else generate_id()

        # Create event with resolved account, locked rate, and tenant_id
        event = Event(
            id=event_id,
            event_date=data.event_date,
            description=data.description,
            amount=data.amount,
            currency=data.currency,
            rate_to_base=rate,
            account_id=account_id,
            story_id=story_id,
            is_baseline=data.is_baseline,
            is_hypothetical=data.is_hypothetical,
            is_auto_adjustment=data.is_auto_adjustment,  # Use value from EventCreate data
            is_opening_balance=data.is_opening_balance,  # Use value from EventCreate data
            tenant_id=tenant_id,  # Multi-tenancy isolation
            created_at=utc_now(),
            created_by=user_id,
            updated_at=utc_now(),
            updated_by=user_id,
            recurring_rule_id=None  # Set by recurring rule generator
        )

        # Insert into MongoDB
        await self.collection.insert_one(event.model_dump(mode="json"))

        # Log change for sync with tenant_id
        await self.log_change(
            "event",
            event.id,
            "create",
            event.model_dump(mode="json"),
            user_id,
            client_id,
            tenant_id
        )

        return event

    async def update(
        self,
        event_id: UUID,
        data: EventUpdate,
        current_user: Optional[dict] = None,
        client_id: Optional[str] = None
    ) -> Event:
        """
        Update existing event.

        Business Rules:
        - Cannot edit is_auto_adjustment events (created by reconciliation system)
        - If currency changed, can optionally update rate_to_base
        - Always update timestamp and updated_by (if user authenticated)

        :param event_id: Event UUID to update
        :type event_id: UUID
        :param data: Update data (partial)
        :type data: EventUpdate
        :param current_user: Current authenticated user (from JWT token)
        :type current_user: Optional[dict]
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

        # Get tenant_id for validation queries
        tenant_id = self._get_tenant_id(current_user)

        # Prevent editing auto-adjustment events
        if existing.is_auto_adjustment:
            raise ResourceConflictError(
                "Cannot edit auto-adjustment event. "
                "These are managed by the reconciliation system."
            )

        # Prepare update dictionary
        update_dict = data.model_dump(exclude_unset=True)

        # Validate account_id if being updated (tenant-scoped)
        if 'account_id' in update_dict and update_dict['account_id']:
            account_query = {
                "id": to_str(update_dict['account_id']),
                "is_archived": False
            }
            if tenant_id:
                account_query["tenant_id"] = str(tenant_id)
            account = await self.db['accounts'].find_one(account_query)
            if not account:
                raise ValidationError(
                    f"account_id {update_dict['account_id']} not found or archived"
                )

        # Always update timestamp and user
        update_dict['updated_at'] = utc_now()
        if current_user:
            update_dict['updated_by'] = UUID(current_user["id"])

        # Apply update with Decimal handling (for mongomock compatibility)
        await self.collection.update_one(
            {"id": to_str(event_id)},
            {"$set": {k: v.isoformat() if hasattr(v, 'isoformat') else
                      str(v) if isinstance(v, (UUID, Decimal)) else v
                      for k, v in update_dict.items()}}
        )

        # Get updated event for change log
        updated_event = await self.get(event_id)

        # Log change for sync with tenant_id
        await self.log_change(
            "event",
            event_id,
            "update",
            updated_event.model_dump(mode="json"),
            self._get_user_id(current_user),
            client_id,
            self._get_tenant_id(current_user)
        )

        # Return updated event
        return updated_event

    async def delete(
        self,
        event_id: UUID,
        current_user: Optional[dict] = None,
        client_id: Optional[str] = None
    ) -> bool:
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

        # Log change BEFORE deletion (to capture entity snapshot) with tenant_id
        await self.log_change(
            "event",
            event_id,
            "delete",
            event.model_dump(mode="json"),
            self._get_user_id(current_user),
            client_id,
            self._get_tenant_id(current_user)
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
        limit: int = 100,
        tenant_id: Optional[UUID] = None
    ) -> list[Event]:
        """
        List events with projection iteration and same-day ordering.

        Critical Ordering for Balance Projections (spec-compliant):
        1. event_date ASC - Chronological iteration across days (projection requirement)
        2. amount DESC - Same-day ordering: income first, then expenses (spec: "amount DESC")
        3. created_at ASC - Same-day tie-breaker: creation order (spec: "created_at ASC")

        This ordering minimizes balance dips by processing income before expenses
        on the same day, while iterating chronologically across dates for projections.

        Spec reference: "Events > Same-day ordering" - Events on the same date are
        ordered by amount DESC (positive before negative) then created_at ASC.

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
        if tenant_id:
            filters['tenant_id'] = str(tenant_id)
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
