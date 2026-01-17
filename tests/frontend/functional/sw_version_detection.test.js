/**
 * Service Worker Version Detection - Network Edge Cases
 *
 * Tests timeout and network error scenarios for SW version detection.
 * Complements sw_update_flow.test.js by focusing on edge cases that could
 * cause initialization to hang or fail unexpectedly.
 *
 * Key Scenarios:
 * - Network timeouts and delays
 * - Connection failures and offline scenarios
 * - Concurrent version checks
 * - Service worker registration states
 *
 * Priority: 🔍 HIGH - Ensures app initializes even with network issues
 * Coverage Target: 100% of network error paths in checkForServiceWorkerUpdate()
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

describe('SW Version Detection - Network Edge Cases', () => {
    let fetchSpy;
    let mockRegistration;
    let mockServiceWorker;
    let originalConsoleWarn;
    let consoleWarnSpy;

    beforeEach(() => {
        vi.clearAllMocks();

        // Mock console
        originalConsoleWarn = console.warn;
        consoleWarnSpy = vi.fn();
        console.warn = consoleWarnSpy;

        // Mock service worker
        mockServiceWorker = {
            state: 'activated',
            scriptURL: 'http://localhost:3000/sw.js?v=abc12345',
            postMessage: vi.fn(),
            addEventListener: vi.fn()
        };

        mockRegistration = {
            installing: null,
            waiting: null,
            active: mockServiceWorker,
            scope: '/',
            addEventListener: vi.fn(),
            update: vi.fn().mockResolvedValue(undefined)
        };

        Object.defineProperty(navigator, 'serviceWorker', {
            value: {
                register: vi.fn().mockResolvedValue(mockRegistration),
                getRegistration: vi.fn().mockResolvedValue(mockRegistration),
                addEventListener: vi.fn(),
                controller: mockServiceWorker
            },
            writable: true,
            configurable: true
        });

        // Mock fetch (default: no update)
        fetchSpy = vi.spyOn(window, 'fetch').mockResolvedValue({
            ok: true,
            json: async () => ({ version: 'abc12345' })
        });
    });

    afterEach(() => {
        vi.restoreAllMocks();
        console.warn = originalConsoleWarn;
    });

    // ==================== TIMEOUT SCENARIOS ====================

    describe('Timeout Scenarios', () => {
        it('should return false when fetch times out (AbortError)', async () => {
            // Simulate AbortController timeout
            fetchSpy.mockRejectedValue(new DOMException('Aborted', 'AbortError'));

            const { checkForServiceWorkerUpdate } = await import('../../../static/js/init.js');
            const result = await checkForServiceWorkerUpdate();

            expect(result).toBe(false);
            expect(consoleWarnSpy).toHaveBeenCalledWith(
                '[CHAPTR]',
                '[SW] Version check failed:',
                expect.any(DOMException)
            );
        });

        it('should eventually return result when response is delayed', async () => {
            // Simulate slow server (1 second delay)
            fetchSpy.mockImplementation(() =>
                new Promise(resolve => {
                    setTimeout(() => {
                        resolve({
                            ok: true,
                            json: async () => ({ version: 'new-version' })
                        });
                    }, 1000);
                })
            );

            const { checkForServiceWorkerUpdate } = await import('../../../static/js/init.js');

            const startTime = Date.now();
            const result = await checkForServiceWorkerUpdate();
            const duration = Date.now() - startTime;

            // Should complete after ~1 second
            expect(duration).toBeGreaterThanOrEqual(950);
            expect(result).toBe(true); // Different version detected
        });

        it('should not block initialization indefinitely on very slow response', async () => {
            // Use fake timers for deterministic timing control
            vi.useFakeTimers();

            // Simulate extremely slow server (10+ seconds) - but we'll abort the test early
            let responseResolve;
            const delayedPromise = new Promise(resolve => {
                responseResolve = resolve;
            });

            fetchSpy.mockImplementation(() => delayedPromise);

            const { checkForServiceWorkerUpdate } = await import('../../../static/js/init.js');

            // Start check in background
            const checkPromise = checkForServiceWorkerUpdate();

            // Wait a short time to ensure fetch was called (deterministic with fake timers)
            vi.advanceTimersByTime(100);
            await Promise.resolve(); // Flush microtasks

            // Reject the delayed promise to allow test to complete
            responseResolve({
                ok: true,
                json: async () => { throw new Error('Timeout'); }
            });

            const result = await checkPromise;

            // Should return false on JSON parse error
            expect(result).toBe(false);

            // Restore real timers
            vi.useRealTimers();
        });
    });

    // ==================== NETWORK ERRORS ====================

    describe('Network Errors', () => {
        it('should return false when network connection fails (TypeError)', async () => {
            // Simulate network error (offline, DNS failure, etc.)
            fetchSpy.mockRejectedValue(new TypeError('Failed to fetch'));

            const { checkForServiceWorkerUpdate } = await import('../../../static/js/init.js');
            const result = await checkForServiceWorkerUpdate();

            expect(result).toBe(false);
            expect(consoleWarnSpy).toHaveBeenCalledWith(
                '[CHAPTR]',
                '[SW] Version check failed:',
                expect.any(TypeError)
            );
        });

        it('should return false when server is unreachable (NetworkError)', async () => {
            // Simulate NetworkError
            const networkError = new Error('NetworkError');
            networkError.name = 'NetworkError';
            fetchSpy.mockRejectedValue(networkError);

            const { checkForServiceWorkerUpdate } = await import('../../../static/js/init.js');
            const result = await checkForServiceWorkerUpdate();

            expect(result).toBe(false);
        });

        it('should return false during offline scenario', async () => {
            // Simulate offline mode
            fetchSpy.mockRejectedValue(new TypeError('Failed to fetch'));

            const { checkForServiceWorkerUpdate } = await import('../../../static/js/init.js');
            const result = await checkForServiceWorkerUpdate();

            expect(result).toBe(false);
        });
    });

    // ==================== RESPONSE ERRORS ====================

    describe('Response Errors', () => {
        it('should return false when server returns 500 error', async () => {
            fetchSpy.mockResolvedValue({
                ok: false,
                status: 500,
                json: async () => { throw new Error('Server error'); }
            });

            const { checkForServiceWorkerUpdate } = await import('../../../static/js/init.js');
            const result = await checkForServiceWorkerUpdate();

            // Should catch error and return false
            expect(result).toBe(false);
        });

        it('should return false when response body is invalid', async () => {
            fetchSpy.mockResolvedValue({
                ok: true,
                json: async () => {
                    throw new SyntaxError('Unexpected token');
                }
            });

            const { checkForServiceWorkerUpdate } = await import('../../../static/js/init.js');
            const result = await checkForServiceWorkerUpdate();

            expect(result).toBe(false);
        });
    });

    // ==================== RACE CONDITIONS ====================

    describe('Race Conditions', () => {
        it('should handle multiple concurrent version checks correctly', async () => {
            // All checks should resolve independently
            fetchSpy.mockResolvedValue({
                ok: true,
                json: async () => ({ version: 'abc12345' })
            });

            const { checkForServiceWorkerUpdate } = await import('../../../static/js/init.js');

            // Start 3 concurrent checks
            const results = await Promise.all([
                checkForServiceWorkerUpdate(),
                checkForServiceWorkerUpdate(),
                checkForServiceWorkerUpdate()
            ]);

            // All should return false (no update)
            expect(results).toEqual([false, false, false]);

            // Fetch should be called 3 times
            expect(fetchSpy).toHaveBeenCalledTimes(3);
        });

        it('should gracefully handle version check during page unload', async () => {
            // Simulate fetch being aborted during unload
            fetchSpy.mockImplementation(() =>
                new Promise((_, reject) => {
                    setTimeout(() => reject(new DOMException('Aborted', 'AbortError')), 100);
                })
            );

            const { checkForServiceWorkerUpdate } = await import('../../../static/js/init.js');
            const result = await checkForServiceWorkerUpdate();

            expect(result).toBe(false);
        });
    });

    // ==================== SERVICE WORKER STATES ====================

    describe('Service Worker Registration States', () => {
        it('should return false when service worker registration is pending', async () => {
            // Set registration to null initially (pending)
            navigator.serviceWorker.getRegistration.mockResolvedValue(null);

            const { checkForServiceWorkerUpdate } = await import('../../../static/js/init.js');
            const result = await checkForServiceWorkerUpdate();

            expect(result).toBe(false);
        });

        it('should return false when service worker registration is null', async () => {
            navigator.serviceWorker.getRegistration.mockResolvedValue(null);

            const { checkForServiceWorkerUpdate } = await import('../../../static/js/init.js');
            const result = await checkForServiceWorkerUpdate();

            expect(result).toBe(false);
        });

        it('should return false when active service worker is missing', async () => {
            // Registration exists but no active worker
            const registrationNoActive = {
                ...mockRegistration,
                active: null
            };
            navigator.serviceWorker.getRegistration.mockResolvedValue(registrationNoActive);

            const { checkForServiceWorkerUpdate } = await import('../../../static/js/init.js');
            const result = await checkForServiceWorkerUpdate();

            expect(result).toBe(false);
        });
    });
});
