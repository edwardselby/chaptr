/**
 * CHAPTR - Auto-Sync Manager
 *
 * Manages automatic periodic sync with dependency injection for Alpine state updates.
 * Handles timer lifecycle, countdown display, and visibility-based sync queuing.
 */

import {
    normalizeAutoSyncInterval,
    formatCountdown
} from './formatting.js';

// ============================================================================
// Storage Keys
// ============================================================================

const STORAGE_KEY = 'chaptr_next_auto_sync';


// ============================================================================
// LocalStorage Helpers
// ============================================================================

/**
 * Get stored next sync timestamp from localStorage.
 *
 * @returns {number|null} Timestamp in ms or null if not stored/unavailable
 */
export function getStoredNextSyncTime() {
    try {
        const stored = localStorage.getItem(STORAGE_KEY);
        return stored ? parseInt(stored, 10) : null;
    } catch (e) {
        return null;
    }
}

/**
 * Store next sync timestamp in localStorage.
 *
 * @param {number|null} timestamp - Timestamp in ms, or null to clear
 */
export function setStoredNextSyncTime(timestamp) {
    try {
        if (timestamp) {
            localStorage.setItem(STORAGE_KEY, timestamp.toString());
        } else {
            localStorage.removeItem(STORAGE_KEY);
        }
    } catch (e) {
        // localStorage not available
    }
}


// ============================================================================
// AutoSyncManager Class
// ============================================================================

/**
 * Manages automatic periodic sync with callback-based integration.
 *
 * Usage:
 * ```javascript
 * const manager = new AutoSyncManager({
 *     onCountdownUpdate: (countdown) => this.autoSyncCountdown = countdown,
 *     onSync: () => this.triggerManualSync(),
 *     onLog: (msg) => console.log(msg),
 *     getQueueCount: () => db.sync_queue.count(),
 *     isOnline: () => navigator.onLine,
 *     isSyncing: () => this.isSyncing,
 *     isHidden: () => document.hidden
 * });
 *
 * manager.start(intervalSeconds, forceReset);
 * manager.stop();
 * manager.handleVisibilityChange();
 * ```
 */
export class AutoSyncManager {
    /**
     * Create an AutoSyncManager.
     *
     * @param {Object} callbacks - Callback functions for integration
     * @param {function(string)} callbacks.onCountdownUpdate - Called with formatted countdown string
     * @param {function():Promise<void>} callbacks.onSync - Called to trigger sync
     * @param {function(string)} callbacks.onLog - Called with log messages
     * @param {function():Promise<number>} callbacks.getQueueCount - Returns pending queue count
     * @param {function():boolean} callbacks.isOnline - Returns online status
     * @param {function():boolean} callbacks.isSyncing - Returns syncing status
     * @param {function():boolean} callbacks.isHidden - Returns tab visibility
     */
    constructor(callbacks) {
        this.callbacks = callbacks;

        // Timer IDs
        this.syncTimerId = null;
        this.countdownTimerId = null;

        // State
        this.syncPending = false;
        this.currentIntervalMs = 0;
    }

    /**
     * Start auto-sync timer.
     *
     * Sets up periodic sync based on interval. If tab is hidden when timer
     * fires, queues sync for when tab becomes visible. Persists next sync
     * time to localStorage for countdown continuity across refreshes.
     *
     * @param {number} rawInterval - Interval value (may be in ms or seconds)
     * @param {boolean} forceReset - If true, ignores stored time and starts fresh
     */
    start(rawInterval, forceReset = false) {
        this.stop(); // Clear any existing timer

        const intervalSeconds = normalizeAutoSyncInterval(rawInterval);
        if (!intervalSeconds || intervalSeconds <= 0) {
            this._log('[CHAPTR] Auto-sync disabled');
            this._updateCountdown('');
            setStoredNextSyncTime(null);
            return;
        }

        const intervalMs = intervalSeconds * 1000;
        this.currentIntervalMs = intervalMs;
        const now = Date.now();
        let nextSyncTime;

        if (forceReset) {
            // User changed interval - start fresh
            nextSyncTime = now + intervalMs;
            setStoredNextSyncTime(nextSyncTime);
            this._log(`[CHAPTR] Auto-sync interval changed to ${intervalSeconds}s`);
        } else {
            // Check if we have a stored next sync time that's still valid
            nextSyncTime = getStoredNextSyncTime();

            if (!nextSyncTime || nextSyncTime <= now) {
                // Set new next sync time
                nextSyncTime = now + intervalMs;
                setStoredNextSyncTime(nextSyncTime);
            }
        }

        // Calculate initial delay (time until stored next sync)
        const initialDelay = Math.max(0, nextSyncTime - now);

        this._log(`[CHAPTR] Starting auto-sync timer: ${intervalSeconds}s (first in ${Math.round(initialDelay / 1000)}s)`);

        // Start countdown display
        this._startCountdownDisplay();

        // Schedule the sync cycle
        const scheduleNextSync = async () => {
            // Update next sync time for future
            const newNextSyncTime = Date.now() + intervalMs;
            setStoredNextSyncTime(newNextSyncTime);

            // Skip if offline or already syncing
            if (!this.callbacks.isOnline() || this.callbacks.isSyncing()) {
                this._log('[CHAPTR] Auto-sync skipped (offline/syncing)');
                return;
            }

            // Check if there's anything to sync
            const queueCount = await this.callbacks.getQueueCount();
            if (queueCount === 0) {
                this._log('[CHAPTR] Auto-sync: nothing to sync');
                return;
            }

            // If tab is hidden, queue sync for when user returns
            if (this.callbacks.isHidden()) {
                this.syncPending = true;
                this._log(`[CHAPTR] Auto-sync queued (${queueCount} pending, tab hidden)`);
                return;
            }

            this._log(`[CHAPTR] Auto-sync triggered (${queueCount} pending)`);
            await this.callbacks.onSync();
        };

        // First sync after initial delay, then regular interval
        this.syncTimerId = setTimeout(async () => {
            await scheduleNextSync();

            // Set up regular interval
            this.syncTimerId = setInterval(scheduleNextSync, intervalMs);
        }, initialDelay);
    }

    /**
     * Stop auto-sync timer and countdown display.
     */
    stop() {
        if (this.syncTimerId) {
            clearInterval(this.syncTimerId);
            clearTimeout(this.syncTimerId); // Could be either
            this.syncTimerId = null;
            this._log('[CHAPTR] Auto-sync timer stopped');
        }
        this._stopCountdownDisplay();
    }

    /**
     * Handle visibility change.
     *
     * When tab becomes visible and sync was pending, triggers sync immediately.
     *
     * @returns {Promise<void>}
     */
    async handleVisibilityChange() {
        if (!this.callbacks.isHidden() && this.syncPending) {
            this._log('[CHAPTR] Tab visible - triggering pending auto-sync');
            this.syncPending = false;
            await this.callbacks.onSync();
        }
    }

    /**
     * Reset timer after manual sync.
     *
     * Called after a successful sync to reset the countdown to full interval.
     *
     * @param {number} rawInterval - Interval value (may be in ms or seconds)
     */
    resetAfterSync(rawInterval) {
        const intervalSeconds = normalizeAutoSyncInterval(rawInterval);
        if (intervalSeconds > 0) {
            const nextSyncTime = Date.now() + (intervalSeconds * 1000);
            setStoredNextSyncTime(nextSyncTime);
        }
    }

    /**
     * Check if sync is pending (queued while tab was hidden).
     *
     * @returns {boolean}
     */
    isPending() {
        return this.syncPending;
    }

    /**
     * Clear pending sync flag.
     */
    clearPending() {
        this.syncPending = false;
    }

    // ========================================================================
    // Private Methods
    // ========================================================================

    /**
     * Start countdown display update interval.
     * @private
     */
    _startCountdownDisplay() {
        this._stopCountdownDisplay();

        // Update countdown every second
        this.countdownTimerId = setInterval(() => {
            const nextSyncTime = getStoredNextSyncTime();
            if (!nextSyncTime) {
                this._updateCountdown('');
                return;
            }

            const remainingMs = nextSyncTime - Date.now();
            if (remainingMs <= 0) {
                this._updateCountdown('');
                return;
            }

            this._updateCountdown(formatCountdown(Math.ceil(remainingMs / 1000)));
        }, 1000);

        // Initial update
        const nextSyncTime = getStoredNextSyncTime();
        if (nextSyncTime) {
            const remainingMs = nextSyncTime - Date.now();
            this._updateCountdown(remainingMs > 0 ? formatCountdown(Math.ceil(remainingMs / 1000)) : '');
        }
    }

    /**
     * Stop countdown display update interval.
     * @private
     */
    _stopCountdownDisplay() {
        if (this.countdownTimerId) {
            clearInterval(this.countdownTimerId);
            this.countdownTimerId = null;
        }
        this._updateCountdown('');
    }

    /**
     * Update countdown display via callback.
     * @private
     * @param {string} countdown - Formatted countdown string
     */
    _updateCountdown(countdown) {
        if (this.callbacks.onCountdownUpdate) {
            this.callbacks.onCountdownUpdate(countdown);
        }
    }

    /**
     * Log message via callback.
     * @private
     * @param {string} message - Log message
     */
    _log(message) {
        if (this.callbacks.onLog) {
            this.callbacks.onLog(message);
        }
    }
}
