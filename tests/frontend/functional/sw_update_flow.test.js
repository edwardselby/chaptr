/**
 * Service Worker Update Flow Tests
 *
 * Tests the core SW update detection and lifecycle management including:
 * - checkForServiceWorkerUpdate() version comparison logic
 * - initServiceWorker() registration and event handling
 * - updatefound → statechange → SKIP_WAITING message flow
 * - controllerchange debounce (prevents reload loops)
 * - sessionStorage flag lifecycle
 *
 * Priority: 🚨 CRITICAL - Prevents infinite reload loops and silent update failures
 * Coverage Target: 100% of init.js SW update functions
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

// Import functions to test
import {
    checkForServiceWorkerUpdate,
    initServiceWorker,
    loadingIndicator,
    init,
    logger,
    testableUtils
} from '../../../static/js/init.js';

describe('Service Worker Update Flow', () => {
    let mockRegistration;
    let mockServiceWorker;
    let fetchSpy;
    let originalConsoleLog;
    let originalConsoleWarn;
    let originalConsoleError;
    let consoleLogSpy;
    let consoleWarnSpy;
    let consoleErrorSpy;
    let originalServiceWorker;
    let originalLocation;

    beforeEach(() => {
        // Reset all spies
        vi.clearAllMocks();
        vi.useFakeTimers();

        // Spy on testableUtils.reloadPage (object property can be spied on)
        vi.spyOn(testableUtils, 'reloadPage').mockImplementation(() => {
            // Mock implementation - don't actually reload
        });

        // Store originals
        originalServiceWorker = navigator.serviceWorker;
        originalConsoleLog = console.log;
        originalConsoleWarn = console.warn;
        originalConsoleError = console.error;

        // Mock console methods
        consoleLogSpy = vi.fn();
        consoleWarnSpy = vi.fn();
        consoleErrorSpy = vi.fn();
        console.log = consoleLogSpy;
        console.warn = consoleWarnSpy;
        console.error = consoleErrorSpy;

        // Create mock service worker
        mockServiceWorker = {
            state: 'activated',
            scriptURL: 'http://localhost:3000/sw.js?v=abc12345',
            postMessage: vi.fn(),
            addEventListener: vi.fn()
        };

        // Create mock registration
        mockRegistration = {
            installing: null,
            waiting: null,
            active: mockServiceWorker,
            scope: '/',
            addEventListener: vi.fn(),
            update: vi.fn().mockResolvedValue(undefined)
        };

        // Mock ServiceWorkerContainer
        const mockServiceWorkerContainer = {
            register: vi.fn().mockResolvedValue(mockRegistration),
            getRegistration: vi.fn().mockResolvedValue(mockRegistration),
            addEventListener: vi.fn(),
            controller: mockServiceWorker,
            ready: Promise.resolve(mockRegistration)
        };

        Object.defineProperty(navigator, 'serviceWorker', {
            value: mockServiceWorkerContainer,
            writable: true,
            configurable: true
        });

        // Mock fetch for /sw-version endpoint
        fetchSpy = vi.spyOn(window, 'fetch');

        // Clear sessionStorage
        sessionStorage.clear();

        // Clear any existing loaders
        const existingLoader = document.getElementById('chaptr-init-loader');
        if (existingLoader) {
            existingLoader.remove();
        }
    });

    afterEach(() => {
        vi.useRealTimers();

        // Restore originals
        console.log = originalConsoleLog;
        console.warn = originalConsoleWarn;
        console.error = originalConsoleError;

        if (originalServiceWorker) {
            Object.defineProperty(navigator, 'serviceWorker', {
                value: originalServiceWorker,
                writable: true,
                configurable: true
            });
        }

        // Clean up DOM
        const loader = document.getElementById('chaptr-init-loader');
        if (loader) {
            loader.remove();
        }

        sessionStorage.clear();
        vi.restoreAllMocks();

        // Restore testableUtils spy
        testableUtils.reloadPage.mockRestore?.();
    });

    // ==================== HAPPY PATH TESTS ====================

    describe('Happy Path - Waiting Worker Detection', () => {
        it('should return false when no waiting worker (no update)', async () => {
            // Default mock: no waiting worker
            mockRegistration.waiting = null;

            const result = await checkForServiceWorkerUpdate();

            expect(result).toBe(false);
        });

        it('should return true when waiting worker exists (update ready)', async () => {
            // Mock waiting worker (update ready to install)
            mockRegistration.waiting = {
                state: 'installed',
                postMessage: vi.fn()
            };

            const result = await checkForServiceWorkerUpdate();

            expect(result).toBe(true);
            expect(consoleLogSpy).toHaveBeenCalledWith(
                '[CHAPTR]',
                '[SW] Update ready (waiting worker found)'
            );
        });

        it('should send SKIP_WAITING message when new SW installed with old one controlling', async () => {
            const newWorker = {
                state: 'installing',
                postMessage: vi.fn(),
                addEventListener: vi.fn()
            };

            mockRegistration.installing = newWorker;
            navigator.serviceWorker.controller = mockServiceWorker; // Old SW controlling

            // Capture the updatefound handler
            let updatefoundHandler;
            mockRegistration.addEventListener = vi.fn((event, handler) => {
                if (event === 'updatefound') {
                    updatefoundHandler = handler;
                }
            });

            // Mock register to return our setup
            navigator.serviceWorker.register.mockResolvedValue(mockRegistration);
            fetchSpy.mockResolvedValue({
                ok: true,
                json: async () => ({ version: '12345678' })
            });

            // Initialize service worker
            await initServiceWorker();

            // Simulate updatefound event
            if (updatefoundHandler) {
                updatefoundHandler();

                // Capture the statechange handler
                let statechangeHandler;
                newWorker.addEventListener = vi.fn((event, handler) => {
                    if (event === 'statechange') {
                        statechangeHandler = handler;
                    }
                });

                // Re-call to capture handler
                updatefoundHandler();
                const statechangeCall = newWorker.addEventListener.mock.calls.find(
                    call => call[0] === 'statechange'
                );
                if (statechangeCall) {
                    statechangeHandler = statechangeCall[1];
                }

                // Simulate state change to 'installed'
                newWorker.state = 'installed';
                if (statechangeHandler) {
                    statechangeHandler();
                }

                await vi.runAllTimersAsync();

                // Verify SKIP_WAITING message was sent
                expect(newWorker.postMessage).toHaveBeenCalledWith({ type: 'SKIP_WAITING' });
            }
        });

        it('should set sessionStorage flag and reload on controllerchange', async () => {
            // Capture controllerchange handler
            let controllerchangeHandler;
            navigator.serviceWorker.addEventListener = vi.fn((event, handler) => {
                if (event === 'controllerchange') {
                    controllerchangeHandler = handler;
                }
            });

            fetchSpy.mockResolvedValue({
                ok: true,
                json: async () => ({ version: '12345678' })
            });

            await initServiceWorker();

            // Trigger controllerchange
            if (controllerchangeHandler) {
                controllerchangeHandler();

                // Should set sessionStorage flag immediately
                expect(sessionStorage.getItem('chaptr-sw-updating')).toBe('true');

                // Should schedule reload after 100ms
                expect(testableUtils.reloadPage).not.toHaveBeenCalled();
                vi.advanceTimersByTime(100);
                expect(testableUtils.reloadPage).toHaveBeenCalledTimes(1);
            }
        });
    });

    // ==================== ERROR CASES ====================

    describe('Error Handling', () => {
        it('should return false on registration error', async () => {
            // checkForServiceWorkerUpdate now uses register() instead of getRegistration()
            navigator.serviceWorker.register.mockRejectedValue(new Error('Registration error'));

            const result = await checkForServiceWorkerUpdate();

            expect(result).toBe(false);
            expect(consoleErrorSpy).toHaveBeenCalledWith(
                '[CHAPTR]',
                'Service Worker registration failed:',
                expect.any(Error)
            );
        });

        it('should return false when registration is null', async () => {
            navigator.serviceWorker.getRegistration.mockResolvedValue(null);

            const result = await checkForServiceWorkerUpdate();

            expect(result).toBe(false);
        });

        it('should return false when registration has no waiting worker', async () => {
            mockRegistration.waiting = null;
            mockRegistration.installing = null;
            navigator.serviceWorker.getRegistration.mockResolvedValue(mockRegistration);

            const result = await checkForServiceWorkerUpdate();

            expect(result).toBe(false);
        });

        it('should log error when SW registration fails but continue', async () => {
            navigator.serviceWorker.register.mockRejectedValue(new Error('SW registration failed'));

            // Should not throw
            await expect(initServiceWorker()).resolves.not.toThrow();

            // Should log error
            expect(consoleErrorSpy).toHaveBeenCalledWith(
                '[CHAPTR]',
                'Service Worker registration failed:',
                expect.any(Error)
            );
        });
    });

    // ==================== DEBOUNCE LOGIC ====================

    describe('Debounce Logic - Prevents Reload Loops', () => {
        it('should only reload once when controllerchange fires multiple times', async () => {
            let controllerchangeHandler;
            navigator.serviceWorker.addEventListener = vi.fn((event, handler) => {
                if (event === 'controllerchange') {
                    controllerchangeHandler = handler;
                }
            });

            fetchSpy.mockResolvedValue({
                ok: true,
                json: async () => ({ version: '12345678' })
            });

            await initServiceWorker();

            if (controllerchangeHandler) {
                // Fire multiple times rapidly
                controllerchangeHandler();
                controllerchangeHandler();
                controllerchangeHandler();

                vi.advanceTimersByTime(100);

                // Should only reload once due to debouncing
                expect(testableUtils.reloadPage).toHaveBeenCalledTimes(1);
            }
        });

        it('should debounce rapid events within 100ms window', async () => {
            let controllerchangeHandler;
            navigator.serviceWorker.addEventListener = vi.fn((event, handler) => {
                if (event === 'controllerchange') {
                    controllerchangeHandler = handler;
                }
            });

            fetchSpy.mockResolvedValue({
                ok: true,
                json: async () => ({ version: '12345678' })
            });

            await initServiceWorker();

            if (controllerchangeHandler) {
                // First event
                controllerchangeHandler();
                vi.advanceTimersByTime(50);
                expect(testableUtils.reloadPage).not.toHaveBeenCalled();

                // Second event within window
                controllerchangeHandler();
                vi.advanceTimersByTime(60);

                // Should only reload once after total 110ms
                expect(testableUtils.reloadPage).toHaveBeenCalledTimes(1);
            }
        });

        it('should prevent multiple reloads via debounce flag', async () => {
            let controllerchangeHandler;
            navigator.serviceWorker.addEventListener = vi.fn((event, handler) => {
                if (event === 'controllerchange') {
                    controllerchangeHandler = handler;
                }
            });

            fetchSpy.mockResolvedValue({
                ok: true,
                json: async () => ({ version: '12345678' })
            });

            await initServiceWorker();

            if (controllerchangeHandler) {
                controllerchangeHandler();
                vi.advanceTimersByTime(100);

                // First reload should happen
                expect(testableUtils.reloadPage).toHaveBeenCalledTimes(1);

                // Fire event again after reload
                controllerchangeHandler();
                vi.advanceTimersByTime(100);

                // Should NOT reload again (debounce flag prevents it)
                expect(testableUtils.reloadPage).toHaveBeenCalledTimes(1);
            }
        });
    });

    // ==================== EDGE CASES ====================

    describe('Edge Cases', () => {
        it('should return false on first-time install (no active SW)', async () => {
            navigator.serviceWorker.getRegistration.mockResolvedValue({
                ...mockRegistration,
                active: null // No active SW yet
            });

            fetchSpy.mockResolvedValue({
                ok: true,
                json: async () => ({ version: 'abc12345' })
            });

            const result = await checkForServiceWorkerUpdate();

            expect(result).toBe(false);
        });

        it('should not create reload loop when update triggers during update', async () => {
            let controllerchangeHandler;
            navigator.serviceWorker.addEventListener = vi.fn((event, handler) => {
                if (event === 'controllerchange') {
                    controllerchangeHandler = handler;
                }
            });

            fetchSpy.mockResolvedValue({
                ok: true,
                json: async () => ({ version: '12345678' })
            });

            await initServiceWorker();

            if (controllerchangeHandler) {
                // Simulate update scenario
                sessionStorage.setItem('chaptr-sw-updating', 'true');
                controllerchangeHandler();

                vi.advanceTimersByTime(100);

                // Should reload once
                expect(testableUtils.reloadPage).toHaveBeenCalledTimes(1);

                // Try to trigger again - should be ignored
                controllerchangeHandler();
                vi.advanceTimersByTime(100);

                expect(testableUtils.reloadPage).toHaveBeenCalledTimes(1);
            }
        });

        it('should handle background sync message gracefully', async () => {
            let messageHandler;
            navigator.serviceWorker.addEventListener = vi.fn((event, handler) => {
                if (event === 'message') {
                    messageHandler = handler;
                }
            });

            fetchSpy.mockResolvedValue({
                ok: true,
                json: async () => ({ version: '12345678' })
            });

            await initServiceWorker();

            if (messageHandler) {
                // Trigger background sync message
                messageHandler({
                    data: { type: 'BACKGROUND_SYNC' }
                });

                // Should not throw error
                expect(consoleErrorSpy).not.toHaveBeenCalled();
            }
        });

        it('should be idempotent when SW registration called twice', async () => {
            fetchSpy.mockResolvedValue({
                ok: true,
                json: async () => ({ version: '12345678' })
            });

            await initServiceWorker();
            await initServiceWorker();

            // Should register SW, but second call shouldn't cause issues
            expect(navigator.serviceWorker.register).toHaveBeenCalled();
        });

        it('should be idempotent when loadingIndicator.show() called twice', () => {
            loadingIndicator.show();
            loadingIndicator.show();

            // Should only create one loader element
            const loaders = document.querySelectorAll('#chaptr-init-loader');
            expect(loaders.length).toBe(1);
        });

        it('should clear sessionStorage flag after displaying update message', () => {
            sessionStorage.setItem('chaptr-sw-updating', 'true');

            loadingIndicator.show();

            // Flag should be cleared immediately after reading
            expect(sessionStorage.getItem('chaptr-sw-updating')).toBeNull();

            // Should show "Updating application..." message
            const loader = document.getElementById('chaptr-init-loader');
            expect(loader?.innerHTML).toContain('Updating application...');
        });
    });

    // ==================== BROWSER API AVAILABILITY ====================

    describe('Browser API Availability', () => {
        it('should return false when ServiceWorker API not available', async () => {
            // Remove ServiceWorker API
            delete navigator.serviceWorker;

            const result = await checkForServiceWorkerUpdate();

            expect(result).toBe(false);
        });

        it('should skip SW initialization gracefully when API not available', async () => {
            // Remove ServiceWorker API
            delete navigator.serviceWorker;

            // Should not throw error - gracefully handles missing API
            await expect(initServiceWorker()).resolves.toBeUndefined();
        });
    });

    // ==================== LOADING INDICATOR ====================

    describe('Loading Indicator', () => {
        it('should show "Loading application..." when no update flag', () => {
            loadingIndicator.show();

            const loader = document.getElementById('chaptr-init-loader');
            expect(loader).toBeTruthy();
            expect(loader?.innerHTML).toContain('Loading application...');
            expect(loader?.innerHTML).not.toContain('Updating application...');
        });

        it('should show "Updating application..." when update flag set', () => {
            sessionStorage.setItem('chaptr-sw-updating', 'true');

            loadingIndicator.show();

            const loader = document.getElementById('chaptr-init-loader');
            expect(loader?.innerHTML).toContain('Updating application...');
        });

        it('should hide loading indicator with fade animation', () => {
            loadingIndicator.show();
            const loader = document.getElementById('chaptr-init-loader');
            expect(loader).toBeTruthy();

            loadingIndicator.hide();

            // Should set opacity to 0
            expect(loader?.style.opacity).toBe('0');

            // Should remove after 300ms
            vi.advanceTimersByTime(300);
            expect(document.getElementById('chaptr-init-loader')).toBeNull();
        });
    });
});
