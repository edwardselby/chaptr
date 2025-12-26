"""
Account repository for CHAPTR API.

Provides data access layer for financial accounts with business logic
for is_default enforcement, archiving, and reconciliation tracking.
"""

from uuid import UUID
from typing import Optional
from decimal import Decimal

from api.repositories.base import BaseRepository
from api.models import Account, AccountCreate, AccountUpdate
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
