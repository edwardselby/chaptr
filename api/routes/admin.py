"""
Admin endpoints for database management.

Provides destructive operations for development and user-specific resets:
- POST /api/admin/clear-changelog - Clear user's change log entries
- POST /api/admin/nuclear-reset - Clear entire database (dev only, password protected, super_admin only)

Multi-tenancy: Operations are scoped to the current user's tenant where appropriate.
"""

from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Body
from pydantic import BaseModel

from api.config import MongoDB, settings
from api.utils.auth import get_current_user, get_current_super_admin_user
from api.utils.db import utc_now


router = APIRouter()


def get_tenant_id(current_user: dict) -> UUID:
    """
    Extract tenant_id from current user for multi-tenancy filtering.

    :param current_user: Current user dict from JWT token
    :type current_user: dict
    :return: Tenant UUID
    :rtype: UUID
    """
    return UUID(current_user["tenant_id"])


class NuclearResetRequest(BaseModel):
    """Request model for nuclear reset with password confirmation."""
    password: str


@router.post("/admin/clear-changelog")
async def clear_user_changelog(current_user: dict = Depends(get_current_user)):
    """
    Clear change_log entries for the current user within their tenant.

    Non-destructive operation that only affects this user's sync history
    within their tenant. Other users' and tenants' change logs are preserved.

    Multi-tenancy: Only deletes change_log entries for the current tenant.

    Use case: User wants a fresh start without old change log entries
    affecting future syncs.

    Returns:
        dict: Number of change_log entries deleted
    """
    db = MongoDB.get_database()
    user_id = current_user["id"]
    tenant_id = get_tenant_id(current_user)

    # Delete all change_log entries where changed_by matches this user AND tenant
    # Note: changed_by is the user who made the change, not changed_by_client
    result = await db.change_log.delete_many({
        "tenant_id": str(tenant_id),  # Multi-tenancy isolation
        "changed_by": user_id
    })

    deleted_count = result.deleted_count

    return {
        "deleted_count": deleted_count,
        "message": f"Cleared {deleted_count} change log entries for user {user_id}"
    }


@router.post("/admin/nuclear-reset")
async def nuclear_reset(
    request: NuclearResetRequest,
    current_user: dict = Depends(get_current_super_admin_user)
):
    """
    🔴 NUCLEAR RESET - Wipes entire database (super_admin only).

    ⚠️ DESTRUCTIVE OPERATION - CANNOT BE UNDONE ⚠️

    This operation:
    - Deletes ALL accounts, stories, events, recurring rules
    - Deletes ALL change_log entries (all users)
    - Deletes ALL conflicts
    - Preserves only: users and settings

    Multi-tenancy: Requires super_admin role. Affects all tenants.
    Intended for development/testing only.
    Requires admin password from environment (ADMIN_PASSWORD)

    Returns:
        dict: Counts of deleted documents per collection
    """
    # Password check - require ADMIN_PASSWORD from settings
    if not settings.admin_password:
        raise HTTPException(
            status_code=500,
            detail="ADMIN_PASSWORD environment variable not set"
        )

    if request.password != settings.admin_password:
        raise HTTPException(status_code=403, detail="Invalid password")

    db = MongoDB.get_database()

    # Delete all data collections
    accounts_result = await db.accounts.delete_many({})
    stories_result = await db.stories.delete_many({})
    events_result = await db.events.delete_many({})
    recurring_rules_result = await db.recurring_rules.delete_many({})
    change_log_result = await db.change_log.delete_many({})
    conflicts_result = await db.conflicts.delete_many({})

    # Note: users and settings are preserved

    return {
        "success": True,
        "message": "Nuclear reset complete - all data wiped",
        "deleted": {
            "accounts": accounts_result.deleted_count,
            "stories": stories_result.deleted_count,
            "events": events_result.deleted_count,
            "recurring_rules": recurring_rules_result.deleted_count,
            "change_log": change_log_result.deleted_count,
            "conflicts": conflicts_result.deleted_count
        },
        "preserved": ["users", "settings"]
    }
