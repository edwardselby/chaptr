/**
 * Integration tests for CHAPTR Dexie database
 *
 * Tests real IndexedDB operations using Vitest Browser Mode
 * Demonstrates: CRUD operations, transactions, queries, helper functions
 */

import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { db } from '../static/js/db.js';
import { generateUUID } from '../static/js/utils.js';

describe('Dexie Database - Initialization', () => {
  it('should have all required tables defined', () => {
    expect(db.accounts).toBeDefined();
    expect(db.stories).toBeDefined();
    expect(db.events).toBeDefined();
    expect(db.recurring_rules).toBeDefined();
    expect(db.users).toBeDefined();
    expect(db.settings).toBeDefined();
    expect(db.conflicts).toBeDefined();
    expect(db.sync_queue).toBeDefined();
    expect(db.sync_meta).toBeDefined();
  });

  it('should initialize default settings on first load', async () => {
    // The ready event runs automatically when db is first accessed
    // We just need to verify default settings exist
    const settings = await db.settings.get(1);

    // Settings should exist (created by ready handler in db.js)
    expect(settings).toBeDefined();

    // If settings don't exist yet (race condition), they should be created
    if (settings) {
      expect(settings.base_currency).toBe('GBP');
      expect(settings.rates).toHaveProperty('GBP');
      expect(settings.rates.GBP).toBe(1.0);
    }
  });
});

describe('Dexie Database - Accounts CRUD', () => {
  const testAccountId = generateUUID();

  beforeEach(async () => {
    // Clear accounts before each test
    await db.accounts.clear();
  });

  afterEach(async () => {
    // Clean up after each test
    await db.accounts.clear();
  });

  it('should create an account', async () => {
    const account = {
      id: testAccountId,
      name: 'Test Account',
      currency: 'GBP',
      current_balance: 1000,
      is_default: true,
      is_archived: false,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString()
    };

    await db.accounts.add(account);

    const retrieved = await db.accounts.get(testAccountId);
    expect(retrieved).toBeDefined();
    expect(retrieved.name).toBe('Test Account');
    expect(retrieved.current_balance).toBe(1000);
    expect(retrieved.is_default).toBe(true);
  });

  it('should read all accounts', async () => {
    // Create multiple accounts
    await db.accounts.bulkAdd([
      {
        id: generateUUID(),
        name: 'Account 1',
        currency: 'GBP',
        current_balance: 500,
        is_default: false,
        is_archived: false,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString()
      },
      {
        id: generateUUID(),
        name: 'Account 2',
        currency: 'USD',
        current_balance: 1000,
        is_default: true,
        is_archived: false,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString()
      }
    ]);

    const accounts = await db.accounts.toArray();
    expect(accounts).toHaveLength(2);

    // Don't assume order - check that both accounts exist
    const names = accounts.map(a => a.name).sort();
    expect(names).toEqual(['Account 1', 'Account 2']);
  });

  it('should update an account', async () => {
    const account = {
      id: testAccountId,
      name: 'Original Name',
      currency: 'GBP',
      current_balance: 1000,
      is_default: true,
      is_archived: false,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString()
    };

    await db.accounts.add(account);

    // Update the account
    await db.accounts.update(testAccountId, {
      name: 'Updated Name',
      current_balance: 2000
    });

    const updated = await db.accounts.get(testAccountId);
    expect(updated.name).toBe('Updated Name');
    expect(updated.current_balance).toBe(2000);
    expect(updated.currency).toBe('GBP'); // Unchanged
  });

  it('should delete an account', async () => {
    const account = {
      id: testAccountId,
      name: 'To Delete',
      currency: 'GBP',
      current_balance: 0,
      is_default: false,
      is_archived: false,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString()
    };

    await db.accounts.add(account);
    expect(await db.accounts.get(testAccountId)).toBeDefined();

    // Delete
    await db.accounts.delete(testAccountId);
    expect(await db.accounts.get(testAccountId)).toBeUndefined();
  });

  it('should query accounts by currency', async () => {
    await db.accounts.bulkAdd([
      {
        id: generateUUID(),
        name: 'GBP Account',
        currency: 'GBP',
        current_balance: 500,
        is_default: false,
        is_archived: false,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString()
      },
      {
        id: generateUUID(),
        name: 'USD Account',
        currency: 'USD',
        current_balance: 1000,
        is_default: false,
        is_archived: false,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString()
      },
      {
        id: generateUUID(),
        name: 'Another GBP',
        currency: 'GBP',
        current_balance: 1500,
        is_default: false,
        is_archived: false,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString()
      }
    ]);

    const gbpAccounts = await db.accounts.where('currency').equals('GBP').toArray();
    expect(gbpAccounts).toHaveLength(2);
    expect(gbpAccounts.every(a => a.currency === 'GBP')).toBe(true);
  });
});

describe('Dexie Database - Helper Functions', () => {
  beforeEach(async () => {
    await db.accounts.clear();
    await db.stories.clear();
    await db.events.clear();
  });

  afterEach(async () => {
    await db.accounts.clear();
    await db.stories.clear();
    await db.events.clear();
  });

  it('should get active accounts (excluding archived)', async () => {
    await db.accounts.bulkAdd([
      {
        id: generateUUID(),
        name: 'Active Account',
        currency: 'GBP',
        current_balance: 1000,
        is_default: false,
        is_archived: false,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString()
      },
      {
        id: generateUUID(),
        name: 'Archived Account',
        currency: 'GBP',
        current_balance: 500,
        is_default: false,
        is_archived: true,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString()
      }
    ]);

    const activeAccounts = await db.getActiveAccounts();
    expect(activeAccounts).toHaveLength(1);
    expect(activeAccounts[0].name).toBe('Active Account');
  });

  it('should get active stories (excluding archived)', async () => {
    await db.stories.bulkAdd([
      {
        id: generateUUID(),
        name: 'Active Story',
        start_date: '2025-01-01',
        end_date: '2025-12-31',
        funding_mode: 'projected',
        is_archived: false,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString()
      },
      {
        id: generateUUID(),
        name: 'Archived Story',
        start_date: '2024-01-01',
        end_date: '2024-12-31',
        funding_mode: 'projected',
        is_archived: true,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString()
      }
    ]);

    const activeStories = await db.getActiveStories();
    expect(activeStories).toHaveLength(1);
    expect(activeStories[0].name).toBe('Active Story');
  });

  it('should get default account', async () => {
    const defaultAccountId = generateUUID();
    await db.accounts.bulkAdd([
      {
        id: generateUUID(),
        name: 'Non-default',
        currency: 'GBP',
        current_balance: 1000,
        is_default: false,
        is_archived: false,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString()
      },
      {
        id: defaultAccountId,
        name: 'Default Account',
        currency: 'GBP',
        current_balance: 2000,
        is_default: true,
        is_archived: false,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString()
      }
    ]);

    const defaultAccount = await db.getDefaultAccount();
    expect(defaultAccount).toBeDefined();
    expect(defaultAccount.name).toBe('Default Account');
    expect(defaultAccount.is_default).toBe(true);
  });

  it('should get events in date range', async () => {
    const accountId = generateUUID();

    await db.events.bulkAdd([
      {
        id: generateUUID(),
        event_date: '2025-01-05',
        description: 'Event 1',
        amount: 100,
        account_id: accountId,
        is_baseline: true,
        is_hypothetical: false,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString()
      },
      {
        id: generateUUID(),
        event_date: '2025-01-15',
        description: 'Event 2',
        amount: 200,
        account_id: accountId,
        is_baseline: true,
        is_hypothetical: false,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString()
      },
      {
        id: generateUUID(),
        event_date: '2025-01-25',
        description: 'Event 3',
        amount: 300,
        account_id: accountId,
        is_baseline: true,
        is_hypothetical: false,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString()
      }
    ]);

    const eventsInRange = await db.getEventsInRange('2025-01-10', '2025-01-20');
    expect(eventsInRange).toHaveLength(1);
    expect(eventsInRange[0].description).toBe('Event 2');
  });

  it('should get baseline events', async () => {
    const accountId = generateUUID();

    await db.events.bulkAdd([
      {
        id: generateUUID(),
        event_date: '2025-01-05',
        description: 'Baseline Event',
        amount: 100,
        account_id: accountId,
        is_baseline: true,
        is_hypothetical: false,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString()
      },
      {
        id: generateUUID(),
        event_date: '2025-01-15',
        description: 'Story Event',
        amount: 200,
        account_id: accountId,
        is_baseline: false,
        is_hypothetical: false,
        story_id: generateUUID(),
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString()
      }
    ]);

    const baselineEvents = await db.getBaselineEvents();
    expect(baselineEvents).toHaveLength(1);
    expect(baselineEvents[0].description).toBe('Baseline Event');
    expect(baselineEvents[0].is_baseline).toBe(true);
  });

  it('should get events for a specific story', async () => {
    const accountId = generateUUID();
    const storyId = generateUUID();

    await db.events.bulkAdd([
      {
        id: generateUUID(),
        event_date: '2025-01-05',
        description: 'Story Event 1',
        amount: 100,
        account_id: accountId,
        is_baseline: false,
        is_hypothetical: false,
        story_id: storyId,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString()
      },
      {
        id: generateUUID(),
        event_date: '2025-01-15',
        description: 'Story Event 2',
        amount: 200,
        account_id: accountId,
        is_baseline: false,
        is_hypothetical: false,
        story_id: storyId,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString()
      },
      {
        id: generateUUID(),
        event_date: '2025-01-20',
        description: 'Different Story Event',
        amount: 300,
        account_id: accountId,
        is_baseline: false,
        is_hypothetical: false,
        story_id: generateUUID(),
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString()
      }
    ]);

    const storyEvents = await db.getStoryEvents(storyId);
    expect(storyEvents).toHaveLength(2);
    expect(storyEvents.every(e => e.story_id === storyId)).toBe(true);
  });
});

describe('Dexie Database - Sync Queue Operations', () => {
  beforeEach(async () => {
    await db.sync_queue.clear();
  });

  afterEach(async () => {
    await db.sync_queue.clear();
  });

  it('should queue a change for sync', async () => {
    const entityId = generateUUID();
    const data = {
      name: 'Test Account',
      currency: 'GBP',
      current_balance: 1000
    };

    await db.queueChange('account', entityId, 'create', data);

    const queuedItems = await db.sync_queue.toArray();
    expect(queuedItems).toHaveLength(1);
    expect(queuedItems[0].entity_type).toBe('account');
    expect(queuedItems[0].entity_id).toBe(entityId);
    expect(queuedItems[0].action).toBe('create');
    expect(queuedItems[0].data.name).toBe('Test Account');
  });

  it('should queue multiple changes', async () => {
    await db.queueChange('account', generateUUID(), 'create', { name: 'Account 1' });
    await db.queueChange('story', generateUUID(), 'update', { name: 'Story 1' });
    await db.queueChange('event', generateUUID(), 'delete', null);

    const queuedItems = await db.sync_queue.toArray();
    expect(queuedItems).toHaveLength(3);
    expect(queuedItems[0].action).toBe('create');
    expect(queuedItems[1].action).toBe('update');
    expect(queuedItems[2].action).toBe('delete');
  });

  it('should include metadata in queue entries', async () => {
    const entityId = generateUUID();
    const metadata = {
      dependencies: [generateUUID(), generateUUID()],
      _derived_from: 'account_creation',
      _optimistic: true
    };

    await db.queueChange('event', entityId, 'create', { amount: 100 }, null, metadata);

    const queuedItem = await db.sync_queue.where('entity_id').equals(entityId).first();
    expect(queuedItem.dependencies).toHaveLength(2);
    expect(queuedItem._derived_from).toBe('account_creation');
    expect(queuedItem._optimistic).toBe(true);
  });

  it('should get pending sync queue items', async () => {
    await db.queueChange('account', generateUUID(), 'create', { name: 'Account 1' });
    await db.queueChange('story', generateUUID(), 'update', { name: 'Story 1' });

    const pendingItems = await db.getPendingSyncQueue();
    expect(pendingItems).toHaveLength(2);
  });

  it('should clear sync queue', async () => {
    await db.queueChange('account', generateUUID(), 'create', { name: 'Account 1' });
    await db.queueChange('story', generateUUID(), 'update', { name: 'Story 1' });

    expect(await db.sync_queue.count()).toBe(2);

    await db.clearSyncQueue();
    expect(await db.sync_queue.count()).toBe(0);
  });

  it('should query queue by entity type', async () => {
    await db.queueChange('account', generateUUID(), 'create', { name: 'Account 1' });
    await db.queueChange('account', generateUUID(), 'update', { name: 'Account 2' });
    await db.queueChange('story', generateUUID(), 'create', { name: 'Story 1' });

    const accountChanges = await db.sync_queue.where('entity_type').equals('account').toArray();
    expect(accountChanges).toHaveLength(2);
    expect(accountChanges.every(item => item.entity_type === 'account')).toBe(true);
  });
});

describe('Dexie Database - Complex Transactions', () => {
  beforeEach(async () => {
    await db.accounts.clear();
    await db.events.clear();
    await db.sync_queue.clear();
  });

  afterEach(async () => {
    await db.accounts.clear();
    await db.events.clear();
    await db.sync_queue.clear();
  });

  it('should perform atomic transaction with multiple operations', async () => {
    const accountId = generateUUID();

    await db.transaction('rw', db.accounts, db.events, db.sync_queue, async () => {
      // Create account
      await db.accounts.add({
        id: accountId,
        name: 'Transaction Account',
        currency: 'GBP',
        current_balance: 1000,
        is_default: false,
        is_archived: false,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString()
      });

      // Create opening balance event
      await db.events.add({
        id: generateUUID(),
        event_date: '2025-01-01',
        description: 'Opening Balance',
        amount: 1000,
        account_id: accountId,
        is_baseline: true,
        is_hypothetical: false,
        is_opening_balance: true,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString()
      });

      // Queue for sync
      await db.queueChange('account', accountId, 'create', { name: 'Transaction Account' });
    });

    // Verify all operations succeeded
    const account = await db.accounts.get(accountId);
    expect(account).toBeDefined();

    const events = await db.events.where('account_id').equals(accountId).toArray();
    expect(events).toHaveLength(1);

    const queuedItems = await db.sync_queue.toArray();
    expect(queuedItems).toHaveLength(1);
  });

  it('should rollback transaction on error', async () => {
    const accountId = generateUUID();

    try {
      await db.transaction('rw', db.accounts, db.events, async () => {
        // Add account
        await db.accounts.add({
          id: accountId,
          name: 'Will Rollback',
          currency: 'GBP',
          current_balance: 1000,
          is_default: false,
          is_archived: false,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString()
        });

        // Throw error to trigger rollback
        throw new Error('Intentional error');
      });
    } catch (error) {
      expect(error.message).toBe('Intentional error');
    }

    // Verify account was NOT created due to rollback
    const account = await db.accounts.get(accountId);
    expect(account).toBeUndefined();
  });
});

describe('Dexie Database - IndexedDB Features', () => {
  beforeEach(async () => {
    await db.events.clear();
  });

  afterEach(async () => {
    await db.events.clear();
  });

  it('should support compound queries with multiple filters', async () => {
    const accountId = generateUUID();

    await db.events.bulkAdd([
      {
        id: generateUUID(),
        event_date: '2025-01-15',
        description: 'Baseline Event',
        amount: 100,
        account_id: accountId,
        is_baseline: true,
        is_hypothetical: false,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString()
      },
      {
        id: generateUUID(),
        event_date: '2025-01-20',
        description: 'Hypothetical Event',
        amount: 200,
        account_id: accountId,
        is_baseline: true,
        is_hypothetical: true,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString()
      },
      {
        id: generateUUID(),
        event_date: '2025-01-25',
        description: 'Story Event',
        amount: 300,
        account_id: accountId,
        is_baseline: false,
        is_hypothetical: false,
        story_id: generateUUID(),
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString()
      }
    ]);

    // Query: baseline AND non-hypothetical
    // Use filter() since is_baseline is not indexed
    const baselineRealEvents = await db.events
      .toArray()
      .then(events => events.filter(e => e.is_baseline === true && e.is_hypothetical === false));

    expect(baselineRealEvents).toHaveLength(1);
    expect(baselineRealEvents[0].description).toBe('Baseline Event');
  });

  it('should support ordering and limiting results', async () => {
    const accountId = generateUUID();

    await db.events.bulkAdd([
      {
        id: generateUUID(),
        event_date: '2025-01-15',
        description: 'Event 2',
        amount: 200,
        account_id: accountId,
        is_baseline: true,
        is_hypothetical: false,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString()
      },
      {
        id: generateUUID(),
        event_date: '2025-01-05',
        description: 'Event 1',
        amount: 100,
        account_id: accountId,
        is_baseline: true,
        is_hypothetical: false,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString()
      },
      {
        id: generateUUID(),
        event_date: '2025-01-25',
        description: 'Event 3',
        amount: 300,
        account_id: accountId,
        is_baseline: true,
        is_hypothetical: false,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString()
      }
    ]);

    // Get first 2 events ordered by date
    const firstTwo = await db.events
      .orderBy('event_date')
      .limit(2)
      .toArray();

    expect(firstTwo).toHaveLength(2);
    expect(firstTwo[0].event_date).toBe('2025-01-05');
    expect(firstTwo[1].event_date).toBe('2025-01-15');
  });

  it('should support bulk operations efficiently', async () => {
    const accountId = generateUUID();
    const events = [];

    // Create 100 events
    for (let i = 1; i <= 100; i++) {
      events.push({
        id: generateUUID(),
        event_date: `2025-01-${String(i % 28 + 1).padStart(2, '0')}`,
        description: `Event ${i}`,
        amount: i * 100,
        account_id: accountId,
        is_baseline: true,
        is_hypothetical: false,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString()
      });
    }

    // Bulk add
    await db.events.bulkAdd(events);

    // Verify count
    const count = await db.events.count();
    expect(count).toBe(100);

    // Bulk update using account_id (which IS indexed)
    await db.events
      .where('account_id').equals(accountId)
      .modify({ is_hypothetical: true });

    // Verify updates by fetching all and filtering
    const allEvents = await db.events.where('account_id').equals(accountId).toArray();
    const hypotheticalCount = allEvents.filter(e => e.is_hypothetical === true).length;
    expect(hypotheticalCount).toBe(100);
  });
});
