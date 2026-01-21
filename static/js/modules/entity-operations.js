/**
 * CHAPTR - Entity Operations
 *
 * Pure CRUD operations for events and stories with dependency injection.
 * These functions have no state dependencies and can be tested in isolation.
 */

// ============================================================================
// Account Resolution
// ============================================================================

/**
 * Resolve account ID using hierarchy (spec: Account Resolution at Creation).
 *
 * Resolution order:
 * 1. User-selected account
 * 2. Story default account
 * 3. Global default account
 *
 * @param {string|null} selectedAccountId - User-selected account ID
 * @param {string|null} storyId - Story ID for this event
 * @param {Array} accounts - Array of account objects
 * @param {Array} stories - Array of story objects
 * @returns {string|null} Resolved account ID
 */
export function resolveAccountId(selectedAccountId, storyId, accounts, stories) {
    // 1. User-selected account
    if (selectedAccountId) {
        return selectedAccountId;
    }

    // 2. Story default account
    if (storyId) {
        const story = stories.find(s => s.id === storyId);
        if (story && story.default_account_id) {
            return story.default_account_id;
        }
    }

    // 3. Global default account
    const defaultAccount = accounts.find(a => a.is_default && !a.is_archived);
    return defaultAccount ? defaultAccount.id : null;
}


// ============================================================================
// Event Operations
// ============================================================================

/**
 * Create a new event.
 *
 * @param {Object} db - Dexie database instance
 * @param {Object} eventData - Event form data
 * @param {Array} accounts - Array of account objects
 * @param {Array} stories - Array of story objects
 * @param {Object} settings - Settings object with base_currency and rates
 * @param {Function} generateId - UUID generator function
 * @returns {Promise<{success: boolean, id?: string, entity?: Object, error?: string}>}
 */
export async function createEvent(db, eventData, accounts, stories, settings, generateId) {
    const localId = generateId();
    const now = new Date().toISOString();

    // Resolve account using hierarchy
    const accountId = resolveAccountId(
        eventData.account_id,
        eventData.story_id,
        accounts,
        stories
    );

    if (!accountId) {
        return { success: false, error: 'Account required' };
    }

    // Get account for currency
    const account = accounts.find(a => a.id === accountId);
    const currency = account ? account.currency : settings.base_currency;

    // Lookup rate_to_base from settings.rates
    const rate_to_base = settings.rates && settings.rates[currency]
        ? settings.rates[currency]
        : 1.0;

    const event = {
        id: localId,
        description: eventData.description,
        amount: String(parseFloat(eventData.amount)),
        event_date: eventData.event_date,
        account_id: accountId,
        currency: currency,
        rate_to_base: rate_to_base,
        story_id: eventData.story_id || null,
        is_baseline: eventData.is_baseline || false,
        is_hypothetical: eventData.is_hypothetical || false,
        created_at: now,
        updated_at: now
    };

    // 1. Optimistic Dexie write
    await db.events.add(event);

    // 2. Queue for sync
    await db.queueChange('event', localId, 'create', event);

    return { success: true, id: localId, entity: event };
}

/**
 * Update an existing event.
 *
 * @param {Object} db - Dexie database instance
 * @param {string} eventId - Event UUID
 * @param {Object} updates - Event updates
 * @param {Array} accounts - Array of account objects
 * @returns {Promise<{success: boolean, entity?: Object, error?: string}>}
 */
export async function updateEvent(db, eventId, updates, accounts) {
    // 0. Get current entity for conflict detection (capture base_updated_at)
    const currentEvent = await db.events.get(eventId);
    if (!currentEvent) {
        return { success: false, error: `Event ${eventId} not found` };
    }
    const baseUpdatedAt = currentEvent.updated_at;

    const now = new Date().toISOString();

    const eventUpdates = {
        ...updates,
        updated_at: now
    };

    // If account changed, update currency and rate
    if (updates.account_id) {
        const account = accounts.find(a => a.id === updates.account_id);
        if (account) {
            eventUpdates.currency = account.currency;
            eventUpdates.rate_to_base = account.rate_to_base;
        }
    }

    // 1. Optimistic Dexie update
    await db.events.update(eventId, eventUpdates);

    // 2. Queue for sync (include base_updated_at for conflict detection)
    await db.queueChange('event', eventId, 'update', eventUpdates, baseUpdatedAt);

    return { success: true, entity: { ...currentEvent, ...eventUpdates } };
}

/**
 * Delete an event.
 *
 * @param {Object} db - Dexie database instance
 * @param {string} eventId - Event UUID
 * @param {Array} events - Array of event objects (for lookup)
 * @returns {Promise<{success: boolean, error?: string}>}
 */
export async function deleteEvent(db, eventId, events) {
    const event = events.find(e => e.id === eventId);
    if (!event) {
        return { success: false, error: 'Event not found' };
    }

    // 0. Get current entity for conflict detection (capture base_updated_at BEFORE delete)
    const currentEvent = await db.events.get(eventId);
    if (!currentEvent) {
        return { success: false, error: `Event ${eventId} not found in database` };
    }
    const baseUpdatedAt = currentEvent.updated_at;

    // 1. Mark as deleted in Dexie (or actually delete)
    await db.events.delete(eventId);

    // 2. Queue for sync (send null data per spec - delete should not send entity data)
    await db.queueChange('event', eventId, 'delete', null, baseUpdatedAt);

    return { success: true };
}


// ============================================================================
// Story Operations
// ============================================================================

/**
 * Create a new story.
 *
 * @param {Object} db - Dexie database instance
 * @param {Object} storyData - Story form data
 * @param {Object} settings - Settings object with base_currency
 * @param {Function} generateId - UUID generator function
 * @returns {Promise<{success: boolean, id?: string, entity?: Object}>}
 */
export async function createStory(db, storyData, settings, generateId) {
    const localId = generateId();
    const now = new Date().toISOString();

    const story = {
        id: localId,
        name: storyData.name,
        start_date: storyData.start_date,
        end_date: storyData.end_date,
        display_currency: storyData.display_currency || settings.base_currency,
        funding_mode: storyData.funding_mode || 'projected',
        funding_amount: String(parseFloat(storyData.funding_amount || 0)),
        goal_type: storyData.goal_type || null,
        goal_amount: String(parseFloat(storyData.goal_amount || 0)),
        default_account_id: storyData.default_account_id || null,
        is_archived: false,
        created_at: now,
        updated_at: now
    };

    // 1. Optimistic Dexie write
    await db.stories.add(story);

    // 2. Queue for sync
    await db.queueChange('story', localId, 'create', story);

    return { success: true, id: localId, entity: story };
}

/**
 * Update an existing story.
 *
 * @param {Object} db - Dexie database instance
 * @param {string} storyId - Story UUID
 * @param {Object} updates - Story updates
 * @returns {Promise<{success: boolean, entity?: Object, error?: string}>}
 */
export async function updateStory(db, storyId, updates) {
    // 0. Get current entity for conflict detection (capture base_updated_at)
    const currentStory = await db.stories.get(storyId);
    if (!currentStory) {
        return { success: false, error: `Story ${storyId} not found` };
    }
    const baseUpdatedAt = currentStory.updated_at;

    const now = new Date().toISOString();

    const storyUpdates = {
        ...updates,
        updated_at: now
    };

    // 1. Optimistic Dexie update
    await db.stories.update(storyId, storyUpdates);

    // 2. Queue for sync (include base_updated_at for conflict detection)
    await db.queueChange('story', storyId, 'update', storyUpdates, baseUpdatedAt);

    return { success: true, entity: { ...currentStory, ...storyUpdates } };
}

/**
 * Perform story deletion (actual deletion logic, without confirmation).
 *
 * Note: This archives the story rather than hard-deleting.
 *
 * @param {Object} db - Dexie database instance
 * @param {string} storyId - Story UUID
 * @returns {Promise<{success: boolean, error?: string}>}
 */
export async function performStoryDeletion(db, storyId) {
    // 0. Get current entity for conflict detection (capture base_updated_at)
    const currentStory = await db.stories.get(storyId);
    if (!currentStory) {
        return { success: false, error: `Story ${storyId} not found` };
    }
    const baseUpdatedAt = currentStory.updated_at;

    const now = new Date().toISOString();

    // 1. Mark as archived in Dexie
    await db.stories.update(storyId, {
        is_archived: true,
        updated_at: now
    });

    // 2. Queue for sync (send null data per spec - delete should not send entity data)
    await db.queueChange('story', storyId, 'delete', null, baseUpdatedAt);

    return { success: true };
}
