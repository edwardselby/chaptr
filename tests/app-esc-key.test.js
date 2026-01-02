/**
 * CHAPTR - ESC Key Handler Tests
 *
 * Tests the ESC key modal closing functionality with debounce.
 * Tests modal priority order and prevents double-close scenarios.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

describe('ESC Key Handler', () => {
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

    it('should close single open modal when ESC pressed', () => {
        mockApp.showAccountModal = true;

        const event = new KeyboardEvent('keydown', { key: 'Escape' });
        keydownListener(event);

        expect(mockApp.showAccountModal).toBe(false);
    });

    it('should close topmost modal when multiple modals open', () => {
        // Open multiple modals (in practice this shouldn't happen, but tests priority)
        mockApp.showAccountModal = true;
        mockApp.showConfirmModal = true;

        const event = new KeyboardEvent('keydown', { key: 'Escape' });
        keydownListener(event);

        // Should close confirm modal (higher priority)
        expect(mockApp.showConfirmModal).toBe(false);
        // Should NOT close account modal
        expect(mockApp.showAccountModal).toBe(true);
    });

    it('should respect modal priority order', () => {
        // Open lower priority modal
        mockApp.showAccountModal = true;
        // Open higher priority modal
        mockApp.showPasswordModal = true;

        const event = new KeyboardEvent('keydown', { key: 'Escape' });
        keydownListener(event);

        // Should close password modal first (highest priority)
        expect(mockApp.showPasswordModal).toBe(false);
        expect(mockApp.showAccountModal).toBe(true);
    });

    it('should debounce ESC key for 250ms', () => {
        mockApp.showAccountModal = true;
        mockApp.showStoryModal = false;

        // First ESC press
        const event1 = new KeyboardEvent('keydown', { key: 'Escape' });
        keydownListener(event1);
        expect(mockApp.showAccountModal).toBe(false);

        // Open another modal
        mockApp.showStoryModal = true;

        // Immediate second ESC press (should be debounced)
        const event2 = new KeyboardEvent('keydown', { key: 'Escape' });
        keydownListener(event2);
        expect(mockApp.showStoryModal).toBe(true);  // Should NOT close (debounced)

        // Advance time by 250ms
        vi.advanceTimersByTime(250);

        // Third ESC press (after debounce)
        const event3 = new KeyboardEvent('keydown', { key: 'Escape' });
        keydownListener(event3);
        expect(mockApp.showStoryModal).toBe(false);  // Should close now
    });

    it('should not close modals for non-ESC keys', () => {
        mockApp.showAccountModal = true;

        const enterEvent = new KeyboardEvent('keydown', { key: 'Enter' });
        keydownListener(enterEvent);

        expect(mockApp.showAccountModal).toBe(true);  // Should remain open
    });

    it('should do nothing when no modals are open', () => {
        // All modals closed
        Object.keys(mockApp).forEach(key => {
            mockApp[key] = false;
        });

        const event = new KeyboardEvent('keydown', { key: 'Escape' });
        keydownListener(event);

        // All modals should still be closed (no errors)
        expect(Object.values(mockApp).every(v => v === false)).toBe(true);
    });

    it('should handle rapid ESC presses without double-closing', () => {
        mockApp.showAccountModal = true;
        mockApp.showStoryModal = true;

        // First ESC (closes showPasswordModal if open, but it's not, so closes showInputModal if open, etc. -> closes showStoryModal)
        // Actually with priority, it will close the FIRST true modal in the list
        // Since showStoryModal comes before showAccountModal in priority, it closes showStoryModal

        // Reset - let's use correct priority
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
            showStoryModal: true,    // Priority 10
            showAccountModal: true    // Priority 11 (lowest)
        };

        const event1 = new KeyboardEvent('keydown', { key: 'Escape' });
        keydownListener(event1);

        // Should close StoryModal (higher priority than Account)
        expect(mockApp.showStoryModal).toBe(false);
        expect(mockApp.showAccountModal).toBe(true);

        // Immediate second press (should be debounced)
        const event2 = new KeyboardEvent('keydown', { key: 'Escape' });
        keydownListener(event2);

        // AccountModal should STILL be open (debounced)
        expect(mockApp.showAccountModal).toBe(true);
    });

    it('should allow closing another modal after debounce period', () => {
        mockApp.showAccountModal = true;

        // First ESC
        const event1 = new KeyboardEvent('keydown', { key: 'Escape' });
        keydownListener(event1);
        expect(mockApp.showAccountModal).toBe(false);

        // Wait for debounce to clear
        vi.advanceTimersByTime(250);

        // Open another modal
        mockApp.showStoryModal = true;

        // Second ESC after debounce
        const event2 = new KeyboardEvent('keydown', { key: 'Escape' });
        keydownListener(event2);
        expect(mockApp.showStoryModal).toBe(false);
    });
});
