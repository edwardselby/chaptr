/**
 * CHAPTR - Entity Operations Tests
 *
 * Tests for CRUD functions in entity-operations.js module
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
    resolveAccountId,
    createEvent,
    updateEvent,
    deleteEvent,
    createStory,
    updateStory,
    performStoryDeletion
} from '../../../static/js/modules/entity-operations.js';


// ============================================================================
// Mock Setup
// ============================================================================

/**
 * Create a mock Dexie database with tracking
 */
function createMockDb() {
    const addedEvents = [];
    const updatedEvents = [];
    const deletedEvents = [];
    const addedStories = [];
    const updatedStories = [];
    const queuedChanges = [];

    return {
        events: {
            add: vi.fn(async (event) => {
                addedEvents.push(event);
                return event.id;
            }),
            get: vi.fn(async (id) => {
                // Return a mock event with updated_at for conflict detection
                return {
                    id,
                    description: 'Test Event',
                    amount: '100',
                    updated_at: '2024-01-01T00:00:00Z'
                };
            }),
            update: vi.fn(async (id, updates) => {
                updatedEvents.push({ id, updates });
                return 1;
            }),
            delete: vi.fn(async (id) => {
                deletedEvents.push(id);
                return 1;
            })
        },
        stories: {
            add: vi.fn(async (story) => {
                addedStories.push(story);
                return story.id;
            }),
            get: vi.fn(async (id) => {
                return {
                    id,
                    name: 'Test Story',
                    updated_at: '2024-01-01T00:00:00Z'
                };
            }),
            update: vi.fn(async (id, updates) => {
                updatedStories.push({ id, updates });
                return 1;
            })
        },
        queueChange: vi.fn(async (entityType, entityId, action, data, baseUpdatedAt) => {
            queuedChanges.push({ entityType, entityId, action, data, baseUpdatedAt });
        }),
        // Tracking helpers
        _addedEvents: addedEvents,
        _updatedEvents: updatedEvents,
        _deletedEvents: deletedEvents,
        _addedStories: addedStories,
        _updatedStories: updatedStories,
        _queuedChanges: queuedChanges
    };
}

/**
 * Create sample test data
 */
function createTestData() {
    return {
        accounts: [
            { id: 'acc-1', name: 'Checking', currency: 'GBP', is_default: true, is_archived: false, rate_to_base: 1 },
            { id: 'acc-2', name: 'Savings', currency: 'USD', is_default: false, is_archived: false, rate_to_base: 0.79 },
            { id: 'acc-3', name: 'Archived', currency: 'GBP', is_default: false, is_archived: true, rate_to_base: 1 }
        ],
        stories: [
            { id: 'story-1', name: 'Trip', default_account_id: 'acc-2' },
            { id: 'story-2', name: 'Project', default_account_id: null }
        ],
        events: [
            { id: 'event-1', description: 'Expense 1', account_id: 'acc-1' },
            { id: 'event-2', description: 'Expense 2', account_id: 'acc-2' }
        ],
        settings: {
            base_currency: 'GBP',
            rates: { 'GBP': 1, 'USD': 0.79, 'EUR': 0.85 }
        }
    };
}


// ============================================================================
// resolveAccountId Tests
// ============================================================================

describe('Entity Operations: resolveAccountId', () => {
    const { accounts, stories } = createTestData();

    it('should return selected account ID when provided', () => {
        const result = resolveAccountId('acc-2', null, accounts, stories);
        expect(result).toBe('acc-2');
    });

    it('should return story default account when no account selected', () => {
        const result = resolveAccountId(null, 'story-1', accounts, stories);
        expect(result).toBe('acc-2'); // story-1's default account
    });

    it('should return global default account when no account selected and no story default', () => {
        const result = resolveAccountId(null, 'story-2', accounts, stories);
        expect(result).toBe('acc-1'); // acc-1 is the global default
    });

    it('should return global default account when no account and no story', () => {
        const result = resolveAccountId(null, null, accounts, stories);
        expect(result).toBe('acc-1');
    });

    it('should return null when no defaults exist', () => {
        const noDefaultAccounts = [
            { id: 'acc-1', is_default: false, is_archived: false }
        ];
        const result = resolveAccountId(null, null, noDefaultAccounts, stories);
        expect(result).toBe(null);
    });

    it('should not return archived account as default', () => {
        const accountsWithArchivedDefault = [
            { id: 'acc-1', is_default: true, is_archived: true },
            { id: 'acc-2', is_default: false, is_archived: false }
        ];
        const result = resolveAccountId(null, null, accountsWithArchivedDefault, []);
        expect(result).toBe(null);
    });

    it('should handle non-existent story ID gracefully', () => {
        const result = resolveAccountId(null, 'non-existent', accounts, stories);
        expect(result).toBe('acc-1'); // Falls back to global default
    });
});


// ============================================================================
// createEvent Tests
// ============================================================================

describe('Entity Operations: createEvent', () => {
    let mockDb;
    let testData;
    const generateId = () => 'generated-uuid-123';

    beforeEach(() => {
        mockDb = createMockDb();
        testData = createTestData();
    });

    it('should create event with resolved account', async () => {
        const eventData = {
            description: 'Test expense',
            amount: '50.00',
            event_date: '2024-06-15',
            story_id: null,
            account_id: 'acc-1'
        };

        const result = await createEvent(
            mockDb, eventData, testData.accounts, testData.stories,
            testData.settings, generateId
        );

        expect(result.success).toBe(true);
        expect(result.id).toBe('generated-uuid-123');
        expect(result.entity.description).toBe('Test expense');
        expect(result.entity.account_id).toBe('acc-1');
        expect(result.entity.currency).toBe('GBP');
    });

    it('should resolve account from story default', async () => {
        const eventData = {
            description: 'Trip expense',
            amount: '100',
            event_date: '2024-06-15',
            story_id: 'story-1',
            account_id: null
        };

        const result = await createEvent(
            mockDb, eventData, testData.accounts, testData.stories,
            testData.settings, generateId
        );

        expect(result.success).toBe(true);
        expect(result.entity.account_id).toBe('acc-2'); // story-1's default
        expect(result.entity.currency).toBe('USD'); // acc-2's currency
    });

    it('should fail when no account can be resolved', async () => {
        const noDefaultAccounts = [
            { id: 'acc-1', is_default: false, is_archived: false }
        ];
        const eventData = {
            description: 'Test',
            amount: '50',
            event_date: '2024-06-15',
            story_id: null,
            account_id: null
        };

        const result = await createEvent(
            mockDb, eventData, noDefaultAccounts, [],
            testData.settings, generateId
        );

        expect(result.success).toBe(false);
        expect(result.error).toBe('Account required');
    });

    it('should queue change for sync', async () => {
        const eventData = {
            description: 'Test',
            amount: '50',
            event_date: '2024-06-15',
            account_id: 'acc-1'
        };

        await createEvent(
            mockDb, eventData, testData.accounts, testData.stories,
            testData.settings, generateId
        );

        expect(mockDb.queueChange).toHaveBeenCalledWith(
            'event',
            'generated-uuid-123',
            'create',
            expect.any(Object)
        );
    });

    it('should use rate_to_base from settings', async () => {
        const eventData = {
            description: 'USD expense',
            amount: '100',
            event_date: '2024-06-15',
            account_id: 'acc-2' // USD account
        };

        const result = await createEvent(
            mockDb, eventData, testData.accounts, testData.stories,
            testData.settings, generateId
        );

        expect(result.entity.rate_to_base).toBe(0.79); // From settings.rates.USD
    });

    it('should default rate_to_base to 1.0 for unknown currency', async () => {
        const settingsNoRates = { base_currency: 'GBP', rates: {} };
        const eventData = {
            description: 'Test',
            amount: '50',
            event_date: '2024-06-15',
            account_id: 'acc-1'
        };

        const result = await createEvent(
            mockDb, eventData, testData.accounts, testData.stories,
            settingsNoRates, generateId
        );

        expect(result.entity.rate_to_base).toBe(1.0);
    });
});


// ============================================================================
// updateEvent Tests
// ============================================================================

describe('Entity Operations: updateEvent', () => {
    let mockDb;
    let testData;

    beforeEach(() => {
        mockDb = createMockDb();
        testData = createTestData();
    });

    it('should update event with new data', async () => {
        const result = await updateEvent(mockDb, 'event-1', {
            description: 'Updated description',
            amount: '75.00'
        }, testData.accounts);

        expect(result.success).toBe(true);
        expect(mockDb.events.update).toHaveBeenCalled();
    });

    it('should update currency when account changes', async () => {
        const result = await updateEvent(mockDb, 'event-1', {
            account_id: 'acc-2'
        }, testData.accounts);

        expect(result.success).toBe(true);
        const updateCall = mockDb._updatedEvents[0];
        expect(updateCall.updates.currency).toBe('USD');
        expect(updateCall.updates.rate_to_base).toBe(0.79);
    });

    it('should fail when event not found', async () => {
        mockDb.events.get = vi.fn().mockResolvedValue(null);

        const result = await updateEvent(mockDb, 'non-existent', {
            description: 'Test'
        }, testData.accounts);

        expect(result.success).toBe(false);
        expect(result.error).toContain('not found');
    });

    it('should include base_updated_at for conflict detection', async () => {
        await updateEvent(mockDb, 'event-1', {
            description: 'Updated'
        }, testData.accounts);

        const queueCall = mockDb._queuedChanges[0];
        expect(queueCall.baseUpdatedAt).toBe('2024-01-01T00:00:00Z');
    });
});


// ============================================================================
// deleteEvent Tests
// ============================================================================

describe('Entity Operations: deleteEvent', () => {
    let mockDb;
    let testData;

    beforeEach(() => {
        mockDb = createMockDb();
        testData = createTestData();
    });

    it('should delete event and queue for sync', async () => {
        const result = await deleteEvent(mockDb, 'event-1', testData.events);

        expect(result.success).toBe(true);
        expect(mockDb.events.delete).toHaveBeenCalledWith('event-1');
        expect(mockDb.queueChange).toHaveBeenCalledWith(
            'event',
            'event-1',
            'delete',
            null,
            '2024-01-01T00:00:00Z'
        );
    });

    it('should fail when event not in events array', async () => {
        const result = await deleteEvent(mockDb, 'non-existent', testData.events);

        expect(result.success).toBe(false);
        expect(result.error).toBe('Event not found');
    });

    it('should fail when event not found in database', async () => {
        mockDb.events.get = vi.fn().mockResolvedValue(null);

        const result = await deleteEvent(mockDb, 'event-1', testData.events);

        expect(result.success).toBe(false);
        expect(result.error).toContain('not found in database');
    });
});


// ============================================================================
// createStory Tests
// ============================================================================

describe('Entity Operations: createStory', () => {
    let mockDb;
    let testData;
    const generateId = () => 'story-uuid-456';

    beforeEach(() => {
        mockDb = createMockDb();
        testData = createTestData();
    });

    it('should create story with all fields', async () => {
        const storyData = {
            name: 'New Trip',
            start_date: '2024-07-01',
            end_date: '2024-07-15',
            funding_mode: 'fixed',
            funding_amount: 500,
            goal_type: 'savings',
            goal_amount: 1000,
            default_account_id: 'acc-1'
        };

        const result = await createStory(mockDb, storyData, testData.settings, generateId);

        expect(result.success).toBe(true);
        expect(result.id).toBe('story-uuid-456');
        expect(result.entity.name).toBe('New Trip');
        expect(result.entity.funding_mode).toBe('fixed');
        expect(result.entity.is_archived).toBe(false);
    });

    it('should use defaults for optional fields', async () => {
        const storyData = {
            name: 'Minimal Story',
            start_date: '2024-07-01',
            end_date: '2024-07-15'
        };

        const result = await createStory(mockDb, storyData, testData.settings, generateId);

        expect(result.entity.display_currency).toBe('GBP'); // From settings
        expect(result.entity.funding_mode).toBe('projected');
        expect(result.entity.goal_type).toBe(null);
        expect(result.entity.default_account_id).toBe(null);
    });

    it('should queue change for sync', async () => {
        const storyData = {
            name: 'Test',
            start_date: '2024-07-01',
            end_date: '2024-07-15'
        };

        await createStory(mockDb, storyData, testData.settings, generateId);

        expect(mockDb.queueChange).toHaveBeenCalledWith(
            'story',
            'story-uuid-456',
            'create',
            expect.any(Object)
        );
    });
});


// ============================================================================
// updateStory Tests
// ============================================================================

describe('Entity Operations: updateStory', () => {
    let mockDb;

    beforeEach(() => {
        mockDb = createMockDb();
    });

    it('should update story with new data', async () => {
        const result = await updateStory(mockDb, 'story-1', {
            name: 'Updated Trip'
        });

        expect(result.success).toBe(true);
        expect(mockDb.stories.update).toHaveBeenCalled();
    });

    it('should fail when story not found', async () => {
        mockDb.stories.get = vi.fn().mockResolvedValue(null);

        const result = await updateStory(mockDb, 'non-existent', {
            name: 'Test'
        });

        expect(result.success).toBe(false);
        expect(result.error).toContain('not found');
    });

    it('should include base_updated_at for conflict detection', async () => {
        await updateStory(mockDb, 'story-1', { name: 'Updated' });

        const queueCall = mockDb._queuedChanges[0];
        expect(queueCall.baseUpdatedAt).toBe('2024-01-01T00:00:00Z');
    });
});


// ============================================================================
// performStoryDeletion Tests
// ============================================================================

describe('Entity Operations: performStoryDeletion', () => {
    let mockDb;

    beforeEach(() => {
        mockDb = createMockDb();
    });

    it('should archive story and queue delete', async () => {
        const result = await performStoryDeletion(mockDb, 'story-1');

        expect(result.success).toBe(true);

        // Should update with is_archived: true
        const updateCall = mockDb._updatedStories[0];
        expect(updateCall.updates.is_archived).toBe(true);

        // Should queue delete with null data
        expect(mockDb.queueChange).toHaveBeenCalledWith(
            'story',
            'story-1',
            'delete',
            null,
            '2024-01-01T00:00:00Z'
        );
    });

    it('should fail when story not found', async () => {
        mockDb.stories.get = vi.fn().mockResolvedValue(null);

        const result = await performStoryDeletion(mockDb, 'non-existent');

        expect(result.success).toBe(false);
        expect(result.error).toContain('not found');
    });
});
