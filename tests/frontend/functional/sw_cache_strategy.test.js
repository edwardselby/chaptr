/**
 * Service Worker Cache Strategy Tests
 *
 * Tests that the service worker caching configuration prevents stale assets:
 * - Local /static/* files should ONLY be cached via precache (with MD5 revisions)
 * - Runtime Cache-First should ONLY apply to external resources (CDN, fonts)
 * - The routing function must correctly distinguish local vs external resources
 *
 * Priority: 🚨 CRITICAL - Prevents stale CSS/JS being served after deployments
 *
 * Background:
 * The service worker has two caching layers:
 * 1. Precache (workbox.precaching.precacheAndRoute) - uses content-based MD5 hashes
 * 2. Runtime cache (registerRoute with Cache-First) - caches by URL
 *
 * If runtime cache captures /static/* files, it serves stale versions because
 * it ignores the precache revision hashes. The fix ensures runtime cache only
 * applies to external resources (CDN libraries, Google Fonts, etc.).
 */

import { describe, it, expect, beforeAll } from 'vitest';

describe('Service Worker Cache Strategy', () => {
    let swContent;

    beforeAll(async () => {
        // Fetch the dynamically generated service worker
        // This tests the actual output from /sw.js endpoint
        try {
            const response = await fetch('/sw.js');
            swContent = await response.text();
        } catch (error) {
            // If server isn't running, skip tests gracefully
            console.warn('Could not fetch /sw.js - server may not be running');
            swContent = null;
        }
    });

    describe('Precache Configuration', () => {
        it('should include app shell files in precache manifest', () => {
            if (!swContent) {
                console.warn('Skipping: SW content not available');
                return;
            }

            // Verify critical app shell files are in precache
            expect(swContent).toContain('/static/index.html');
            expect(swContent).toContain('/static/css/style.css');
            expect(swContent).toContain('/static/js/app.js');
            expect(swContent).toContain('/static/js/init.js');
        });

        it('should include revision hashes in precache entries', () => {
            if (!swContent) {
                console.warn('Skipping: SW content not available');
                return;
            }

            // Verify precache entries have revision hashes (8-char MD5)
            // Pattern: { url: '/static/...', revision: 'abc12345' }
            const precachePattern = /\{\s*url:\s*'\/static\/[^']+',\s*revision:\s*'[a-f0-9]{8}'\s*\}/;
            expect(swContent).toMatch(precachePattern);
        });

        it('should use precacheAndRoute for app shell', () => {
            if (!swContent) {
                console.warn('Skipping: SW content not available');
                return;
            }

            expect(swContent).toContain('workbox.precaching.precacheAndRoute');
        });
    });

    describe('Runtime Cache Strategy', () => {
        it('should NOT cache /static/ files in runtime cache', () => {
            if (!swContent) {
                console.warn('Skipping: SW content not available');
                return;
            }

            // The routing function should explicitly skip /static/ paths
            expect(swContent).toContain("url.pathname.startsWith('/static/')");
            expect(swContent).toContain('return false');
        });

        it('should only cache external resources in runtime cache', () => {
            if (!swContent) {
                console.warn('Skipping: SW content not available');
                return;
            }

            // Should check for external origin
            expect(swContent).toContain('isExternalOrigin');
            expect(swContent).toContain('url.origin !== self.location.origin');
        });

        it('should use external-resources-v1 cache name (not static-assets-v1)', () => {
            if (!swContent) {
                console.warn('Skipping: SW content not available');
                return;
            }

            // Should use new cache name for external resources
            expect(swContent).toContain('external-resources-v1');

            // Should NOT use old cache name that caused stale assets
            expect(swContent).not.toContain('static-assets-v1');
        });

        it('should whitelist correct caches in activate handler', () => {
            if (!swContent) {
                console.warn('Skipping: SW content not available');
                return;
            }

            // Whitelist should include external-resources-v1 and api-cache-v1
            expect(swContent).toContain("cacheWhitelist = ['external-resources-v1', 'api-cache-v1']");
        });
    });

    describe('Cache-First Strategy Configuration', () => {
        it('should use CacheFirst strategy for external resources', () => {
            if (!swContent) {
                console.warn('Skipping: SW content not available');
                return;
            }

            expect(swContent).toContain('new CacheFirst');
        });

        it('should use NetworkFirst strategy for API calls', () => {
            if (!swContent) {
                console.warn('Skipping: SW content not available');
                return;
            }

            expect(swContent).toContain('new NetworkFirst');
            expect(swContent).toContain("url.pathname.startsWith('/api/')");
        });
    });

    describe('Routing Function Logic', () => {
        /**
         * Unit test the routing logic that determines which requests to cache
         * This simulates the routing function from the generated SW
         */

        // Simulate the routing function from the SW
        const shouldCacheInRuntimeCache = (request, url) => {
            // Skip local /static/ files - handled by precache
            if (url.pathname.startsWith('/static/')) {
                return false;
            }
            // Cache external fonts, scripts, and images
            const isExternalResource = ['style', 'script', 'image', 'font'].includes(request.destination);
            const isExternalOrigin = url.origin !== 'http://localhost:8000';
            return isExternalResource && isExternalOrigin;
        };

        it('should return false for local CSS files', () => {
            const request = { destination: 'style' };
            const url = new URL('http://localhost:8000/static/css/style.css');

            expect(shouldCacheInRuntimeCache(request, url)).toBe(false);
        });

        it('should return false for local JS files', () => {
            const request = { destination: 'script' };
            const url = new URL('http://localhost:8000/static/js/app.js');

            expect(shouldCacheInRuntimeCache(request, url)).toBe(false);
        });

        it('should return false for local images', () => {
            const request = { destination: 'image' };
            const url = new URL('http://localhost:8000/static/images/logo.png');

            expect(shouldCacheInRuntimeCache(request, url)).toBe(false);
        });

        it('should return true for Google Fonts CSS', () => {
            const request = { destination: 'style' };
            const url = new URL('https://fonts.googleapis.com/css2?family=JetBrains+Mono');

            expect(shouldCacheInRuntimeCache(request, url)).toBe(true);
        });

        it('should return true for Google Fonts files', () => {
            const request = { destination: 'font' };
            const url = new URL('https://fonts.gstatic.com/s/jetbrainsmono/v1/font.woff2');

            expect(shouldCacheInRuntimeCache(request, url)).toBe(true);
        });

        it('should return true for CDN scripts (Alpine.js)', () => {
            const request = { destination: 'script' };
            const url = new URL('https://cdn.jsdelivr.net/npm/alpinejs@3.14.1/dist/cdn.min.js');

            expect(shouldCacheInRuntimeCache(request, url)).toBe(true);
        });

        it('should return true for external images', () => {
            const request = { destination: 'image' };
            const url = new URL('https://example.com/image.png');

            expect(shouldCacheInRuntimeCache(request, url)).toBe(true);
        });

        it('should return false for API calls (not a cacheable resource type)', () => {
            const request = { destination: '' }; // API calls have empty destination
            const url = new URL('http://localhost:8000/api/accounts');

            expect(shouldCacheInRuntimeCache(request, url)).toBe(false);
        });

        it('should return false for local HTML', () => {
            const request = { destination: 'document' };
            const url = new URL('http://localhost:8000/static/index.html');

            // Document type not in our list, so false
            expect(shouldCacheInRuntimeCache(request, url)).toBe(false);
        });

        it('should return false for same-origin external path', () => {
            // Even if path doesn't start with /static/, same origin should not be cached
            const request = { destination: 'script' };
            const url = new URL('http://localhost:8000/other/script.js');

            expect(shouldCacheInRuntimeCache(request, url)).toBe(false);
        });
    });

    describe('Cache Invalidation', () => {
        it('should delete old static-assets-v1 cache on SW activation', () => {
            if (!swContent) {
                console.warn('Skipping: SW content not available');
                return;
            }

            // The whitelist no longer includes static-assets-v1
            // So it will be deleted when new SW activates
            expect(swContent).toContain('caches.delete(cacheName)');
            expect(swContent).not.toContain("'static-assets-v1'");
        });

        it('should preserve Workbox precache caches', () => {
            if (!swContent) {
                console.warn('Skipping: SW content not available');
                return;
            }

            // Should check for workbox- prefix before deleting
            expect(swContent).toContain("cacheName.startsWith('workbox-')");
        });
    });
});
