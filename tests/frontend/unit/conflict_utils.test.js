/**
 * CHAPTR - Conflict Utils Tests
 *
 * Tests for pure functions in conflict-utils.js module
 */

import { describe, it, expect } from 'vitest';
import {
    formatConflictDateTime,
    isNewerVersion,
    areValuesEquivalent,
    isFieldDifferent,
    serializeMongoEvent,
    serializeMongoAccount,
    serializeMongoStory,
    serializeForConflictResolution
} from '../../../static/js/modules/conflict-utils.js';


// ============================================================================
// formatConflictDateTime Tests
// ============================================================================

describe('Conflict Utils: formatConflictDateTime', () => {
    it('should return empty string for null input', () => {
        expect(formatConflictDateTime(null)).toBe('');
    });

    it('should return empty string for undefined input', () => {
        expect(formatConflictDateTime(undefined)).toBe('');
    });

    it('should return empty string for empty string input', () => {
        expect(formatConflictDateTime('')).toBe('');
    });

    it('should return empty string for invalid date string', () => {
        expect(formatConflictDateTime('not-a-date')).toBe('');
    });

    it('should format valid ISO datetime correctly', () => {
        // Note: This test depends on local timezone
        const result = formatConflictDateTime('2024-01-15T14:30:00Z');
        // Just verify it returns a non-empty string in expected format
        expect(result).toMatch(/^[A-Z][a-z]{2} \d{1,2}, \d{2}:\d{2}$/);
    });

    it('should format midnight correctly', () => {
        const result = formatConflictDateTime('2024-06-01T00:00:00Z');
        expect(result).toMatch(/^[A-Z][a-z]{2} \d{1,2}, \d{2}:\d{2}$/);
    });

    it('should pad single-digit minutes', () => {
        // Create a date with a time that has single-digit minutes in UTC
        const date = new Date('2024-03-15T10:05:00Z');
        const result = formatConflictDateTime(date.toISOString());
        // Minutes should be padded to 2 digits
        expect(result).toMatch(/:\d{2}$/);
    });

    it('should handle all months correctly', () => {
        const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                       'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

        months.forEach((month, index) => {
            const monthNum = String(index + 1).padStart(2, '0');
            const result = formatConflictDateTime(`2024-${monthNum}-15T12:00:00Z`);
            // Result should contain one of the month abbreviations
            expect(months.some(m => result.includes(m))).toBe(true);
        });
    });
});


// ============================================================================
// isNewerVersion Tests
// ============================================================================

describe('Conflict Utils: isNewerVersion', () => {
    it('should return false if first version has no updated_at', () => {
        const version = { id: '1' };
        const otherVersion = { id: '2', updated_at: '2024-01-15T10:00:00Z' };
        expect(isNewerVersion(version, otherVersion)).toBe(false);
    });

    it('should return false if other version has no updated_at', () => {
        const version = { id: '1', updated_at: '2024-01-15T10:00:00Z' };
        const otherVersion = { id: '2' };
        expect(isNewerVersion(version, otherVersion)).toBe(false);
    });

    it('should return false if first version is null', () => {
        const otherVersion = { id: '2', updated_at: '2024-01-15T10:00:00Z' };
        expect(isNewerVersion(null, otherVersion)).toBe(false);
    });

    it('should return false if other version is null', () => {
        const version = { id: '1', updated_at: '2024-01-15T10:00:00Z' };
        expect(isNewerVersion(version, null)).toBe(false);
    });

    it('should return true if first version is newer', () => {
        const version = { id: '1', updated_at: '2024-01-15T12:00:00Z' };
        const otherVersion = { id: '2', updated_at: '2024-01-15T10:00:00Z' };
        expect(isNewerVersion(version, otherVersion)).toBe(true);
    });

    it('should return false if first version is older', () => {
        const version = { id: '1', updated_at: '2024-01-15T08:00:00Z' };
        const otherVersion = { id: '2', updated_at: '2024-01-15T10:00:00Z' };
        expect(isNewerVersion(version, otherVersion)).toBe(false);
    });

    it('should return false if versions have same timestamp', () => {
        const version = { id: '1', updated_at: '2024-01-15T10:00:00Z' };
        const otherVersion = { id: '2', updated_at: '2024-01-15T10:00:00Z' };
        expect(isNewerVersion(version, otherVersion)).toBe(false);
    });

    it('should handle timestamps with milliseconds', () => {
        const version = { id: '1', updated_at: '2024-01-15T10:00:00.500Z' };
        const otherVersion = { id: '2', updated_at: '2024-01-15T10:00:00.100Z' };
        expect(isNewerVersion(version, otherVersion)).toBe(true);
    });
});


// ============================================================================
// areValuesEquivalent Tests
// ============================================================================

describe('Conflict Utils: areValuesEquivalent', () => {
    it('should return true for both null', () => {
        expect(areValuesEquivalent(null, null)).toBe(true);
    });

    it('should return true for both undefined', () => {
        expect(areValuesEquivalent(undefined, undefined)).toBe(true);
    });

    it('should return true for null and undefined', () => {
        expect(areValuesEquivalent(null, undefined)).toBe(true);
        expect(areValuesEquivalent(undefined, null)).toBe(true);
    });

    it('should return false for null vs value', () => {
        expect(areValuesEquivalent(null, 'value')).toBe(false);
        expect(areValuesEquivalent('value', null)).toBe(false);
    });

    it('should return false for undefined vs value', () => {
        expect(areValuesEquivalent(undefined, 'value')).toBe(false);
        expect(areValuesEquivalent('value', undefined)).toBe(false);
    });

    it('should return true for equal strings', () => {
        expect(areValuesEquivalent('test', 'test')).toBe(true);
    });

    it('should return false for different strings', () => {
        expect(areValuesEquivalent('test1', 'test2')).toBe(false);
    });

    it('should return true for equal numbers', () => {
        expect(areValuesEquivalent(100, 100)).toBe(true);
        expect(areValuesEquivalent(0, 0)).toBe(true);
        expect(areValuesEquivalent(-5, -5)).toBe(true);
    });

    it('should return false for different numbers', () => {
        expect(areValuesEquivalent(100, 200)).toBe(false);
    });

    it('should return true for equal booleans', () => {
        expect(areValuesEquivalent(true, true)).toBe(true);
        expect(areValuesEquivalent(false, false)).toBe(true);
    });

    it('should return false for different booleans', () => {
        expect(areValuesEquivalent(true, false)).toBe(false);
    });

    it('should handle empty string vs null correctly', () => {
        expect(areValuesEquivalent('', null)).toBe(false);
        expect(areValuesEquivalent(null, '')).toBe(false);
    });

    it('should handle 0 vs null correctly', () => {
        expect(areValuesEquivalent(0, null)).toBe(false);
        expect(areValuesEquivalent(null, 0)).toBe(false);
    });
});


// ============================================================================
// isFieldDifferent Tests
// ============================================================================

describe('Conflict Utils: isFieldDifferent', () => {
    it('should return false if server version is null', () => {
        expect(isFieldDifferent(null, { name: 'test' }, 'name')).toBe(false);
    });

    it('should return false if client version is null', () => {
        expect(isFieldDifferent({ name: 'test' }, null, 'name')).toBe(false);
    });

    it('should return false if both versions are null', () => {
        expect(isFieldDifferent(null, null, 'name')).toBe(false);
    });

    it('should return false if field values are equal', () => {
        const server = { name: 'Test Account', balance: 100 };
        const client = { name: 'Test Account', balance: 200 };
        expect(isFieldDifferent(server, client, 'name')).toBe(false);
    });

    it('should return true if field values differ', () => {
        const server = { name: 'Server Name', balance: 100 };
        const client = { name: 'Client Name', balance: 100 };
        expect(isFieldDifferent(server, client, 'name')).toBe(true);
    });

    it('should return false if both fields are null', () => {
        const server = { name: null };
        const client = { name: null };
        expect(isFieldDifferent(server, client, 'name')).toBe(false);
    });

    it('should return false if both fields are undefined (missing)', () => {
        const server = { other: 'value' };
        const client = { other: 'value' };
        expect(isFieldDifferent(server, client, 'name')).toBe(false);
    });

    it('should return true if one field is null and other has value', () => {
        const server = { name: null };
        const client = { name: 'Client Name' };
        expect(isFieldDifferent(server, client, 'name')).toBe(true);
    });

    it('should return true if one field is undefined and other has value', () => {
        const server = {};
        const client = { name: 'Client Name' };
        expect(isFieldDifferent(server, client, 'name')).toBe(true);
    });

    it('should handle numeric field comparison', () => {
        const server = { amount: 100.50 };
        const client = { amount: 100.50 };
        expect(isFieldDifferent(server, client, 'amount')).toBe(false);

        const server2 = { amount: 100.50 };
        const client2 = { amount: 200.00 };
        expect(isFieldDifferent(server2, client2, 'amount')).toBe(true);
    });

    it('should handle boolean field comparison', () => {
        const server = { is_active: true };
        const client = { is_active: true };
        expect(isFieldDifferent(server, client, 'is_active')).toBe(false);

        const server2 = { is_active: true };
        const client2 = { is_active: false };
        expect(isFieldDifferent(server2, client2, 'is_active')).toBe(true);
    });
});


// ============================================================================
// serializeMongoEvent Tests
// ============================================================================

describe('Conflict Utils: serializeMongoEvent', () => {
    it('should return null/undefined input as-is', () => {
        expect(serializeMongoEvent(null)).toBe(null);
        expect(serializeMongoEvent(undefined)).toBe(undefined);
    });

    it('should convert amount to float', () => {
        const event = { amount: '100.50' };
        const result = serializeMongoEvent(event);
        expect(result.amount).toBe(100.50);
        expect(typeof result.amount).toBe('number');
    });

    it('should convert rate_to_base to float', () => {
        const event = { amount: 100, rate_to_base: '1.25' };
        const result = serializeMongoEvent(event);
        expect(result.rate_to_base).toBe(1.25);
    });

    it('should default rate_to_base to 1.0 if missing', () => {
        const event = { amount: 100 };
        const result = serializeMongoEvent(event);
        expect(result.rate_to_base).toBe(1.0);
    });

    it('should convert account_id to string', () => {
        const event = { amount: 100, account_id: 12345 };
        const result = serializeMongoEvent(event);
        expect(result.account_id).toBe('12345');
    });

    it('should preserve null account_id', () => {
        const event = { amount: 100, account_id: null };
        const result = serializeMongoEvent(event);
        expect(result.account_id).toBe(null);
    });

    it('should convert story_id to string', () => {
        const event = { amount: 100, story_id: 67890 };
        const result = serializeMongoEvent(event);
        expect(result.story_id).toBe('67890');
    });

    it('should preserve null story_id', () => {
        const event = { amount: 100, story_id: null };
        const result = serializeMongoEvent(event);
        expect(result.story_id).toBe(null);
    });

    it('should convert recurring_rule_id to string', () => {
        const event = { amount: 100, recurring_rule_id: 'rule-123' };
        const result = serializeMongoEvent(event);
        expect(result.recurring_rule_id).toBe('rule-123');
    });

    it('should preserve other fields unchanged', () => {
        const event = {
            id: 'evt-123',
            amount: 50,
            description: 'Test event',
            event_date: '2024-01-15',
            currency: 'GBP'
        };
        const result = serializeMongoEvent(event);
        expect(result.id).toBe('evt-123');
        expect(result.description).toBe('Test event');
        expect(result.event_date).toBe('2024-01-15');
        expect(result.currency).toBe('GBP');
    });
});


// ============================================================================
// serializeMongoAccount Tests
// ============================================================================

describe('Conflict Utils: serializeMongoAccount', () => {
    it('should return null/undefined input as-is', () => {
        expect(serializeMongoAccount(null)).toBe(null);
        expect(serializeMongoAccount(undefined)).toBe(undefined);
    });

    it('should convert current_balance to float', () => {
        const account = { current_balance: '1500.75' };
        const result = serializeMongoAccount(account);
        expect(result.current_balance).toBe(1500.75);
        expect(typeof result.current_balance).toBe('number');
    });

    it('should convert rate_to_base to float', () => {
        const account = { current_balance: 100, rate_to_base: '0.85' };
        const result = serializeMongoAccount(account);
        expect(result.rate_to_base).toBe(0.85);
    });

    it('should default rate_to_base to 1.0 if missing', () => {
        const account = { current_balance: 100 };
        const result = serializeMongoAccount(account);
        expect(result.rate_to_base).toBe(1.0);
    });

    it('should handle negative balances', () => {
        const account = { current_balance: '-500.25' };
        const result = serializeMongoAccount(account);
        expect(result.current_balance).toBe(-500.25);
    });

    it('should preserve other fields unchanged', () => {
        const account = {
            id: 'acc-123',
            current_balance: 100,
            name: 'Checking',
            currency: 'USD',
            account_type: 'checking'
        };
        const result = serializeMongoAccount(account);
        expect(result.id).toBe('acc-123');
        expect(result.name).toBe('Checking');
        expect(result.currency).toBe('USD');
        expect(result.account_type).toBe('checking');
    });
});


// ============================================================================
// serializeMongoStory Tests
// ============================================================================

describe('Conflict Utils: serializeMongoStory', () => {
    it('should return null/undefined input as-is', () => {
        expect(serializeMongoStory(null)).toBe(null);
        expect(serializeMongoStory(undefined)).toBe(undefined);
    });

    it('should convert funding_amount to float when present', () => {
        const story = { funding_amount: '5000.00' };
        const result = serializeMongoStory(story);
        expect(result.funding_amount).toBe(5000.00);
    });

    it('should not add funding_amount if not present', () => {
        const story = { name: 'Test Story' };
        const result = serializeMongoStory(story);
        expect(result.funding_amount).toBe(undefined);
    });

    it('should convert goal_amount to float when present', () => {
        const story = { goal_amount: '10000.50' };
        const result = serializeMongoStory(story);
        expect(result.goal_amount).toBe(10000.50);
    });

    it('should not add goal_amount if not present', () => {
        const story = { name: 'Test Story' };
        const result = serializeMongoStory(story);
        expect(result.goal_amount).toBe(undefined);
    });

    it('should convert default_account_id to string', () => {
        const story = { default_account_id: 12345 };
        const result = serializeMongoStory(story);
        expect(result.default_account_id).toBe('12345');
    });

    it('should preserve null default_account_id', () => {
        const story = { default_account_id: null };
        const result = serializeMongoStory(story);
        expect(result.default_account_id).toBe(null);
    });

    it('should preserve other fields unchanged', () => {
        const story = {
            id: 'story-123',
            name: 'Trip to Paris',
            start_date: '2024-06-01',
            end_date: '2024-06-15',
            funding_mode: 'projected'
        };
        const result = serializeMongoStory(story);
        expect(result.id).toBe('story-123');
        expect(result.name).toBe('Trip to Paris');
        expect(result.start_date).toBe('2024-06-01');
        expect(result.end_date).toBe('2024-06-15');
        expect(result.funding_mode).toBe('projected');
    });

    it('should handle null funding_amount', () => {
        const story = { funding_amount: null };
        const result = serializeMongoStory(story);
        // null is falsy so funding_amount won't be converted
        expect(result.funding_amount).toBe(null);
    });
});


// ============================================================================
// serializeForConflictResolution Tests
// ============================================================================

describe('Conflict Utils: serializeForConflictResolution', () => {
    it('should return null for null selectedVersion', () => {
        const result = serializeForConflictResolution('event', null, 'entity-123', '2024-01-15T10:00:00Z');
        expect(result).toBe(null);
    });

    it('should use selectedVersion.id if present', () => {
        const version = { id: 'version-id', amount: 100 };
        const result = serializeForConflictResolution('event', version, 'fallback-id', '2024-01-15T10:00:00Z');
        expect(result.id).toBe('version-id');
    });

    it('should use entityId as fallback if id is missing', () => {
        const version = { amount: 100 }; // no id
        const result = serializeForConflictResolution('event', version, 'fallback-id', '2024-01-15T10:00:00Z');
        expect(result.id).toBe('fallback-id');
    });

    it('should set updated_at to resolvedTimestamp', () => {
        const version = { id: 'v1', amount: 100 };
        const timestamp = '2024-01-15T12:00:00Z';
        const result = serializeForConflictResolution('event', version, 'v1', timestamp);
        expect(result.updated_at).toBe(timestamp);
    });

    it('should remove _id field from result', () => {
        const version = { id: 'v1', _id: 'mongo-object-id', amount: 100 };
        const result = serializeForConflictResolution('event', version, 'v1', '2024-01-15T10:00:00Z');
        expect(result._id).toBe(undefined);
    });

    describe('event type serialization', () => {
        it('should serialize event with all MongoDB types', () => {
            const version = {
                id: 'evt-1',
                amount: '150.75',
                rate_to_base: '1.2',
                account_id: 'acc-123',
                story_id: 'story-456',
                recurring_rule_id: 'rule-789',
                description: 'Test event',
                _id: 'mongo-id'
            };
            const result = serializeForConflictResolution('event', version, 'evt-1', '2024-01-15T10:00:00Z');

            expect(result.id).toBe('evt-1');
            expect(result.amount).toBe(150.75);
            expect(result.rate_to_base).toBe(1.2);
            expect(result.account_id).toBe('acc-123');
            expect(result.story_id).toBe('story-456');
            expect(result.recurring_rule_id).toBe('rule-789');
            expect(result.description).toBe('Test event');
            expect(result._id).toBe(undefined);
        });
    });

    describe('account type serialization', () => {
        it('should serialize account with all MongoDB types', () => {
            const version = {
                id: 'acc-1',
                current_balance: '2500.50',
                rate_to_base: '0.85',
                name: 'Checking',
                currency: 'EUR',
                _id: 'mongo-id'
            };
            const result = serializeForConflictResolution('account', version, 'acc-1', '2024-01-15T10:00:00Z');

            expect(result.id).toBe('acc-1');
            expect(result.current_balance).toBe(2500.50);
            expect(result.rate_to_base).toBe(0.85);
            expect(result.name).toBe('Checking');
            expect(result.currency).toBe('EUR');
            expect(result._id).toBe(undefined);
        });
    });

    describe('story type serialization', () => {
        it('should serialize story with all MongoDB types', () => {
            const version = {
                id: 'story-1',
                funding_amount: '5000.00',
                goal_amount: '10000.00',
                default_account_id: 'acc-123',
                name: 'Vacation',
                _id: 'mongo-id'
            };
            const result = serializeForConflictResolution('story', version, 'story-1', '2024-01-15T10:00:00Z');

            expect(result.id).toBe('story-1');
            expect(result.funding_amount).toBe(5000.00);
            expect(result.goal_amount).toBe(10000.00);
            expect(result.default_account_id).toBe('acc-123');
            expect(result.name).toBe('Vacation');
            expect(result._id).toBe(undefined);
        });
    });

    describe('unknown type handling', () => {
        it('should handle unknown entity types (no type-specific conversion)', () => {
            const version = {
                id: 'unknown-1',
                some_field: 'value',
                _id: 'mongo-id'
            };
            const result = serializeForConflictResolution('unknown_type', version, 'unknown-1', '2024-01-15T10:00:00Z');

            expect(result.id).toBe('unknown-1');
            expect(result.some_field).toBe('value');
            expect(result.updated_at).toBe('2024-01-15T10:00:00Z');
            expect(result._id).toBe(undefined);
        });
    });

    it('should preserve id and updated_at over serialized values', () => {
        // If the source version has different id/updated_at, they should be overridden
        const version = {
            id: 'original-id',
            updated_at: '2020-01-01T00:00:00Z',
            amount: 100
        };
        const result = serializeForConflictResolution('event', version, 'fallback-id', '2024-01-15T10:00:00Z');

        // id should be from version (it exists), not fallback
        expect(result.id).toBe('original-id');
        // updated_at should be the resolved timestamp, not the original
        expect(result.updated_at).toBe('2024-01-15T10:00:00Z');
    });
});
