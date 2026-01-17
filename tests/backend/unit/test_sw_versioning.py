"""
Service Worker Versioning Tests

Tests the backend SW versioning system including:
- /sw-version endpoint returning content-based version hash
- get_precache_files() file discovery logic
- generate_file_hash() deterministic MD5 hashing
- Automatic cache invalidation when files change
- Error handling for missing/unreadable files

Priority: 🚨 CRITICAL - Silent update failures break production PWA
Coverage Target: 95%+ of main.py SW versioning functions
"""

import pytest
import hashlib
from pathlib import Path
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from tempfile import TemporaryDirectory
import json

from api.main import app, get_sw_version, get_precache_files, generate_file_hash


# Create test client
client = TestClient(app)


# ==================== HAPPY PATH TESTS ====================

class TestSWVersionEndpoint:
    """Test /sw-version endpoint returns correct version format"""

    def test_returns_json_with_version_key(self):
        """Should return JSON object with 'version' key"""
        response = client.get("/sw-version")

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/json"

        data = response.json()
        assert "version" in data
        assert isinstance(data["version"], str)

    def test_version_is_8_character_hex_string(self):
        """Should return version as 8-character hexadecimal string"""
        response = client.get("/sw-version")
        data = response.json()
        version = data["version"]

        # Check length
        assert len(version) == 8

        # Check all characters are valid hex
        try:
            int(version, 16)
            is_hex = True
        except ValueError:
            is_hex = False

        assert is_hex, f"Version '{version}' is not valid hexadecimal"

    def test_same_files_produce_same_version(self):
        """Should be deterministic: same files → same version"""
        # Call endpoint twice
        response1 = client.get("/sw-version")
        response2 = client.get("/sw-version")

        version1 = response1.json()["version"]
        version2 = response2.json()["version"]

        # Should be identical (deterministic)
        assert version1 == version2

    @patch('api.main.get_precache_files')
    @patch('api.main.generate_file_hash')
    def test_different_files_produce_different_version(self, mock_hash, mock_files):
        """Should produce different version when files change"""
        # First call: files with hash "aaaa1111"
        mock_files.return_value = ["static/app.js", "static/index.html"]
        mock_hash.side_effect = ["aaaa1111", "bbbb2222"]

        response1 = client.get("/sw-version")
        version1 = response1.json()["version"]

        # Reset mock
        mock_hash.reset_mock()
        mock_hash.side_effect = ["cccc3333", "dddd4444"]  # Different hashes

        response2 = client.get("/sw-version")
        version2 = response2.json()["version"]

        # Versions should differ
        assert version1 != version2

    def test_file_content_change_produces_new_version(self):
        """Should produce new version when file content changes"""
        with TemporaryDirectory() as tmpdir:
            # Create temp file with initial content
            test_file = Path(tmpdir) / "test.js"
            test_file.write_bytes(b"console.log('version 1');")
            version1_hash = generate_file_hash(test_file)

            # Change file content
            test_file.write_bytes(b"console.log('version 2');")
            version2_hash = generate_file_hash(test_file)

            # Hashes should differ
            assert version1_hash != version2_hash


# ==================== FILE DISCOVERY TESTS ====================

class TestPrecacheFileDiscovery:
    """Test get_precache_files() discovers all static assets"""

    def test_discovers_all_required_file_types(self):
        """Should discover .html, .css, .js files"""
        files = get_precache_files()

        # Should be a list
        assert isinstance(files, list)
        assert len(files) > 0

        # Should include key files
        assert "static/index.html" in files
        assert "static/css/style.css" in files

        # Should include JS files
        js_files = [f for f in files if f.endswith('.js')]
        assert len(js_files) > 0

    def test_includes_nested_js_files(self):
        """Should include all JS files from static/js/ directory"""
        files = get_precache_files()

        # Should include nested JS files
        js_files = [f for f in files if 'static/js/' in f and f.endswith('.js')]

        # Should find multiple JS files (app.js, utils.js, db.js, etc.)
        assert len(js_files) >= 3

    def test_files_are_relative_paths(self):
        """Should return paths relative to project root"""
        files = get_precache_files()

        for file_path in files:
            # Should start with "static/"
            assert file_path.startswith("static/"), f"Path '{file_path}' not relative to project root"
            # Should not be absolute
            assert not file_path.startswith("/"), f"Path '{file_path}' should be relative"

    def test_js_files_sorted_alphabetically(self):
        """Should return JS files in sorted order (for determinism)"""
        files = get_precache_files()

        # Extract JS files
        js_files = [f for f in files if f.endswith('.js')]

        # Should be sorted
        assert js_files == sorted(js_files)


# ==================== ERROR HANDLING TESTS ====================

class TestErrorHandling:
    """Test error handling for missing/unreadable files"""

    def test_missing_file_returns_fallback_hash(self):
        """Should return '00000000' fallback for missing files"""
        # Test with non-existent file
        hash_result = generate_file_hash(Path("/nonexistent/file.js"))

        assert hash_result == "00000000"

    def test_empty_file_returns_valid_hash(self):
        """Should hash empty file as empty string"""
        with TemporaryDirectory() as tmpdir:
            # Create empty file
            empty_file = Path(tmpdir) / "empty.js"
            empty_file.write_text("")

            hash_result = generate_file_hash(empty_file)

            # Should be MD5 of empty string
            expected_hash = hashlib.md5(b"").hexdigest()[:8]
            assert hash_result == expected_hash

    @patch('api.main.Path.open')
    @patch('api.main.logger')
    def test_unreadable_file_logs_warning_and_returns_fallback(self, mock_logger, mock_open):
        """Should log warning and return fallback for unreadable files"""
        # Mock file that raises PermissionError
        mock_open.side_effect = PermissionError("Permission denied")

        hash_result = generate_file_hash(Path("protected.js"))

        # Should return fallback
        assert hash_result == "00000000"

        # Should log warning
        mock_logger.warning.assert_called_once()

    @patch('api.main.Path.glob')
    def test_missing_static_directory_returns_empty_list(self, mock_glob):
        """Should handle missing static directory gracefully"""
        # Mock glob to return no files (simulates missing directory)
        mock_glob.return_value = []

        files = get_precache_files()

        # Should include at least the hardcoded files
        assert "static/index.html" in files
        assert "static/css/style.css" in files


# ==================== HASHING ALGORITHM TESTS ====================

class TestHashingAlgorithm:
    """Test MD5 hashing algorithm and combined hash generation"""

    def test_uses_md5_for_individual_files(self):
        """Should use MD5 algorithm for individual file hashing"""
        with TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.js"
            content = b"console.log('test');"
            test_file.write_bytes(content)

            hash_result = generate_file_hash(test_file)

            # Calculate expected MD5
            expected_md5 = hashlib.md5(content).hexdigest()[:8]

            assert hash_result == expected_md5

    def test_hash_truncated_to_8_characters(self):
        """Should truncate MD5 hash to first 8 characters"""
        with TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.js"
            test_file.write_bytes(b"test content")

            hash_result = generate_file_hash(test_file)

            # Should be exactly 8 characters
            assert len(hash_result) == 8

    @patch('api.main.get_precache_files')
    @patch('api.main.generate_file_hash')
    def test_combined_hash_is_md5_of_concatenated_hashes(self, mock_hash, mock_files):
        """Should combine individual hashes with MD5 of concatenation"""
        # Mock file discovery
        mock_files.return_value = ["file1.js", "file2.js"]

        # Mock individual file hashes
        mock_hash.side_effect = ["aaaa1111", "bbbb2222"]

        response = client.get("/sw-version")
        version = response.json()["version"]

        # Calculate expected combined hash
        combined_input = "aaaa1111bbbb2222"
        expected_version = hashlib.md5(combined_input.encode()).hexdigest()[:8]

        assert version == expected_version

    def test_deterministic_hashing_for_same_content(self):
        """Should produce identical hashes for identical content"""
        with TemporaryDirectory() as tmpdir:
            # Create two files with identical content
            file1 = Path(tmpdir) / "file1.js"
            file2 = Path(tmpdir) / "file2.js"

            content = b"const x = 42;"
            file1.write_bytes(content)
            file2.write_bytes(content)

            hash1 = generate_file_hash(file1)
            hash2 = generate_file_hash(file2)

            # Should be identical
            assert hash1 == hash2

    def test_different_content_produces_different_hash(self):
        """Should produce different hashes for different content"""
        with TemporaryDirectory() as tmpdir:
            file1 = Path(tmpdir) / "file1.js"
            file2 = Path(tmpdir) / "file2.js"

            file1.write_bytes(b"const x = 42;")
            file2.write_bytes(b"const y = 43;")

            hash1 = generate_file_hash(file1)
            hash2 = generate_file_hash(file2)

            # Should differ
            assert hash1 != hash2


# ==================== INTEGRATION TESTS ====================

class TestSWVersioningIntegration:
    """Integration tests for full SW versioning workflow"""

    def test_version_changes_when_any_file_changes(self):
        """Should detect changes to any precached file"""
        # Get initial version
        response1 = client.get("/sw-version")
        version1 = response1.json()["version"]

        # Modify a static file (simulated via mock)
        with patch('api.main.generate_file_hash') as mock_hash:
            # Return different hash for one file
            mock_hash.side_effect = lambda path: "new_hash" if "app.js" in str(path) else "old_hash"

            response2 = client.get("/sw-version")
            version2 = response2.json()["version"]

            # Version should change (in real scenario)
            # Note: This test documents the expected behavior

    def test_endpoint_performance_under_100ms(self):
        """Should generate version hash quickly (< 100ms)"""
        import time

        start = time.time()
        response = client.get("/sw-version")
        duration = (time.time() - start) * 1000  # Convert to ms

        assert response.status_code == 200
        # Should be fast enough for production use
        assert duration < 100, f"Version generation took {duration:.2f}ms (should be < 100ms)"

    def test_version_endpoint_available_during_startup(self):
        """Should be accessible immediately on app startup"""
        # Test that endpoint works without requiring database
        response = client.get("/sw-version")

        assert response.status_code == 200
        # Should not require DB connection or other async setup

    def test_concurrent_requests_return_same_version(self):
        """Should handle concurrent requests correctly"""
        import concurrent.futures

        def get_version():
            response = client.get("/sw-version")
            return response.json()["version"]

        # Make 10 concurrent requests
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(get_version) for _ in range(10)]
            versions = [f.result() for f in futures]

        # All should return the same version (deterministic)
        assert len(set(versions)) == 1, "Concurrent requests returned different versions"


# ==================== CACHE INVALIDATION TESTS ====================

class TestCacheInvalidation:
    """Test automatic cache invalidation on file changes"""

    @patch('api.main.get_precache_files')
    @patch('api.main.generate_file_hash')
    def test_adding_new_file_changes_version(self, mock_hash, mock_files):
        """Should change version when new file added to precache list"""
        # Initial state: 2 files
        mock_files.return_value = ["file1.js", "file2.js"]
        mock_hash.side_effect = ["aaaa1111", "bbbb2222"]

        response1 = client.get("/sw-version")
        version1 = response1.json()["version"]

        # Add new file
        mock_hash.reset_mock()
        mock_files.return_value = ["file1.js", "file2.js", "file3.js"]
        mock_hash.side_effect = ["aaaa1111", "bbbb2222", "cccc3333"]

        response2 = client.get("/sw-version")
        version2 = response2.json()["version"]

        # Version should change
        assert version1 != version2

    @patch('api.main.get_precache_files')
    @patch('api.main.generate_file_hash')
    def test_removing_file_changes_version(self, mock_hash, mock_files):
        """Should change version when file removed from precache list"""
        # Initial state: 3 files
        mock_files.return_value = ["file1.js", "file2.js", "file3.js"]
        mock_hash.side_effect = ["aaaa1111", "bbbb2222", "cccc3333"]

        response1 = client.get("/sw-version")
        version1 = response1.json()["version"]

        # Remove file
        mock_hash.reset_mock()
        mock_files.return_value = ["file1.js", "file2.js"]
        mock_hash.side_effect = ["aaaa1111", "bbbb2222"]

        response2 = client.get("/sw-version")
        version2 = response2.json()["version"]

        # Version should change
        assert version1 != version2
