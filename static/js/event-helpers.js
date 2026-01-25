/**
 * CHAPTR - Event Helper Functions
 *
 * Pure functions for creating event data objects.
 * No Dexie dependencies - just data transformation for queue-as-state architecture.
 */

import { parseISODate, toLocalISODate, generateUUID } from './utils.js';

/**
 * Calculate exchange rate to base currency
 *
 * @param {string} currency - Currency code (e.g., 'GBP', 'USD')
 * @param {object} settings - Settings object with base_currency and rates
 * @returns {number} Exchange rate to base currency
 */
export function calculateRateToBase(currency, settings) {
    const baseCurrency = settings?.base_currency || 'GBP';

    if (currency === baseCurrency) {
        return 1.0;
    }

    if (settings?.rates && settings.rates[currency]) {
        // rates are stored as "1 base = X foreign", invert to get "1 foreign = X base"
        return 1 / settings.rates[currency];
    }

    // Fallback to 1.0 if rate not found
    return 1.0;
}

/**
 * Create opening balance event data for an account
 *
 * Pure function - returns event data object without creating in Dexie.
 *
 * @param {object} account - Account object (must have id, current_balance, currency, is_default)
 * @param {object} settings - Settings object with base_currency and rates
 * @returns {object|null} Event data object or null if balance is zero
 */
export function createOpeningBalanceEventData(account, settings) {
    // Skip if balance is zero (per spec)
    if (account.current_balance === 0) {
        return null;
    }

    const rateToBase = calculateRateToBase(account.currency, settings);
    const eventDate = toLocalISODate(new Date());

    // HIGH PRIORITY FIX: Opening balance events must never be transfers
    return {
        id: generateUUID(),
        event_date: eventDate,
        description: 'opening balance',  // Lowercase to match backend
        amount: account.current_balance,
        currency: account.currency,
        rate_to_base: rateToBase,
        account_id: account.id,
        story_id: null,
        is_baseline: account.is_default || false,  // Inherit from account
        is_hypothetical: false,
        is_opening_balance: true,
        is_auto_adjustment: false,
        is_transfer: false,  // Opening balances are never transfers
        recurring_rule_id: null
    };
}

/**
 * Create recurring event instance data for a specific date
 *
 * Pure function - returns event data object without creating in Dexie.
 *
 * @param {object} rule - Recurring rule object
 * @param {Date} date - Date for this instance
 * @param {object} settings - Settings object with base_currency and rates
 * @param {boolean} isBaseline - Whether this instance is baseline (from account lookup)
 * @returns {object} Event data object
 */
export function createRecurringInstanceData(rule, date, settings, isBaseline = false) {
    const rateToBase = calculateRateToBase(rule.currency, settings);
    const dateStr = toLocalISODate(date);

    return {
        id: generateUUID(),
        event_date: dateStr,
        description: rule.description,
        amount: rule.amount,
        currency: rule.currency,
        rate_to_base: rateToBase,
        account_id: rule.account_id,
        story_id: null,  // Recurring events not tied to stories
        is_baseline: isBaseline,  // Inherit from account
        is_hypothetical: false,
        is_opening_balance: false,
        is_auto_adjustment: false,
        is_transfer: false,  // Recurring instances are never transfers (consistency with opening balances)
        recurring_rule_id: rule.id
    };
}

/**
 * Check if a date matches a recurring rule
 *
 * @param {Date} date - Date to check
 * @param {object} rule - Recurring rule with frequency and day
 * @returns {boolean} True if date matches rule
 */
function matchesRule(date, rule) {
    if (rule.frequency === 'weekly') {
        // day: 1=Monday, 7=Sunday
        // getDay(): 0=Sunday, 6=Saturday
        const dayOfWeek = date.getDay() === 0 ? 7 : date.getDay();
        return dayOfWeek === rule.day;
    }

    if (rule.frequency === 'monthly') {
        return date.getDate() === rule.day;
    }

    if (rule.frequency === 'annual') {
        const ruleStart = parseISODate(rule.start_date);
        return date.getMonth() === ruleStart.getMonth() && date.getDate() === rule.day;
    }

    return false;
}

/**
 * Generate recurring event instances for a time window
 *
 * Pure function - returns array of event data objects.
 * Window: 30 days back, forwardDays forward (default 365 for financial planning).
 *
 * @param {object} rule - Recurring rule object
 * @param {number} forwardDays - Number of days forward to generate (default 365 for 12 months)
 * @param {object} settings - Settings object with base_currency and rates
 * @param {boolean} isBaseline - Whether instances should be baseline (from account lookup)
 * @returns {Array<object>} Array of event data objects
 */
export function generateInstancesForWindow(rule, forwardDays, settings, isBaseline = false) {
    const instances = [];
    const today = new Date();

    // Calculate window boundaries: 30 days back, forwardDays forward
    const windowStart = new Date(today);
    windowStart.setDate(windowStart.getDate() - 30);  // Always 30 days back

    const windowEnd = new Date(today);
    windowEnd.setDate(windowEnd.getDate() + forwardDays);  // Forward based on parameter

    // Check if rule overlaps with window
    const ruleStart = parseISODate(rule.start_date);
    const ruleEnd = rule.end_date ? parseISODate(rule.end_date) : null;

    const genStart = ruleStart > windowStart ? ruleStart : windowStart;
    const genEnd = ruleEnd && ruleEnd < windowEnd ? ruleEnd : windowEnd;

    if (genStart > windowEnd || genEnd < windowStart) {
        return instances; // Rule doesn't overlap window
    }

    // Generate dates based on frequency
    let current = new Date(genStart);

    // Parse excluded dates for comparison (handle both string and Date formats)
    const excludedDates = (rule.excluded_dates || []).map(d => {
        if (typeof d === 'string') return d;
        return toLocalISODate(d);
    });

    while (current <= genEnd) {
        if (matchesRule(current, rule)) {
            // Skip excluded dates (single-instance deletions)
            const currentStr = toLocalISODate(current);
            if (!excludedDates.includes(currentStr)) {
                instances.push(createRecurringInstanceData(rule, current, settings, isBaseline));
            }
        }

        // Advance by 1 day
        current.setDate(current.getDate() + 1);
    }

    return instances;
}

/**
 * Generate all recurring instances for a rule at creation time
 *
 * Generates instances for 30 days back and forwardDays forward (default 365 for 12 months).
 * This is called when a recurring rule is created or updated.
 *
 * @param {object} rule - Recurring rule object
 * @param {object} settings - Settings object with base_currency and rates
 * @param {boolean} isBaseline - Whether instances should be baseline (from account lookup)
 * @param {number} forwardDays - Number of days forward to generate (default 365 for 12 months)
 * @returns {Array<object>} Array of event data objects
 */
export function generateRecurringInstances(rule, settings, isBaseline = false, forwardDays = 365) {
    return generateInstancesForWindow(rule, forwardDays, settings, isBaseline);
}
