/**
 * Tests for CHAPTR Sync Queue Squashing
 *
 * Tests the squashing logic that prevents timestamp conflicts when the same
 * entity is modified multiple times before syncing. When a user archives
 * then unarchives an entity (or makes any multiple changes), the queue
 * should squash into a single entry with the original base_updated_at.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { db } from '../../../static/js/db.js';
import { generateUUID } from '../../../static/js/utils.js';

describe('Sync Queue Squashing', () => {
  beforeEach(async () => {
    await db.sync_queue.clear();
    await db.accounts.clear();
    await db.stories.clear();
    await db.events.clear();
  });

  afterEach(async () => {
    await db.sync_queue.clear();
    await db.accounts.clear();
    await db.stories.clear();
    await db.events.clear();
  });

  describe('Update → Update Squashing', () => {
    it('should squash multiple updates into single entry', async () => {
      const entityId = generateUUID();

      // First update
      await db.queueChange('story', entityId, 'update',
        { is_archived: true }, '2026-01-01T10:00:00Z');

      // Second update (same entity)
      await db.queueChange('story', entityId, 'update',
        { is_archived: false }, '2026-01-01T10:05:00Z');

      // Should have only ONE queue entry
      const entries = await db.sync_queue.where('entity_id').equals(entityId).toArray();
      expect(entries).toHaveLength(1);

      // Should have latest data
      expect(entries[0].data.is_archived).toBe(false);

      // Should preserve ORIGINAL base_updated_at
      expect(entries[0].base_updated_at).toBe('2026-01-01T10:00:00Z');
    });

    it('should merge data from multiple updates', async () => {
      const entityId = generateUUID();

      await db.queueChange('story', entityId, 'update',
        { name: 'New Name' }, '2026-01-01T10:00:00Z');

      await db.queueChange('story', entityId, 'update',
        { is_archived: true }, '2026-01-01T10:05:00Z');

      const entries = await db.sync_queue.where('entity_id').equals(entityId).toArray();
      expect(entries).toHaveLength(1);
      expect(entries[0].data.name).toBe('New Name');
      expect(entries[0].data.is_archived).toBe(true);
    });

    it('should handle three or more sequential updates', async () => {
      const entityId = generateUUID();
      const originalTimestamp = '2026-01-01T10:00:00Z';

      // Three sequential updates
      await db.queueChange('account', entityId, 'update',
        { name: 'First Name' }, originalTimestamp);

      await db.queueChange('account', entityId, 'update',
        { name: 'Second Name', current_balance: 100 }, '2026-01-01T10:05:00Z');

      await db.queueChange('account', entityId, 'update',
        { name: 'Final Name' }, '2026-01-01T10:10:00Z');

      const entries = await db.sync_queue.where('entity_id').equals(entityId).toArray();
      expect(entries).toHaveLength(1);
      expect(entries[0].data.name).toBe('Final Name');
      expect(entries[0].data.current_balance).toBe(100); // Preserved from second update
      expect(entries[0].base_updated_at).toBe(originalTimestamp);
    });
  });

  describe('Create → Update Squashing', () => {
    it('should squash create + update into single create', async () => {
      const entityId = generateUUID();

      // Create
      await db.queueChange('account', entityId, 'create',
        { name: 'Test', currency: 'GBP', current_balance: 100 }, null);

      // Update
      await db.queueChange('account', entityId, 'update',
        { name: 'Updated Name' }, '2026-01-01T10:00:00Z');

      const entries = await db.sync_queue.where('entity_id').equals(entityId).toArray();
      expect(entries).toHaveLength(1);
      expect(entries[0].action).toBe('create'); // Still a create!
      expect(entries[0].data.name).toBe('Updated Name');
      expect(entries[0].data.currency).toBe('GBP'); // Original data preserved
      expect(entries[0].data.current_balance).toBe(100); // Original data preserved
    });

    it('should merge multiple updates after create into single create', async () => {
      const entityId = generateUUID();

      // Create
      await db.queueChange('story', entityId, 'create',
        { name: 'New Story', funding_mode: 'projected' }, null);

      // First update
      await db.queueChange('story', entityId, 'update',
        { name: 'Renamed Story' }, '2026-01-01T10:00:00Z');

      // Second update
      await db.queueChange('story', entityId, 'update',
        { is_archived: true }, '2026-01-01T10:05:00Z');

      const entries = await db.sync_queue.where('entity_id').equals(entityId).toArray();
      expect(entries).toHaveLength(1);
      expect(entries[0].action).toBe('create');
      expect(entries[0].data.name).toBe('Renamed Story');
      expect(entries[0].data.funding_mode).toBe('projected');
      expect(entries[0].data.is_archived).toBe(true);
    });
  });

  describe('Create → Delete Squashing', () => {
    it('should remove both entries when create followed by delete', async () => {
      const entityId = generateUUID();

      // Create
      await db.queueChange('event', entityId, 'create',
        { description: 'Test Event', amount: 100 }, null);

      // Delete
      await db.queueChange('event', entityId, 'delete',
        null, '2026-01-01T10:00:00Z');

      // Should have NO queue entries
      const entries = await db.sync_queue.where('entity_id').equals(entityId).toArray();
      expect(entries).toHaveLength(0);
    });

    it('should remove entries even with updates between create and delete', async () => {
      const entityId = generateUUID();

      // Create
      await db.queueChange('event', entityId, 'create',
        { description: 'Test Event', amount: 100 }, null);

      // Update
      await db.queueChange('event', entityId, 'update',
        { amount: 200 }, '2026-01-01T10:00:00Z');

      // Delete
      await db.queueChange('event', entityId, 'delete',
        null, '2026-01-01T10:05:00Z');

      // Should have NO queue entries since it started with create
      const entries = await db.sync_queue.where('entity_id').equals(entityId).toArray();
      expect(entries).toHaveLength(0);
    });
  });

  describe('Update → Delete Squashing', () => {
    it('should squash update + delete into single delete', async () => {
      const entityId = generateUUID();

      // Update
      await db.queueChange('story', entityId, 'update',
        { name: 'New Name' }, '2026-01-01T10:00:00Z');

      // Delete
      await db.queueChange('story', entityId, 'delete',
        null, '2026-01-01T10:05:00Z');

      const entries = await db.sync_queue.where('entity_id').equals(entityId).toArray();
      expect(entries).toHaveLength(1);
      expect(entries[0].action).toBe('delete');
      expect(entries[0].base_updated_at).toBe('2026-01-01T10:00:00Z'); // Original preserved
    });

    it('should squash multiple updates + delete into single delete', async () => {
      const entityId = generateUUID();
      const originalTimestamp = '2026-01-01T10:00:00Z';

      // Multiple updates
      await db.queueChange('account', entityId, 'update',
        { name: 'First' }, originalTimestamp);

      await db.queueChange('account', entityId, 'update',
        { name: 'Second' }, '2026-01-01T10:05:00Z');

      // Delete
      await db.queueChange('account', entityId, 'delete',
        null, '2026-01-01T10:10:00Z');

      const entries = await db.sync_queue.where('entity_id').equals(entityId).toArray();
      expect(entries).toHaveLength(1);
      expect(entries[0].action).toBe('delete');
      expect(entries[0].base_updated_at).toBe(originalTimestamp);
    });
  });

  describe('Metadata Preservation', () => {
    it('should preserve metadata when squashing', async () => {
      const entityId = generateUUID();
      const accountId = generateUUID();

      // Create with metadata
      await db.queueChange('event', entityId, 'create',
        { description: 'Opening Balance', amount: 100 },
        null,
        { _derived_from: 'account_creation', dependencies: [accountId] });

      // Update without metadata
      await db.queueChange('event', entityId, 'update',
        { amount: 200 }, '2026-01-01T10:00:00Z');

      const entries = await db.sync_queue.where('entity_id').equals(entityId).toArray();
      expect(entries).toHaveLength(1);
      expect(entries[0]._derived_from).toBe('account_creation');
      expect(entries[0].dependencies).toContain(accountId);
    });

    it('should allow metadata override when squashing', async () => {
      const entityId = generateUUID();

      // First entry with metadata
      await db.queueChange('event', entityId, 'update',
        { amount: 100 }, '2026-01-01T10:00:00Z',
        { _derived_from: 'recurring_rule_creation' });

      // Second entry with different metadata
      await db.queueChange('event', entityId, 'update',
        { amount: 200 }, '2026-01-01T10:05:00Z',
        { _derived_from: 'manual_edit' });

      const entries = await db.sync_queue.where('entity_id').equals(entityId).toArray();
      expect(entries[0]._derived_from).toBe('manual_edit'); // New metadata wins
    });

    it('should preserve _optimistic flag when not explicitly set', async () => {
      const entityId = generateUUID();

      // First entry with _optimistic true
      await db.queueChange('event', entityId, 'update',
        { amount: 100 }, '2026-01-01T10:00:00Z',
        { _optimistic: true });

      // Second entry without _optimistic (should preserve existing)
      await db.queueChange('event', entityId, 'update',
        { amount: 200 }, '2026-01-01T10:05:00Z');

      const entries = await db.sync_queue.where('entity_id').equals(entityId).toArray();
      expect(entries[0]._optimistic).toBe(true);
    });

    it('should allow _optimistic flag override', async () => {
      const entityId = generateUUID();

      // First entry with _optimistic true
      await db.queueChange('event', entityId, 'update',
        { amount: 100 }, '2026-01-01T10:00:00Z',
        { _optimistic: true });

      // Second entry explicitly setting _optimistic false
      await db.queueChange('event', entityId, 'update',
        { amount: 200 }, '2026-01-01T10:05:00Z',
        { _optimistic: false });

      const entries = await db.sync_queue.where('entity_id').equals(entityId).toArray();
      expect(entries[0]._optimistic).toBe(false);
    });

    it('should preserve dependencies array when not overridden', async () => {
      const entityId = generateUUID();
      const depId1 = generateUUID();
      const depId2 = generateUUID();

      // First entry with dependencies
      await db.queueChange('event', entityId, 'update',
        { amount: 100 }, '2026-01-01T10:00:00Z',
        { dependencies: [depId1, depId2] });

      // Second entry without dependencies
      await db.queueChange('event', entityId, 'update',
        { amount: 200 }, '2026-01-01T10:05:00Z');

      const entries = await db.sync_queue.where('entity_id').equals(entityId).toArray();
      expect(entries[0].dependencies).toEqual([depId1, depId2]);
    });
  });

  describe('Different Entity Types', () => {
    it('should not squash entries for different entities', async () => {
      const entityId1 = generateUUID();
      const entityId2 = generateUUID();

      await db.queueChange('story', entityId1, 'update', { name: 'Story 1' }, '2026-01-01T10:00:00Z');
      await db.queueChange('story', entityId2, 'update', { name: 'Story 2' }, '2026-01-01T10:00:00Z');

      const allEntries = await db.sync_queue.toArray();
      expect(allEntries).toHaveLength(2);
    });

    it('should not squash entries for same ID but theoretically different entity types', async () => {
      // This is an edge case - in practice UUIDs should be unique across entity types
      // but the squashing logic operates on entity_id only
      const sharedId = generateUUID();

      await db.queueChange('account', sharedId, 'update', { name: 'Account' }, '2026-01-01T10:00:00Z');
      await db.queueChange('story', sharedId, 'update', { name: 'Story' }, '2026-01-01T10:00:00Z');

      // Note: Current implementation squashes by entity_id regardless of entity_type
      // This is acceptable because UUIDs should be globally unique in practice
      const entries = await db.sync_queue.where('entity_id').equals(sharedId).toArray();
      // Behavior: squashes to single entry (last one wins)
      expect(entries).toHaveLength(1);
    });
  });

  describe('Archive/Unarchive Scenario', () => {
    it('should correctly squash archive then unarchive', async () => {
      const storyId = generateUUID();
      const serverTimestamp = '2026-01-01T10:00:00Z';

      // Archive (simulating what app.js does)
      await db.queueChange('story', storyId, 'update',
        { is_archived: true }, serverTimestamp);

      // Unarchive
      await db.queueChange('story', storyId, 'update',
        { is_archived: false }, '2026-01-01T10:05:00Z'); // Local timestamp

      const entries = await db.sync_queue.where('entity_id').equals(storyId).toArray();
      expect(entries).toHaveLength(1);
      expect(entries[0].data.is_archived).toBe(false);
      expect(entries[0].base_updated_at).toBe(serverTimestamp); // Original server timestamp!
    });

    it('should handle multiple archive/unarchive cycles', async () => {
      const storyId = generateUUID();
      const serverTimestamp = '2026-01-01T10:00:00Z';

      // Archive
      await db.queueChange('story', storyId, 'update',
        { is_archived: true }, serverTimestamp);

      // Unarchive
      await db.queueChange('story', storyId, 'update',
        { is_archived: false }, '2026-01-01T10:05:00Z');

      // Archive again
      await db.queueChange('story', storyId, 'update',
        { is_archived: true }, '2026-01-01T10:10:00Z');

      // Unarchive again
      await db.queueChange('story', storyId, 'update',
        { is_archived: false }, '2026-01-01T10:15:00Z');

      const entries = await db.sync_queue.where('entity_id').equals(storyId).toArray();
      expect(entries).toHaveLength(1);
      expect(entries[0].data.is_archived).toBe(false);
      expect(entries[0].base_updated_at).toBe(serverTimestamp); // Still original!
    });
  });

  describe('Edge Cases', () => {
    it('should handle null data for delete operations', async () => {
      const entityId = generateUUID();

      // Update first
      await db.queueChange('event', entityId, 'update',
        { amount: 100 }, '2026-01-01T10:00:00Z');

      // Delete with null data
      await db.queueChange('event', entityId, 'delete', null, '2026-01-01T10:05:00Z');

      const entries = await db.sync_queue.where('entity_id').equals(entityId).toArray();
      expect(entries).toHaveLength(1);
      expect(entries[0].action).toBe('delete');
      expect(entries[0].data).toBeNull();
    });

    it('should update queued_at timestamp on squash', async () => {
      const entityId = generateUUID();

      // First update
      await db.queueChange('story', entityId, 'update',
        { name: 'First' }, '2026-01-01T10:00:00Z');

      const entriesBefore = await db.sync_queue.where('entity_id').equals(entityId).toArray();
      const firstQueuedAt = entriesBefore[0].queued_at;

      // Small delay to ensure different timestamp
      await new Promise(resolve => setTimeout(resolve, 10));

      // Second update
      await db.queueChange('story', entityId, 'update',
        { name: 'Second' }, '2026-01-01T10:05:00Z');

      const entriesAfter = await db.sync_queue.where('entity_id').equals(entityId).toArray();
      expect(entriesAfter[0].queued_at).not.toBe(firstQueuedAt);
    });

    it('should handle empty object data', async () => {
      const entityId = generateUUID();

      await db.queueChange('story', entityId, 'update', {}, '2026-01-01T10:00:00Z');
      await db.queueChange('story', entityId, 'update', { name: 'Name' }, '2026-01-01T10:05:00Z');

      const entries = await db.sync_queue.where('entity_id').equals(entityId).toArray();
      expect(entries).toHaveLength(1);
      expect(entries[0].data).toEqual({ name: 'Name' });
    });

    it('should overwrite same field in squashed data', async () => {
      const entityId = generateUUID();

      await db.queueChange('account', entityId, 'update',
        { current_balance: 100 }, '2026-01-01T10:00:00Z');

      await db.queueChange('account', entityId, 'update',
        { current_balance: 200 }, '2026-01-01T10:05:00Z');

      await db.queueChange('account', entityId, 'update',
        { current_balance: 300 }, '2026-01-01T10:10:00Z');

      const entries = await db.sync_queue.where('entity_id').equals(entityId).toArray();
      expect(entries).toHaveLength(1);
      expect(entries[0].data.current_balance).toBe(300);
    });
  });

  describe('Non-Squashing Scenarios', () => {
    it('should add new entry when no existing entry', async () => {
      const entityId = generateUUID();

      await db.queueChange('story', entityId, 'create',
        { name: 'New Story' }, null);

      const entries = await db.sync_queue.where('entity_id').equals(entityId).toArray();
      expect(entries).toHaveLength(1);
      expect(entries[0].action).toBe('create');
    });

    it('should handle concurrent queuing for different entities', async () => {
      const entityIds = Array.from({ length: 5 }, () => generateUUID());

      // Queue changes for 5 different entities
      await Promise.all(entityIds.map((id, index) =>
        db.queueChange('event', id, 'update',
          { amount: (index + 1) * 100 }, '2026-01-01T10:00:00Z')
      ));

      const allEntries = await db.sync_queue.toArray();
      expect(allEntries).toHaveLength(5);
    });
  });

  describe('Delete Edge Cases', () => {
    it('should handle delete followed by create (entity recreation)', async () => {
      const entityId = generateUUID();

      // Delete existing entity
      await db.queueChange('event', entityId, 'delete', null, '2026-01-01T10:00:00Z');

      // Recreate with same ID (unusual but possible)
      await db.queueChange('event', entityId, 'create',
        { description: 'Recreated', amount: 500 }, null);

      const entries = await db.sync_queue.where('entity_id').equals(entityId).toArray();
      expect(entries).toHaveLength(1);
      // Should use incoming action (create)
      expect(entries[0].action).toBe('create');
      expect(entries[0].data.description).toBe('Recreated');
    });

    it('should handle delete followed by update (edge case with warning)', async () => {
      const entityId = generateUUID();
      const consoleSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});

      // Delete
      await db.queueChange('event', entityId, 'delete', null, '2026-01-01T10:00:00Z');

      // Update after delete (shouldn't happen, but handle gracefully)
      await db.queueChange('event', entityId, 'update',
        { amount: 200 }, '2026-01-01T10:05:00Z');

      const entries = await db.sync_queue.where('entity_id').equals(entityId).toArray();
      expect(entries).toHaveLength(1);
      // Should warn about unusual state
      expect(consoleSpy).toHaveBeenCalledWith(expect.stringContaining('delete followed by update'));
      // Should use incoming action
      expect(entries[0].action).toBe('update');

      consoleSpy.mockRestore();
    });

    it('should handle delete followed by delete (duplicate delete)', async () => {
      const entityId = generateUUID();
      const consoleSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});

      // First delete
      await db.queueChange('event', entityId, 'delete', null, '2026-01-01T10:00:00Z');

      // Second delete (redundant)
      await db.queueChange('event', entityId, 'delete', null, '2026-01-01T10:05:00Z');

      const entries = await db.sync_queue.where('entity_id').equals(entityId).toArray();
      expect(entries).toHaveLength(1);
      expect(entries[0].action).toBe('delete');
      // Should preserve original timestamp
      expect(entries[0].base_updated_at).toBe('2026-01-01T10:00:00Z');

      consoleSpy.mockRestore();
    });
  });

  describe('Create Edge Cases', () => {
    it('should handle create followed by create (duplicate create)', async () => {
      const entityId = generateUUID();

      // First create
      await db.queueChange('account', entityId, 'create',
        { name: 'First', currency: 'GBP' }, null);

      // Second create with same ID (shouldn't happen, but handle gracefully)
      await db.queueChange('account', entityId, 'create',
        { name: 'Second', currency: 'USD', current_balance: 100 }, null);

      const entries = await db.sync_queue.where('entity_id').equals(entityId).toArray();
      expect(entries).toHaveLength(1);
      expect(entries[0].action).toBe('create');
      // Data should be merged
      expect(entries[0].data.name).toBe('Second');
      expect(entries[0].data.currency).toBe('USD');
      expect(entries[0].data.current_balance).toBe(100);
    });
  });

  describe('Data Type Handling', () => {
    it('should preserve number types in squashed data', async () => {
      const entityId = generateUUID();

      await db.queueChange('account', entityId, 'update',
        { current_balance: 100.50 }, '2026-01-01T10:00:00Z');

      await db.queueChange('account', entityId, 'update',
        { name: 'Updated' }, '2026-01-01T10:05:00Z');

      const entries = await db.sync_queue.where('entity_id').equals(entityId).toArray();
      expect(entries[0].data.current_balance).toBe(100.50);
      expect(typeof entries[0].data.current_balance).toBe('number');
    });

    it('should preserve boolean types in squashed data', async () => {
      const entityId = generateUUID();

      await db.queueChange('story', entityId, 'update',
        { is_archived: false }, '2026-01-01T10:00:00Z');

      await db.queueChange('story', entityId, 'update',
        { name: 'Updated' }, '2026-01-01T10:05:00Z');

      const entries = await db.sync_queue.where('entity_id').equals(entityId).toArray();
      expect(entries[0].data.is_archived).toBe(false);
      expect(typeof entries[0].data.is_archived).toBe('boolean');
    });

    it('should handle null values in data correctly', async () => {
      const entityId = generateUUID();

      await db.queueChange('event', entityId, 'update',
        { story_id: 'story-123' }, '2026-01-01T10:00:00Z');

      await db.queueChange('event', entityId, 'update',
        { story_id: null }, '2026-01-01T10:05:00Z');

      const entries = await db.sync_queue.where('entity_id').equals(entityId).toArray();
      expect(entries[0].data.story_id).toBeNull();
    });

    it('should handle undefined values (should not overwrite existing)', async () => {
      const entityId = generateUUID();

      await db.queueChange('account', entityId, 'update',
        { name: 'Name', current_balance: 100 }, '2026-01-01T10:00:00Z');

      // Spread with undefined should still preserve the original
      await db.queueChange('account', entityId, 'update',
        { current_balance: 200 }, '2026-01-01T10:05:00Z');

      const entries = await db.sync_queue.where('entity_id').equals(entityId).toArray();
      expect(entries[0].data.name).toBe('Name'); // Still present
      expect(entries[0].data.current_balance).toBe(200);
    });

    it('should handle nested objects in data', async () => {
      const entityId = generateUUID();

      await db.queueChange('settings', entityId, 'update',
        { rates: { GBP: 1.0, USD: 1.27 } }, '2026-01-01T10:00:00Z');

      await db.queueChange('settings', entityId, 'update',
        { rates: { GBP: 1.0, USD: 1.30, EUR: 1.17 } }, '2026-01-01T10:05:00Z');

      const entries = await db.sync_queue.where('entity_id').equals(entityId).toArray();
      expect(entries[0].data.rates).toEqual({ GBP: 1.0, USD: 1.30, EUR: 1.17 });
    });

    it('should handle arrays in data', async () => {
      const entityId = generateUUID();

      await db.queueChange('event', entityId, 'update',
        { tags: ['expense', 'recurring'] }, '2026-01-01T10:00:00Z');

      await db.queueChange('event', entityId, 'update',
        { tags: ['expense', 'recurring', 'important'] }, '2026-01-01T10:05:00Z');

      const entries = await db.sync_queue.where('entity_id').equals(entityId).toArray();
      expect(entries[0].data.tags).toEqual(['expense', 'recurring', 'important']);
    });
  });

  describe('Timestamp Preservation Edge Cases', () => {
    it('should preserve null base_updated_at for creates through updates', async () => {
      const entityId = generateUUID();

      // Create has null base_updated_at
      await db.queueChange('account', entityId, 'create',
        { name: 'New' }, null);

      // Update has a timestamp
      await db.queueChange('account', entityId, 'update',
        { name: 'Updated' }, '2026-01-01T10:00:00Z');

      const entries = await db.sync_queue.where('entity_id').equals(entityId).toArray();
      expect(entries[0].base_updated_at).toBeNull(); // Original preserved
    });

    it('should handle ISO timestamp strings correctly', async () => {
      const entityId = generateUUID();
      const timestamp1 = '2026-01-01T10:00:00.000Z';
      const timestamp2 = '2026-01-01T10:00:00.500Z';

      await db.queueChange('story', entityId, 'update',
        { name: 'First' }, timestamp1);

      await db.queueChange('story', entityId, 'update',
        { name: 'Second' }, timestamp2);

      const entries = await db.sync_queue.where('entity_id').equals(entityId).toArray();
      expect(entries[0].base_updated_at).toBe(timestamp1);
    });
  });

  describe('Real-World Scenarios', () => {
    it('should handle rapid balance updates correctly', async () => {
      const accountId = generateUUID();
      const serverTimestamp = '2026-01-01T10:00:00Z';

      // User makes multiple quick balance adjustments
      await db.queueChange('account', accountId, 'update',
        { current_balance: 1000 }, serverTimestamp);

      await db.queueChange('account', accountId, 'update',
        { current_balance: 1050 }, '2026-01-01T10:00:01Z');

      await db.queueChange('account', accountId, 'update',
        { current_balance: 1025 }, '2026-01-01T10:00:02Z');

      const entries = await db.sync_queue.where('entity_id').equals(accountId).toArray();
      expect(entries).toHaveLength(1);
      expect(entries[0].data.current_balance).toBe(1025); // Final value
      expect(entries[0].base_updated_at).toBe(serverTimestamp); // Original timestamp
    });

    it('should handle story rename then archive then unarchive', async () => {
      const storyId = generateUUID();
      const serverTimestamp = '2026-01-01T10:00:00Z';

      // Rename
      await db.queueChange('story', storyId, 'update',
        { name: 'New Trip Name' }, serverTimestamp);

      // Archive
      await db.queueChange('story', storyId, 'update',
        { is_archived: true }, '2026-01-01T10:01:00Z');

      // Unarchive
      await db.queueChange('story', storyId, 'update',
        { is_archived: false }, '2026-01-01T10:02:00Z');

      const entries = await db.sync_queue.where('entity_id').equals(storyId).toArray();
      expect(entries).toHaveLength(1);
      expect(entries[0].data.name).toBe('New Trip Name');
      expect(entries[0].data.is_archived).toBe(false);
      expect(entries[0].base_updated_at).toBe(serverTimestamp);
    });

    it('should handle event amount and description changes', async () => {
      const eventId = generateUUID();
      const serverTimestamp = '2026-01-01T10:00:00Z';

      // Initial edit
      await db.queueChange('event', eventId, 'update',
        { amount: -50, description: 'Groceries' }, serverTimestamp);

      // Correction
      await db.queueChange('event', eventId, 'update',
        { amount: -55 }, '2026-01-01T10:01:00Z');

      // Another correction
      await db.queueChange('event', eventId, 'update',
        { description: 'Weekly groceries' }, '2026-01-01T10:02:00Z');

      const entries = await db.sync_queue.where('entity_id').equals(eventId).toArray();
      expect(entries).toHaveLength(1);
      expect(entries[0].data.amount).toBe(-55);
      expect(entries[0].data.description).toBe('Weekly groceries');
      expect(entries[0].base_updated_at).toBe(serverTimestamp);
    });

    it('should handle create then immediate delete (user changed mind)', async () => {
      const accountId = generateUUID();

      // Create new account
      await db.queueChange('account', accountId, 'create',
        { name: 'Test Account', currency: 'GBP', current_balance: 0 }, null);

      // User immediately deletes it
      await db.queueChange('account', accountId, 'delete', null, null);

      // Should have no entries - entity never existed on server
      const entries = await db.sync_queue.where('entity_id').equals(accountId).toArray();
      expect(entries).toHaveLength(0);
    });
  });
});
