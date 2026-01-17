/**
 * Service Worker Updating UX Tests
 *
 * Tests the user experience feedback system for service worker updates:
 * - sessionStorage flag detection and display
 * - "Loading application..." vs "Updating application..." messages
 * - Flag lifecycle (set before reload, read after reload, cleared after display)
 * - Graceful fallback when sessionStorage unavailable
 * - Message priority when multiple show() calls occur
 *
 * Priority: 🚨 CRITICAL - Ensures users understand when updates are happening
 * Coverage Target: 100% of loadingIndicator.show() UX logic
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { loadingIndicator } from '../../../static/js/init.js';

describe('Service Worker Updating UX', () => {
    let originalSessionStorage;

    beforeEach(() => {
        // Store original sessionStorage BEFORE any operations
        originalSessionStorage = window.sessionStorage;

        // Clear sessionStorage before each test (wrap in try/catch for mocked scenarios)
        try {
            sessionStorage.clear();
        } catch (e) {
            // Ignore if sessionStorage is mocked to throw
        }

        // Clear any existing loaders
        const existingLoader = document.getElementById('chaptr-init-loader');
        if (existingLoader) {
            existingLoader.remove();
        }
    });

    afterEach(() => {
        // Clean up DOM
        const loader = document.getElementById('chaptr-init-loader');
        if (loader) {
            loader.remove();
        }

        // Restore original sessionStorage BEFORE clearing
        if (originalSessionStorage !== window.sessionStorage) {
            Object.defineProperty(window, 'sessionStorage', {
                value: originalSessionStorage,
                writable: true,
                configurable: true
            });
        }

        // Clear sessionStorage (after restoration, wrapped in try/catch)
        try {
            sessionStorage.clear();
        } catch (e) {
            // Ignore if sessionStorage is mocked to throw
        }
    });

    // ==================== FLAG DETECTION AND MESSAGES ====================

    describe('Flag Detection and Message Display', () => {
        it('should display "Updating application..." when flag is set', () => {
            // Set the update flag (simulates SW update flow)
            sessionStorage.setItem('chaptr-sw-updating', 'true');

            loadingIndicator.show();

            const loader = document.getElementById('chaptr-init-loader');
            expect(loader).toBeTruthy();
            expect(loader?.textContent).toContain('Updating application...');
            expect(loader?.textContent).not.toContain('Loading application...');
        });

        it('should display "Loading application..." when flag is NOT set', () => {
            // No flag set (normal load)
            loadingIndicator.show();

            const loader = document.getElementById('chaptr-init-loader');
            expect(loader).toBeTruthy();
            expect(loader?.textContent).toContain('Loading application...');
            expect(loader?.textContent).not.toContain('Updating application...');
        });

        it('should clear flag immediately after reading it', () => {
            sessionStorage.setItem('chaptr-sw-updating', 'true');

            // Verify flag is set before show()
            expect(sessionStorage.getItem('chaptr-sw-updating')).toBe('true');

            loadingIndicator.show();

            // Flag should be cleared immediately after reading
            expect(sessionStorage.getItem('chaptr-sw-updating')).toBeNull();
        });

        it('should preserve flag value during reload (flag persists across page transition)', () => {
            // Simulate SW update flow:
            // 1. controllerchange handler sets flag
            sessionStorage.setItem('chaptr-sw-updating', 'true');

            // 2. Page reloads (simulated by flag still being present)
            expect(sessionStorage.getItem('chaptr-sw-updating')).toBe('true');

            // 3. After reload, init.js reads flag
            loadingIndicator.show();

            // 4. Flag should have been cleared after display
            expect(sessionStorage.getItem('chaptr-sw-updating')).toBeNull();

            // Verify correct message was shown
            const loader = document.getElementById('chaptr-init-loader');
            expect(loader?.textContent).toContain('Updating application...');
        });

        it('should not show update message on subsequent loads (flag removed before next normal load)', () => {
            // First load: SW update scenario
            sessionStorage.setItem('chaptr-sw-updating', 'true');
            loadingIndicator.show();

            // Verify update message shown and flag cleared
            let loader = document.getElementById('chaptr-init-loader');
            expect(loader?.textContent).toContain('Updating application...');
            expect(sessionStorage.getItem('chaptr-sw-updating')).toBeNull();

            // Clean up
            loader?.remove();

            // Second load: Normal scenario (no flag set)
            loadingIndicator.show();

            loader = document.getElementById('chaptr-init-loader');
            expect(loader?.textContent).toContain('Loading application...');
            expect(loader?.textContent).not.toContain('Updating application...');
        });
    });

    // ==================== SESSIONSTORAGE FALLBACK ====================

    describe('sessionStorage Disabled Fallback', () => {
        it('should gracefully fallback to "Loading application..." when sessionStorage disabled', () => {
            // Mock sessionStorage as disabled (SecurityError in private browsing, etc.)
            Object.defineProperty(window, 'sessionStorage', {
                value: {
                    getItem: () => {
                        throw new Error('SecurityError: sessionStorage is disabled');
                    },
                    setItem: () => {
                        throw new Error('SecurityError: sessionStorage is disabled');
                    },
                    removeItem: () => {
                        throw new Error('SecurityError: sessionStorage is disabled');
                    },
                    clear: () => {
                        throw new Error('SecurityError: sessionStorage is disabled');
                    }
                },
                writable: true,
                configurable: true
            });

            // Should not throw error
            expect(() => loadingIndicator.show()).not.toThrow();

            // Should show default "Loading application..." message
            const loader = document.getElementById('chaptr-init-loader');
            expect(loader).toBeTruthy();
            expect(loader?.textContent).toContain('Loading application...');
        });

        it('should handle sessionStorage getItem returning null gracefully', () => {
            // Mock sessionStorage that returns null
            Object.defineProperty(window, 'sessionStorage', {
                value: {
                    getItem: vi.fn(() => null),
                    setItem: vi.fn(),
                    removeItem: vi.fn(),
                    clear: vi.fn()
                },
                writable: true,
                configurable: true
            });

            loadingIndicator.show();

            const loader = document.getElementById('chaptr-init-loader');
            expect(loader?.textContent).toContain('Loading application...');
        });
    });

    // ==================== TIMING AND EDGE CASES ====================

    describe('Timing and Edge Cases', () => {
        it('should handle multiple show() calls with last message taking priority', () => {
            // First call: normal loading
            loadingIndicator.show();
            let loader = document.getElementById('chaptr-init-loader');
            expect(loader?.textContent).toContain('Loading application...');

            // Remove first loader
            loader?.remove();

            // Second call: update scenario
            sessionStorage.setItem('chaptr-sw-updating', 'true');
            loadingIndicator.show();
            loader = document.getElementById('chaptr-init-loader');
            expect(loader?.textContent).toContain('Updating application...');
        });

        it('should create new loader with correct message when called after previous loader removed', () => {
            // First call
            sessionStorage.setItem('chaptr-sw-updating', 'true');
            loadingIndicator.show();

            let loader = document.getElementById('chaptr-init-loader');
            expect(loader?.textContent).toContain('Updating application...');

            // Remove loader
            loader?.remove();
            expect(document.getElementById('chaptr-init-loader')).toBeNull();

            // Second call (flag already cleared from first call)
            loadingIndicator.show();
            loader = document.getElementById('chaptr-init-loader');
            expect(loader?.textContent).toContain('Loading application...');
        });

        it('should maintain correct state when flag is manually set between calls', () => {
            // Call 1: Normal load
            loadingIndicator.show();
            let loader = document.getElementById('chaptr-init-loader');
            expect(loader?.textContent).toContain('Loading application...');
            loader?.remove();

            // Manually set flag (simulating async SW update detection)
            sessionStorage.setItem('chaptr-sw-updating', 'true');

            // Call 2: Should detect flag
            loadingIndicator.show();
            loader = document.getElementById('chaptr-init-loader');
            expect(loader?.textContent).toContain('Updating application...');
            expect(sessionStorage.getItem('chaptr-sw-updating')).toBeNull();
        });

        it('should handle empty string flag value as falsy', () => {
            sessionStorage.setItem('chaptr-sw-updating', '');

            loadingIndicator.show();

            const loader = document.getElementById('chaptr-init-loader');
            // Empty string should be treated as falsy, show normal message
            expect(loader?.textContent).toContain('Loading application...');
        });

        it('should only respond to exact "true" string value', () => {
            // Test various truthy-looking values
            const values = ['1', 'yes', 'TRUE', 'True', 'enabled'];

            values.forEach(value => {
                sessionStorage.clear();
                const existingLoader = document.getElementById('chaptr-init-loader');
                if (existingLoader) {
                    existingLoader.remove();
                }

                sessionStorage.setItem('chaptr-sw-updating', value);
                loadingIndicator.show();

                const loader = document.getElementById('chaptr-init-loader');
                // Only exact "true" should trigger update message
                expect(loader?.textContent).toContain('Loading application...');

                loader?.remove();
            });

            // Now test exact "true" value
            sessionStorage.clear();
            sessionStorage.setItem('chaptr-sw-updating', 'true');
            loadingIndicator.show();

            const loader = document.getElementById('chaptr-init-loader');
            expect(loader?.textContent).toContain('Updating application...');
        });
    });

    // ==================== DOM STRUCTURE ====================

    describe('DOM Structure and Styling', () => {
        it('should create loader with correct ID and structure', () => {
            loadingIndicator.show();

            const loader = document.getElementById('chaptr-init-loader');
            expect(loader).toBeTruthy();
            expect(loader?.id).toBe('chaptr-init-loader');
            expect(loader?.style.position).toBe('fixed');
            expect(loader?.style.zIndex).toBe('999999');
        });

        it('should include progress bar animation in both loading modes', () => {
            // Test normal loading
            loadingIndicator.show();
            let loader = document.getElementById('chaptr-init-loader');
            expect(loader?.innerHTML).toContain('animation: progress');

            loader?.remove();

            // Test update mode
            sessionStorage.setItem('chaptr-sw-updating', 'true');
            loadingIndicator.show();
            loader = document.getElementById('chaptr-init-loader');
            expect(loader?.innerHTML).toContain('animation: progress');
        });

        it('should use CHAPTR brand colors (green #4af626 on black)', () => {
            loadingIndicator.show();

            const loader = document.getElementById('chaptr-init-loader');
            expect(loader?.innerHTML).toContain('#4af626'); // CHAPTR green (in content)
            // Browser converts #0a0a0a to rgb(10, 10, 10)
            expect(loader?.style.background).toContain('rgb(10, 10, 10)'); // Background black
        });

        it('should be visible on top of all content (z-index 999999)', () => {
            loadingIndicator.show();

            const loader = document.getElementById('chaptr-init-loader');
            expect(loader?.style.zIndex).toBe('999999');
            expect(loader?.style.position).toBe('fixed');
            expect(loader?.style.top).toBe('0px');
            expect(loader?.style.left).toBe('0px');
            expect(loader?.style.right).toBe('0px');
            expect(loader?.style.bottom).toBe('0px');
        });
    });
});
