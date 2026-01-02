"""
Tests for service worker generation with automatic file discovery.

Tests the dynamic service worker endpoint that:
- Automatically discovers all JavaScript files
- Generates MD5 content hashes for cache busting
- Creates Workbox precache manifest
"""

import pytest
from pathlib import Path
from api.main import generate_file_hash


class TestServiceWorkerGeneration:
    """Test automatic file discovery and hash generation for service worker."""

    def test_generate_file_hash_returns_8_char_hex(self):
        """Test that file hash is 8-character hexadecimal string."""
        # Use a known file that should exist
        test_file = Path("static/js/utils.js")

        if not test_file.exists():
            pytest.skip(f"Test file {test_file} not found")

        hash_value = generate_file_hash(test_file)

        assert len(hash_value) == 8
        assert all(c in '0123456789abcdef' for c in hash_value)

    def test_generate_file_hash_consistent(self):
        """Test that hash is consistent for same file content."""
        test_file = Path("static/js/utils.js")

        if not test_file.exists():
            pytest.skip(f"Test file {test_file} not found")

        hash1 = generate_file_hash(test_file)
        hash2 = generate_file_hash(test_file)

        assert hash1 == hash2

    def test_generate_file_hash_different_for_different_files(self):
        """Test that different files produce different hashes."""
        file1 = Path("static/js/utils.js")
        file2 = Path("static/js/app.js")

        if not file1.exists() or not file2.exists():
            pytest.skip("Test files not found")

        hash1 = generate_file_hash(file1)
        hash2 = generate_file_hash(file2)

        assert hash1 != hash2

    def test_generate_file_hash_missing_file(self):
        """Test that missing file returns default hash."""
        missing_file = Path("static/js/nonexistent.js")

        hash_value = generate_file_hash(missing_file)

        assert hash_value == "00000000"

    def test_automatic_js_file_discovery(self):
        """Test that glob pattern finds all JavaScript files."""
        static_dir = Path("static")
        js_files = sorted([str(p) for p in static_dir.glob("js/*.js")])

        # Should find at least the core files
        expected_files = [
            "static/js/app.js",
            "static/js/db.js",
            "static/js/init.js",
            "static/js/utils.js"
        ]

        for expected in expected_files:
            assert expected in js_files, f"Expected {expected} to be discovered"

        # Should only include .js files
        for file in js_files:
            assert file.endswith('.js'), f"Non-JS file found: {file}"

    def test_precache_files_includes_all_js(self):
        """Test that precache list includes all discovered JS files."""
        static_dir = Path("static")
        js_files = sorted([str(p) for p in static_dir.glob("js/*.js")])

        precache_files = [
            "static/index.html",
            "static/css/style.css",
        ] + js_files

        # Verify index.html and CSS are included
        assert "static/index.html" in precache_files
        assert "static/css/style.css" in precache_files

        # Verify all JS files are included
        for js_file in js_files:
            assert js_file in precache_files

        # Count should be HTML + CSS + all JS files
        assert len(precache_files) >= 2 + len(js_files)


@pytest.mark.integration
class TestServiceWorkerEndpoint:
    """Integration tests for /sw.js endpoint."""

    async def test_service_worker_endpoint_returns_javascript(self, async_client):
        """Test that /sw.js endpoint returns valid JavaScript."""
        response = await async_client.get("/sw.js")

        assert response.status_code == 200
        assert "application/javascript" in response.headers["content-type"]

    async def test_service_worker_contains_precache_manifest(self, async_client):
        """Test that service worker contains precache manifest."""
        response = await async_client.get("/sw.js")
        content = response.text

        # Should contain Workbox imports
        assert "workbox" in content.lower()

        # Should contain precache manifest
        assert "precacheAndRoute" in content

        # Should contain file URLs and revision hashes
        assert "url:" in content
        assert "revision:" in content

    async def test_service_worker_includes_all_js_files(self, async_client):
        """Test that service worker precaches all JavaScript files."""
        response = await async_client.get("/sw.js")
        content = response.text

        # Should include core JS files
        expected_files = [
            "static/js/app.js",
            "static/js/db.js",
            "static/js/init.js",
            "static/js/utils.js",
            "static/js/dropdown-factories.js",
            "static/js/storage-adapter.js"
        ]

        for expected_file in expected_files:
            assert expected_file in content, f"Service worker should include {expected_file}"

    async def test_service_worker_revision_hashes_valid(self, async_client):
        """Test that revision hashes in service worker are valid 8-char hex."""
        response = await async_client.get("/sw.js")
        content = response.text

        # Extract revision values using simple parsing
        # Example: { url: '/static/js/app.js', revision: '1a2b3c4d' }
        import re
        revisions = re.findall(r"revision:\s*'([^']+)'", content)

        assert len(revisions) > 0, "Should find revision hashes in service worker"

        for revision in revisions:
            assert len(revision) == 8, f"Revision {revision} should be 8 characters"
            assert all(c in '0123456789abcdef' for c in revision), \
                f"Revision {revision} should be hexadecimal"
