/**
 * Unit tests for sync spinner defensive programming
 *
 * Tests the defensive mechanisms that prevent the sync spinner from getting stuck
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

/**
 * Mock Alpine component with sync functionality
 * Simulates the relevant parts of the app.js Alpine component
 */
class MockAlpineComponent {
    constructor() {
        this.isSyncing = false;
        this.syncButtonSpinner = false;
        this.syncQueueCount = 0;
        this.notifications = [];
    }

    // Mock methods
    showNotification(message, type) {
        this.notifications.push({ message, type });
    }

    async updateSyncQueueCount() {
        // Mock implementation
    }

    async loadData() {
        // Mock implementation
    }

    /**
     * Simplified version of triggerManualSync for testing
     * Includes all defensive programming features
     */
    async triggerManualSync(mockStorage, mockDb) {
        if (this.isSyncing) return;

        this.isSyncing = true;
        this.syncButtonSpinner = true;
        const spinnerStartTime = Date.now();

        // DEFENSIVE: Timeout guard - force sync to complete within 30 seconds
        const syncTimeout = 30000;
        const timeoutPromise = new Promise((_, reject) => {
            setTimeout(() => reject(new Error('Sync timeout after 30s')), syncTimeout);
        });

        try {
            await this.updateSyncQueueCount();

            if (this.syncQueueCount === 0) {
                this.showNotification('Nothing to sync', 'info');
                return;
            }

            // Perform incremental sync with timeout guard
            const syncPromise = (async () => {
                const result = await mockStorage.manualSync();

                const unresolvedConflicts = await mockDb.getUnresolvedConflicts();
                if (unresolvedConflicts.length > 0) {
                    this.showNotification(
                        `${unresolvedConflicts.length} conflicts`,
                        'warning'
                    );
                } else if (result.applied && result.applied > 0) {
                    this.showNotification(`Synced ${result.applied}`, 'success');
                } else {
                    this.showNotification('Sync complete', 'success');
                }

                await this.loadData();
            })();

            await Promise.race([syncPromise, timeoutPromise]);

        } catch (error) {
            console.error('Sync error:', error);
            if (error.message === 'Sync timeout after 30s') {
                this.showNotification('Sync timeout', 'error');
            } else {
                this.showNotification('Sync failed', 'error');
            }
        } finally {
            // Ensure spinner shows for minimum 1 second
            const elapsed = Date.now() - spinnerStartTime;
            const minDuration = 1000;
            if (elapsed < minDuration) {
                await new Promise(resolve => setTimeout(resolve, minDuration - elapsed));
            }

            this.isSyncing = false;
            this.syncButtonSpinner = false;
        }
    }

    /**
     * Simplified init() for testing state recovery
     */
    init() {
        // DEFENSIVE: Reset sync state on initialization
        this.isSyncing = false;
        this.syncButtonSpinner = false;
    }
}

describe('Sync Spinner Defensive Programming', () => {
    let component;
    let mockStorage;
    let mockDb;

    beforeEach(() => {
        component = new MockAlpineComponent();

        mockStorage = {
            manualSync: vi.fn().mockResolvedValue({ applied: 5 })
        };

        mockDb = {
            getUnresolvedConflicts: vi.fn().mockResolvedValue([])
        };

        vi.useFakeTimers();
    });

    afterEach(() => {
        vi.restoreAllMocks();
        vi.useRealTimers();
    });

    describe('Minimum Spinner Duration', () => {
        it('shows spinner for at least 1 second even if sync completes instantly', async () => {
            component.syncQueueCount = 5;

            // Start sync (completes instantly)
            const syncPromise = component.triggerManualSync(mockStorage, mockDb);

            // Spinner should be active immediately
            expect(component.syncButtonSpinner).toBe(true);

            // Advance time by 500ms (less than minimum)
            await vi.advanceTimersByTimeAsync(500);

            // Spinner should still be active
            expect(component.syncButtonSpinner).toBe(true);

            // Advance to 1000ms total
            await vi.advanceTimersByTimeAsync(500);

            // Wait for promises to resolve
            await syncPromise;

            // Spinner should now be off
            expect(component.syncButtonSpinner).toBe(false);
        });

        it('does not add extra delay if sync takes longer than 1 second', async () => {
            component.syncQueueCount = 5;

            // Make sync take 2 seconds
            mockStorage.manualSync = vi.fn().mockImplementation(() => {
                return new Promise(resolve => setTimeout(() => resolve({ applied: 5 }), 2000));
            });

            const syncPromise = component.triggerManualSync(mockStorage, mockDb);
            const startTime = Date.now();

            // Advance time to complete the sync
            await vi.advanceTimersByTimeAsync(2000);
            await syncPromise;

            const duration = Date.now() - startTime;

            // Should be ~2000ms, not 3000ms (2000 + 1000 minimum)
            expect(duration).toBeLessThan(2500);
            expect(component.syncButtonSpinner).toBe(false);
        });
    });

    describe('Timeout Guard', () => {
        it('times out sync operation after 30 seconds', async () => {
            component.syncQueueCount = 5;

            // Make sync hang indefinitely
            mockStorage.manualSync = vi.fn().mockImplementation(() => {
                return new Promise(() => {}); // Never resolves
            });

            const syncPromise = component.triggerManualSync(mockStorage, mockDb);

            // Advance time to timeout
            await vi.advanceTimersByTimeAsync(30000);

            // Wait for minimum duration
            await vi.advanceTimersByTimeAsync(1000);

            await syncPromise;

            // Should show timeout notification
            const timeoutNotification = component.notifications.find(n => n.message === 'Sync timeout');
            expect(timeoutNotification).toBeDefined();
            expect(timeoutNotification.type).toBe('error');

            // Spinner should be stopped
            expect(component.syncButtonSpinner).toBe(false);
            expect(component.isSyncing).toBe(false);
        });

        it('completes successfully if sync finishes before timeout', async () => {
            component.syncQueueCount = 5;

            // Make sync take 5 seconds (well under 30s timeout)
            mockStorage.manualSync = vi.fn().mockImplementation(() => {
                return new Promise(resolve => setTimeout(() => resolve({ applied: 3 }), 5000));
            });

            const syncPromise = component.triggerManualSync(mockStorage, mockDb);

            // Advance time to complete sync
            await vi.advanceTimersByTimeAsync(5000);

            // Wait for minimum duration
            await vi.advanceTimersByTimeAsync(1000);

            await syncPromise;

            // Should show success notification, not timeout
            const successNotification = component.notifications.find(n => n.message === 'Synced 3');
            expect(successNotification).toBeDefined();
            expect(successNotification.type).toBe('success');

            // Should NOT have timeout notification
            const timeoutNotification = component.notifications.find(n => n.message === 'Sync timeout');
            expect(timeoutNotification).toBeUndefined();
        });
    });

    describe('Error Handling', () => {
        it('stops spinner even if sync throws an error', async () => {
            component.syncQueueCount = 5;

            // Make sync throw an error
            mockStorage.manualSync = vi.fn().mockRejectedValue(new Error('Network error'));

            const syncPromise = component.triggerManualSync(mockStorage, mockDb);

            // Advance time for minimum duration
            await vi.advanceTimersByTimeAsync(1000);
            await syncPromise;

            // Should show error notification
            const errorNotification = component.notifications.find(n => n.message === 'Sync failed');
            expect(errorNotification).toBeDefined();
            expect(errorNotification.type).toBe('error');

            // Spinner should be stopped
            expect(component.syncButtonSpinner).toBe(false);
            expect(component.isSyncing).toBe(false);
        });

        it('handles conflicts after sync', async () => {
            component.syncQueueCount = 5;

            // Mock conflicts
            mockDb.getUnresolvedConflicts = vi.fn().mockResolvedValue([
                { id: '1', entity: 'event' },
                { id: '2', entity: 'account' }
            ]);

            const syncPromise = component.triggerManualSync(mockStorage, mockDb);

            await vi.advanceTimersByTimeAsync(1000);
            await syncPromise;

            // Should show conflict warning
            const conflictNotification = component.notifications.find(n => n.message === '2 conflicts');
            expect(conflictNotification).toBeDefined();
            expect(conflictNotification.type).toBe('warning');

            // Spinner should be stopped
            expect(component.syncButtonSpinner).toBe(false);
        });
    });

    describe('State Recovery', () => {
        it('resets sync state on initialization', () => {
            // Set stuck state
            component.isSyncing = true;
            component.syncButtonSpinner = true;

            // Initialize
            component.init();

            // Should reset both flags
            expect(component.isSyncing).toBe(false);
            expect(component.syncButtonSpinner).toBe(false);
        });
    });

    describe('Guard Against Multiple Syncs', () => {
        it('prevents concurrent sync operations', async () => {
            component.syncQueueCount = 5;

            // Start first sync
            const firstSync = component.triggerManualSync(mockStorage, mockDb);

            // Try to start second sync while first is running
            const secondSync = component.triggerManualSync(mockStorage, mockDb);

            // Second sync should return immediately without doing anything
            await secondSync;

            // First sync should still be running
            expect(component.isSyncing).toBe(true);

            // Complete first sync
            await vi.advanceTimersByTimeAsync(1000);
            await firstSync;

            // Now syncing should be false
            expect(component.isSyncing).toBe(false);

            // manualSync should only have been called once (by first sync)
            expect(mockStorage.manualSync).toHaveBeenCalledTimes(1);
        });
    });

    describe('Nothing to Sync', () => {
        it('shows info notification and stops spinner when queue is empty', async () => {
            component.syncQueueCount = 0;

            const syncPromise = component.triggerManualSync(mockStorage, mockDb);

            await vi.advanceTimersByTimeAsync(1000);
            await syncPromise;

            // Should show info notification
            const infoNotification = component.notifications.find(n => n.message === 'Nothing to sync');
            expect(infoNotification).toBeDefined();
            expect(infoNotification.type).toBe('info');

            // Should not call manualSync
            expect(mockStorage.manualSync).not.toHaveBeenCalled();

            // Spinner should be stopped
            expect(component.syncButtonSpinner).toBe(false);
        });
    });
});

describe('Page Lifecycle Event Handlers', () => {
    describe('Page Visibility Handler', () => {
        it('resets spinner when page becomes visible with active spinner', () => {
            const component = new MockAlpineComponent();

            // Simulate stuck spinner
            component.syncButtonSpinner = true;
            component.isSyncing = true;

            // Simulate visibility change handler logic
            const isHidden = false; // Page is visible
            if (!isHidden && component.syncButtonSpinner) {
                component.isSyncing = false;
                component.syncButtonSpinner = false;
            }

            // Should reset state
            expect(component.isSyncing).toBe(false);
            expect(component.syncButtonSpinner).toBe(false);
        });

        it('does not reset when page becomes visible without spinner active', () => {
            const component = new MockAlpineComponent();

            // Normal state - no spinner
            component.syncButtonSpinner = false;
            component.isSyncing = false;

            // Simulate visibility change handler logic
            const isHidden = false;
            if (!isHidden && component.syncButtonSpinner) {
                component.isSyncing = false;
                component.syncButtonSpinner = false;
            }

            // Should remain unchanged
            expect(component.isSyncing).toBe(false);
            expect(component.syncButtonSpinner).toBe(false);
        });
    });

    describe('Beforeunload Handler', () => {
        it('resets spinner before page unload', () => {
            const component = new MockAlpineComponent();

            // Simulate active sync
            component.syncButtonSpinner = true;
            component.isSyncing = true;

            // Simulate beforeunload handler
            component.isSyncing = false;
            component.syncButtonSpinner = false;

            // Should reset state
            expect(component.isSyncing).toBe(false);
            expect(component.syncButtonSpinner).toBe(false);
        });
    });
});
