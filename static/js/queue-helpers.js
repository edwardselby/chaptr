/**
 * CHAPTR - Queue Helper Functions
 *
 * Functions for applying changes to IndexedDB and queueing them for sync.
 * Implements queue-as-state architecture: IndexedDB = Last Server State + Applied Sync Queue
 */

import { db } from './db.js';

/**
 * Apply a queued change to Dexie and add to sync queue
 *
 * This is the core queue-as-state operation:
 * 1. Apply the change to IndexedDB immediately (optimistic update)
 * 2. Queue the change for server sync
 * 3. Mark the entity with _queued_op flag
 *
 * @param {object} change - Change object
 * @param {string} change.entity_type - Entity type (e.g., 'account', 'event')
 * @param {string} change.entity_id - Entity UUID
 * @param {string} change.action - Action: 'create', 'update', or 'delete'
 * @param {object} change.data - Entity data (null for deletes)
 * @param {string} change.base_updated_at - Last known updated_at (for conflict detection)
 * @returns {Promise<void>}
 */
export async function applyQueuedChange(change) {
    // HIGH PRIORITY FIX: Validate required fields
    if (!change || typeof change !== 'object') {
        throw new Error('applyQueuedChange: change must be an object');
    }

    const { entity_type, entity_id, action, data, base_updated_at } = change;

    if (!entity_type) {
        throw new Error('applyQueuedChange: entity_type is required');
    }
    if (!entity_id) {
        throw new Error('applyQueuedChange: entity_id is required');
    }
    if (!action || !['create', 'update', 'delete'].includes(action)) {
        throw new Error('applyQueuedChange: action must be create, update, or delete');
    }
    if (action !== 'delete' && !data) {
        throw new Error('applyQueuedChange: data is required for create/update actions');
    }

    // Determine table name from entity type
    const tableName = getTableName(entity_type);

    try {
        // Apply change to Dexie
        if (action === 'create') {
            await db[tableName].add({
                ...data,
                _queued_op: 'create'
            });
        } else if (action === 'update') {
            await db[tableName].update(entity_id, {
                ...data,
                _queued_op: 'update'
            });
        } else if (action === 'delete') {
            // Mark as deleted but keep in Dexie until sync succeeds
            await db[tableName].update(entity_id, {
                _queued_op: 'delete'
            });
        }

        // Queue for sync
        await db.queueChange(entity_type, entity_id, action, data, base_updated_at);
    } catch (error) {
        console.error(`[CHAPTR] Error applying queued change:`, error);
        throw new Error(`Failed to apply ${action} for ${entity_type}: ${error.message}`);
    }
}

/**
 * Apply a derived change to Dexie with metadata
 *
 * Derived changes are those created automatically by the frontend
 * (e.g., opening balance events, recurring instances).
 *
 * Server may override these with authoritative versions during sync.
 *
 * @param {object} change - Change object
 * @param {string} change.entity_type - Entity type (e.g., 'event')
 * @param {string} change.entity_id - Entity UUID
 * @param {string} change.action - Action: 'create', 'update', or 'delete'
 * @param {object} change.data - Entity data
 * @param {string} change.base_updated_at - Last known updated_at (optional)
 * @param {object} metadata - Queue metadata
 * @param {string} metadata._derived_from - Derivation source (e.g., 'account_creation', 'recurring_rule_creation')
 * @param {array} metadata.dependencies - Array of entity IDs this change depends on
 * @param {boolean} metadata._optimistic - Is this a frontend guess? (default: true for derived changes)
 * @returns {Promise<void>}
 */
export async function applyDerivedChange(change, metadata) {
    // HIGH PRIORITY FIX: Validate required fields
    if (!change || typeof change !== 'object') {
        throw new Error('applyDerivedChange: change must be an object');
    }
    if (!metadata || typeof metadata !== 'object') {
        throw new Error('applyDerivedChange: metadata must be an object');
    }
    if (!metadata._derived_from) {
        throw new Error('applyDerivedChange: metadata._derived_from is required');
    }
    if (!Array.isArray(metadata.dependencies)) {
        throw new Error('applyDerivedChange: metadata.dependencies must be an array');
    }

    const { entity_type, entity_id, action, data, base_updated_at } = change;

    if (!entity_type) {
        throw new Error('applyDerivedChange: entity_type is required');
    }
    if (!entity_id) {
        throw new Error('applyDerivedChange: entity_id is required');
    }
    if (!action || !['create', 'update', 'delete'].includes(action)) {
        throw new Error('applyDerivedChange: action must be create, update, or delete');
    }
    if (action !== 'delete' && !data) {
        throw new Error('applyDerivedChange: data is required for create/update actions');
    }

    // Determine table name from entity type
    const tableName = getTableName(entity_type);

    try {
        // Apply change to Dexie with _queued_op flag
        if (action === 'create') {
            await db[tableName].add({
                ...data,
                _queued_op: 'create'
            });
        } else if (action === 'update') {
            await db[tableName].update(entity_id, {
                ...data,
                _queued_op: 'update'
            });
        } else if (action === 'delete') {
            await db[tableName].update(entity_id, {
                _queued_op: 'delete'
            });
        }

        // Queue for sync with metadata
        // Mark as optimistic by default for derived changes
        const enrichedMetadata = {
            ...metadata,
            _optimistic: metadata._optimistic !== undefined ? metadata._optimistic : true
        };

        await db.queueChange(entity_type, entity_id, action, data, base_updated_at, enrichedMetadata);
    } catch (error) {
        console.error(`[CHAPTR] Error applying derived change:`, error);
        throw new Error(`Failed to apply derived ${action} for ${entity_type}: ${error.message}`);
    }
}

/**
 * Apply multiple derived changes as a batch
 *
 * Useful for operations that create multiple entities at once
 * (e.g., creating recurring instances, account + opening balance).
 *
 * @param {Array<object>} changes - Array of change objects
 * @param {object} sharedMetadata - Metadata shared across all changes
 * @returns {Promise<void>}
 */
export async function applyDerivedChangesBatch(changes, sharedMetadata) {
    // HIGH PRIORITY FIX: Validate batch parameters
    if (!Array.isArray(changes)) {
        throw new Error('applyDerivedChangesBatch: changes must be an array');
    }
    if (!sharedMetadata || typeof sharedMetadata !== 'object') {
        throw new Error('applyDerivedChangesBatch: sharedMetadata must be an object');
    }

    const appliedChanges = [];
    const failedChanges = [];

    for (const change of changes) {
        try {
            await applyDerivedChange(change, sharedMetadata);
            appliedChanges.push(change);
        } catch (error) {
            console.error(`[CHAPTR] Failed to apply batch change:`, error);
            failedChanges.push({ change, error: error.message });
            // Continue with remaining changes instead of failing entire batch
        }
    }

    if (failedChanges.length > 0) {
        console.warn(`[CHAPTR] Batch completed with ${failedChanges.length} failures out of ${changes.length} total`);
        // Don't throw - let calling code decide how to handle partial success
    }

    return {
        applied: appliedChanges.length,
        failed: failedChanges.length,
        failures: failedChanges
    };
}

/**
 * Remove queued operation markers from entities
 *
 * Called after successful sync to clean up _queued_op flags.
 *
 * @param {string} tableName - Table name (e.g., 'accounts', 'events')
 * @param {array} entityIds - Array of entity IDs to clean
 * @returns {Promise<void>}
 */
export async function clearQueuedMarkers(tableName, entityIds) {
    for (const id of entityIds) {
        await db[tableName].update(id, {
            _queued_op: undefined
        });
    }
}

/**
 * Get table name from entity type
 *
 * Maps entity type strings to Dexie table names.
 *
 * @param {string} entityType - Entity type (e.g., 'account', 'event')
 * @returns {string} Table name (e.g., 'accounts', 'events')
 */
function getTableName(entityType) {
    const mapping = {
        'account': 'accounts',
        'story': 'stories',
        'event': 'events',
        'recurring_rule': 'recurring_rules',
        'user': 'users',
        'setting': 'settings'
    };

    return mapping[entityType] || entityType + 's';
}
