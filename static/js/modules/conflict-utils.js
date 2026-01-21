/**
 * CHAPTR - Conflict Resolution Utilities
 *
 * Pure functions for conflict comparison, version detection, and MongoDB type serialization.
 * These functions have zero state dependencies and can be tested in isolation.
 */

// ============================================================================
// DateTime Formatting
// ============================================================================

/**
 * Format datetime for conflict display.
 *
 * @param {string} dateTimeStr - ISO datetime string
 * @returns {string} Formatted datetime (e.g., "Jan 15, 14:30")
 */
export function formatConflictDateTime(dateTimeStr) {
    if (!dateTimeStr) return '';
    const date = new Date(dateTimeStr);
    if (isNaN(date.getTime())) return '';

    const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                   'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    const month = months[date.getMonth()];
    const day = date.getDate();
    const hours = String(date.getHours()).padStart(2, '0');
    const minutes = String(date.getMinutes()).padStart(2, '0');

    return `${month} ${day}, ${hours}:${minutes}`;
}


// ============================================================================
// Version Comparison
// ============================================================================

/**
 * Determine if version is newer based on updated_at timestamp.
 *
 * @param {Object} version - Version object with updated_at field
 * @param {Object} otherVersion - Other version to compare against
 * @returns {boolean} True if this version is newer
 */
export function isNewerVersion(version, otherVersion) {
    if (!version?.updated_at || !otherVersion?.updated_at) return false;
    const versionTime = new Date(version.updated_at).getTime();
    const otherTime = new Date(otherVersion.updated_at).getTime();
    return versionTime > otherTime;
}


// ============================================================================
// Field Comparison
// ============================================================================

/**
 * Check if two values are equivalent (handling null/undefined).
 *
 * @param {*} val1 - First value
 * @param {*} val2 - Second value
 * @returns {boolean} True if values are equivalent
 */
export function areValuesEquivalent(val1, val2) {
    // Handle null/undefined equivalence
    const isNullish1 = val1 === null || val1 === undefined;
    const isNullish2 = val2 === null || val2 === undefined;
    if (isNullish1 && isNullish2) return true;
    if (isNullish1 !== isNullish2) return false;

    // Direct comparison
    return val1 === val2;
}

/**
 * Check if a specific field differs between two versions.
 *
 * @param {Object} serverVersion - Server version object
 * @param {Object} clientVersion - Client version object
 * @param {string} fieldKey - The field name to compare
 * @returns {boolean} True if values differ
 */
export function isFieldDifferent(serverVersion, clientVersion, fieldKey) {
    if (!serverVersion || !clientVersion) return false;
    return !areValuesEquivalent(serverVersion[fieldKey], clientVersion[fieldKey]);
}


// ============================================================================
// MongoDB Type Serialization
// ============================================================================

/**
 * Serialize MongoDB event types to plain JavaScript.
 *
 * Converts Decimal128 amounts/rates and ObjectId references to JS primitives.
 *
 * @param {Object} source - Source event data (may contain MongoDB types)
 * @returns {Object} Event data with all fields serialized to JS types
 */
export function serializeMongoEvent(source) {
    if (!source) return source;

    return {
        ...source,
        amount: parseFloat(source.amount),
        rate_to_base: parseFloat(source.rate_to_base || 1.0),
        account_id: source.account_id ? String(source.account_id) : null,
        story_id: source.story_id ? String(source.story_id) : null,
        recurring_rule_id: source.recurring_rule_id ? String(source.recurring_rule_id) : null
    };
}

/**
 * Serialize MongoDB account types to plain JavaScript.
 *
 * Converts Decimal128 balance/rate fields to JS numbers.
 *
 * @param {Object} source - Source account data (may contain MongoDB types)
 * @returns {Object} Account data with all fields serialized to JS types
 */
export function serializeMongoAccount(source) {
    if (!source) return source;

    return {
        ...source,
        current_balance: parseFloat(source.current_balance),
        rate_to_base: parseFloat(source.rate_to_base || 1.0)
    };
}

/**
 * Serialize MongoDB story types to plain JavaScript.
 *
 * Converts Decimal128 funding/goal amounts and ObjectId references to JS primitives.
 *
 * @param {Object} source - Source story data (may contain MongoDB types)
 * @returns {Object} Story data with all fields serialized to JS types
 */
export function serializeMongoStory(source) {
    if (!source) return source;

    const result = { ...source };

    if (source.funding_amount !== undefined && source.funding_amount !== null) {
        result.funding_amount = parseFloat(source.funding_amount);
    }
    if (source.goal_amount !== undefined && source.goal_amount !== null) {
        result.goal_amount = parseFloat(source.goal_amount);
    }
    result.default_account_id = source.default_account_id ? String(source.default_account_id) : null;

    return result;
}

/**
 * Serialize MongoDB entity types to plain JavaScript based on entity type.
 *
 * This is the main entry point for conflict resolution serialization.
 * It handles the common patterns:
 * - Uses entity_id as fallback if id is missing
 * - Sets the resolved timestamp
 * - Removes MongoDB _id field
 * - Calls the appropriate type-specific serializer
 *
 * @param {string} entityType - Entity type ('event', 'account', 'story')
 * @param {Object} selectedVersion - The version to serialize
 * @param {string} entityId - Fallback entity ID (from conflict.entity_id)
 * @param {string} resolvedTimestamp - The timestamp to use for updated_at
 * @returns {Object} Serialized entity ready for Dexie storage
 */
export function serializeForConflictResolution(entityType, selectedVersion, entityId, resolvedTimestamp) {
    if (!selectedVersion) return null;

    // Base conversion: set ID and timestamp
    let entityData = {
        ...selectedVersion,
        id: selectedVersion.id || entityId,
        updated_at: resolvedTimestamp
    };

    // Type-specific serialization
    switch (entityType) {
        case 'event':
            entityData = {
                ...entityData,
                ...serializeMongoEvent(selectedVersion)
            };
            break;
        case 'account':
            entityData = {
                ...entityData,
                ...serializeMongoAccount(selectedVersion)
            };
            break;
        case 'story':
            entityData = {
                ...entityData,
                ...serializeMongoStory(selectedVersion)
            };
            break;
    }

    // Ensure id and timestamp are preserved after spread
    entityData.id = selectedVersion.id || entityId;
    entityData.updated_at = resolvedTimestamp;

    // Remove MongoDB _id field if present
    delete entityData._id;

    return entityData;
}
