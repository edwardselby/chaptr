"""
Recurring rule management endpoints.

Provides CRUD operations for recurring event rules (salary, rent, subscriptions).

Note: Event generation logic (±1 month window) is deferred to Phase 7.
Phase 1.4 implements CRUD operations only - no event materialization yet.
"""

from fastapi import APIRouter, Depends
from uuid import UUID

from api.config import MongoDB
from api.models import RecurringRule, RecurringRuleCreate, RecurringRuleUpdate
from api.repositories.recurring_rules import RecurringRuleRepository
from api.utils.auth import get_current_user

router = APIRouter()


def get_recurring_rule_repo() -> RecurringRuleRepository:
    """
    Dependency injection for RecurringRuleRepository.

    :return: Initialized RecurringRuleRepository
    :rtype: RecurringRuleRepository
    """
    db = MongoDB.get_database()
    return RecurringRuleRepository(db)


def get_tenant_id(current_user: dict) -> UUID:
    """
    Extract tenant_id from current user for multi-tenancy filtering.

    :param current_user: Current user dict from JWT token
    :type current_user: dict
    :return: Tenant UUID
    :rtype: UUID
    """
    return UUID(current_user["tenant_id"])


@router.get("/recurring-rules", response_model=list[RecurringRule])
async def list_recurring_rules(
    current_user: dict = Depends(get_current_user),
    repo: RecurringRuleRepository = Depends(get_recurring_rule_repo)
):
    """
    List all recurring rules for current tenant.

    Returns all recurring event rules (salary, rent, subscriptions, etc.).

    Multi-tenancy: Only returns rules belonging to the current user's tenant.

    Note: Event generation from these rules (±1 month window) is implemented
    in Phase 7. This endpoint returns rule definitions only.

    :param repo: Injected RecurringRuleRepository
    :type repo: RecurringRuleRepository
    :return: List of recurring rules
    :rtype: list[RecurringRule]

    :Example:

    ```bash
    curl http://localhost:8000/api/recurring-rules
    ```
    """
    tenant_id = get_tenant_id(current_user)
    return await repo.list_for_tenant(tenant_id)


@router.get("/recurring-rules/{rule_id}", response_model=RecurringRule)
async def get_recurring_rule(
    rule_id: UUID,
    current_user: dict = Depends(get_current_user),
    repo: RecurringRuleRepository = Depends(get_recurring_rule_repo)
):
    """
    Get single recurring rule by ID.

    Multi-tenancy: Only returns rule if it belongs to the current user's tenant.

    :param rule_id: Recurring rule UUID
    :type rule_id: UUID
    :param repo: Injected RecurringRuleRepository
    :type repo: RecurringRuleRepository
    :return: Recurring rule details
    :rtype: RecurringRule
    :raises ResourceNotFoundError: If rule not found (404)

    :Example:

    ```bash
    curl http://localhost:8000/api/recurring-rules/{rule-id}
    ```
    """
    tenant_id = get_tenant_id(current_user)
    return await repo.get_for_tenant(rule_id, tenant_id)


@router.post("/recurring-rules", response_model=RecurringRule, status_code=201)
async def create_recurring_rule(
    data: RecurringRuleCreate,
    current_user: dict = Depends(get_current_user),
    repo: RecurringRuleRepository = Depends(get_recurring_rule_repo)
):
    """
    Create new recurring rule.

    Business Rules:
    - account_id must reference existing, non-archived account
    - Frequency (weekly, monthly, annual) determines day interpretation:
      - Weekly: day 1-7 (Monday=1, Sunday=7)
      - Monthly/Annual: day 1-31 (day of month)
    - end_date optional (null = ongoing)

    Note: Event generation from this rule (±1 month window) is implemented
    in Phase 7. Creating a rule does not create events yet.

    :param data: Recurring rule creation data
    :type data: RecurringRuleCreate
    :param repo: Injected RecurringRuleRepository
    :type repo: RecurringRuleRepository
    :return: Created recurring rule
    :rtype: RecurringRule
    :raises ValidationError: If business rules violated (422)

    :Example:

    ```bash
    # Create monthly salary rule
    curl -X POST http://localhost:8000/api/recurring-rules \\
      -H "Content-Type: application/json" \\
      -d '{
        "description": "Monthly Salary",
        "amount": 3000,
        "currency": "GBP",
        "account_id": "{account-id}",
        "frequency": "monthly",
        "day": 25,
        "start_date": "2025-01-01"
      }'

    # Create weekly coffee expense
    curl -X POST http://localhost:8000/api/recurring-rules \\
      -H "Content-Type: application/json" \\
      -d '{
        "description": "Weekly Coffee",
        "amount": -25,
        "currency": "GBP",
        "account_id": "{account-id}",
        "frequency": "weekly",
        "day": 1,
        "start_date": "2025-01-06"
      }'
    ```

    Multi-tenancy: Rule is created in the current user's tenant.
    """
    tenant_id = get_tenant_id(current_user)
    return await repo.create(data, current_user=current_user, client_id=None, tenant_id=tenant_id)


@router.put("/recurring-rules/{rule_id}", response_model=RecurringRule)
async def update_recurring_rule(
    rule_id: UUID,
    data: RecurringRuleUpdate,
    current_user: dict = Depends(get_current_user),
    repo: RecurringRuleRepository = Depends(get_recurring_rule_repo)
):
    """
    Update existing recurring rule.

    Supports partial updates - only provided fields are updated.

    Business Rules:
    - Modification affects future events only
    - Past generated events remain unchanged
    - account_id must exist and not be archived if being updated

    Multi-tenancy: Only updates rule if it belongs to the current user's tenant.

    Note: Event regeneration from updated rules is implemented in Phase 7.
    Updating a rule in Phase 1.4 only updates the rule definition.

    :param rule_id: Recurring rule UUID
    :type rule_id: UUID
    :param data: Update data (partial)
    :type data: RecurringRuleUpdate
    :param repo: Injected RecurringRuleRepository
    :type repo: RecurringRuleRepository
    :return: Updated recurring rule
    :rtype: RecurringRule
    :raises ResourceNotFoundError: If rule not found (404)
    :raises ValidationError: If validation fails (422)

    :Example:

    ```bash
    # Update salary amount
    curl -X PUT http://localhost:8000/api/recurring-rules/{rule-id} \\
      -H "Content-Type: application/json" \\
      -d '{"amount": 3200}'

    # Update frequency
    curl -X PUT http://localhost:8000/api/recurring-rules/{rule-id} \\
      -H "Content-Type: application/json" \\
      -d '{
        "frequency": "weekly",
        "day": 5
      }'
    ```
    """
    # Verify rule belongs to tenant before update
    tenant_id = get_tenant_id(current_user)
    await repo.get_for_tenant(rule_id, tenant_id)
    return await repo.update(rule_id, data, current_user=current_user, client_id=None)


@router.delete("/recurring-rules/{rule_id}", status_code=204)
async def delete_recurring_rule(
    rule_id: UUID,
    current_user: dict = Depends(get_current_user),
    repo: RecurringRuleRepository = Depends(get_recurring_rule_repo)
):
    """
    Delete recurring rule (hard delete).

    Business Rules:
    - Removes the rule definition permanently
    - Future events will no longer be generated (Phase 7)
    - Past generated events are retained

    Multi-tenancy: Only deletes rule if it belongs to the current user's tenant.

    Note: Event cleanup from deleted rules is implemented in Phase 7.
    Deleting a rule in Phase 1.4 only deletes the rule definition.

    :param rule_id: Recurring rule UUID
    :type rule_id: UUID
    :param repo: Injected RecurringRuleRepository
    :type repo: RecurringRuleRepository
    :return: No content (204)
    :raises ResourceNotFoundError: If rule not found (404)

    :Example:

    ```bash
    curl -X DELETE http://localhost:8000/api/recurring-rules/{rule-id}
    ```
    """
    # Verify rule belongs to tenant before delete
    tenant_id = get_tenant_id(current_user)
    await repo.get_for_tenant(rule_id, tenant_id)
    await repo.delete(rule_id, current_user=current_user, client_id=None)
    return None
