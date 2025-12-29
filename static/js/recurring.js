/**
 * Client-side recurring event generation for offline mode
 * Mirrors backend logic from api/utils/recurring.py
 */

import { parseISODate, toLocalISODate } from './utils.js';
import { db } from './db.js';

/**
 * Generate phantom recurring events for projection calculation
 *
 * @param {Array} rules - Array of recurring rules
 * @param {Date} windowStart - Start of generation window
 * @param {Date} windowEnd - End of generation window
 * @param {Object} settings - Settings object with rates and base_currency
 * @returns {Array} Array of phantom event objects
 */
export async function generateRecurringEventsClientSide(rules, windowStart, windowEnd, settings) {
    const phantomEvents = [];

    // Get all accounts to check baseline status
    const accounts = await db.accounts.toArray();
    const accountMap = new Map(accounts.map(acc => [acc.id, acc]));

    for (const rule of rules) {
        // Check if rule overlaps with window
        const ruleStart = parseISODate(rule.start_date);
        const ruleEnd = rule.end_date ? parseISODate(rule.end_date) : null;

        const genStart = ruleStart > windowStart ? ruleStart : windowStart;
        const genEnd = ruleEnd && ruleEnd < windowEnd ? ruleEnd : windowEnd;

        if (genStart > windowEnd || genEnd < windowStart) {
            continue; // Rule doesn't overlap window
        }

        // Generate dates based on frequency
        const dates = generateDates(rule, genStart, genEnd);

        for (const date of dates) {
            const dateStr = toLocalISODate(date);

            // Check if event already exists (server-generated or user-created)
            const existing = await db.events.where({
                recurring_rule_id: rule.id,
                event_date: dateStr
            }).first();

            if (existing) {
                continue; // Skip if already exists
            }

            // Look up account to determine baseline status
            const account = accountMap.get(rule.account_id);
            const isBaseline = account ? (account.is_default || false) : false;

            // Calculate rate_to_base from settings
            const baseCurrency = settings?.base_currency || 'GBP';
            const ruleCurrency = rule.currency || baseCurrency;
            let rateToBase = 1.0;

            if (ruleCurrency !== baseCurrency && settings?.rates) {
                // Convert from rule currency to base currency
                // If rate exists in settings, use it; otherwise default to 1.0
                rateToBase = settings.rates[ruleCurrency] || 1.0;
            }

            // Create phantom event
            phantomEvents.push({
                id: `phantom-${rule.id}-${dateStr}`,  // Temporary ID
                event_date: dateStr,
                description: rule.description,
                amount: rule.amount,
                currency: rule.currency,
                rate_to_base: rateToBase,
                account_id: rule.account_id,
                story_id: null,  // Recurring events not tied to stories
                is_baseline: isBaseline,  // Inherit from account
                recurring_rule_id: rule.id,
                _clientGenerated: true  // Flag for phantom events
            });
        }
    }

    return phantomEvents;
}

/**
 * Generate dates for a recurring rule
 *
 * @param {Object} rule - Recurring rule
 * @param {Date} start - Start date
 * @param {Date} end - End date
 * @returns {Array<Date>} Array of dates
 */
function generateDates(rule, start, end) {
    const dates = [];
    let current = new Date(start);

    while (current <= end) {
        if (matchesRule(current, rule)) {
            dates.push(new Date(current));
        }

        // Advance by 1 day
        current.setDate(current.getDate() + 1);
    }

    return dates;
}

/**
 * Check if a date matches a recurring rule
 *
 * @param {Date} date - Date to check
 * @param {Object} rule - Recurring rule
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
