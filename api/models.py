"""
Pydantic models for data validation.

Defines all data models with field validation for CHAPTR entities.

Implementation Status: SKELETON - Phase 1.3
TODO Phase 1.3: Add complete field definitions per spec
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator, model_validator
from enum import Enum
from datetime import datetime, date
from typing import Optional
from decimal import Decimal
from uuid import UUID


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
    """
    Base account model representing where money actually lives.

    Accounts are reference points for sanity-checking and per-account
    balance tracking. Balances are manually updated (not synced to banks).
    """
    name: str = Field(..., min_length=1, description="Account name (e.g., Monzo, HSBC)")
    currency: str = Field(..., min_length=3, max_length=3, description="Currency code (GBP, CAD, USD)")
    current_balance: Decimal = Field(..., description="Current account balance (manually updated snapshot)")
    balance_updated_at: Optional[datetime] = Field(default=None, description="When balance was last updated (set on manual balance updates)")
    is_default: bool = Field(default=False, description="Is this the global default spending account?")
    is_archived: bool = Field(default=False, description="Archived accounts are hidden but retained for history")
    pending_reconciliation: bool = Field(default=False, description="Balance updated but reconciliation not yet run?")

    @field_validator('currency')
    @classmethod
    def validate_currency_code(cls, v: str) -> str:
        """Validate currency code is 3 uppercase letters."""
        if not v.isupper() or len(v) != 3:
            raise ValueError('Currency code must be 3 uppercase letters (e.g., GBP, CAD, USD)')
        return v


class AccountCreate(AccountBase):
    """
    Model for creating an account.

    Note: Exactly one account must have is_default=true (enforced at API level).
    """
    pass


class AccountUpdate(BaseModel):
    """
    Model for updating an account (all fields optional for partial updates).
    """
    name: Optional[str] = Field(default=None, min_length=1)
    currency: Optional[str] = Field(default=None, min_length=3, max_length=3)
    current_balance: Optional[Decimal] = Field(default=None)
    balance_updated_at: Optional[datetime] = Field(default=None)
    is_default: Optional[bool] = Field(default=None)
    is_archived: Optional[bool] = Field(default=None)
    pending_reconciliation: Optional[bool] = Field(default=None)

    @field_validator('currency')
    @classmethod
    def validate_currency_code(cls, v: Optional[str]) -> Optional[str]:
        """Validate currency code is 3 uppercase letters if provided."""
        if v and (not v.isupper() or len(v) != 3):
            raise ValueError('Currency code must be 3 uppercase letters')
        return v


class Account(AccountBase):
    """
    Complete account model with metadata.

    Accounts cannot be deleted, only archived. Archived accounts
    retain historical events but are hidden from active account lists.
    """
    id: UUID = Field(..., description="Unique account identifier")
    created_at: datetime = Field(..., description="Account creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")


# ==================== Story Models ====================

class StoryBase(BaseModel):
    """
    Base story model - a container for related financial activity.

    Stories are layers on top of shared reality - they don't hold money,
    they represent planned spending/income for a specific context
    (e.g., canada-trip, volvo, skiing-2025).
    """
    name: str = Field(..., min_length=1, description="Story name (e.g., canada-trip, volvo)")
    start_date: date = Field(..., description="When this story begins")
    end_date: Optional[date] = Field(default=None, description="When this story ends (null=ongoing)")
    default_account_id: Optional[UUID] = Field(default=None, description="Default account for events in this story")
    funding_mode: FundingMode = Field(default=FundingMode.PROJECTED, description="How starting balance is determined")
    funding_amount: Optional[Decimal] = Field(default=None, description="Fixed or adjustment amount for funding")
    goal_type: GoalType = Field(default=GoalType.NONE, description="Optional goal for this story")
    goal_amount: Optional[Decimal] = Field(default=None, description="Target amount if goal set")
    display_currency: str = Field(..., min_length=3, max_length=3, description="Currency for this story's view")

    @field_validator('display_currency')
    @classmethod
    def validate_currency_code(cls, v: str) -> str:
        """Validate currency code is 3 uppercase letters."""
        if not v.isupper() or len(v) != 3:
            raise ValueError('Currency code must be 3 uppercase letters (e.g., GBP, CAD, USD)')
        return v

    @model_validator(mode='after')
    def validate_date_range(self):
        """Validate end_date is after start_date if provided."""
        if self.end_date and self.end_date <= self.start_date:
            raise ValueError('end_date must be after start_date')
        return self

    @model_validator(mode='after')
    def validate_funding(self):
        """Validate funding_amount required for FIXED/PROJECTED_PLUS modes."""
        if self.funding_mode in [FundingMode.FIXED, FundingMode.PROJECTED_PLUS]:
            if self.funding_amount is None:
                raise ValueError(f'funding_amount required for {self.funding_mode.value} mode')
        return self

    @model_validator(mode='after')
    def validate_goal(self):
        """Validate goal_amount required when goal_type is set."""
        if self.goal_type != GoalType.NONE and self.goal_amount is None:
            raise ValueError('goal_amount required when goal_type is set')
        return self


class StoryCreate(StoryBase):
    """
    Model for creating a story.

    Story default account is used as fallback for events in this story.
    If not set, falls back to global default account.
    """
    pass


class StoryUpdate(BaseModel):
    """
    Model for updating a story (all fields optional for partial updates).

    Changing default_account_id only affects future events, not existing ones.
    """
    name: Optional[str] = Field(default=None, min_length=1)
    start_date: Optional[date] = Field(default=None)
    end_date: Optional[date] = Field(default=None)
    default_account_id: Optional[UUID] = Field(default=None)
    funding_mode: Optional[FundingMode] = Field(default=None)
    funding_amount: Optional[Decimal] = Field(default=None)
    goal_type: Optional[GoalType] = Field(default=None)
    goal_amount: Optional[Decimal] = Field(default=None)
    display_currency: Optional[str] = Field(default=None, min_length=3, max_length=3)

    @field_validator('display_currency')
    @classmethod
    def validate_currency_code(cls, v: Optional[str]) -> Optional[str]:
        """Validate currency code is 3 uppercase letters if provided."""
        if v and (not v.isupper() or len(v) != 3):
            raise ValueError('Currency code must be 3 uppercase letters')
        return v

    @model_validator(mode='after')
    def validate_date_range(self):
        """Validate end_date is after start_date if both provided."""
        if self.start_date and self.end_date and self.end_date <= self.start_date:
            raise ValueError('end_date must be after start_date')
        return self

    @model_validator(mode='after')
    def validate_funding(self):
        """Validate funding_amount required for FIXED/PROJECTED_PLUS modes if funding_mode provided."""
        if self.funding_mode in [FundingMode.FIXED, FundingMode.PROJECTED_PLUS]:
            if self.funding_amount is None:
                raise ValueError(f'funding_amount required for {self.funding_mode.value} mode')
        return self

    @model_validator(mode='after')
    def validate_goal(self):
        """Validate goal_amount required when goal_type is set."""
        if self.goal_type and self.goal_type != GoalType.NONE and self.goal_amount is None:
            raise ValueError('goal_amount required when goal_type is set')
        return self


class Story(StoryBase):
    """
    Complete story model with metadata and user tracking.

    Stories can have overlapping date ranges. The system handles this
    via gap indicators in projections.
    """
    id: UUID = Field(..., description="Unique story identifier")
    created_at: datetime = Field(..., description="Story creation timestamp")
    created_by: UUID = Field(..., description="User who created the story")
    updated_at: datetime = Field(..., description="Last update timestamp")
    updated_by: UUID = Field(..., description="User who last updated the story")


# ==================== Event Models ====================

class EventBase(BaseModel):
    """
    Base event model representing a point in time where money moves.

    Events belong to either baseline or a story. Account resolution happens
    at creation via hierarchy and is stored permanently.
    """
    event_date: date = Field(..., alias='date', serialization_alias='date', description="When this event occurs")
    description: str = Field(..., min_length=1, description="Event description (e.g., Car rental, Hotel deposit)")
    amount: Decimal = Field(..., description="Amount (positive=income, negative=expense)")
    currency: str = Field(..., min_length=3, max_length=3, description="Native currency code (GBP, CAD, USD)")
    rate_to_base: Decimal = Field(..., gt=0, description="Conversion rate to base currency (locked at creation)")
    account_id: UUID = Field(..., description="Account this event affects (REQUIRED, resolved at creation)")
    story_id: Optional[UUID] = Field(default=None, description="Story this belongs to (null=baseline)")
    is_baseline: bool = Field(default=False, description="Is this a baseline event?")
    is_hypothetical: bool = Field(default=False, description="Is this planned/hypothetical funding?")
    is_auto_adjustment: bool = Field(default=False, description="Created by reconciliation system?")

    @field_validator('currency')
    @classmethod
    def validate_currency_code(cls, v: str) -> str:
        """Validate currency code is 3 uppercase letters."""
        if not v.isupper() or len(v) != 3:
            raise ValueError('Currency code must be 3 uppercase letters (e.g., GBP, CAD, USD)')
        return v


class EventCreate(EventBase):
    """
    Model for creating an event.

    Account resolution hierarchy (resolved at API level, stored permanently):
    1. User specifies account_id → use it
    2. Story's default_account_id → use it
    3. Global default account → use it (fallback)

    Currency and account are independent - a GBP event can be assigned to a CAD account.
    """
    pass


class EventUpdate(BaseModel):
    """
    Model for updating an event (all fields optional for partial updates).

    Past events CAN be edited - users may need to correct mistakes.
    Editing triggers recalculation of all subsequent running balances.
    """
    event_date: Optional[date] = Field(default=None, alias='date', serialization_alias='date')
    description: Optional[str] = Field(default=None, min_length=1)
    amount: Optional[Decimal] = Field(default=None)
    currency: Optional[str] = Field(default=None, min_length=3, max_length=3)
    rate_to_base: Optional[Decimal] = Field(default=None, gt=0)
    account_id: Optional[UUID] = Field(default=None)
    story_id: Optional[UUID] = Field(default=None)
    is_baseline: Optional[bool] = Field(default=None)
    is_hypothetical: Optional[bool] = Field(default=None)
    is_auto_adjustment: Optional[bool] = Field(default=None)

    @field_validator('currency')
    @classmethod
    def validate_currency_code(cls, v: Optional[str]) -> Optional[str]:
        """Validate currency code is 3 uppercase letters if provided."""
        if v and (not v.isupper() or len(v) != 3):
            raise ValueError('Currency code must be 3 uppercase letters')
        return v


class Event(EventBase):
    """
    Complete event model with metadata and user tracking.

    Same-day ordering: Events on same date ordered by amount DESC (income first),
    then created_at ASC (earlier created first) to minimize balance dips.
    """
    id: UUID = Field(..., description="Unique event identifier")
    created_at: datetime = Field(..., description="Event creation timestamp (for same-day ordering)")
    created_by: UUID = Field(..., description="User who created the event")
    updated_at: datetime = Field(..., description="Last update timestamp")
    updated_by: UUID = Field(..., description="User who last updated the event")
    recurring_rule_id: Optional[UUID] = Field(default=None, description="Recurring rule that generated this event")


# ==================== Recurring Rule Models ====================

class RecurringRuleBase(BaseModel):
    """
    Base recurring rule model for generating events.

    Recurring events (salary, rent, subscriptions, etc.) are stored as rules
    and materialized as actual event rows within a generation window (±1 month).
    """
    description: str = Field(..., min_length=1, description="Rule description (e.g., Salary, Rent)")
    amount: Decimal = Field(..., description="Amount (positive=income, negative=expense)")
    currency: str = Field(..., min_length=3, max_length=3, description="Currency code (GBP, CAD, USD)")
    account_id: UUID = Field(..., description="Account this rule applies to")
    frequency: Frequency = Field(..., description="Recurrence frequency (weekly, monthly, annual)")
    day: int = Field(..., ge=1, le=31, description="Day of week (1-7) or month (1-31)")
    start_date: date = Field(..., description="First occurrence date")
    end_date: Optional[date] = Field(default=None, description="Last occurrence date (null=ongoing)")

    @field_validator('currency')
    @classmethod
    def validate_currency_code(cls, v: str) -> str:
        """Validate currency code is 3 uppercase letters."""
        if not v.isupper() or len(v) != 3:
            raise ValueError('Currency code must be 3 uppercase letters (e.g., GBP, CAD, USD)')
        return v

    @model_validator(mode='after')
    def validate_day_for_frequency(self):
        """Validate day range based on frequency."""
        if self.frequency == Frequency.WEEKLY and not (1 <= self.day <= 7):
            raise ValueError('Weekly frequency requires day 1-7 (Monday=1, Sunday=7)')
        if self.frequency in [Frequency.MONTHLY, Frequency.ANNUAL] and not (1 <= self.day <= 31):
            raise ValueError('Monthly/Annual frequency requires day 1-31')
        return self

    @model_validator(mode='after')
    def validate_date_range(self):
        """Validate end_date is after start_date if provided."""
        if self.end_date and self.end_date <= self.start_date:
            raise ValueError('end_date must be after start_date')
        return self


class RecurringRuleCreate(RecurringRuleBase):
    """
    Model for creating a recurring rule.

    Events are generated as real rows within generation window (±1 month).
    Modification affects future events only; past events unchanged.
    """
    pass


class RecurringRuleUpdate(BaseModel):
    """
    Model for updating a recurring rule (all fields optional for partial updates).

    Updating a rule affects only future events; past generated events remain unchanged.
    """
    description: Optional[str] = Field(default=None, min_length=1)
    amount: Optional[Decimal] = Field(default=None)
    currency: Optional[str] = Field(default=None, min_length=3, max_length=3)
    account_id: Optional[UUID] = Field(default=None)
    frequency: Optional[Frequency] = Field(default=None)
    day: Optional[int] = Field(default=None, ge=1, le=31)
    start_date: Optional[date] = Field(default=None)
    end_date: Optional[date] = Field(default=None)

    @field_validator('currency')
    @classmethod
    def validate_currency_code(cls, v: Optional[str]) -> Optional[str]:
        """Validate currency code is 3 uppercase letters if provided."""
        if v and (not v.isupper() or len(v) != 3):
            raise ValueError('Currency code must be 3 uppercase letters')
        return v

    @model_validator(mode='after')
    def validate_day_for_frequency(self):
        """Validate day range based on frequency if both provided."""
        if self.frequency and self.day:
            if self.frequency == Frequency.WEEKLY and not (1 <= self.day <= 7):
                raise ValueError('Weekly frequency requires day 1-7 (Monday=1, Sunday=7)')
            if self.frequency in [Frequency.MONTHLY, Frequency.ANNUAL] and not (1 <= self.day <= 31):
                raise ValueError('Monthly/Annual frequency requires day 1-31')
        return self

    @model_validator(mode='after')
    def validate_date_range(self):
        """Validate end_date is after start_date if both provided."""
        if self.start_date and self.end_date and self.end_date <= self.start_date:
            raise ValueError('end_date must be after start_date')
        return self


class RecurringRule(RecurringRuleBase):
    """
    Complete recurring rule model with metadata.

    Lifecycle: Creation generates events, modification updates future events,
    deletion removes rule and future events (past events retained).
    """
    id: UUID = Field(..., description="Unique rule identifier")
    created_at: datetime = Field(..., description="Rule creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")


# ==================== User Models ====================

class UserBase(BaseModel):
    """
    Base user model with role assignment and identity.

    Note: External auth assumed for credentials (email/password).
    Minimal fields for UI purposes and user tracking on events/stories.
    """
    username: str = Field(..., min_length=1, description="Display name for UI (e.g., 'Edward', 'Kat')")
    role: UserRole = Field(..., description="User role: admin or user")


class UserCreate(UserBase):
    """
    Model for creating a user.

    Inherits from UserBase - external authentication system
    handles credentials and identity.
    """
    pass


class User(UserBase):
    """
    Complete user model with unique identifier and metadata.

    Used for tracking created_by/updated_by/resolved_by fields
    on events, stories, and conflicts.
    """
    id: UUID = Field(..., description="Unique user identifier")
    created_at: datetime = Field(..., description="User account creation timestamp")


# ==================== Settings Models ====================

class SettingsBase(BaseModel):
    """
    Base settings model with application preferences and configuration.

    Settings are global (not per-user) and admin-only for modification.
    """
    base_currency: str = Field(..., min_length=3, max_length=3, description="Base currency for conversions (e.g., GBP)")
    default_currency: str = Field(..., min_length=3, max_length=3, description="Default currency for new items")
    date_format: str = Field(default="DD/MM/YYYY", description="Date display format")
    baseline_display_months: int = Field(default=1, ge=1, le=12, description="Months to show in baseline view")
    rates: dict[str, Decimal] = Field(default_factory=dict, description="Currency conversion rates (currency → rate)")
    server_url: str = Field(default="", description="Sync server URL")
    last_backup_date: Optional[datetime] = Field(default=None, description="Last backup timestamp")
    version: str = Field(default="1.0.0", description="Application version")

    @field_validator('base_currency', 'default_currency')
    @classmethod
    def validate_currency_code(cls, v: str) -> str:
        """Validate currency code is 3 uppercase letters."""
        if not v.isupper() or len(v) != 3:
            raise ValueError('Currency code must be 3 uppercase letters (e.g., GBP, CAD, USD)')
        return v

    @model_validator(mode='after')
    def validate_rates(self):
        """Validate all rate values are positive."""
        if self.rates:
            for currency, rate in self.rates.items():
                if rate <= 0:
                    raise ValueError(f'Rate for {currency} must be positive, got {rate}')
        return self


class SettingsUpdate(BaseModel):
    """
    Model for updating settings (all fields optional for partial updates).
    """
    base_currency: Optional[str] = Field(default=None, min_length=3, max_length=3)
    default_currency: Optional[str] = Field(default=None, min_length=3, max_length=3)
    date_format: Optional[str] = Field(default=None)
    baseline_display_months: Optional[int] = Field(default=None, ge=1, le=12)
    rates: Optional[dict[str, Decimal]] = Field(default=None)
    server_url: Optional[str] = Field(default=None)
    last_backup_date: Optional[datetime] = Field(default=None)
    version: Optional[str] = Field(default=None)

    @field_validator('base_currency', 'default_currency')
    @classmethod
    def validate_currency_code(cls, v: Optional[str]) -> Optional[str]:
        """Validate currency code is 3 uppercase letters if provided."""
        if v and (not v.isupper() or len(v) != 3):
            raise ValueError('Currency code must be 3 uppercase letters')
        return v

    @model_validator(mode='after')
    def validate_rates(self):
        """Validate all rate values are positive if rates provided."""
        if self.rates:
            for currency, rate in self.rates.items():
                if rate <= 0:
                    raise ValueError(f'Rate for {currency} must be positive, got {rate}')
        return self


class Settings(SettingsBase):
    """Complete settings model with metadata."""
    id: UUID = Field(..., description="Settings document ID")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")


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
