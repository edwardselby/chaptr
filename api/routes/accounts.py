"""
Account management endpoints.

Provides CRUD operations for financial accounts (Monzo, HSBC, etc.).
"""

from fastapi import APIRouter, Depends, Query
from uuid import UUID
from typing import Annotated

from api.config import MongoDB
from api.models import Account, AccountCreate, AccountUpdate
from api.repositories.accounts import AccountRepository
from api.utils.auth import get_current_user

router = APIRouter()


def get_account_repo() -> AccountRepository:
    """
    Dependency injection for AccountRepository.

    :return: Initialized AccountRepository
    :rtype: AccountRepository
    """
    db = MongoDB.get_database()
    return AccountRepository(db)


@router.get("/accounts", response_model=list[Account])
async def list_accounts(
    current_user: dict = Depends(get_current_user),
    include_archived: Annotated[bool, Query(
        description="Include archived accounts in results"
    )] = False,
    repo: AccountRepository = Depends(get_account_repo)
):
    """
    List all accounts.

    By default, excludes archived accounts. Use include_archived=true
    to include archived accounts in the response.

    :param include_archived: Whether to include archived accounts (default: False)
    :type include_archived: bool
    :param repo: Injected AccountRepository
    :type repo: AccountRepository
    :return: List of accounts
    :rtype: list[Account]

    :Example:

    ```bash
    # List active accounts only
    curl http://localhost:8000/api/accounts

    # List all accounts including archived
    curl http://localhost:8000/api/accounts?include_archived=true
    ```
    """
    if include_archived:
        return await repo.list()
    return await repo.list_active()


@router.get("/accounts/{account_id}", response_model=Account)
async def get_account(
    account_id: UUID,
    current_user: dict = Depends(get_current_user),
    repo: AccountRepository = Depends(get_account_repo)
):
    """
    Get single account by ID.

    :param account_id: Account UUID
    :type account_id: UUID
    :param repo: Injected AccountRepository
    :type repo: AccountRepository
    :return: Account details
    :rtype: Account
    :raises ResourceNotFoundError: If account not found (404)

    :Example:

    ```bash
    curl http://localhost:8000/api/accounts/{account-id}
    ```
    """
    return await repo.get(account_id)


@router.post("/accounts", response_model=Account, status_code=201)
async def create_account(
    data: AccountCreate,
    repo: AccountRepository = Depends(get_account_repo)
):
    """
    Create new account.

    Business Rules:
    - If this is the first account, is_default is automatically set to true
    - If is_default=true, all other accounts are set to is_default=false
    - Server generates UUID and timestamps

    :param data: Account creation data
    :type data: AccountCreate
    :param repo: Injected AccountRepository
    :type repo: AccountRepository
    :return: Created account
    :rtype: Account

    :Example:

    ```bash
    # Create first account (auto-sets is_default=true)
    curl -X POST http://localhost:8000/api/accounts \\
      -H "Content-Type: application/json" \\
      -d '{
        "name": "Monzo",
        "currency": "GBP",
        "current_balance": 2500,
        "balance_updated_at": "2024-12-19T10:00:00Z"
      }'

    # Create second account and set as default
    curl -X POST http://localhost:8000/api/accounts \\
      -H "Content-Type: application/json" \\
      -d '{
        "name": "HSBC",
        "currency": "GBP",
        "current_balance": 5000,
        "balance_updated_at": "2024-12-19T10:00:00Z",
        "is_default": true
      }'
    ```
    """
    return await repo.create(data, client_id=None)


@router.put("/accounts/{account_id}", response_model=Account)
async def update_account(
    account_id: UUID,
    data: AccountUpdate,
    repo: AccountRepository = Depends(get_account_repo)
):
    """
    Update existing account.

    Supports partial updates - only provided fields are updated.

    Business Rules:
    - If setting is_default=true, all other accounts are set to false
    - If balance is updated, pending_reconciliation is automatically set to true
    - balance_updated_at is updated if balance changes

    :param account_id: Account UUID
    :type account_id: UUID
    :param data: Update data (partial)
    :type data: AccountUpdate
    :param repo: Injected AccountRepository
    :type repo: AccountRepository
    :return: Updated account
    :rtype: Account
    :raises ResourceNotFoundError: If account not found (404)

    :Example:

    ```bash
    # Update account balance
    curl -X PUT http://localhost:8000/api/accounts/{account-id} \\
      -H "Content-Type: application/json" \\
      -d '{"current_balance": 3000}'

    # Set as default account
    curl -X PUT http://localhost:8000/api/accounts/{account-id} \\
      -H "Content-Type: application/json" \\
      -d '{"is_default": true}'
    ```
    """
    return await repo.update(account_id, data, client_id=None)


@router.delete("/accounts/{account_id}", status_code=204)
async def delete_account(
    account_id: UUID,
    current_user: dict = Depends(get_current_user),
    repo: AccountRepository = Depends(get_account_repo)
):
    """
    Archive account (soft delete).

    Accounts are never hard-deleted to preserve historical data.
    Instead, they are archived (is_archived=true).

    Business Rules:
    - Cannot archive the default account - set another as default first
    - Archived accounts are hidden from active account lists
    - Historical events are retained

    :param account_id: Account UUID
    :type account_id: UUID
    :param repo: Injected AccountRepository
    :type repo: AccountRepository
    :return: No content (204)
    :raises ResourceNotFoundError: If account not found (404)
    :raises ResourceConflictError: If trying to archive default account (409)

    :Example:

    ```bash
    curl -X DELETE http://localhost:8000/api/accounts/{account-id}
    ```
    """
    await repo.archive(account_id, client_id=None)
    return None
