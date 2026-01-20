"""
Pydantic models for data validation.

Defines all data models with field validation for CHAPTR entities.

Implementation Status: SKELETON - Phase 1.3
TODO Phase 1.3: Add complete field definitions per spec
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator, model_validator, ConfigDict
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
    """User role options for multi-tenant authorization.

    - super_admin: System-level admin, can create admins (new tenants), has own tenant
    - admin: Tenant root/anchor, can create users, can promote users to admin (same tenant)
    - user: Regular user, belongs to a tenant, cannot create users
    """
    SUPER_ADMIN = "super_admin"
    ADMIN = "admin"
    USER = "user"


class ConflictType(str, Enum):
    """Conflict type options."""
    EDIT_EDIT = "edit_edit"
    DELETE_EDIT = "delete_edit"


class EntityType(str, Enum):
    """Entity types tracked in change_log."""
    EVENT = "event"
    ACCOUNT = "account"
    STORY = "story"
    RECURRING_RULE = "recurring_rule"


class AccountType(str, Enum):
    """Account type for balance interpretation and warning logic.

    - checking: Standard account, negative balance triggers warning
    - savings: Same behavior as checking
    - credit_card: Inverted logic, warning when exceeding credit limit
    """
    CHECKING = "checking"
    SAVINGS = "savings"
    CREDIT_CARD = "credit_card"


class ChangeAction(str, Enum):
    """Change actions tracked in change_log."""
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"


# ==================== Account Models ====================

class AccountBase(BaseModel):
    """
    Base account model representing where money actually lives.

    Accounts are reference points for sanity-checking and per-account
    balance tracking. Balances are manually updated (not synced to banks).

    Multi-tenancy: Accounts are isolated by tenant_id (admin's user_id).
    """
    name: str = Field(..., min_length=1, description="Account name (e.g., Monzo, HSBC)")
    currency: str = Field(..., min_length=3, max_length=3, description="Currency code (GBP, CAD, USD)")
    current_balance: Decimal = Field(..., max_digits=19, decimal_places=4, description="Current account balance (manually updated snapshot)")
    balance_updated_at: Optional[datetime] = Field(default=None, description="When balance was last updated (set on manual balance updates)")
    is_default: bool = Field(default=False, description="Is this the global default spending account?")
    is_archived: bool = Field(default=False, description="Archived accounts are hidden but retained for history")
    pending_reconciliation: bool = Field(default=False, description="Balance updated but reconciliation not yet run?")
    account_type: AccountType = Field(
        default=AccountType.CHECKING,
        description="Account type: checking, savings, or credit_card"
    )
    credit_limit: Optional[Decimal] = Field(
        default=None,
        max_digits=19,
        decimal_places=4,
        description="Credit limit (required for credit_card type, forbidden for others)"
    )
    tenant_id: Optional[UUID] = Field(default=None, description="Tenant identifier (admin's user_id) for multi-tenancy isolation")

    @field_validator('currency')
    @classmethod
    def validate_currency_code(cls, v: str) -> str:
        """Validate currency code is 3 uppercase letters."""
        if not v.isupper() or len(v) != 3:
            raise ValueError('Currency code must be 3 uppercase letters (e.g., GBP, CAD, USD)')
        return v

    @model_validator(mode='after')
    def validate_credit_limit(self):
        """Validate credit_limit is required for credit_card, forbidden for others."""
        if self.account_type == AccountType.CREDIT_CARD:
            if self.credit_limit is None:
                raise ValueError('credit_limit is required for credit_card accounts')
            if self.credit_limit <= 0:
                raise ValueError('credit_limit must be positive')
        else:
            if self.credit_limit is not None:
                raise ValueError('credit_limit is only valid for credit_card accounts')
        return self


class AccountCreate(AccountBase):
    """
    Model for creating an account.

    Note: Exactly one account must have is_default=true (enforced at API level).
    """
    pass


class AccountUpdate(BaseModel):
    """
    Model for updating an account (all fields optional for partial updates).

    Note: When changing account_type to credit_card, credit_limit must also be provided.
    When changing from credit_card to another type, credit_limit will be cleared.
    Full validation of account_type/credit_limit relationship happens at repository level
    after merging with existing account data.
    """
    name: Optional[str] = Field(default=None, min_length=1)
    currency: Optional[str] = Field(default=None, min_length=3, max_length=3)
    current_balance: Optional[Decimal] = Field(default=None, max_digits=19, decimal_places=4)
    balance_updated_at: Optional[datetime] = Field(default=None)
    is_default: Optional[bool] = Field(default=None)
    is_archived: Optional[bool] = Field(default=None)
    pending_reconciliation: Optional[bool] = Field(default=None)
    account_type: Optional[AccountType] = Field(default=None, description="Account type: checking, savings, or credit_card")
    credit_limit: Optional[Decimal] = Field(default=None, max_digits=19, decimal_places=4, description="Credit limit for credit_card accounts")

    @field_validator('currency')
    @classmethod
    def validate_currency_code(cls, v: Optional[str]) -> Optional[str]:
        """Validate currency code is 3 uppercase letters if provided."""
        if v and (not v.isupper() or len(v) != 3):
            raise ValueError('Currency code must be 3 uppercase letters')
        return v

    @field_validator('credit_limit')
    @classmethod
    def validate_credit_limit_positive(cls, v: Optional[Decimal]) -> Optional[Decimal]:
        """Validate credit_limit is positive if provided."""
        if v is not None and v <= 0:
            raise ValueError('credit_limit must be positive')
        return v


class Account(AccountBase):
    """
    Complete account model with metadata.

    Accounts cannot be deleted, only archived. Archived accounts
    retain historical events but are hidden from active account lists.

    Note: id, created_at, updated_at, and tenant_id are required fields.
    Generated by API layer (Phase 1.4) during creation.
    """
    id: UUID = Field(..., description="Unique account identifier")
    created_at: datetime = Field(..., description="Account creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    # Override tenant_id to be required for persisted entities (security)
    tenant_id: UUID = Field(..., description="Tenant identifier (admin's user_id) for multi-tenancy isolation")


# ==================== Story Models ====================

class StoryBase(BaseModel):
    """
    Base story model - a container for related financial activity.

    Stories are layers on top of shared reality - they don't hold money,
    they represent planned spending/income for a specific context
    (e.g., canada-trip, volvo, skiing-2025).

    Multi-tenancy: Stories are isolated by tenant_id (admin's user_id).
    """
    name: str = Field(..., min_length=1, description="Story name (e.g., canada-trip, volvo)")
    start_date: date = Field(..., description="When this story begins")
    end_date: Optional[date] = Field(default=None, description="When this story ends (null=ongoing)")
    default_account_id: Optional[UUID] = Field(default=None, description="Default account for events in this story")
    funding_mode: FundingMode = Field(default=FundingMode.PROJECTED, description="How starting balance is determined")
    funding_amount: Optional[Decimal] = Field(default=None, max_digits=19, decimal_places=4, description="Fixed or adjustment amount for funding")
    goal_type: GoalType = Field(default=GoalType.NONE, description="Optional goal for this story")
    goal_amount: Optional[Decimal] = Field(default=None, max_digits=19, decimal_places=4, description="Target amount if goal set")
    display_currency: str = Field(..., min_length=3, max_length=3, description="Currency for this story's view")
    is_archived: bool = Field(default=False, description="Archived stories are hidden but retained for history")
    tenant_id: Optional[UUID] = Field(default=None, description="Tenant identifier (admin's user_id) for multi-tenancy isolation")

    @field_validator('display_currency')
    @classmethod
    def validate_currency_code(cls, v: str) -> str:
        """Validate currency code is 3 uppercase letters."""
        if not v.isupper() or len(v) != 3:
            raise ValueError('Currency code must be 3 uppercase letters (e.g., GBP, CAD, USD)')
        return v

    @model_validator(mode='after')
    def validate_date_range(self):
        """Validate end_date is after or equal to start_date if provided."""
        if self.end_date and self.end_date < self.start_date:
            raise ValueError('end_date must be after or equal to start_date')
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

    Note: Validators check field relationships only when both fields are provided
    in the update. Full validation (e.g., ensuring funding_amount exists when
    changing funding_mode to FIXED) must happen at API level by merging with
    existing story data before applying update.
    """
    name: Optional[str] = Field(default=None, min_length=1)
    start_date: Optional[date] = Field(default=None)
    end_date: Optional[date] = Field(default=None)
    default_account_id: Optional[UUID] = Field(default=None)
    funding_mode: Optional[FundingMode] = Field(default=None)
    funding_amount: Optional[Decimal] = Field(default=None, max_digits=19, decimal_places=4)
    goal_type: Optional[GoalType] = Field(default=None)
    goal_amount: Optional[Decimal] = Field(default=None, max_digits=19, decimal_places=4)
    display_currency: Optional[str] = Field(default=None, min_length=3, max_length=3)
    is_archived: Optional[bool] = Field(default=None)

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

    # NOTE: Removed validate_funding and validate_goal from StoryUpdate
    # These validators cannot work correctly in partial update context where
    # only one field (e.g., funding_mode) might be provided without its related
    # field (e.g., funding_amount). The relationship must be validated at the
    # API layer after merging update data with existing record.
    # See: StoryBase validators for creation-time validation


class Story(StoryBase):
    """
    Complete story model with metadata and user tracking.

    Stories can have overlapping date ranges. The system handles this
    via gap indicators in projections.

    Note: id, created_at, updated_at, and tenant_id are required fields generated by API layer (Phase 1.4).
    created_by and updated_by are optional until authentication is implemented (Phase 1.5).
    """
    id: UUID = Field(..., description="Unique story identifier")
    created_at: datetime = Field(..., description="Story creation timestamp")
    created_by: Optional[UUID] = Field(default=None, description="User who created the story (requires auth)")
    updated_at: datetime = Field(..., description="Last update timestamp")
    updated_by: Optional[UUID] = Field(default=None, description="User who last updated the story (requires auth)")
    # Override tenant_id to be required for persisted entities (security)
    tenant_id: UUID = Field(..., description="Tenant identifier (admin's user_id) for multi-tenancy isolation")


# ==================== Event Models ====================

class EventBase(BaseModel):
    """
    Base event model representing a point in time where money moves.

    Events belong to either baseline or a story. Account resolution happens
    at creation via hierarchy and is stored permanently.

    Multi-tenancy: Events are isolated by tenant_id (admin's user_id).
    """
    model_config = ConfigDict(populate_by_name=True)

    event_date: date = Field(..., description="When this event occurs")
    description: str = Field(..., min_length=1, description="Event description (e.g., Car rental, Hotel deposit)")
    amount: Decimal = Field(..., max_digits=19, decimal_places=4, description="Amount (positive=income, negative=expense)")
    currency: str = Field(..., min_length=3, max_length=3, description="Native currency code (GBP, CAD, USD)")
    rate_to_base: Decimal = Field(..., gt=0, max_digits=19, decimal_places=8, description="Conversion rate to base currency (locked at creation)")
    account_id: UUID = Field(..., description="Account this event affects (REQUIRED, resolved at creation)")
    story_id: Optional[UUID] = Field(default=None, description="Story this belongs to (null=baseline)")
    is_baseline: bool = Field(default=False, description="Is this a baseline event?")
    is_hypothetical: bool = Field(default=False, description="Is this planned/hypothetical funding?")
    is_auto_adjustment: bool = Field(default=False, description="Created by reconciliation system?")
    is_opening_balance: bool = Field(default=False, description="System-created opening balance event?")
    tenant_id: Optional[UUID] = Field(default=None, description="Tenant identifier (admin's user_id) for multi-tenancy isolation")

    @field_validator('currency')
    @classmethod
    def validate_currency_code(cls, v: str) -> str:
        """Validate currency code is 3 uppercase letters."""
        if not v.isupper() or len(v) != 3:
            raise ValueError('Currency code must be 3 uppercase letters (e.g., GBP, CAD, USD)')
        return v

    @model_validator(mode='after')
    def validate_baseline_story_exclusivity(self):
        """Ensure baseline events and story events are mutually exclusive."""
        if self.is_baseline and self.story_id is not None:
            raise ValueError('Baseline events cannot belong to a story (story_id must be None when is_baseline=True)')
        return self


class EventCreate(EventBase):
    """
    Model for creating an event.

    Account resolution hierarchy (resolved at API level, stored permanently):
    1. User specifies account_id → use it
    2. Story's default_account_id → use it
    3. Global default account → use it (fallback)

    Rate locking (resolved at API level, locked from settings):
    - If rate_to_base not provided, automatically locked from current settings
    - If provided, uses explicit rate (for manual corrections)

    Currency and account are independent - a GBP event can be assigned to a CAD account.
    """
    # Override to make optional - resolved via 3-level hierarchy if not provided
    account_id: Optional[UUID] = Field(
        default=None,
        description="Optional account (resolved via hierarchy if not provided)"
    )

    # Override to make optional - auto-locked from settings if not provided
    rate_to_base: Optional[Decimal] = Field(
        default=None,
        gt=0,
        max_digits=19,
        decimal_places=8,
        description="Optional rate (auto-locked from settings if not provided)"
    )


class EventUpdate(BaseModel):
    """
    Model for updating an event (all fields optional for partial updates).

    Past events CAN be edited - users may need to correct mistakes.
    Editing triggers recalculation of all subsequent running balances.
    """
    model_config = ConfigDict(populate_by_name=True)

    event_date: Optional[date] = Field(default=None)
    description: Optional[str] = Field(default=None, min_length=1)
    amount: Optional[Decimal] = Field(default=None, max_digits=19, decimal_places=4)
    currency: Optional[str] = Field(default=None, min_length=3, max_length=3)
    rate_to_base: Optional[Decimal] = Field(default=None, gt=0, max_digits=19, decimal_places=8)
    account_id: Optional[UUID] = Field(default=None)
    story_id: Optional[UUID] = Field(default=None)
    is_baseline: Optional[bool] = Field(default=None)
    is_hypothetical: Optional[bool] = Field(default=None)
    is_auto_adjustment: Optional[bool] = Field(default=None)
    is_opening_balance: Optional[bool] = Field(default=None)

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

    Note: id, created_at, updated_at, and tenant_id are required fields generated by API layer (Phase 1.4).
    created_by and updated_by are optional until authentication is implemented (Phase 1.5).
    """
    id: UUID = Field(..., description="Unique event identifier")
    created_at: datetime = Field(..., description="Event creation timestamp (used for same-day ordering)")
    created_by: Optional[UUID] = Field(default=None, description="User who created the event (requires auth)")
    updated_at: datetime = Field(..., description="Last update timestamp")
    updated_by: Optional[UUID] = Field(default=None, description="User who last updated the event (requires auth)")
    recurring_rule_id: Optional[UUID] = Field(default=None, description="Recurring rule that generated this event")
    # Override tenant_id to be required for persisted entities (security)
    tenant_id: UUID = Field(..., description="Tenant identifier (admin's user_id) for multi-tenancy isolation")


# ==================== Recurring Rule Models ====================

class RecurringRuleBase(BaseModel):
    """
    Base recurring rule model for generating events.

    Recurring events (salary, rent, subscriptions, etc.) are stored as rules
    and materialized as actual event rows within a generation window (±1 month).

    Multi-tenancy: Recurring rules are isolated by tenant_id (admin's user_id).
    """
    description: str = Field(..., min_length=1, description="Rule description (e.g., Salary, Rent)")
    amount: Decimal = Field(..., max_digits=19, decimal_places=4, description="Amount (positive=income, negative=expense)")
    currency: str = Field(..., min_length=3, max_length=3, description="Currency code (GBP, CAD, USD)")
    account_id: UUID = Field(..., description="Account this rule applies to")
    frequency: Frequency = Field(..., description="Recurrence frequency (weekly, monthly, annual)")
    day: int = Field(..., ge=1, le=31, description="Day of week (1-7) or month (1-31)")
    start_date: date = Field(..., description="First occurrence date")
    end_date: Optional[date] = Field(default=None, description="Last occurrence date (null=ongoing)")
    tenant_id: Optional[UUID] = Field(default=None, description="Tenant identifier (admin's user_id) for multi-tenancy isolation")

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
        """Validate end_date is after or equal to start_date if provided."""
        if self.end_date and self.end_date < self.start_date:
            raise ValueError('end_date must be after or equal to start_date')
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
    amount: Optional[Decimal] = Field(default=None, max_digits=19, decimal_places=4)
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

    Note: id, created_at, updated_at, tenant_id, created_by, and updated_by are required fields
    generated by API layer (Phase 1.4+1.5).
    """
    id: UUID = Field(..., description="Unique rule identifier")
    created_at: datetime = Field(..., description="Rule creation timestamp")
    created_by: Optional[UUID] = Field(default=None, description="User who created the rule (Phase 1.5)")
    updated_at: datetime = Field(..., description="Last update timestamp")
    updated_by: Optional[UUID] = Field(default=None, description="User who last updated the rule (Phase 1.5)")
    # Override tenant_id to be required for persisted entities (security)
    tenant_id: UUID = Field(..., description="Tenant identifier (admin's user_id) for multi-tenancy isolation")


# ==================== User Models ====================

class UserBase(BaseModel):
    """
    Base user model with role assignment and identity.

    JWT authentication with username/password (self-contained, no external auth).
    Minimal fields for UI purposes and user tracking on events/stories.

    Multi-tenancy:
    - tenant_id identifies which tenant this user belongs to
    - For admin users: tenant_id == user.id (they anchor their own tenant)
    - For regular users: tenant_id == their admin's user_id
    """
    username: str = Field(..., min_length=1, description="Display name for UI (e.g., 'Edward', 'Kat')")
    role: UserRole = Field(..., description="User role: super_admin, admin, or user")
    tenant_id: Optional[UUID] = Field(default=None, description="Tenant identifier - admin's user_id (self-referencing for admins)")


class UserCreate(UserBase):
    """
    Model for creating a user - includes plain text password for hashing.

    Password is hashed using bcrypt before storage.
    Requirements: Min 8 chars, uppercase, lowercase, and number.
    """
    password: str = Field(..., min_length=8, description="Plain text password (min 8 chars, will be hashed)")

    @field_validator('password')
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        """
        Validate password strength requirements.

        Requirements:
        - Minimum 8 characters (enforced by Field)
        - At least one uppercase letter
        - At least one lowercase letter
        - At least one digit

        :param v: Password to validate
        :type v: str
        :return: Validated password
        :rtype: str
        :raises ValueError: If password doesn't meet strength requirements
        """
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.islower() for c in v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        return v


class User(UserBase):
    """
    Complete user model with unique identifier, password hash, and metadata.

    Used for authentication and tracking created_by/updated_by/resolved_by fields
    on events, stories, and conflicts.

    Note: id, created_at, and tenant_id are required fields generated by API layer.
    password_hash is bcrypt-hashed password (never stored in plain text).
    """
    id: UUID = Field(..., description="Unique user identifier")
    password_hash: str = Field(..., description="Bcrypt hashed password")
    created_at: datetime = Field(..., description="User account creation timestamp")
    updated_at: datetime = Field(..., description="Last modification timestamp")
    # Override tenant_id to be required for persisted entities (security)
    tenant_id: UUID = Field(..., description="Tenant identifier - admin's user_id (self-referencing for admins)")


class UserUpdate(BaseModel):
    """
    Partial update model for user modifications - all fields optional.

    Used for both admin user updates and self-service profile updates.
    For self-service, current_password is required when changing password.
    Role changes ignored for self-service (cannot self-promote).

    :Example:

    >>> # Admin update (can change any field)
    >>> admin_update = UserUpdate(username="NewName", role="admin")

    >>> # Self-service update (role ignored, current_password required for password change)
    >>> self_update = UserUpdate(username="NewName", password="NewPass1", current_password="OldPass1")
    """
    username: Optional[str] = Field(None, min_length=1, description="New username")
    role: Optional[UserRole] = Field(None, description="New role (admin-only)")
    password: Optional[str] = Field(None, min_length=8, description="New password")
    current_password: Optional[str] = Field(None, description="Current password (for self-service verification)")

    @field_validator('password')
    @classmethod
    def validate_password_strength(cls, v: Optional[str]) -> Optional[str]:
        """
        Validate password strength requirements if provided.

        Requirements:
        - Minimum 8 characters (enforced by Field)
        - At least one uppercase letter
        - At least one lowercase letter
        - At least one digit

        :param v: Password to validate
        :type v: Optional[str]
        :return: Validated password
        :rtype: Optional[str]
        :raises ValueError: If password doesn't meet strength requirements
        """
        if v is None:
            return v
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.islower() for c in v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        return v


class UserResponse(BaseModel):
    """
    Response model for user data - excludes password_hash.

    Used in list/get operations to ensure password hashes are never exposed.

    :Example:

    >>> # Convert User to UserResponse
    >>> user = User(id=..., username="Edward", role="admin", ...)
    >>> response = UserResponse(
    ...     id=user.id,
    ...     username=user.username,
    ...     role=user.role,
    ...     tenant_id=user.tenant_id,
    ...     created_at=user.created_at,
    ...     updated_at=user.updated_at
    ... )
    """
    id: UUID = Field(..., description="Unique user identifier")
    username: str = Field(..., description="User display name")
    role: UserRole = Field(..., description="User role (super_admin, admin, or user)")
    tenant_id: Optional[UUID] = Field(default=None, description="Tenant identifier for multi-tenancy")
    created_at: datetime = Field(..., description="User account creation timestamp")
    updated_at: datetime = Field(..., description="Last modification timestamp")

    @staticmethod
    def from_user(user: "User") -> "UserResponse":
        """
        Convert a User model to a UserResponse (excluding password_hash).

        :param user: Full user model
        :type user: User
        :return: User response without password hash
        :rtype: UserResponse
        """
        return UserResponse(
            id=user.id,
            username=user.username,
            role=user.role,
            tenant_id=user.tenant_id,
            created_at=user.created_at,
            updated_at=user.updated_at
        )


class LoginRequest(BaseModel):
    """
    Login credentials for authentication.

    Used by POST /api/auth/login endpoint.
    """
    username: str = Field(..., description="Username for authentication")
    password: str = Field(..., description="Plain text password")


class LoginResponse(BaseModel):
    """
    Login response with JWT token and user information.

    Returned by POST /api/auth/login endpoint on successful authentication.
    Token should be included in Authorization header as 'Bearer <token>'.
    """
    access_token: str = Field(..., description="JWT access token")
    token_type: str = Field(default="bearer", description="Token type (always 'bearer')")
    user: dict = Field(..., description="User information (id, username, role)")


# ==================== Settings Models ====================

class SettingsBase(BaseModel):
    """
    Base settings model with application preferences and configuration.

    Multi-tenancy: Settings are per-tenant (not global singleton anymore).
    Each tenant has its own settings instance.
    """
    base_currency: str = Field(..., min_length=3, max_length=3, description="Base currency for conversions (e.g., GBP)")
    default_currency: str = Field(..., min_length=3, max_length=3, description="Default currency for new items")
    date_format: str = Field(default="DD/MM/YYYY", description="Date display format")
    baseline_display_months: int = Field(default=1, ge=1, le=12, description="Months to show in baseline view")
    rates: dict[str, Decimal] = Field(default_factory=dict, description="Currency conversion rates (currency → rate)")
    server_url: str = Field(default="", description="Sync server URL")
    last_backup_date: Optional[datetime] = Field(default=None, description="Last backup timestamp")
    version: str = Field(default="1.0.0", description="Application version")
    tenant_id: Optional[UUID] = Field(default=None, description="Tenant identifier (admin's user_id) for multi-tenancy isolation")

    @field_validator('base_currency', 'default_currency')
    @classmethod
    def validate_currency_code(cls, v: str) -> str:
        """Validate currency code is 3 uppercase letters."""
        if not v.isupper() or len(v) != 3:
            raise ValueError('Currency code must be 3 uppercase letters (e.g., GBP, CAD, USD)')
        return v

    @field_validator('rates')
    @classmethod
    def validate_rate_precision(cls, v: dict[str, Decimal]) -> dict[str, Decimal]:
        """
        Validate rate values for precision, positivity, and currency code format.

        Enforces:
        - Currency codes must be 3 uppercase letters
        - Rates must be positive
        - max_digits=19, decimal_places=8 for consistency with other Decimal fields
        """
        if v:
            for currency, rate in v.items():
                # Validate currency code format
                if not currency.isupper() or len(currency) != 3:
                    raise ValueError(f'Currency code {currency} must be 3 uppercase letters (e.g., GBP, CAD, USD)')

                # Check positive value
                if rate <= 0:
                    raise ValueError(f'Rate for {currency} must be positive, got {rate}')

                # Check precision (8 decimal places maximum)
                if rate.as_tuple().exponent < -8:
                    raise ValueError(
                        f'Rate for {currency} exceeds maximum precision of 8 decimal places'
                    )
        return v


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

    @field_validator('rates')
    @classmethod
    def validate_rate_precision(cls, v: Optional[dict[str, Decimal]]) -> Optional[dict[str, Decimal]]:
        """
        Validate rate values for precision, positivity, and currency code format if rates provided.

        Enforces:
        - Currency codes must be 3 uppercase letters
        - Rates must be positive
        - max_digits=19, decimal_places=8 for consistency with other Decimal fields
        """
        if v:
            for currency, rate in v.items():
                # Validate currency code format
                if not currency.isupper() or len(currency) != 3:
                    raise ValueError(f'Currency code {currency} must be 3 uppercase letters (e.g., GBP, CAD, USD)')

                # Check positive value
                if rate <= 0:
                    raise ValueError(f'Rate for {currency} must be positive, got {rate}')

                # Check precision (8 decimal places maximum)
                if rate.as_tuple().exponent < -8:
                    raise ValueError(
                        f'Rate for {currency} exceeds maximum precision of 8 decimal places'
                    )
        return v


class Settings(SettingsBase):
    """
    Complete settings model with metadata.

    Note: id, created_at, updated_at, and tenant_id are required fields generated by API layer (Phase 1.4).
    """
    id: UUID = Field(..., description="Settings document ID")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    # Override tenant_id to be required for persisted entities (security)
    tenant_id: UUID = Field(..., description="Tenant identifier (admin's user_id) for multi-tenancy isolation")


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


# ==================== Change Log Models ====================

class ChangeLogEntry(BaseModel):
    """
    Change log entry for sync protocol.

    Tracks all creates, updates, and deletes for syncing changes
    between client and server. Used by sync protocol (Phase 3).

    Entries are pruned after 31 days to prevent unbounded growth.
    Clients with last_sync_at older than oldest entry receive
    full_sync_required=true response.

    Note: data field is null for delete actions.
    """
    id: UUID = Field(..., description="Unique change log entry identifier")
    entity_type: EntityType = Field(..., description="Type of entity changed")
    entity_id: UUID = Field(..., description="ID of the changed entity")
    action: ChangeAction = Field(..., description="Type of change (create/update/delete)")
    data: Optional[dict] = Field(
        default=None,
        description="Full entity snapshot (null for deletes)"
    )
    changed_by_user: UUID = Field(..., description="User who made the change")
    changed_by_client: UUID = Field(
        ...,
        description="Client/device ID that made the change"
    )
    changed_at: datetime = Field(
        ...,
        description="When the change occurred (UTC timestamp)"
    )

    @model_validator(mode='after')
    def validate_data_for_action(self):
        """
        Validate data field based on action type.

        Business Rules:
        - DELETE actions: data must be None (no snapshot needed)
        - CREATE/UPDATE actions: data should be present (entity snapshot)
        """
        if self.action == ChangeAction.DELETE and self.data is not None:
            raise ValueError('DELETE actions must have data=None')
        return self


# ==================== Sync Protocol Models ====================

class SyncChangeMetadata(BaseModel):
    """
    Metadata for sync changes, used to track derived events and dependencies.

    Enables server-side detection of client-generated derived events
    (opening balances, recurring instances) that may be overridden by
    authoritative server-generated versions.
    """
    derived_from: Optional[str] = Field(
        default=None,
        alias='_derived_from',
        serialization_alias='_derived_from',
        description="Derivation source (e.g., 'account_creation', 'recurring_rule_creation', 'balance_update')"
    )
    optimistic: Optional[bool] = Field(
        default=None,
        alias='_optimistic',
        serialization_alias='_optimistic',
        description="Is this a frontend optimistic guess? (true for derived changes)"
    )
    dependencies: Optional[list[str]] = Field(
        default=None,
        description="Array of entity IDs this change depends on (for cascade operations)"
    )

    model_config = ConfigDict(extra='allow', populate_by_name=True)  # Allow additional fields and populate by alias


class SyncChange(BaseModel):
    """
    Client change to push to server during sync.

    Represents a single entity modification (create/update/delete)
    that the client wants to apply to the server during the push phase.

    For conflict detection, updates and deletes include base_updated_at
    to compare against server's current updated_at timestamp.
    """
    entity_type: EntityType = Field(..., description="Type of entity being changed")
    entity_id: UUID = Field(..., description="ID of the entity")
    action: ChangeAction = Field(..., description="Type of modification")
    data: Optional[dict] = Field(
        default=None,
        description="Full entity data (null for deletes, required for creates/updates)"
    )
    base_updated_at: Optional[datetime] = Field(
        default=None,
        description="Client's last known updated_at for conflict detection (updates/deletes only)"
    )
    metadata: Optional[SyncChangeMetadata] = Field(
        default=None,
        description="Queue metadata: _derived_from, _optimistic, dependencies (for derived event detection)"
    )

    @model_validator(mode='after')
    def validate_base_updated_at_for_deletes(self):
        """
        Validate base_updated_at is provided for DELETE actions.

        Business Rules:
        - DELETE actions: Must include base_updated_at for conflict detection
        - UPDATE actions: base_updated_at optional (allows same-batch CREATE→UPDATE bypass)
        - CREATE actions: base_updated_at should be None (entity doesn't exist yet)

        The sync route handles UPDATE conflict detection:
        - Same-batch updates (CREATE→UPDATE in one sync) skip conflict check
        - Non-same-batch updates with base_updated_at compare timestamps
        - Non-same-batch updates without base_updated_at apply without conflict check
        """
        if self.action == ChangeAction.DELETE:
            if self.base_updated_at is None:
                raise ValueError(
                    'delete actions require base_updated_at for conflict detection'
                )
        return self


class SyncRequest(BaseModel):
    """
    Request payload for POST /api/sync endpoint.

    Bidirectional sync protocol:
    1. Push phase: Apply client changes to server
    2. Pull phase: Get changes from other clients since last_sync_at

    Client must track last_sync_at from previous sync response.
    First sync sends last_sync_at=None to indicate full sync needed.
    """
    client_id: str = Field(
        ...,
        min_length=1,
        description="Unique identifier for this client/device"
    )
    last_sync_at: Optional[datetime] = Field(
        default=None,
        description="Timestamp of last successful sync (None = first sync)"
    )
    changes: list[SyncChange] = Field(
        default=[],
        description="Client changes to push to server"
    )

    @model_validator(mode='after')
    def validate_last_sync_at_not_future(self):
        """
        Validate last_sync_at is not in the future.

        Business Rules:
        - last_sync_at must be <= current server time
        - Prevents client clock drift or malicious future timestamps
        - None is allowed (first sync)
        """
        if self.last_sync_at is not None:
            from api.utils.db import utc_now
            if self.last_sync_at > utc_now():
                raise ValueError('last_sync_at cannot be in the future')
        return self


class SyncConflict(BaseModel):
    """
    Conflict detected during push phase.

    Four conflict types:
    - edit_edit: Client and server both modified entity
    - delete_edit: Client deleted, server modified (or vice versa)
    - business_rule: Change violates business logic (e.g., delete account with events)
    - derived_event_overridden: Client's optimistic derived event replaced by server's authoritative version

    Both versions included for client-side resolution UI.
    For derived_event_overridden, frontend auto-resolves by deleting client version.
    """
    entity_type: EntityType = Field(..., description="Type of conflicting entity")
    entity_id: UUID = Field(..., description="ID of conflicting entity")
    conflict_type: str = Field(
        ...,
        description="Conflict category: edit_edit, delete_edit, business_rule, derived_event_overridden"
    )
    client_version: Optional[dict] = Field(
        default=None,
        description="Client's version of the entity (null if client deleted)"
    )
    server_version: Optional[dict] = Field(
        default=None,
        description="Server's current version of the entity (null if server deleted)"
    )


class SyncServerChange(BaseModel):
    """
    Change from server to pull to client.

    Represents modifications made by other clients since last_sync_at.
    Client applies these changes to local database and updates UI.
    """
    entity_type: EntityType = Field(..., description="Type of entity changed")
    entity_id: UUID = Field(..., description="ID of changed entity")
    action: ChangeAction = Field(..., description="Type of modification")
    data: Optional[dict] = Field(
        default=None,
        description="Full entity snapshot (null for deletes)"
    )


class AppliedChange(BaseModel):
    """
    Successfully applied change returned to client.

    Contains the entity's new updated_at timestamp so the client can
    synchronize its local copy. This prevents false conflicts on
    subsequent updates.
    """
    entity_type: EntityType = Field(..., description="Type of entity changed")
    entity_id: UUID = Field(..., description="ID of changed entity")
    updated_at: datetime = Field(..., description="Server's new updated_at timestamp")


class SyncResponse(BaseModel):
    """
    Response from POST /api/sync endpoint.

    Returns:
    - applied: Successfully applied client changes
    - conflicts: Changes that couldn't be applied (need resolution)
    - server_changes: Changes from other clients to pull
    - sync_timestamp: New last_sync_at for next sync
    - full_sync_required: True if client is stale (missing change log entries)

    Client should:
    1. Store sync_timestamp for next sync
    2. Handle conflicts with user intervention
    3. Apply server_changes to local database
    4. If full_sync_required=true, call GET /api/sync/full
    """
    applied: list[AppliedChange] = Field(
        default=[],
        description="Successfully applied client changes with updated timestamps"
    )
    conflicts: list[SyncConflict] = Field(
        default=[],
        description="Changes that conflicted and need resolution"
    )
    server_changes: list[SyncServerChange] = Field(
        default=[],
        description="Changes from other clients to apply locally"
    )
    sync_timestamp: datetime = Field(
        ...,
        description="Current server time - use as last_sync_at for next sync"
    )
    full_sync_required: bool = Field(
        default=False,
        description="True if client is stale and should call GET /api/sync/full"
    )
    rates_updated: bool = Field(
        default=False,
        description="True if currency rates were refreshed during this sync"
    )
    rates: Optional[dict] = Field(
        default=None,
        description="Updated currency rates (only present when rates_updated=true)"
    )


class FullSyncResponse(BaseModel):
    """
    Response from GET /api/sync/full endpoint.

    Returns complete dataset for stale clients who missed too many changes.
    Client should clear local database and repopulate with this data.

    Used when:
    - First sync (client has no last_sync_at)
    - Stale client (last_sync_at older than oldest change_log entry)
    - Client explicitly requests full refresh

    All entities are filtered by user to ensure data isolation.
    """
    accounts: list[dict] = Field(
        default=[],
        description="All accounts owned by user"
    )
    stories: list[dict] = Field(
        default=[],
        description="All stories owned by user"
    )
    events: list[dict] = Field(
        default=[],
        description="All events owned by user"
    )
    recurring_rules: list[dict] = Field(
        default=[],
        description="All recurring rules owned by user"
    )
    settings: dict = Field(
        ...,
        description="Global settings (shared across users)"
    )
    sync_timestamp: datetime = Field(
        ...,
        description="Current server time - use as last_sync_at for next sync"
    )


"""
Required MongoDB Indexes for change_log Collection:

1. Compound index for sync queries:
   db.change_log.create_index([
       ("changed_at", 1),           # Time-based filtering
       ("changed_by_client", 1)     # Exclude originating client
   ])

2. Entity lookup index:
   db.change_log.create_index([
       ("entity_type", 1),
       ("entity_id", 1)
   ])

3. Pruning index:
   db.change_log.create_index([("changed_at", 1)])

Note: Index creation deferred to Phase 3 (sync protocol implementation).
"""


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


# ==================== Projection Models ====================

class ProjectionResponse(BaseModel):
    """
    Projection response model for GET /api/projection endpoint.

    Returns financial projection data including events with running balances,
    optional warnings, and gap indicators for filtered views.

    The projection shows how balances will change over time based on
    scheduled events, account balances, and story configurations.
    """
    view: str = Field(
        ...,
        description="View mode: 'all', 'all_what_if', or story UUID"
    )
    start_date: date = Field(
        ...,
        description="Projection start date (YYYY-MM-DD)"
    )
    end_date: date = Field(
        ...,
        description="Projection end date (YYYY-MM-DD)"
    )
    starting_balance: Decimal = Field(
        ...,
        max_digits=19,
        decimal_places=4,
        description="Total balance at projection start (base currency)"
    )
    events: list[dict] = Field(
        ...,
        description="List of events with running balances and gap indicators"
    )
    warnings: Optional[list[dict]] = Field(
        default=None,
        description="Optional warnings (included if include_warnings=true)"
    )
    display_currency: str = Field(
        ...,
        min_length=3,
        max_length=3,
        description="Currency used for display amounts"
    )
