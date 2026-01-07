/**
 * CHAPTR - Application Initialization
 *
 * Production-ready initialization system that coordinates:
 * 1. App module loading
 * 2. Global component registration
 * 3. Alpine.js framework loading (with retry)
 * 4. Service worker registration
 *
 * Features:
 * - Visual loading indicator
 * - Performance monitoring
 * - Automatic retry on CDN failure
 * - Environment-aware logging
 * - Graceful error handling
 */

import { settingsDropdown, modalDropdown } from './dropdown-factories.js';

// Environment detection
const isDevelopment = location.hostname === 'localhost' || location.hostname === '127.0.0.1';

// Performance tracking
const perf = {
    start: performance.now(),
    marks: {}
};

/**
 * Environment-aware logging
 */
const logger = {
    info: (...args) => {
        if (isDevelopment) {
            console.log('[CHAPTR]', ...args);
        }
    },
    warn: (...args) => console.warn('[CHAPTR]', ...args),
    error: (...args) => console.error('[CHAPTR]', ...args),
    perf: (label) => {
        perf.marks[label] = performance.now() - perf.start;
        if (isDevelopment) {
            console.log(`[CHAPTR] ⏱️  ${label}: ${perf.marks[label].toFixed(2)}ms`);
        }
    }
};

/**
 * Show/hide loading indicator
 */
const loadingIndicator = {
    show() {
        if (!document.getElementById('chaptr-init-loader')) {
            // Check if reloading due to service worker update
            // Handle sessionStorage being disabled (private browsing, SecurityError)
            let isUpdating = false;
            try {
                isUpdating = sessionStorage.getItem('chaptr-sw-updating') === 'true';
            } catch (e) {
                // sessionStorage disabled - default to normal loading message
                logger.info('[Loading] sessionStorage unavailable:', e.message);
            }

            const loadingMessage = isUpdating ? 'Updating application...' : 'Loading application...';

            // Clear the flag immediately (before showing loader)
            if (isUpdating) {
                try {
                    sessionStorage.removeItem('chaptr-sw-updating');
                } catch (e) {
                    // sessionStorage disabled - flag can't be cleared but that's OK
                }
            }

            const loader = document.createElement('div');
            loader.id = 'chaptr-init-loader';
            loader.style.cssText = `
                position: fixed;
                top: 0;
                left: 0;
                right: 0;
                bottom: 0;
                background: #0a0a0a;
                display: flex;
                align-items: center;
                justify-content: center;
                z-index: 999999;
                font-family: 'JetBrains Mono', monospace;
            `;
            loader.innerHTML = `
                <div style="text-align: center;">
                    <div style="color: #4af626; font-size: 2rem; margin-bottom: 1rem; font-weight: 600;">CHAPTR</div>
                    <div style="color: #888; font-size: 0.9rem;">${loadingMessage}</div>
                    <div style="width: 200px; height: 2px; background: #1a1a1a; margin: 1.5rem auto; overflow: hidden;">
                        <div style="height: 100%; background: #4af626; animation: progress 1.5s ease-in-out infinite;"></div>
                    </div>
                </div>
                <style>
                    @keyframes progress {
                        0% { width: 0%; margin-left: 0; }
                        50% { width: 70%; margin-left: 15%; }
                        100% { width: 0%; margin-left: 100%; }
                    }
                </style>
            `;
            document.body.appendChild(loader);
        }
    },

    hide() {
        const loader = document.getElementById('chaptr-init-loader');
        if (loader) {
            loader.style.transition = 'opacity 0.3s ease-out';
            loader.style.opacity = '0';
            setTimeout(() => loader.remove(), 300);
        }
    }
};

/**
 * Load Alpine.js from CDN with retry logic
 * @param {number} attempt - Current attempt number
 * @returns {Promise<void>}
 */
async function loadAlpine(attempt = 1) {
    const maxAttempts = 2;
    const timeout = 10000; // 10 seconds

    return new Promise((resolve, reject) => {
        logger.info(`Loading Alpine.js (attempt ${attempt}/${maxAttempts})...`);

        const script = document.createElement('script');
        script.src = 'https://cdn.jsdelivr.net/npm/alpinejs@3.14.1/dist/cdn.min.js';
        // Note: defer has no effect on dynamically created scripts
        // They execute asynchronously by default

        let resolved = false;

        script.onload = () => {
            if (!resolved) {
                resolved = true;
                logger.info('Alpine.js loaded successfully');
                logger.perf('Alpine.js load time');
                resolve();
            }
        };

        script.onerror = async () => {
            if (!resolved) {
                resolved = true;
                document.head.removeChild(script);

                if (attempt < maxAttempts) {
                    logger.warn(`Alpine.js load failed, retrying (${attempt}/${maxAttempts})...`);
                    try {
                        await new Promise(r => setTimeout(r, 1000)); // Wait 1s before retry
                        await loadAlpine(attempt + 1);
                        resolve();
                    } catch (retryError) {
                        reject(retryError);
                    }
                } else {
                    const error = new Error(`Failed to load Alpine.js after ${maxAttempts} attempts`);
                    logger.error(error);
                    reject(error);
                }
            }
        };

        document.head.appendChild(script);

        // Timeout fallback
        setTimeout(() => {
            if (!resolved && !window.Alpine) {
                resolved = true;
                reject(new Error(`Alpine.js load timeout after ${timeout}ms`));
            }
        }, timeout);
    });
}

/**
 * Register global components and utilities
 * These must be available before Alpine initializes
 */
function registerGlobals() {
    logger.info('Registering global components...');

    // Register dropdown factories with validation
    try {
        window.settingsDropdown = settingsDropdown;
        window.modalDropdown = modalDropdown;
        logger.info('Registered: settingsDropdown, modalDropdown');
        logger.perf('Global registration');
    } catch (error) {
        throw new Error(`Failed to register global components: ${error.message}`);
    }
}

/**
 * Initialize service worker for offline support
 */
async function initServiceWorker() {
    if (!('serviceWorker' in navigator)) {
        logger.info('Service Worker not supported');
        return;
    }

    const registerSW = async () => {
        try {
            // Fetch SW version to force browser to check for updates
            // This ensures browser treats SW as a new URL when version changes
            const versionResponse = await fetch('/sw-version');
            const { version } = await versionResponse.json();

            const registration = await navigator.serviceWorker.register(`/sw.js?v=${version}`, {
                updateViaCache: 'none'  // Always fetch SW from network, never use HTTP cache
            });
            logger.info('Service Worker registered:', registration.scope, `(version: ${version})`);
            logger.perf('Service Worker registration');

            // Check for updates on registration
            registration.addEventListener('updatefound', () => {
                const newWorker = registration.installing;
                logger.info('[SW] Update found, new service worker installing...');

                newWorker.addEventListener('statechange', () => {
                    if (newWorker.state === 'installed' && navigator.serviceWorker.controller) {
                        // New service worker installed but old one still controlling
                        // Tell it to skip waiting (will trigger controllerchange)
                        logger.info('[SW] New service worker installed, activating...');
                        newWorker.postMessage({ type: 'SKIP_WAITING' });
                        // Don't reload here - wait for controllerchange event
                    }
                });
            });

            // Listen for controlling service worker change (reload only here)
            // Debounced to prevent reload loops in edge cases
            let controllerChangeHandled = false;
            navigator.serviceWorker.addEventListener('controllerchange', () => {
                if (!controllerChangeHandled) {
                    controllerChangeHandled = true;
                    logger.info('[SW] Controller changed, reloading page...');

                    // Set flag to show "Updating Application..." on next load
                    // Handle sessionStorage being disabled (private browsing, SecurityError)
                    try {
                        sessionStorage.setItem('chaptr-sw-updating', 'true');
                    } catch (e) {
                        // sessionStorage disabled - UX message won't show but reload still works
                        logger.info('[SW] sessionStorage unavailable, update message will not show');
                    }

                    setTimeout(() => testableUtils.reloadPage(), 100);
                }
            });

            // Listen for background sync messages
            navigator.serviceWorker.addEventListener('message', event => {
                if (event.data?.type === 'BACKGROUND_SYNC') {
                    logger.info('Background sync triggered');

                    // Trigger Alpine.js manual sync if available
                    const appElement = document.querySelector('[x-data]');
                    if (appElement?.__x?.$data?.manualSync) {
                        try {
                            appElement.__x.$data.manualSync();
                        } catch (error) {
                            logger.error('Manual sync failed:', error);
                        }
                    }
                }
            });
        } catch (error) {
            logger.error('Service Worker registration failed:', error);
            // Don't throw - app works without SW
        }
    };

    // Check if page has already fully loaded
    if (document.readyState === 'complete') {
        await registerSW();
    } else {
        window.addEventListener('load', registerSW);
    }
}

/**
 * HTML escape for safe error display
 * @param {string} str - String to escape
 * @returns {string} Escaped string
 */
function escapeHTML(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

/**
 * Display user-friendly error screen
 * @param {Error} error - Error to display
 */
function showErrorScreen(error) {
    logger.error('Initialization failed:', error);

    const errorMessage = escapeHTML(error.message);
    const errorStack = isDevelopment && error.stack ?
        `<details style="margin-top: 1rem;">
            <summary style="cursor: pointer; color: #888;">Technical Details</summary>
            <pre style="margin-top: 0.5rem; font-size: 0.8rem; color: #666; overflow-x: auto;">${escapeHTML(error.stack)}</pre>
        </details>` : '';

    document.body.innerHTML = `
        <div style="font-family: 'JetBrains Mono', monospace; padding: 2rem; max-width: 600px; margin: 2rem auto; color: #ccc;">
            <h1 style="color: #4af626; font-size: 2rem; margin-bottom: 1rem; font-weight: 600;">CHAPTR</h1>
            <div style="background: #1a1a1a; padding: 1.5rem; border-radius: 8px; border-left: 4px solid #ff4444;">
                <h2 style="color: #ff4444; margin: 0 0 1rem 0; font-size: 1.2rem;">Initialization Error</h2>
                <p style="margin: 0 0 1rem 0; line-height: 1.6;">The application failed to initialize:</p>
                <pre style="background: #0a0a0a; padding: 1rem; border-radius: 4px; overflow-x: auto; color: #ff6666;">${errorMessage}</pre>
                ${errorStack}
            </div>
            <div style="margin-top: 1.5rem; padding: 1rem; background: #1a1a1a; border-radius: 8px;">
                <p style="margin: 0 0 0.5rem 0; font-weight: 600;">What to do:</p>
                <ul style="margin: 0; padding-left: 1.5rem; line-height: 1.8;">
                    <li>Check your internet connection</li>
                    <li>Try refreshing the page</li>
                    <li>Clear browser cache and reload</li>
                    <li>If problem persists, contact support</li>
                </ul>
            </div>
            <button onclick="location.reload()" style="
                margin-top: 1.5rem;
                background: #4af626;
                color: #0a0a0a;
                border: none;
                padding: 0.75rem 1.5rem;
                border-radius: 4px;
                font-family: 'JetBrains Mono', monospace;
                font-weight: 600;
                cursor: pointer;
                font-size: 1rem;
                width: 100%;
            ">Reload Page</button>
        </div>
    `;
}

/**
 * Testable utilities - exposed as object properties for mocking
 * @private
 */
const testableUtils = {
    /**
     * Wrapper for window.location.reload() that can be mocked in tests
     */
    reloadPage() {
        window.location.reload();
    }
};

/**
 * Check if service worker update is available
 * Returns true if update needed, false otherwise
 */
async function checkForServiceWorkerUpdate() {
    if (!('serviceWorker' in navigator)) {
        return false;
    }

    try {
        // Get current SW version from server
        const versionResponse = await fetch('/sw-version');
        const { version: newVersion } = await versionResponse.json();

        // Check if we have an active SW with different version
        const registration = await navigator.serviceWorker.getRegistration();
        if (registration?.active) {
            const currentUrl = registration.active.scriptURL;
            const currentVersion = new URL(currentUrl).searchParams.get('v');

            if (currentVersion && currentVersion !== newVersion) {
                logger.info(`[SW] Update available: ${currentVersion} → ${newVersion}`);
                return true;
            }
        }
    } catch (error) {
        logger.warn('[SW] Version check failed:', error);
    }

    return false;
}

/**
 * Main initialization sequence
 */
async function init() {
    try {
        logger.info('Starting initialization...');
        loadingIndicator.show();

        // Step 0: Check for SW update BEFORE loading app
        // If update available, skip loading and go straight to SW registration
        const updateAvailable = await checkForServiceWorkerUpdate();

        if (!updateAvailable) {
            // No update - load app normally
            // Step 1: Import app module (sets window.app)
            await import('./app.js');
            logger.perf('App module import');

            if (typeof window.app !== 'function') {
                throw new Error('app() function not defined after importing app.js');
            }
            logger.info('App module loaded ✓');

            // Step 2: Register global components
            registerGlobals();

            // Step 3: Load Alpine.js (with retry)
            await loadAlpine();
        } else {
            logger.info('[SW] Skipping app load, update will trigger reload');
        }

        // Step 4: Initialize service worker (always run, triggers reload if update)
        await initServiceWorker();

        // Complete (only hide loader if no update pending)
        if (!updateAvailable) {
            const totalTime = (performance.now() - perf.start).toFixed(2);
            logger.info(`Initialization complete ✓ (${totalTime}ms)`);

            if (isDevelopment) {
                console.table(perf.marks);
            }

            // Hide loading indicator
            loadingIndicator.hide();
        } else {
            logger.info('[SW] Waiting for service worker update to trigger reload...');
            // Keep loader visible - will reload soon
        }

    } catch (error) {
        loadingIndicator.hide();
        showErrorScreen(error);
    }
}

/**
 * Module Exports
 *
 * Note: These exports are primarily for testing purposes. ES modules do not support
 * conditional exports, so all functions remain exported in production. In production
 * bundles, tree-shaking will remove unused exports.
 *
 * Export Categories:
 * - TEST-ONLY: testableUtils - Required for mocking window.location.reload() in tests
 * - TEST-ONLY: checkForServiceWorkerUpdate - Unit testing SW version detection
 * - TEST-ONLY: initServiceWorker - Unit testing SW registration logic
 * - TEST-ONLY: loadingIndicator - Unit testing loader show/hide behavior
 * - TEST-ONLY: logger - Unit testing log output
 * - INTERNAL: init - Main initialization function (called automatically, exported for test access)
 *
 * Production Impact: None - init() auto-runs, other functions unused in production code
 */
export {
    checkForServiceWorkerUpdate,
    initServiceWorker,
    loadingIndicator,
    init,
    logger,
    testableUtils
};

// Start initialization when DOM is ready (skip in test environment)
if (typeof process === 'undefined' || process.env.NODE_ENV !== 'test') {
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
}
