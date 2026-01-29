/**
 * Unit tests for TODAY divider functionality
 *
 * Tests the insertGapIndicators function's TODAY divider logic
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { insertGapIndicators } from '../../../static/js/projection.js';

// Helper to create mock event rows
function createMockRow(date, description = 'Event') {
    return {
        id: `event-${date}`,
        event_date: date,
        description,
        amount: 100,
        balance: 1000
    };
}

describe('TODAY Divider Positioning', () => {
    let originalDate;

    beforeEach(() => {
        // Save original Date constructor
        originalDate = globalThis.Date;
    });

    afterEach(() => {
        // Restore original Date
        globalThis.Date = originalDate;
    });

    it('should place TODAY divider after last event of today when there are future events', () => {
        const rows = [
            createMockRow('2026-01-28', 'Event 1'),
            createMockRow('2026-01-28', 'Event 2'),
            createMockRow('2026-01-29', 'Future Event')
        ];

        // Mock Date to return Jan 28, 2026
        globalThis.Date = class extends originalDate {
            constructor(...args) {
                if (args.length === 0) {
                    super('2026-01-28T00:00:00Z');
                } else {
                    super(...args);
                }
            }
            static now() {
                return new originalDate('2026-01-28T00:00:00Z').getTime();
            }
        };

        const result = insertGapIndicators(rows, 7, []);

        // Find the row with showTodayDivider
        const rowWithDivider = result.find(r => r.showTodayDivider);

        expect(rowWithDivider).toBeDefined();
        expect(rowWithDivider.description).toBe('Event 2'); // Last event of today
        expect(rowWithDivider.event_date).toBe('2026-01-28');
        expect(rowWithDivider.todayDate).toBe('2026-01-28');
    });

    it('should place TODAY divider after last event when all events are today or earlier', () => {
        const rows = [
            createMockRow('2026-01-27', 'Yesterday'),
            createMockRow('2026-01-28', 'Today 1'),
            createMockRow('2026-01-28', 'Today 2')
        ];

        globalThis.Date = class extends originalDate {
            constructor(...args) {
                if (args.length === 0) {
                    super('2026-01-28T00:00:00Z');
                } else {
                    super(...args);
                }
            }
            static now() {
                return new originalDate('2026-01-28T00:00:00Z').getTime();
            }
        };

        const result = insertGapIndicators(rows, 7, []);

        const rowWithDivider = result.find(r => r.showTodayDivider);

        expect(rowWithDivider).toBeDefined();
        expect(rowWithDivider.description).toBe('Today 2'); // Last event overall
        expect(rowWithDivider.event_date).toBe('2026-01-28');
    });

    it('should not add TODAY divider when all events are in the future', () => {
        const rows = [
            createMockRow('2026-01-29', 'Tomorrow'),
            createMockRow('2026-01-30', 'Day After')
        ];

        globalThis.Date = class extends originalDate {
            constructor(...args) {
                if (args.length === 0) {
                    super('2026-01-28T00:00:00Z');
                } else {
                    super(...args);
                }
            }
            static now() {
                return new originalDate('2026-01-28T00:00:00Z').getTime();
            }
        };

        const result = insertGapIndicators(rows, 7, []);

        const rowWithDivider = result.find(r => r.showTodayDivider);

        expect(rowWithDivider).toBeUndefined(); // No divider when all events are future
    });

    it('should inject virtual drift rows after TODAY divider', () => {
        const rows = [
            createMockRow('2026-01-28', 'Today Event'),
            createMockRow('2026-01-29', 'Future Event')
        ];

        const virtualDrifts = [
            { id: 'drift-1', description: 'Virtual Drift 1', isDrift: true },
            { id: 'drift-2', description: 'Virtual Drift 2', isDrift: true }
        ];

        globalThis.Date = class extends originalDate {
            constructor(...args) {
                if (args.length === 0) {
                    super('2026-01-28T00:00:00Z');
                } else {
                    super(...args);
                }
            }
            static now() {
                return new originalDate('2026-01-28T00:00:00Z').getTime();
            }
        };

        const result = insertGapIndicators(rows, 7, virtualDrifts);

        // Find index of row with TODAY divider
        const dividerIndex = result.findIndex(r => r.showTodayDivider);
        expect(dividerIndex).toBeGreaterThanOrEqual(0);

        // Next two rows should be virtual drifts
        expect(result[dividerIndex + 1]).toEqual(virtualDrifts[0]);
        expect(result[dividerIndex + 2]).toEqual(virtualDrifts[1]);

        // Then future event should follow
        expect(result[dividerIndex + 3].description).toBe('Future Event');
    });

    it('should handle empty rows array', () => {
        const rows = [];

        globalThis.Date = class extends originalDate {
            constructor(...args) {
                if (args.length === 0) {
                    super('2026-01-28T00:00:00Z');
                } else {
                    super(...args);
                }
            }
            static now() {
                return new originalDate('2026-01-28T00:00:00Z').getTime();
            }
        };

        const result = insertGapIndicators(rows, 7, []);

        expect(result).toEqual([]);
    });

    it('should place TODAY divider correctly with multiple events on same day', () => {
        const rows = [
            createMockRow('2026-01-28', 'Morning'),
            createMockRow('2026-01-28', 'Afternoon'),
            createMockRow('2026-01-28', 'Evening'),
            createMockRow('2026-01-28', 'Balance Adjustment'),
            createMockRow('2026-02-01', 'Next Month')
        ];

        globalThis.Date = class extends originalDate {
            constructor(...args) {
                if (args.length === 0) {
                    super('2026-01-28T00:00:00Z');
                } else {
                    super(...args);
                }
            }
            static now() {
                return new originalDate('2026-01-28T00:00:00Z').getTime();
            }
        };

        const result = insertGapIndicators(rows, 7, []);

        const rowWithDivider = result.find(r => r.showTodayDivider);

        expect(rowWithDivider).toBeDefined();
        expect(rowWithDivider.description).toBe('Balance Adjustment'); // Last of Jan 28
        expect(rowWithDivider.event_date).toBe('2026-01-28');
    });
});

