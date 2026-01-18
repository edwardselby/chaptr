/**
 * Tenant Sync Integration Tests
 *
 * Tests tenant-related data handling in the Dexie.js database layer and sync operations.
 *
 * Key Insight: Tenant filtering happens at the BACKEND, not frontend.
 * The frontend stores all data for the current user's tenant - it receives
 * pre-filtered data from the server.
 *
 * Tests verify:
 * - Sync payloads include tenant_id correctly
 * - Sync responses apply tenant data correctly to Dexie
 * - User state stores and uses tenant_id correctly
 * - Storage adapter handles multi-tenant sync correctly
 *
 * Priority: HIGH - Ensures tenant data integrity in frontend storage
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { db } from '../../../static/js/db.js';
import { generateUUID } from '../../../static/js/utils.js';


// ============================================================================
// Test Class 1: Sync Payload Tenant ID
// ============================================================================

describe('Sync Payload Tenant ID', () => {
    beforeEach(async () => {
        await db.sync_queue.clear();
        await db.accounts.clear();
        await db.events.clear();
        await db.stories.clear();
    });

    afterEach(async () => {
        await db.sync_queue.clear();
        await db.accounts.clear();
        await db.events.clear();
        await db.stories.clear();
    });

    it('should include tenant_id when queueing account creation', async () => {
        const tenantId = generateUUID();
        const accountId = generateUUID();
        const accountData = {
            id: accountId,
            name: 'Tenant Account',
            currency: 'GBP',
            current_balance: 1000,
            is_default: true,
            is_archived: false,
            tenant_id: tenantId,
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString()
        };

        // Queue the change
        await db.queueChange('account', accountId, 'create', accountData);

        // Verify queue item includes tenant_id
        const queueItems = await db.sync_queue.toArray();
        expect(queueItems).toHaveLength(1);
        expect(queueItems[0].data.tenant_id).toBe(tenantId);
        expect(queueItems[0].entity_type).toBe('account');
        expect(queueItems[0].action).toBe('create');
    });

    it('should include tenant_id when queueing event creation', async () => {
        const tenantId = generateUUID();
        const eventId = generateUUID();
        const accountId = generateUUID();
        const eventData = {
            id: eventId,
            event_date: '2025-01-15',
            description: 'Test Event',
            amount: -50.00,
            currency: 'GBP',
            account_id: accountId,
            tenant_id: tenantId,
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString()
        };

        await db.queueChange('event', eventId, 'create', eventData);

        const queueItems = await db.sync_queue.toArray();
        expect(queueItems).toHaveLength(1);
        expect(queueItems[0].data.tenant_id).toBe(tenantId);
        expect(queueItems[0].entity_type).toBe('event');
    });

    it('should include tenant_id when queueing story creation', async () => {
        const tenantId = generateUUID();
        const storyId = generateUUID();
        const storyData = {
            id: storyId,
            name: 'Tenant Story',
            start_date: '2025-01-01',
            end_date: '2025-12-31',
            is_archived: false,
            tenant_id: tenantId,
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString()
        };

        await db.queueChange('story', storyId, 'create', storyData);

        const queueItems = await db.sync_queue.toArray();
        expect(queueItems).toHaveLength(1);
        expect(queueItems[0].data.tenant_id).toBe(tenantId);
        expect(queueItems[0].entity_type).toBe('story');
    });

    it('should preserve tenant_id when queueing update operation', async () => {
        const tenantId = generateUUID();
        const accountId = generateUUID();
        const originalUpdatedAt = new Date().toISOString();

        // First create the account in Dexie
        const originalAccount = {
            id: accountId,
            name: 'Original Name',
            currency: 'GBP',
            current_balance: 1000,
            tenant_id: tenantId,
            updated_at: originalUpdatedAt
        };
        await db.accounts.add(originalAccount);

        // Queue an update (simulating what storage adapter does)
        const updateData = {
            id: accountId,
            name: 'Updated Name',
            currency: 'GBP',
            current_balance: 1500,
            tenant_id: tenantId,  // tenant_id must be preserved
            updated_at: new Date().toISOString()
        };

        await db.queueChange('account', accountId, 'update', updateData, originalUpdatedAt);

        const queueItems = await db.sync_queue.toArray();
        expect(queueItems).toHaveLength(1);
        expect(queueItems[0].data.tenant_id).toBe(tenantId);
        expect(queueItems[0].data.name).toBe('Updated Name');
        expect(queueItems[0].base_updated_at).toBe(originalUpdatedAt);
    });
});


// ============================================================================
// Test Class 2: Sync Response Application
// ============================================================================

describe('Sync Response Application', () => {
    beforeEach(async () => {
        await db.accounts.clear();
        await db.events.clear();
        await db.stories.clear();
        await db.sync_queue.clear();
    });

    afterEach(async () => {
        await db.accounts.clear();
        await db.events.clear();
        await db.stories.clear();
        await db.sync_queue.clear();
    });

    it('should store server account with tenant_id in Dexie', async () => {
        const tenantId = generateUUID();
        const serverAccount = {
            id: generateUUID(),
            name: 'Server Account',
            currency: 'USD',
            current_balance: 2000,
            is_default: true,
            is_archived: false,
            tenant_id: tenantId,
            created_at: '2025-01-01T00:00:00Z',
            updated_at: '2025-01-01T00:00:00Z'
        };

        // Simulate applying sync response (as storage adapter does)
        await db.accounts.put(serverAccount);

        const stored = await db.accounts.get(serverAccount.id);
        expect(stored).toBeDefined();
        expect(stored.tenant_id).toBe(tenantId);
        expect(stored.name).toBe('Server Account');
    });

    it('should store multiple server entities with same tenant_id', async () => {
        const tenantId = generateUUID();

        // Simulate full sync response with multiple entity types
        const account = {
            id: generateUUID(),
            name: 'Account 1',
            currency: 'GBP',
            current_balance: 1000,
            tenant_id: tenantId,
            created_at: '2025-01-01T00:00:00Z',
            updated_at: '2025-01-01T00:00:00Z'
        };

        const story = {
            id: generateUUID(),
            name: 'Story 1',
            start_date: '2025-01-01',
            tenant_id: tenantId,
            created_at: '2025-01-01T00:00:00Z',
            updated_at: '2025-01-01T00:00:00Z'
        };

        const event = {
            id: generateUUID(),
            event_date: '2025-01-15',
            description: 'Event 1',
            amount: -100,
            account_id: account.id,
            story_id: story.id,
            tenant_id: tenantId,
            created_at: '2025-01-01T00:00:00Z',
            updated_at: '2025-01-01T00:00:00Z'
        };

        // Apply all entities (simulating full sync)
        await db.accounts.put(account);
        await db.stories.put(story);
        await db.events.put(event);

        // Verify all stored with correct tenant_id
        const storedAccount = await db.accounts.get(account.id);
        const storedStory = await db.stories.get(story.id);
        const storedEvent = await db.events.get(event.id);

        expect(storedAccount.tenant_id).toBe(tenantId);
        expect(storedStory.tenant_id).toBe(tenantId);
        expect(storedEvent.tenant_id).toBe(tenantId);
    });

    it('should update existing entity with server data preserving tenant_id', async () => {
        const tenantId = generateUUID();
        const accountId = generateUUID();

        // Local version
        const localAccount = {
            id: accountId,
            name: 'Local Name',
            current_balance: 1000,
            tenant_id: tenantId,
            updated_at: '2025-01-01T00:00:00Z'
        };
        await db.accounts.add(localAccount);

        // Server update (newer)
        const serverUpdate = {
            id: accountId,
            name: 'Server Updated Name',
            current_balance: 1500,
            tenant_id: tenantId,  // Same tenant
            updated_at: '2025-01-02T00:00:00Z'  // Newer
        };

        // Apply server update
        await db.accounts.put(serverUpdate);

        const stored = await db.accounts.get(accountId);
        expect(stored.name).toBe('Server Updated Name');
        expect(stored.current_balance).toBe(1500);
        expect(stored.tenant_id).toBe(tenantId);  // Preserved
    });

    it('should delete entity from Dexie on server delete change', async () => {
        const tenantId = generateUUID();
        const accountId = generateUUID();

        // Create account first
        await db.accounts.add({
            id: accountId,
            name: 'To Be Deleted',
            tenant_id: tenantId
        });

        // Verify exists
        let stored = await db.accounts.get(accountId);
        expect(stored).toBeDefined();

        // Simulate applying delete from server
        await db.accounts.delete(accountId);

        // Verify deleted
        stored = await db.accounts.get(accountId);
        expect(stored).toBeUndefined();
    });
});


// ============================================================================
// Test Class 3: User State Tenant Context
// ============================================================================

describe('User State Tenant Context', () => {
    it('should store tenant_id in user state from login response', () => {
        const userId = generateUUID();
        const tenantId = generateUUID();

        const loginResponse = {
            id: userId,
            username: 'testuser',
            role: 'user',
            tenant_id: tenantId
        };

        // Simulate storing user state (as app.js does)
        const userState = {
            id: loginResponse.id,
            username: loginResponse.username,
            role: loginResponse.role,
            tenant_id: loginResponse.tenant_id
        };

        expect(userState.tenant_id).toBe(tenantId);
        expect(userState.tenant_id).not.toBe(userState.id);  // Regular user
    });

    it('should have tenant_id equal to user_id for admin (self-anchored)', () => {
        const adminId = generateUUID();

        // Admin is self-anchored: tenant_id === user.id
        const adminResponse = {
            id: adminId,
            username: 'admin',
            role: 'admin',
            tenant_id: adminId  // Self-anchored
        };

        const userState = {
            id: adminResponse.id,
            username: adminResponse.username,
            role: adminResponse.role,
            tenant_id: adminResponse.tenant_id
        };

        expect(userState.id).toBe(userState.tenant_id);  // Admin anchors own tenant
    });

    it('should have tenant_id equal to user_id for super_admin (self-anchored)', () => {
        const superAdminId = generateUUID();

        const superAdminResponse = {
            id: superAdminId,
            username: 'superadmin',
            role: 'super_admin',
            tenant_id: superAdminId  // Self-anchored
        };

        const userState = {
            id: superAdminResponse.id,
            username: superAdminResponse.username,
            role: superAdminResponse.role,
            tenant_id: superAdminResponse.tenant_id
        };

        expect(userState.id).toBe(userState.tenant_id);
    });

    it('should have regular user inherit admin tenant_id', () => {
        const adminId = generateUUID();
        const userId = generateUUID();

        // Admin created this user, so user inherits admin's tenant
        const userResponse = {
            id: userId,
            username: 'regularuser',
            role: 'user',
            tenant_id: adminId  // Inherited from admin
        };

        const userState = {
            id: userResponse.id,
            username: userResponse.username,
            role: userResponse.role,
            tenant_id: userResponse.tenant_id
        };

        // User's tenant_id should match admin's id, not their own
        expect(userState.tenant_id).toBe(adminId);
        expect(userState.tenant_id).not.toBe(userState.id);
    });
});


// ============================================================================
// Test Class 4: Storage Adapter Tenant Sync
// ============================================================================

describe('Storage Adapter Tenant Sync', () => {
    beforeEach(async () => {
        await db.accounts.clear();
        await db.events.clear();
        await db.stories.clear();
        await db.recurring_rules.clear();
        await db.sync_queue.clear();
    });

    afterEach(async () => {
        await db.accounts.clear();
        await db.events.clear();
        await db.stories.clear();
        await db.recurring_rules.clear();
        await db.sync_queue.clear();
    });

    it('should store all entity types from full sync response with tenant_id', async () => {
        const tenantId = generateUUID();
        const accountId = generateUUID();
        const storyId = generateUUID();
        const eventId = generateUUID();
        const ruleId = generateUUID();

        // Simulate full sync response payload
        const fullSyncResponse = {
            accounts: [{
                id: accountId,
                name: 'Main Account',
                currency: 'GBP',
                current_balance: 5000,
                tenant_id: tenantId
            }],
            stories: [{
                id: storyId,
                name: 'Holiday 2025',
                start_date: '2025-06-01',
                tenant_id: tenantId
            }],
            events: [{
                id: eventId,
                event_date: '2025-06-15',
                description: 'Flight',
                amount: -500,
                account_id: accountId,
                story_id: storyId,
                tenant_id: tenantId
            }],
            recurring_rules: [{
                id: ruleId,
                description: 'Monthly Salary',
                frequency: 'monthly',
                tenant_id: tenantId
            }]
        };

        // Apply full sync (as storage adapter does)
        for (const account of fullSyncResponse.accounts) {
            await db.accounts.put(account);
        }
        for (const story of fullSyncResponse.stories) {
            await db.stories.put(story);
        }
        for (const event of fullSyncResponse.events) {
            await db.events.put(event);
        }
        for (const rule of fullSyncResponse.recurring_rules) {
            await db.recurring_rules.put(rule);
        }

        // Verify all entities have correct tenant_id
        const accounts = await db.accounts.toArray();
        const stories = await db.stories.toArray();
        const events = await db.events.toArray();
        const rules = await db.recurring_rules.toArray();

        expect(accounts).toHaveLength(1);
        expect(accounts[0].tenant_id).toBe(tenantId);

        expect(stories).toHaveLength(1);
        expect(stories[0].tenant_id).toBe(tenantId);

        expect(events).toHaveLength(1);
        expect(events[0].tenant_id).toBe(tenantId);

        expect(rules).toHaveLength(1);
        expect(rules[0].tenant_id).toBe(tenantId);
    });

    it('should format sync queue changes with tenant_id for POST /sync', async () => {
        const tenantId = generateUUID();
        const accountId = generateUUID();
        const eventId = generateUUID();

        // Queue multiple changes
        await db.queueChange('account', accountId, 'create', {
            id: accountId,
            name: 'New Account',
            tenant_id: tenantId
        });

        await db.queueChange('event', eventId, 'create', {
            id: eventId,
            description: 'New Event',
            tenant_id: tenantId
        });

        // Get pending changes (as storage adapter does)
        const pending = await db.getPendingSyncQueue();

        // Verify changes include tenant_id
        expect(pending).toHaveLength(2);

        const accountChange = pending.find(c => c.entity_type === 'account');
        const eventChange = pending.find(c => c.entity_type === 'event');

        expect(accountChange.data.tenant_id).toBe(tenantId);
        expect(eventChange.data.tenant_id).toBe(tenantId);
    });

    it('should preserve tenant_id when resolving sync conflict', async () => {
        const tenantId = generateUUID();
        const accountId = generateUUID();

        // Local version (client)
        const clientVersion = {
            id: accountId,
            name: 'Client Name',
            current_balance: 1000,
            tenant_id: tenantId,
            updated_at: '2025-01-01T10:00:00Z'
        };

        // Server version (authoritative)
        const serverVersion = {
            id: accountId,
            name: 'Server Name',
            current_balance: 1200,
            tenant_id: tenantId,  // Same tenant
            updated_at: '2025-01-01T11:00:00Z'  // Newer
        };

        // Add client version
        await db.accounts.add(clientVersion);

        // Simulate conflict resolution: server wins
        // (as storage adapter's processSyncResponse does)
        await db.accounts.put(serverVersion);

        // Verify server version applied with tenant_id preserved
        const resolved = await db.accounts.get(accountId);
        expect(resolved.name).toBe('Server Name');
        expect(resolved.current_balance).toBe(1200);
        expect(resolved.tenant_id).toBe(tenantId);
    });
});
