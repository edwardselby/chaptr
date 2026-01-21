/**
 * CHAPTR - Balance Utilities
 *
 * Pure functions for balance calculations and drift detection.
 * These functions have zero state dependencies and can be tested in isolation.
 */

// ============================================================================
// Event Filtering
// ============================================================================

/**
 * Filter events for a specific account within a date range.
 *
 * @param {Array} events - Array of event objects
 * @param {string} accountId - Account UUID to filter by
 * @param {string|null} startDate - Start date (exclusive) in YYYY-MM-DD format, or null for no lower bound
 * @param {string} endDate - End date (inclusive) in YYYY-MM-DD format
 * @param {Object} options - Filter options
 * @param {boolean} options.excludeOpeningBalance - Exclude is_opening_balance events (default: false)
 * @param {boolean} options.excludeHypothetical - Exclude is_hypothetical events (default: false)
 * @returns {Array} Filtered events
 */
export function filterEventsForAccount(events, accountId, startDate, endDate, options = {}) {
    const { excludeOpeningBalance = false, excludeHypothetical = false } = options;

    return events.filter(e => {
        // Must match account
        if (e.account_id !== accountId) return false;

        // Date range: startDate < event_date <= endDate
        if (startDate !== null && e.event_date <= startDate) return false;
        if (e.event_date > endDate) return false;

        // Optional exclusions
        if (excludeOpeningBalance && e.is_opening_balance) return false;
        if (excludeHypothetical && e.is_hypothetical) return false;

        return true;
    });
}

/**
 * Sum event amounts.
 *
 * @param {Array} events - Array of event objects with amount property
 * @returns {number} Total sum of all event amounts
 */
export function sumEventAmounts(events) {
    return events.reduce((sum, event) => sum + parseFloat(event.amount || 0), 0);
}


// ============================================================================
// Balance Calculations
// ============================================================================

/**
 * Calculate account balance at a specific date.
 *
 * Two calculation modes:
 * 1. If account has balance_updated_at: Start from current_balance, add events AFTER that date
 * 2. Otherwise: Sum all events up to and including target date
 *
 * @param {Object} account - Account object with id, current_balance, balance_updated_at
 * @param {Array} events - Array of all events
 * @param {string} targetDate - Date to calculate balance for (YYYY-MM-DD)
 * @returns {number} Projected balance at target date
 */
export function calculateAccountBalanceAtDate(account, events, targetDate) {
    if (!account) return 0;

    // If balance has been manually updated, start from that snapshot
    if (account.balance_updated_at) {
        const balanceDate = account.balance_updated_at.split('T')[0]; // YYYY-MM-DD
        const startBalance = parseFloat(account.current_balance || 0);

        // Get events AFTER the balance update, up to target date
        const relevantEvents = filterEventsForAccount(
            events,
            account.id,
            balanceDate,  // startDate (exclusive)
            targetDate,   // endDate (inclusive)
            { excludeOpeningBalance: true }
        );

        return startBalance + sumEventAmounts(relevantEvents);
    }

    // No manual update - calculate from all events up to target date
    const relevantEvents = filterEventsForAccount(
        events,
        account.id,
        null,        // No start date constraint
        targetDate,
        { excludeOpeningBalance: false }
    );

    return sumEventAmounts(relevantEvents);
}

/**
 * Calculate 30-day projection for an account.
 *
 * Projects the account balance 30 days into the future based on
 * upcoming non-hypothetical events.
 *
 * @param {Object} account - Account object with id, current_balance
 * @param {Array} events - Array of all events
 * @param {string} todayStr - Today's date in YYYY-MM-DD format
 * @returns {number} Projected balance in 30 days
 */
export function calculateAccountProjection30Days(account, events, todayStr) {
    if (!account) return 0;

    // Calculate target date (30 days from today)
    const today = new Date(todayStr);
    const targetDate = new Date(today.getTime() + 30 * 24 * 60 * 60 * 1000);
    const targetDateStr = targetDate.toISOString().split('T')[0];

    // Get non-hypothetical events in the 30-day window
    const relevantEvents = filterEventsForAccount(
        events,
        account.id,
        todayStr,      // startDate (exclusive) - only future events
        targetDateStr, // endDate (inclusive)
        { excludeHypothetical: true }
    );

    const startBalance = parseFloat(account.current_balance || 0);
    return startBalance + sumEventAmounts(relevantEvents);
}


// ============================================================================
// Drift Calculations
// ============================================================================

/**
 * Calculate balance drift (difference between actual and projected).
 *
 * Drift = Actual Balance - Projected Balance
 * - Positive drift: Account has more money than expected
 * - Negative drift: Account has less money than expected
 *
 * @param {number} projectedBalance - Expected balance from projection
 * @param {number} actualBalance - Actual balance (already signed)
 * @returns {number} Drift amount
 */
export function calculateDrift(projectedBalance, actualBalance) {
    return actualBalance - projectedBalance;
}

/**
 * Determine if drift is significant enough to warrant an adjustment.
 *
 * A drift of exactly 0 means no adjustment is needed.
 *
 * @param {number} drift - Drift amount
 * @returns {boolean} True if drift requires adjustment
 */
export function isDriftSignificant(drift) {
    return drift !== 0;
}

/**
 * Create an adjustment event to reconcile drift.
 *
 * @param {string} accountId - Account UUID
 * @param {number} drift - Drift amount to adjust
 * @param {string} eventDate - Date for the adjustment event (YYYY-MM-DD)
 * @param {string} currency - Currency code (e.g., 'GBP')
 * @param {function} generateId - Function to generate UUID
 * @returns {Object} Adjustment event object
 */
export function createAdjustmentEvent(accountId, drift, eventDate, currency, generateId) {
    const now = new Date().toISOString();

    return {
        id: generateId(),
        account_id: accountId,
        story_id: null,
        description: '[auto] Balance adjustment',
        amount: drift,
        currency: currency,
        rate_to_base: 1,
        event_date: eventDate,
        is_baseline: true,
        is_hypothetical: false,
        is_opening_balance: false,
        is_auto_adjustment: true,
        recurring_rule_id: null,
        created_at: now,
        updated_at: now,
        _queued_op: 'create',
        _optimistic: true
    };
}
