"""
Service Worker Generation Tests

Tests the /sw.js endpoint that dynamically generates service worker content with
automatic revision numbers based on file content hashes.

Key Scenarios:
- Content-Type header validation (application/javascript)
- Workbox imports present in generated code
- Precache list generation with URLs and revision hashes
- Cache strategy routes (CacheFirst, NetworkFirst)
- Generated code is valid JavaScript

Priority: 💡 MEDIUM - Ensures SW is correctly generated for PWA functionality
Coverage Target: 95%+ of /sw.js endpoint and SW generation logic
"""

import pytest
import re
from fastapi.testclient import TestClient

from api.main import app

# Create test client
client = TestClient(app)


# ==================== HAPPY PATH TESTS ====================

class TestSWGenerationEndpoint:
    """Test /sw.js endpoint returns correct service worker content"""

    def test_returns_javascript_content_type(self):
        """Should return application/javascript content-type"""
        response = client.get("/sw.js")

        assert response.status_code == 200
        assert "javascript" in response.headers["content-type"].lower()

    def test_contains_workbox_import(self):
        """Should import Workbox from CDN"""
        response = client.get("/sw.js")
        content = response.text

        # Check for Workbox CDN import
        assert "importScripts" in content
        assert "workbox-sw.js" in content
        assert "storage.googleapis.com/workbox-cdn" in content

    def test_contains_precache_route_call(self):
        """Should call workbox.precaching.precacheAndRoute()"""
        response = client.get("/sw.js")
        content = response.text

        # Check for precacheAndRoute call
        assert "workbox.precaching.precacheAndRoute" in content

    def test_precache_list_contains_static_files(self):
        """Should include static/index.html and static/css/style.css in precache list"""
        response = client.get("/sw.js")
        content = response.text

        # Check for key static files
        assert "/static/index.html" in content
        assert "/static/css/style.css" in content

    def test_precache_entries_have_revision_hashes(self):
        """Should generate revision hashes for each precached file"""
        response = client.get("/sw.js")
        content = response.text

        # Check for revision hash format: { url: '/static/...', revision: 'abc12345' }
        # Revision should be 8-character hex string
        revision_pattern = r"revision:\s*'[0-9a-f]{8}'"
        matches = re.findall(revision_pattern, content)

        # Should have multiple precache entries with revisions
        assert len(matches) >= 3, "Should have at least 3 precache entries with revisions"


# ==================== CACHE STRATEGY TESTS ====================

class TestCacheStrategies:
    """Test generated SW includes correct caching strategies"""

    def test_includes_cache_first_strategy(self):
        """Should include CacheFirst strategy for static assets"""
        response = client.get("/sw.js")
        content = response.text

        assert "CacheFirst" in content
        assert "external-resources" in content.lower()

    def test_includes_network_first_strategy(self):
        """Should include NetworkFirst strategy for API calls"""
        response = client.get("/sw.js")
        content = response.text

        assert "NetworkFirst" in content
        assert "/api/" in content

    def test_includes_expiration_plugin(self):
        """Should use ExpirationPlugin to limit cache size"""
        response = client.get("/sw.js")
        content = response.text

        assert "ExpirationPlugin" in content
        assert "maxEntries" in content
        assert "maxAgeSeconds" in content

    def test_includes_cacheable_response_plugin(self):
        """Should use CacheableResponsePlugin to filter responses"""
        response = client.get("/sw.js")
        content = response.text

        assert "CacheableResponsePlugin" in content

    def test_includes_register_route_calls(self):
        """Should call registerRoute to setup caching strategies"""
        response = client.get("/sw.js")
        content = response.text

        # Should have multiple registerRoute calls
        register_route_count = content.count("registerRoute")
        assert register_route_count >= 2, "Should have at least 2 registerRoute calls"


# ==================== GENERATED CODE VALIDITY ====================

class TestGeneratedCodeValidity:
    """Test that generated service worker is valid JavaScript"""

    def test_no_syntax_errors_in_template(self):
        """Should generate valid JavaScript without syntax errors"""
        response = client.get("/sw.js")
        content = response.text

        # Check for balanced braces
        assert content.count("{") == content.count("}")

        # Check for balanced brackets
        assert content.count("[") == content.count("]")

        # Check for balanced parentheses
        assert content.count("(") == content.count(")")

    def test_includes_cache_names(self):
        """Should define cache names for different strategies"""
        response = client.get("/sw.js")
        content = response.text

        # Check for cache name definitions
        assert "cacheName" in content

    def test_includes_documentation_comments(self):
        """Should include JSDoc comments explaining functionality"""
        response = client.get("/sw.js")
        content = response.text

        # Check for documentation
        assert "/**" in content  # JSDoc comment start
        assert "*/" in content   # JSDoc comment end
        assert "CHAPTR Service Worker" in content

    def test_precache_entries_are_comma_separated(self):
        """Should generate comma-separated precache entries"""
        response = client.get("/sw.js")
        content = response.text

        # Extract precache array (between precacheAndRoute([ and ]))
        match = re.search(r'precacheAndRoute\(\[(.*?)\]\)', content, re.DOTALL)
        assert match, "Should find precacheAndRoute array"

        precache_content = match.group(1)

        # Check for proper comma separation (at least one comma between entries)
        assert "," in precache_content, "Precache entries should be comma-separated"

    def test_no_python_template_artifacts(self):
        """Should not contain Python f-string artifacts or template errors"""
        import re
        response = client.get("/sw.js")
        content = response.text

        # Check for common f-string artifacts
        assert "{precache_list}" not in content, "Should not have unresolved template variables"
        assert "f\"" not in content, "Should not have Python f-string syntax"
        # Check for f' at word boundaries (start of line or after whitespace)
        # This avoids false positives from hashes ending in 'f' like '1d50ea5f'
        assert not re.search(r"(?:^|\s)f'", content), "Should not have Python f-string syntax"


# ==================== OFFLINE NAVIGATION TESTS ====================

class TestNavigationFallback:
    """Test service worker handles navigation requests for offline support"""

    def test_includes_navigation_request_handler(self):
        """Should include handler for navigation requests (request.mode === 'navigate')"""
        response = client.get("/sw.js")
        content = response.text

        # Check for navigation mode check
        assert "request.mode === 'navigate'" in content or "request.mode==='navigate'" in content, \
            "Should check for navigation requests"

    def test_navigation_handler_serves_cached_index(self):
        """Should serve cached index.html for offline navigation requests"""
        response = client.get("/sw.js")
        content = response.text

        # Check for fallback to index.html
        assert "/static/index.html" in content, "Should reference index.html for fallback"
        assert "getCacheKeyForURL" in content, "Should use Workbox cache key lookup"

    def test_navigation_handler_has_try_catch(self):
        """Should handle network errors gracefully with try/catch"""
        response = client.get("/sw.js")
        content = response.text

        # Navigation handler should have error handling
        # Look for try/catch pattern near navigate check
        assert "try {" in content or "try{" in content, "Should have try block for error handling"
        assert "catch" in content, "Should have catch block for error handling"


# ==================== MODULE PRECACHING TESTS ====================

class TestModulePrecaching:
    """Test that JS modules subdirectory is properly precached"""

    def test_precache_includes_modules_directory(self):
        """Should include files from js/modules/ subdirectory in precache"""
        response = client.get("/sw.js")
        content = response.text

        # Check for module files
        assert "/static/js/modules/" in content, "Should include modules directory in precache"

    def test_precache_includes_entity_operations_module(self):
        """Should include entity-operations.js module"""
        response = client.get("/sw.js")
        content = response.text

        assert "entity-operations.js" in content, "Should precache entity-operations.js module"

    def test_precache_includes_formatting_module(self):
        """Should include formatting.js module"""
        response = client.get("/sw.js")
        content = response.text

        assert "formatting.js" in content, "Should precache formatting.js module"

    def test_precache_includes_all_extracted_modules(self):
        """Should include all modules extracted from app.js"""
        response = client.get("/sw.js")
        content = response.text

        expected_modules = [
            "entity-operations.js",
            "formatting.js",
            "balance-utils.js",
            "auto-sync.js",
            "conflict-utils.js"
        ]

        for module in expected_modules:
            assert module in content, f"Should precache {module} module"
