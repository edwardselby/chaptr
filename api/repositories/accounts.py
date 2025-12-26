"""
Account repository for CHAPTR API.

Provides data access layer for financial accounts with business logic
for is_default enforcement, archiving, and reconciliation tracking.
"""

from uuid import UUID
from typing import Optional
from decimal import Decimal
from datetime import date

from api.repositories.base import BaseRepository
from api.models import Account, AccountCreate, AccountUpdate, EventCreate
from api.utils.db import generate_id, utc_now, to_str
from api.utils.errors import ResourceConflictError


class AccountRepository(BaseRepository[Account]):
    """
    Repository for managing financial accounts.

    Implements business rules:
    - Exactly one account must have is_default=true
    - First account auto-sets is_default=true
    - Cannot archive the default account
    - Balance updates set pending_reconciliation=true

    :Example:

    >>> repo = AccountRepository(db)
    >>> account = await repo.create(AccountCreate(
    ...     name="Monzo",
    ...     currency="GBP",
    ...     current_balance=Decimal("2500"),
    ...     balance_updated_at=utc_now()
    ... ))
    """

    def __init__(self, db):
        """
        Initialize account repository.

        :param db: MongoDB database instance
        :type db: AsyncIOMotorDatabase
        """
        super().__init__(db, "accounts", Account)

    async def create(
        self,
        data: AccountCreate,
        current_user: Optional[dict] = None,
        client_id: Optional[str] = None,
        entity_id: Optional[UUID] = None  # For sync protocol - client-specified ID
    ) -> Account:
        """
        Create new account with is_default enforcement.

        Business Rules:
        - If first account, auto-set is_default=true
        - If is_default=true, unset other accounts' is_default flag
        - Generate server-side UUID and timestamps

        :param data: Account creation data
        :type data: AccountCreate
        :return: Created account
        :rtype: Account

        :Example:

        >>> account = await repo.create(AccountCreate(
        ...     name="Monzo",
        ...     currency="GBP",
        ...     current_balance=Decimal("2500"),
        ...     balance_updated_at=utc_now()
        ... ))
        """
        # Check if this is the first account
        count = await self.count({})
        is_first_account = count == 0

        # First account must be default
        if is_first_account:
            data.is_default = True

        # If setting as default, unset other accounts
        if data.is_default:
            await self.collection.update_many(
                {"is_default": True},
                {"$set": {
                    "is_default": False,
                    "updated_at": utc_now().isoformat()
                }}
            )

        # Use provided entity_id (from sync) or generate new ID
        account_id = entity_id if entity_id is not None else generate_id()

        # Create account with generated ID and timestamps
        account = Account(
            id=account_id,
            **data.model_dump(),
            created_at=utc_now(),
            updated_at=utc_now()
        )

        # Insert into MongoDB
        await self.collection.insert_one(account.model_dump(mode="json"))

        # Log change for sync
        await self.log_change(
            "account",
            account.id,
            "create",
            account.model_dump(mode="json"),
            self._get_user_id(current_user),
            client_id
        )

        # Create opening balance event (fixes reconciliation architecture)
        # Without this, event sourcing calculates projected balance from £0,
        # but account starts with current_balance, causing incorrect drift.
        #
        # Example:
        # - Account created with 1000 GBP
        # - Without opening balance event: projected = 0, actual = 1000, drift = +1000 (WRONG!)
        # - With opening balance event: projected = 1000, actual = 1000, drift = 0 (CORRECT!)
        await self._create_opening_balance_event(
            account=account,
            current_user=current_user,
            client_id=client_id
        )

        return account

    async def update(
        self,
        account_id: UUID,
        data: AccountUpdate,
        current_user: Optional[dict] = None,
        client_id: Optional[str] = None
    ) -> Account:
        """
        Update existing account.

        Business Rules:
        - If setting is_default=true, unset other accounts
        - If balance updated, set pending_reconciliation=true
        - Always update updated_at timestamp

        :param account_id: Account UUID to update
        :type account_id: UUID
        :param data: Update data (partial)
        :type data: AccountUpdate
        :return: Updated account
        :rtype: Account
        :raises ResourceNotFoundError: If account not found

        :Example:

        >>> account = await repo.update(
        ...     account_id,
        ...     AccountUpdate(current_balance=Decimal("3000"))
        ... )
        """
        # Verify account exists
        await self.get(account_id)

        # Prepare update dictionary
        update_dict = data.model_dump(exclude_unset=True)

        # If setting as default, unset other accounts
        if update_dict.get('is_default') is True:
            await self.collection.update_many(
                {"is_default": True, "id": {"$ne": to_str(account_id)}},
                {"$set": {
                    "is_default": False,
                    "updated_at": utc_now().isoformat()
                }}
            )

        # If balance updated, set pending_reconciliation and update timestamp
        if 'current_balance' in update_dict:
            update_dict['pending_reconciliation'] = True
            if 'balance_updated_at' not in update_dict:
                update_dict['balance_updated_at'] = utc_now()

        # Always update timestamp
        update_dict['updated_at'] = utc_now()

        # Apply update
        mongo_update = {k: v.isoformat() if hasattr(v, 'isoformat') else
                      str(v) if isinstance(v, (UUID, Decimal)) else v
                      for k, v in update_dict.items()}

        await self.collection.update_one(
            {"id": to_str(account_id)},
            {"$set": mongo_update}
        )

        # Get updated account for change log
        updated_account = await self.get(account_id)

        # Log change for sync
        await self.log_change(
            "account",
            account_id,
            "update",
            updated_account.model_dump(mode="json"),
            self._get_user_id(current_user),
            client_id
        )

        # Return updated account
        return updated_account

    async def archive(
        self,
        account_id: UUID,
        current_user: Optional[dict] = None,
        client_id: Optional[str] = None
    ) -> bool:
        """
        Soft delete account by setting is_archived=true.

        Business Rules:
        - Cannot archive the default account
        - Archived accounts retain all historical data
        - Archived accounts hidden from active lists

        :param account_id: Account UUID to archive
        :type account_id: UUID
        :return: True if archived successfully
        :rtype: bool
        :raises ResourceNotFoundError: If account not found
        :raises ResourceConflictError: If trying to archive default account

        :Example:

        >>> await repo.archive(account_id)
        True
        """
        # Get account to check if it's default
        account = await self.get(account_id)

        if account.is_default:
            raise ResourceConflictError(
                "Cannot archive default account. "
                "Set another account as default first."
            )

        # Archive the account
        await self.collection.update_one(
            {"id": to_str(account_id)},
            {"$set": {
                "is_archived": True,
                "updated_at": utc_now().isoformat()
            }}
        )

        # Get updated account for change log (after archiving)
        updated_account = await self.get(account_id)

        # Log change for sync (archiving is an update, not delete)
        await self.log_change(
            "account",
            account_id,
            "update",
            updated_account.model_dump(mode="json"),
            self._get_user_id(current_user),
            client_id
        )

        return True

    async def list_active(self) -> list[Account]:
        """
        List all non-archived accounts.

        Convenience method for getting active accounts only.

        :return: List of active accounts
        :rtype: list[Account]

        :Example:

        >>> active_accounts = await repo.list_active()
        """
        return await self.list(filters={"is_archived": False})

    async def get_default(self) -> Optional[Account]:
        """
        Get the default account.

        :return: Default account or None if not set
        :rtype: Optional[Account]

        :Example:

        >>> default = await repo.get_default()
        >>> if default:
        ...     print(f"Default account: {default.name}")
        """
        doc = await self.collection.find_one({
            "is_default": True,
            "is_archived": False
        })

        if not doc:
            return None

        return Account(**doc)

    async def _create_opening_balance_event(
        self,
        account: Account,
        current_user: Optional[dict] = None,
        client_id: Optional[str] = None
    ) -> None:
        """
        Create opening balance event for new account.

        Opening balance events enable proper event sourcing reconciliation:
        - Account balance serves as starting point
        - Events track all changes from that point
        - Projected balance = opening_balance + sum(events)

        Without opening balance events, projected = sum(events) starts from £0,
        which causes incorrect drift calculations when reconciling.

        The event is:
        - Created on account creation date (today)
        - Amount = account current_balance
        - Baseline event (not part of any story)
        - Marked with is_opening_balance=True flag
        - Uses account's currency and conversion rate from settings

        :param account: Newly created account
        :type account: Account
        :param current_user: User creating the account
        :type current_user: Optional[dict]
        :param client_id: Client/device identifier for sync
        :type client_id: Optional[str]
        :return: None
        :rtype: None
        """
        from api.repositories.events import EventRepository
        from api.repositories.settings import SettingsRepository

        # Get settings for rate_to_base conversion
        settings_repo = SettingsRepository(self.db)
        settings = await settings_repo.get_or_create_default()

        # Calculate rate_to_base for this currency
        # If account currency matches base currency, rate = 1.0
        # Otherwise, look up rate from settings
        if account.currency == settings.base_currency:
            rate_to_base = Decimal('1.0')
        else:
            rate_to_base = settings.rates.get(account.currency, Decimal('1.0'))

        # Create opening balance event
        event_data = EventCreate(
            event_date=date.today(),  # Opening balance dated today
            description="opening balance",
            amount=account.current_balance,  # Amount = account starting balance
            currency=account.currency,
            rate_to_base=rate_to_base,
            account_id=account.id,
            story_id=None,  # Opening balance is baseline (not part of any story)
            is_baseline=True,
            is_hypothetical=False,
            is_auto_adjustment=False,
            is_opening_balance=True  # Mark as opening balance event
        )

        # Debug logging
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"Creating opening balance event with is_opening_balance={event_data.is_opening_balance}")
        logger.info(f"Event data dict: {event_data.model_dump()}")

        # Use EventRepository to create the event
        # This ensures proper validation, change log, etc.
        event_repo = EventRepository(self.db)
        created_event = await event_repo.create(
            data=event_data,
            current_user=current_user,
            client_id=client_id
        )

        # Log for debugging
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"Created opening balance event: {created_event.id} for account {account.id} with amount {account.current_balance}")
