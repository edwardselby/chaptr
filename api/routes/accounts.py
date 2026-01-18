"""
Account management endpoints.

Provides CRUD operations for financial accounts (Monzo, HSBC, etc.).
Multi-tenancy: All operations are scoped to the current user's tenant.
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


def get_tenant_id(current_user: dict) -> UUID:
    """
    Extract tenant_id from current user for multi-tenancy filtering.

    :param current_user: Current user dict from JWT token
    :type current_user: dict
    :return: Tenant UUID
    :rtype: UUID
    """
    return UUID(current_user["tenant_id"])


@router.get("/accounts", response_model=list[Account])
async def list_accounts(
    current_user: dict = Depends(get_current_user),
    include_archived: Annotated[bool, Query(
        description="Include archived accounts in results"
    )] = False,
    repo: AccountRepository = Depends(get_account_repo)
):
    """
    List all accounts for current tenant.

    By default, excludes archived accounts. Use include_archived=true
    to include archived accounts in the response.

    Multi-tenancy: Only returns accounts belonging to the current user's tenant.

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
    tenant_id = get_tenant_id(current_user)
    if include_archived:
        return await repo.list_for_tenant(tenant_id)
    return await repo.list_for_tenant(tenant_id, filters={"is_archived": False})


@router.get("/accounts/{account_id}", response_model=Account)
async def get_account(
    account_id: UUID,
    current_user: dict = Depends(get_current_user),
    repo: AccountRepository = Depends(get_account_repo)
):
    """
    Get single account by ID.

    Multi-tenancy: Only returns account if it belongs to the current user's tenant.

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
    tenant_id = get_tenant_id(current_user)
    return await repo.get_for_tenant(account_id, tenant_id)


@router.post("/accounts", response_model=Account, status_code=201)
async def create_account(
    data: AccountCreate,
    current_user: dict = Depends(get_current_user),
    repo: AccountRepository = Depends(get_account_repo)
):
    """
    Create new account in current tenant.

    Business Rules:
    - If this is the first account in tenant, is_default is automatically set to true
    - If is_default=true, all other accounts in tenant are set to is_default=false
    - Server generates UUID and timestamps

    Multi-tenancy: Account is created in the current user's tenant.

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
    tenant_id = get_tenant_id(current_user)
    return await repo.create(data, current_user=current_user, client_id=None, tenant_id=tenant_id)


@router.put("/accounts/{account_id}", response_model=Account)
async def update_account(
    account_id: UUID,
    data: AccountUpdate,
    current_user: dict = Depends(get_current_user),
    repo: AccountRepository = Depends(get_account_repo)
):
    """
    Update existing account.

    Supports partial updates - only provided fields are updated.

    Business Rules:
    - If setting is_default=true, all other accounts in tenant are set to false
    - If balance is updated, pending_reconciliation is automatically set to true
    - balance_updated_at is updated if balance changes

    Multi-tenancy: Only updates account if it belongs to the current user's tenant.

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
    # Verify account belongs to tenant before update
    tenant_id = get_tenant_id(current_user)
    await repo.get_for_tenant(account_id, tenant_id)
    return await repo.update(account_id, data, current_user=current_user, client_id=None)


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

    Multi-tenancy: Only archives account if it belongs to the current user's tenant.

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
    # Verify account belongs to tenant before archive
    tenant_id = get_tenant_id(current_user)
    await repo.get_for_tenant(account_id, tenant_id)
    await repo.archive(account_id, current_user=current_user, client_id=None)
    return None
