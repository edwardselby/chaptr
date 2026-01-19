/**
 * Tenant Change Database Clearing Tests
 *
 * Tests the tenant isolation mechanism that clears the local IndexedDB
 * database when a user from a different tenant logs in on the same device.
 *
 * Security Context:
 * - Prevents data leakage between tenants sharing a device
 * - Ensures each tenant sees only their own data
 * - Backend always enforces tenant isolation via JWT, this is defense-in-depth
 *
 * Priority: 🚨 CRITICAL - Security feature preventing cross-tenant data exposure
 */

import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { db } from '../../../static/js/db.js';

/**
 * Generate a UUID for test data.
 * @returns {string} A new UUID
 */
function generateUUID() {
    return crypto.randomUUID();
}

describe('Tenant Change Database Clearing', () => {
    // Generate unique tenant IDs for each test run
    let tenant1Id;
    let tenant2Id;

    beforeEach(async () => {
        tenant1Id = generateUUID();
        tenant2Id = generateUUID();

        // Clear all tables for clean slate
        await db.clearAllData();
        // Also clear sync_meta separately since clearAllData clears it
        // but we want to ensure it's empty for tenant_id tests
    });

    afterEach(async () => {
        await db.clearAllData();
    });

    // ==================== TENANT ID STORAGE ====================

    describe('Tenant ID Storage', () => {
        it('should store tenant_id in sync_meta', async () => {
            await db.setTenantId(tenant1Id);

            // Verify directly in sync_meta table
            const meta = await db.sync_meta.get('tenant_id');
            expect(meta).toBeDefined();
            expect(meta.id).toBe('tenant_id');
            expect(meta.value).toBe(tenant1Id);
        });

        it('should retrieve stored tenant_id', async () => {
            await db.setTenantId(tenant1Id);

            const stored = await db.getTenantId();
            expect(stored).toBe(tenant1Id);
        });

        it('should return null when no tenant_id stored', async () => {
            // Fresh database - no tenant_id set
            const stored = await db.getTenantId();
            expect(stored).toBeNull();
        });

        it('should overwrite existing tenant_id', async () => {
            await db.setTenantId(tenant1Id);
            expect(await db.getTenantId()).toBe(tenant1Id);

            await db.setTenantId(tenant2Id);
            expect(await db.getTenantId()).toBe(tenant2Id);

            // Only one entry should exist
            const allMeta = await db.sync_meta.toArray();
            const tenantIdEntries = allMeta.filter(m => m.id === 'tenant_id');
            expect(tenantIdEntries).toHaveLength(1);
        });
    });

    // ==================== TENANT CHANGE DETECTION ====================

    describe('Tenant Change Detection', () => {
        it('should not clear database on first login (no stored tenant)', async () => {
            // Add some data as if from a previous session without tenant tracking
            const accountId = generateUUID();
            await db.accounts.add({
                id: accountId,
                name: 'Pre-existing Account',
                currency: 'GBP',
                current_balance: 1000,
                tenant_id: tenant1Id,
                created_at: new Date().toISOString(),
                updated_at: new Date().toISOString()
            });

            // Simulate first login check (as handleLogin would do)
            const storedTenantId = await db.getTenantId();
            const newTenantId = tenant1Id;

            // First login: no stored tenant, so no clearing
            if (storedTenantId && storedTenantId !== newTenantId) {
                await db.clearAllData();
            }
            await db.setTenantId(newTenantId);

            // Data should be preserved (first login doesn't clear)
            expect(await db.accounts.count()).toBe(1);
            expect(await db.getTenantId()).toBe(tenant1Id);
        });

        it('should not clear database when same tenant logs in again', async () => {
            // Setup: Store tenant 1 ID and data
            await db.setTenantId(tenant1Id);
            await db.accounts.add({
                id: generateUUID(),
                name: 'Tenant 1 Account',
                currency: 'GBP',
                current_balance: 1000,
                tenant_id: tenant1Id,
                created_at: new Date().toISOString(),
                updated_at: new Date().toISOString()
            });
            await db.events.add({
                id: generateUUID(),
                description: 'Tenant 1 Event',
                amount: -50,
                currency: 'GBP',
                rate_to_base: 1,
                event_date: '2025-01-15',
                account_id: generateUUID(),
                tenant_id: tenant1Id,
                created_at: new Date().toISOString(),
                updated_at: new Date().toISOString()
            });

            expect(await db.accounts.count()).toBe(1);
            expect(await db.events.count()).toBe(1);

            // Simulate same tenant login
            const storedTenantId = await db.getTenantId();
            const newTenantId = tenant1Id; // Same tenant

            if (storedTenantId && storedTenantId !== newTenantId) {
                await db.clearAllData();
            }
            await db.setTenantId(newTenantId);

            // Data should be preserved
            expect(await db.accounts.count()).toBe(1);
            expect(await db.events.count()).toBe(1);
        });

        it('should clear database when different tenant logs in', async () => {
            // Setup: Store tenant 1 data
            await db.setTenantId(tenant1Id);
            await db.accounts.add({
                id: generateUUID(),
                name: 'Tenant 1 Account',
                currency: 'GBP',
                current_balance: 1000,
                tenant_id: tenant1Id,
                created_at: new Date().toISOString(),
                updated_at: new Date().toISOString()
            });
            await db.stories.add({
                id: generateUUID(),
                name: 'Tenant 1 Story',
                start_date: '2025-01-01',
                display_currency: 'GBP',
                funding_mode: 'projected',
                goal_type: 'none',
                tenant_id: tenant1Id,
                created_at: new Date().toISOString(),
                updated_at: new Date().toISOString()
            });
            await db.events.add({
                id: generateUUID(),
                description: 'Tenant 1 Event',
                amount: -100,
                currency: 'GBP',
                rate_to_base: 1,
                event_date: '2025-01-15',
                account_id: generateUUID(),
                tenant_id: tenant1Id,
                created_at: new Date().toISOString(),
                updated_at: new Date().toISOString()
            });

            expect(await db.accounts.count()).toBe(1);
            expect(await db.stories.count()).toBe(1);
            expect(await db.events.count()).toBe(1);

            // Simulate different tenant login
            const storedTenantId = await db.getTenantId();
            const newTenantId = tenant2Id; // Different tenant!

            if (storedTenantId && storedTenantId !== newTenantId) {
                await db.clearAllData();
            }
            await db.setTenantId(newTenantId);

            // All data should be cleared
            expect(await db.accounts.count()).toBe(0);
            expect(await db.stories.count()).toBe(0);
            expect(await db.events.count()).toBe(0);
            expect(await db.getTenantId()).toBe(tenant2Id);
        });

        it('should clear sync_queue on tenant change', async () => {
            // Setup: Tenant 1 has pending sync changes
            await db.setTenantId(tenant1Id);
            await db.sync_queue.add({
                entity_type: 'account',
                entity_id: generateUUID(),
                action: 'create',
                data: { name: 'Pending Account', tenant_id: tenant1Id },
                queued_at: new Date().toISOString()
            });
            await db.sync_queue.add({
                entity_type: 'event',
                entity_id: generateUUID(),
                action: 'update',
                data: { description: 'Updated Event', tenant_id: tenant1Id },
                queued_at: new Date().toISOString()
            });

            expect(await db.sync_queue.count()).toBe(2);

            // Tenant change
            const storedTenantId = await db.getTenantId();
            if (storedTenantId && storedTenantId !== tenant2Id) {
                await db.clearAllData();
            }
            await db.setTenantId(tenant2Id);

            // Sync queue should be cleared
            expect(await db.sync_queue.count()).toBe(0);
        });

        it('should clear conflicts on tenant change', async () => {
            // Setup: Tenant 1 has unresolved conflicts
            await db.setTenantId(tenant1Id);
            await db.conflicts.add({
                id: generateUUID(),
                entity_type: 'account',
                entity_id: generateUUID(),
                conflict_type: 'edit_edit',
                client_version: { name: 'Local Name' },
                server_version: { name: 'Server Name' },
                detected_at: new Date().toISOString()
            });

            expect(await db.conflicts.count()).toBe(1);

            // Tenant change
            const storedTenantId = await db.getTenantId();
            if (storedTenantId && storedTenantId !== tenant2Id) {
                await db.clearAllData();
            }
            await db.setTenantId(tenant2Id);

            // Conflicts should be cleared
            expect(await db.conflicts.count()).toBe(0);
        });
    });

    // ==================== DATA ISOLATION VERIFICATION ====================

    describe('Data Isolation Verification', () => {
        it('should not expose tenant A data to tenant B', async () => {
            // Tenant A logs in and creates data
            await db.setTenantId(tenant1Id);

            const tenantAAccount = {
                id: generateUUID(),
                name: 'Tenant A Secret Account',
                currency: 'GBP',
                current_balance: 50000,
                tenant_id: tenant1Id,
                created_at: new Date().toISOString(),
                updated_at: new Date().toISOString()
            };
            await db.accounts.add(tenantAAccount);

            const tenantAEvent = {
                id: generateUUID(),
                description: 'Tenant A Salary',
                amount: 5000,
                currency: 'GBP',
                rate_to_base: 1,
                event_date: '2025-01-01',
                account_id: tenantAAccount.id,
                tenant_id: tenant1Id,
                created_at: new Date().toISOString(),
                updated_at: new Date().toISOString()
            };
            await db.events.add(tenantAEvent);

            // Verify Tenant A data exists
            expect(await db.accounts.count()).toBe(1);
            expect(await db.events.count()).toBe(1);

            // Tenant B logs in (different tenant)
            const storedTenantId = await db.getTenantId();
            if (storedTenantId && storedTenantId !== tenant2Id) {
                await db.clearAllData();
            }
            await db.setTenantId(tenant2Id);

            // Tenant B should see empty database
            expect(await db.accounts.count()).toBe(0);
            expect(await db.events.count()).toBe(0);

            // Specifically verify Tenant A's account is not accessible
            const tenantAAccountCheck = await db.accounts.get(tenantAAccount.id);
            expect(tenantAAccountCheck).toBeUndefined();
        });

        it('should clear all tenant-scoped tables on tenant change', async () => {
            // Setup: Populate all tenant-scoped tables for tenant 1
            await db.setTenantId(tenant1Id);

            await db.accounts.add({
                id: generateUUID(),
                name: 'Account',
                currency: 'GBP',
                current_balance: 1000,
                tenant_id: tenant1Id,
                created_at: new Date().toISOString(),
                updated_at: new Date().toISOString()
            });

            await db.stories.add({
                id: generateUUID(),
                name: 'Story',
                start_date: '2025-01-01',
                display_currency: 'GBP',
                funding_mode: 'projected',
                goal_type: 'none',
                tenant_id: tenant1Id,
                created_at: new Date().toISOString(),
                updated_at: new Date().toISOString()
            });

            await db.events.add({
                id: generateUUID(),
                description: 'Event',
                amount: -100,
                currency: 'GBP',
                rate_to_base: 1,
                event_date: '2025-01-15',
                account_id: generateUUID(),
                tenant_id: tenant1Id,
                created_at: new Date().toISOString(),
                updated_at: new Date().toISOString()
            });

            await db.recurring_rules.add({
                id: generateUUID(),
                description: 'Monthly Rent',
                amount: -1000,
                currency: 'GBP',
                account_id: generateUUID(),
                frequency: 'monthly',
                day: 1,
                start_date: '2025-01-01',
                tenant_id: tenant1Id,
                created_at: new Date().toISOString(),
                updated_at: new Date().toISOString()
            });

            await db.sync_queue.add({
                entity_type: 'account',
                entity_id: generateUUID(),
                action: 'create',
                data: {},
                queued_at: new Date().toISOString()
            });

            await db.conflicts.add({
                id: generateUUID(),
                entity_type: 'event',
                entity_id: generateUUID(),
                conflict_type: 'edit_edit',
                detected_at: new Date().toISOString()
            });

            await db.sync_meta.put({ id: 'lastSyncAt', value: new Date().toISOString() });

            // Verify all tables have data
            expect(await db.accounts.count()).toBe(1);
            expect(await db.stories.count()).toBe(1);
            expect(await db.events.count()).toBe(1);
            expect(await db.recurring_rules.count()).toBe(1);
            expect(await db.sync_queue.count()).toBe(1);
            expect(await db.conflicts.count()).toBe(1);
            // sync_meta has tenant_id + lastSyncAt
            expect(await db.sync_meta.count()).toBeGreaterThanOrEqual(2);

            // Tenant change
            const storedTenantId = await db.getTenantId();
            if (storedTenantId && storedTenantId !== tenant2Id) {
                await db.clearAllData();
            }
            await db.setTenantId(tenant2Id);

            // All tenant-scoped tables should be empty
            expect(await db.accounts.count()).toBe(0);
            expect(await db.stories.count()).toBe(0);
            expect(await db.events.count()).toBe(0);
            expect(await db.recurring_rules.count()).toBe(0);
            expect(await db.sync_queue.count()).toBe(0);
            expect(await db.conflicts.count()).toBe(0);
            // sync_meta should only have the new tenant_id
            expect(await db.sync_meta.count()).toBe(1);
        });

        it('should preserve settings table on tenant change (user preferences)', async () => {
            // Setup: User has settings preferences
            await db.setTenantId(tenant1Id);

            // Note: db.js initializes default settings, so we update rather than add
            const testSettingsId = 'test-user-settings';
            await db.settings.put({
                id: testSettingsId,
                base_currency: 'EUR',
                default_currency: 'EUR',
                date_format: 'YYYY-MM-DD',
                rates: { USD: 1.10, GBP: 0.85 }
            });

            // Count before tenant change (may include default settings)
            const countBefore = await db.settings.count();
            expect(countBefore).toBeGreaterThanOrEqual(1);

            // Verify our test settings exist
            const settingsBefore = await db.settings.get(testSettingsId);
            expect(settingsBefore).toBeDefined();
            expect(settingsBefore.base_currency).toBe('EUR');

            // Tenant change - settings should be preserved per clearAllData() design
            const storedTenantId = await db.getTenantId();
            if (storedTenantId && storedTenantId !== tenant2Id) {
                await db.clearAllData();
            }
            await db.setTenantId(tenant2Id);

            // Settings should still exist (clearAllData preserves settings)
            const countAfter = await db.settings.count();
            expect(countAfter).toBe(countBefore); // Same count as before

            // Our specific settings entry should still exist
            const settingsAfter = await db.settings.get(testSettingsId);
            expect(settingsAfter).toBeDefined();
            expect(settingsAfter.base_currency).toBe('EUR');
        });
    });

    // ==================== EDGE CASES ====================

    describe('Edge Cases', () => {
        it('should handle null tenant_id gracefully', async () => {
            // Setup: Store tenant 1 data
            await db.setTenantId(tenant1Id);
            await db.accounts.add({
                id: generateUUID(),
                name: 'Account',
                currency: 'GBP',
                current_balance: 1000,
                tenant_id: tenant1Id,
                created_at: new Date().toISOString(),
                updated_at: new Date().toISOString()
            });

            // Simulate login with null tenant_id (malformed user data)
            const storedTenantId = await db.getTenantId();
            const newTenantId = null;

            // Should not crash, treats null as "no tenant" (clear to be safe)
            if (storedTenantId && storedTenantId !== newTenantId) {
                await db.clearAllData();
            }
            if (newTenantId) {
                await db.setTenantId(newTenantId);
            }

            // Data should be cleared since tenant_id changed from value to null
            expect(await db.accounts.count()).toBe(0);
        });

        it('should handle undefined tenant_id gracefully', async () => {
            // Setup: Store tenant 1 data
            await db.setTenantId(tenant1Id);
            await db.accounts.add({
                id: generateUUID(),
                name: 'Account',
                currency: 'GBP',
                current_balance: 1000,
                tenant_id: tenant1Id,
                created_at: new Date().toISOString(),
                updated_at: new Date().toISOString()
            });

            // Simulate login with undefined tenant_id
            const storedTenantId = await db.getTenantId();
            const newTenantId = undefined;

            // Should not crash
            if (storedTenantId && storedTenantId !== newTenantId) {
                await db.clearAllData();
            }
            if (newTenantId) {
                await db.setTenantId(newTenantId);
            }

            // Data should be cleared since tenant_id changed
            expect(await db.accounts.count()).toBe(0);
        });

        it('should work correctly after multiple tenant switches', async () => {
            const tenant3Id = generateUUID();

            // Tenant 1 logs in
            await db.setTenantId(tenant1Id);
            await db.accounts.add({
                id: generateUUID(),
                name: 'Tenant 1 Account',
                currency: 'GBP',
                current_balance: 1000,
                tenant_id: tenant1Id,
                created_at: new Date().toISOString(),
                updated_at: new Date().toISOString()
            });
            expect(await db.accounts.count()).toBe(1);

            // Tenant 2 logs in
            let storedTenantId = await db.getTenantId();
            if (storedTenantId && storedTenantId !== tenant2Id) {
                await db.clearAllData();
            }
            await db.setTenantId(tenant2Id);
            await db.accounts.add({
                id: generateUUID(),
                name: 'Tenant 2 Account',
                currency: 'USD',
                current_balance: 2000,
                tenant_id: tenant2Id,
                created_at: new Date().toISOString(),
                updated_at: new Date().toISOString()
            });
            expect(await db.accounts.count()).toBe(1);
            expect(await db.getTenantId()).toBe(tenant2Id);

            // Tenant 3 logs in
            storedTenantId = await db.getTenantId();
            if (storedTenantId && storedTenantId !== tenant3Id) {
                await db.clearAllData();
            }
            await db.setTenantId(tenant3Id);
            expect(await db.accounts.count()).toBe(0);
            expect(await db.getTenantId()).toBe(tenant3Id);

            // Tenant 1 logs in again
            storedTenantId = await db.getTenantId();
            if (storedTenantId && storedTenantId !== tenant1Id) {
                await db.clearAllData();
            }
            await db.setTenantId(tenant1Id);
            expect(await db.accounts.count()).toBe(0); // Cleared, needs fresh sync
            expect(await db.getTenantId()).toBe(tenant1Id);
        });
    });

    // ==================== BACKUP/RESTORE TENANT ISOLATION ====================

    describe('Backup/Restore Tenant Isolation', () => {
        /**
         * Helper to create a backup object (simulates downloadBackup output)
         */
        function createBackup(version, tenantId, accounts = [], stories = [], events = []) {
            return {
                version,
                exported_at: new Date().toISOString(),
                tenant_id: tenantId,
                accounts,
                stories,
                events,
                users: [],
                settings: null,
                recurring_rules: []
            };
        }

        /**
         * Helper to simulate performBackupRestore validation logic
         * Returns { success: boolean, error?: string }
         */
        function validateBackupRestore(backup, currentTenantId) {
            // Version validation
            if (!backup.version || typeof backup.version !== 'string') {
                return { success: false, error: 'Invalid backup: missing or invalid version' };
            }

            // Tenant isolation check for v1.1+ backups
            if (backup.version !== '1.0' && backup.tenant_id) {
                if (currentTenantId && backup.tenant_id !== currentTenantId) {
                    return { success: false, error: 'Cannot restore: backup belongs to a different tenant' };
                }
            }

            // Required arrays validation
            const requiredArrays = ['accounts', 'stories', 'events'];
            for (const field of requiredArrays) {
                if (!backup[field] || !Array.isArray(backup[field])) {
                    return { success: false, error: `Invalid backup: missing or invalid ${field} array` };
                }
            }

            return { success: true };
        }

        describe('Backup Format', () => {
            it('should create v1.1 backup with tenant_id', () => {
                const backup = createBackup('1.1', tenant1Id);
                expect(backup.version).toBe('1.1');
                expect(backup.tenant_id).toBe(tenant1Id);
            });

            it('should include all required fields in backup', () => {
                const backup = createBackup('1.1', tenant1Id);
                expect(backup).toHaveProperty('version');
                expect(backup).toHaveProperty('exported_at');
                expect(backup).toHaveProperty('tenant_id');
                expect(backup).toHaveProperty('accounts');
                expect(backup).toHaveProperty('stories');
                expect(backup).toHaveProperty('events');
                expect(backup).toHaveProperty('users');
                expect(backup).toHaveProperty('settings');
                expect(backup).toHaveProperty('recurring_rules');
            });
        });

        describe('Restore Tenant Validation', () => {
            it('should allow restore when backup tenant_id matches current tenant', () => {
                const backup = createBackup('1.1', tenant1Id);
                const result = validateBackupRestore(backup, tenant1Id);
                expect(result.success).toBe(true);
            });

            it('should reject restore when backup tenant_id differs from current tenant', () => {
                const backup = createBackup('1.1', tenant1Id);
                const result = validateBackupRestore(backup, tenant2Id);
                expect(result.success).toBe(false);
                expect(result.error).toBe('Cannot restore: backup belongs to a different tenant');
            });

            it('should allow legacy v1.0 backups without tenant_id check', () => {
                // v1.0 backups don't have tenant_id, so they bypass the check
                const legacyBackup = {
                    version: '1.0',
                    exported_at: new Date().toISOString(),
                    accounts: [],
                    stories: [],
                    events: [],
                    users: [],
                    settings: null,
                    recurring_rules: []
                };
                const result = validateBackupRestore(legacyBackup, tenant1Id);
                expect(result.success).toBe(true);
            });

            it('should allow restore when backup has tenant_id but user has no tenant', () => {
                // Edge case: user without tenant_id (shouldn't happen, but handle gracefully)
                const backup = createBackup('1.1', tenant1Id);
                const result = validateBackupRestore(backup, null);
                expect(result.success).toBe(true);
            });

            it('should allow restore when backup has no tenant_id', () => {
                // v1.1+ backup without tenant_id (user was not logged in during export)
                const backup = createBackup('1.1', null);
                const result = validateBackupRestore(backup, tenant1Id);
                expect(result.success).toBe(true);
            });
        });

        describe('Restore Validation Edge Cases', () => {
            it('should reject backup with missing version', () => {
                const invalidBackup = {
                    exported_at: new Date().toISOString(),
                    tenant_id: tenant1Id,
                    accounts: [],
                    stories: [],
                    events: []
                };
                const result = validateBackupRestore(invalidBackup, tenant1Id);
                expect(result.success).toBe(false);
                expect(result.error).toContain('version');
            });

            it('should reject backup with missing accounts array', () => {
                const invalidBackup = {
                    version: '1.1',
                    tenant_id: tenant1Id,
                    stories: [],
                    events: []
                };
                const result = validateBackupRestore(invalidBackup, tenant1Id);
                expect(result.success).toBe(false);
                expect(result.error).toContain('accounts');
            });

            it('should reject backup with non-array accounts', () => {
                const invalidBackup = {
                    version: '1.1',
                    tenant_id: tenant1Id,
                    accounts: 'not an array',
                    stories: [],
                    events: []
                };
                const result = validateBackupRestore(invalidBackup, tenant1Id);
                expect(result.success).toBe(false);
                expect(result.error).toContain('accounts');
            });
        });

        describe('Security: Cross-Tenant Data Prevention', () => {
            it('should prevent restoring tenant A backup when logged in as tenant B', async () => {
                // Create backup from tenant A with data
                const tenantABackup = createBackup('1.1', tenant1Id, [
                    {
                        id: generateUUID(),
                        name: 'Tenant A Secret Account',
                        currency: 'GBP',
                        current_balance: 100000,
                        tenant_id: tenant1Id
                    }
                ]);

                // User is logged in as tenant B
                await db.setTenantId(tenant2Id);

                // Attempt to restore should fail validation
                const result = validateBackupRestore(tenantABackup, tenant2Id);
                expect(result.success).toBe(false);
                expect(result.error).toBe('Cannot restore: backup belongs to a different tenant');
            });

            it('should allow restoring own tenant backup', async () => {
                // Create backup from tenant A
                const tenantABackup = createBackup('1.1', tenant1Id, [
                    {
                        id: generateUUID(),
                        name: 'My Account',
                        currency: 'GBP',
                        current_balance: 5000,
                        tenant_id: tenant1Id
                    }
                ]);

                // User is logged in as tenant A
                await db.setTenantId(tenant1Id);

                // Restore should pass validation
                const result = validateBackupRestore(tenantABackup, tenant1Id);
                expect(result.success).toBe(true);
            });

            it('should handle UUID tenant_id comparison correctly', () => {
                // Ensure UUIDs are compared as strings
                const backupTenantId = '550e8400-e29b-41d4-a716-446655440000';
                const currentTenantId = '550e8400-e29b-41d4-a716-446655440000';

                const backup = createBackup('1.1', backupTenantId);
                const result = validateBackupRestore(backup, currentTenantId);
                expect(result.success).toBe(true);
            });

            it('should reject even with similar but different tenant_ids', () => {
                // One character difference
                const backupTenantId = '550e8400-e29b-41d4-a716-446655440000';
                const currentTenantId = '550e8400-e29b-41d4-a716-446655440001';

                const backup = createBackup('1.1', backupTenantId);
                const result = validateBackupRestore(backup, currentTenantId);
                expect(result.success).toBe(false);
            });
        });
    });
});
