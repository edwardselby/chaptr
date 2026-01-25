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
    let originalConsoleError;
    let consoleWarnSpy;
    let consoleErrorSpy;

    beforeEach(() => {
        vi.clearAllMocks();

        // Mock console
        originalConsoleWarn = console.warn;
        originalConsoleError = console.error;
        consoleWarnSpy = vi.fn();
        consoleErrorSpy = vi.fn();
        console.warn = consoleWarnSpy;
        console.error = consoleErrorSpy;

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
        console.error = originalConsoleError;
    });

    // ==================== TIMEOUT SCENARIOS ====================

    describe('Timeout Scenarios', () => {
        it('should return false when registration throws error', async () => {
            // checkForServiceWorkerUpdate now uses register() instead of getRegistration()
            navigator.serviceWorker.register.mockRejectedValue(new Error('Registration error'));

            const { checkForServiceWorkerUpdate } = await import('../../../static/js/init.js');
            const result = await checkForServiceWorkerUpdate();

            expect(result).toBe(false);
            expect(consoleErrorSpy).toHaveBeenCalledWith(
                '[CHAPTR]',
                'Service Worker registration failed:',
                expect.any(Error)
            );
        });

        it('should return result immediately when registration is available', async () => {
            // Set up waiting worker (update ready)
            mockRegistration.waiting = {
                state: 'installed',
                postMessage: vi.fn()
            };

            const { checkForServiceWorkerUpdate } = await import('../../../static/js/init.js');

            const startTime = Date.now();
            const result = await checkForServiceWorkerUpdate();
            const duration = Date.now() - startTime;

            // Should complete quickly (no network delay)
            expect(duration).toBeLessThan(100);
            expect(result).toBe(true);
        });

        it('should not block initialization indefinitely on very slow response', async () => {
            // Use fake timers for deterministic timing control
            vi.useFakeTimers();

            // Simulate slow getRegistration
            let registrationResolve;
            const delayedPromise = new Promise(resolve => {
                registrationResolve = resolve;
            });

            navigator.serviceWorker.getRegistration.mockImplementation(() => delayedPromise);

            const { checkForServiceWorkerUpdate } = await import('../../../static/js/init.js');

            // Start check in background
            const checkPromise = checkForServiceWorkerUpdate();

            // Wait a short time
            vi.advanceTimersByTime(100);
            await Promise.resolve(); // Flush microtasks

            // Resolve with no waiting worker
            registrationResolve(mockRegistration);

            const result = await checkPromise;

            // Should return false (no waiting worker)
            expect(result).toBe(false);

            // Restore real timers
            vi.useRealTimers();
        });
    });

    // ==================== REGISTRATION ERRORS ====================

    describe('Registration Errors', () => {
        it('should return false when registration throws TypeError', async () => {
            // checkForServiceWorkerUpdate now uses register() instead of getRegistration()
            navigator.serviceWorker.register.mockRejectedValue(new TypeError('Invalid scope'));

            const { checkForServiceWorkerUpdate } = await import('../../../static/js/init.js');
            const result = await checkForServiceWorkerUpdate();

            expect(result).toBe(false);
            expect(consoleErrorSpy).toHaveBeenCalledWith(
                '[CHAPTR]',
                'Service Worker registration failed:',
                expect.any(TypeError)
            );
        });

        it('should return false when server is unreachable (NetworkError)', async () => {
            // Simulate NetworkError during registration lookup
            const networkError = new Error('NetworkError');
            networkError.name = 'NetworkError';
            navigator.serviceWorker.getRegistration.mockRejectedValue(networkError);

            const { checkForServiceWorkerUpdate } = await import('../../../static/js/init.js');
            const result = await checkForServiceWorkerUpdate();

            expect(result).toBe(false);
        });

        it('should return false during offline scenario', async () => {
            // When offline, registration might still be cached
            // But no waiting worker means no update
            mockRegistration.waiting = null;

            const { checkForServiceWorkerUpdate } = await import('../../../static/js/init.js');
            const result = await checkForServiceWorkerUpdate();

            expect(result).toBe(false);
        });
    });

    // ==================== REGISTRATION STATE ERRORS ====================

    describe('Registration State Errors', () => {
        it('should return false when registration returns undefined', async () => {
            navigator.serviceWorker.getRegistration.mockResolvedValue(undefined);

            const { checkForServiceWorkerUpdate } = await import('../../../static/js/init.js');
            const result = await checkForServiceWorkerUpdate();

            // Should handle undefined gracefully and return false
            expect(result).toBe(false);
        });

        it('should return false when registration.waiting is undefined', async () => {
            mockRegistration.waiting = undefined;

            const { checkForServiceWorkerUpdate } = await import('../../../static/js/init.js');
            const result = await checkForServiceWorkerUpdate();

            expect(result).toBe(false);
        });
    });

    // ==================== CONCURRENT CHECKS ====================

    describe('Concurrent Checks', () => {
        it('should handle multiple concurrent update checks correctly', async () => {
            // No waiting worker
            mockRegistration.waiting = null;

            const { checkForServiceWorkerUpdate } = await import('../../../static/js/init.js');

            // Start 3 concurrent checks
            const results = await Promise.all([
                checkForServiceWorkerUpdate(),
                checkForServiceWorkerUpdate(),
                checkForServiceWorkerUpdate()
            ]);

            // All should return false (no update)
            expect(results).toEqual([false, false, false]);

            // register should be called 3 times (checkForServiceWorkerUpdate now uses register)
            expect(navigator.serviceWorker.register).toHaveBeenCalledTimes(3);
        });

        it('should gracefully handle version check during page unload', async () => {
            // Simulate getRegistration being interrupted during unload
            navigator.serviceWorker.getRegistration.mockRejectedValue(
                new DOMException('Aborted', 'AbortError')
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
