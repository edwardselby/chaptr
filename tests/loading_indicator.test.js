/**
 * Loading Indicator Tests
 *
 * Tests the loadingIndicator object that shows/hides the initialization loading screen.
 * The loading indicator displays different messages based on whether the page is loading
 * normally or updating due to a service worker change.
 *
 * Key functionality:
 * - show(): Creates and displays loader with appropriate message
 * - hide(): Fades out and removes loader with 300ms animation
 * - Message selection: "Loading application..." vs "Updating application..."
 * - SessionStorage resilience: Graceful handling when unavailable
 *
 * Priority: 💡 MEDIUM - Ensures proper UX feedback during initialization
 * Coverage Target: 100% of loadingIndicator.show() and hide() methods
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

describe('Loading Indicator - Show/Hide', () => {
    let originalSessionStorage;

    beforeEach(() => {
        // Store original sessionStorage
        originalSessionStorage = window.sessionStorage;

        // Clear sessionStorage and DOM
        try {
            sessionStorage.clear();
        } catch (e) {
            // Ignore if already mocked
        }

        // Clean up any existing loaders
        const existingLoader = document.getElementById('chaptr-init-loader');
        if (existingLoader) {
            existingLoader.remove();
        }

        vi.useFakeTimers();
    });

    afterEach(() => {
        vi.useRealTimers();
        vi.restoreAllMocks();

        // Restore original sessionStorage
        if (originalSessionStorage !== window.sessionStorage) {
            Object.defineProperty(window, 'sessionStorage', {
                value: originalSessionStorage,
                writable: true,
                configurable: true
            });
        }

        // Clean up DOM
        const loader = document.getElementById('chaptr-init-loader');
        if (loader) {
            loader.remove();
        }

        try {
            sessionStorage.clear();
        } catch (e) {
            // Ignore
        }
    });

    // ==================== SHOW METHOD ====================

    describe('show() method', () => {
        it('should create loader element with correct ID when none exists', async () => {
            const { loadingIndicator } = await import('../static/js/init.js');

            loadingIndicator.show();

            const loader = document.getElementById('chaptr-init-loader');
            expect(loader).toBeTruthy();
            expect(loader.id).toBe('chaptr-init-loader');
        });

        it('should not create duplicate loader when called multiple times', async () => {
            const { loadingIndicator } = await import('../static/js/init.js');

            loadingIndicator.show();
            loadingIndicator.show();
            loadingIndicator.show();

            const loaders = document.querySelectorAll('#chaptr-init-loader');
            expect(loaders.length).toBe(1);
        });

        it('should display "Loading application..." by default', async () => {
            const { loadingIndicator } = await import('../static/js/init.js');

            loadingIndicator.show();

            const loader = document.getElementById('chaptr-init-loader');
            expect(loader?.textContent).toContain('Loading application...');
        });
    });

    // ==================== HIDE METHOD ====================

    describe('hide() method', () => {
        it('should fade out loader with opacity transition', async () => {
            const { loadingIndicator } = await import('../static/js/init.js');

            // Show loader first
            loadingIndicator.show();
            const loader = document.getElementById('chaptr-init-loader');
            expect(loader).toBeTruthy();

            // Hide loader
            loadingIndicator.hide();

            // Check opacity set to 0
            expect(loader?.style.opacity).toBe('0');
            // Check transition applied
            expect(loader?.style.transition).toContain('opacity');
        });

        it('should remove loader from DOM after 300ms delay', async () => {
            const { loadingIndicator } = await import('../static/js/init.js');

            // Show loader first
            loadingIndicator.show();
            let loader = document.getElementById('chaptr-init-loader');
            expect(loader).toBeTruthy();

            // Hide loader
            loadingIndicator.hide();

            // Loader should still exist immediately
            loader = document.getElementById('chaptr-init-loader');
            expect(loader).toBeTruthy();

            // Fast-forward 300ms
            vi.advanceTimersByTime(300);

            // Loader should now be removed
            loader = document.getElementById('chaptr-init-loader');
            expect(loader).toBeNull();
        });

        it('should do nothing when no loader exists', async () => {
            const { loadingIndicator } = await import('../static/js/init.js');

            // Call hide without showing first
            expect(() => loadingIndicator.hide()).not.toThrow();

            // No loader should exist
            const loader = document.getElementById('chaptr-init-loader');
            expect(loader).toBeNull();
        });
    });

    // ==================== SHOW/HIDE SEQUENCE ====================

    describe('show/hide sequence', () => {
        it('should handle complete show → hide cycle', async () => {
            const { loadingIndicator } = await import('../static/js/init.js');

            // Show loader
            loadingIndicator.show();
            let loader = document.getElementById('chaptr-init-loader');
            expect(loader).toBeTruthy();
            expect(loader?.style.opacity).not.toBe('0');

            // Hide loader
            loadingIndicator.hide();
            expect(loader?.style.opacity).toBe('0');

            // Wait for removal
            vi.advanceTimersByTime(300);
            loader = document.getElementById('chaptr-init-loader');
            expect(loader).toBeNull();
        });

        it('should allow re-showing loader after hiding', async () => {
            const { loadingIndicator } = await import('../static/js/init.js');

            // First cycle
            loadingIndicator.show();
            loadingIndicator.hide();
            vi.advanceTimersByTime(300);
            expect(document.getElementById('chaptr-init-loader')).toBeNull();

            // Second cycle
            loadingIndicator.show();
            const loader = document.getElementById('chaptr-init-loader');
            expect(loader).toBeTruthy();
            expect(loader?.textContent).toContain('Loading application...');
        });
    });
});
