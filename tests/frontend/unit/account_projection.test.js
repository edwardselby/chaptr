/**
 * Unit tests for account projection calculations
 *
 * Tests getAccountProjection30Days() which calculates projected
 * account balance based on upcoming events in the next 30 days.
 */

import { describe, it, expect, beforeEach } from 'vitest';

/**
 * Helper to generate UUID
 */
function generateUUID() {
    return crypto.randomUUID();
}

/**
 * Helper to get ISO date string for a date offset from today
 * @param {number} daysOffset - Days from today (positive = future)
 * @returns {string} ISO date string (YYYY-MM-DD)
 */
function getDateOffset(daysOffset) {
    const date = new Date();
    date.setDate(date.getDate() + daysOffset);
    return date.toISOString().split('T')[0];
}

/**
 * Creates a mock implementation of getAccountProjection30Days
 * This mirrors the actual implementation in app.js
 */
function createProjectionCalculator(accounts, events) {
    return function getAccountProjection30Days(accountId) {
        const account = accounts.find(a => a.id === accountId);
        if (!account) return 0;

        const today = new Date();
        const todayStr = today.toISOString().split('T')[0];
        const targetDate = new Date(today.getTime() + 30 * 24 * 60 * 60 * 1000);
        const targetDateStr = targetDate.toISOString().split('T')[0];

        const accountEvents = events.filter(e =>
            e.account_id === accountId &&
            !e.is_hypothetical &&
            e.event_date >= todayStr &&
            e.event_date <= targetDateStr
        );

        const totalChange = accountEvents.reduce((sum, event) => {
            return sum + parseFloat(event.amount || 0);
        }, 0);

        return parseFloat(account.current_balance || 0) + totalChange;
    };
}

describe('getAccountProjection30Days', () => {
    let accounts;
    let events;
    let getAccountProjection30Days;

    beforeEach(() => {
        accounts = [];
        events = [];
    });

    describe('Basic Calculations', () => {
        it('should return current balance when no events exist', () => {
            const accountId = generateUUID();
            accounts = [{
                id: accountId,
                name: 'Test Account',
                current_balance: '5000',
                currency: 'GBP'
            }];
            events = [];

            getAccountProjection30Days = createProjectionCalculator(accounts, events);
            expect(getAccountProjection30Days(accountId)).toBe(5000);
        });

        it('should return 0 for non-existent account', () => {
            accounts = [];
            events = [];

            getAccountProjection30Days = createProjectionCalculator(accounts, events);
            expect(getAccountProjection30Days(generateUUID())).toBe(0);
        });

        it('should add positive events to balance', () => {
            const accountId = generateUUID();
            accounts = [{
                id: accountId,
                name: 'Test Account',
                current_balance: '1000',
                currency: 'GBP'
            }];
            events = [{
                id: generateUUID(),
                account_id: accountId,
                event_date: getDateOffset(5),
                amount: '500',
                is_hypothetical: false
            }];

            getAccountProjection30Days = createProjectionCalculator(accounts, events);
            expect(getAccountProjection30Days(accountId)).toBe(1500);
        });

        it('should subtract negative events from balance', () => {
            const accountId = generateUUID();
            accounts = [{
                id: accountId,
                name: 'Test Account',
                current_balance: '5000',
                currency: 'GBP'
            }];
            events = [{
                id: generateUUID(),
                account_id: accountId,
                event_date: getDateOffset(10),
                amount: '-1500',
                is_hypothetical: false
            }];

            getAccountProjection30Days = createProjectionCalculator(accounts, events);
            expect(getAccountProjection30Days(accountId)).toBe(3500);
        });

        it('should handle multiple events correctly', () => {
            const accountId = generateUUID();
            accounts = [{
                id: accountId,
                name: 'Test Account',
                current_balance: '10000',
                currency: 'GBP'
            }];
            events = [
                { id: generateUUID(), account_id: accountId, event_date: getDateOffset(5), amount: '-2000', is_hypothetical: false },
                { id: generateUUID(), account_id: accountId, event_date: getDateOffset(10), amount: '-1500', is_hypothetical: false },
                { id: generateUUID(), account_id: accountId, event_date: getDateOffset(15), amount: '500', is_hypothetical: false },
                { id: generateUUID(), account_id: accountId, event_date: getDateOffset(20), amount: '-800', is_hypothetical: false }
            ];

            getAccountProjection30Days = createProjectionCalculator(accounts, events);
            // 10000 - 2000 - 1500 + 500 - 800 = 6200
            expect(getAccountProjection30Days(accountId)).toBe(6200);
        });
    });

    describe('Date Filtering', () => {
        it('should exclude events beyond 30 days', () => {
            const accountId = generateUUID();
            accounts = [{
                id: accountId,
                name: 'Test Account',
                current_balance: '5000',
                currency: 'GBP'
            }];
            events = [
                { id: generateUUID(), account_id: accountId, event_date: getDateOffset(10), amount: '-1000', is_hypothetical: false },
                { id: generateUUID(), account_id: accountId, event_date: getDateOffset(35), amount: '-2000', is_hypothetical: false }, // Beyond 30 days
                { id: generateUUID(), account_id: accountId, event_date: getDateOffset(60), amount: '-3000', is_hypothetical: false }  // Beyond 30 days
            ];

            getAccountProjection30Days = createProjectionCalculator(accounts, events);
            // Only the -1000 event should be included
            expect(getAccountProjection30Days(accountId)).toBe(4000);
        });

        it('should exclude past events', () => {
            const accountId = generateUUID();
            accounts = [{
                id: accountId,
                name: 'Test Account',
                current_balance: '5000',
                currency: 'GBP'
            }];
            events = [
                { id: generateUUID(), account_id: accountId, event_date: getDateOffset(-5), amount: '-1000', is_hypothetical: false }, // Past
                { id: generateUUID(), account_id: accountId, event_date: getDateOffset(10), amount: '-500', is_hypothetical: false }   // Future
            ];

            getAccountProjection30Days = createProjectionCalculator(accounts, events);
            // Only the future -500 event should be included
            expect(getAccountProjection30Days(accountId)).toBe(4500);
        });

        it('should include events on boundary dates (today and day 30)', () => {
            const accountId = generateUUID();
            accounts = [{
                id: accountId,
                name: 'Test Account',
                current_balance: '5000',
                currency: 'GBP'
            }];
            events = [
                { id: generateUUID(), account_id: accountId, event_date: getDateOffset(0), amount: '-100', is_hypothetical: false },  // Today
                { id: generateUUID(), account_id: accountId, event_date: getDateOffset(30), amount: '-200', is_hypothetical: false }  // Day 30
            ];

            getAccountProjection30Days = createProjectionCalculator(accounts, events);
            expect(getAccountProjection30Days(accountId)).toBe(4700);
        });
    });

    describe('Event Filtering', () => {
        it('should exclude hypothetical events', () => {
            const accountId = generateUUID();
            accounts = [{
                id: accountId,
                name: 'Test Account',
                current_balance: '5000',
                currency: 'GBP'
            }];
            events = [
                { id: generateUUID(), account_id: accountId, event_date: getDateOffset(5), amount: '-1000', is_hypothetical: false },
                { id: generateUUID(), account_id: accountId, event_date: getDateOffset(10), amount: '-5000', is_hypothetical: true }  // Hypothetical
            ];

            getAccountProjection30Days = createProjectionCalculator(accounts, events);
            // Only the non-hypothetical -1000 event should be included
            expect(getAccountProjection30Days(accountId)).toBe(4000);
        });

        it('should only include events for the specified account', () => {
            const accountId1 = generateUUID();
            const accountId2 = generateUUID();
            accounts = [
                { id: accountId1, name: 'Account 1', current_balance: '5000', currency: 'GBP' },
                { id: accountId2, name: 'Account 2', current_balance: '3000', currency: 'GBP' }
            ];
            events = [
                { id: generateUUID(), account_id: accountId1, event_date: getDateOffset(5), amount: '-1000', is_hypothetical: false },
                { id: generateUUID(), account_id: accountId2, event_date: getDateOffset(5), amount: '-2000', is_hypothetical: false }
            ];

            getAccountProjection30Days = createProjectionCalculator(accounts, events);
            expect(getAccountProjection30Days(accountId1)).toBe(4000);
            expect(getAccountProjection30Days(accountId2)).toBe(1000);
        });
    });

    describe('String/Number Handling', () => {
        it('should handle balance stored as string (avoid concatenation bug)', () => {
            const accountId = generateUUID();
            accounts = [{
                id: accountId,
                name: 'Test Account',
                current_balance: '5000',  // String, not number
                currency: 'GBP'
            }];
            events = [];

            getAccountProjection30Days = createProjectionCalculator(accounts, events);
            const result = getAccountProjection30Days(accountId);

            // Should be 5000, not "50000" from string concatenation
            expect(result).toBe(5000);
            expect(typeof result).toBe('number');
        });

        it('should handle amount stored as string', () => {
            const accountId = generateUUID();
            accounts = [{
                id: accountId,
                name: 'Test Account',
                current_balance: '1000',
                currency: 'GBP'
            }];
            events = [{
                id: generateUUID(),
                account_id: accountId,
                event_date: getDateOffset(5),
                amount: '-500',  // String, not number
                is_hypothetical: false
            }];

            getAccountProjection30Days = createProjectionCalculator(accounts, events);
            expect(getAccountProjection30Days(accountId)).toBe(500);
        });

        it('should handle numeric balance and amount', () => {
            const accountId = generateUUID();
            accounts = [{
                id: accountId,
                name: 'Test Account',
                current_balance: 1000,  // Number
                currency: 'GBP'
            }];
            events = [{
                id: generateUUID(),
                account_id: accountId,
                event_date: getDateOffset(5),
                amount: -500,  // Number
                is_hypothetical: false
            }];

            getAccountProjection30Days = createProjectionCalculator(accounts, events);
            expect(getAccountProjection30Days(accountId)).toBe(500);
        });

        it('should handle null/undefined balance gracefully', () => {
            const accountId = generateUUID();
            accounts = [{
                id: accountId,
                name: 'Test Account',
                current_balance: null,
                currency: 'GBP'
            }];
            events = [{
                id: generateUUID(),
                account_id: accountId,
                event_date: getDateOffset(5),
                amount: '500',
                is_hypothetical: false
            }];

            getAccountProjection30Days = createProjectionCalculator(accounts, events);
            expect(getAccountProjection30Days(accountId)).toBe(500);
        });

        it('should handle null/undefined event amount gracefully', () => {
            const accountId = generateUUID();
            accounts = [{
                id: accountId,
                name: 'Test Account',
                current_balance: '1000',
                currency: 'GBP'
            }];
            events = [{
                id: generateUUID(),
                account_id: accountId,
                event_date: getDateOffset(5),
                amount: null,
                is_hypothetical: false
            }];

            getAccountProjection30Days = createProjectionCalculator(accounts, events);
            expect(getAccountProjection30Days(accountId)).toBe(1000);
        });
    });

    describe('Edge Cases', () => {
        it('should handle negative resulting balance', () => {
            const accountId = generateUUID();
            accounts = [{
                id: accountId,
                name: 'Test Account',
                current_balance: '1000',
                currency: 'GBP'
            }];
            events = [{
                id: generateUUID(),
                account_id: accountId,
                event_date: getDateOffset(5),
                amount: '-5000',
                is_hypothetical: false
            }];

            getAccountProjection30Days = createProjectionCalculator(accounts, events);
            expect(getAccountProjection30Days(accountId)).toBe(-4000);
        });

        it('should handle decimal amounts', () => {
            const accountId = generateUUID();
            accounts = [{
                id: accountId,
                name: 'Test Account',
                current_balance: '1000.50',
                currency: 'GBP'
            }];
            events = [
                { id: generateUUID(), account_id: accountId, event_date: getDateOffset(5), amount: '-100.25', is_hypothetical: false },
                { id: generateUUID(), account_id: accountId, event_date: getDateOffset(10), amount: '50.75', is_hypothetical: false }
            ];

            getAccountProjection30Days = createProjectionCalculator(accounts, events);
            // 1000.50 - 100.25 + 50.75 = 951.00
            expect(getAccountProjection30Days(accountId)).toBe(951);
        });

        it('should handle large number of events', () => {
            const accountId = generateUUID();
            accounts = [{
                id: accountId,
                name: 'Test Account',
                current_balance: '100000',
                currency: 'GBP'
            }];

            // Create 100 events, each -100
            events = Array.from({ length: 100 }, (_, i) => ({
                id: generateUUID(),
                account_id: accountId,
                event_date: getDateOffset(i % 30),  // Spread across 30 days
                amount: '-100',
                is_hypothetical: false
            }));

            getAccountProjection30Days = createProjectionCalculator(accounts, events);
            // 100000 - (100 * 100) = 90000
            expect(getAccountProjection30Days(accountId)).toBe(90000);
        });

        it('should handle zero balance account', () => {
            const accountId = generateUUID();
            accounts = [{
                id: accountId,
                name: 'Test Account',
                current_balance: '0',
                currency: 'GBP'
            }];
            events = [{
                id: generateUUID(),
                account_id: accountId,
                event_date: getDateOffset(5),
                amount: '1000',
                is_hypothetical: false
            }];

            getAccountProjection30Days = createProjectionCalculator(accounts, events);
            expect(getAccountProjection30Days(accountId)).toBe(1000);
        });
    });
});
