"""
Unit tests for CurrencyService lazy refresh pattern.

Tests the two-level throttling mechanism:
1. In-memory throttle (60s) - prevents DB checks on every request
2. Database throttle (24h) - controls actual API calls

External API (frankfurter.app) is mocked in these tests.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from api.services.currency import (
    CurrencyService,
    reset_throttle_state,
    _IN_MEMORY_THROTTLE_SECONDS,
    _REFRESH_INTERVAL_HOURS,
)


class TestShouldCheckRefresh:
    """Tests for in-memory throttle logic."""

    def setup_method(self):
        """Reset throttle state before each test."""
        reset_throttle_state()

    def test_first_call_returns_true(self):
        """First call should always pass throttle."""
        result = CurrencyService.should_check_refresh()
        assert result is True

    def test_immediate_second_call_returns_false(self):
        """Immediate second call should be throttled."""
        CurrencyService.should_check_refresh()  # First call
        result = CurrencyService.should_check_refresh()  # Second call
        assert result is False

    @patch('time.time')
    def test_call_after_throttle_period_returns_true(self, mock_time):
        """Call after throttle period should pass."""
        # First call at time 0
        mock_time.return_value = 0
        CurrencyService.should_check_refresh()

        # Second call at time > throttle period
        mock_time.return_value = _IN_MEMORY_THROTTLE_SECONDS + 1
        result = CurrencyService.should_check_refresh()
        assert result is True


class TestNeedsRefresh:
    """Tests for database-level refresh logic."""

    def setup_method(self):
        """Reset throttle state before each test."""
        reset_throttle_state()

    def test_returns_true_when_no_last_refresh(self):
        """Should refresh when never refreshed before."""
        result = CurrencyService.needs_refresh(None)
        assert result is True

    def test_returns_false_when_recently_refreshed(self):
        """Should not refresh when recently updated."""
        recent = datetime.utcnow() - timedelta(hours=1)
        result = CurrencyService.needs_refresh(recent)
        assert result is False

    def test_returns_true_when_stale(self):
        """Should refresh when older than refresh interval."""
        stale = datetime.utcnow() - timedelta(hours=_REFRESH_INTERVAL_HOURS + 1)
        result = CurrencyService.needs_refresh(stale)
        assert result is True

    def test_returns_false_just_under_threshold(self):
        """Should not refresh when just under threshold (boundary condition)."""
        # Use 23.9 hours to ensure we're safely under the 24h threshold
        just_under = datetime.utcnow() - timedelta(hours=_REFRESH_INTERVAL_HOURS - 0.1)
        result = CurrencyService.needs_refresh(just_under)
        assert result is False


class TestFetchRates:
    """Tests for external API fetching."""

    def setup_method(self):
        """Reset throttle state before each test."""
        reset_throttle_state()

    @pytest.mark.asyncio
    @patch('httpx.AsyncClient')
    async def test_fetch_rates_includes_base_currency(self, mock_client_class):
        """Fetched rates should include base currency with rate 1.0."""
        # Setup mock
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "base": "GBP",
            "date": "2025-01-01",
            "rates": {"USD": 1.27, "EUR": 1.17}
        }
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response

        # Call and verify
        rates = await CurrencyService.fetch_rates("GBP")

        assert rates["GBP"] == 1.0
        assert rates["USD"] == 1.27
        assert rates["EUR"] == 1.17
        assert len(rates) == 3

    @pytest.mark.asyncio
    @patch('httpx.AsyncClient')
    async def test_fetch_rates_handles_api_error(self, mock_client_class):
        """Should raise exception on API error."""
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_client.get.side_effect = Exception("Network error")

        with pytest.raises(Exception, match="Network error"):
            await CurrencyService.fetch_rates("GBP")

    @pytest.mark.asyncio
    @patch('httpx.AsyncClient')
    async def test_fetch_rates_resets_error_count_on_success(self, mock_client_class):
        """Successful fetch should reset error count."""
        from api.services import currency
        currency._error_count = 3  # Simulate previous errors

        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client

        mock_response = MagicMock()
        mock_response.json.return_value = {"rates": {"USD": 1.27}}
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response

        await CurrencyService.fetch_rates("GBP")

        assert currency._error_count == 0


class TestMaybeRefreshRates:
    """Tests for the main lazy refresh entry point."""

    def setup_method(self):
        """Reset throttle state before each test."""
        reset_throttle_state()

    @pytest.mark.asyncio
    async def test_skips_when_in_memory_throttled(self):
        """Should return None when in-memory throttled."""
        # Trigger throttle
        CurrencyService.should_check_refresh()

        # Setup mocks
        settings_repo = AsyncMock()
        global_config_repo = AsyncMock()

        # Call - should be throttled
        from uuid import uuid4
        result = await CurrencyService.maybe_refresh_rates(
            tenant_id=uuid4(),
            base_currency="GBP",
            settings_repo=settings_repo,
            global_config_repo=global_config_repo
        )

        assert result is None
        # Should not have checked database
        global_config_repo.get_refresh_status.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_when_rates_fresh(self):
        """Should return None when rates are still fresh."""
        settings_repo = AsyncMock()
        global_config_repo = AsyncMock()
        global_config_repo.get_refresh_status.return_value = {
            "last_refresh": datetime.utcnow() - timedelta(hours=1),
            "success": True
        }

        from uuid import uuid4
        result = await CurrencyService.maybe_refresh_rates(
            tenant_id=uuid4(),
            base_currency="GBP",
            settings_repo=settings_repo,
            global_config_repo=global_config_repo
        )

        assert result is None
        # Should have checked database but not fetched
        global_config_repo.get_refresh_status.assert_called_once()
        settings_repo.update_rates.assert_not_called()

    @pytest.mark.asyncio
    @patch.object(CurrencyService, 'fetch_rates')
    async def test_refreshes_when_stale(self, mock_fetch):
        """Should fetch and update rates when stale."""
        mock_fetch.return_value = {"GBP": 1.0, "USD": 1.27, "EUR": 1.17}

        settings_repo = AsyncMock()
        global_config_repo = AsyncMock()
        global_config_repo.get_refresh_status.return_value = {
            "last_refresh": datetime.utcnow() - timedelta(hours=25),
            "success": True
        }

        from uuid import uuid4
        tenant_id = uuid4()

        result = await CurrencyService.maybe_refresh_rates(
            tenant_id=tenant_id,
            base_currency="GBP",
            settings_repo=settings_repo,
            global_config_repo=global_config_repo
        )

        assert result is not None
        assert result["GBP"] == 1.0
        assert result["USD"] == 1.27

        # Should have updated settings and recorded refresh
        settings_repo.update_rates.assert_called_once_with(tenant_id, result)
        global_config_repo.set_refresh_status.assert_called_once()

    @pytest.mark.asyncio
    @patch.object(CurrencyService, 'fetch_rates')
    async def test_refreshes_when_never_refreshed(self, mock_fetch):
        """Should fetch rates when no previous refresh."""
        mock_fetch.return_value = {"GBP": 1.0, "USD": 1.27}

        settings_repo = AsyncMock()
        global_config_repo = AsyncMock()
        global_config_repo.get_refresh_status.return_value = None

        from uuid import uuid4
        result = await CurrencyService.maybe_refresh_rates(
            tenant_id=uuid4(),
            base_currency="GBP",
            settings_repo=settings_repo,
            global_config_repo=global_config_repo
        )

        assert result is not None
        mock_fetch.assert_called_once_with("GBP")

    @pytest.mark.asyncio
    @patch.object(CurrencyService, 'fetch_rates')
    async def test_handles_fetch_failure_gracefully(self, mock_fetch):
        """Should return None and record failure on fetch error."""
        mock_fetch.side_effect = Exception("API down")

        settings_repo = AsyncMock()
        global_config_repo = AsyncMock()
        global_config_repo.get_refresh_status.return_value = None

        from uuid import uuid4
        result = await CurrencyService.maybe_refresh_rates(
            tenant_id=uuid4(),
            base_currency="GBP",
            settings_repo=settings_repo,
            global_config_repo=global_config_repo
        )

        assert result is None
        # Should not have updated settings
        settings_repo.update_rates.assert_not_called()
        # Should have recorded failure
        global_config_repo.set_refresh_status.assert_called_once()
        call_args = global_config_repo.set_refresh_status.call_args
        assert call_args[0][1]["success"] is False
        assert "API down" in call_args[0][1]["error"]


class TestErrorBackoff:
    """Tests for exponential backoff on errors."""

    def setup_method(self):
        """Reset throttle state before each test."""
        reset_throttle_state()

    @pytest.mark.asyncio
    @patch('httpx.AsyncClient')
    async def test_error_increments_backoff(self, mock_client_class):
        """Each error should increment the backoff level."""
        from api.services import currency

        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_client.get.side_effect = Exception("Network error")

        initial_count = currency._error_count

        try:
            await CurrencyService.fetch_rates("GBP")
        except:
            pass

        assert currency._error_count == initial_count + 1

    def test_backoff_affects_refresh_threshold(self):
        """Higher error count should increase time before next refresh."""
        from api.services import currency

        # With error count = 0, needs refresh after 24h
        currency._error_count = 0
        stale_24h = datetime.utcnow() - timedelta(hours=25)
        assert CurrencyService.needs_refresh(stale_24h) is True

        # With error count = 2, needs refresh after 96h (24 * 2^2)
        currency._error_count = 2
        stale_48h = datetime.utcnow() - timedelta(hours=48)
        assert CurrencyService.needs_refresh(stale_48h) is False

        stale_100h = datetime.utcnow() - timedelta(hours=100)
        assert CurrencyService.needs_refresh(stale_100h) is True

        # Reset for other tests
        reset_throttle_state()


class TestGlobalConfigRepository:
    """Tests for the GlobalConfigRepository."""

    @pytest.mark.asyncio
    async def test_get_refresh_status_returns_none_when_not_found(self):
        """Should return None when no status exists."""
        from api.repositories.global_config import GlobalConfigRepository

        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_db.__getitem__.return_value = mock_collection
        mock_collection.find_one = AsyncMock(return_value=None)

        repo = GlobalConfigRepository(mock_db)
        result = await repo.get_refresh_status("currency_rates")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_refresh_status_returns_document(self):
        """Should return document when status exists."""
        from api.repositories.global_config import GlobalConfigRepository

        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_db.__getitem__.return_value = mock_collection

        expected_doc = {
            "_id": "currency_rates",
            "last_refresh": datetime.utcnow(),
            "success": True
        }
        mock_collection.find_one = AsyncMock(return_value=expected_doc)

        repo = GlobalConfigRepository(mock_db)
        result = await repo.get_refresh_status("currency_rates")

        assert result == expected_doc

    @pytest.mark.asyncio
    async def test_set_refresh_status_uses_upsert(self):
        """Should use upsert to create or update document."""
        from api.repositories.global_config import GlobalConfigRepository

        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_db.__getitem__.return_value = mock_collection
        mock_collection.update_one = AsyncMock()

        repo = GlobalConfigRepository(mock_db)
        await repo.set_refresh_status("currency_rates", {
            "last_refresh": datetime.utcnow(),
            "success": True
        })

        mock_collection.update_one.assert_called_once()
        call_args = mock_collection.update_one.call_args
        # Verify upsert=True
        assert call_args[1]["upsert"] is True
