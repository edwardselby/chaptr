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
        return settings.rates[currency];
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
 *
 * @param {object} rule - Recurring rule object
 * @param {number} windowDays - Number of days forward/backward to generate (e.g., 30 for ±30 days)
 * @param {object} settings - Settings object with base_currency and rates
 * @param {boolean} isBaseline - Whether instances should be baseline (from account lookup)
 * @returns {Array<object>} Array of event data objects
 */
export function generateInstancesForWindow(rule, windowDays, settings, isBaseline = false) {
    const instances = [];
    const today = new Date();

    // Calculate window boundaries
    const windowStart = new Date(today);
    windowStart.setDate(windowStart.getDate() - windowDays);

    const windowEnd = new Date(today);
    windowEnd.setDate(windowEnd.getDate() + windowDays);

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

    while (current <= genEnd) {
        if (matchesRule(current, rule)) {
            instances.push(createRecurringInstanceData(rule, current, settings, isBaseline));
        }

        // Advance by 1 day
        current.setDate(current.getDate() + 1);
    }

    return instances;
}

/**
 * Generate all recurring instances for a rule at creation time
 *
 * Generates instances for ±30 days from today (configurable).
 * This is called when a recurring rule is created or updated.
 *
 * @param {object} rule - Recurring rule object
 * @param {object} settings - Settings object with base_currency and rates
 * @param {boolean} isBaseline - Whether instances should be baseline (from account lookup)
 * @param {number} windowDays - Number of days to generate (default 30)
 * @returns {Array<object>} Array of event data objects
 */
export function generateRecurringInstances(rule, settings, isBaseline = false, windowDays = 30) {
    return generateInstancesForWindow(rule, windowDays, settings, isBaseline);
}
