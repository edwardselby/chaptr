"""
Recurring Rule repository for CHAPTR API.

Provides data access layer for recurring event rules (salary, rent, subscriptions).

Note: Event generation logic (±1 month window) is deferred to Phase 7.
Phase 1.4 implements CRUD operations only - no event materialization yet.
"""

from uuid import UUID
from typing import Optional
from decimal import Decimal
from datetime import date

from api.repositories.base import BaseRepository
from api.models import RecurringRule, RecurringRuleCreate, RecurringRuleUpdate
from api.utils.db import generate_id, utc_now, to_str
from api.utils.errors import ValidationError
from api.utils.recurring import generate_recurring_events


class RecurringRuleRepository(BaseRepository[RecurringRule]):
    """
    Repository for managing recurring event rules.

    Implements business rules:
    - CRUD operations for rule definitions
    - Validation of frequency and day relationships
    - Validation of account_id existence

    Note: This repository manages rule definitions only. Event generation
    from these rules (±1 month window) is implemented in Phase 7.

    :Example:

    >>> repo = RecurringRuleRepository(db)
    >>> rule = await repo.create(
    ...     RecurringRuleCreate(
    ...         description="Monthly Salary",
    ...         amount=Decimal("3000"),
    ...         currency="GBP",
    ...         account_id=account_id,
    ...         frequency=Frequency.MONTHLY,
    ...         day=25,
    ...         start_date=date(2025, 1, 1)
    ...     )
    ... )
    """

    def __init__(self, db):
        """
        Initialize recurring rule repository.

        :param db: MongoDB database instance
        :type db: AsyncIOMotorDatabase
        """
        super().__init__(db, "recurring_rules", RecurringRule)

    async def create(
        self,
        data: RecurringRuleCreate,
        current_user: Optional[dict] = None,
        client_id: Optional[str] = None,
        entity_id: Optional[UUID] = None  # For sync protocol - client-specified ID
    ) -> RecurringRule:
        """
        Create new recurring rule.

        Business Rules:
        - account_id must exist and not be archived
        - Frequency and day validated by Pydantic
        - No event generation yet (deferred to Phase 7)
        - Auto-populates created_by/updated_by if user authenticated

        :param data: Recurring rule creation data
        :type data: RecurringRuleCreate
        :param current_user: Current authenticated user (from JWT token)
        :type current_user: Optional[dict]
        :return: Created recurring rule
        :rtype: RecurringRule
        :raises ValidationError: If account_id references non-existent or archived account

        :Example:

        >>> rule = await repo.create(
        ...     RecurringRuleCreate(
        ...         description="Weekly Coffee",
        ...         amount=Decimal("-25"),
        ...         currency="GBP",
        ...         account_id=account_id,
        ...         frequency=Frequency.WEEKLY,
        ...         day=1,  # Monday
        ...         start_date=date(2025, 1, 6)
        ...     )
        ... )
        """
        # Validate account_id exists and not archived
        account = await self.db['accounts'].find_one({
            "id": to_str(data.account_id),
            "is_archived": False
        })
        if not account:
            raise ValidationError(
                f"account_id {data.account_id} not found or archived"
            )

        # Extract user ID from current_user if authenticated
        user_id = self._get_user_id(current_user)

        # Use provided entity_id (from sync) or generate new ID
        rule_id = entity_id if entity_id is not None else generate_id()

        # Create recurring rule with generated ID and timestamps
        rule = RecurringRule(
            id=rule_id,
            **data.model_dump(),
            created_at=utc_now(),
            created_by=user_id,
            updated_at=utc_now(),
            updated_by=user_id
        )

        # Insert into MongoDB
        await self.collection.insert_one(rule.model_dump(mode="json"))

        # Log change for sync
        await self.log_change(
            "recurring_rule",
            rule.id,
            "create",
            rule.model_dump(mode="json"),
            user_id,
            client_id
        )

        return rule

    async def update(
        self,
        rule_id: UUID,
        data: RecurringRuleUpdate,
        current_user: Optional[dict] = None,
        client_id: Optional[str] = None
    ) -> RecurringRule:
        """
        Update existing recurring rule.

        Business Rules:
        - Partial updates supported
        - account_id must exist and not be archived if being updated
        - Modification affects future events only
        - Past generated events remain unchanged
        - Future unedited instances deleted and regenerated with new values
        - Always update timestamp and updated_by (if user authenticated)

        Spec compliance (line 1347): "Modification: Future generated events updated"
        Implementation: Deletes future unedited instances ($expr updated_at == created_at),
        logs deletions to change_log for sync, and regenerates them with updated rule values

        :param rule_id: Recurring rule UUID to update
        :type rule_id: UUID
        :param data: Update data (partial)
        :type data: RecurringRuleUpdate
        :param current_user: Current authenticated user (from JWT token)
        :type current_user: Optional[dict]
        :return: Updated recurring rule
        :rtype: RecurringRule
        :raises ResourceNotFoundError: If rule not found
        :raises ValidationError: If account_id validation fails

        :Example:

        >>> rule = await repo.update(
        ...     rule_id,
        ...     RecurringRuleUpdate(amount=Decimal("3200"))
        ... )
        """
        # Get existing rule
        existing = await self.get(rule_id)

        # Prepare update dictionary
        update_dict = data.model_dump(exclude_unset=True)

        # Validate account_id if being updated
        if 'account_id' in update_dict and update_dict['account_id']:
            account = await self.db['accounts'].find_one({
                "id": to_str(update_dict['account_id']),
                "is_archived": False
            })
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
            {"id": to_str(rule_id)},
            {"$set": {k: v.isoformat() if hasattr(v, 'isoformat') else
                      str(v) if isinstance(v, (UUID, Decimal)) else v
                      for k, v in update_dict.items()}}
        )

        # Get updated rule for change log
        updated_rule = await self.get(rule_id)

        # Log change for sync
        await self.log_change(
            "recurring_rule",
            rule_id,
            "update",
            updated_rule.model_dump(mode="json"),
            self._get_user_id(current_user),
            client_id
        )

        # Spec compliance (line 1347): Regenerate future events with updated rule
        # First, fetch future unedited instances to log deletions for sync protocol
        today = date.today()
        events_to_delete = await self.db["events"].find({
            "recurring_rule_id": to_str(rule_id),
            "event_date": {"$gt": today.isoformat()},
            "$expr": {"$eq": ["$updated_at", "$created_at"]}  # Not edited
        }).to_list(length=None)

        # Log each deletion to change_log for sync (critical for multi-client sync)
        user_id = self._get_user_id(current_user)
        for event_doc in events_to_delete:
            await self.log_change(
                "event",
                UUID(event_doc["id"]),
                "delete",
                event_doc,
                user_id,
                client_id
            )

        # Delete future unedited instances
        if events_to_delete:
            await self.db["events"].delete_many({
                "recurring_rule_id": to_str(rule_id),
                "event_date": {"$gt": today.isoformat()},
                "$expr": {"$eq": ["$updated_at", "$created_at"]}
            })

        # Regenerate events with updated rule values
        # Note: Currently regenerates all user rules within ±1 month window
        # Future optimization: Pass rule_id to generate only for this specific rule
        await generate_recurring_events(self.db, user_id, client_id)

        # Return updated rule
        return updated_rule

    async def delete(
        self,
        rule_id: UUID,
        current_user: Optional[dict] = None,
        client_id: Optional[str] = None
    ) -> bool:
        """
        Delete recurring rule and future unedited instances.

        Business Rules:
        - Removes the rule definition
        - Deletes only FUTURE event instances that haven't been edited
        - Past events and edited instances retained
        - Edited instance detection: updated_at != created_at
        - Hard delete (permanent)

        :param rule_id: Recurring rule UUID to delete
        :type rule_id: UUID
        :param current_user: Current authenticated user (from JWT token)
        :type current_user: Optional[dict]
        :param client_id: Client ID for change_log tracking
        :type client_id: Optional[str]
        :return: True if deleted successfully
        :rtype: bool
        :raises ResourceNotFoundError: If rule not found

        :Example:

        >>> await repo.delete(rule_id, current_user=user, client_id="client-a")
        True
        """
        from datetime import date

        # Verify rule exists and get snapshot for change log (before deletion)
        rule = await self.get(rule_id)

        # Delete only FUTURE instances that haven't been edited
        today = date.today()
        await self.db["events"].delete_many({
            "recurring_rule_id": to_str(rule_id),
            "event_date": {"$gt": today.isoformat()},
            "$expr": {"$eq": ["$updated_at", "$created_at"]}  # Not edited
        })

        # Delete the rule itself
        await self.collection.delete_one({"id": to_str(rule_id)})

        # Log change for sync
        await self.log_change(
            "recurring_rule",
            rule_id,
            "delete",
            rule.model_dump(mode="json"),
            self._get_user_id(current_user),
            client_id
        )

        return True
