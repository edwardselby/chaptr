"""
Unit tests for Account CRUD endpoints.

Tests all account endpoints including:
- GET /api/accounts (list with filtering)
- GET /api/accounts/{id} (single account)
- POST /api/accounts (create)
- PATCH /api/accounts/{id} (update)
- DELETE /api/accounts/{id} (archive)

Business logic tested:
- is_default enforcement (exactly one default account)
- Archive behavior (soft delete)
- pending_reconciliation flag on balance updates
"""

import pytest
from decimal import Decimal
from datetime import datetime


# ============================================================================
# GET /api/accounts - List Accounts
# ============================================================================

class TestAccountList:
    """Tests for GET /api/accounts endpoint."""

    @pytest.mark.asyncio
    async def test_list_accounts_empty(self, async_client):
        """Empty database returns empty list."""
        response = await async_client.get("/api/accounts")

        assert response.status_code == 200
        data = response.json()
        assert data == []

    @pytest.mark.asyncio
    async def test_list_accounts_returns_accounts(self, async_client, sample_account):
        """List returns created accounts."""
        response = await async_client.get("/api/accounts")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["name"] == "Test Account"
        assert data[0]["currency"] == "GBP"

    @pytest.mark.asyncio
    async def test_list_accounts_excludes_archived_by_default(
        self, async_client, sample_account, sample_archived_account
    ):
        """Archived accounts excluded by default."""
        response = await async_client.get("/api/accounts")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["name"] == "Test Account"
        assert data[0]["is_archived"] is False

    @pytest.mark.asyncio
    async def test_list_accounts_includes_archived_when_requested(
        self, async_client, sample_account, sample_archived_account
    ):
        """include_archived=true includes archived accounts."""
        response = await async_client.get("/api/accounts?include_archived=true")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2

        # Check both accounts present
        names = {acc["name"] for acc in data}
        assert "Test Account" in names
        assert "Archived Account" in names

    @pytest.mark.asyncio
    async def test_list_accounts_multiple_accounts(
        self, async_client, sample_account, sample_account_usd
    ):
        """List returns multiple active accounts."""
        response = await async_client.get("/api/accounts")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2


# ============================================================================
# GET /api/accounts/{id} - Get Single Account
# ============================================================================

class TestAccountGet:
    """Tests for GET /api/accounts/{id} endpoint."""

    @pytest.mark.asyncio
    async def test_get_account_success(self, async_client, sample_account):
        """Get existing account returns 200 with account data."""
        response = await async_client.get(f"/api/accounts/{sample_account.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(sample_account.id)
        assert data["name"] == "Test Account"
        assert data["currency"] == "GBP"
        assert data["current_balance"] == "1000.00"
        assert data["is_default"] is True

    @pytest.mark.asyncio
    async def test_get_account_not_found(self, async_client):
        """Get non-existent account returns 404."""
        from uuid import uuid4
        fake_id = uuid4()

        response = await async_client.get(f"/api/accounts/{fake_id}")

        assert response.status_code == 404
        data = response.json()
        assert "detail" in data

    @pytest.mark.asyncio
    async def test_get_archived_account_success(self, async_client, sample_archived_account):
        """Can get archived account by ID (doesn't filter archived)."""
        response = await async_client.get(f"/api/accounts/{sample_archived_account.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["is_archived"] is True


# ============================================================================
# POST /api/accounts - Create Account
# ============================================================================

class TestAccountCreate:
    """Tests for POST /api/accounts endpoint."""

    @pytest.mark.asyncio
    async def test_create_first_account_auto_sets_default(self, async_client):
        """First account automatically sets is_default=true."""
        payload = {
            "name": "First Account",
            "currency": "GBP",
            "current_balance": 1500.00,
            "balance_updated_at": datetime.utcnow().isoformat() + "Z",
            "is_default": False,  # Explicitly set to False
            "is_archived": False,
            "pending_reconciliation": False
        }

        response = await async_client.post("/api/accounts", json=payload)

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "First Account"
        assert data["is_default"] is True  # Auto-set by system
        assert data["id"] is not None
        assert data["created_at"] is not None

    @pytest.mark.asyncio
    async def test_create_second_account_not_default(self, async_client, sample_account):
        """Second account can be created without being default."""
        payload = {
            "name": "Second Account",
            "currency": "USD",
            "current_balance": 2000.00,
            "balance_updated_at": datetime.utcnow().isoformat() + "Z",
            "is_default": False,
            "is_archived": False,
            "pending_reconciliation": False
        }

        response = await async_client.post("/api/accounts", json=payload)

        assert response.status_code == 201
        data = response.json()
        assert data["is_default"] is False

    @pytest.mark.asyncio
    async def test_create_account_with_default_unsets_previous(
        self, async_client, sample_account
    ):
        """Creating new default account unsets previous default."""
        # Verify sample_account is default
        assert sample_account.is_default is True

        # Create new account as default
        payload = {
            "name": "New Default Account",
            "currency": "USD",
            "current_balance": 3000.00,
            "balance_updated_at": datetime.utcnow().isoformat() + "Z",
            "is_default": True,
            "is_archived": False,
            "pending_reconciliation": False
        }

        response = await async_client.post("/api/accounts", json=payload)

        assert response.status_code == 201
        data = response.json()
        assert data["is_default"] is True

        # Verify old default account is no longer default
        old_account_response = await async_client.get(
            f"/api/accounts/{sample_account.id}"
        )
        assert old_account_response.status_code == 200
        old_account_data = old_account_response.json()
        assert old_account_data["is_default"] is False

    @pytest.mark.asyncio
    async def test_create_account_validation_error_missing_name(self, async_client):
        """Create account without name returns 422."""
        payload = {
            "currency": "GBP",
            "current_balance": 1000.00,
            "balance_updated_at": datetime.utcnow().isoformat() + "Z"
        }

        response = await async_client.post("/api/accounts", json=payload)

        assert response.status_code == 422
        data = response.json()
        assert "detail" in data

    @pytest.mark.asyncio
    async def test_create_account_validation_error_invalid_currency(self, async_client):
        """Create account with invalid currency returns 422."""
        payload = {
            "name": "Test Account",
            "currency": "gb",  # Invalid: not 3 uppercase letters
            "current_balance": 1000.00,
            "balance_updated_at": datetime.utcnow().isoformat() + "Z"
        }

        response = await async_client.post("/api/accounts", json=payload)

        assert response.status_code == 422
        data = response.json()
        assert "detail" in data


# ============================================================================
# PATCH /api/accounts/{id} - Update Account
# ============================================================================

class TestAccountUpdate:
    """Tests for PATCH /api/accounts/{id} endpoint."""

    @pytest.mark.asyncio
    async def test_update_account_name_success(self, async_client, sample_account):
        """Update account name returns updated data."""
        payload = {"name": "Updated Account Name"}

        response = await async_client.patch(
            f"/api/accounts/{sample_account.id}",
            json=payload
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Account Name"
        assert data["currency"] == "GBP"  # Unchanged
        assert data["id"] == str(sample_account.id)

    @pytest.mark.asyncio
    async def test_update_balance_sets_pending_reconciliation(
        self, async_client, sample_account
    ):
        """Updating balance sets pending_reconciliation=true."""
        payload = {
            "current_balance": 2500.00,
            "balance_updated_at": datetime.utcnow().isoformat() + "Z"
        }

        response = await async_client.patch(
            f"/api/accounts/{sample_account.id}",
            json=payload
        )

        assert response.status_code == 200
        data = response.json()
        assert data["current_balance"] == "2500.00"
        assert data["pending_reconciliation"] is True

    @pytest.mark.asyncio
    async def test_update_account_to_default_unsets_previous(
        self, async_client, sample_account, sample_account_usd
    ):
        """Updating account to default unsets previous default."""
        # sample_account is default, sample_account_usd is not
        assert sample_account.is_default is True

        # Update USD account to be default
        payload = {"is_default": True}

        response = await async_client.patch(
            f"/api/accounts/{sample_account_usd.id}",
            json=payload
        )

        assert response.status_code == 200
        data = response.json()
        assert data["is_default"] is True

        # Verify old default is no longer default
        old_response = await async_client.get(f"/api/accounts/{sample_account.id}")
        old_data = old_response.json()
        assert old_data["is_default"] is False

    @pytest.mark.asyncio
    async def test_update_account_not_found(self, async_client):
        """Update non-existent account returns 404."""
        from uuid import uuid4
        fake_id = uuid4()

        payload = {"name": "New Name"}
        response = await async_client.patch(
            f"/api/accounts/{fake_id}",
            json=payload
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_account_validation_error(self, async_client, sample_account):
        """Update with invalid data returns 422."""
        payload = {"currency": "invalid"}  # Invalid currency format

        response = await async_client.patch(
            f"/api/accounts/{sample_account.id}",
            json=payload
        )

        assert response.status_code == 422


# ============================================================================
# DELETE /api/accounts/{id} - Archive Account
# ============================================================================

class TestAccountDelete:
    """Tests for DELETE /api/accounts/{id} endpoint (archive operation)."""

    @pytest.mark.asyncio
    async def test_archive_account_success(self, async_client, sample_account_usd):
        """DELETE sets is_archived=true (soft delete)."""
        response = await async_client.delete(f"/api/accounts/{sample_account_usd.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Account archived successfully"

        # Verify account is archived
        get_response = await async_client.get(
            f"/api/accounts/{sample_account_usd.id}"
        )
        assert get_response.status_code == 200
        account_data = get_response.json()
        assert account_data["is_archived"] is True

    @pytest.mark.asyncio
    async def test_archive_account_not_found(self, async_client):
        """DELETE non-existent account returns 404."""
        from uuid import uuid4
        fake_id = uuid4()

        response = await async_client.delete(f"/api/accounts/{fake_id}")

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_archived_account_excluded_from_list(
        self, async_client, sample_account, sample_account_usd
    ):
        """Archived account excluded from default list."""
        # Archive USD account
        await async_client.delete(f"/api/accounts/{sample_account_usd.id}")

        # List accounts (without include_archived)
        response = await async_client.get("/api/accounts")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["id"] == str(sample_account.id)
