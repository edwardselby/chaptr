/**
 * CHAPTR - Projection Engine (Client-Side)
 *
 * Port of core/projection.py to JavaScript for offline-first operation
 */

import { db } from './db.js';
import { parseISODate, daysBetween, toLocalISODate } from './utils.js';

/**
 * Convert amount to base currency
 * @param {number} amount - Amount in native currency
 * @param {number} rateToBase - Conversion rate (1 native = X base)
 * @returns {number} Amount in base currency
 */
export function convertToBaseCurrency(amount, rateToBase) {
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
export function convertFromBaseCurrency(baseAmount, displayCurrency, baseCurrency, rates) {
    if (displayCurrency === baseCurrency) {
        return baseAmount;
    }

    const displayRate = rates[displayCurrency] || 1.0;
    const result = Math.round(baseAmount * displayRate * 100) / 100;

    return result;
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
    virtualDrifts = [],
    settings = null  // ← Accept settings as parameter!
) {
    try {
        // Validate dates
        if (!startDate || !endDate) {
            console.warn('calculateProjection called with null dates');
            return [];
        }

        // Use passed settings or fall back to loading from Dexie
        if (!settings) {
            settings = await db.settings.get(1) || { base_currency: 'GBP', rates: {} };
        }

        // Step 1: Calculate starting balance from ALL historical events
        // This includes:
        // - Opening balance events (is_opening_balance=true) - ALWAYS included regardless of date
        // - All other events before startDate
        let startingBalance = 0;
        let historicalEventsCount = 0;
        let historicalEventsTotal = 0;

        // Get ALL events (we'll filter below)
        const allEvents = await db.events.toArray();

        // Separate opening balance events from regular historical events
        // FIX: Opening balance events should only be in starting balance if dated BEFORE startDate
        // Otherwise they appear as projection rows (causing double counting)
        const openingBalanceEvents = allEvents.filter(e => e.is_opening_balance === true && e.event_date < startDate);
        const regularHistoricalEvents = allEvents.filter(e =>
            e.is_opening_balance !== true && e.event_date < startDate
        );

        // Process opening balance events (only those before projection start)
        for (const event of openingBalanceEvents) {
            // Filter based on view
            let includeEvent = false;
            if (view === 'baseline') {
                includeEvent = event.is_baseline;
            } else if (view !== 'all' && storyId) {
                includeEvent = event.story_id === storyId || event.is_baseline;
            } else {
                includeEvent = !event.is_hypothetical;
            }

            if (includeEvent) {
                const amount = parseFloat(event.amount || 0);
                const rateToBase = parseFloat(event.rate_to_base || 1.0);
                const baseAmount = convertToBaseCurrency(amount, rateToBase);
                startingBalance += baseAmount;
                historicalEventsCount++;
                historicalEventsTotal += baseAmount;
            }
        }

        // Process regular historical events (before projection start)
        for (const event of regularHistoricalEvents) {
            // Filter based on view
            let includeEvent = false;
            if (view === 'baseline') {
                includeEvent = event.is_baseline;
            } else if (view !== 'all' && storyId) {
                includeEvent = event.story_id === storyId || event.is_baseline;
            } else {
                includeEvent = !event.is_hypothetical;
            }

            if (includeEvent) {
                const amount = parseFloat(event.amount || 0);
                const rateToBase = parseFloat(event.rate_to_base || 1.0);
                const baseAmount = convertToBaseCurrency(amount, rateToBase);
                startingBalance += baseAmount;
                historicalEventsCount++;
                historicalEventsTotal += baseAmount;
            }
        }

        // Step 2: Fetch events in date range
        // Queue-as-state: All recurring instances are real events in Dexie (no phantom generation needed)
        const rangeEvents = await db.events
            .where('event_date')
            .between(startDate, endDate, true, true)
            .toArray();

        // Filter by view - determine visible and hidden events
        let visibleEvents = [];
        let allEventsForBalance = [];  // Events that affect running balance

        if (view === 'baseline') {
            // Baseline view: only baseline events, exclude auto-adjustments (shown only in ALL view)
            visibleEvents = rangeEvents.filter(e => e.is_baseline && !e.is_auto_adjustment);
            allEventsForBalance = visibleEvents;  // No hidden events in baseline view
        } else if (view !== 'all' && storyId) {
            // Story view: ONLY show story events, hide baseline and other stories (spec: gap indicators)
            // Auto-adjustments excluded from all non-ALL views
            visibleEvents = rangeEvents.filter(e => e.story_id === storyId && !e.is_auto_adjustment);
            // For balance calculation: include ALL non-hypothetical events (baseline + all stories)
            allEventsForBalance = rangeEvents.filter(e => !e.is_hypothetical);
        } else if (view === 'all') {
            // ALL view: show baseline + all non-hypothetical events (including auto-adjustments)
            visibleEvents = rangeEvents.filter(e => !e.is_hypothetical);
            allEventsForBalance = visibleEvents;  // No hidden events in all view
        }

        // Step 3: Convert ALL events to base currency and sort
        const allEventsWithBase = allEventsForBalance.map(event => {
            const amount = parseFloat(event.amount || 0);
            const rateToBase = parseFloat(event.rate_to_base || 1.0);
            const baseAmount = convertToBaseCurrency(amount, rateToBase);

            return {
                ...event,
                base_amount: baseAmount
            };
        });

        // Sort by: date ASC, amount DESC (income first), created_at ASC
        allEventsWithBase.sort((a, b) => {
            // Primary: Sort by date
            if (a.event_date !== b.event_date) {
                return a.event_date < b.event_date ? -1 : 1;
            }

            // Same-day ordering (per spec):
            // 1. Opening balance events first
            if (a.is_opening_balance !== b.is_opening_balance) {
                return a.is_opening_balance ? -1 : 1;
            }

            // 2. Auto-adjustments next (before regular events)
            if (a.is_auto_adjustment !== b.is_auto_adjustment) {
                return a.is_auto_adjustment ? -1 : 1;
            }

            // 3. Then by amount (debits before credits = negative before positive)
            if (a.base_amount !== b.base_amount) {
                return a.base_amount - b.base_amount;
            }

            // 4. Tie-breaker: created_at ASC
            return a.created_at < b.created_at ? -1 : 1;
        });

        // Step 4: Calculate running balance using ALL events
        // Build visible event set for filtering
        const visibleEventIds = new Set(visibleEvents.map(e => e.id));

        let runningBalance = startingBalance;
        const results = [];

        for (const event of allEventsWithBase) {
            runningBalance += event.base_amount;

            // Only include visible events in results
            const isVisible = visibleEventIds.has(event.id);

            if (isVisible) {
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
                    isGap: false,
                    is_auto_adjustment: event.is_auto_adjustment || false,
                    recurring_rule_id: event.recurring_rule_id || null
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
        }

        // Step 5: Attach gap indicator metadata for story views (matches backend format)
        if (view !== 'all' && storyId) {
            const gaps = detectGapsBetweenVisibleEvents(allEventsWithBase, visibleEventIds);

            console.log('[CHAPTR] Gap detection for story view:', {
                totalGaps: gaps.length,
                gaps: gaps.map(g => ({
                    after_event_id: g.after_event_id,
                    before_event_id: g.before_event_id,
                    hidden_count: g.hidden_event_count,
                    delta: g.delta_base,
                    hidden_event_dates: g.hidden_events.map(e => e.event_date),
                    start_date: g.start_date,
                    end_date: g.end_date
                }))
            });

            // Also log the sorted events to see ordering
            console.log('[CHAPTR] Event ordering (first 10):', allEventsWithBase.slice(0, 10).map(e => ({
                date: e.event_date,
                desc: e.description,
                visible: visibleEventIds.has(e.id),
                is_baseline: e.is_baseline,
                is_opening: e.is_opening_balance,
                is_adjustment: e.is_auto_adjustment
            })));

            // Build index of results by event ID for fast lookup
            const resultsByEventId = {};
            for (const result of results) {
                resultsByEventId[result.id] = result;
            }

            // Attach gap metadata to visible events
            // Gap shows AFTER the event that precedes hidden events
            for (const gap of gaps) {
                // For gaps with a following event, attach to the following event
                // For trailing gaps (no following event), attach to the preceding event
                let targetEventId;
                let position;

                if (gap.before_event_id) {
                    // Gap has a following event - attach to it (shows BEFORE that event)
                    targetEventId = gap.before_event_id;
                    position = 'before';
                } else {
                    // Trailing gap - attach to preceding event (shows AFTER that event)
                    targetEventId = gap.after_event_id;
                    position = 'after';
                }

                if (targetEventId && resultsByEventId[targetEventId]) {
                    const targetEvent = resultsByEventId[targetEventId];

                    // Convert delta to display currency if requested
                    let deltaDisplay = gap.delta_base;
                    if (displayCurrency && displayCurrency !== settings.base_currency) {
                        deltaDisplay = convertFromBaseCurrency(
                            gap.delta_base,
                            displayCurrency,
                            settings.base_currency,
                            settings.rates
                        );
                    }

                    console.log('[CHAPTR] Attaching gap to event:', {
                        targetEventId,
                        eventDate: targetEvent.event_date,
                        eventDesc: targetEvent.description,
                        position,
                        hiddenCount: gap.hidden_event_count,
                        delta: deltaDisplay
                    });

                    // Attach gap_indicator field (matches backend format from core/projection.py:514)
                    resultsByEventId[targetEventId].gap_indicator = {
                        type: 'gap',
                        delta_base: gap.delta_base,
                        delta_display: deltaDisplay,
                        display_currency: displayCurrency || settings.base_currency,
                        hidden_event_count: gap.hidden_event_count,
                        date_range: {
                            start: gap.start_date,
                            end: gap.end_date
                        },
                        hidden_events: gap.hidden_events,
                        position: position  // 'before' or 'after' this event
                    };
                }
            }
        }

        // Step 5: Insert gap indicators and virtual drift rows (threshold: 7 days)
        const rowsWithGaps = insertGapIndicators(results, 7, virtualDrifts);

        // Step 6: Prepend historical events indicator if there are historical events
        if (historicalEventsCount > 0) {
            // Convert historical total to display currency if needed
            let historicalDisplayTotal = historicalEventsTotal;
            if (displayCurrency && displayCurrency !== settings.base_currency) {
                historicalDisplayTotal = convertFromBaseCurrency(
                    historicalEventsTotal,
                    displayCurrency,
                    settings.base_currency,
                    settings.rates
                );
            }

            // Create historical events indicator row
            const historicalIndicator = {
                isHistoricalGap: true,
                hidden_event_count: historicalEventsCount,
                delta_display: historicalDisplayTotal,
                display_currency: displayCurrency || settings.base_currency
            };

            // Prepend to results
            rowsWithGaps.unshift(historicalIndicator);
        }

        return rowsWithGaps;

    } catch (error) {
        console.error('Projection calculation error:', error);
        return [];
    }
}

/**
 * Detect gaps between visible events where hidden events affect running balance
 *
 * Matches backend implementation in core/projection.py:664-768
 *
 * @param {Array} allEventsSorted - ALL events sorted by date, amount DESC, created_at
 * @param {Set} visibleEventIds - Set of event IDs that are visible
 * @returns {Array} Array of gap metadata objects
 */
function detectGapsBetweenVisibleEvents(allEventsSorted, visibleEventIds) {
    const gaps = [];

    // Track state as we iterate through ALL events
    let lastVisibleEvent = null;
    let hiddenEventsAccumulator = [];
    let isFirstVisibleEvent = true;

    for (const event of allEventsSorted) {
        const eventId = event.id;
        const isVisible = visibleEventIds.has(eventId);

        if (isVisible) {
            // We've hit a visible event
            // Check if we accumulated hidden events since last visible event (or before first)
            if (hiddenEventsAccumulator.length > 0) {
                // Calculate net delta from hidden events (in base currency)
                const deltaBase = hiddenEventsAccumulator.reduce((sum, e) => sum + e.base_amount, 0);

                // Only create gap if delta != 0 (meaningful change)
                if (deltaBase !== 0) {
                    // Record gap metadata
                    gaps.push({
                        type: 'gap_indicator',
                        after_event_id: lastVisibleEvent?.id || null,  // null if before first visible
                        before_event_id: eventId,  // Current visible event
                        hidden_event_count: hiddenEventsAccumulator.length,
                        hidden_events: [...hiddenEventsAccumulator],
                        delta_base: deltaBase,
                        start_date: hiddenEventsAccumulator[0].event_date,
                        end_date: hiddenEventsAccumulator[hiddenEventsAccumulator.length - 1].event_date
                    });
                }

                // Reset accumulator
                hiddenEventsAccumulator = [];
            }

            // Update last visible event
            lastVisibleEvent = event;
            isFirstVisibleEvent = false;
        } else {
            // Hidden event - accumulate it
            hiddenEventsAccumulator.push(event);
        }
    }

    // Handle trailing hidden events after last visible event
    if (lastVisibleEvent !== null && hiddenEventsAccumulator.length > 0) {
        const deltaBase = hiddenEventsAccumulator.reduce((sum, e) => sum + e.base_amount, 0);
        if (deltaBase !== 0) {
            gaps.push({
                type: 'gap_indicator',
                after_event_id: lastVisibleEvent.id,
                before_event_id: null,  // No next visible event
                hidden_event_count: hiddenEventsAccumulator.length,
                hidden_events: [...hiddenEventsAccumulator],
                delta_base: deltaBase,
                start_date: hiddenEventsAccumulator[0].event_date,
                end_date: hiddenEventsAccumulator[hiddenEventsAccumulator.length - 1].event_date
            });
        }
    }

    return gaps;
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
    const today = toLocalISODate(new Date());
    let todayDividerInserted = false;

    for (let i = 0; i < rows.length; i++) {
        const row = rows[i];

        // Insert TODAY divider after today's events, before first future event
        if (!todayDividerInserted && row.event_date > today) {
            row.showTodayDivider = true;
            todayDividerInserted = true;
        }

        // Push the current row first
        withGaps.push(row);

        // Then inject virtual drift rows AFTER the row with today divider
        if (row.showTodayDivider && virtualDrifts && virtualDrifts.length > 0) {
            for (const driftRow of virtualDrifts) {
                withGaps.push(driftRow);
            }
        }

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
