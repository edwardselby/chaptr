/**
 * Tests for CHAPTR Queue Helper Functions
 *
 * Tests queue-as-state operations: applying changes to IndexedDB
 * and queueing for sync with proper validation and error handling.
 */

import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { db } from '../static/js/db.js';
import {
  applyQueuedChange,
  applyDerivedChange,
  applyDerivedChangesBatch,
  clearQueuedMarkers
} from '../static/js/queue-helpers.js';
import { generateUUID } from '../static/js/utils.js';

describe('Queue Helpers - applyQueuedChange', () => {
  const testAccountId = generateUUID();

  beforeEach(async () => {
    // Clear tables before each test
    await db.accounts.clear();
    await db.sync_queue.clear();
  });

  afterEach(async () => {
    await db.accounts.clear();
    await db.sync_queue.clear();
  });

  it('should validate required fields', async () => {
    // Null/undefined change
    await expect(applyQueuedChange(null)).rejects.toThrow('change must be an object');
    await expect(applyQueuedChange(undefined)).rejects.toThrow('change must be an object');

    // Missing entity_type
    await expect(applyQueuedChange({
      entity_id: testAccountId,
      action: 'create',
      data: {}
    })).rejects.toThrow('entity_type is required');

    // Missing entity_id
    await expect(applyQueuedChange({
      entity_type: 'account',
      action: 'create',
      data: {}
    })).rejects.toThrow('entity_id is required');

    // Invalid action
    await expect(applyQueuedChange({
      entity_type: 'account',
      entity_id: testAccountId,
      action: 'invalid',
      data: {}
    })).rejects.toThrow('action must be create, update, or delete');

    // Missing data for create
    await expect(applyQueuedChange({
      entity_type: 'account',
      entity_id: testAccountId,
      action: 'create'
    })).rejects.toThrow('data is required for create/update actions');
  });

  it('should apply CREATE action to IndexedDB', async () => {
    const accountData = {
      id: testAccountId,
      name: 'Test Account',
      currency: 'GBP',
      current_balance: 1000,
      is_default: false,
      is_archived: false
    };

    await applyQueuedChange({
      entity_type: 'account',
      entity_id: testAccountId,
      action: 'create',
      data: accountData
    });

    // Verify entity added to IndexedDB
    const account = await db.accounts.get(testAccountId);
    expect(account).toBeDefined();
    expect(account.name).toBe('Test Account');
    expect(account._queued_op).toBe('create');

    // Verify change queued for sync
    const queueEntry = await db.sync_queue.where({ entity_id: testAccountId }).first();
    expect(queueEntry).toBeDefined();
    expect(queueEntry.action).toBe('create');
    expect(queueEntry.entity_type).toBe('account');
  });

  it('should apply UPDATE action to IndexedDB', async () => {
    // Create initial account
    const accountId = generateUUID();
    await db.accounts.add({
      id: accountId,
      name: 'Original Name',
      currency: 'GBP',
      current_balance: 1000,
      is_default: false,
      is_archived: false
    });

    // Apply update
    await applyQueuedChange({
      entity_type: 'account',
      entity_id: accountId,
      action: 'update',
      data: { name: 'Updated Name', current_balance: 2000 },
      base_updated_at: new Date().toISOString()
    });

    // Verify entity updated
    const account = await db.accounts.get(accountId);
    expect(account.name).toBe('Updated Name');
    expect(account.current_balance).toBe(2000);
    expect(account._queued_op).toBe('update');

    // Verify change queued
    const queueEntry = await db.sync_queue.where({ entity_id: accountId }).first();
    expect(queueEntry.action).toBe('update');
  });

  it('should apply DELETE action to IndexedDB', async () => {
    // Create initial account
    const accountId = generateUUID();
    await db.accounts.add({
      id: accountId,
      name: 'To Delete',
      currency: 'GBP',
      current_balance: 1000,
      is_default: false,
      is_archived: false
    });

    // Apply delete
    await applyQueuedChange({
      entity_type: 'account',
      entity_id: accountId,
      action: 'delete',
      base_updated_at: new Date().toISOString()
    });

    // Verify entity marked as deleted (not removed)
    const account = await db.accounts.get(accountId);
    expect(account).toBeDefined();
    expect(account._queued_op).toBe('delete');

    // Verify change queued
    const queueEntry = await db.sync_queue.where({ entity_id: accountId }).first();
    expect(queueEntry.action).toBe('delete');
  });
});

describe('Queue Helpers - applyDerivedChange', () => {
  const testEventId = generateUUID();
  const testAccountId = generateUUID();

  beforeEach(async () => {
    await db.events.clear();
    await db.sync_queue.clear();
  });

  afterEach(async () => {
    await db.events.clear();
    await db.sync_queue.clear();
  });

  it('should validate required fields', async () => {
    const validChange = {
      entity_type: 'event',
      entity_id: testEventId,
      action: 'create',
      data: { id: testEventId, description: 'test' }
    };

    // Missing metadata
    await expect(applyDerivedChange(validChange, null)).rejects.toThrow('metadata must be an object');

    // Missing _derived_from
    await expect(applyDerivedChange(validChange, {
      dependencies: []
    })).rejects.toThrow('metadata._derived_from is required');

    // Invalid dependencies (not array)
    await expect(applyDerivedChange(validChange, {
      _derived_from: 'account_creation',
      dependencies: 'not-an-array'
    })).rejects.toThrow('metadata.dependencies must be an array');
  });

  it('should apply derived change with metadata', async () => {
    const eventData = {
      id: testEventId,
      event_date: '2025-01-01',
      description: 'opening balance',
      amount: 1000,
      currency: 'GBP',
      rate_to_base: 1.0,
      account_id: testAccountId,
      is_opening_balance: true,
      is_transfer: false
    };

    const metadata = {
      _derived_from: 'account_creation',
      dependencies: [testAccountId]
    };

    await applyDerivedChange({
      entity_type: 'event',
      entity_id: testEventId,
      action: 'create',
      data: eventData
    }, metadata);

    // Verify entity added
    const event = await db.events.get(testEventId);
    expect(event).toBeDefined();
    expect(event.description).toBe('opening balance');
    expect(event._queued_op).toBe('create');

    // Verify metadata queued (stored as individual fields, not nested object)
    const queueEntry = await db.sync_queue.where({ entity_id: testEventId }).first();
    expect(queueEntry).toBeDefined();
    expect(queueEntry._derived_from).toBe('account_creation');
    expect(queueEntry._optimistic).toBe(true); // Default value
    expect(queueEntry.dependencies).toEqual([testAccountId]);
  });

  it('should respect explicit _optimistic flag', async () => {
    const eventData = {
      id: testEventId,
      event_date: '2025-01-01',
      description: 'test',
      amount: 100,
      currency: 'GBP'
    };

    // Explicitly set _optimistic to false
    const metadata = {
      _derived_from: 'recurring_rule_creation',
      dependencies: [],
      _optimistic: false
    };

    await applyDerivedChange({
      entity_type: 'event',
      entity_id: testEventId,
      action: 'create',
      data: eventData
    }, metadata);

    const queueEntry = await db.sync_queue.where({ entity_id: testEventId }).first();
    expect(queueEntry._optimistic).toBe(false);
  });
});

describe('Queue Helpers - applyDerivedChangesBatch', () => {
  beforeEach(async () => {
    await db.events.clear();
    await db.sync_queue.clear();
  });

  afterEach(async () => {
    await db.events.clear();
    await db.sync_queue.clear();
  });

  it('should validate batch parameters', async () => {
    // Not an array
    await expect(applyDerivedChangesBatch('not-array', {})).rejects.toThrow('changes must be an array');

    // Missing metadata
    await expect(applyDerivedChangesBatch([], null)).rejects.toThrow('sharedMetadata must be an object');
  });

  it('should apply multiple changes successfully', async () => {
    const event1Id = generateUUID();
    const event2Id = generateUUID();
    const accountId = generateUUID();

    const changes = [
      {
        entity_type: 'event',
        entity_id: event1Id,
        action: 'create',
        data: {
          id: event1Id,
          event_date: '2025-01-15',
          description: 'Instance 1',
          amount: 100,
          currency: 'GBP'
        }
      },
      {
        entity_type: 'event',
        entity_id: event2Id,
        action: 'create',
        data: {
          id: event2Id,
          event_date: '2025-02-15',
          description: 'Instance 2',
          amount: 100,
          currency: 'GBP'
        }
      }
    ];

    const metadata = {
      _derived_from: 'recurring_rule_creation',
      dependencies: [accountId]
    };

    const result = await applyDerivedChangesBatch(changes, metadata);

    expect(result.applied).toBe(2);
    expect(result.failed).toBe(0);
    expect(result.failures).toHaveLength(0);

    // Verify both events created
    const event1 = await db.events.get(event1Id);
    const event2 = await db.events.get(event2Id);
    expect(event1).toBeDefined();
    expect(event2).toBeDefined();

    // Verify both queued
    const queueEntries = await db.sync_queue.toArray();
    expect(queueEntries.length).toBeGreaterThanOrEqual(2);
  });

  it('should handle partial failures gracefully', async () => {
    const validEventId = generateUUID();
    const invalidEventId = generateUUID();

    const changes = [
      {
        entity_type: 'event',
        entity_id: validEventId,
        action: 'create',
        data: {
          id: validEventId,
          description: 'Valid event',
          amount: 100
        }
      },
      {
        entity_type: 'event',
        entity_id: invalidEventId,
        action: 'invalid_action', // This will fail
        data: { id: invalidEventId }
      }
    ];

    const metadata = {
      _derived_from: 'test',
      dependencies: []
    };

    const result = await applyDerivedChangesBatch(changes, metadata);

    // Should succeed for valid change, fail for invalid
    expect(result.applied).toBe(1);
    expect(result.failed).toBe(1);
    expect(result.failures).toHaveLength(1);

    // Valid event should be created
    const validEvent = await db.events.get(validEventId);
    expect(validEvent).toBeDefined();
  });

  it('should return empty failures array when all succeed', async () => {
    const changes = [];
    const metadata = { _derived_from: 'test', dependencies: [] };

    const result = await applyDerivedChangesBatch(changes, metadata);

    expect(result.applied).toBe(0);
    expect(result.failed).toBe(0);
    expect(result.failures).toHaveLength(0);
  });
});

describe('Queue Helpers - clearQueuedMarkers', () => {
  beforeEach(async () => {
    await db.accounts.clear();
  });

  afterEach(async () => {
    await db.accounts.clear();
  });

  it('should remove _queued_op markers from entities', async () => {
    const accountId1 = generateUUID();
    const accountId2 = generateUUID();

    // Create accounts with _queued_op markers
    await db.accounts.add({
      id: accountId1,
      name: 'Account 1',
      currency: 'GBP',
      current_balance: 1000,
      _queued_op: 'create'
    });

    await db.accounts.add({
      id: accountId2,
      name: 'Account 2',
      currency: 'USD',
      current_balance: 2000,
      _queued_op: 'update'
    });

    // Clear markers
    await clearQueuedMarkers('accounts', [accountId1, accountId2]);

    // Verify markers removed
    const account1 = await db.accounts.get(accountId1);
    const account2 = await db.accounts.get(accountId2);

    expect(account1._queued_op).toBeUndefined();
    expect(account2._queued_op).toBeUndefined();

    // Verify other fields preserved
    expect(account1.name).toBe('Account 1');
    expect(account2.currency).toBe('USD');
  });

  it('should handle empty entity ID array', async () => {
    // Should not throw
    await expect(clearQueuedMarkers('accounts', [])).resolves.toBeUndefined();
  });

  it('should handle non-existent entities gracefully', async () => {
    const nonExistentId = generateUUID();

    // Should not throw even if entity doesn't exist
    await expect(clearQueuedMarkers('accounts', [nonExistentId])).resolves.toBeUndefined();
  });
});
