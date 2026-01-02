/**
 * CHAPTR - Dexie.js Database Configuration
 *
 * IndexedDB database using Dexie.js for offline-first storage
 */

// Initialize Dexie
const db = new Dexie('CHAPTR');

/**
 * Database Schema
 *
 * Version 1: Initial schema with all core tables
 * Version 2: Migrated event date field from 'date' to 'event_date'
 * Version 3: Enhanced sync_queue for queue-as-state architecture
 *            - Added _derived_from index for derived event tracking
 *            - Queue fields: dependencies, _derived_from, _optimistic (non-indexed)
 * Version 4: Added compound index on conflicts (entity_id + conflict_type)
 */
db.version(1).stores({
    // Core entities
    accounts: 'id, currency, is_default, is_archived',
    stories: 'id, start_date, end_date, is_archived',
    events: 'id, date, story_id, account_id, is_baseline, is_hypothetical',
    recurring_rules: 'id, story_id, frequency, next_occurrence',
    users: 'id, username, role',
    settings: 'id',

    // Sync protocol
    conflicts: 'id, entity_type, entity_id, resolved_at',
    sync_queue: '++id, entity_type, entity_id, queued_at, action',
    sync_meta: 'id'
});

db.version(2).stores({
    // Core entities
    accounts: 'id, currency, is_default, is_archived',
    stories: 'id, start_date, end_date, is_archived',
    events: 'id, event_date, story_id, account_id, is_baseline, is_hypothetical, is_opening_balance, is_auto_adjustment',
    recurring_rules: 'id, story_id, frequency, next_occurrence',
    users: 'id, username, role',
    settings: 'id',

    // Sync protocol
    conflicts: 'id, entity_type, entity_id, resolved_at',
    sync_queue: '++id, entity_type, entity_id, queued_at, action',
    sync_meta: 'id'
});

db.version(3).stores({
    // Core entities (unchanged)
    accounts: 'id, currency, is_default, is_archived',
    stories: 'id, start_date, end_date, is_archived',
    events: 'id, event_date, story_id, account_id, is_baseline, is_hypothetical, is_opening_balance, is_auto_adjustment, recurring_rule_id',
    recurring_rules: 'id, story_id, frequency, next_occurrence',
    users: 'id, username, role',
    settings: 'id',

    // Sync protocol - ENHANCED queue schema for queue-as-state architecture
    conflicts: 'id, entity_type, entity_id, resolved_at',
    sync_queue: '++id, entity_type, entity_id, queued_at, action, _derived_from',
    sync_meta: 'id'
}).upgrade(async trans => {
    // Migrate existing queue entries to v3 schema with metadata fields
    console.log('[CHAPTR] Upgrading to schema v3 - adding queue metadata fields');

    await trans.sync_queue.toCollection().modify(entry => {
        // Add missing metadata fields with safe defaults
        if (entry.dependencies === undefined) {
            entry.dependencies = [];
        }
        if (entry._derived_from === undefined) {
            entry._derived_from = null;
        }
        if (entry._optimistic === undefined) {
            entry._optimistic = false;
        }
    });

    console.log('[CHAPTR] Schema v3 upgrade complete');
});

db.version(4).stores({
    // Core entities (unchanged)
    accounts: 'id, currency, is_default, is_archived',
    stories: 'id, start_date, end_date, is_archived',
    events: 'id, event_date, story_id, account_id, is_baseline, is_hypothetical, is_opening_balance, is_auto_adjustment, recurring_rule_id',
    recurring_rules: 'id, story_id, frequency, next_occurrence',
    users: 'id, username, role',
    settings: 'id',

    // Conflicts: Added compound index [entity_id+conflict_type] for performance
    conflicts: 'id, entity_type, [entity_id+conflict_type], resolved_at',

    // Sync protocol (unchanged)
    sync_queue: '++id, entity_type, entity_id, queued_at, action, _derived_from',
    sync_meta: 'id'
});

/**
 * Initialize default settings if not present
 */
db.on('ready', async () => {
    const settingsCount = await db.settings.count();
    if (settingsCount === 0) {
        await db.settings.add({
            id: 1,
            base_currency: 'GBP',
            rates: {
                'GBP': 1.0,
                'USD': 1.27,
                'EUR': 1.17,
                'CAD': 1.72
            },
            baseline_display_months: 3,
            date_format: 'DD MMM',
            auto_sync_interval: 300000 // 5 minutes
        });
        console.log('Default settings initialized');
    }
});

/**
 * Helper: Get all accounts (excluding archived)
 */
db.getActiveAccounts = async function() {
    const all = await db.accounts.toArray();
    return all.filter(a => !a.is_archived);
};

/**
 * Helper: Get all active stories (excluding archived)
 */
db.getActiveStories = async function() {
    const all = await db.stories.toArray();
    return all.filter(s => !s.is_archived);
};

/**
 * Helper: Get events for a date range
 */
db.getEventsInRange = async function(startDate, endDate) {
    return await db.events
        .where('event_date')
        .between(startDate, endDate, true, true)
        .toArray();
};

/**
 * Helper: Get events for a specific story
 */
db.getStoryEvents = async function(storyId) {
    return await db.events.where('story_id').equals(storyId).toArray();
};

/**
 * Helper: Get baseline events
 */
db.getBaselineEvents = async function() {
    const all = await db.events.toArray();
    return all.filter(e => e.is_baseline === true);
};

/**
 * Helper: Get default account
 */
db.getDefaultAccount = async function() {
    const all = await db.accounts.toArray();
    return all.find(a => a.is_default === true);
};

/**
 * Helper: Queue an entity change for sync
 *
 * Queue-as-state architecture: Queue represents "what server will look like soon"
 *
 * @param {string} entityType - Type of entity (account, story, event, etc.)
 * @param {string} entityId - UUID of the entity
 * @param {string} action - Action type: 'create', 'update', or 'delete'
 * @param {object} data - Entity data (null for deletes)
 * @param {string} baseUpdatedAt - Last known updated_at timestamp (for conflict detection on updates/deletes)
 * @param {object} metadata - Optional metadata for queue-as-state
 * @param {array} metadata.dependencies - Array of entity IDs this change depends on
 * @param {string} metadata._derived_from - Mark derived operations ('account_creation', 'recurring_rule_creation')
 * @param {boolean} metadata._optimistic - Is this a frontend guess? (server may correct)
 */
db.queueChange = async function(entityType, entityId, action, data, baseUpdatedAt = null, metadata = {}) {
    await db.sync_queue.add({
        entity_type: entityType,
        entity_id: entityId,
        action: action, // 'create', 'update', 'delete'
        data: data,
        base_updated_at: baseUpdatedAt, // For conflict detection (update/delete only)
        queued_at: new Date().toISOString(),

        // Queue-as-state enhancements (v3)
        dependencies: metadata.dependencies || [],
        _derived_from: metadata._derived_from || null,
        _optimistic: metadata._optimistic || false
    });
};

/**
 * Helper: Mark an entity as having a queued operation
 *
 * Sets the _queued_op flag on an entity to indicate it has pending changes.
 * This flag helps identify which entities are part of queue-as-state.
 *
 * @param {string} tableName - Name of the Dexie table (e.g., 'accounts', 'events')
 * @param {string} entityId - UUID of the entity
 * @param {string} action - Action type: 'create', 'update', or 'delete'
 */
db.markAsQueued = async function(tableName, entityId, action) {
    await db[tableName].update(entityId, {
        _queued_op: action
    });
};

/**
 * Helper: Get pending sync queue items
 */
db.getPendingSyncQueue = async function() {
    return await db.sync_queue.toArray();
};

/**
 * Helper: Clear sync queue after successful sync
 */
db.clearSyncQueue = async function() {
    await db.sync_queue.clear();
};

/**
 * Helper: Get unresolved conflicts
 */
db.getUnresolvedConflicts = async function() {
    // Dexie doesn't support .equals(null) - filter after fetch instead
    const allConflicts = await db.conflicts.toArray();
    return allConflicts.filter(c => c.resolved_at === null || c.resolved_at === undefined);
};

/**
 * Helper: Mark conflict as resolved
 */
db.resolveConflict = async function(conflictId) {
    await db.conflicts.update(conflictId, {
        resolved_at: new Date().toISOString()
    });
};

/**
 * Helper: Clear all local data (admin only)
 *
 * Clears all tables in the database. This is a destructive operation
 * that should only be performed by admin users. After clearing, the
 * app should trigger a full sync to re-download all data from server.
 *
 * @returns {Promise<void>}
 */
db.clearAllData = async function() {
    await db.accounts.clear();
    await db.stories.clear();
    await db.events.clear();
    await db.recurring_rules.clear();
    await db.conflicts.clear();
    await db.sync_queue.clear();
    await db.sync_meta.clear();
    // Note: users and settings are preserved to maintain login and preferences
};

// Export database instance
export { db };
