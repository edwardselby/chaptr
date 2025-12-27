/**
 * CHAPTR - Projection Engine (Client-Side)
 *
 * Port of core/projection.py to JavaScript for offline-first operation
 */

import { db } from './db.js';
import { parseISODate, daysBetween } from './utils.js';

/**
 * Convert amount to base currency
 * @param {number} amount - Amount in native currency
 * @param {number} rateToBase - Conversion rate (1 native = X base)
 * @returns {number} Amount in base currency
 */
function convertToBaseCurrency(amount, rateToBase) {
    return Math.round(amount * rateToBase * 100) / 100;
}

/**
 * Convert amount from base currency to display currency
 * @param {number} baseAmount - Amount in base currency
 * @param {string} displayCurrency - Target currency code
 * @param {string} baseCurrency - Base currency code
 * @param {object} rates - Current conversion rates
 * @returns {number} Amount in display currency
 */
function convertFromBaseCurrency(baseAmount, displayCurrency, baseCurrency, rates) {
    if (displayCurrency === baseCurrency) {
        return baseAmount;
    }

    const displayRate = rates[displayCurrency] || 1.0;
    return Math.round(baseAmount * displayRate * 100) / 100;
}

/**
 * Calculate global projection across all accounts and stories
 *
 * Algorithm (from spec):
 * 1. Sum all account.current_balance as starting point
 * 2. Fetch events in date range
 * 3. Apply same-day ordering: date ASC, amount DESC, created_at ASC
 * 4. Calculate running balance for each event
 * 5. Insert gap indicators where gaps > threshold
 *
 * @param {string} startDate - ISO date string (YYYY-MM-DD)
 * @param {string} endDate - ISO date string (YYYY-MM-DD)
 * @param {string} view - 'all', 'baseline', or story ID
 * @param {string|null} storyId - Story UUID (optional)
 * @param {string|null} displayCurrency - Display currency code (optional)
 * @returns {Promise<Array>} Array of event rows with running balance
 */
export async function calculateProjection(
    startDate,
    endDate,
    view = 'all',
    storyId = null,
    displayCurrency = null,
    virtualDrifts = []
) {
    try {
        // Validate dates
        if (!startDate || !endDate) {
            console.warn('calculateProjection called with null dates');
            return [];
        }

        // Get settings for currency conversion
        const settings = await db.settings.get(1) || { base_currency: 'GBP', rates: {} };

        // Step 1: Sum all account current_balance as starting point
        const allAccounts = await db.accounts.toArray();
        const accounts = allAccounts.filter(a => !a.is_archived);
        let startingBalance = 0;

        for (const account of accounts) {
            const balance = parseFloat(account.current_balance || 0);
            const rateToBase = parseFloat(account.rate_to_base || 1.0);
            const baseBalance = convertToBaseCurrency(balance, rateToBase);
            startingBalance += baseBalance;
        }

        // Step 2: Fetch events in date range
        let events = await db.events
            .where('event_date')
            .between(startDate, endDate, true, true)
            .toArray();

        // Filter by view
        if (view === 'baseline') {
            events = events.filter(e => e.is_baseline);
        } else if (view !== 'all' && storyId) {
            events = events.filter(e => e.story_id === storyId || e.is_baseline);
        }

        // Exclude hypothetical for 'all' view
        if (view === 'all') {
            events = events.filter(e => !e.is_hypothetical);
        }

        // Step 3: Convert events to base currency and sort
        const eventsWithBase = events.map(event => {
            const amount = parseFloat(event.amount || 0);
            const rateToBase = parseFloat(event.rate_to_base || 1.0);
            const baseAmount = convertToBaseCurrency(amount, rateToBase);

            return {
                ...event,
                base_amount: baseAmount
            };
        });

        // Sort by: date ASC, amount DESC (income first), created_at ASC
        eventsWithBase.sort((a, b) => {
            if (a.event_date !== b.event_date) {
                return a.event_date < b.event_date ? -1 : 1;
            }
            // Sort by base_amount DESC (income first)
            if (a.base_amount !== b.base_amount) {
                return b.base_amount - a.base_amount;
            }
            // Tie-breaker: created_at ASC
            return a.created_at < b.created_at ? -1 : 1;
        });

        // Step 4: Calculate running balance
        let runningBalance = startingBalance;
        const results = [];

        for (const event of eventsWithBase) {
            runningBalance += event.base_amount;

            // Determine source tag
            let source = null;
            if (event.is_baseline) {
                source = 'baseline';
            } else if (event.story_id) {
                const story = await db.stories.get(event.story_id);
                source = story ? story.name : 'story';
            }

            // Create result row
            const row = {
                id: event.id,
                event_date: event.event_date,
                description: event.description,
                amount: event.base_amount,
                balance: runningBalance,
                source: source,
                isGap: false
            };

            // Convert to display currency if requested
            if (displayCurrency && displayCurrency !== settings.base_currency) {
                row.amount = convertFromBaseCurrency(
                    event.base_amount,
                    displayCurrency,
                    settings.base_currency,
                    settings.rates
                );
                row.balance = convertFromBaseCurrency(
                    runningBalance,
                    displayCurrency,
                    settings.base_currency,
                    settings.rates
                );
            }

            results.push(row);
        }

        // Step 5: Insert gap indicators and virtual drift rows (threshold: 7 days)
        const rowsWithGaps = insertGapIndicators(results, 7, virtualDrifts);

        return rowsWithGaps;

    } catch (error) {
        console.error('Projection calculation error:', error);
        return [];
    }
}

/**
 * Insert gap indicator rows where gaps > threshold days
 *
 * @param {Array} rows - Array of event rows
 * @param {number} thresholdDays - Minimum gap in days to show indicator
 * @returns {Array} Rows with gap indicators inserted
 */
function insertGapIndicators(rows, thresholdDays = 7, virtualDrifts = []) {
    if (rows.length === 0) return rows;

    const withGaps = [];
    const today = new Date().toISOString().split('T')[0];
    let todayDividerInserted = false;

    for (let i = 0; i < rows.length; i++) {
        const row = rows[i];

        // Insert TODAY divider before first future event
        if (!todayDividerInserted && row.event_date >= today) {
            row.showTodayDivider = true;
            todayDividerInserted = true;

            // Inject virtual drift rows after TODAY divider, before future events
            if (virtualDrifts && virtualDrifts.length > 0) {
                for (const driftRow of virtualDrifts) {
                    withGaps.push(driftRow);
                }
            }
        }

        withGaps.push(row);

        // Check gap to next event
        if (i < rows.length - 1) {
            const nextRow = rows[i + 1];
            const gapDays = daysBetween(row.event_date, nextRow.event_date);

            if (gapDays > thresholdDays) {
                withGaps.push({
                    id: `gap-${i}`,
                    isGap: true,
                    gapDays: gapDays,
                    startDate: row.event_date,
                    endDate: nextRow.event_date
                });
            }
        }
    }

    return withGaps;
}

/**
 * Calculate story projection with funding modes
 *
 * @param {string} storyId - Story UUID
 * @param {string} startDate - ISO date string
 * @param {string} endDate - ISO date string
 * @param {string|null} displayCurrency - Display currency code
 * @returns {Promise<object>} Story projection data
 */
export async function calculateStoryProjection(
    storyId,
    startDate,
    endDate,
    displayCurrency = null
) {
    try {
        const story = await db.stories.get(storyId);
        if (!story) {
            throw new Error('Story not found');
        }

        // Calculate starting balance based on funding mode
        let startingBalance = 0;
        const fundingMode = story.funding_mode || 'projected';

        if (fundingMode === 'projected') {
            // Use projected balance on story start date
            // TODO: Implement projected balance calculation
            startingBalance = 0;
        } else if (fundingMode === 'fixed') {
            startingBalance = parseFloat(story.funding_amount || 0);
        } else if (fundingMode === 'projected_plus') {
            // TODO: Implement projected + adjustment
            startingBalance = parseFloat(story.funding_amount || 0);
        }

        // Get events for this story
        const projection = await calculateProjection(
            startDate || story.start_date,
            endDate || story.end_date,
            story.id,
            storyId,
            displayCurrency || story.display_currency
        );

        return {
            story: story,
            starting_balance: startingBalance,
            events: projection
        };

    } catch (error) {
        console.error('Story projection error:', error);
        return null;
    }
}
