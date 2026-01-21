/**
 * CHAPTR - Balance Utilities Unit Tests
 *
 * Tests for balance calculation functions:
 * - Event filtering for accounts
 * - Balance calculation at specific dates
 * - 30-day projection calculations
 * - Drift calculations
 * - Adjustment event creation
 */

import { describe, it, expect } from 'vitest';
import {
    filterEventsForAccount,
    sumEventAmounts,
    calculateAccountBalanceAtDate,
    calculateAccountProjection30Days,
    calculateDrift,
    isDriftSignificant,
    createAdjustmentEvent
} from '../../../static/js/modules/balance-utils.js';


// ============================================================================
// Test Helpers
// ============================================================================

function generateUUID() {
    return crypto.randomUUID();
}

function createAccount(overrides = {}) {
    return {
        id: generateUUID(),
        name: 'Test Account',
        currency: 'GBP',
        current_balance: 1000,
        balance_updated_at: null,
        ...overrides
    };
}

function createEvent(accountId, overrides = {}) {
    return {
        id: generateUUID(),
        account_id: accountId,
        description: 'Test Event',
        amount: 100,
        currency: 'GBP',
        event_date: '2025-01-15',
        is_baseline: false,
        is_hypothetical: false,
        is_opening_balance: false,
        is_auto_adjustment: false,
        ...overrides
    };
}


// ============================================================================
// filterEventsForAccount Tests
// ============================================================================

describe('filterEventsForAccount', () => {
    describe('basic filtering', () => {
        it('filters events by account ID', () => {
            const accountId = generateUUID();
            const otherAccountId = generateUUID();
            const events = [
                createEvent(accountId, { event_date: '2025-01-10', amount: 100 }),
                createEvent(otherAccountId, { event_date: '2025-01-10', amount: 200 }),
                createEvent(accountId, { event_date: '2025-01-15', amount: 300 })
            ];

            const result = filterEventsForAccount(events, accountId, null, '2025-01-20');

            expect(result.length).toBe(2);
            expect(result.every(e => e.account_id === accountId)).toBe(true);
        });

        it('filters events by date range (exclusive start, inclusive end)', () => {
            const accountId = generateUUID();
            const events = [
                createEvent(accountId, { event_date: '2025-01-05', amount: 100 }),
                createEvent(accountId, { event_date: '2025-01-10', amount: 200 }),  // exactly at start - excluded
                createEvent(accountId, { event_date: '2025-01-15', amount: 300 }),
                createEvent(accountId, { event_date: '2025-01-20', amount: 400 }),  // exactly at end - included
                createEvent(accountId, { event_date: '2025-01-25', amount: 500 })
            ];

            const result = filterEventsForAccount(events, accountId, '2025-01-10', '2025-01-20');

            expect(result.length).toBe(2);
            expect(result[0].event_date).toBe('2025-01-15');
            expect(result[1].event_date).toBe('2025-01-20');
        });

        it('includes all dates when startDate is null', () => {
            const accountId = generateUUID();
            const events = [
                createEvent(accountId, { event_date: '2024-01-01', amount: 100 }),
                createEvent(accountId, { event_date: '2025-01-15', amount: 200 }),
                createEvent(accountId, { event_date: '2025-01-20', amount: 300 })
            ];

            const result = filterEventsForAccount(events, accountId, null, '2025-01-20');

            expect(result.length).toBe(3);
        });

        it('returns empty array when no events match', () => {
            const accountId = generateUUID();
            const events = [
                createEvent(generateUUID(), { event_date: '2025-01-15' })
            ];

            const result = filterEventsForAccount(events, accountId, null, '2025-01-20');

            expect(result.length).toBe(0);
        });
    });

    describe('optional exclusions', () => {
        it('excludes opening balance events when option set', () => {
            const accountId = generateUUID();
            const events = [
                createEvent(accountId, { event_date: '2025-01-10', is_opening_balance: true, amount: 1000 }),
                createEvent(accountId, { event_date: '2025-01-15', is_opening_balance: false, amount: 200 })
            ];

            const result = filterEventsForAccount(
                events,
                accountId,
                null,
                '2025-01-20',
                { excludeOpeningBalance: true }
            );

            expect(result.length).toBe(1);
            expect(result[0].amount).toBe(200);
        });

        it('includes opening balance events by default', () => {
            const accountId = generateUUID();
            const events = [
                createEvent(accountId, { event_date: '2025-01-10', is_opening_balance: true, amount: 1000 }),
                createEvent(accountId, { event_date: '2025-01-15', is_opening_balance: false, amount: 200 })
            ];

            const result = filterEventsForAccount(events, accountId, null, '2025-01-20');

            expect(result.length).toBe(2);
        });

        it('excludes hypothetical events when option set', () => {
            const accountId = generateUUID();
            const events = [
                createEvent(accountId, { event_date: '2025-01-10', is_hypothetical: true, amount: 500 }),
                createEvent(accountId, { event_date: '2025-01-15', is_hypothetical: false, amount: 200 })
            ];

            const result = filterEventsForAccount(
                events,
                accountId,
                null,
                '2025-01-20',
                { excludeHypothetical: true }
            );

            expect(result.length).toBe(1);
            expect(result[0].amount).toBe(200);
        });

        it('applies multiple exclusion options', () => {
            const accountId = generateUUID();
            const events = [
                createEvent(accountId, { event_date: '2025-01-05', is_opening_balance: true, amount: 1000 }),
                createEvent(accountId, { event_date: '2025-01-10', is_hypothetical: true, amount: 500 }),
                createEvent(accountId, { event_date: '2025-01-15', amount: 200 })
            ];

            const result = filterEventsForAccount(
                events,
                accountId,
                null,
                '2025-01-20',
                { excludeOpeningBalance: true, excludeHypothetical: true }
            );

            expect(result.length).toBe(1);
            expect(result[0].amount).toBe(200);
        });
    });
});


// ============================================================================
// sumEventAmounts Tests
// ============================================================================

describe('sumEventAmounts', () => {
    it('sums positive amounts', () => {
        const events = [
            { amount: 100 },
            { amount: 200 },
            { amount: 300 }
        ];

        expect(sumEventAmounts(events)).toBe(600);
    });

    it('sums negative amounts', () => {
        const events = [
            { amount: -100 },
            { amount: -50 }
        ];

        expect(sumEventAmounts(events)).toBe(-150);
    });

    it('sums mixed positive and negative amounts', () => {
        const events = [
            { amount: 500 },
            { amount: -200 },
            { amount: 100 }
        ];

        expect(sumEventAmounts(events)).toBe(400);
    });

    it('returns 0 for empty array', () => {
        expect(sumEventAmounts([])).toBe(0);
    });

    it('handles string amounts', () => {
        const events = [
            { amount: '100.50' },
            { amount: '200.25' }
        ];

        expect(sumEventAmounts(events)).toBe(300.75);
    });

    it('handles null/undefined amounts as 0', () => {
        const events = [
            { amount: 100 },
            { amount: null },
            { amount: undefined },
            { amount: 50 }
        ];

        expect(sumEventAmounts(events)).toBe(150);
    });
});


// ============================================================================
// calculateAccountBalanceAtDate Tests
// ============================================================================

describe('calculateAccountBalanceAtDate', () => {
    describe('without balance_updated_at', () => {
        it('sums all events up to target date', () => {
            const account = createAccount({ balance_updated_at: null });
            const events = [
                createEvent(account.id, { event_date: '2025-01-05', amount: 100 }),
                createEvent(account.id, { event_date: '2025-01-10', amount: 200 }),
                createEvent(account.id, { event_date: '2025-01-15', amount: 300 }),
                createEvent(account.id, { event_date: '2025-01-25', amount: 400 })  // after target
            ];

            const balance = calculateAccountBalanceAtDate(account, events, '2025-01-20');

            expect(balance).toBe(600);  // 100 + 200 + 300
        });

        it('includes opening balance events', () => {
            const account = createAccount({ balance_updated_at: null });
            const events = [
                createEvent(account.id, { event_date: '2025-01-01', amount: 1000, is_opening_balance: true }),
                createEvent(account.id, { event_date: '2025-01-15', amount: -50 })
            ];

            const balance = calculateAccountBalanceAtDate(account, events, '2025-01-20');

            expect(balance).toBe(950);  // 1000 - 50
        });

        it('returns 0 when no events', () => {
            const account = createAccount({ balance_updated_at: null });

            const balance = calculateAccountBalanceAtDate(account, [], '2025-01-20');

            expect(balance).toBe(0);
        });
    });

    describe('with balance_updated_at', () => {
        it('starts from current_balance and adds events after update', () => {
            const account = createAccount({
                current_balance: 5000,
                balance_updated_at: '2025-01-10T10:00:00Z'
            });
            const events = [
                createEvent(account.id, { event_date: '2025-01-05', amount: 1000 }),  // before update - ignored
                createEvent(account.id, { event_date: '2025-01-10', amount: 200 }),   // same date - ignored (start is exclusive)
                createEvent(account.id, { event_date: '2025-01-15', amount: 300 }),   // after update - included
                createEvent(account.id, { event_date: '2025-01-18', amount: -100 })   // after update - included
            ];

            const balance = calculateAccountBalanceAtDate(account, events, '2025-01-20');

            expect(balance).toBe(5200);  // 5000 + 300 - 100
        });

        it('excludes opening balance events when starting from manual update', () => {
            const account = createAccount({
                current_balance: 5000,
                balance_updated_at: '2025-01-10T10:00:00Z'
            });
            const events = [
                createEvent(account.id, { event_date: '2025-01-15', amount: 1000, is_opening_balance: true }),
                createEvent(account.id, { event_date: '2025-01-16', amount: 200 })
            ];

            const balance = calculateAccountBalanceAtDate(account, events, '2025-01-20');

            expect(balance).toBe(5200);  // 5000 + 200 (opening balance excluded)
        });

        it('returns current_balance when no events after update', () => {
            const account = createAccount({
                current_balance: 5000,
                balance_updated_at: '2025-01-10T10:00:00Z'
            });
            const events = [
                createEvent(account.id, { event_date: '2025-01-05', amount: 1000 })  // before update
            ];

            const balance = calculateAccountBalanceAtDate(account, events, '2025-01-20');

            expect(balance).toBe(5000);
        });
    });

    describe('edge cases', () => {
        it('returns 0 for null account', () => {
            expect(calculateAccountBalanceAtDate(null, [], '2025-01-20')).toBe(0);
        });

        it('returns 0 for undefined account', () => {
            expect(calculateAccountBalanceAtDate(undefined, [], '2025-01-20')).toBe(0);
        });

        it('handles accounts with string current_balance', () => {
            const account = createAccount({
                current_balance: '5000.50',
                balance_updated_at: '2025-01-10T10:00:00Z'
            });
            const events = [
                createEvent(account.id, { event_date: '2025-01-15', amount: 100.25 })
            ];

            const balance = calculateAccountBalanceAtDate(account, events, '2025-01-20');

            expect(balance).toBe(5100.75);
        });

        it('ignores events for other accounts', () => {
            const account = createAccount({ balance_updated_at: null });
            const otherAccountId = generateUUID();
            const events = [
                createEvent(account.id, { event_date: '2025-01-10', amount: 100 }),
                createEvent(otherAccountId, { event_date: '2025-01-15', amount: 999 })
            ];

            const balance = calculateAccountBalanceAtDate(account, events, '2025-01-20');

            expect(balance).toBe(100);
        });
    });
});


// ============================================================================
// calculateAccountProjection30Days Tests
// ============================================================================

describe('calculateAccountProjection30Days', () => {
    it('projects balance 30 days from today', () => {
        const account = createAccount({ current_balance: 1000 });
        const today = '2025-01-15';
        const events = [
            createEvent(account.id, { event_date: '2025-01-20', amount: 200 }),  // within 30 days
            createEvent(account.id, { event_date: '2025-02-10', amount: 300 }),  // within 30 days
            createEvent(account.id, { event_date: '2025-02-20', amount: 500 })   // after 30 days - excluded
        ];

        const projection = calculateAccountProjection30Days(account, events, today);

        expect(projection).toBe(1500);  // 1000 + 200 + 300
    });

    it('excludes hypothetical events', () => {
        const account = createAccount({ current_balance: 1000 });
        const today = '2025-01-15';
        const events = [
            createEvent(account.id, { event_date: '2025-01-20', amount: 200, is_hypothetical: false }),
            createEvent(account.id, { event_date: '2025-01-25', amount: 500, is_hypothetical: true })
        ];

        const projection = calculateAccountProjection30Days(account, events, today);

        expect(projection).toBe(1200);  // 1000 + 200 (hypothetical excluded)
    });

    it('excludes events before today', () => {
        const account = createAccount({ current_balance: 1000 });
        const today = '2025-01-15';
        const events = [
            createEvent(account.id, { event_date: '2025-01-10', amount: 100 }),  // before today - excluded
            createEvent(account.id, { event_date: '2025-01-15', amount: 200 }),  // today - excluded (start is exclusive)
            createEvent(account.id, { event_date: '2025-01-20', amount: 300 })   // after today - included
        ];

        const projection = calculateAccountProjection30Days(account, events, today);

        expect(projection).toBe(1300);  // 1000 + 300
    });

    it('returns current balance when no future events', () => {
        const account = createAccount({ current_balance: 5000 });

        const projection = calculateAccountProjection30Days(account, [], '2025-01-15');

        expect(projection).toBe(5000);
    });

    it('returns 0 for null account', () => {
        expect(calculateAccountProjection30Days(null, [], '2025-01-15')).toBe(0);
    });
});


// ============================================================================
// calculateDrift Tests
// ============================================================================

describe('calculateDrift', () => {
    it('returns positive drift when actual exceeds projected', () => {
        expect(calculateDrift(1000, 1200)).toBe(200);
    });

    it('returns negative drift when actual is less than projected', () => {
        expect(calculateDrift(1000, 800)).toBe(-200);
    });

    it('returns 0 when actual equals projected', () => {
        expect(calculateDrift(1000, 1000)).toBe(0);
    });

    it('handles negative balances', () => {
        expect(calculateDrift(-500, -600)).toBe(-100);  // owe more
        expect(calculateDrift(-500, -300)).toBe(200);   // owe less
    });

    it('handles decimal values', () => {
        expect(calculateDrift(100.50, 125.75)).toBe(25.25);
    });
});


// ============================================================================
// isDriftSignificant Tests
// ============================================================================

describe('isDriftSignificant', () => {
    it('returns true for positive drift', () => {
        expect(isDriftSignificant(100)).toBe(true);
    });

    it('returns true for negative drift', () => {
        expect(isDriftSignificant(-100)).toBe(true);
    });

    it('returns false for zero drift', () => {
        expect(isDriftSignificant(0)).toBe(false);
    });

    it('returns true for small drift', () => {
        expect(isDriftSignificant(0.01)).toBe(true);
        expect(isDriftSignificant(-0.01)).toBe(true);
    });
});


// ============================================================================
// createAdjustmentEvent Tests
// ============================================================================

describe('createAdjustmentEvent', () => {
    it('creates adjustment event with correct structure', () => {
        const accountId = generateUUID();
        const mockGenerateId = () => 'test-uuid-123';

        const event = createAdjustmentEvent(
            accountId,
            150.50,
            '2025-01-15',
            'GBP',
            mockGenerateId
        );

        expect(event.id).toBe('test-uuid-123');
        expect(event.account_id).toBe(accountId);
        expect(event.amount).toBe(150.50);
        expect(event.currency).toBe('GBP');
        expect(event.event_date).toBe('2025-01-15');
        expect(event.description).toBe('[auto] Balance adjustment');
    });

    it('sets correct flags for adjustment event', () => {
        const event = createAdjustmentEvent(
            generateUUID(),
            100,
            '2025-01-15',
            'USD',
            generateUUID
        );

        expect(event.story_id).toBeNull();
        expect(event.is_baseline).toBe(true);
        expect(event.is_hypothetical).toBe(false);
        expect(event.is_opening_balance).toBe(false);
        expect(event.is_auto_adjustment).toBe(true);
        expect(event._queued_op).toBe('create');
        expect(event._optimistic).toBe(true);
    });

    it('handles negative drift (reduction)', () => {
        const event = createAdjustmentEvent(
            generateUUID(),
            -250,
            '2025-01-15',
            'EUR',
            generateUUID
        );

        expect(event.amount).toBe(-250);
    });

    it('sets timestamps', () => {
        const beforeCreate = new Date().toISOString();

        const event = createAdjustmentEvent(
            generateUUID(),
            100,
            '2025-01-15',
            'GBP',
            generateUUID
        );

        const afterCreate = new Date().toISOString();

        expect(event.created_at >= beforeCreate).toBe(true);
        expect(event.created_at <= afterCreate).toBe(true);
        expect(event.updated_at).toBe(event.created_at);
    });
});


// ============================================================================
// Integration Scenarios
// ============================================================================

describe('Balance Utils Integration Scenarios', () => {
    describe('reconciliation workflow', () => {
        it('calculates drift and creates adjustment for underspending', () => {
            // Account projected to have £1000, actually has £1200 (spent less)
            const account = createAccount({
                current_balance: 1000,
                balance_updated_at: null
            });
            const events = [
                createEvent(account.id, { event_date: '2025-01-01', amount: 1000, is_opening_balance: true })
            ];

            const projectedBalance = calculateAccountBalanceAtDate(account, events, '2025-01-15');
            const actualBalance = 1200;  // User reports actual balance
            const drift = calculateDrift(projectedBalance, actualBalance);

            expect(projectedBalance).toBe(1000);
            expect(drift).toBe(200);
            expect(isDriftSignificant(drift)).toBe(true);

            // Create adjustment event
            const adjustment = createAdjustmentEvent(
                account.id,
                drift,
                '2025-01-15',
                account.currency,
                generateUUID
            );

            expect(adjustment.amount).toBe(200);
        });

        it('calculates drift and creates adjustment for overspending', () => {
            // Account projected to have £1000, actually has £800 (spent more)
            const account = createAccount({
                current_balance: 1000,
                balance_updated_at: null
            });
            const events = [
                createEvent(account.id, { event_date: '2025-01-01', amount: 1000, is_opening_balance: true })
            ];

            const projectedBalance = calculateAccountBalanceAtDate(account, events, '2025-01-15');
            const actualBalance = 800;
            const drift = calculateDrift(projectedBalance, actualBalance);

            expect(projectedBalance).toBe(1000);
            expect(drift).toBe(-200);
            expect(isDriftSignificant(drift)).toBe(true);

            const adjustment = createAdjustmentEvent(
                account.id,
                drift,
                '2025-01-15',
                account.currency,
                generateUUID
            );

            expect(adjustment.amount).toBe(-200);
        });

        it('detects no drift when balances match', () => {
            const account = createAccount({
                current_balance: 1000,
                balance_updated_at: '2025-01-01T00:00:00Z'
            });

            const projectedBalance = calculateAccountBalanceAtDate(account, [], '2025-01-15');
            const actualBalance = 1000;
            const drift = calculateDrift(projectedBalance, actualBalance);

            expect(projectedBalance).toBe(1000);
            expect(drift).toBe(0);
            expect(isDriftSignificant(drift)).toBe(false);
        });
    });

    describe('credit card scenario', () => {
        it('calculates drift correctly for credit card (negative balances)', () => {
            // Credit card: projected -£500 owed, actually -£600 owed (spent more)
            const account = createAccount({
                current_balance: -500,
                balance_updated_at: '2025-01-01T00:00:00Z'
            });

            const projectedBalance = calculateAccountBalanceAtDate(account, [], '2025-01-15');
            const actualBalance = -600;
            const drift = calculateDrift(projectedBalance, actualBalance);

            expect(projectedBalance).toBe(-500);
            expect(drift).toBe(-100);  // Drift is negative (owe more than expected)
        });
    });
});
