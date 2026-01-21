/**
 * Unit tests for auto-sync timer functionality
 *
 * Tests the automatic periodic sync feature including:
 * - Interval normalization (ms to seconds migration)
 * - Interval formatting for display
 * - Timer lifecycle (start/stop/restart)
 * - Pending sync when tab hidden, triggered on return
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import {
    normalizeAutoSyncInterval,
    formatSyncInterval,
    formatCountdown
} from '../../../static/js/modules/formatting.js';
import {
    AutoSyncManager,
    getStoredNextSyncTime,
    setStoredNextSyncTime
} from '../../../static/js/modules/auto-sync.js';

/**
 * Mock Alpine component with auto-sync functionality
 * Simulates the relevant parts of the app.js Alpine component
 *
 * NOTE: This mock delegates formatting functions to the real implementations
 * from formatting.js. Only state management and timer behavior is mocked.
 */
class MockAutoSyncComponent {
    constructor() {
        this.settings = { auto_sync_interval: 0 };
        this.autoSyncTimerId = null;
        this.autoSyncPending = false;  // Sync pending while tab was hidden
        this.autoSyncCountdown = '';   // Countdown display string
        this.isSyncing = false;
        this.syncTriggerCount = 0;
        this.logs = [];
        this.mockTabHidden = false;  // Simulates document.hidden
        this.mockNow = null;         // Mock current time for testing
    }

    /**
     * Mock localStorage storage for next sync time
     */
    _storedNextSyncTime = null;

    getStoredNextSyncTime() {
        return this._storedNextSyncTime;
    }

    setStoredNextSyncTime(timestamp) {
        this._storedNextSyncTime = timestamp;
    }

    /**
     * Start auto-sync timer (simplified for testing - uses callback instead of setInterval)
     * @param {boolean} forceReset - If true, ignores stored time and starts fresh
     */
    startAutoSyncTimer(forceReset = false) {
        this.stopAutoSyncTimer();

        const intervalSeconds = normalizeAutoSyncInterval(this.settings.auto_sync_interval);
        if (!intervalSeconds || intervalSeconds <= 0) {
            this.logs.push('[CHAPTR] Auto-sync disabled');
            this.autoSyncCountdown = '';
            this.setStoredNextSyncTime(null);
            return;
        }

        const intervalMs = intervalSeconds * 1000;
        const now = this.mockNow || Date.now();
        let nextSyncTime;

        if (forceReset) {
            // User changed interval - start fresh
            nextSyncTime = now + intervalMs;
            this.setStoredNextSyncTime(nextSyncTime);
            this.logs.push(`[CHAPTR] Auto-sync interval changed to ${intervalSeconds}s`);
        } else {
            // Check if we have a stored next sync time that's still valid
            nextSyncTime = this.getStoredNextSyncTime();

            if (!nextSyncTime || nextSyncTime <= now) {
                nextSyncTime = now + intervalMs;
                this.setStoredNextSyncTime(nextSyncTime);
            }
        }

        // Calculate initial delay
        const initialDelay = Math.max(0, nextSyncTime - now);
        this.logs.push(`[CHAPTR] Starting auto-sync timer: ${intervalSeconds}s (first in ${Math.round(initialDelay / 1000)}s)`);

        // Store the callback so tests can invoke it
        this._timerCallback = () => {
            // Skip if offline or already syncing
            if (this.mockOffline || this.isSyncing) {
                this.logs.push('[CHAPTR] Auto-sync skipped (offline/syncing)');
                return;
            }

            // Check if there's anything to sync
            if (this.mockQueueCount === 0) {
                this.logs.push('[CHAPTR] Auto-sync: nothing to sync');
                return;
            }

            // If tab is hidden, queue sync for when user returns
            if (this.mockTabHidden) {
                this.autoSyncPending = true;
                this.logs.push(`[CHAPTR] Auto-sync queued (${this.mockQueueCount} pending, tab hidden)`);
                return;
            }

            this.logs.push(`[CHAPTR] Auto-sync triggered (${this.mockQueueCount} pending)`);
            this.syncTriggerCount++;
        };

        this.autoSyncTimerId = setInterval(this._timerCallback, intervalMs);
    }

    /**
     * Simulate timer firing (for testing without real timers)
     */
    simulateTimerFire() {
        if (this._timerCallback) {
            this._timerCallback();
        }
    }

    /**
     * Stop auto-sync timer
     */
    stopAutoSyncTimer() {
        if (this.autoSyncTimerId) {
            clearInterval(this.autoSyncTimerId);
            this.autoSyncTimerId = null;
            this._timerCallback = null;
            this.logs.push('[CHAPTR] Auto-sync timer stopped');
        }
    }

    /**
     * Handle visibility change
     * When tab becomes visible and sync was pending, triggers sync immediately.
     */
    handleAutoSyncVisibilityChange(isHidden) {
        this.mockTabHidden = isHidden;
        if (!isHidden && this.autoSyncPending) {
            this.logs.push('[CHAPTR] Tab visible - triggering pending auto-sync');
            this.autoSyncPending = false;
            this.syncTriggerCount++;
        }
    }

    // Mock properties for testing
    mockQueueCount = 0;
    mockOffline = false;
}

// ============================================================================
// Pure Function Tests - Testing Real Implementations
// ============================================================================

describe('Auto-Sync: normalizeAutoSyncInterval', () => {
    it('should return 0 for null/undefined/0 values', () => {
        expect(normalizeAutoSyncInterval(null)).toBe(0);
        expect(normalizeAutoSyncInterval(undefined)).toBe(0);
        expect(normalizeAutoSyncInterval(0)).toBe(0);
        expect(normalizeAutoSyncInterval(-1)).toBe(0);
    });

    it('should pass through values <= 86400 (seconds)', () => {
        expect(normalizeAutoSyncInterval(300)).toBe(300);      // 5 minutes
        expect(normalizeAutoSyncInterval(3600)).toBe(3600);    // 1 hour
        expect(normalizeAutoSyncInterval(86400)).toBe(86400);  // 1 day
    });

    it('should convert values > 86400 (milliseconds) to seconds', () => {
        expect(normalizeAutoSyncInterval(300000)).toBe(300);      // 5 min in ms -> 5 min in s
        expect(normalizeAutoSyncInterval(3600000)).toBe(3600);    // 1 hr in ms -> 1 hr in s
        expect(normalizeAutoSyncInterval(86400000)).toBe(86400);  // 1 day in ms -> 1 day in s
    });
});

describe('Auto-Sync: formatSyncInterval', () => {
    it('should format 60 seconds as "1m"', () => {
        expect(formatSyncInterval(60)).toBe('1m');
    });

    it('should format 300 seconds as "5m"', () => {
        expect(formatSyncInterval(300)).toBe('5m');
    });

    it('should format 3600 seconds as "1h"', () => {
        expect(formatSyncInterval(3600)).toBe('1h');
    });

    it('should format 86400 seconds as "1d"', () => {
        expect(formatSyncInterval(86400)).toBe('1d');
    });

    it('should format multi-day intervals', () => {
        expect(formatSyncInterval(172800)).toBe('2d');  // 2 days
    });

    it('should format multi-hour intervals', () => {
        expect(formatSyncInterval(7200)).toBe('2h');  // 2 hours
    });

    it('should format multi-minute intervals', () => {
        expect(formatSyncInterval(600)).toBe('10m');  // 10 minutes
    });

    it('should format small intervals in seconds', () => {
        expect(formatSyncInterval(30)).toBe('30s');
    });
});

describe('Auto-Sync: formatCountdown', () => {
    it('should return empty string for 0 or negative values', () => {
        expect(formatCountdown(0)).toBe('');
        expect(formatCountdown(-5)).toBe('');
    });

    it('should format seconds under 60 as just the number', () => {
        expect(formatCountdown(45)).toBe('45');
        expect(formatCountdown(5)).toBe('5');
        expect(formatCountdown(59)).toBe('59');
    });

    it('should format 60+ seconds as mm:ss', () => {
        expect(formatCountdown(60)).toBe('1:00');
        expect(formatCountdown(90)).toBe('1:30');
        expect(formatCountdown(125)).toBe('2:05');
    });

    it('should pad seconds with leading zero', () => {
        expect(formatCountdown(61)).toBe('1:01');
        expect(formatCountdown(305)).toBe('5:05');
    });

    it('should handle longer durations', () => {
        expect(formatCountdown(300)).toBe('5:00');
        expect(formatCountdown(3599)).toBe('59:59');
        expect(formatCountdown(3600)).toBe('60:00');
    });
});

// ============================================================================
// Timer Integration Tests - Using Mock Component with Real Functions
// ============================================================================

describe('Auto-Sync: Timer Lifecycle', () => {
    let component;

    beforeEach(() => {
        vi.useFakeTimers();
        component = new MockAutoSyncComponent();
    });

    afterEach(() => {
        component.stopAutoSyncTimer();
        vi.useRealTimers();
    });

    it('should not start timer when interval is 0 (off)', () => {
        component.settings.auto_sync_interval = 0;
        component.startAutoSyncTimer();

        expect(component.autoSyncTimerId).toBeNull();
        expect(component.logs).toContain('[CHAPTR] Auto-sync disabled');
    });

    it('should start timer when interval > 0', () => {
        component.settings.auto_sync_interval = 300;  // 5 minutes
        component.startAutoSyncTimer();

        expect(component.autoSyncTimerId).not.toBeNull();
        // Log includes countdown info: "Starting auto-sync timer: 300s (first in Xs)"
        expect(component.logs.some(l => l.startsWith('[CHAPTR] Starting auto-sync timer: 300s'))).toBe(true);
    });

    it('should clear old timer when restarting', () => {
        component.settings.auto_sync_interval = 300;
        component.startAutoSyncTimer();
        const firstTimerId = component.autoSyncTimerId;

        component.settings.auto_sync_interval = 3600;
        component.startAutoSyncTimer();

        expect(component.autoSyncTimerId).not.toBe(firstTimerId);
        expect(component.logs.filter(l => l.includes('timer stopped')).length).toBe(1);
    });

    it('should stop timer when called', () => {
        component.settings.auto_sync_interval = 300;
        component.startAutoSyncTimer();

        expect(component.autoSyncTimerId).not.toBeNull();

        component.stopAutoSyncTimer();

        expect(component.autoSyncTimerId).toBeNull();
        expect(component.logs).toContain('[CHAPTR] Auto-sync timer stopped');
    });
});

describe('Auto-Sync: Timer Behavior', () => {
    let component;

    beforeEach(() => {
        component = new MockAutoSyncComponent();
    });

    afterEach(() => {
        component.stopAutoSyncTimer();
    });

    it('should queue sync when tab is hidden and trigger on return', () => {
        component.settings.auto_sync_interval = 300;
        component.mockQueueCount = 5;
        component.mockTabHidden = true;
        component.startAutoSyncTimer();

        // Simulate timer firing - sync should be queued, not triggered
        component.simulateTimerFire();

        expect(component.autoSyncPending).toBe(true);
        expect(component.logs).toContain('[CHAPTR] Auto-sync queued (5 pending, tab hidden)');
        expect(component.syncTriggerCount).toBe(0);

        // Tab becomes visible - sync should trigger immediately
        component.handleAutoSyncVisibilityChange(false);

        expect(component.autoSyncPending).toBe(false);
        expect(component.logs).toContain('[CHAPTR] Tab visible - triggering pending auto-sync');
        expect(component.syncTriggerCount).toBe(1);
    });

    it('should not trigger sync on tab visible if nothing was pending', () => {
        component.settings.auto_sync_interval = 300;
        component.mockQueueCount = 5;
        component.startAutoSyncTimer();

        // Tab becomes visible without any pending sync
        component.handleAutoSyncVisibilityChange(false);

        expect(component.logs).not.toContain('[CHAPTR] Tab visible - triggering pending auto-sync');
        expect(component.syncTriggerCount).toBe(0);
    });

    it('should skip sync when offline', () => {
        component.settings.auto_sync_interval = 300;
        component.mockQueueCount = 5;
        component.mockOffline = true;
        component.startAutoSyncTimer();

        component.simulateTimerFire();

        expect(component.logs).toContain('[CHAPTR] Auto-sync skipped (offline/syncing)');
        expect(component.syncTriggerCount).toBe(0);
    });

    it('should skip sync when already syncing', () => {
        component.settings.auto_sync_interval = 300;
        component.mockQueueCount = 5;
        component.isSyncing = true;
        component.startAutoSyncTimer();

        component.simulateTimerFire();

        expect(component.logs).toContain('[CHAPTR] Auto-sync skipped (offline/syncing)');
        expect(component.syncTriggerCount).toBe(0);
    });

    it('should skip sync when queue is empty', () => {
        component.settings.auto_sync_interval = 300;
        component.mockQueueCount = 0;
        component.startAutoSyncTimer();

        component.simulateTimerFire();

        expect(component.logs).toContain('[CHAPTR] Auto-sync: nothing to sync');
        expect(component.syncTriggerCount).toBe(0);
    });

    it('should trigger sync when all conditions are met', () => {
        component.settings.auto_sync_interval = 300;
        component.mockQueueCount = 5;
        component.mockOffline = false;
        component.mockTabHidden = false;
        component.startAutoSyncTimer();

        component.simulateTimerFire();

        expect(component.logs).toContain('[CHAPTR] Auto-sync triggered (5 pending)');
        expect(component.syncTriggerCount).toBe(1);
    });

    it('should trigger multiple syncs over time', () => {
        component.settings.auto_sync_interval = 300;
        component.mockQueueCount = 3;
        component.startAutoSyncTimer();

        // First interval
        component.simulateTimerFire();
        expect(component.syncTriggerCount).toBe(1);

        // Second interval
        component.simulateTimerFire();
        expect(component.syncTriggerCount).toBe(2);

        // Third interval
        component.simulateTimerFire();
        expect(component.syncTriggerCount).toBe(3);
    });

    it('should sync when user returns after timer fired while away', () => {
        component.settings.auto_sync_interval = 300;  // 5 minutes
        component.mockQueueCount = 5;
        component.startAutoSyncTimer();

        // User is away from tab when timer fires
        component.mockTabHidden = true;
        component.simulateTimerFire();

        // Sync should be queued
        expect(component.autoSyncPending).toBe(true);
        expect(component.syncTriggerCount).toBe(0);

        // User returns to tab - sync triggers immediately
        component.handleAutoSyncVisibilityChange(false);
        expect(component.syncTriggerCount).toBe(1);
    });
});

describe('Auto-Sync: Settings Change', () => {
    let component;

    beforeEach(() => {
        vi.useFakeTimers();
        component = new MockAutoSyncComponent();
    });

    afterEach(() => {
        component.stopAutoSyncTimer();
        vi.useRealTimers();
    });

    it('should switch from off to 5 minutes correctly', () => {
        // Start with off
        component.settings.auto_sync_interval = 0;
        component.startAutoSyncTimer();
        expect(component.autoSyncTimerId).toBeNull();

        // Change to 5 minutes
        component.settings.auto_sync_interval = 300;
        component.startAutoSyncTimer();
        expect(component.autoSyncTimerId).not.toBeNull();
    });

    it('should switch from 5 minutes to off correctly', () => {
        // Start with 5 minutes
        component.settings.auto_sync_interval = 300;
        component.startAutoSyncTimer();
        expect(component.autoSyncTimerId).not.toBeNull();

        // Change to off
        component.settings.auto_sync_interval = 0;
        component.startAutoSyncTimer();
        expect(component.autoSyncTimerId).toBeNull();
    });

    it('should switch from 5 minutes to 1 hour correctly', () => {
        // Start with 5 minutes
        component.settings.auto_sync_interval = 300;
        component.startAutoSyncTimer();
        const firstTimerId = component.autoSyncTimerId;

        // Change to 1 hour
        component.settings.auto_sync_interval = 3600;
        component.startAutoSyncTimer();

        expect(component.autoSyncTimerId).not.toBeNull();
        expect(component.autoSyncTimerId).not.toBe(firstTimerId);
    });

    it('should handle pending sync when settings change', () => {
        component.settings.auto_sync_interval = 300;
        component.mockQueueCount = 5;
        component.mockTabHidden = true;
        component.startAutoSyncTimer();

        // Sync queued while hidden
        component.simulateTimerFire();
        expect(component.autoSyncPending).toBe(true);

        // User changes to 1 hour - pending flag remains
        component.settings.auto_sync_interval = 3600;
        component.startAutoSyncTimer();

        // Tab becomes visible - pending sync still triggers
        component.handleAutoSyncVisibilityChange(false);
        expect(component.syncTriggerCount).toBe(1);
    });
});

describe('Auto-Sync: Force Reset on Interval Change', () => {
    let component;

    beforeEach(() => {
        component = new MockAutoSyncComponent();
        component.mockNow = 1000000; // Fixed time for predictable testing
    });

    afterEach(() => {
        component.stopAutoSyncTimer();
    });

    it('should use stored time when forceReset is false', () => {
        // Set a stored next sync time 100 seconds from now
        const storedNextSync = component.mockNow + 100000; // 100 seconds
        component.setStoredNextSyncTime(storedNextSync);

        component.settings.auto_sync_interval = 300; // 5 minutes
        component.startAutoSyncTimer(false); // Don't force reset

        // Should use the stored time, not create a new one
        expect(component.getStoredNextSyncTime()).toBe(storedNextSync);
        // Log should show 100s initial delay, not 300s
        expect(component.logs.some(l => l.includes('first in 100s'))).toBe(true);
    });

    it('should ignore stored time when forceReset is true', () => {
        // Set a stored next sync time 100 seconds from now
        const storedNextSync = component.mockNow + 100000; // 100 seconds
        component.setStoredNextSyncTime(storedNextSync);

        component.settings.auto_sync_interval = 300; // 5 minutes = 300 seconds
        component.startAutoSyncTimer(true); // Force reset

        // Should create a new time based on the interval, not use stored
        const expectedNextSync = component.mockNow + 300000; // 5 minutes from now
        expect(component.getStoredNextSyncTime()).toBe(expectedNextSync);
        // Should log "interval changed"
        expect(component.logs.some(l => l.includes('interval changed to 300s'))).toBe(true);
        // Should show full interval as initial delay
        expect(component.logs.some(l => l.includes('first in 300s'))).toBe(true);
    });

    it('should reset countdown when changing from 5m to 1m', () => {
        // Start with 5 minutes, timer partially elapsed
        component.settings.auto_sync_interval = 300;
        component.startAutoSyncTimer(false);
        const first5mNextSync = component.getStoredNextSyncTime();

        // Simulate time passing (2 minutes)
        component.mockNow += 120000;
        component.logs = []; // Clear logs

        // Change to 1 minute with force reset
        component.settings.auto_sync_interval = 60;
        component.startAutoSyncTimer(true);

        // New next sync should be 1 minute from current time, not continuing old countdown
        const expectedNextSync = component.mockNow + 60000;
        expect(component.getStoredNextSyncTime()).toBe(expectedNextSync);
        expect(component.logs.some(l => l.includes('interval changed to 60s'))).toBe(true);
    });

    it('should clear stored time when switching to Off', () => {
        // Start with 5 minutes
        component.settings.auto_sync_interval = 300;
        component.startAutoSyncTimer(false);
        expect(component.getStoredNextSyncTime()).not.toBeNull();

        // Switch to off
        component.settings.auto_sync_interval = 0;
        component.startAutoSyncTimer(true);

        // Stored time should be cleared
        expect(component.getStoredNextSyncTime()).toBeNull();
        expect(component.autoSyncCountdown).toBe('');
    });

    it('should create new stored time if none exists (page refresh scenario)', () => {
        // No stored time (simulates fresh start or localStorage cleared)
        expect(component.getStoredNextSyncTime()).toBeNull();

        component.settings.auto_sync_interval = 300;
        component.startAutoSyncTimer(false); // Not forcing reset

        // Should create a new stored time
        const expectedNextSync = component.mockNow + 300000;
        expect(component.getStoredNextSyncTime()).toBe(expectedNextSync);
    });

    it('should create new stored time if stored time is in the past', () => {
        // Stored time is in the past (timer expired while page was closed)
        component.setStoredNextSyncTime(component.mockNow - 50000); // 50 seconds ago

        component.settings.auto_sync_interval = 300;
        component.startAutoSyncTimer(false); // Not forcing reset

        // Should create a new stored time since old one expired
        const expectedNextSync = component.mockNow + 300000;
        expect(component.getStoredNextSyncTime()).toBe(expectedNextSync);
    });
});


// ============================================================================
// AutoSyncManager Tests - Testing Real Implementation
// ============================================================================

describe('AutoSyncManager', () => {
    let manager;
    let callbacks;
    let logs;
    let countdownUpdates;

    beforeEach(() => {
        vi.useFakeTimers();
        logs = [];
        countdownUpdates = [];

        // Clear localStorage
        setStoredNextSyncTime(null);

        callbacks = {
            onCountdownUpdate: (countdown) => { countdownUpdates.push(countdown); },
            onSync: vi.fn().mockResolvedValue(undefined),
            onLog: (msg) => { logs.push(msg); },
            getQueueCount: vi.fn().mockResolvedValue(5),
            isOnline: vi.fn().mockReturnValue(true),
            isSyncing: vi.fn().mockReturnValue(false),
            isHidden: vi.fn().mockReturnValue(false)
        };

        manager = new AutoSyncManager(callbacks);
    });

    afterEach(() => {
        manager.stop();
        vi.useRealTimers();
        setStoredNextSyncTime(null);
    });

    describe('start()', () => {
        it('should disable when interval is 0', () => {
            manager.start(0);

            expect(logs).toContain('[CHAPTR] Auto-sync disabled');
            expect(getStoredNextSyncTime()).toBeNull();
        });

        it('should start timer when interval > 0', () => {
            manager.start(300); // 5 minutes

            expect(logs.some(l => l.includes('Starting auto-sync timer: 300s'))).toBe(true);
        });

        it('should normalize millisecond values to seconds', () => {
            manager.start(300000); // 300000ms = 300s

            expect(logs.some(l => l.includes('Starting auto-sync timer: 300s'))).toBe(true);
        });

        it('should force reset countdown when forceReset is true', () => {
            // Set a stored time
            const storedTime = Date.now() + 100000;
            setStoredNextSyncTime(storedTime);

            manager.start(300, true); // Force reset

            expect(logs.some(l => l.includes('interval changed to 300s'))).toBe(true);
        });

        it('should use stored time when forceReset is false', () => {
            const storedTime = Date.now() + 100000; // 100 seconds from now
            setStoredNextSyncTime(storedTime);

            manager.start(300, false);

            // Should show countdown based on stored time
            expect(logs.some(l => l.includes('first in 100s'))).toBe(true);
        });
    });

    describe('stop()', () => {
        it('should clear timer and log message', () => {
            manager.start(300);
            logs = []; // Clear logs

            manager.stop();

            expect(logs).toContain('[CHAPTR] Auto-sync timer stopped');
        });

        it('should clear countdown display', () => {
            manager.start(300);
            countdownUpdates = [];

            manager.stop();

            expect(countdownUpdates).toContain('');
        });
    });

    describe('handleVisibilityChange()', () => {
        it('should trigger sync when tab becomes visible and sync was pending', async () => {
            manager.start(300);
            manager.syncPending = true;
            callbacks.isHidden.mockReturnValue(false);

            await manager.handleVisibilityChange();

            expect(callbacks.onSync).toHaveBeenCalled();
            expect(manager.syncPending).toBe(false);
            expect(logs).toContain('[CHAPTR] Tab visible - triggering pending auto-sync');
        });

        it('should not trigger sync when nothing pending', async () => {
            manager.start(300);
            manager.syncPending = false;
            callbacks.isHidden.mockReturnValue(false);

            await manager.handleVisibilityChange();

            expect(callbacks.onSync).not.toHaveBeenCalled();
        });

        it('should not trigger sync when tab is still hidden', async () => {
            manager.start(300);
            manager.syncPending = true;
            callbacks.isHidden.mockReturnValue(true);

            await manager.handleVisibilityChange();

            expect(callbacks.onSync).not.toHaveBeenCalled();
        });
    });

    describe('resetAfterSync()', () => {
        it('should update stored next sync time', () => {
            const before = Date.now();
            manager.resetAfterSync(300);
            const after = Date.now();

            const storedTime = getStoredNextSyncTime();
            expect(storedTime).toBeGreaterThanOrEqual(before + 300000);
            expect(storedTime).toBeLessThanOrEqual(after + 300000);
        });

        it('should not update when interval is 0', () => {
            setStoredNextSyncTime(null);
            manager.resetAfterSync(0);

            expect(getStoredNextSyncTime()).toBeNull();
        });
    });

    describe('isPending() and clearPending()', () => {
        it('should track pending state', () => {
            expect(manager.isPending()).toBe(false);

            manager.syncPending = true;
            expect(manager.isPending()).toBe(true);

            manager.clearPending();
            expect(manager.isPending()).toBe(false);
        });
    });
});

describe('getStoredNextSyncTime / setStoredNextSyncTime', () => {
    afterEach(() => {
        setStoredNextSyncTime(null);
    });

    it('should store and retrieve timestamp', () => {
        const timestamp = 1234567890;
        setStoredNextSyncTime(timestamp);

        expect(getStoredNextSyncTime()).toBe(timestamp);
    });

    it('should return null when not set', () => {
        setStoredNextSyncTime(null);

        expect(getStoredNextSyncTime()).toBeNull();
    });

    it('should clear storage when set to null', () => {
        setStoredNextSyncTime(1234567890);
        setStoredNextSyncTime(null);

        expect(getStoredNextSyncTime()).toBeNull();
    });
});
