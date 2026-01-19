/**
 * Unit tests for sync notification formatting
 *
 * Tests the formatSyncResult function that creates entity-aware
 * notification messages for sync operations.
 */

import { describe, it, expect, beforeEach } from 'vitest';

/**
 * Mock component with formatSyncResult function
 * Mirrors the implementation in app.js
 */
class MockSyncComponent {
    /**
     * Format sync result for notification display
     *
     * Returns entity-aware message when single type, generic "changes" for mixed types.
     * Examples: "Synced 3 events", "Synced 1 account", "Synced 5 changes"
     *
     * @param {Object} result - Sync result with applied count and appliedByType breakdown
     * @param {number} result.applied - Total number of applied changes
     * @param {Object} result.appliedByType - Breakdown by entity type
     * @returns {string} - Formatted message for notification
     */
    formatSyncResult(result) {
        if (!result.applied || result.applied === 0) {
            return 'Already in sync';
        }

        const typeLabels = {
            event: { singular: 'event', plural: 'events' },
            account: { singular: 'account', plural: 'accounts' },
            story: { singular: 'story', plural: 'stories' },
            recurring_rule: { singular: 'rule', plural: 'rules' },
            settings: { singular: 'settings', plural: 'settings' }
        };

        const types = Object.keys(result.appliedByType || {});

        // Single entity type: show specific label
        if (types.length === 1) {
            const type = types[0];
            const count = result.appliedByType[type];
            const labels = typeLabels[type] || { singular: type, plural: type + 's' };
            const label = count === 1 ? labels.singular : labels.plural;
            return `Synced ${count} ${label}`;
        }

        // Multiple types: use generic "changes"
        return `Synced ${result.applied} changes`;
    }
}

describe('Sync Notifications: formatSyncResult', () => {
    let component;

    beforeEach(() => {
        component = new MockSyncComponent();
    });

    describe('No changes', () => {
        it('should return "Already in sync" when applied is 0', () => {
            const result = { applied: 0, appliedByType: {} };
            expect(component.formatSyncResult(result)).toBe('Already in sync');
        });

        it('should return "Already in sync" when applied is undefined', () => {
            const result = {};
            expect(component.formatSyncResult(result)).toBe('Already in sync');
        });

        it('should return "Already in sync" when applied is null', () => {
            const result = { applied: null, appliedByType: {} };
            expect(component.formatSyncResult(result)).toBe('Already in sync');
        });
    });

    describe('Single entity type - events', () => {
        it('should return "Synced 1 event" for single event', () => {
            const result = { applied: 1, appliedByType: { event: 1 } };
            expect(component.formatSyncResult(result)).toBe('Synced 1 event');
        });

        it('should return "Synced 3 events" for multiple events', () => {
            const result = { applied: 3, appliedByType: { event: 3 } };
            expect(component.formatSyncResult(result)).toBe('Synced 3 events');
        });
    });

    describe('Single entity type - accounts', () => {
        it('should return "Synced 1 account" for single account', () => {
            const result = { applied: 1, appliedByType: { account: 1 } };
            expect(component.formatSyncResult(result)).toBe('Synced 1 account');
        });

        it('should return "Synced 2 accounts" for multiple accounts', () => {
            const result = { applied: 2, appliedByType: { account: 2 } };
            expect(component.formatSyncResult(result)).toBe('Synced 2 accounts');
        });
    });

    describe('Single entity type - stories', () => {
        it('should return "Synced 1 story" for single story', () => {
            const result = { applied: 1, appliedByType: { story: 1 } };
            expect(component.formatSyncResult(result)).toBe('Synced 1 story');
        });

        it('should return "Synced 4 stories" for multiple stories', () => {
            const result = { applied: 4, appliedByType: { story: 4 } };
            expect(component.formatSyncResult(result)).toBe('Synced 4 stories');
        });
    });

    describe('Single entity type - recurring rules', () => {
        it('should return "Synced 1 rule" for single recurring rule', () => {
            const result = { applied: 1, appliedByType: { recurring_rule: 1 } };
            expect(component.formatSyncResult(result)).toBe('Synced 1 rule');
        });

        it('should return "Synced 5 rules" for multiple recurring rules', () => {
            const result = { applied: 5, appliedByType: { recurring_rule: 5 } };
            expect(component.formatSyncResult(result)).toBe('Synced 5 rules');
        });
    });

    describe('Single entity type - settings', () => {
        it('should return "Synced 1 settings" for settings', () => {
            const result = { applied: 1, appliedByType: { settings: 1 } };
            expect(component.formatSyncResult(result)).toBe('Synced 1 settings');
        });
    });

    describe('Multiple entity types', () => {
        it('should return "Synced X changes" for events and accounts', () => {
            const result = { applied: 5, appliedByType: { event: 3, account: 2 } };
            expect(component.formatSyncResult(result)).toBe('Synced 5 changes');
        });

        it('should return "Synced X changes" for three entity types', () => {
            const result = {
                applied: 10,
                appliedByType: { event: 5, account: 3, story: 2 }
            };
            expect(component.formatSyncResult(result)).toBe('Synced 10 changes');
        });

        it('should return "Synced X changes" for all entity types', () => {
            const result = {
                applied: 15,
                appliedByType: {
                    event: 8,
                    account: 3,
                    story: 2,
                    recurring_rule: 1,
                    settings: 1
                }
            };
            expect(component.formatSyncResult(result)).toBe('Synced 15 changes');
        });
    });

    describe('Unknown entity types', () => {
        it('should handle unknown entity type with default pluralization', () => {
            const result = { applied: 2, appliedByType: { widget: 2 } };
            expect(component.formatSyncResult(result)).toBe('Synced 2 widgets');
        });

        it('should handle unknown entity type singular', () => {
            const result = { applied: 1, appliedByType: { widget: 1 } };
            expect(component.formatSyncResult(result)).toBe('Synced 1 widget');
        });
    });

    describe('Edge cases', () => {
        it('should handle missing appliedByType', () => {
            const result = { applied: 3 };
            expect(component.formatSyncResult(result)).toBe('Synced 3 changes');
        });

        it('should handle empty appliedByType with applied count', () => {
            const result = { applied: 3, appliedByType: {} };
            expect(component.formatSyncResult(result)).toBe('Synced 3 changes');
        });
    });
});
