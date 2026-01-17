"""
Smoke tests for test infrastructure.

Verifies that conftest.py fixtures work correctly before implementing
full endpoint tests.
"""

import pytest


class TestInfrastructure:
    """Verify test infrastructure is working."""

    @pytest.mark.asyncio
    async def test_clean_database_fixture(self, clean_database):
        """Test that clean_database fixture provides a working database."""
        # Should be able to list collections
        collections = await clean_database.list_collection_names()
        assert isinstance(collections, list)

    @pytest.mark.asyncio
    async def test_async_client_fixture(self, async_client):
        """Test that async_client fixture works."""
        # Should be able to make request to health endpoint
        response = await async_client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data

    @pytest.mark.asyncio
    async def test_sample_account_fixture(self, sample_account):
        """Test that sample_account fixture creates an account."""
        assert sample_account is not None
        assert sample_account.name == "Test Account"
        assert sample_account.currency == "GBP"
        assert sample_account.is_default is True

    @pytest.mark.asyncio
    async def test_sample_story_fixture(self, sample_story):
        """Test that sample_story fixture creates a story."""
        assert sample_story is not None
        assert sample_story.name == "Test Story"
        assert sample_story.funding_mode == "projected"

    @pytest.mark.asyncio
    async def test_account_repo_fixture(self, account_repo):
        """Test that account_repo fixture provides repository."""
        assert account_repo is not None
        # Should be able to count accounts
        count = await account_repo.count({})
        assert count == 0  # Fresh database
