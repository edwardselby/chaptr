/**
 * Storage Adapter - Progressive Enhancement for CHAPTR
 *
 * Three-tier architecture:
 * - Mode 1 (Full): Dexie + Sync + Offline (HTTPS + IndexedDB required)
 * - Mode 2 (Sync-Only): Online sync without Dexie (private browsing fallback)
 * - Mode 3 (Basic): Direct REST calls (HTTP fallback, last write wins)
 *
 * Mode detection: <500ms timeout, locked at initialization
 * Queue limits: Warn at 400, hard block at 500
 */

import { db } from './db.js';
import { apiRequest, generateClientId, showToast, getModeAwareErrorMessage, generateUUID } from './utils.js';

class StorageAdapter {
    constructor() {
        this.mode = null;              // 'full' | 'sync-only' | 'basic'
        this.lastSyncAt = null;        // ISO timestamp of last successful sync
        this.memoryStore = {           // Mode 2 & 3 in-memory storage
            accounts: [],
            stories: [],
            events: [],
            recurring_rules: [],
            settings: null
        };
    }

    /**
     * Initialize storage adapter with mode detection
     *
     * Detection order (with timeout <500ms):
     * 1. Check forced mode (query param > localStorage > auto-detect)
     * 2. Try Mode 1 (Full): Attempt Dexie.open()
     * 3. Try Mode 2 (Sync-Only): testSyncEndpoint() with 500ms timeout
     * 4. Fallback Mode 3 (Basic): Last resort for HTTP/restricted environments
     *
     * @returns {Promise<string>} Detected mode ('full', 'sync-only', or 'basic')
     */
    async init() {
        console.log('[CHAPTR] Initializing storage adapter...');

        // 1. Check for forced mode
        const forcedMode = this.getForcedMode();
        if (forcedMode) {
            this.mode = forcedMode;
            console.log(`[CHAPTR] Mode forced: ${this.mode}`);
            await this.bootstrap();
            this.logModeCapabilities();
            return this.mode;
        }

        // 2. Try Mode 1 (Full): Dexie + Offline
        try {
            await db.open();
            this.mode = 'full';
            console.log('[CHAPTR] Mode detected: Full (Dexie + Offline)');
            await this.bootstrap();
            this.logModeCapabilities();
            return this.mode;
        } catch (error) {
            console.warn('[CHAPTR] Dexie unavailable:', error.message);
        }

        // 3. Try Mode 2 (Sync-Only): Online sync without Dexie
        if (navigator.onLine) {
            try {
                await this.testSyncEndpoint();
                this.mode = 'sync-only';
                console.log('[CHAPTR] Mode detected: Sync-Only (Online required)');
                await this.bootstrap();
                this.logModeCapabilities();
                return this.mode;
            } catch (error) {
                console.warn('[CHAPTR] Sync endpoint unavailable:', error.message);
            }
        }

        // 4. Fallback Mode 3 (Basic): Direct REST
        this.mode = 'basic';
        console.log('[CHAPTR] Mode detected: Basic (Limited functionality)');
        await this.bootstrap();
        this.logModeCapabilities();
        return this.mode;
    }

    /**
     * Check for forced mode via query param or localStorage
     *
     * Priority: ?mode=full > localStorage.FORCE_MODE > auto-detect
     *
     * Usage:
     * - Query param: ?mode=full or ?mode=sync-only or ?mode=basic
     * - localStorage: localStorage.setItem('FORCE_MODE', 'sync-only')
     *
     * @returns {string|null} Forced mode or null if auto-detect
     */
    getForcedMode() {
        // Check query parameter first (highest priority)
        const urlParams = new URLSearchParams(window.location.search);
        const queryMode = urlParams.get('mode');
        if (queryMode && ['full', 'sync-only', 'basic'].includes(queryMode)) {
            return queryMode;
        }

        // Check localStorage (second priority)
        const storageMode = localStorage.getItem('FORCE_MODE');
        if (storageMode && ['full', 'sync-only', 'basic'].includes(storageMode)) {
            return storageMode;
        }

        return null;
    }

    /**
     * Test sync endpoint availability with 500ms timeout
     *
     * Used during mode detection to determine if Mode 2 (Sync-Only) is available.
     * If sync endpoint responds within 500ms, we can use Mode 2.
     *
     * @throws {Error} If endpoint unavailable or timeout exceeded
     * @returns {Promise<void>}
     */
    async testSyncEndpoint() {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 500);

        try {
            const response = await fetch('/api/sync/full', {
                method: 'GET',
                signal: controller.signal,
                headers: {
                    'Authorization': `Bearer ${localStorage.getItem('jwt_token')}`
                }
            });

            clearTimeout(timeoutId);

            if (!response.ok) {
                throw new Error(`Sync endpoint returned ${response.status}`);
            }

            return; // Success - sync endpoint available
        } catch (error) {
            clearTimeout(timeoutId);
            if (error.name === 'AbortError') {
                throw new Error('Sync endpoint timeout (>500ms)');
            }
            throw error;
        }
    }

    /**
     * Log mode capabilities to console
     *
     * Displays current mode and available features for debugging.
     */
    logModeCapabilities() {
        const capabilities = {
            offline: this.mode === 'full',
            sync: this.mode !== 'basic',
            storage: this.mode === 'full' ? 'IndexedDB (Dexie)' : 'Memory'
        };

        console.log('[CHAPTR] Initialized in mode:', this.mode);
        console.log('[CHAPTR] Capabilities:', capabilities);
    }

    /**
     * Bootstrap data based on detected mode
     *
     * Mode 1 & 2: GET /api/sync/full (efficient single request)
     * Mode 3: Sequential REST calls (5 endpoints)
     *
     * @returns {Promise<void>}
     */
    async bootstrap() {
        switch (this.mode) {
            case 'full':
                await this.bootstrap_Full();
                break;
            case 'sync-only':
                await this.bootstrap_SyncOnly();
                break;
            case 'basic':
                await this.bootstrap_Basic();
                break;
        }
    }

    /**
     * Bootstrap Mode 1 (Full): Check Dexie, fetch if empty
     *
     * @returns {Promise<void>}
     */
    async bootstrap_Full() {
        const accountCount = await db.accounts.count();

        if (accountCount === 0) {
            console.log('[CHAPTR] Dexie empty, fetching full sync...');
            await this.fetchAndPopulateDexie();
        } else {
            console.log(`[CHAPTR] Dexie loaded (${accountCount} accounts)`);
        }

        // Load last sync timestamp from metadata
        const syncMeta = await db.sync_meta.get('lastSyncAt');
        this.lastSyncAt = syncMeta?.value || null;
    }

    /**
     * Bootstrap Mode 2 (Sync-Only): Always fetch from server
     *
     * No sessionStorage - always fresh data on page load.
     * Data stored in memory only (Alpine.js state).
     *
     * @returns {Promise<void>}
     */
    async bootstrap_SyncOnly() {
        console.log('[CHAPTR] Fetching full sync (Mode 2)...');
        const response = await apiRequest('/api/sync/full', { method: 'GET' });
        const data = await response.json();

        // Populate memory store
        this.memoryStore.accounts = data.accounts;
        this.memoryStore.stories = data.stories;
        this.memoryStore.events = data.events;
        this.memoryStore.recurring_rules = data.recurring_rules;
        this.memoryStore.settings = data.settings;
        this.lastSyncAt = data.sync_timestamp;

        console.log(`[CHAPTR] Memory loaded (${data.accounts.length} accounts)`);
    }

    /**
     * Bootstrap Mode 3 (Basic): Sequential REST calls
     *
     * Slower than Mode 1/2 but works in all environments.
     *
     * @returns {Promise<void>}
     */
    async bootstrap_Basic() {
        console.log('[CHAPTR] Fetching via REST endpoints (Mode 3)...');

        // Sequential REST calls (5 endpoints)
        const [accountsRes, storiesRes, eventsRes, rulesRes, settingsRes] = await Promise.all([
            apiRequest('/api/accounts', { method: 'GET' }),
            apiRequest('/api/stories', { method: 'GET' }),
            apiRequest('/api/events', { method: 'GET' }),
            apiRequest('/api/recurring-rules', { method: 'GET' }),
            apiRequest('/api/settings', { method: 'GET' })
        ]);

        // Populate memory store
        this.memoryStore.accounts = await accountsRes.json();
        this.memoryStore.stories = await storiesRes.json();
        this.memoryStore.events = await eventsRes.json();
        this.memoryStore.recurring_rules = await rulesRes.json();
        this.memoryStore.settings = await settingsRes.json();

        console.log(`[CHAPTR] Memory loaded (${this.memoryStore.accounts.length} accounts)`);
    }

    /**
     * Fetch full sync and populate Dexie (Mode 1 only)
     *
     * @returns {Promise<void>}
     */
    async fetchAndPopulateDexie() {
        const response = await apiRequest('/api/sync/full', { method: 'GET' });
        const data = await response.json();

        // Populate Dexie tables
        await db.transaction('rw', [db.accounts, db.stories, db.events, db.recurring_rules, db.settings], async () => {
            await db.accounts.bulkPut(data.accounts);
            await db.stories.bulkPut(data.stories);
            await db.events.bulkPut(data.events);
            await db.recurring_rules.bulkPut(data.recurring_rules);
            await db.settings.put(data.settings);
        });

        // Store sync timestamp
        await db.sync_meta.put({ key: 'lastSyncAt', value: data.sync_timestamp });
        this.lastSyncAt = data.sync_timestamp;

        console.log('[CHAPTR] Dexie populated from full sync');
    }

    // ==================== CRUD Operations ====================

    /**
     * Get all accounts
     *
     * @returns {Promise<Array>} Array of account objects
     */
    async getAccounts() {
        switch (this.mode) {
            case 'full':
                return await db.accounts.where({ is_archived: 0 }).toArray();
            case 'sync-only':
            case 'basic':
                return this.memoryStore.accounts.filter(a => !a.is_archived);
        }
    }

    /**
     * Get all stories
     *
     * @returns {Promise<Array>} Array of story objects
     */
    async getStories() {
        switch (this.mode) {
            case 'full':
                return await db.stories.toArray();
            case 'sync-only':
            case 'basic':
                return this.memoryStore.stories;
        }
    }

    /**
     * Get all events
     *
     * @returns {Promise<Array>} Array of event objects
     */
    async getEvents() {
        switch (this.mode) {
            case 'full':
                return await db.events.toArray();
            case 'sync-only':
            case 'basic':
                return this.memoryStore.events;
        }
    }

    /**
     * Get all recurring rules
     *
     * @returns {Promise<Array>} Array of recurring rule objects
     */
    async getRecurringRules() {
        switch (this.mode) {
            case 'full':
                return await db.recurring_rules.toArray();
            case 'sync-only':
            case 'basic':
                return this.memoryStore.recurring_rules;
        }
    }

    /**
     * Get settings
     *
     * @returns {Promise<Object>} Settings object
     */
    async getSettings() {
        switch (this.mode) {
            case 'full':
                return await db.settings.toArray().then(arr => arr[0]);
            case 'sync-only':
            case 'basic':
                return this.memoryStore.settings;
        }
    }

    // ==================== CREATE Operations ====================

    /**
     * Create account
     *
     * Mode 1 (Full): Optimistic Dexie write + queue + API attempt
     * Mode 2 (Sync-Only): Immediate sync required
     * Mode 3 (Basic): Direct REST POST
     *
     * @param {Object} accountData - Account data (name, currency, current_balance, is_default)
     * @returns {Promise<Object>} Created account
     */
    async createAccount(accountData) {
        const now = new Date().toISOString();

        switch (this.mode) {
            case 'full':
                return await this.createAccount_Full(accountData, now);
            case 'sync-only':
                return await this.createAccount_SyncOnly(accountData);
            case 'basic':
                return await this.createAccount_Basic(accountData);
        }
    }

    async createAccount_Full(accountData, now) {
        const { generateUUID } = await import('./utils.js');
        const localId = generateUUID();

        const fullData = {
            id: localId,
            ...accountData,
            is_archived: false,
            rate_to_base: 1.0,
            created_at: now,
            updated_at: now
        };

        // 1. Optimistic Dexie write
        await db.accounts.add(fullData);

        // 2. Queue for sync
        await db.queueChange('account', localId, 'create', fullData);

        // 3. Immediate API attempt if online
        if (navigator.onLine) {
            try {
                const response = await apiRequest('/api/accounts', {
                    method: 'POST',
                    body: JSON.stringify(accountData)
                });

                if (response.ok) {
                    const serverData = await response.json();
                    // Replace temp ID with server ID
                    await db.accounts.delete(localId);
                    await db.accounts.put(serverData);
                    await db.sync_queue.where({ entity_id: localId }).delete();
                    return serverData;
                }
            } catch (error) {
                console.warn('[CHAPTR] API call failed, queued for sync:', error.message);
                // Check queue limit
                await this.checkQueueLimit();
            }
        }

        return fullData;
    }

    async createAccount_SyncOnly(accountData) {
        try {
            const response = await apiRequest('/api/accounts', {
                method: 'POST',
                body: JSON.stringify(accountData)
            });

            if (!response.ok) {
                throw new Error(`API error: ${response.status}`);
            }

            const serverData = await response.json();

            // Add to memory store
            this.memoryStore.accounts.push(serverData);

            return serverData;
        } catch (error) {
            showToast(getModeAwareErrorMessage(this.mode, 'create account'), 'error');
            throw error;
        }
    }

    async createAccount_Basic(accountData) {
        try {
            const response = await apiRequest('/api/accounts', {
                method: 'POST',
                body: JSON.stringify(accountData)
            });

            if (!response.ok) {
                throw new Error(`API error: ${response.status}`);
            }

            const serverData = await response.json();

            // Add to memory store
            this.memoryStore.accounts.push(serverData);

            return serverData;
        } catch (error) {
            showToast(getModeAwareErrorMessage(this.mode, 'create account'), 'error');
            throw error;
        }
    }

    // ==================== UPDATE Operations ====================

    /**
     * Update account
     *
     * @param {string} accountId - Account UUID
     * @param {Object} updates - Fields to update
     * @returns {Promise<Object>} Updated account
     */
    async updateAccount(accountId, updates) {
        const now = new Date().toISOString();
        const updateData = { ...updates, updated_at: now };

        switch (this.mode) {
            case 'full':
                return await this.updateAccount_Full(accountId, updateData);
            case 'sync-only':
                return await this.updateAccount_SyncOnly(accountId, updateData);
            case 'basic':
                return await this.updateAccount_Basic(accountId, updateData);
        }
    }

    async updateAccount_Full(accountId, updateData) {
        // 1. Optimistic Dexie update
        await db.accounts.update(accountId, updateData);

        // 2. Queue for sync
        await db.queueChange('account', accountId, 'update', updateData);

        // 3. Immediate API attempt if online
        if (navigator.onLine) {
            try {
                const response = await apiRequest(`/api/accounts/${accountId}`, {
                    method: 'PUT',
                    body: JSON.stringify(updateData)
                });

                if (response.ok) {
                    const serverData = await response.json();
                    await db.accounts.put(serverData);
                    await db.sync_queue.where({ entity_id: accountId, action: 'update' }).delete();
                    return serverData;
                }
            } catch (error) {
                console.warn('[CHAPTR] API call failed, queued for sync:', error.message);
                await this.checkQueueLimit();
            }
        }

        return await db.accounts.get(accountId);
    }

    async updateAccount_SyncOnly(accountId, updateData) {
        try {
            const response = await apiRequest(`/api/accounts/${accountId}`, {
                method: 'PUT',
                body: JSON.stringify(updateData)
            });

            if (!response.ok) {
                throw new Error(`API error: ${response.status}`);
            }

            const serverData = await response.json();

            // Update in memory store
            const index = this.memoryStore.accounts.findIndex(a => a.id === accountId);
            if (index !== -1) {
                this.memoryStore.accounts[index] = serverData;
            }

            return serverData;
        } catch (error) {
            showToast(getModeAwareErrorMessage(this.mode, 'update account'), 'error');
            throw error;
        }
    }

    async updateAccount_Basic(accountId, updateData) {
        try {
            const response = await apiRequest(`/api/accounts/${accountId}`, {
                method: 'PUT',
                body: JSON.stringify(updateData)
            });

            if (!response.ok) {
                throw new Error(`API error: ${response.status}`);
            }

            const serverData = await response.json();

            // Update in memory store
            const index = this.memoryStore.accounts.findIndex(a => a.id === accountId);
            if (index !== -1) {
                this.memoryStore.accounts[index] = serverData;
            }

            return serverData;
        } catch (error) {
            showToast(getModeAwareErrorMessage(this.mode, 'update account'), 'error');
            throw error;
        }
    }

    // ==================== DELETE Operations ====================

    /**
     * Delete account (soft delete - mark as archived)
     *
     * @param {string} accountId - Account UUID
     * @returns {Promise<void>}
     */
    async deleteAccount(accountId) {
        const now = new Date().toISOString();

        switch (this.mode) {
            case 'full':
                return await this.deleteAccount_Full(accountId, now);
            case 'sync-only':
                return await this.deleteAccount_SyncOnly(accountId);
            case 'basic':
                return await this.deleteAccount_Basic(accountId);
        }
    }

    async deleteAccount_Full(accountId, now) {
        // 1. Soft delete in Dexie (mark as archived)
        await db.accounts.update(accountId, {
            is_archived: true,
            updated_at: now
        });

        // 2. Queue for sync
        await db.queueChange('account', accountId, 'delete', { is_archived: true });

        // 3. Immediate API attempt if online
        if (navigator.onLine) {
            try {
                const response = await apiRequest(`/api/accounts/${accountId}`, {
                    method: 'DELETE'
                });

                if (response.ok) {
                    await db.sync_queue.where({ entity_id: accountId, action: 'delete' }).delete();
                }
            } catch (error) {
                console.warn('[CHAPTR] API call failed, queued for sync:', error.message);
                await this.checkQueueLimit();
            }
        }
    }

    async deleteAccount_SyncOnly(accountId) {
        try {
            const response = await apiRequest(`/api/accounts/${accountId}`, {
                method: 'DELETE'
            });

            if (!response.ok) {
                throw new Error(`API error: ${response.status}`);
            }

            // Remove from memory store
            this.memoryStore.accounts = this.memoryStore.accounts.filter(a => a.id !== accountId);
        } catch (error) {
            showToast(getModeAwareErrorMessage(this.mode, 'delete account'), 'error');
            throw error;
        }
    }

    async deleteAccount_Basic(accountId) {
        try {
            const response = await apiRequest(`/api/accounts/${accountId}`, {
                method: 'DELETE'
            });

            if (!response.ok) {
                throw new Error(`API error: ${response.status}`);
            }

            // Remove from memory store
            this.memoryStore.accounts = this.memoryStore.accounts.filter(a => a.id !== accountId);
        } catch (error) {
            showToast(getModeAwareErrorMessage(this.mode, 'delete account'), 'error');
            throw error;
        }
    }

    // ==================== Queue Management ====================

    /**
     * Check sync queue limit and show warning/blocking modal
     *
     * Queue limits:
     * - 400: Warning toast
     * - 500: Hard block modal
     *
     * @returns {Promise<void>}
     */
    async checkQueueLimit() {
        if (this.mode !== 'full') return; // Queue only exists in Mode 1

        const count = await db.sync_queue.count();

        if (count === 400) {
            showToast('⚠ 400+ pending changes. Sync recommended.', 'warning', 5000);
        } else if (count >= 500) {
            // Hard block - show modal (to be implemented in UI layer)
            throw new Error('QUEUE_LIMIT_REACHED');
        }
    }

    /**
     * Get sync queue count (Mode 1 only)
     *
     * @returns {Promise<number>} Number of pending changes
     */
    async getSyncQueueCount() {
        if (this.mode !== 'full') return 0;
        return await db.sync_queue.count();
    }

    // ==================== MANUAL SYNC ====================

    /**
     * Manual sync - Send queued changes to server and apply server changes
     *
     * Mode 1 (Full): Process sync queue via POST /api/sync
     * Mode 2/3: No sync queue (changes sent immediately)
     *
     * @returns {Promise<Object>} Sync result
     */
    async manualSync() {
        if (this.mode !== 'full') {
            console.log('[CHAPTR] Manual sync not needed - Mode 2/3 syncs immediately');
            return { success: true, message: 'No sync needed' };
        }

        console.log('[CHAPTR] Starting manual sync...');

        try {
            // 1. Get pending changes from sync_queue
            const pending = await db.getPendingSyncQueue();

            if (pending.length === 0) {
                console.log('[CHAPTR] No pending changes to sync');
                return { success: true, message: 'No changes to sync' };
            }

            console.log(`[CHAPTR] Syncing ${pending.length} pending changes...`);

            // 2. Format changes for sync protocol
            const changes = pending.map(c => ({
                entity_type: c.entity_type,
                entity_id: c.entity_id,
                action: c.action,
                data: c.data,
                base_updated_at: c.base_updated_at || null
            }));

            // 3. POST /api/sync
            const response = await apiRequest('/api/sync', {
                method: 'POST',
                body: JSON.stringify({
                    client_id: await generateClientId(),
                    last_sync_at: this.lastSyncAt,
                    changes: changes
                })
            });

            if (!response.ok) {
                throw new Error(`Sync failed: ${response.status}`);
            }

            const syncData = await response.json();

            // 4. Process sync response
            await this.processSyncResponse(syncData);

            console.log(`[CHAPTR] Sync complete: ${syncData.applied.length} applied, ${syncData.conflicts.length} conflicts`);

            return {
                success: true,
                applied: syncData.applied.length,
                conflicts: syncData.conflicts.length
            };

        } catch (error) {
            console.error('[CHAPTR] Manual sync failed:', error);
            showToast('Sync failed. Changes still queued.', 'error');
            throw error;
        }
    }

    /**
     * Process sync response from server
     *
     * @param {Object} syncData - Response from POST /api/sync
     * @returns {Promise<void>}
     */
    async processSyncResponse(syncData) {
        // Store conflicts in conflicts table
        for (const conflict of syncData.conflicts) {
            await db.conflicts.add({
                id: generateUUID(),
                entity_type: conflict.entity_type,
                entity_id: conflict.entity_id,
                conflict_type: conflict.conflict_type,
                client_version: conflict.client_version,
                server_version: conflict.server_version,
                resolved_at: null
            });
        }

        // Clear successfully applied changes from queue
        for (const appliedId of syncData.applied) {
            await db.sync_queue.where({ entity_id: appliedId }).delete();
        }

        // Apply server changes to Dexie
        const tableMap = {
            'account': 'accounts',
            'story': 'stories',
            'event': 'events',
            'recurring_rule': 'recurring_rules',
            'settings': 'settings'
        };

        for (const change of syncData.server_changes) {
            const tableName = tableMap[change.entity_type];
            if (!tableName) continue;

            if (change.action === 'delete') {
                await db[tableName].delete(change.entity_id);
            } else {
                await db[tableName].put(change.data);
            }
        }

        // Update sync metadata
        this.lastSyncAt = syncData.sync_timestamp;
        await db.sync_meta.put({ key: 'lastSyncAt', value: syncData.sync_timestamp });

        // Handle full sync if required
        if (syncData.full_sync_required) {
            await this.handleFullSyncRequired();
        }
    }

    /**
     * Handle full sync required (stale client)
     *
     * Called when client's last_sync_at is older than oldest change_log entry.
     *
     * @returns {Promise<void>}
     */
    async handleFullSyncRequired() {
        console.warn('[CHAPTR] Full sync required - client is stale');

        showToast('Updating to latest data...', 'info', 2000);

        // Clear Dexie and re-download
        await db.transaction('rw', [db.accounts, db.stories, db.events, db.recurring_rules, db.settings, db.sync_queue], async () => {
            await db.accounts.clear();
            await db.stories.clear();
            await db.events.clear();
            await db.recurring_rules.clear();
            await db.settings.clear();
            await db.sync_queue.clear();
        });

        // Re-fetch from server
        await this.fetchAndPopulateDexie();

        showToast('Data updated successfully', 'success');
    }
}

// Export singleton instance
export const storage = new StorageAdapter();
