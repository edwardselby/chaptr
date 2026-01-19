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
 * Determine the squashed result of two queue entries for the same entity.
 *
 * When multiple changes are made to the same entity before syncing, we need to
 * combine them into a single queue entry to prevent timestamp conflicts on sync.
 *
 * Action combination matrix:
 * | Existing | Incoming | Result | Rationale |
 * |----------|----------|--------|-----------|
 * | Create   | Update   | Create (merged data) | Entity still needs creation with latest data |
 * | Create   | Delete   | null (remove both)   | Entity never existed on server |
 * | Update   | Update   | Update (latest data) | Only final state matters |
 * | Update   | Delete   | Delete               | Entity should be deleted |
 * | Delete   | *        | Warning + incoming   | Shouldn't happen - entity gone locally |
 *
 * @param {Object} existing - The existing queue entry
 * @param {Object} incoming - The new queue entry
 * @returns {Object|null} - Squashed entry, or null if both should be removed
 */
function squashQueueEntries(existing, incoming) {
    const existingAction = existing.action;
    const incomingAction = incoming.action;

    //: Create → Delete = null (entity never existed on server, remove both)
    if (existingAction === 'create' && incomingAction === 'delete') {
        return null;
    }

    //: Create → Update = Create (with latest data)
    if (existingAction === 'create' && incomingAction === 'update') {
        return {
            action: 'create',
            data: { ...existing.data, ...incoming.data }
        };
    }

    //: Update → Update = Update (with latest data)
    if (existingAction === 'update' && incomingAction === 'update') {
        return {
            action: 'update',
            data: { ...existing.data, ...incoming.data }
        };
    }

    //: Update → Delete = Delete
    if (existingAction === 'update' && incomingAction === 'delete') {
        return {
            action: 'delete',
            data: null
        };
    }

    //: Delete → anything = shouldn't happen (entity is gone locally)
    //: But if it does, keep the incoming action and log warning
    if (existingAction === 'delete') {
        console.warn(`[CHAPTR] Unexpected queue state: delete followed by ${incomingAction}`);
        return {
            action: incomingAction,
            data: incoming.data
        };
    }

    //: Default: use incoming (shouldn't reach here)
    return {
        action: incomingAction,
        data: incoming.data
    };
}

/**
 * Helper: Queue an entity change for sync
 *
 * Queue-as-state architecture: Queue represents "what server will look like soon"
 *
 * Squashing logic: When adding a new entry for an entity that already has a pending
 * entry, replaces the existing entry with squashed data while preserving the original
 * base_updated_at timestamp. This prevents timestamp conflicts when the same entity
 * is modified multiple times before syncing (e.g., archive then unarchive).
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
    //: Check for existing pending entry for this entity
    const existingEntry = await db.sync_queue
        .where('entity_id')
        .equals(entityId)
        .first();

    if (existingEntry) {
        //: Squash: Determine final action and preserve original base_updated_at
        const squashedEntry = squashQueueEntries(existingEntry, {
            entity_type: entityType,
            entity_id: entityId,
            action: action,
            data: data,
            base_updated_at: baseUpdatedAt,
            ...metadata
        });

        if (squashedEntry === null) {
            //: Create → Delete = remove both (entity never existed on server)
            await db.sync_queue.delete(existingEntry.id);
            return;
        }

        //: Replace existing entry with squashed entry
        await db.sync_queue.update(existingEntry.id, {
            action: squashedEntry.action,
            data: squashedEntry.data,
            //: Keep original base_updated_at (server's actual state)
            base_updated_at: existingEntry.base_updated_at,
            queued_at: new Date().toISOString(),
            //: Update metadata - new values override existing if provided
            dependencies: metadata.dependencies || existingEntry.dependencies,
            _derived_from: metadata._derived_from || existingEntry._derived_from,
            _optimistic: metadata._optimistic ?? existingEntry._optimistic
        });
    } else {
        //: No existing entry - add new one
        await db.sync_queue.add({
            entity_type: entityType,
            entity_id: entityId,
            action: action,
            data: data,
            base_updated_at: baseUpdatedAt,
            queued_at: new Date().toISOString(),
            dependencies: metadata.dependencies || [],
            _derived_from: metadata._derived_from || null,
            _optimistic: metadata._optimistic ?? false
        });
    }
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

/**
 * Get stored tenant_id from sync_meta.
 *
 * Used to detect tenant changes on login - if the new user's tenant_id
 * differs from the stored one, the database should be cleared to prevent
 * data leakage between tenants.
 *
 * @returns {Promise<string|null>} Stored tenant_id or null if not set
 */
db.getTenantId = async function() {
    const meta = await db.sync_meta.get('tenant_id');
    return meta?.value || null;
};

/**
 * Store tenant_id in sync_meta.
 *
 * Called after login to track which tenant's data is in the local database.
 * On subsequent logins, this is compared to detect tenant changes.
 *
 * @param {string} tenantId - Tenant identifier to store
 * @returns {Promise<void>}
 */
db.setTenantId = async function(tenantId) {
    await db.sync_meta.put({ id: 'tenant_id', value: tenantId });
};

// Export database instance
export { db };
