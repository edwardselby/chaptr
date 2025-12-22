"""
Unit tests for Settings endpoints.

Tests all settings endpoints including:
- GET /api/settings (singleton with auto-create)
- PUT /api/settings (partial update)

Business logic tested:
- Singleton pattern (only one settings document)
- Auto-create default settings if none exist
- Partial updates (only specified fields changed)
- Currency validation
- Rates dictionary handling
"""

import pytest
from datetime import date


# ============================================================================
# GET /api/settings - Get Settings (Singleton)
# ============================================================================

class TestSettingsGet:
    """Tests for GET /api/settings endpoint."""

    @pytest.mark.asyncio
    async def test_get_settings_creates_default_if_none_exist(self, async_client):
        """GET settings with empty database creates default settings."""
        response = await async_client.get("/api/settings")

        assert response.status_code == 200
        data = response.json()

        # Verify default values
        assert data["base_currency"] == "GBP"
        assert data["default_currency"] == "GBP"
        assert data["date_format"] == "DD/MM/YYYY"
        assert data["baseline_display_months"] == 1
        assert data["version"] == "1.0.0"

        # Verify default rates
        assert "USD" in data["rates"]
        assert "CAD" in data["rates"]
        assert "EUR" in data["rates"]

        # Verify metadata fields
        assert data["id"] is not None
        assert data["created_at"] is not None
        assert data["updated_at"] is not None

    @pytest.mark.asyncio
    async def test_get_settings_returns_existing_singleton(self, async_client, sample_settings):
        """GET settings returns existing singleton document."""
        # sample_settings fixture creates settings via update_singleton
        response = await async_client.get("/api/settings")

        assert response.status_code == 200
        data = response.json()

        # Should return the same settings instance
        assert data["id"] == str(sample_settings.id)
        assert data["base_currency"] == sample_settings.base_currency

    @pytest.mark.asyncio
    async def test_get_settings_idempotent(self, async_client):
        """Multiple GET requests return same singleton."""
        # First request creates default
        response1 = await async_client.get("/api/settings")
        assert response1.status_code == 200
        data1 = response1.json()
        settings_id = data1["id"]

        # Second request returns same instance
        response2 = await async_client.get("/api/settings")
        assert response2.status_code == 200
        data2 = response2.json()

        assert data2["id"] == settings_id


# ============================================================================
# PUT /api/settings - Update Settings (Partial)
# ============================================================================

class TestSettingsUpdate:
    """Tests for PUT /api/settings endpoint."""

    @pytest.mark.asyncio
    async def test_update_settings_partial_rates_only(self, async_client, sample_settings):
        """Update only rates field (partial update)."""
        payload = {
            "rates": {
                "USD": "1.30",
                "EUR": "1.18"
            }
        }

        response = await async_client.put("/api/settings", json=payload)

        assert response.status_code == 200
        data = response.json()

        # Rates updated
        assert data["rates"]["USD"] == "1.30"
        assert data["rates"]["EUR"] == "1.18"

        # Other fields unchanged
        assert data["base_currency"] == sample_settings.base_currency
        assert data["date_format"] == sample_settings.date_format

    @pytest.mark.asyncio
    async def test_update_settings_change_base_currency(self, async_client, sample_settings):
        """Update base_currency field."""
        payload = {
            "base_currency": "USD"
        }

        response = await async_client.put("/api/settings", json=payload)

        assert response.status_code == 200
        data = response.json()

        # Base currency changed
        assert data["base_currency"] == "USD"

        # Other fields unchanged
        assert data["date_format"] == sample_settings.date_format
        assert data["baseline_display_months"] == sample_settings.baseline_display_months

    @pytest.mark.asyncio
    async def test_update_settings_multiple_fields(self, async_client, sample_settings):
        """Update multiple fields at once."""
        payload = {
            "base_currency": "EUR",
            "default_currency": "EUR",
            "date_format": "YYYY-MM-DD",
            "baseline_display_months": 3,
            "rates": {
                "GBP": "0.85",
                "USD": "1.08"
            }
        }

        response = await async_client.put("/api/settings", json=payload)

        assert response.status_code == 200
        data = response.json()

        # All specified fields updated
        assert data["base_currency"] == "EUR"
        assert data["default_currency"] == "EUR"
        assert data["date_format"] == "YYYY-MM-DD"
        assert data["baseline_display_months"] == 3
        assert data["rates"]["GBP"] == "0.85"
        assert data["rates"]["USD"] == "1.08"

    @pytest.mark.asyncio
    async def test_update_settings_server_url(self, async_client, sample_settings):
        """Update server_url for sync configuration."""
        payload = {
            "server_url": "https://chaptr.example.com"
        }

        response = await async_client.put("/api/settings", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert data["server_url"] == "https://chaptr.example.com"

    @pytest.mark.asyncio
    async def test_update_settings_creates_if_none_exist(self, async_client):
        """PUT creates default settings if none exist (singleton pattern)."""
        # Empty database, no settings yet
        payload = {
            "base_currency": "USD"
        }

        response = await async_client.put("/api/settings", json=payload)

        assert response.status_code == 200
        data = response.json()

        # Settings created with updated value
        assert data["base_currency"] == "USD"

        # Other fields have defaults
        assert data["date_format"] == "DD/MM/YYYY"
        assert data["version"] == "1.0.0"

    @pytest.mark.asyncio
    async def test_update_settings_validation_error_invalid_currency(
        self, async_client, sample_settings
    ):
        """Update with invalid currency code returns 422."""
        payload = {
            "base_currency": "invalid"  # Not 3 uppercase letters
        }

        response = await async_client.put("/api/settings", json=payload)

        assert response.status_code == 422
        data = response.json()
        assert "detail" in data

    @pytest.mark.asyncio
    async def test_update_settings_validation_error_invalid_baseline_months(
        self, async_client, sample_settings
    ):
        """Update with invalid baseline_display_months returns 422."""
        payload = {
            "baseline_display_months": -1  # Must be >= 1
        }

        response = await async_client.put("/api/settings", json=payload)

        assert response.status_code == 422
        data = response.json()
        assert "detail" in data

    @pytest.mark.asyncio
    async def test_update_settings_updates_updated_at_timestamp(
        self, async_client, sample_settings
    ):
        """PUT always updates the updated_at timestamp."""
        original_updated_at = sample_settings.updated_at

        payload = {
            "base_currency": "USD"
        }

        response = await async_client.put("/api/settings", json=payload)

        assert response.status_code == 200
        data = response.json()

        # updated_at should be newer
        assert data["updated_at"] != original_updated_at.isoformat()
