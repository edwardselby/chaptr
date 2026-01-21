/**
 * CHAPTR - Formatting Utilities
 *
 * Pure functions for data formatting and transformation.
 * These functions have zero state dependencies and can be tested in isolation.
 */

// ============================================================================
// Auto-Sync Formatting
// ============================================================================

/**
 * Normalize auto-sync interval to seconds.
 *
 * Handles migration from milliseconds (old format) to seconds (new format).
 * Values > 86400 are assumed to be milliseconds and are converted.
 *
 * @param {number} value - Raw interval value from settings
 * @returns {number} Interval in seconds (0 = off)
 */
export function normalizeAutoSyncInterval(value) {
    if (!value || value <= 0) return 0;
    // If value > 86400 (1 day in seconds), assume it's milliseconds
    if (value > 86400) {
        return Math.round(value / 1000);
    }
    return value;
}

/**
 * Format sync interval for display.
 *
 * @param {number} seconds - Interval in seconds
 * @returns {string} Formatted interval (e.g., "1m", "5m", "1h", "1d")
 */
export function formatSyncInterval(seconds) {
    if (seconds === 60) return '1m';
    if (seconds === 300) return '5m';
    if (seconds === 3600) return '1h';
    if (seconds === 86400) return '1d';
    if (seconds >= 86400) return `${Math.round(seconds / 86400)}d`;
    if (seconds >= 3600) return `${Math.round(seconds / 3600)}h`;
    if (seconds >= 60) return `${Math.round(seconds / 60)}m`;
    return `${seconds}s`;
}

/**
 * Format countdown for display (mm:ss or ss).
 *
 * @param {number} seconds - Remaining seconds
 * @returns {string} Formatted countdown (e.g., "4:32" or "45")
 */
export function formatCountdown(seconds) {
    if (seconds <= 0) return '';
    if (seconds < 60) return `${seconds}`;
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
}

/**
 * Format sync result for notification display.
 *
 * Returns entity-aware message when single type, generic "changes" for mixed types.
 * Examples: "Synced 3 events", "Synced 1 account", "Synced 5 changes"
 *
 * @param {Object} result - Sync result with applied count and appliedByType breakdown
 * @param {number} result.applied - Total number of applied changes
 * @param {Object} result.appliedByType - Breakdown by entity type (e.g., { event: 3, account: 1 })
 * @returns {string} Formatted message for notification
 */
export function formatSyncResult(result) {
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


// ============================================================================
// Account Balance Formatting
// ============================================================================

/**
 * Get CSS class for account balance based on account type.
 *
 * For credit cards: negative balance within limit is "positive" (green),
 * exceeding limit is "negative" (red).
 * For checking/savings: positive is green, negative is red.
 *
 * @param {Object} account - Account with current_balance, account_type, credit_limit
 * @returns {string} 'positive' or 'negative'
 */
export function getBalanceClass(account) {
    const balance = parseFloat(account.current_balance || 0);

    if (account.account_type === 'credit_card') {
        // Credit card: negative only if exceeding credit limit
        const limit = parseFloat(account.credit_limit || 0);
        return balance < -limit ? 'negative' : 'positive';
    }

    // Checking/savings: standard positive/negative logic
    return balance >= 0 ? 'positive' : 'negative';
}

/**
 * Apply sign to balance based on toggle state.
 *
 * Used in account forms where users enter positive numbers and toggle
 * a [+]/[-] button to indicate sign.
 *
 * @param {number} absoluteBalance - Positive balance value from input
 * @param {boolean} isNegative - Whether the toggle is set to negative
 * @returns {number} Signed balance value
 */
export function applyBalanceSign(absoluteBalance, isNegative) {
    return isNegative
        ? -Math.abs(parseFloat(absoluteBalance || 0))
        : Math.abs(parseFloat(absoluteBalance || 0));
}

/**
 * Get default sign for account type.
 *
 * Credit cards default to negative (owing money is normal).
 * Checking/savings default to positive.
 *
 * @param {string} accountType - 'checking', 'savings', or 'credit_card'
 * @returns {boolean} True if default should be negative
 */
export function getDefaultSignForAccountType(accountType) {
    return accountType === 'credit_card';
}

/**
 * Parse existing balance for form editing.
 *
 * Extracts absolute value and sign from a balance for display in
 * forms with separate input field and sign toggle.
 *
 * @param {number|string} balance - Current balance (may be negative)
 * @returns {Object} { absoluteValue: number, isNegative: boolean }
 */
export function parseBalanceForForm(balance) {
    const numericBalance = parseFloat(balance || 0);
    return {
        absoluteValue: Math.abs(numericBalance),
        isNegative: numericBalance < 0
    };
}
