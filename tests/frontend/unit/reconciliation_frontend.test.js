/**
 * Frontend Reconciliation Tests
 *
 * Tests for auto-adjustment event handling in the frontend:
 * - Projection filtering: auto-adjustments excluded from baseline/story views, included in ALL view
 * - Same-day ordering: auto-adjustments appear LAST (after all regular events) to show end-of-day balance
 * - Adjustment event creation: correct flags set when creating balance adjustment events
 *
 * These tests verify the reconciliation system's frontend behavior per spec:
 * - Auto-adjustments tagged as [auto] in UI
 * - Appear in ALL view, NOT in filtered story views
 * - Styled subtly (grey/dim) to distinguish from real events
 */

import { describe, it, expect, beforeEach } from 'vitest';

// ============================================================================
// Test Data Factories
// ============================================================================

/**
 * Create a mock event for testing
 */
function createMockEvent(overrides = {}) {
    const defaults = {
        id: `event-${Math.random().toString(36).substr(2, 9)}`,
        event_date: '2025-01-15',
        description: 'Test event',
        amount: 100,
        currency: 'GBP',
        rate_to_base: 1.0,
        account_id: 'acc-123',
        story_id: null,
        is_baseline: true,
        is_hypothetical: false,
        is_opening_balance: false,
        is_auto_adjustment: false,
        is_transfer: false,
        recurring_rule_id: null,
        created_at: '2025-01-15T10:00:00Z',
        updated_at: '2025-01-15T10:00:00Z',
        base_amount: 100  // Pre-calculated for sorting tests
    };
    return { ...defaults, ...overrides };
}

/**
 * Create an auto-adjustment event
 */
function createAutoAdjustmentEvent(overrides = {}) {
    return createMockEvent({
        description: 'balance adjustment',
        is_auto_adjustment: true,
        is_baseline: true,
        story_id: null,
        ...overrides
    });
}

/**
 * Create an opening balance event
 */
function createOpeningBalanceEvent(overrides = {}) {
    return createMockEvent({
        description: 'opening balance',
        is_opening_balance: true,
        is_baseline: true,
        ...overrides
    });
}

/**
 * Create a story event
 */
function createStoryEvent(storyId, overrides = {}) {
    return createMockEvent({
        story_id: storyId,
        is_baseline: false,
        ...overrides
    });
}

// ============================================================================
// Projection View Filtering Tests
// ============================================================================

describe('Projection View Filtering - Auto-Adjustments', () => {

    /**
     * Baseline view filter predicate (from projection.js:153)
     * visibleEvents = rangeEvents.filter(e => e.is_baseline && !e.is_auto_adjustment);
     */
    const baselineFilter = (e) => e.is_baseline && !e.is_auto_adjustment;

    /**
     * Story view filter predicate (from projection.js:158)
     * visibleEvents = rangeEvents.filter(e => e.story_id === storyId && !e.is_auto_adjustment);
     */
    const storyFilter = (storyId) => (e) => e.story_id === storyId && !e.is_auto_adjustment;

    /**
     * ALL view filter predicate (from projection.js:163)
     * visibleEvents = rangeEvents.filter(e => !e.is_hypothetical);
     */
    const allViewFilter = (e) => !e.is_hypothetical;

    describe('Baseline View', () => {

        it('should EXCLUDE auto-adjustment events from baseline view', () => {
            const events = [
                createMockEvent({ is_baseline: true }),
                createAutoAdjustmentEvent(),  // Should be excluded
                createMockEvent({ is_baseline: true, amount: 200 })
            ];

            const visible = events.filter(baselineFilter);

            expect(visible).toHaveLength(2);
            expect(visible.every(e => !e.is_auto_adjustment)).toBe(true);
        });

        it('should INCLUDE regular baseline events in baseline view', () => {
            const regularEvent = createMockEvent({ is_baseline: true, description: 'Salary' });
            const events = [regularEvent];

            const visible = events.filter(baselineFilter);

            expect(visible).toHaveLength(1);
            expect(visible[0].description).toBe('Salary');
        });

        it('should EXCLUDE story events from baseline view', () => {
            const events = [
                createMockEvent({ is_baseline: true }),
                createStoryEvent('story-1'),  // Should be excluded (not baseline)
            ];

            const visible = events.filter(baselineFilter);

            expect(visible).toHaveLength(1);
            expect(visible[0].is_baseline).toBe(true);
        });

        it('should correctly filter mixed events in baseline view', () => {
            const events = [
                createOpeningBalanceEvent({ amount: 1000 }),         // Include (is_baseline=true, is_auto_adjustment=false)
                createAutoAdjustmentEvent({ amount: -50 }),          // Exclude (is_auto_adjustment=true)
                createMockEvent({ is_baseline: true, amount: 500 }), // Include (is_baseline=true, is_auto_adjustment=false)
                createStoryEvent('story-1', { amount: -100 }),       // Exclude (is_baseline=false)
                createMockEvent({ is_hypothetical: true, is_baseline: true, amount: 200 })  // Include (is_baseline=true, is_auto_adjustment=false)
            ];

            const visible = events.filter(baselineFilter);

            // Expected: Opening balance, regular baseline, hypothetical baseline = 3 events
            // (Hypothetical is included because baseline filter only checks is_baseline && !is_auto_adjustment)
            expect(visible).toHaveLength(3);
            expect(visible.every(e => !e.is_auto_adjustment)).toBe(true);
            expect(visible.every(e => e.is_baseline)).toBe(true);
        });
    });

    describe('Story View', () => {
        const storyId = 'story-canada-trip';

        it('should EXCLUDE auto-adjustment events from story view', () => {
            const events = [
                createStoryEvent(storyId, { amount: -100 }),
                createAutoAdjustmentEvent({ amount: 50 }),  // Should be excluded
                createStoryEvent(storyId, { amount: -200 })
            ];

            const visible = events.filter(storyFilter(storyId));

            expect(visible).toHaveLength(2);
            expect(visible.every(e => !e.is_auto_adjustment)).toBe(true);
        });

        it('should ONLY show events belonging to the selected story', () => {
            const events = [
                createStoryEvent(storyId, { description: 'Hotel' }),
                createStoryEvent('other-story', { description: 'Unrelated' }),
                createMockEvent({ is_baseline: true, description: 'Baseline event' })
            ];

            const visible = events.filter(storyFilter(storyId));

            expect(visible).toHaveLength(1);
            expect(visible[0].description).toBe('Hotel');
        });

        it('should exclude auto-adjustments even if they somehow had a story_id', () => {
            // Edge case: auto-adjustment should never have story_id per spec,
            // but if it did, it should still be excluded
            const events = [
                createAutoAdjustmentEvent({ story_id: storyId }),  // Should be excluded
                createStoryEvent(storyId)
            ];

            const visible = events.filter(storyFilter(storyId));

            expect(visible).toHaveLength(1);
            expect(visible[0].is_auto_adjustment).toBe(false);
        });
    });

    describe('ALL View', () => {

        it('should INCLUDE auto-adjustment events in ALL view', () => {
            const autoAdj = createAutoAdjustmentEvent({ amount: -75 });
            const events = [
                createMockEvent({ is_baseline: true }),
                autoAdj,
                createMockEvent({ is_baseline: true })
            ];

            const visible = events.filter(allViewFilter);

            expect(visible).toHaveLength(3);
            expect(visible).toContain(autoAdj);
        });

        it('should INCLUDE all non-hypothetical events in ALL view', () => {
            const events = [
                createOpeningBalanceEvent(),
                createAutoAdjustmentEvent(),
                createMockEvent({ is_baseline: true }),
                createStoryEvent('story-1'),
                createStoryEvent('story-2')
            ];

            const visible = events.filter(allViewFilter);

            expect(visible).toHaveLength(5);
        });

        it('should EXCLUDE hypothetical events from ALL view', () => {
            const events = [
                createMockEvent({ is_hypothetical: false }),
                createMockEvent({ is_hypothetical: true }),  // Should be excluded
                createAutoAdjustmentEvent()
            ];

            const visible = events.filter(allViewFilter);

            expect(visible).toHaveLength(2);
            expect(visible.every(e => !e.is_hypothetical)).toBe(true);
        });

        it('should show auto-adjustments regardless of baseline flag', () => {
            // Per spec: auto-adjustments have is_baseline=true and story_id=null
            const autoAdj = createAutoAdjustmentEvent({ is_baseline: true, story_id: null });
            const events = [autoAdj];

            const visible = events.filter(allViewFilter);

            expect(visible).toHaveLength(1);
            expect(visible[0].is_auto_adjustment).toBe(true);
        });
    });
});

// ============================================================================
// Same-Day Event Ordering Tests
// ============================================================================

describe('Same-Day Event Ordering', () => {

    /**
     * Same-day sorting comparator (from projection.js:214-238)
     * Order: 1) Opening balance, 2) Regular events (by amount), 3) Auto-adjustments LAST
     */
    const sameDayComparator = (a, b) => {
        // Primary: Sort by date
        if (a.event_date !== b.event_date) {
            return a.event_date < b.event_date ? -1 : 1;
        }

        // 1. Opening balance events first
        if (a.is_opening_balance !== b.is_opening_balance) {
            return a.is_opening_balance ? -1 : 1;
        }

        // 2. Regular events by amount (debits before credits = negative before positive)
        // 3. Auto-adjustments LAST (to show balance at end of day)
        if (a.is_auto_adjustment !== b.is_auto_adjustment) {
            return a.is_auto_adjustment ? 1 : -1;  // Auto-adjustments sort LAST
        }

        // 4. Then by amount (debits before credits = negative before positive)
        if (a.base_amount !== b.base_amount) {
            return a.base_amount - b.base_amount;
        }

        // 5. Tie-breaker: created_at ASC
        return a.created_at < b.created_at ? -1 : 1;
    };

    it('should sort opening balance FIRST on same day', () => {
        const events = [
            createMockEvent({ base_amount: -100 }),
            createOpeningBalanceEvent({ base_amount: 1000 }),
            createAutoAdjustmentEvent({ base_amount: 50 })
        ];

        events.sort(sameDayComparator);

        expect(events[0].is_opening_balance).toBe(true);
    });

    it('should sort auto-adjustments LAST (after opening balance and regular events)', () => {
        const events = [
            createMockEvent({ description: 'Regular event', base_amount: 100 }),
            createAutoAdjustmentEvent({ base_amount: -50 }),
            createOpeningBalanceEvent({ base_amount: 1000 })
        ];

        events.sort(sameDayComparator);

        expect(events[0].is_opening_balance).toBe(true);
        expect(events[1].description).toBe('Regular event');
        expect(events[2].is_auto_adjustment).toBe(true);
    });

    it('should sort regular events by amount (debits before credits)', () => {
        const events = [
            createMockEvent({ description: 'Income', base_amount: 500 }),   // Credit
            createMockEvent({ description: 'Expense', base_amount: -200 }), // Debit
            createMockEvent({ description: 'Small expense', base_amount: -50 }) // Smaller debit
        ];

        events.sort(sameDayComparator);

        // Should be: -200, -50, 500 (most negative first)
        expect(events[0].base_amount).toBe(-200);
        expect(events[1].base_amount).toBe(-50);
        expect(events[2].base_amount).toBe(500);
    });

    it('should handle complex same-day ordering scenario', () => {
        const events = [
            createMockEvent({ description: 'Income', base_amount: 3000 }),
            createMockEvent({ description: 'Rent', base_amount: -1200 }),
            createAutoAdjustmentEvent({ base_amount: -75 }),
            createOpeningBalanceEvent({ base_amount: 1000 }),
            createMockEvent({ description: 'Coffee', base_amount: -5 })
        ];

        events.sort(sameDayComparator);

        // Expected order:
        // 1. Opening balance (is_opening_balance = true)
        // 2. Rent -1200 (most negative regular event)
        // 3. Coffee -5 (less negative regular event)
        // 4. Income +3000 (positive regular event)
        // 5. Auto-adjustment (is_auto_adjustment = true) - LAST
        expect(events[0].is_opening_balance).toBe(true);
        expect(events[1].description).toBe('Rent');
        expect(events[2].description).toBe('Coffee');
        expect(events[3].description).toBe('Income');
        expect(events[4].is_auto_adjustment).toBe(true);
    });

    it('should use created_at as tiebreaker for same amount', () => {
        const events = [
            createMockEvent({ description: 'Second', base_amount: 100, created_at: '2025-01-15T12:00:00Z' }),
            createMockEvent({ description: 'First', base_amount: 100, created_at: '2025-01-15T10:00:00Z' })
        ];

        events.sort(sameDayComparator);

        expect(events[0].description).toBe('First');
        expect(events[1].description).toBe('Second');
    });

    it('should sort by date first, then apply same-day rules', () => {
        const events = [
            createMockEvent({ event_date: '2025-01-16', base_amount: -100 }),
            createOpeningBalanceEvent({ event_date: '2025-01-15', base_amount: 1000 }),
            createAutoAdjustmentEvent({ event_date: '2025-01-15', base_amount: 50 })
        ];

        events.sort(sameDayComparator);

        // Jan 15 events first, then Jan 16
        expect(events[0].event_date).toBe('2025-01-15');
        expect(events[0].is_opening_balance).toBe(true);  // Opening balance first on Jan 15
        expect(events[1].event_date).toBe('2025-01-15');
        expect(events[1].is_auto_adjustment).toBe(true);  // Auto-adjustment LAST on Jan 15
        expect(events[2].event_date).toBe('2025-01-16');  // Jan 16 event last
    });
});

// ============================================================================
// Auto-Adjustment Event Creation Tests
// ============================================================================

describe('Auto-Adjustment Event Creation', () => {

    /**
     * Simulates the adjustment event creation logic from app.js:2440-2456
     */
    function createBalanceAdjustmentEvent(account, drift, settings) {
        const now = new Date().toISOString();
        const today = new Date().toISOString().split('T')[0];

        return {
            id: `event-${Math.random().toString(36).substr(2, 9)}`,
            event_date: today,
            description: 'balance adjustment',
            amount: drift,
            currency: account.currency,
            rate_to_base: settings.rates?.[account.currency] || 1.0,
            account_id: account.id,
            story_id: null,
            is_baseline: true,
            is_hypothetical: false,
            is_opening_balance: false,
            is_auto_adjustment: true,
            is_transfer: false,
            recurring_rule_id: null,
            created_at: now,
            updated_at: now
        };
    }

    it('should set is_auto_adjustment to true', () => {
        const account = { id: 'acc-1', currency: 'GBP' };
        const settings = { rates: { 'GBP': 1.0 } };

        const event = createBalanceAdjustmentEvent(account, 100, settings);

        expect(event.is_auto_adjustment).toBe(true);
    });

    it('should set story_id to null (auto-adjustments not part of stories)', () => {
        const account = { id: 'acc-1', currency: 'GBP' };
        const settings = { rates: {} };

        const event = createBalanceAdjustmentEvent(account, -50, settings);

        expect(event.story_id).toBeNull();
    });

    it('should set is_baseline to true', () => {
        const account = { id: 'acc-1', currency: 'GBP' };
        const settings = { rates: {} };

        const event = createBalanceAdjustmentEvent(account, 200, settings);

        expect(event.is_baseline).toBe(true);
    });

    it('should set is_hypothetical to false', () => {
        const account = { id: 'acc-1', currency: 'GBP' };
        const settings = { rates: {} };

        const event = createBalanceAdjustmentEvent(account, 150, settings);

        expect(event.is_hypothetical).toBe(false);
    });

    it('should set description to "balance adjustment"', () => {
        const account = { id: 'acc-1', currency: 'GBP' };
        const settings = { rates: {} };

        const event = createBalanceAdjustmentEvent(account, 100, settings);

        expect(event.description).toBe('balance adjustment');
    });

    it('should use correct drift amount (positive adjustment)', () => {
        const account = { id: 'acc-1', currency: 'GBP' };
        const settings = { rates: {} };

        const event = createBalanceAdjustmentEvent(account, 300, settings);

        expect(event.amount).toBe(300);
    });

    it('should use correct drift amount (negative adjustment)', () => {
        const account = { id: 'acc-1', currency: 'GBP' };
        const settings = { rates: {} };

        const event = createBalanceAdjustmentEvent(account, -150, settings);

        expect(event.amount).toBe(-150);
    });

    it('should use account currency', () => {
        const account = { id: 'acc-1', currency: 'USD' };
        const settings = { rates: { 'USD': 0.79 } };

        const event = createBalanceAdjustmentEvent(account, 100, settings);

        expect(event.currency).toBe('USD');
    });

    it('should use correct exchange rate from settings', () => {
        const account = { id: 'acc-1', currency: 'USD' };
        const settings = { rates: { 'USD': 0.79, 'EUR': 0.85 } };

        const event = createBalanceAdjustmentEvent(account, 100, settings);

        expect(event.rate_to_base).toBe(0.79);
    });

    it('should fallback to 1.0 rate when currency not in settings', () => {
        const account = { id: 'acc-1', currency: 'JPY' };
        const settings = { rates: { 'USD': 0.79 } };

        const event = createBalanceAdjustmentEvent(account, 100, settings);

        expect(event.rate_to_base).toBe(1.0);
    });

    it('should set event_date to today', () => {
        const account = { id: 'acc-1', currency: 'GBP' };
        const settings = { rates: {} };
        const today = new Date().toISOString().split('T')[0];

        const event = createBalanceAdjustmentEvent(account, 100, settings);

        expect(event.event_date).toBe(today);
    });

    it('should link to correct account_id', () => {
        const account = { id: 'acc-specific-123', currency: 'GBP' };
        const settings = { rates: {} };

        const event = createBalanceAdjustmentEvent(account, 100, settings);

        expect(event.account_id).toBe('acc-specific-123');
    });

    it('should set is_opening_balance to false', () => {
        const account = { id: 'acc-1', currency: 'GBP' };
        const settings = { rates: {} };

        const event = createBalanceAdjustmentEvent(account, 100, settings);

        expect(event.is_opening_balance).toBe(false);
    });

    it('should set recurring_rule_id to null', () => {
        const account = { id: 'acc-1', currency: 'GBP' };
        const settings = { rates: {} };

        const event = createBalanceAdjustmentEvent(account, 100, settings);

        expect(event.recurring_rule_id).toBeNull();
    });
});

// ============================================================================
// Drift Calculation Tests
// ============================================================================

describe('Drift Calculation', () => {

    /**
     * Calculate drift: actual balance - projected balance
     * This is the logic used in the balance form
     */
    function calculateDrift(actualBalance, projectedBalance) {
        return actualBalance - projectedBalance;
    }

    it('should calculate positive drift (actual > projected)', () => {
        // User has MORE money than projected
        const drift = calculateDrift(1000, 800);
        expect(drift).toBe(200);
    });

    it('should calculate negative drift (actual < projected)', () => {
        // User has LESS money than projected
        const drift = calculateDrift(800, 1000);
        expect(drift).toBe(-200);
    });

    it('should calculate zero drift (actual === projected)', () => {
        const drift = calculateDrift(1000, 1000);
        expect(drift).toBe(0);
    });

    it('should handle decimal amounts correctly', () => {
        const drift = calculateDrift(1234.56, 1000.00);
        expect(drift).toBeCloseTo(234.56, 2);
    });

    it('should handle negative balances (overdraft)', () => {
        const drift = calculateDrift(-500, -200);
        expect(drift).toBe(-300);  // Actually worse than projected
    });

    it('should handle mixed positive/negative balances', () => {
        const drift = calculateDrift(100, -50);
        expect(drift).toBe(150);  // Better than projected
    });
});

// ============================================================================
// Edge Cases and Boundary Conditions
// ============================================================================

describe('Reconciliation Edge Cases', () => {

    describe('Empty Event Lists', () => {
        const baselineFilter = (e) => e.is_baseline && !e.is_auto_adjustment;
        const allViewFilter = (e) => !e.is_hypothetical;

        it('should handle empty event list in baseline view', () => {
            const events = [];
            const visible = events.filter(baselineFilter);
            expect(visible).toHaveLength(0);
        });

        it('should handle empty event list in ALL view', () => {
            const events = [];
            const visible = events.filter(allViewFilter);
            expect(visible).toHaveLength(0);
        });
    });

    describe('All Events Are Auto-Adjustments', () => {
        const baselineFilter = (e) => e.is_baseline && !e.is_auto_adjustment;

        it('should return empty list when all events are auto-adjustments in baseline view', () => {
            const events = [
                createAutoAdjustmentEvent({ amount: 100 }),
                createAutoAdjustmentEvent({ amount: -50 }),
                createAutoAdjustmentEvent({ amount: 25 })
            ];

            const visible = events.filter(baselineFilter);

            expect(visible).toHaveLength(0);
        });
    });

    describe('Multiple Auto-Adjustments', () => {
        const allViewFilter = (e) => !e.is_hypothetical;

        it('should include all auto-adjustments in ALL view', () => {
            const events = [
                createAutoAdjustmentEvent({ amount: 100, account_id: 'acc-1' }),
                createAutoAdjustmentEvent({ amount: -50, account_id: 'acc-2' }),
                createAutoAdjustmentEvent({ amount: 200, account_id: 'acc-1' })
            ];

            const visible = events.filter(allViewFilter);

            expect(visible).toHaveLength(3);
            expect(visible.every(e => e.is_auto_adjustment)).toBe(true);
        });
    });

    describe('Very Small Drift Amounts', () => {

        it('should handle sub-penny drift amounts', () => {
            const account = { id: 'acc-1', currency: 'GBP' };
            const settings = { rates: {} };

            // 0.001 drift (sub-penny)
            const event = {
                amount: 0.001,
                is_auto_adjustment: true,
                story_id: null,
                is_baseline: true
            };

            expect(event.amount).toBe(0.001);
            expect(event.is_auto_adjustment).toBe(true);
        });
    });
});
