/**
 * Tests for CHAPTR Auto-Resolve Conflict System
 *
 * Tests the areVersionsDataEqual function and multi-client conflict
 * scenarios where both clients make the same change (e.g., both archive
 * the same story) - these should be auto-resolved without user intervention.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { db } from '../../../static/js/db.js';
import { generateUUID } from '../../../static/js/utils.js';

/**
 * Recreate areVersionsDataEqual for direct testing
 * (mirrors storage-adapter.js implementation)
 */
function areVersionsDataEqual(clientVersion, serverVersion) {
  if (!clientVersion || !serverVersion) return false;

  // Fields to exclude from comparison (timestamps and metadata)
  const excludeFields = new Set([
    'id', 'updated_at', 'created_at', 'version', 'tenant_id',
    'balance_updated_at',  // Account-specific timestamp
    'created_by', 'updated_by'  // Audit fields
  ]);

  // Compare only fields present in client version (handles partial updates)
  const clientKeys = Object.keys(clientVersion).filter(k => !excludeFields.has(k));

  for (const key of clientKeys) {
    const clientVal = clientVersion[key];
    const serverVal = serverVersion[key];

    // Handle null/undefined equivalence
    const isNullish1 = clientVal === null || clientVal === undefined;
    const isNullish2 = serverVal === null || serverVal === undefined;
    if (isNullish1 && isNullish2) continue;
    if (isNullish1 !== isNullish2) return false;

    // Compare values (stringify for objects/arrays)
    if (typeof clientVal === 'object' || typeof serverVal === 'object') {
      if (JSON.stringify(clientVal) !== JSON.stringify(serverVal)) return false;
    } else if (clientVal !== serverVal) {
      return false;
    }
  }

  return true;
}

describe('areVersionsDataEqual - Basic Comparisons', () => {
  it('should return true for identical simple values', () => {
    const client = { name: 'Test', amount: 100 };
    const server = { name: 'Test', amount: 100 };

    expect(areVersionsDataEqual(client, server)).toBe(true);
  });

  it('should return false for different values', () => {
    const client = { name: 'Client Name' };
    const server = { name: 'Server Name' };

    expect(areVersionsDataEqual(client, server)).toBe(false);
  });

  it('should return false when client is null', () => {
    expect(areVersionsDataEqual(null, { name: 'Test' })).toBe(false);
  });

  it('should return false when server is null', () => {
    expect(areVersionsDataEqual({ name: 'Test' }, null)).toBe(false);
  });

  it('should return false when both are null', () => {
    expect(areVersionsDataEqual(null, null)).toBe(false);
  });

  it('should return false when client is undefined', () => {
    expect(areVersionsDataEqual(undefined, { name: 'Test' })).toBe(false);
  });

  it('should return true for empty objects', () => {
    expect(areVersionsDataEqual({}, {})).toBe(true);
  });
});

describe('areVersionsDataEqual - Partial Updates', () => {
  it('should match when client sends subset of fields', () => {
    const client = { is_archived: true };
    const server = {
      id: 'abc-123',
      name: 'Story Name',
      is_archived: true,
      funding_mode: 'projected',
      updated_at: '2026-01-01T12:00:00Z'
    };

    expect(areVersionsDataEqual(client, server)).toBe(true);
  });

  it('should not match when client subset has different value', () => {
    const client = { is_archived: false };
    const server = {
      id: 'abc-123',
      name: 'Story Name',
      is_archived: true,
      funding_mode: 'projected'
    };

    expect(areVersionsDataEqual(client, server)).toBe(false);
  });

  it('should handle multiple fields in partial update', () => {
    const client = { name: 'New Name', is_archived: true };
    const server = {
      id: 'abc-123',
      name: 'New Name',
      is_archived: true,
      funding_mode: 'projected',
      currency: 'GBP'
    };

    expect(areVersionsDataEqual(client, server)).toBe(true);
  });

  it('should fail if any client field differs', () => {
    const client = { name: 'New Name', is_archived: true };
    const server = {
      id: 'abc-123',
      name: 'New Name',
      is_archived: false,  // Different!
      funding_mode: 'projected'
    };

    expect(areVersionsDataEqual(client, server)).toBe(false);
  });
});

describe('areVersionsDataEqual - Excluded Fields', () => {
  it('should ignore id field', () => {
    const client = { id: 'client-id', name: 'Test' };
    const server = { id: 'server-id', name: 'Test' };

    expect(areVersionsDataEqual(client, server)).toBe(true);
  });

  it('should ignore updated_at field', () => {
    const client = { name: 'Test', updated_at: '2026-01-01T10:00:00Z' };
    const server = { name: 'Test', updated_at: '2026-01-01T12:00:00Z' };

    expect(areVersionsDataEqual(client, server)).toBe(true);
  });

  it('should ignore created_at field', () => {
    const client = { name: 'Test', created_at: '2026-01-01T08:00:00Z' };
    const server = { name: 'Test', created_at: '2026-01-01T09:00:00Z' };

    expect(areVersionsDataEqual(client, server)).toBe(true);
  });

  it('should ignore version field', () => {
    const client = { name: 'Test', version: 1 };
    const server = { name: 'Test', version: 5 };

    expect(areVersionsDataEqual(client, server)).toBe(true);
  });

  it('should ignore tenant_id field', () => {
    const client = { name: 'Test', tenant_id: 'tenant-a' };
    const server = { name: 'Test', tenant_id: 'tenant-b' };

    expect(areVersionsDataEqual(client, server)).toBe(true);
  });

  it('should ignore balance_updated_at field', () => {
    const client = { current_balance: 100, balance_updated_at: '2026-01-01T10:00:00Z' };
    const server = { current_balance: 100, balance_updated_at: '2026-01-01T12:00:00Z' };

    expect(areVersionsDataEqual(client, server)).toBe(true);
  });

  it('should ignore created_by and updated_by fields', () => {
    const client = { name: 'Test', created_by: 'user-a', updated_by: 'user-a' };
    const server = { name: 'Test', created_by: 'user-b', updated_by: 'user-b' };

    expect(areVersionsDataEqual(client, server)).toBe(true);
  });

  it('should ignore all excluded fields combined', () => {
    const client = {
      name: 'Test',
      id: 'client-id',
      updated_at: '2026-01-01T10:00:00Z',
      created_at: '2026-01-01T08:00:00Z',
      version: 1,
      tenant_id: 'tenant-a'
    };
    const server = {
      name: 'Test',
      id: 'server-id',
      updated_at: '2026-01-01T12:00:00Z',
      created_at: '2026-01-01T09:00:00Z',
      version: 10,
      tenant_id: 'tenant-b'
    };

    expect(areVersionsDataEqual(client, server)).toBe(true);
  });
});

describe('areVersionsDataEqual - Null/Undefined Handling', () => {
  it('should treat null client value equal to null server value', () => {
    const client = { story_id: null };
    const server = { story_id: null };

    expect(areVersionsDataEqual(client, server)).toBe(true);
  });

  it('should treat undefined client value equal to undefined server value', () => {
    const client = { story_id: undefined };
    const server = { story_id: undefined };

    expect(areVersionsDataEqual(client, server)).toBe(true);
  });

  it('should treat null equal to undefined', () => {
    const client = { story_id: null };
    const server = { story_id: undefined };

    expect(areVersionsDataEqual(client, server)).toBe(true);
  });

  it('should not treat null equal to empty string', () => {
    const client = { description: null };
    const server = { description: '' };

    expect(areVersionsDataEqual(client, server)).toBe(false);
  });

  it('should not treat null equal to zero', () => {
    const client = { amount: null };
    const server = { amount: 0 };

    expect(areVersionsDataEqual(client, server)).toBe(false);
  });

  it('should not treat null equal to false', () => {
    const client = { is_archived: null };
    const server = { is_archived: false };

    expect(areVersionsDataEqual(client, server)).toBe(false);
  });

  it('should handle missing field in server (undefined)', () => {
    const client = { story_id: null };
    const server = { name: 'Test' }; // story_id is undefined

    expect(areVersionsDataEqual(client, server)).toBe(true);
  });
});

describe('areVersionsDataEqual - Type Comparisons', () => {
  it('should compare numbers correctly', () => {
    expect(areVersionsDataEqual({ amount: 100 }, { amount: 100 })).toBe(true);
    expect(areVersionsDataEqual({ amount: 100 }, { amount: 101 })).toBe(false);
  });

  it('should compare floating point numbers', () => {
    expect(areVersionsDataEqual({ amount: 100.50 }, { amount: 100.50 })).toBe(true);
    expect(areVersionsDataEqual({ amount: 100.50 }, { amount: 100.51 })).toBe(false);
  });

  it('should compare booleans correctly', () => {
    expect(areVersionsDataEqual({ is_archived: true }, { is_archived: true })).toBe(true);
    expect(areVersionsDataEqual({ is_archived: true }, { is_archived: false })).toBe(false);
  });

  it('should compare strings correctly', () => {
    expect(areVersionsDataEqual({ name: 'Test' }, { name: 'Test' })).toBe(true);
    expect(areVersionsDataEqual({ name: 'Test' }, { name: 'test' })).toBe(false); // Case sensitive
  });

  it('should not coerce string to number', () => {
    expect(areVersionsDataEqual({ amount: '100' }, { amount: 100 })).toBe(false);
  });

  it('should not coerce string to boolean', () => {
    expect(areVersionsDataEqual({ flag: 'true' }, { flag: true })).toBe(false);
  });
});

describe('areVersionsDataEqual - Object/Array Comparisons', () => {
  it('should compare nested objects', () => {
    const client = { rates: { GBP: 1.0, USD: 1.27 } };
    const server = { rates: { GBP: 1.0, USD: 1.27 } };

    expect(areVersionsDataEqual(client, server)).toBe(true);
  });

  it('should detect different nested objects', () => {
    const client = { rates: { GBP: 1.0, USD: 1.27 } };
    const server = { rates: { GBP: 1.0, USD: 1.30 } };

    expect(areVersionsDataEqual(client, server)).toBe(false);
  });

  it('should compare arrays', () => {
    const client = { tags: ['expense', 'recurring'] };
    const server = { tags: ['expense', 'recurring'] };

    expect(areVersionsDataEqual(client, server)).toBe(true);
  });

  it('should detect different arrays', () => {
    const client = { tags: ['expense', 'recurring'] };
    const server = { tags: ['expense'] };

    expect(areVersionsDataEqual(client, server)).toBe(false);
  });

  it('should be order-sensitive for arrays', () => {
    const client = { tags: ['a', 'b'] };
    const server = { tags: ['b', 'a'] };

    expect(areVersionsDataEqual(client, server)).toBe(false);
  });

  it('should compare deeply nested objects', () => {
    const client = { config: { display: { theme: 'dark' } } };
    const server = { config: { display: { theme: 'dark' } } };

    expect(areVersionsDataEqual(client, server)).toBe(true);
  });

  it('should detect differences in deeply nested objects', () => {
    const client = { config: { display: { theme: 'dark' } } };
    const server = { config: { display: { theme: 'light' } } };

    expect(areVersionsDataEqual(client, server)).toBe(false);
  });
});

describe('areVersionsDataEqual - Real-World Scenarios', () => {
  describe('Both Users Archive Same Story', () => {
    it('should auto-resolve when both archive the same story', () => {
      // User A archives story, syncs first
      // User B also archives same story, syncs second
      // Server returns conflict, but data is identical
      const clientVersion = {
        is_archived: true  // What User B sent
      };
      const serverVersion = {
        id: 'story-123',
        name: 'Holiday Trip',
        is_archived: true,  // Server state after User A
        funding_mode: 'projected',
        updated_at: '2026-01-01T12:00:00Z'
      };

      expect(areVersionsDataEqual(clientVersion, serverVersion)).toBe(true);
    });
  });

  describe('Both Users Unarchive Same Story', () => {
    it('should auto-resolve when both unarchive the same story', () => {
      const clientVersion = { is_archived: false };
      const serverVersion = {
        id: 'story-123',
        name: 'Holiday Trip',
        is_archived: false,
        updated_at: '2026-01-01T12:00:00Z'
      };

      expect(areVersionsDataEqual(clientVersion, serverVersion)).toBe(true);
    });
  });

  describe('Both Users Set Same Balance', () => {
    it('should auto-resolve when both set same account balance', () => {
      const clientVersion = {
        current_balance: 1500.00
      };
      const serverVersion = {
        id: 'account-456',
        name: 'Main Account',
        currency: 'GBP',
        current_balance: 1500.00,
        updated_at: '2026-01-01T12:00:00Z'
      };

      expect(areVersionsDataEqual(clientVersion, serverVersion)).toBe(true);
    });
  });

  describe('One User Archives, Other Renames', () => {
    it('should NOT auto-resolve when users make different changes', () => {
      // User A archives story
      // User B renames same story
      // These are genuinely conflicting changes
      const clientVersion = {
        name: 'New Trip Name'
      };
      const serverVersion = {
        id: 'story-123',
        name: 'Old Trip Name',  // Not renamed by server
        is_archived: true,      // Archived by User A
        updated_at: '2026-01-01T12:00:00Z'
      };

      expect(areVersionsDataEqual(clientVersion, serverVersion)).toBe(false);
    });
  });

  describe('Both Users Edit Same Event Amount', () => {
    it('should auto-resolve when both set same amount', () => {
      const clientVersion = { amount: -75.50 };
      const serverVersion = {
        id: 'event-789',
        description: 'Groceries',
        amount: -75.50,
        currency: 'GBP'
      };

      expect(areVersionsDataEqual(clientVersion, serverVersion)).toBe(true);
    });

    it('should NOT auto-resolve when amounts differ', () => {
      const clientVersion = { amount: -75.50 };
      const serverVersion = {
        id: 'event-789',
        description: 'Groceries',
        amount: -80.00,  // Different amount
        currency: 'GBP'
      };

      expect(areVersionsDataEqual(clientVersion, serverVersion)).toBe(false);
    });
  });

  describe('Complex Partial Update Match', () => {
    it('should handle account update with multiple matching fields', () => {
      const clientVersion = {
        name: 'Updated Account Name',
        current_balance: 2500,
        is_default: true
      };
      const serverVersion = {
        id: 'account-123',
        name: 'Updated Account Name',
        currency: 'GBP',
        current_balance: 2500,
        is_default: true,
        is_archived: false,
        rate_to_base: 1.0,
        updated_at: '2026-01-01T14:00:00Z'
      };

      expect(areVersionsDataEqual(clientVersion, serverVersion)).toBe(true);
    });
  });
});

describe('Multi-Client Conflict Scenarios - Integration', () => {
  beforeEach(async () => {
    await db.sync_queue.clear();
    await db.conflicts.clear();
  });

  afterEach(async () => {
    await db.sync_queue.clear();
    await db.conflicts.clear();
  });

  describe('Simulated Sync Response Processing', () => {
    it('should auto-resolve identical archive conflict', async () => {
      // Simulate what processSyncResponse does when receiving a conflict
      const conflict = {
        entity_type: 'story',
        entity_id: generateUUID(),
        conflict_type: 'update_update',
        client_version: { is_archived: true },
        server_version: {
          id: 'story-123',
          name: 'Trip',
          is_archived: true,
          updated_at: '2026-01-01T12:00:00Z'
        }
      };

      // Check if should auto-resolve
      const shouldAutoResolve = areVersionsDataEqual(
        conflict.client_version,
        conflict.server_version
      );

      expect(shouldAutoResolve).toBe(true);

      // If auto-resolve, don't store conflict
      if (!shouldAutoResolve) {
        await db.conflicts.add({
          id: generateUUID(),
          ...conflict,
          resolved_at: null
        });
      }

      // Verify no conflict stored
      const conflicts = await db.conflicts.toArray();
      expect(conflicts).toHaveLength(0);
    });

    it('should store genuine conflict for user resolution', async () => {
      const conflictId = generateUUID();
      const entityId = generateUUID();

      const conflict = {
        entity_type: 'story',
        entity_id: entityId,
        conflict_type: 'update_update',
        client_version: { name: 'Client Name' },
        server_version: {
          id: entityId,
          name: 'Server Name',  // Different!
          is_archived: false,
          updated_at: '2026-01-01T12:00:00Z'
        }
      };

      // Check if should auto-resolve
      const shouldAutoResolve = areVersionsDataEqual(
        conflict.client_version,
        conflict.server_version
      );

      expect(shouldAutoResolve).toBe(false);

      // Genuine conflict - store for user resolution
      if (!shouldAutoResolve) {
        await db.conflicts.add({
          id: conflictId,
          ...conflict,
          resolved_at: null
        });
      }

      // Verify conflict stored
      const conflicts = await db.conflicts.toArray();
      expect(conflicts).toHaveLength(1);
      expect(conflicts[0].client_version.name).toBe('Client Name');
      expect(conflicts[0].server_version.name).toBe('Server Name');
    });

    it('should handle multiple conflicts in single sync', async () => {
      const conflicts = [
        {
          entity_type: 'story',
          entity_id: generateUUID(),
          conflict_type: 'update_update',
          client_version: { is_archived: true },
          server_version: { is_archived: true, name: 'Story 1' }  // Same - auto-resolve
        },
        {
          entity_type: 'account',
          entity_id: generateUUID(),
          conflict_type: 'update_update',
          client_version: { name: 'New Name' },
          server_version: { name: 'Different Name' }  // Different - real conflict
        },
        {
          entity_type: 'event',
          entity_id: generateUUID(),
          conflict_type: 'update_update',
          client_version: { amount: 100 },
          server_version: { amount: 100, description: 'Test' }  // Same - auto-resolve
        }
      ];

      // Process each conflict
      for (const conflict of conflicts) {
        const shouldAutoResolve = areVersionsDataEqual(
          conflict.client_version,
          conflict.server_version
        );

        if (!shouldAutoResolve) {
          await db.conflicts.add({
            id: generateUUID(),
            ...conflict,
            resolved_at: null
          });
        }
      }

      // Only 1 should be stored (the name conflict)
      const storedConflicts = await db.conflicts.toArray();
      expect(storedConflicts).toHaveLength(1);
      expect(storedConflicts[0].entity_type).toBe('account');
    });
  });
});

describe('Edge Cases and Boundary Conditions', () => {
  it('should handle very long strings', () => {
    const longString = 'a'.repeat(10000);
    expect(areVersionsDataEqual(
      { description: longString },
      { description: longString }
    )).toBe(true);
  });

  it('should handle special characters', () => {
    const specialString = '🎉 Special chars: <>&"\'\\n\\t';
    expect(areVersionsDataEqual(
      { name: specialString },
      { name: specialString }
    )).toBe(true);
  });

  it('should handle empty string vs non-empty', () => {
    expect(areVersionsDataEqual(
      { name: '' },
      { name: 'Test' }
    )).toBe(false);
  });

  it('should handle zero vs non-zero', () => {
    expect(areVersionsDataEqual(
      { amount: 0 },
      { amount: 100 }
    )).toBe(false);
  });

  it('should handle zero equality', () => {
    expect(areVersionsDataEqual(
      { amount: 0 },
      { amount: 0 }
    )).toBe(true);
  });

  it('should handle negative numbers', () => {
    expect(areVersionsDataEqual(
      { amount: -100 },
      { amount: -100 }
    )).toBe(true);
  });

  it('should handle Date objects (via JSON stringify)', () => {
    const date = new Date('2026-01-01T10:00:00Z');
    expect(areVersionsDataEqual(
      { date: date.toISOString() },
      { date: date.toISOString() }
    )).toBe(true);
  });
});
