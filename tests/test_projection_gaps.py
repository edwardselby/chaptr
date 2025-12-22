"""
Unit tests for gap indicator detection in story projections.

Tests the detect_gaps_between_visible_events() function that identifies
hidden events between visible events in filtered story views.

Phase 2.4 - Tasks 2, 3, 4:
- Task 2: Identify hidden events between visible events
- Task 3: Calculate delta amount for gap indicators
- Task 4: Convert gap amounts to story display_currency
"""

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from core.projection import (
    detect_gaps_between_visible_events,
    convert_from_base_currency
)


class TestDetectGapsBetweenVisibleEvents:
    """Test gap detection algorithm."""

    def test_detect_gaps_with_single_hidden_event(self):
        """Hidden event between two visible events creates gap."""
        # Setup: visible -> hidden -> visible
        car_rental_id = uuid4()
        parts_id = uuid4()
        gifts_id = uuid4()

        visible_ids = {car_rental_id, gifts_id}
        all_events = [
            {
                "_id": car_rental_id,
                "date": date(2024, 12, 20),
                "description": "car rental",
                "base_amount": Decimal("-320.00")
            },
            {
                "_id": parts_id,
                "date": date(2024, 12, 22),
                "description": "parts [volvo]",
                "base_amount": Decimal("-180.00")  # hidden
            },
            {
                "_id": gifts_id,
                "date": date(2024, 12, 25),
                "description": "gifts",
                "base_amount": Decimal("-150.00")
            }
        ]

        gaps = detect_gaps_between_visible_events(
            all_events,
            visible_ids
        )

        # Assert: One gap created
        assert len(gaps) == 1
        assert gaps[0]["type"] == "gap_indicator"
        assert gaps[0]["after_event_id"] == car_rental_id
        assert gaps[0]["before_event_id"] == gifts_id
        assert gaps[0]["delta_base"] == Decimal("-180.00")
        assert gaps[0]["hidden_event_count"] == 1
        assert len(gaps[0]["hidden_events"]) == 1
        assert gaps[0]["hidden_events"][0]["description"] == "parts [volvo]"
        assert gaps[0]["start_date"] == date(2024, 12, 22)
        assert gaps[0]["end_date"] == date(2024, 12, 22)

    def test_detect_gaps_with_multiple_hidden_events(self):
        """Multiple hidden events sum to cumulative delta."""
        # Setup: visible -> hidden1 -> hidden2 -> visible
        car_rental_id = uuid4()
        parts_id = uuid4()
        lift_pass_id = uuid4()
        gifts_id = uuid4()

        visible_ids = {car_rental_id, gifts_id}
        all_events = [
            {"_id": car_rental_id, "date": date(2024, 12, 20), "base_amount": Decimal("-320.00")},
            {"_id": parts_id, "date": date(2024, 12, 22), "base_amount": Decimal("-180.00")},  # hidden
            {"_id": lift_pass_id, "date": date(2024, 12, 23), "base_amount": Decimal("-150.00")},  # hidden
            {"_id": gifts_id, "date": date(2024, 12, 25), "base_amount": Decimal("-150.00")}
        ]

        gaps = detect_gaps_between_visible_events(all_events, visible_ids)

        # Assert: One gap with cumulative delta
        assert len(gaps) == 1
        assert gaps[0]["delta_base"] == Decimal("-330.00")  # -180 + -150
        assert gaps[0]["hidden_event_count"] == 2
        assert gaps[0]["start_date"] == date(2024, 12, 22)
        assert gaps[0]["end_date"] == date(2024, 12, 23)

    def test_detect_gaps_skips_zero_delta(self):
        """Gap with delta=0 (income offset by expense) is skipped."""
        # Setup: visible -> hidden_income (+100) -> hidden_expense (-100) -> visible
        visible1_id = uuid4()
        hidden_income_id = uuid4()
        hidden_expense_id = uuid4()
        visible2_id = uuid4()

        visible_ids = {visible1_id, visible2_id}
        all_events = [
            {"_id": visible1_id, "date": date(2024, 12, 20), "base_amount": Decimal("-100.00")},
            {"_id": hidden_income_id, "date": date(2024, 12, 21), "base_amount": Decimal("100.00")},
            {"_id": hidden_expense_id, "date": date(2024, 12, 22), "base_amount": Decimal("-100.00")},
            {"_id": visible2_id, "date": date(2024, 12, 25), "base_amount": Decimal("-50.00")}
        ]

        gaps = detect_gaps_between_visible_events(all_events, visible_ids)

        # Assert: No gap (delta = 0)
        assert len(gaps) == 0

    def test_detect_gaps_handles_trailing_hidden_events(self):
        """Hidden events after last visible event create trailing gap."""
        # Setup: visible -> hidden1 -> hidden2 (no more visible events)
        visible_id = uuid4()
        hidden1_id = uuid4()
        hidden2_id = uuid4()

        visible_ids = {visible_id}
        all_events = [
            {"_id": visible_id, "date": date(2024, 12, 20), "base_amount": Decimal("-100.00")},
            {"_id": hidden1_id, "date": date(2024, 12, 22), "base_amount": Decimal("-50.00")},
            {"_id": hidden2_id, "date": date(2024, 12, 24), "base_amount": Decimal("-75.00")}
        ]

        gaps = detect_gaps_between_visible_events(all_events, visible_ids)

        # Assert: Trailing gap with before_event_id = None
        assert len(gaps) == 1
        assert gaps[0]["after_event_id"] == visible_id
        assert gaps[0]["before_event_id"] is None  # No next visible event
        assert gaps[0]["delta_base"] == Decimal("-125.00")
        assert gaps[0]["hidden_event_count"] == 2

    def test_detect_gaps_no_hidden_events(self):
        """No gaps when all events visible."""
        # Setup: All events are visible (viewing ALL or only baseline exists)
        event1_id = uuid4()
        event2_id = uuid4()
        event3_id = uuid4()

        visible_ids = {event1_id, event2_id, event3_id}
        all_events = [
            {"_id": event1_id, "date": date(2024, 12, 20), "base_amount": Decimal("-100.00")},
            {"_id": event2_id, "date": date(2024, 12, 22), "base_amount": Decimal("-50.00")},
            {"_id": event3_id, "date": date(2024, 12, 24), "base_amount": Decimal("-75.00")}
        ]

        gaps = detect_gaps_between_visible_events(all_events, visible_ids)

        # Assert: No gaps
        assert len(gaps) == 0

    def test_detect_gaps_handles_empty_visible_events(self):
        """No gaps when no visible events exist."""
        # Setup: No visible events (all hidden)
        hidden1_id = uuid4()
        hidden2_id = uuid4()

        visible_ids = set()  # No visible events
        all_events = [
            {"_id": hidden1_id, "date": date(2024, 12, 20), "base_amount": Decimal("-100.00")},
            {"_id": hidden2_id, "date": date(2024, 12, 22), "base_amount": Decimal("-50.00")}
        ]

        gaps = detect_gaps_between_visible_events(all_events, visible_ids)

        # Assert: No gaps (no visible events to attach metadata to)
        assert len(gaps) == 0

    def test_detect_gaps_handles_empty_all_events(self):
        """No gaps when no events exist."""
        visible_ids = {uuid4()}
        all_events = []

        gaps = detect_gaps_between_visible_events(all_events, visible_ids)

        # Assert: No gaps
        assert len(gaps) == 0

    def test_detect_gaps_with_positive_delta(self):
        """Gap can have positive delta (hidden income events)."""
        # Setup: visible -> hidden_income (+500) -> visible
        visible1_id = uuid4()
        hidden_income_id = uuid4()
        visible2_id = uuid4()

        visible_ids = {visible1_id, visible2_id}
        all_events = [
            {"_id": visible1_id, "date": date(2024, 12, 20), "base_amount": Decimal("-100.00")},
            {"_id": hidden_income_id, "date": date(2024, 12, 22), "base_amount": Decimal("500.00")},
            {"_id": visible2_id, "date": date(2024, 12, 25), "base_amount": Decimal("-50.00")}
        ]

        gaps = detect_gaps_between_visible_events(all_events, visible_ids)

        # Assert: Gap with positive delta
        assert len(gaps) == 1
        assert gaps[0]["delta_base"] == Decimal("500.00")


class TestGapCurrencyConversion:
    """Test currency conversion for gap deltas (Task 4)."""

    def test_gap_currency_conversion_to_foreign_currency(self):
        """Convert -£180 to CAD at rate 1.72 = -$309.60."""
        delta_base = Decimal("-180.00")
        target_currency = "CAD"
        base_currency = "GBP"
        rates = {"CAD": Decimal("1.72")}

        delta_display = convert_from_base_currency(
            delta_base,
            target_currency,
            base_currency,
            rates
        )

        # Assert: Correct conversion
        assert delta_display == Decimal("-309.60")

    def test_gap_currency_conversion_to_base_currency(self):
        """No conversion needed when display_currency = base_currency."""
        delta_base = Decimal("-180.00")
        target_currency = "GBP"
        base_currency = "GBP"
        rates = {}

        delta_display = convert_from_base_currency(
            delta_base,
            target_currency,
            base_currency,
            rates
        )

        # Assert: Same value (no conversion)
        assert delta_display == delta_base

    def test_gap_currency_conversion_positive_amount(self):
        """Convert positive amount (income) correctly."""
        delta_base = Decimal("500.00")
        target_currency = "USD"
        base_currency = "GBP"
        rates = {"USD": Decimal("1.27")}

        delta_display = convert_from_base_currency(
            delta_base,
            target_currency,
            base_currency,
            rates
        )

        # Assert: Correct conversion
        assert delta_display == Decimal("635.00")

    def test_gap_currency_conversion_precision(self):
        """Preserve decimal precision in currency conversion."""
        delta_base = Decimal("-123.45")
        target_currency = "EUR"
        base_currency = "GBP"
        rates = {"EUR": Decimal("1.18")}

        delta_display = convert_from_base_currency(
            delta_base,
            target_currency,
            base_currency,
            rates
        )

        # Assert: Maintains precision
        assert delta_display == Decimal("-145.67")  # -123.45 * 1.18 = -145.671 -> -145.67


class TestGapDetectionEdgeCases:
    """Test edge cases for gap detection."""

    def test_gap_with_single_visible_event(self):
        """Single visible event can have trailing gap."""
        visible_id = uuid4()
        hidden_id = uuid4()

        visible_ids = {visible_id}
        all_events = [
            {"_id": visible_id, "date": date(2024, 12, 20), "base_amount": Decimal("-100.00")},
            {"_id": hidden_id, "date": date(2024, 12, 22), "base_amount": Decimal("-50.00")}
        ]

        gaps = detect_gaps_between_visible_events(all_events, visible_ids)

        # Assert: Trailing gap attached to single visible event
        assert len(gaps) == 1
        assert gaps[0]["after_event_id"] == visible_id
        assert gaps[0]["before_event_id"] is None

    def test_gap_with_consecutive_visible_events_no_gap(self):
        """Consecutive visible events with no hidden events = no gap."""
        visible1_id = uuid4()
        visible2_id = uuid4()

        visible_ids = {visible1_id, visible2_id}
        all_events = [
            {"_id": visible1_id, "date": date(2024, 12, 20), "base_amount": Decimal("-100.00")},
            {"_id": visible2_id, "date": date(2024, 12, 21), "base_amount": Decimal("-50.00")}
        ]

        gaps = detect_gaps_between_visible_events(all_events, visible_ids)

        # Assert: No gaps
        assert len(gaps) == 0

    def test_gap_with_very_large_delta(self):
        """Large delta values handled correctly."""
        visible1_id = uuid4()
        hidden_id = uuid4()
        visible2_id = uuid4()

        visible_ids = {visible1_id, visible2_id}
        all_events = [
            {"_id": visible1_id, "date": date(2024, 12, 20), "base_amount": Decimal("-100.00")},
            {"_id": hidden_id, "date": date(2024, 12, 22), "base_amount": Decimal("-999999.99")},
            {"_id": visible2_id, "date": date(2024, 12, 25), "base_amount": Decimal("-50.00")}
        ]

        gaps = detect_gaps_between_visible_events(all_events, visible_ids)

        # Assert: Large delta handled correctly
        assert len(gaps) == 1
        assert gaps[0]["delta_base"] == Decimal("-999999.99")
