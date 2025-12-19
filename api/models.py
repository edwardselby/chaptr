"""
Pydantic models for data validation.

Defines all data models with field validation for CHAPTR entities.

Implementation Status: SKELETON - Phase 1.3
TODO Phase 1.3: Add complete field definitions per spec
"""

from pydantic import BaseModel
from enum import Enum
from datetime import datetime, date
from typing import Optional
from decimal import Decimal


# ==================== Enums ====================

class FundingMode(str, Enum):
    """Story funding mode options."""
    PROJECTED = "projected"
    FIXED = "fixed"
    PROJECTED_PLUS = "projected_plus"


class GoalType(str, Enum):
    """Story goal type options."""
    END_WITH_AT_LEAST = "end_with_at_least"
    SPEND_UP_TO = "spend_up_to"
    NONE = "none"


class Frequency(str, Enum):
    """Recurring event frequency options."""
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    ANNUAL = "annual"


class UserRole(str, Enum):
    """User role options."""
    ADMIN = "admin"
    USER = "user"


class ConflictType(str, Enum):
    """Conflict type options."""
    EDIT_EDIT = "edit_edit"
    DELETE_EDIT = "delete_edit"


# ==================== Account Models ====================

class AccountBase(BaseModel):
    """Base account model with common fields."""
    # TODO Phase 1.3: Add all fields per spec (Core Concepts > Accounts)
    # Fields: name, currency, current_balance, balance_updated_at,
    #         is_default, is_archived, pending_reconciliation
    pass


class AccountCreate(AccountBase):
    """Model for creating an account."""
    # TODO Phase 1.3: Add required fields for creation
    pass


class AccountUpdate(AccountBase):
    """Model for updating an account."""
    # TODO Phase 1.3: All fields optional for partial updates
    pass


class Account(AccountBase):
    """Complete account model with all fields."""
    # TODO Phase 1.3: Add id, created_at, updated_at
    pass


# ==================== Story Models ====================

class StoryBase(BaseModel):
    """Base story model with common fields."""
    # TODO Phase 1.3: Add all fields per spec (Core Concepts > Stories)
    # Fields: name, start_date, end_date, default_account_id, funding_mode,
    #         funding_amount, goal_type, goal_amount, display_currency
    pass


class StoryCreate(StoryBase):
    """Model for creating a story."""
    # TODO Phase 1.3: Add required fields for creation
    pass


class StoryUpdate(StoryBase):
    """Model for updating a story."""
    # TODO Phase 1.3: All fields optional for partial updates
    pass


class Story(StoryBase):
    """Complete story model with all fields."""
    # TODO Phase 1.3: Add id, created_at, created_by, updated_at, updated_by
    pass


# ==================== Event Models ====================

class EventBase(BaseModel):
    """Base event model with common fields."""
    # TODO Phase 1.3: Add all fields per spec (Core Concepts > Events)
    # Fields: date, description, amount, currency, rate_to_base, account_id,
    #         story_id, is_baseline, is_hypothetical, is_auto_adjustment
    pass


class EventCreate(EventBase):
    """Model for creating an event."""
    # TODO Phase 1.3: Add required fields for creation
    # Note: account_id resolved via hierarchy if not provided
    pass


class EventUpdate(EventBase):
    """Model for updating an event."""
    # TODO Phase 1.3: All fields optional for partial updates
    pass


class Event(EventBase):
    """Complete event model with all fields."""
    # TODO Phase 1.3: Add id, created_at, created_by, updated_at, updated_by,
    #                  recurring_rule_id (optional)
    pass


# ==================== Recurring Rule Models ====================

class RecurringRuleBase(BaseModel):
    """Base recurring rule model."""
    # TODO Phase 1.3: Add fields per spec (recurring_rules collection)
    # Fields: description, amount, currency, account_id, frequency, day,
    #         start_date, end_date
    pass


class RecurringRuleCreate(RecurringRuleBase):
    """Model for creating a recurring rule."""
    pass


class RecurringRule(RecurringRuleBase):
    """Complete recurring rule model."""
    # TODO Phase 1.3: Add id, created_at, updated_at
    pass


# ==================== User Models ====================

class UserBase(BaseModel):
    """Base user model."""
    # TODO Phase 1.3: Add fields (username, email, role)
    pass


class UserCreate(UserBase):
    """Model for creating a user."""
    # TODO Phase 1.3: Add password field (plain, will be hashed)
    pass


class User(UserBase):
    """Complete user model."""
    # TODO Phase 1.3: Add id, password_hash, created_at, updated_at
    # Note: password_hash not exposed in responses
    pass


# ==================== Settings Models ====================

class SettingsBase(BaseModel):
    """Base settings model."""
    # TODO Phase 1.3: Add fields (base_currency, rates, baseline_display_months,
    #                              date_format)
    pass


class SettingsUpdate(SettingsBase):
    """Model for updating settings."""
    # TODO Phase 1.3: All fields optional
    pass


class Settings(SettingsBase):
    """Complete settings model."""
    # TODO Phase 1.3: Add id, created_at, updated_at
    pass


# ==================== Sync Models ====================

class ChangeItem(BaseModel):
    """Single change in sync request."""
    # TODO Phase 3: Add fields (entity_type, entity_id, action, data, base_updated_at)
    pass


class SyncRequest(BaseModel):
    """Sync request from client."""
    # TODO Phase 3: Add fields (client_id, last_sync_at, changes)
    pass


class ConflictItem(BaseModel):
    """Conflict detected during sync."""
    # TODO Phase 3: Add fields (entity_type, entity_id, conflict_type,
    #                           client_version, server_version)
    pass


class SyncResponse(BaseModel):
    """Sync response to client."""
    # TODO Phase 3: Add fields (applied, conflicts, server_changes,
    #                           sync_timestamp, full_sync_required)
    pass


# ==================== Conflict Resolution Models ====================

class Conflict(BaseModel):
    """Conflict record."""
    # TODO Phase 6: Add fields (id, entity_type, entity_id, local_version,
    #                           server_version, local_user_id, server_user_id,
    #                           conflict_type, detected_at, resolved_at,
    #                           resolved_by, resolution)
    pass


class ConflictResolution(BaseModel):
    """Conflict resolution request."""
    # TODO Phase 6: Add fields (resolution: 'kept_local' or 'kept_server')
    pass
