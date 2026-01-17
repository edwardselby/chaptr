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
    async def test_list_accounts_empty(self, async_client, auth_headers):
        """Empty database returns empty list."""
        response = await async_client.get("/api/accounts", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data == []

    @pytest.mark.asyncio
    async def test_list_accounts_returns_accounts(self, async_client, sample_account, auth_headers):
        """List returns created accounts."""
        response = await async_client.get("/api/accounts", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["name"] == "Test Account"
        assert data[0]["currency"] == "GBP"

    @pytest.mark.asyncio
    async def test_list_accounts_excludes_archived_by_default(
        self, async_client, sample_account, sample_archived_account, auth_headers
    ):
        """Archived accounts excluded by default."""
        response = await async_client.get("/api/accounts", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["name"] == "Test Account"
        assert data[0]["is_archived"] is False

    @pytest.mark.asyncio
    async def test_list_accounts_includes_archived_when_requested(
        self, async_client, sample_account, sample_archived_account, auth_headers
    ):
        """include_archived=true includes archived accounts."""
        response = await async_client.get("/api/accounts?include_archived=true", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2

        # Check both accounts present
        names = {acc["name"] for acc in data}
        assert "Test Account" in names
        assert "Archived Account" in names

    @pytest.mark.asyncio
    async def test_list_accounts_multiple_accounts(
        self, async_client, sample_account, sample_account_usd, auth_headers
    ):
        """List returns multiple active accounts."""
        response = await async_client.get("/api/accounts", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2


# ============================================================================
# GET /api/accounts/{id} - Get Single Account
# ============================================================================

class TestAccountGet:
    """Tests for GET /api/accounts/{id} endpoint."""

    @pytest.mark.asyncio
    async def test_get_account_success(self, async_client, sample_account, auth_headers):
        """Get existing account returns 200 with account data."""
        response = await async_client.get(f"/api/accounts/{sample_account.id}", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(sample_account.id)
        assert data["name"] == "Test Account"
        assert data["currency"] == "GBP"
        assert data["current_balance"] == "1000.00"
        assert data["is_default"] is True

    @pytest.mark.asyncio
    async def test_get_account_not_found(self, async_client, auth_headers):
        """Get non-existent account returns 404."""
        from uuid import uuid4
        fake_id = uuid4()

        response = await async_client.get(f"/api/accounts/{fake_id}", headers=auth_headers)

        assert response.status_code == 404
        data = response.json()
        assert "detail" in data

    @pytest.mark.asyncio
    async def test_get_archived_account_success(self, async_client, sample_archived_account, auth_headers):
        """Can get archived account by ID (doesn't filter archived)."""
        response = await async_client.get(f"/api/accounts/{sample_archived_account.id}", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["is_archived"] is True


# ============================================================================
# POST /api/accounts - Create Account
# ============================================================================

class TestAccountCreate:
    """Tests for POST /api/accounts endpoint."""

    @pytest.mark.asyncio
    async def test_create_first_account_auto_sets_default(self, async_client, auth_headers):
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

        response = await async_client.post("/api/accounts", json=payload, headers=auth_headers)

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "First Account"
        assert data["is_default"] is True  # Auto-set by system
        assert data["id"] is not None
        assert data["created_at"] is not None

    @pytest.mark.asyncio
    async def test_create_second_account_not_default(self, async_client, sample_account, auth_headers):
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

        response = await async_client.post("/api/accounts", json=payload, headers=auth_headers)

        assert response.status_code == 201
        data = response.json()
        assert data["is_default"] is False

    @pytest.mark.asyncio
    async def test_create_account_with_default_conflicts_if_default_exists(
        self, async_client, sample_account, auth_headers
    ):
        """Creating account with is_default=True when default exists returns 409."""
        # Verify sample_account is default
        assert sample_account.is_default is True

        # Try to create new account as default (should fail with 409)
        payload = {
            "name": "New Default Account",
            "currency": "USD",
            "current_balance": 3000.00,
            "balance_updated_at": datetime.utcnow().isoformat() + "Z",
            "is_default": True,
            "is_archived": False,
            "pending_reconciliation": False
        }

        response = await async_client.post("/api/accounts", json=payload, headers=auth_headers)

        # Should return 409 Conflict (must unset existing default first)
        assert response.status_code == 409
        data = response.json()
        assert "default" in data["detail"].lower()

    @pytest.mark.asyncio
    async def test_change_default_requires_explicit_unset(
        self, async_client, sample_account, auth_headers
    ):
        """Changing default account requires explicitly unsetting old default first."""
        # Verify sample_account is default
        assert sample_account.is_default is True

        # Create new account (NOT as default)
        payload = {
            "name": "New Account",
            "currency": "USD",
            "current_balance": 3000.00,
            "balance_updated_at": datetime.utcnow().isoformat() + "Z",
            "is_default": False,
            "is_archived": False,
            "pending_reconciliation": False
        }
        create_response = await async_client.post("/api/accounts", json=payload, headers=auth_headers)
        assert create_response.status_code == 201
        new_account_id = create_response.json()["id"]

        # Unset old default first
        unset_response = await async_client.put(
            f"/api/accounts/{sample_account.id}",
            json={"is_default": False},
            headers=auth_headers
        )
        assert unset_response.status_code == 200

        # Now set new account as default
        set_response = await async_client.put(
            f"/api/accounts/{new_account_id}",
            json={"is_default": True},
            headers=auth_headers
        )
        assert set_response.status_code == 200
        assert set_response.json()["is_default"] is True

        # Verify only new account is default
        list_response = await async_client.get("/api/accounts", headers=auth_headers)
        accounts = list_response.json()
        default_accounts = [acc for acc in accounts if acc["is_default"] is True]
        assert len(default_accounts) == 1
        assert default_accounts[0]["id"] == new_account_id

    @pytest.mark.asyncio
    async def test_create_account_validation_error_missing_name(self, async_client, auth_headers):
        """Create account without name returns 422."""
        payload = {
            "currency": "GBP",
            "current_balance": 1000.00,
            "balance_updated_at": datetime.utcnow().isoformat() + "Z"
        }

        response = await async_client.post("/api/accounts", json=payload, headers=auth_headers)

        assert response.status_code == 422
        data = response.json()
        assert "detail" in data

    @pytest.mark.asyncio
    async def test_create_account_validation_error_invalid_currency(self, async_client, auth_headers):
        """Create account with invalid currency returns 422."""
        payload = {
            "name": "Test Account",
            "currency": "gb",  # Invalid: not 3 uppercase letters
            "current_balance": 1000.00,
            "balance_updated_at": datetime.utcnow().isoformat() + "Z"
        }

        response = await async_client.post("/api/accounts", json=payload, headers=auth_headers)

        assert response.status_code == 422
        data = response.json()
        assert "detail" in data


# ============================================================================
# PUT /api/accounts/{id} - Update Account
# ============================================================================

class TestAccountUpdate:
    """Tests for PUT /api/accounts/{id} endpoint."""

    @pytest.mark.asyncio
    async def test_update_account_name_success(self, async_client, sample_account, auth_headers):
        """Update account name returns updated data."""
        payload = {"name": "Updated Account Name"}

        response = await async_client.put(
            f"/api/accounts/{sample_account.id}",
            json=payload,
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Account Name"
        assert data["currency"] == "GBP"  # Unchanged
        assert data["id"] == str(sample_account.id)

    @pytest.mark.asyncio
    async def test_update_balance_sets_pending_reconciliation(
        self, async_client, sample_account, auth_headers
    ):
        """Updating balance sets pending_reconciliation=true."""
        payload = {
            "current_balance": 2500.00,
            "balance_updated_at": datetime.utcnow().isoformat() + "Z"
        }

        response = await async_client.put(
            f"/api/accounts/{sample_account.id}",
            json=payload,
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["current_balance"] == "2500.0"  # API returns single trailing zero
        assert data["pending_reconciliation"] is True

    @pytest.mark.asyncio
    async def test_update_account_to_default_conflicts_if_default_exists(
        self, async_client, sample_account, sample_account_usd, auth_headers
    ):
        """Updating account to default when another default exists returns 409."""
        # sample_account is default, sample_account_usd is not
        assert sample_account.is_default is True

        # Try to update USD account to be default (should fail with 409)
        payload = {"is_default": True}

        response = await async_client.put(
            f"/api/accounts/{sample_account_usd.id}",
            json=payload,
            headers=auth_headers
        )

        # Should return 409 Conflict (must unset existing default first)
        assert response.status_code == 409
        data = response.json()
        assert "default" in data["detail"].lower()

    @pytest.mark.asyncio
    async def test_update_account_not_found(self, async_client, auth_headers):
        """Update non-existent account returns 404."""
        from uuid import uuid4
        fake_id = uuid4()

        payload = {"name": "New Name"}
        response = await async_client.put(
            f"/api/accounts/{fake_id}",
            json=payload,
            headers=auth_headers
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_account_validation_error(self, async_client, sample_account, auth_headers):
        """Update with invalid data returns 422."""
        payload = {"currency": "invalid"}  # Invalid currency format

        response = await async_client.put(
            f"/api/accounts/{sample_account.id}",
            json=payload,
            headers=auth_headers
        )

        assert response.status_code == 422


# ============================================================================
# DELETE /api/accounts/{id} - Archive Account
# ============================================================================

class TestAccountDelete:
    """Tests for DELETE /api/accounts/{id} endpoint (archive operation)."""

    @pytest.mark.asyncio
    async def test_archive_account_success(self, async_client, sample_account, sample_account_usd, auth_headers):
        """DELETE sets is_archived=true (soft delete)."""
        # sample_account is default, sample_account_usd is not (so it can be archived)
        response = await async_client.delete(f"/api/accounts/{sample_account_usd.id}", headers=auth_headers)

        assert response.status_code == 204  # No content
        assert response.text == ""  # No body

        # Verify account is archived
        get_response = await async_client.get(
            f"/api/accounts/{sample_account_usd.id}",
            headers=auth_headers
        )
        assert get_response.status_code == 200
        account_data = get_response.json()
        assert account_data["is_archived"] is True

    @pytest.mark.asyncio
    async def test_archive_account_not_found(self, async_client, auth_headers):
        """DELETE non-existent account returns 404."""
        from uuid import uuid4
        fake_id = uuid4()

        response = await async_client.delete(f"/api/accounts/{fake_id}", headers=auth_headers)

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_archived_account_excluded_from_list(
        self, async_client, sample_account, sample_account_usd, auth_headers
    ):
        """Archived account excluded from default list."""
        # Archive USD account
        await async_client.delete(f"/api/accounts/{sample_account_usd.id}", headers=auth_headers)

        # List accounts (without include_archived)
        response = await async_client.get("/api/accounts", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["id"] == str(sample_account.id)
