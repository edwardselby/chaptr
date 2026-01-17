"""
Comprehensive tests for Pydantic model validation.

Tests all models for:
- Valid creation with all required fields
- Validation error cases (invalid currency, date ranges, funding modes)
- Partial update scenarios
- Edge cases (max precision, boundary values)
- Validator behavior (cross-field relationships)
"""

import pytest
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4
from pydantic import ValidationError

from api.models import (
    # Enums
    FundingMode, GoalType, Frequency, UserRole,
    # Settings
    SettingsBase, SettingsUpdate, Settings,
    # User
    UserBase, UserCreate, User,
    # Account
    AccountBase, AccountCreate, AccountUpdate, Account,
    # RecurringRule
    RecurringRuleBase, RecurringRuleCreate, RecurringRuleUpdate, RecurringRule,
    # Story
    StoryBase, StoryCreate, StoryUpdate, Story,
    # Event
    EventBase, EventCreate, EventUpdate, Event,
)


# ============================================================================
# Settings Model Tests
# ============================================================================

class TestSettingsModel:
    """Tests for Settings model and validation."""

    def test_settings_create_valid(self):
        """Test creating valid settings with all required fields."""
        settings_data = {
            "base_currency": "GBP",
            "default_currency": "GBP",
            "rates": {"CAD": Decimal("1.75"), "USD": Decimal("1.28")}
        }
        settings = SettingsBase(**settings_data)
        assert settings.base_currency == "GBP"
        assert settings.default_currency == "GBP"
        assert settings.rates["CAD"] == Decimal("1.75")

    def test_settings_currency_code_validation(self):
        """Test currency codes must be 3 uppercase letters."""
        # Invalid base_currency (too short - Field constraint)
        with pytest.raises(ValidationError) as exc_info:
            SettingsBase(base_currency="gb", default_currency="GBP")
        assert "String should have at least 3 characters" in str(exc_info.value)

        # Invalid default_currency
        with pytest.raises(ValidationError) as exc_info:
            SettingsBase(base_currency="GBP", default_currency="usd")
        assert "Currency code must be 3 uppercase letters" in str(exc_info.value)

    def test_settings_rates_currency_code_validation(self):
        """Test rates dict keys must be valid currency codes."""
        settings_data = {
            "base_currency": "GBP",
            "default_currency": "GBP",
            "rates": {"ca": Decimal("1.75")}  # Invalid: lowercase
        }
        with pytest.raises(ValidationError) as exc_info:
            SettingsBase(**settings_data)
        assert "must be 3 uppercase letters" in str(exc_info.value)

    def test_settings_rates_positive_validation(self):
        """Test rates must be positive values."""
        settings_data = {
            "base_currency": "GBP",
            "default_currency": "GBP",
            "rates": {"CAD": Decimal("-1.75")}  # Invalid: negative
        }
        with pytest.raises(ValidationError) as exc_info:
            SettingsBase(**settings_data)
        assert "must be positive" in str(exc_info.value)

    def test_settings_rates_precision_validation(self):
        """Test rates precision limited to 8 decimal places."""
        settings_data = {
            "base_currency": "GBP",
            "default_currency": "GBP",
            "rates": {"CAD": Decimal("1.123456789")}  # 9 decimal places
        }
        with pytest.raises(ValidationError) as exc_info:
            SettingsBase(**settings_data)
        assert "exceeds maximum precision of 8 decimal places" in str(exc_info.value)

    def test_settings_baseline_display_months_range(self):
        """Test baseline_display_months must be 1-12."""
        with pytest.raises(ValidationError) as exc_info:
            SettingsBase(
                base_currency="GBP",
                default_currency="GBP",
                baseline_display_months=0  # Invalid: too low
            )
        assert "greater than or equal to 1" in str(exc_info.value)

        with pytest.raises(ValidationError) as exc_info:
            SettingsBase(
                base_currency="GBP",
                default_currency="GBP",
                baseline_display_months=13  # Invalid: too high
            )
        assert "less than or equal to 12" in str(exc_info.value)

    def test_settings_update_partial(self):
        """Test partial updates work correctly."""
        update = SettingsUpdate(default_currency="USD")
        assert update.default_currency == "USD"
        assert update.base_currency is None  # Not provided


# ============================================================================
# User Model Tests
# ============================================================================

class TestUserModel:
    """Tests for User model and validation."""

    def test_user_create_valid(self):
        """Test creating valid user."""
        user_data = {
            "username": "Edward",
            "role": UserRole.ADMIN
        }
        user = UserCreate(**user_data)
        assert user.username == "Edward"
        assert user.role == UserRole.ADMIN

    def test_user_username_required(self):
        """Test username cannot be empty."""
        with pytest.raises(ValidationError) as exc_info:
            UserCreate(username="", role=UserRole.USER)
        assert "at least 1" in str(exc_info.value)


# ============================================================================
# Account Model Tests
# ============================================================================

class TestAccountModel:
    """Tests for Account model and validation."""

    def test_account_create_valid(self):
        """Test creating valid account."""
        account_data = {
            "name": "Monzo",
            "currency": "GBP",
            "current_balance": Decimal("2500.50"),
            "balance_updated_at": datetime.now(timezone.utc),
            "is_default": True
        }
        account = AccountCreate(**account_data)
        assert account.name == "Monzo"
        assert account.currency == "GBP"
        assert account.current_balance == Decimal("2500.50")

    def test_account_currency_validation(self):
        """Test account currency must be 3 uppercase letters."""
        with pytest.raises(ValidationError) as exc_info:
            AccountCreate(
                name="Test",
                currency="gb",  # Invalid: too short (Field constraint)
                current_balance=Decimal("0")
            )
        assert "String should have at least 3 characters" in str(exc_info.value)

    def test_account_balance_updated_at_optional(self):
        """Test balance_updated_at is optional for new accounts."""
        account = AccountCreate(
            name="New Account",
            currency="GBP",
            current_balance=Decimal("0")
        )
        assert account.balance_updated_at is None

    def test_account_update_partial(self):
        """Test partial account updates."""
        update = AccountUpdate(name="Monzo Updated")
        assert update.name == "Monzo Updated"
        assert update.currency is None


# ============================================================================
# RecurringRule Model Tests
# ============================================================================

class TestRecurringRuleModel:
    """Tests for RecurringRule model and validation."""

    def test_recurring_rule_create_valid(self):
        """Test creating valid recurring rule."""
        rule_data = {
            "description": "Monthly salary",
            "amount": Decimal("3000.00"),
            "currency": "GBP",
            "account_id": uuid4(),
            "frequency": Frequency.MONTHLY,
            "day": 28,
            "start_date": date(2024, 1, 1),
        }
        rule = RecurringRuleCreate(**rule_data)
        assert rule.description == "Monthly salary"
        assert rule.frequency == Frequency.MONTHLY
        assert rule.day == 28

    def test_recurring_rule_day_validation_weekly(self):
        """Test weekly frequency requires day 1-7."""
        rule_data = {
            "description": "Weekly expense",
            "amount": Decimal("-50.00"),
            "currency": "GBP",
            "account_id": uuid4(),
            "frequency": Frequency.WEEKLY,
            "day": 10,  # Invalid: > 7
            "start_date": date(2024, 1, 1),
        }
        with pytest.raises(ValidationError) as exc_info:
            RecurringRuleCreate(**rule_data)
        assert "Weekly frequency requires day 1-7" in str(exc_info.value)

    def test_recurring_rule_day_validation_monthly(self):
        """Test monthly frequency requires day 1-31."""
        rule_data = {
            "description": "Monthly rent",
            "amount": Decimal("-1200.00"),
            "currency": "GBP",
            "account_id": uuid4(),
            "frequency": Frequency.MONTHLY,
            "day": 32,  # Invalid: > 31 (Field constraint)
            "start_date": date(2024, 1, 1),
        }
        with pytest.raises(ValidationError) as exc_info:
            RecurringRuleCreate(**rule_data)
        assert "Input should be less than or equal to 31" in str(exc_info.value)

    def test_recurring_rule_date_range_validation(self):
        """Test end_date must be after or equal to start_date."""
        rule_data = {
            "description": "Limited rule",
            "amount": Decimal("100.00"),
            "currency": "GBP",
            "account_id": uuid4(),
            "frequency": Frequency.MONTHLY,
            "day": 1,
            "start_date": date(2024, 12, 1),
            "end_date": date(2024, 11, 1),  # Invalid: before start_date
        }
        with pytest.raises(ValidationError) as exc_info:
            RecurringRuleCreate(**rule_data)
        assert "end_date must be after or equal to start_date" in str(exc_info.value)

    def test_recurring_rule_update_partial_validation(self):
        """Test RecurringRuleUpdate only validates when both frequency and day provided."""
        # Only frequency provided - should pass (no validation)
        update = RecurringRuleUpdate(frequency=Frequency.WEEKLY)
        assert update.frequency == Frequency.WEEKLY
        assert update.day is None

        # Both provided - should validate
        with pytest.raises(ValidationError) as exc_info:
            RecurringRuleUpdate(frequency=Frequency.WEEKLY, day=10)
        assert "Weekly frequency requires day 1-7" in str(exc_info.value)


# ============================================================================
# Story Model Tests
# ============================================================================

class TestStoryModel:
    """Tests for Story model and validation."""

    def test_story_create_valid_projected(self):
        """Test creating valid story with PROJECTED funding."""
        story_data = {
            "name": "Canada Trip",
            "start_date": date(2025, 6, 1),
            "end_date": date(2025, 6, 15),
            "funding_mode": FundingMode.PROJECTED,
            "goal_type": GoalType.NONE,
            "display_currency": "CAD"
        }
        story = StoryCreate(**story_data)
        assert story.name == "Canada Trip"
        assert story.funding_mode == FundingMode.PROJECTED

    def test_story_create_valid_fixed(self):
        """Test creating story with FIXED funding requires funding_amount."""
        story_data = {
            "name": "Fixed Budget Project",
            "start_date": date(2025, 1, 1),
            "funding_mode": FundingMode.FIXED,
            "funding_amount": Decimal("5000.00"),
            "goal_type": GoalType.NONE,
            "display_currency": "GBP"
        }
        story = StoryCreate(**story_data)
        assert story.funding_amount == Decimal("5000.00")

    def test_story_funding_mode_requires_amount(self):
        """Test FIXED/PROJECTED_PLUS modes require funding_amount."""
        story_data = {
            "name": "Invalid Story",
            "start_date": date(2025, 1, 1),
            "funding_mode": FundingMode.FIXED,
            # Missing funding_amount
            "goal_type": GoalType.NONE,
            "display_currency": "GBP"
        }
        with pytest.raises(ValidationError) as exc_info:
            StoryCreate(**story_data)
        assert "funding_amount required" in str(exc_info.value)

    def test_story_goal_type_requires_amount(self):
        """Test goal_type requires goal_amount when set."""
        story_data = {
            "name": "Goal Story",
            "start_date": date(2025, 1, 1),
            "funding_mode": FundingMode.PROJECTED,
            "goal_type": GoalType.SPEND_UP_TO,
            # Missing goal_amount
            "display_currency": "GBP"
        }
        with pytest.raises(ValidationError) as exc_info:
            StoryCreate(**story_data)
        assert "goal_amount required" in str(exc_info.value)

    def test_story_date_range_validation(self):
        """Test end_date must be after or equal to start_date."""
        story_data = {
            "name": "Invalid Dates",
            "start_date": date(2025, 6, 15),
            "end_date": date(2025, 6, 1),  # Invalid: before start_date
            "funding_mode": FundingMode.PROJECTED,
            "goal_type": GoalType.NONE,
            "display_currency": "GBP"
        }
        with pytest.raises(ValidationError) as exc_info:
            StoryCreate(**story_data)
        assert "end_date must be after or equal to start_date" in str(exc_info.value)

    def test_story_update_partial_no_validation(self):
        """Test StoryUpdate allows partial updates without cross-field validation."""
        # Only update funding_mode - should pass (validation removed)
        update = StoryUpdate(funding_mode=FundingMode.FIXED)
        assert update.funding_mode == FundingMode.FIXED
        assert update.funding_amount is None  # Not provided

        # Only update goal_type - should pass (validation removed)
        update2 = StoryUpdate(goal_type=GoalType.SPEND_UP_TO)
        assert update2.goal_type == GoalType.SPEND_UP_TO
        assert update2.goal_amount is None  # Not provided


# ============================================================================
# Event Model Tests
# ============================================================================

class TestEventModel:
    """Tests for Event model and validation."""

    def test_event_create_valid(self):
        """Test creating valid event."""
        event_data = {
            "event_date": date(2024, 12, 25),
            "description": "Christmas gift",
            "amount": Decimal("-50.00"),
            "currency": "GBP",
            "rate_to_base": Decimal("1.0"),
            "account_id": uuid4(),
        }
        event = EventCreate(**event_data)
        assert event.event_date == date(2024, 12, 25)
        assert event.description == "Christmas gift"
        assert event.amount == Decimal("-50.00")

    def test_event_rate_to_base_positive(self):
        """Test rate_to_base must be positive."""
        event_data = {
            "event_date": date(2024, 12, 25),
            "description": "Test",
            "amount": Decimal("100.00"),
            "currency": "GBP",
            "rate_to_base": Decimal("-1.0"),  # Invalid: negative
            "account_id": uuid4(),
        }
        with pytest.raises(ValidationError) as exc_info:
            EventCreate(**event_data)
        assert "greater than 0" in str(exc_info.value)

    def test_event_baseline_story_exclusivity(self):
        """Test baseline events cannot belong to a story."""
        event_data = {
            "event_date": date(2024, 12, 25),
            "description": "Test",
            "amount": Decimal("100.00"),
            "currency": "GBP",
            "rate_to_base": Decimal("1.0"),
            "account_id": uuid4(),
            "is_baseline": True,
            "story_id": uuid4(),  # Invalid: can't have both
        }
        with pytest.raises(ValidationError) as exc_info:
            EventCreate(**event_data)
        assert "Baseline events cannot belong to a story" in str(exc_info.value)

    def test_event_baseline_without_story(self):
        """Test baseline event without story_id is valid."""
        event_data = {
            "event_date": date(2024, 12, 25),
            "description": "Baseline event",
            "amount": Decimal("-100.00"),
            "currency": "GBP",
            "rate_to_base": Decimal("1.0"),
            "account_id": uuid4(),
            "is_baseline": True,
        }
        event = EventCreate(**event_data)
        assert event.is_baseline is True
        assert event.story_id is None

    def test_event_story_without_baseline(self):
        """Test story event without is_baseline is valid."""
        story_id = uuid4()
        event_data = {
            "event_date": date(2024, 12, 25),
            "description": "Story event",
            "amount": Decimal("-100.00"),
            "currency": "GBP",
            "rate_to_base": Decimal("1.0"),
            "account_id": uuid4(),
            "story_id": story_id,
        }
        event = EventCreate(**event_data)
        assert event.story_id == story_id
        assert event.is_baseline is False  # Default

    def test_event_decimal_precision(self):
        """Test event amount and rate precision constraints."""
        # Valid: 4 decimal places for amount
        event = EventCreate(
            event_date=date(2024, 12, 25),
            description="Test",
            amount=Decimal("123.4567"),
            currency="GBP",
            rate_to_base=Decimal("1.12345678"),  # Valid: 8 decimal places
            account_id=uuid4(),
        )
        assert event.amount == Decimal("123.4567")
        assert event.rate_to_base == Decimal("1.12345678")


# ============================================================================
# Edge Cases and Boundary Tests
# ============================================================================

class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_decimal_max_precision_amounts(self):
        """Test maximum precision for amount fields."""
        # 19 digits total, 4 decimal places = max 15 integer digits
        max_amount = Decimal("999999999999999.9999")
        event = EventCreate(
            event_date=date(2024, 12, 25),
            description="Max amount",
            amount=max_amount,
            currency="GBP",
            rate_to_base=Decimal("1.0"),
            account_id=uuid4(),
        )
        assert event.amount == max_amount

    def test_decimal_max_precision_rates(self):
        """Test maximum precision for rate fields."""
        # 19 digits total, 8 decimal places = max 11 integer digits
        max_rate = Decimal("99999999999.99999999")
        event = EventCreate(
            event_date=date(2024, 12, 25),
            description="Test",
            amount=Decimal("100.00"),
            currency="GBP",
            rate_to_base=max_rate,
            account_id=uuid4(),
        )
        assert event.rate_to_base == max_rate

    def test_empty_string_descriptions(self):
        """Test empty descriptions are rejected."""
        with pytest.raises(ValidationError) as exc_info:
            EventCreate(
                event_date=date(2024, 12, 25),
                description="",  # Invalid: empty
                amount=Decimal("100.00"),
                currency="GBP",
                rate_to_base=Decimal("1.0"),
                account_id=uuid4(),
            )
        assert "at least 1" in str(exc_info.value)

    def test_currency_code_edge_cases(self):
        """Test currency code validation edge cases."""
        # Too short
        with pytest.raises(ValidationError):
            EventCreate(
                event_date=date(2024, 12, 25),
                description="Test",
                amount=Decimal("100.00"),
                currency="GB",  # Invalid: too short
                rate_to_base=Decimal("1.0"),
                account_id=uuid4(),
            )

        # Too long
        with pytest.raises(ValidationError):
            EventCreate(
                event_date=date(2024, 12, 25),
                description="Test",
                amount=Decimal("100.00"),
                currency="GBPX",  # Invalid: too long
                rate_to_base=Decimal("1.0"),
                account_id=uuid4(),
            )
