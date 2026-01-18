"""
Story repository for CHAPTR API.

Provides data access layer for financial stories (trips, projects, life events)
with business logic for funding modes, goals, and cascade delete.
"""

from uuid import UUID
from typing import Optional
from decimal import Decimal

from api.repositories.base import BaseRepository
from api.models import Story, StoryCreate, StoryUpdate, StoryBase
from api.utils.db import generate_id, utc_now, to_str
from api.utils.errors import ValidationError


class StoryRepository(BaseRepository[Story]):
    """
    Repository for managing financial stories.

    Implements business rules:
    - Validate default_account_id exists and not archived
    - Validate funding_mode and funding_amount relationship
    - Validate goal_type and goal_amount relationship
    - Cascade delete to events when story deleted
    - Merge-then-validate for partial updates

    :Example:

    >>> repo = StoryRepository(db)
    >>> story = await repo.create(StoryCreate(
    ...     name="canada-trip",
    ...     start_date=date(2025, 6, 1),
    ...     end_date=date(2025, 6, 30),
    ...     display_currency="CAD",
    ...     funding_mode=FundingMode.PROJECTED
    ... ))
    """

    def __init__(self, db):
        """
        Initialize story repository.

        :param db: MongoDB database instance
        :type db: AsyncIOMotorDatabase
        """
        super().__init__(db, "stories", Story)

    async def create(
        self,
        data: StoryCreate,
        current_user: Optional[dict] = None,
        client_id: Optional[str] = None,
        entity_id: Optional[UUID] = None,  # For sync protocol - client-specified ID
        tenant_id: Optional[UUID] = None  # For multi-tenancy - from current_user
    ) -> Story:
        """
        Create new story with tenant isolation.

        Business Rules:
        - default_account_id must exist and not be archived
        - Funding mode and amount relationship validated by Pydantic
        - Goal type and amount relationship validated by Pydantic
        - Auto-populates created_by/updated_by if user authenticated
        - tenant_id required for multi-tenancy isolation

        :param data: Story creation data
        :type data: StoryCreate
        :param current_user: Current authenticated user (from JWT token)
        :type current_user: Optional[dict]
        :param tenant_id: Tenant identifier for multi-tenancy
        :type tenant_id: Optional[UUID]
        :return: Created story
        :rtype: Story
        :raises ValidationError: If default_account_id references non-existent or archived account

        :Example:

        >>> story = await repo.create(StoryCreate(
        ...     name="volvo",
        ...     start_date=date(2025, 3, 1),
        ...     display_currency="GBP",
        ...     funding_mode=FundingMode.FIXED,
        ...     funding_amount=Decimal("15000")
        ... ), current_user=user, tenant_id=UUID(user["tenant_id"]))
        """
        # Get tenant_id from current_user if not explicitly provided
        if tenant_id is None and current_user:
            tenant_id = self._get_tenant_id(current_user)

        # Validate default_account_id if provided (within tenant)
        if data.default_account_id:
            account_filter = {
                "id": to_str(data.default_account_id),
                "is_archived": False
            }
            if tenant_id:
                account_filter["tenant_id"] = str(tenant_id)
            account = await self.db['accounts'].find_one(account_filter)
            if not account:
                raise ValidationError(
                    f"default_account_id {data.default_account_id} not found or archived"
                )

        # Extract user ID from current_user if authenticated
        user_id = self._get_user_id(current_user)

        # Use provided entity_id (from sync) or generate new ID
        story_id = entity_id if entity_id is not None else generate_id()

        # Create story with generated ID, timestamps, and tenant_id
        story_data = data.model_dump()
        story_data['tenant_id'] = tenant_id  # Override with resolved tenant_id
        story = Story(
            id=story_id,
            **story_data,
            created_at=utc_now(),
            created_by=user_id,
            updated_at=utc_now(),
            updated_by=user_id
        )

        # Insert into MongoDB
        await self.collection.insert_one(story.model_dump(mode="json"))

        # Log change for sync with tenant_id
        await self.log_change(
            "story",
            story.id,
            "create",
            story.model_dump(mode="json"),
            user_id,
            client_id,
            tenant_id
        )

        return story

    async def update(
        self,
        story_id: UUID,
        data: StoryUpdate,
        current_user: Optional[dict] = None,
        client_id: Optional[str] = None
    ) -> Story:
        """
        Update existing story with partial update validation.

        Business Rules:
        - Merge update with existing before validation (cross-field relationships)
        - default_account_id must exist and not be archived
        - Changing default_account_id only affects future events

        :param story_id: Story UUID to update
        :type story_id: UUID
        :param data: Update data (partial)
        :type data: StoryUpdate
        :param current_user: Current authenticated user (auto-populated by route)
        :type current_user: Optional[dict]
        :return: Updated story
        :rtype: Story
        :raises ResourceNotFoundError: If story not found
        :raises ValidationError: If cross-field validation fails

        :Example:

        >>> story = await repo.update(
        ...     story_id,
        ...     StoryUpdate(funding_mode=FundingMode.PROJECTED_PLUS, funding_amount=Decimal("5000"))
        ... )
        """
        # Get existing story
        existing = await self.get(story_id)

        # Get tenant_id for validation queries
        tenant_id = self._get_tenant_id(current_user)

        # Prepare update dictionary
        update_dict = data.model_dump(exclude_unset=True)

        # Merge with existing for validation
        merged = existing.model_dump()
        merged.update(update_dict)

        # Validate full relationships using base model
        # This ensures funding_mode + funding_amount and goal_type + goal_amount are valid
        StoryBase(**merged)

        # Validate default_account_id if being updated (tenant-scoped)
        if 'default_account_id' in update_dict and update_dict['default_account_id']:
            account_query = {
                "id": to_str(update_dict['default_account_id']),
                "is_archived": False
            }
            if tenant_id:
                account_query["tenant_id"] = str(tenant_id)
            account = await self.db['accounts'].find_one(account_query)
            if not account:
                raise ValidationError(
                    f"default_account_id {update_dict['default_account_id']} not found or archived"
                )

        # Always update timestamp and user
        update_dict['updated_at'] = utc_now()
        if current_user:
            update_dict['updated_by'] = UUID(current_user["id"])

        # Apply update with Decimal handling (for mongomock compatibility)
        await self.collection.update_one(
            {"id": to_str(story_id)},
            {"$set": {k: v.isoformat() if hasattr(v, 'isoformat') else
                      str(v) if isinstance(v, (UUID, Decimal)) else v
                      for k, v in update_dict.items()}}
        )

        # Get updated story for change log
        updated_story = await self.get(story_id)

        # Log change for sync with tenant_id
        await self.log_change(
            "story",
            story_id,
            "update",
            updated_story.model_dump(mode="json"),
            self._get_user_id(current_user),
            client_id,
            self._get_tenant_id(current_user)
        )

        # Return updated story
        return updated_story

    async def delete(
        self,
        story_id: UUID,
        current_user: Optional[dict] = None,
        client_id: Optional[str] = None
    ) -> bool:
        """
        Hard delete story and cascade to events.

        Business Rules:
        - Deletes ALL events with story_id = this story
        - This is destructive (hard delete, no archive)
        - Deletion is permanent

        :param story_id: Story UUID to delete
        :type story_id: UUID
        :return: True if deleted successfully
        :rtype: bool
        :raises ResourceNotFoundError: If story not found

        :Example:

        >>> await repo.delete(story_id)
        True
        """
        # Verify story exists and get snapshot for change log
        story = await self.get(story_id)

        # Log change BEFORE deletion (to capture entity snapshot) with tenant_id
        await self.log_change(
            "story",
            story_id,
            "delete",
            story.model_dump(mode="json"),
            self._get_user_id(current_user),
            client_id,
            self._get_tenant_id(current_user)
        )

        # CASCADE: Delete all events belonging to this story
        # Include tenant_id for security (defense-in-depth)
        tenant_id = self._get_tenant_id(current_user)
        cascade_query = {'story_id': to_str(story_id)}
        if tenant_id:
            cascade_query['tenant_id'] = str(tenant_id)
        await self.db['events'].delete_many(cascade_query)

        # Delete the story itself (include tenant_id for security)
        delete_query = {'id': to_str(story_id)}
        if tenant_id:
            delete_query['tenant_id'] = str(tenant_id)
        result = await self.collection.delete_one(delete_query)

        return True
