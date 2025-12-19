"""
Account management endpoints.

Provides CRUD operations for financial accounts (Monzo, HSBC, etc.).

TODO Phase 1.4: Implement full CRUD logic
See spec: Core Concepts > Accounts
"""

from fastapi import APIRouter, HTTPException

router = APIRouter()


@router.get("/accounts")
async def list_accounts():
    """
    List all accounts (excluding archived by default).

    TODO Phase 1.4:
    - Query MongoDB accounts collection
    - Filter is_archived = false by default
    - Add query param to include archived if needed
    - Return array of Account models

    Returns:
        list: Array of account objects
    """
    return []


@router.get("/accounts/{id}")
async def get_account(id: str):
    """
    Get single account by ID.

    TODO Phase 1.4:
    - Query MongoDB by id
    - Return 404 if not found
    - Return Account model

    Args:
        id: Account UUID

    Returns:
        dict: Account object
    """
    raise HTTPException(status_code=404, detail="Account not found")


@router.post("/accounts")
async def create_account():
    """
    Create new account.

    TODO Phase 1.4:
    - Validate AccountCreate model
    - Enforce exactly one is_default = true
    - Insert into MongoDB
    - Return created Account

    Business Rules:
    - Exactly one account must have is_default = true
    - If creating first account, auto-set is_default = true
    - Currency must be 3-char ISO code

    Returns:
        dict: Created account object
    """
    raise HTTPException(status_code=501, detail="Not implemented")


@router.put("/accounts/{id}")
async def update_account(id: str):
    """
    Update existing account.

    TODO Phase 1.4:
    - Validate AccountUpdate model
    - Check if account exists
    - Update in MongoDB
    - Handle is_default enforcement
    - Set pending_reconciliation flag if balance updated
    - Return updated Account

    Args:
        id: Account UUID

    Returns:
        dict: Updated account object
    """
    raise HTTPException(status_code=501, detail="Not implemented")


@router.delete("/accounts/{id}")
async def delete_account(id: str):
    """
    Archive account (soft delete).

    TODO Phase 1.4:
    - Set is_archived = true (don't hard delete)
    - Prevent deletion if is_default = true (must reassign first)
    - Return success status

    Args:
        id: Account UUID

    Returns:
        dict: Success message
    """
    raise HTTPException(status_code=501, detail="Not implemented")
