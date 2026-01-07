/**
 * ESC Key Handler - Extended Edge Cases
 *
 * Extends the basic ESC key handler tests (app-esc-key.test.js) with additional
 * edge cases and integration scenarios. Tests focus on scenarios that could
 * occur in production but are less common.
 *
 * Key scenarios:
 * - All modals closed simultaneously
 * - ESC during debounce window with state changes
 * - Modal state consistency after multiple operations
 * - Edge cases with timing and state transitions
 *
 * Priority: 💡 MEDIUM - Additional coverage for production edge cases
 * Coverage Target: Edge cases not covered by basic tests
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

describe('ESC Key Handler - Extended Edge Cases', () => {
    let mockApp;
    let keydownListener;
    let debounceTimer;

    beforeEach(() => {
        // Mock the Alpine.js app data
        mockApp = {
            showPasswordModal: false,
            showInputModal: false,
            showConfirmModal: false,
            showConflictModal: false,
            showDatabaseToolsModal: false,
            showBalanceModal: false,
            showHelpModal: false,
            showUserModal: false,
            showEventModal: false,
            showStoryModal: false,
            showAccountModal: false
        };

        // Simulate the ESC key handler logic from app.js init()
        debounceTimer = null;
        keydownListener = (event) => {
            if (event.key === 'Escape' && !debounceTimer) {
                // Find and close the topmost modal
                const modalPriority = [
                    'showPasswordModal',
                    'showInputModal',
                    'showConfirmModal',
                    'showConflictModal',
                    'showDatabaseToolsModal',
                    'showBalanceModal',
                    'showHelpModal',
                    'showUserModal',
                    'showEventModal',
                    'showStoryModal',
                    'showAccountModal'
                ];

                for (const modalName of modalPriority) {
                    if (mockApp[modalName] === true) {
                        mockApp[modalName] = false;
                        break; // Only close one modal per ESC press
                    }
                }

                // Debounce 250ms
                debounceTimer = setTimeout(() => {
                    debounceTimer = null;
                }, 250);
            }
        };

        vi.useFakeTimers();
    });

    afterEach(() => {
        vi.restoreAllMocks();
        vi.useRealTimers();
    });

    // ==================== STATE CONSISTENCY ====================

    it('should maintain state consistency when closing multiple modals sequentially', () => {
        // Open 3 modals
        mockApp.showAccountModal = true;
        mockApp.showStoryModal = true;
        mockApp.showEventModal = true;

        // Close first modal (EventModal - priority 9)
        const event1 = new KeyboardEvent('keydown', { key: 'Escape' });
        keydownListener(event1);
        expect(mockApp.showEventModal).toBe(false);
        expect(mockApp.showStoryModal).toBe(true);
        expect(mockApp.showAccountModal).toBe(true);

        // Wait for debounce
        vi.advanceTimersByTime(250);

        // Close second modal (StoryModal - priority 10)
        const event2 = new KeyboardEvent('keydown', { key: 'Escape' });
        keydownListener(event2);
        expect(mockApp.showEventModal).toBe(false);
        expect(mockApp.showStoryModal).toBe(false);
        expect(mockApp.showAccountModal).toBe(true);

        // Wait for debounce
        vi.advanceTimersByTime(250);

        // Close third modal (AccountModal - priority 11)
        const event3 = new KeyboardEvent('keydown', { key: 'Escape' });
        keydownListener(event3);
        expect(mockApp.showEventModal).toBe(false);
        expect(mockApp.showStoryModal).toBe(false);
        expect(mockApp.showAccountModal).toBe(false);
    });

    // ==================== DEBOUNCE EDGE CASES ====================

    it('should ignore ESC if debounce timer is active even if modal state changes', () => {
        mockApp.showAccountModal = true;

        // First ESC press
        const event1 = new KeyboardEvent('keydown', { key: 'Escape' });
        keydownListener(event1);
        expect(mockApp.showAccountModal).toBe(false);

        // Change modal state while debounce active
        mockApp.showStoryModal = true;
        mockApp.showEventModal = true;

        // Second ESC immediately (should be ignored)
        const event2 = new KeyboardEvent('keydown', { key: 'Escape' });
        keydownListener(event2);

        // Both modals should still be open (debounced)
        expect(mockApp.showStoryModal).toBe(true);
        expect(mockApp.showEventModal).toBe(true);

        // Advance time by 100ms (still within debounce window)
        vi.advanceTimersByTime(100);

        // Third ESC (still debounced)
        const event3 = new KeyboardEvent('keydown', { key: 'Escape' });
        keydownListener(event3);
        expect(mockApp.showStoryModal).toBe(true);
        expect(mockApp.showEventModal).toBe(true);
    });

    // ==================== KEY EVENT EDGE CASES ====================

    it('should handle case-sensitive key check correctly', () => {
        mockApp.showAccountModal = true;

        // Try lowercase "escape" (should NOT work - KeyboardEvent.key is case-sensitive)
        const event1 = new KeyboardEvent('keydown', { key: 'escape' });
        keydownListener(event1);
        expect(mockApp.showAccountModal).toBe(true);

        // Try correct case "Escape"
        const event2 = new KeyboardEvent('keydown', { key: 'Escape' });
        keydownListener(event2);
        expect(mockApp.showAccountModal).toBe(false);
    });

    it('should ignore ESC when debounce timer exists (even if just started)', () => {
        mockApp.showAccountModal = true;
        mockApp.showStoryModal = true;

        // First ESC
        const event1 = new KeyboardEvent('keydown', { key: 'Escape' });
        keydownListener(event1);

        // AccountModal closed based on priority (actually, showStoryModal is priority 10, showAccountModal is 11)
        // So StoryModal should close first
        expect(mockApp.showStoryModal).toBe(false);
        expect(mockApp.showAccountModal).toBe(true);

        // Immediately try another ESC (debounce timer active)
        const event2 = new KeyboardEvent('keydown', { key: 'Escape' });
        keydownListener(event2);

        // AccountModal should NOT close (debounced)
        expect(mockApp.showAccountModal).toBe(true);

        // Advance only 1ms (debounce timer still active)
        vi.advanceTimersByTime(1);

        // Try again (still debounced)
        const event3 = new KeyboardEvent('keydown', { key: 'Escape' });
        keydownListener(event3);
        expect(mockApp.showAccountModal).toBe(true);
    });

    // ==================== MODAL PRIORITY EDGE CASES ====================

    it('should close highest priority modal when all modals are open', () => {
        // Open ALL modals
        Object.keys(mockApp).forEach(key => {
            mockApp[key] = true;
        });

        const event = new KeyboardEvent('keydown', { key: 'Escape' });
        keydownListener(event);

        // Should close Password modal (highest priority)
        expect(mockApp.showPasswordModal).toBe(false);

        // All others should still be open
        expect(mockApp.showInputModal).toBe(true);
        expect(mockApp.showConfirmModal).toBe(true);
        expect(mockApp.showAccountModal).toBe(true);
    });
});
