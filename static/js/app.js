/**
 * CHAPTR - Alpine.js Application Component
 *
 * Main application state and logic using Alpine.js
 */

import {
    formatCurrency,
    formatDate,
    formatDateRange,
    formatRelativeTime,
    isToday,
    isPast,
    apiRequest,
    getClientId,
    clearAuth,
    generateUUID,
    showToast
} from './utils.js';

import { db } from './db.js';
import { storage } from './storage-adapter.js';
import { calculateProjection } from './projection.js';

/**
 * Main Alpine.js app component
 * @returns {object} Alpine.js component
 */
window.app = function() {
    return {
        // ===== STATE =====

        // Storage adapter (exposed for UI access)
        storage: storage,
        storageMode: null,  // Reactive copy of storage.mode for Alpine bindings

        // Navigation
        currentScreen: 'dashboard',

        // Authentication
        isAuthenticated: false,
        loginForm: {
            username: '',
            password: ''
        },
        loginError: '',
        isLoggingIn: false,

        // User
        user: null,

        // Data
        stories: [],
        accounts: [],
        events: [],
        settings: {},
        users: [],

        // UI State
        isSyncing: false,
        syncQueueCount: 0, // Track pending changes for UI indicator
        showAccountModal: false,
        showStoryModal: false,
        showEventModal: false,
        showUserModal: false,
        showHelpModal: false,
        accountForm: {},
        storyForm: {},
        eventForm: {},
        userForm: {},
        settingsForm: {},
        accountsTotal: 0,

        // Projection State
        currentView: 'all',
        displayCurrency: null,
        projectionStartDate: null,
        projectionEndDate: null,
        projectionStartingBalance: 0,
        projectionRows: [],
        projectionToday: 0,
        projectionEndOfMonth: 0,

        // Story goal statuses (cached to avoid expensive recalculation on every render)
        storyStatuses: {},

        // Expanded gaps tracking
        expandedGaps: new Set(),

        // ===== LIFECYCLE =====

        /**
         * Initialize app on mount
         */
        async init() {
            console.log('CHAPTR initializing...');

            // Check authentication first
            await this.checkAuth();

            // If not authenticated, stop here (login screen will show)
            if (!this.isAuthenticated) {
                console.log('Not authenticated - showing login screen');
                return;
            }

            // Set initial projection dates FIRST (before any rendering happens)
            this.setDefaultProjectionDates();

            // Initialize storage adapter (detects mode and bootstraps)
            await storage.init();

            // Sync storage mode to reactive property for Alpine bindings
            this.storageMode = storage.mode;

            // Add mode-3-active class to body if in Basic mode (for CSS styling)
            if (storage.mode === 'basic') {
                document.body.classList.add('mode-3-active');
            }

            // Load data from storage adapter
            await this.loadData();

            // Setup network reconnection handler - auto-retry sync when online
            window.addEventListener('online', async () => {
                console.log('Network reconnected - triggering auto-sync...');
                await this.updateSyncQueueCount();
                if (this.syncQueueCount > 0) {
                    await this.manualSync();
                }
            });

            console.log('CHAPTR ready!');
        },


        /**
         * Load data from storage adapter
         */
        async loadData() {
            try {
                // Load from storage adapter (handles all 3 modes)
                this.stories = await storage.getStories();
                this.accounts = await storage.getAccounts();
                this.events = await storage.getEvents();
                this.users = []; // Users still from Dexie (admin only)
                this.settings = await storage.getSettings() || { base_currency: 'GBP' };

                // Load users from Dexie if Mode 1
                if (storage.mode === 'full') {
                    this.users = await db.users.toArray();
                }

                // Initialize settings form
                this.settingsForm = { ...this.settings };

                console.log(`[CHAPTR] Loaded: ${this.accounts.length} accounts, ${this.stories.length} stories, ${this.events.length} events`);

                // Update dashboard projection summary
                await this.updateDashboardProjection();

                // Calculate story goal statuses
                await this.calculateStoryStatuses();

                // Calculate accounts total
                this.calculateAccountsTotal();

                // Update sync queue count for UI indicator
                await this.updateSyncQueueCount();
            } catch (error) {
                console.error('Error loading from Dexie:', error);
            }
        },

        /**
         * Update Dashboard projection summary (today, end of month)
         */
        async updateDashboardProjection() {
            try {
                const today = new Date();
                const endOfMonth = new Date(today.getFullYear(), today.getMonth() + 1, 0);

                // Calculate projection from today to end of month
                const projection = await calculateProjection(
                    today.toISOString().split('T')[0],
                    endOfMonth.toISOString().split('T')[0],
                    'all',
                    null,
                    this.settings.base_currency
                );

                // Find today's balance (first event on or after today, or last past event)
                const todayStr = today.toISOString().split('T')[0];
                const todayEvent = projection.find(row => !row.isGap && row.date >= todayStr);
                this.projectionToday = todayEvent ? todayEvent.balance : 0;

                // Find end of month balance (last event)
                const lastEvent = projection.filter(row => !row.isGap).pop();
                this.projectionEndOfMonth = lastEvent ? lastEvent.balance : 0;
            } catch (error) {
                console.error('Error updating dashboard projection:', error);
            }
        },

        /**
         * Calculate goal status for all stories
         */
        async calculateStoryStatuses() {
            try {
                for (const story of this.stories) {
                    // If no goal, use lifecycle status
                    if (!story.goal_type || !story.goal_amount) {
                        this.storyStatuses[story.id] = this.getStoryLifecycleStatus(story);
                        continue;
                    }

                    const goalAmount = parseFloat(story.goal_amount || 0);
                    const currency = story.display_currency || this.settings.base_currency || 'GBP';

                    if (story.goal_type === 'spend_up_to') {
                        // Calculate total spending in this story
                        const storyEvents = this.events.filter(e =>
                            e.story_id === story.id &&
                            e.amount < 0 &&
                            e.date >= story.start_date &&
                            e.date <= story.end_date
                        );

                        const totalSpent = Math.abs(storyEvents.reduce((sum, e) => sum + e.amount, 0));
                        const remaining = goalAmount - totalSpent;

                        if (remaining >= 0) {
                            this.storyStatuses[story.id] = `✓ ${formatCurrency(remaining, currency)} LEFT`;
                        } else {
                            this.storyStatuses[story.id] = `⚠ ${formatCurrency(Math.abs(remaining), currency)} OVER`;
                        }
                    } else if (story.goal_type === 'end_with_at_least') {
                        // Run projection to story end date
                        try {
                            const projection = await calculateProjection(
                                story.start_date,
                                story.end_date,
                                story.id,
                                story.id,
                                currency
                            );

                            const lastEvent = projection.filter(row => !row.isGap).pop();
                            const endingBalance = lastEvent ? lastEvent.balance : 0;
                            const difference = endingBalance - goalAmount;

                            if (difference >= 0) {
                                this.storyStatuses[story.id] = `✓ ${formatCurrency(difference, currency)} OVER`;
                            } else {
                                this.storyStatuses[story.id] = `⚠ ${formatCurrency(Math.abs(difference), currency)} SHORT`;
                            }
                        } catch (error) {
                            console.error(`Error calculating status for story ${story.id}:`, error);
                            this.storyStatuses[story.id] = `END WITH ${formatCurrency(goalAmount, currency)}`;
                        }
                    }
                }
            } catch (error) {
                console.error('Error calculating story statuses:', error);
            }
        },

        /**
         * Perform full sync with backend
         */
        async fullSync() {
            try {
                this.isSyncing = true;

                const response = await apiRequest('/api/sync', {
                    method: 'POST',
                    body: JSON.stringify({
                        client_id: await getClientId(),
                        last_sync_at: null,
                        changes: []
                    })
                });

                if (!response.ok) {
                    throw new Error('Sync failed');
                }

                const data = await response.json();
                await this.populateDexie(data.server_changes || []);

                console.log('Full sync complete');
            } catch (error) {
                console.error('Sync error:', error);
            } finally {
                this.isSyncing = false;
            }
        },

        /**
         * Populate Dexie from server changes
         * @param {Array} serverChanges - Array of change log entries
         */
        async populateDexie(serverChanges) {
            // Map entity types to Dexie table names
            const entityTableMap = {
                'account': 'accounts',
                'story': 'stories',
                'event': 'events',
                'recurring_rule': 'recurring_rules',
                'user': 'users',
                'setting': 'settings'
            };

            try {
                await db.transaction('rw', [db.accounts, db.stories, db.events, db.settings, db.recurring_rules, db.users], async () => {
                    for (const change of serverChanges) {
                        const table = entityTableMap[change.entity_type];

                        if (!table) {
                            console.warn(`Unknown entity type: ${change.entity_type}`);
                            continue;
                        }

                        if (change.action === 'create' || change.action === 'update') {
                            await db[table].put(change.data);
                        } else if (change.action === 'delete') {
                            await db[table].delete(change.entity_id);
                        }
                    }
                });

                await this.loadFromDexie();
            } catch (error) {
                console.error('Error populating Dexie:', error);
            }
        },

        // ===== NAVIGATION =====

        /**
         * Switch to a different screen
         * @param {string} screen - Screen name (dashboard, projection, accounts, settings)
         */
        async switchScreen(screen) {
            this.currentScreen = screen;

            // Update projection rows when switching to projection screen
            if (screen === 'projection') {
                await this.updateProjectionRows();
            }
        },

        /**
         * Get screen title for header
         * @returns {string} Screen title
         */
        get screenTitle() {
            const titles = {
                dashboard: '',
                projection: '// projection',
                accounts: '// accounts',
                settings: '// settings'
            };
            return titles[this.currentScreen] || '';
        },

        // ===== PROJECTION =====

        /**
         * Set default projection date range (today to +1 month)
         */
        setDefaultProjectionDates() {
            const today = new Date();
            const nextMonth = new Date(today);
            nextMonth.setMonth(nextMonth.getMonth() + 1);

            this.projectionStartDate = today.toISOString().split('T')[0];
            this.projectionEndDate = nextMonth.toISOString().split('T')[0];
        },

        /**
         * View story projection
         * @param {string} storyId - Story UUID
         */
        async viewStoryProjection(storyId) {
            this.currentView = storyId;
            this.currentScreen = 'projection';
            await this.updateProjectionRows();
        },

        /**
         * Set projection view (all, baseline, or story ID)
         * @param {string} view - View identifier
         */
        async setView(view) {
            this.currentView = view;
            // Reset display currency when switching views
            if (view !== 'all') {
                this.displayCurrency = null;
            }
            // Update projection rows with new view
            await this.updateProjectionRows();
        },

        /**
         * Toggle display currency (for ALL view only)
         */
        async toggleDisplayCurrency() {
            if (this.currentView !== 'all') return;

            // Build currency list from settings.rates, with base currency first
            const baseCurrency = this.settings.base_currency || 'GBP';
            const rateCurrencies = Object.keys(this.settings.rates || {}).filter(c => c !== baseCurrency);
            const currencies = [baseCurrency, ...rateCurrencies];

            // Fallback to common currencies if no rates defined
            if (currencies.length === 1) {
                currencies.push('USD', 'EUR', 'CAD');
            }

            const currentIndex = currencies.indexOf(this.displayCurrency || baseCurrency);
            const nextIndex = (currentIndex + 1) % currencies.length;
            this.displayCurrency = currencies[nextIndex];

            // Update projection rows with new currency
            await this.updateProjectionRows();
        },

        /**
         * Update projection rows based on current view and dates
         */
        async updateProjectionRows() {
            try {
                this.projectionRows = await calculateProjection(
                    this.projectionStartDate,
                    this.projectionEndDate,
                    this.currentView,
                    this.currentView !== 'all' && this.currentView !== 'baseline' ? this.currentView : null,
                    this.displayCurrency
                );

                // Extract starting balance from first row
                if (this.projectionRows.length > 0 && !this.projectionRows[0].isGap) {
                    // Starting balance is the balance of the first event minus its amount
                    const firstEvent = this.projectionRows[0];
                    this.projectionStartingBalance = firstEvent.balance - firstEvent.amount;
                } else {
                    this.projectionStartingBalance = 0;
                }
            } catch (error) {
                console.error('Error updating projection rows:', error);
                this.projectionRows = [];
                this.projectionStartingBalance = 0;
            }
        },

        /**
         * Get projection title based on current view
         * @returns {string} Projection title
         */
        getProjectionTitle() {
            if (this.currentView === 'all') return 'All activity';
            if (this.currentView === 'baseline') return 'Baseline';

            const story = this.stories.find(s => s.id === this.currentView);
            return story ? story.name : 'Unknown';
        },

        /**
         * Toggle gap expansion
         * @param {string} gapId - Gap identifier
         */
        toggleGap(gapId) {
            if (this.expandedGaps.has(gapId)) {
                this.expandedGaps.delete(gapId);
            } else {
                this.expandedGaps.add(gapId);
            }
        },

        // ===== STORIES =====

        /**
         * Get story status (OK, WARN, OVER)
         * @param {object} story - Story object
         * @returns {string} Status text
         */
        getStoryStatus(story) {
            // Return cached status if available
            if (this.storyStatuses[story.id]) {
                return this.storyStatuses[story.id];
            }

            // Fallback to lifecycle status if not yet calculated
            return this.getStoryLifecycleStatus(story);
        },

        /**
         * Get story lifecycle status (active, ended, ongoing)
         * @param {object} story - Story object
         * @returns {string} Lifecycle status
         */
        getStoryLifecycleStatus(story) {
            const today = new Date().toISOString().split('T')[0];
            if (story.end_date < today) {
                return 'ENDED';
            } else if (story.start_date > today) {
                return 'UPCOMING';
            } else {
                return 'ACTIVE';
            }
        },

        /**
         * Get story status CSS class
         * @param {object} story - Story object
         * @returns {string} CSS class name
         */
        getStoryStatusClass(story) {
            const today = new Date().toISOString().split('T')[0];

            // Lifecycle-based classes
            if (story.end_date < today) {
                return 'status-past';
            } else if (story.start_date > today) {
                return 'status-upcoming';
            }

            // Active story - default ok (real calculation in projection view)
            return 'status-ok';
        },

        // ===== ACCOUNTS =====

        /**
         * Calculate total of all account balances
         */
        calculateAccountsTotal() {
            this.accountsTotal = this.accounts
                .filter(a => !a.is_archived)
                .reduce((sum, account) => {
                    const balance = parseFloat(account.current_balance || 0);
                    const rateToBase = parseFloat(account.rate_to_base || 1.0);
                    return sum + (balance * rateToBase);
                }, 0);
        },

        /**
         * Update sync queue count for UI indicator
         */
        async updateSyncQueueCount() {
            try {
                this.syncQueueCount = await storage.getSyncQueueCount();
            } catch (error) {
                console.error('Error counting sync queue:', error);
                this.syncQueueCount = 0;
            }
        },

        /**
         * Manual sync - trigger sync of pending changes
         */
        async manualSync() {
            if (this.isSyncing) {
                console.log('[CHAPTR] Sync already in progress');
                return;
            }

            try {
                this.isSyncing = true;

                const result = await storage.manualSync();

                if (result.conflicts && result.conflicts > 0) {
                    showToast(`Sync complete: ${result.conflicts} conflicts need resolution`, 'warning', 5000);
                } else if (result.applied && result.applied > 0) {
                    showToast(`Synced ${result.applied} changes`, 'success');
                }

                // Update queue count
                await this.updateSyncQueueCount();

                // Reload data to reflect server changes
                await this.loadData();

            } catch (error) {
                console.error('[CHAPTR] Sync failed:', error);
            } finally {
                this.isSyncing = false;
            }
        },

        /**
         * Open account modal for adding new account
         */
        openAccountModal() {
            this.accountForm = {
                name: '',
                currency: this.settings.base_currency || 'GBP',
                current_balance: 0,
                is_default: false
            };
            this.showAccountModal = true;
        },

        /**
         * View account details (open edit modal)
         * @param {string} accountId - Account UUID
         */
        viewAccountDetails(accountId) {
            const account = this.accounts.find(a => a.id === accountId);
            if (account) {
                this.accountForm = { ...account };
                this.showAccountModal = true;
            }
        },

        /**
         * Save account (create or update)
         */
        async saveAccount() {
            try {
                const isEdit = !!this.accountForm.id;

                if (isEdit) {
                    await this.updateAccount();
                } else {
                    await this.createAccount();
                }

                this.showAccountModal = false;

            } catch (error) {
                console.error('Error saving account:', error);
                alert('Failed to save account');
            }
        },

        /**
         * Create new account (via storage adapter)
         */
        async createAccount() {
            const accountData = {
                name: this.accountForm.name,
                currency: this.accountForm.currency.toUpperCase(),
                current_balance: String(parseFloat(this.accountForm.current_balance || 0)),
                is_default: this.accountForm.is_default || false
            };

            // Use storage adapter (handles all 3 modes)
            await storage.createAccount(accountData);

            // Update sync queue count for UI indicator
            await this.updateSyncQueueCount();

            // Reload data
            await this.loadData();
        },

        /**
         * Update existing account (via storage adapter)
         */
        async updateAccount() {
            const accountId = this.accountForm.id;

            const updates = {
                name: this.accountForm.name,
                currency: this.accountForm.currency.toUpperCase(),
                current_balance: String(parseFloat(this.accountForm.current_balance || 0)),
                is_default: this.accountForm.is_default || false
            };

            // Use storage adapter (handles all 3 modes)
            await storage.updateAccount(accountId, updates);

            // Update sync queue count for UI indicator
            await this.updateSyncQueueCount();

            // Reload data
            await this.loadData();
        },

        /**
         * Delete account (via storage adapter)
         */
        async deleteAccount() {
            if (!confirm(`Delete account "${this.accountForm.name}"?`)) {
                return;
            }

            try {
                const accountId = this.accountForm.id;

                // Use storage adapter (handles all 3 modes)
                await storage.deleteAccount(accountId);

                // Update sync queue count for UI indicator
                await this.updateSyncQueueCount();

                this.showAccountModal = false;

                // Reload data
                await this.loadData();

            } catch (error) {
                console.error('Error deleting account:', error);
                alert('Failed to delete account');
            }
        },

        // ===== STORIES =====

        /**
         * Open story modal for adding new story
         */
        openStoryModal() {
            this.storyForm = {
                name: '',
                start_date: new Date().toISOString().split('T')[0],
                end_date: '',
                default_account_id: '',
                display_currency: '',
                funding_mode: 'projected',
                funding_amount: '0',
                goal_type: 'none',
                goal_amount: '0'
            };
            this.showStoryModal = true;
        },

        /**
         * View story details (open edit modal)
         * @param {string} storyId - Story UUID
         */
        viewStoryDetails(storyId) {
            const story = this.stories.find(s => s.id === storyId);
            if (story) {
                this.storyForm = {
                    ...story,
                    end_date: story.end_date || '',
                    default_account_id: story.default_account_id || '',
                    display_currency: story.display_currency || '',
                    goal_type: story.goal_type || 'none',
                    funding_amount: story.funding_amount || '0',
                    goal_amount: story.goal_amount || '0'
                };
                this.showStoryModal = true;
            }
        },

        /**
         * Save story (create or update)
         */
        async saveStory() {
            // Validation
            if (this.storyForm.end_date && this.storyForm.end_date < this.storyForm.start_date) {
                alert('End date must be after start date');
                return;
            }

            if ((this.storyForm.funding_mode === 'fixed' || this.storyForm.funding_mode === 'projected_plus')
                && !this.storyForm.funding_amount) {
                alert('Funding amount is required for this funding mode');
                return;
            }

            if (this.storyForm.goal_type && this.storyForm.goal_type !== 'none' && !this.storyForm.goal_amount) {
                alert('Goal amount is required when goal type is set');
                return;
            }

            if (this.storyForm.display_currency && !/^[A-Z]{3}$/.test(this.storyForm.display_currency.toUpperCase())) {
                alert('Display currency must be a 3-letter code (e.g., GBP, USD)');
                return;
            }

            try {
                const isEdit = !!this.storyForm.id;

                const storyData = {
                    name: this.storyForm.name,
                    start_date: this.storyForm.start_date,
                    end_date: this.storyForm.end_date || null,
                    default_account_id: this.storyForm.default_account_id || null,
                    display_currency: this.storyForm.display_currency ?
                        this.storyForm.display_currency.toUpperCase() : null,
                    funding_mode: this.storyForm.funding_mode,
                    funding_amount: this.storyForm.funding_mode !== 'projected' ?
                        String(parseFloat(this.storyForm.funding_amount || 0)) : '0',
                    goal_type: this.storyForm.goal_type,
                    goal_amount: this.storyForm.goal_type !== 'none' ?
                        String(parseFloat(this.storyForm.goal_amount || 0)) : '0'
                };

                if (isEdit) {
                    await this.updateStory(this.storyForm.id, storyData);
                } else {
                    await this.createStory(storyData);
                }

                this.showStoryModal = false;

            } catch (error) {
                console.error('Error saving story:', error);
                alert('Failed to save story');
            }
        },

        /**
         * Delete story from modal
         */
        async deleteStoryFromModal() {
            try {
                await this.deleteStory(this.storyForm.id);
                this.showStoryModal = false;
            } catch (error) {
                console.error('Error deleting story:', error);
                alert('Failed to delete story');
            }
        },

        /**
         * Navigate to stories management (opens modal for now)
         */
        openStoriesManage() {
            this.openStoryModal();
        },

        /**
         * Get projected balances for an account at 3 future dates
         * Uses filtered projection to show account-specific balances
         * @param {string} accountId - Account UUID
         * @returns {Array} Array of {date, balance} objects
         */
        getAccountProjections(accountId) {
            const account = this.accounts.find(a => a.id === accountId);
            if (!account) return [];

            // Calculate 3 dates: 1 week, 2 weeks, 1 month from today
            const today = new Date();
            const dates = [
                new Date(today.getTime() + 7 * 24 * 60 * 60 * 1000),   // +1 week
                new Date(today.getTime() + 14 * 24 * 60 * 60 * 1000),  // +2 weeks
                new Date(today.getTime() + 30 * 24 * 60 * 60 * 1000)   // +1 month
            ];

            // For now, return mock data
            // TODO PR2: Implement real per-account projection calculation
            return dates.map(date => ({
                date: date.toISOString().split('T')[0],
                balance: account.current_balance // Mock: just use current balance
            }));
        },

        // ===== STORIES =====

        /**
         * Create new story (CRUD implementation)
         * @param {object} storyData - Story form data
         */
        async createStory(storyData) {
            const localId = generateUUID();
            const now = new Date().toISOString();

            const story = {
                id: localId,
                name: storyData.name,
                start_date: storyData.start_date,
                end_date: storyData.end_date,
                display_currency: storyData.display_currency || this.settings.base_currency,
                funding_mode: storyData.funding_mode || 'projected',
                funding_amount: String(parseFloat(storyData.funding_amount || 0)),
                goal_type: storyData.goal_type || null,
                goal_amount: String(parseFloat(storyData.goal_amount || 0)),
                default_account_id: storyData.default_account_id || null,
                is_archived: false,
                created_at: now,
                updated_at: now
            };

            // 1. Optimistic Dexie write
            await db.stories.add(story);

            // 2. Queue for sync
            await db.queueChange('story', localId, 'create', story);

            console.log(`[CHAPTR] Created story with entity_id: ${localId} (queued for sync)`);

            // 3. Reload data
            await this.loadData();
        },

        /**
         * Update existing story (CRUD implementation)
         * @param {string} storyId - Story UUID
         * @param {object} updates - Story updates
         */
        async updateStory(storyId, updates) {
            // 0. Get current entity for conflict detection (capture base_updated_at)
            const currentStory = await db.stories.get(storyId);
            if (!currentStory) {
                throw new Error(`Story ${storyId} not found`);
            }
            const baseUpdatedAt = currentStory.updated_at;

            const now = new Date().toISOString();

            const storyUpdates = {
                ...updates,
                updated_at: now
            };

            // 1. Optimistic Dexie update
            await db.stories.update(storyId, storyUpdates);

            // 2. Queue for sync (include base_updated_at for conflict detection)
            await db.queueChange('story', storyId, 'update', storyUpdates, baseUpdatedAt);

            console.log(`[CHAPTR] Updated story ${storyId} (queued for sync)`);

            // 3. Reload data
            await this.loadData();
        },

        /**
         * Delete story with cascade warning (CRUD implementation)
         * @param {string} storyId - Story UUID
         */
        async deleteStory(storyId) {
            const story = this.stories.find(s => s.id === storyId);
            if (!story) return;

            // Check for associated events
            const associatedEvents = this.events.filter(e => e.story_id === storyId);

            if (associatedEvents.length > 0) {
                const confirmMsg = `Delete story "${story.name}"?\n\nThis will also delete ${associatedEvents.length} associated event(s).`;
                if (!confirm(confirmMsg)) {
                    return;
                }

                // Delete associated events
                for (const event of associatedEvents) {
                    await this.deleteEvent(event.id);
                }
            } else {
                if (!confirm(`Delete story "${story.name}"?`)) {
                    return;
                }
            }

            // 0. Get current entity for conflict detection (capture base_updated_at)
            const currentStory = await db.stories.get(storyId);
            if (!currentStory) {
                throw new Error(`Story ${storyId} not found`);
            }
            const baseUpdatedAt = currentStory.updated_at;

            const now = new Date().toISOString();

            // 1. Mark as archived in Dexie
            await db.stories.update(storyId, {
                is_archived: true,
                updated_at: now
            });

            // 2. Queue for sync (send null data per spec - delete should not send entity data)
            await db.queueChange('story', storyId, 'delete', null, baseUpdatedAt);

            console.log(`[CHAPTR] Deleted story ${storyId} (queued for sync)`);

            // 3. Reload data
            await this.loadData();
        },

        // ===== EVENTS =====

        /**
         * Resolve account ID using hierarchy (spec: Account Resolution at Creation)
         * 1. User-selected account
         * 2. Story default account
         * 3. Global default account
         * @param {string|null} selectedAccountId - User-selected account ID
         * @param {string|null} storyId - Story ID for this event
         * @returns {string|null} Resolved account ID
         */
        resolveAccountId(selectedAccountId, storyId) {
            // 1. User-selected account
            if (selectedAccountId) {
                return selectedAccountId;
            }

            // 2. Story default account
            if (storyId) {
                const story = this.stories.find(s => s.id === storyId);
                if (story && story.default_account_id) {
                    return story.default_account_id;
                }
            }

            // 3. Global default account
            const defaultAccount = this.accounts.find(a => a.is_default && !a.is_archived);
            return defaultAccount ? defaultAccount.id : null;
        },

        /**
         * Create new event (CRUD implementation)
         * @param {object} eventData - Event form data
         */
        async createEvent(eventData) {
            const localId = generateUUID();
            const now = new Date().toISOString();

            // Resolve account using hierarchy
            const accountId = this.resolveAccountId(
                eventData.account_id,
                eventData.story_id
            );

            if (!accountId) {
                alert('No account available. Please create an account first.');
                return;
            }

            // Get account for currency
            const account = this.accounts.find(a => a.id === accountId);
            const currency = account ? account.currency : this.settings.base_currency;

            // Lookup rate_to_base from settings.rates
            const rate_to_base = this.settings.rates && this.settings.rates[currency]
                ? this.settings.rates[currency]
                : 1.0;

            const event = {
                id: localId,
                description: eventData.description,
                amount: String(parseFloat(eventData.amount)),
                date: eventData.date,
                account_id: accountId,
                currency: currency,
                rate_to_base: rate_to_base,
                story_id: eventData.story_id || null,
                is_baseline: eventData.is_baseline || false,
                is_hypothetical: eventData.is_hypothetical || false,
                event_type: eventData.event_type || 'OUTGOING',
                notes: eventData.notes || '',
                created_at: now,
                updated_at: now
            };

            // 1. Optimistic Dexie write
            await db.events.add(event);

            // 2. Queue for sync
            await db.queueChange('event', localId, 'create', event);

            console.log(`[CHAPTR] Created event with entity_id: ${localId} (queued for sync)`);

            // 3. Reload data
            await this.loadFromDexie();
        },

        /**
         * Update existing event (CRUD implementation)
         * @param {string} eventId - Event UUID
         * @param {object} updates - Event updates
         */
        async updateEvent(eventId, updates) {
            // 0. Get current entity for conflict detection (capture base_updated_at)
            const currentEvent = await db.events.get(eventId);
            if (!currentEvent) {
                throw new Error(`Event ${eventId} not found`);
            }
            const baseUpdatedAt = currentEvent.updated_at;

            const now = new Date().toISOString();

            const eventUpdates = {
                ...updates,
                updated_at: now
            };

            // If account changed, update currency and rate
            if (updates.account_id) {
                const account = this.accounts.find(a => a.id === updates.account_id);
                if (account) {
                    eventUpdates.currency = account.currency;
                    eventUpdates.rate_to_base = account.rate_to_base;
                }
            }

            // 1. Optimistic Dexie update
            await db.events.update(eventId, eventUpdates);

            // 2. Queue for sync (include base_updated_at for conflict detection)
            await db.queueChange('event', eventId, 'update', eventUpdates, baseUpdatedAt);

            console.log(`[CHAPTR] Updated event ${eventId} (queued for sync)`);

            // 3. Reload data
            await this.loadFromDexie();
        },

        /**
         * Delete event (CRUD implementation)
         * @param {string} eventId - Event UUID
         */
        async deleteEvent(eventId) {
            const event = this.events.find(e => e.id === eventId);
            if (!event) return;

            if (!confirm(`Delete event "${event.description}"?`)) {
                return;
            }

            // 0. Get current entity for conflict detection (capture base_updated_at BEFORE delete)
            const currentEvent = await db.events.get(eventId);
            if (!currentEvent) {
                throw new Error(`Event ${eventId} not found`);
            }
            const baseUpdatedAt = currentEvent.updated_at;

            // 1. Mark as deleted in Dexie (or actually delete)
            await db.events.delete(eventId);

            // 2. Queue for sync (send null data per spec - delete should not send entity data)
            await db.queueChange('event', eventId, 'delete', null, baseUpdatedAt);

            console.log(`[CHAPTR] Deleted event ${eventId} (queued for sync)`);

            // 4. Reload data
            await this.loadFromDexie();
        },

        // ===== SETTINGS =====

        /**
         * Open user modal for adding new user
         */
        openUserModal() {
            this.userForm = {
                username: '',
                password: '',
                is_admin: false,
                role: 'user'
            };
            this.showUserModal = true;
        },

        /**
         * Edit existing user
         * @param {string} userId - User UUID
         */
        editUser(userId) {
            const user = this.users.find(u => u.id === userId);
            if (user) {
                this.userForm = { ...user };
                this.showUserModal = true;
            }
        },

        /**
         * Update settings (preferences, sync interval, etc.)
         */
        async updateSettings() {
            try {
                // For PR2, this will integrate with Dexie + API
                console.log('Update settings:', this.settingsForm);

                // TODO PR2: Implement settings update
                // - Write to Dexie settings table
                // - Call API endpoint
                // - Reload data

            } catch (error) {
                console.error('Error updating settings:', error);
                alert('Failed to update settings');
            }
        },

        /**
         * Add a new conversion rate
         */
        addConversionRate() {
            const currency = prompt('Enter currency code (e.g., EUR, CAD):');
            if (!currency) return;

            const upperCurrency = currency.toUpperCase();
            if (upperCurrency.length !== 3) {
                alert('Currency code must be 3 letters');
                return;
            }

            const rate = prompt(`Enter conversion rate for 1 ${upperCurrency} to ${this.settingsForm.base_currency}:`);
            if (!rate) return;

            this.settingsForm.rates[upperCurrency] = parseFloat(rate);
            this.updateSettings();
        },

        /**
         * Update conversion rate
         * @param {string} currency - Currency code
         * @param {string} value - New rate value
         */
        updateRate(currency, value) {
            this.settingsForm.rates[currency] = parseFloat(value);
            this.updateSettings();
        },

        /**
         * Delete conversion rate
         * @param {string} currency - Currency code
         */
        deleteRate(currency) {
            if (!confirm(`Remove ${currency} conversion rate?`)) return;

            delete this.settingsForm.rates[currency];
            this.updateSettings();
        },

        /**
         * Download backup as JSON
         */
        async downloadBackup() {
            try {
                // Gather all data
                const backup = {
                    version: '1.0',
                    exported_at: new Date().toISOString(),
                    accounts: await db.accounts.toArray(),
                    stories: await db.stories.toArray(),
                    events: await db.events.toArray(),
                    users: await db.users.toArray(),
                    settings: await db.settings.get(1),
                    recurring_rules: await db.recurring_rules.toArray()
                };

                // Create download link
                const dataStr = JSON.stringify(backup, null, 2);
                const dataBlob = new Blob([dataStr], { type: 'application/json' });
                const url = URL.createObjectURL(dataBlob);
                const link = document.createElement('a');
                link.href = url;
                link.download = `chaptr-backup-${new Date().toISOString().split('T')[0]}.json`;
                link.click();
                URL.revokeObjectURL(url);

                console.log('Backup downloaded');
            } catch (error) {
                console.error('Error downloading backup:', error);
                alert('Failed to download backup');
            }
        },

        /**
         * Upload and restore backup from JSON
         * @param {Event} event - File input change event
         */
        async uploadBackup(event) {
            const file = event.target.files[0];
            if (!file) return;

            // Validate file size (max 10MB)
            const maxSizeMB = 10;
            if (file.size > maxSizeMB * 1024 * 1024) {
                alert(`File too large. Maximum size is ${maxSizeMB}MB.`);
                event.target.value = '';
                return;
            }

            if (!confirm('⚠ This will OVERWRITE all existing data. Continue?')) {
                event.target.value = '';
                return;
            }

            try {
                const text = await file.text();
                const backup = JSON.parse(text);

                // Comprehensive backup validation
                if (!backup.version || typeof backup.version !== 'string') {
                    throw new Error('Invalid backup: missing or invalid version');
                }

                // Validate required array fields
                const requiredArrays = ['accounts', 'stories', 'events'];
                for (const field of requiredArrays) {
                    if (!backup[field] || !Array.isArray(backup[field])) {
                        throw new Error(`Invalid backup: missing or invalid ${field} array`);
                    }
                }

                // Validate optional fields
                if (backup.users && !Array.isArray(backup.users)) {
                    throw new Error('Invalid backup: users must be an array');
                }
                if (backup.recurring_rules && !Array.isArray(backup.recurring_rules)) {
                    throw new Error('Invalid backup: recurring_rules must be an array');
                }
                if (backup.settings && typeof backup.settings !== 'object') {
                    throw new Error('Invalid backup: settings must be an object');
                }

                // Clear existing data and restore
                await db.transaction('rw', [db.accounts, db.stories, db.events, db.users, db.settings, db.recurring_rules], async () => {
                    await db.accounts.clear();
                    await db.stories.clear();
                    await db.events.clear();
                    await db.users.clear();
                    await db.settings.clear();
                    await db.recurring_rules.clear();

                    await db.accounts.bulkAdd(backup.accounts);
                    await db.stories.bulkAdd(backup.stories);
                    await db.events.bulkAdd(backup.events);
                    await db.users.bulkAdd(backup.users || []);
                    if (backup.settings) {
                        await db.settings.put(backup.settings);
                    }
                    await db.recurring_rules.bulkAdd(backup.recurring_rules || []);
                });

                alert('✓ Backup restored successfully');
                await this.loadFromDexie();
            } catch (error) {
                console.error('Error restoring backup:', error);
                alert('Failed to restore backup: ' + error.message);
            }

            event.target.value = '';
        },

        /**
         * Trigger manual sync
         */
        async triggerManualSync() {
            if (this.isSyncing) return;

            try {
                this.isSyncing = true;
                await this.fullSync();
                alert('✓ Sync complete');
            } catch (error) {
                console.error('Sync error:', error);
                alert('Sync failed');
            } finally {
                this.isSyncing = false;
            }
        },

        /**
         * Clear sync queue (Mode 1 only)
         *
         * Clears all pending sync queue items without syncing to server.
         * Useful for development/testing to clear stale queue items.
         */
        async clearSyncQueue() {
            if (!confirm('Clear all pending sync items? This cannot be undone.')) {
                return;
            }

            try {
                const count = await storage.clearSyncQueue();
                await this.updateSyncQueueCount();
                showToast(`Cleared ${count} pending sync items`, 'success');
            } catch (error) {
                console.error('Clear queue error:', error);
                showToast('Failed to clear sync queue', 'error');
            }
        },

        // ===== COMMAND BAR (Context-Sensitive) =====

        /**
         * Get label for + button based on current screen
         * @returns {string} Button label
         */
        getPlusLabel() {
            const labels = {
                dashboard: 'Event',
                projection: 'To Story',
                accounts: 'Account',
                settings: 'User'
            };
            return labels[this.currentScreen] || 'Add';
        },

        /**
         * Get label for $ button based on current screen
         * @returns {string} Button label
         */
        getDollarLabel() {
            const labels = {
                dashboard: 'Balance',
                projection: 'Funding',
                accounts: 'Balance',
                settings: 'Settings'
            };
            return labels[this.currentScreen] || 'Update';
        },

        /**
         * Handle + button action based on current screen
         */
        handlePlusAction() {
            const actions = {
                dashboard: () => this.addEvent(),
                projection: () => this.addEventToStory(),
                accounts: () => this.openAccountModal(),
                settings: () => this.openUserModal()
            };

            const action = actions[this.currentScreen];
            if (action) {
                action();
            } else {
                console.warn('No + action defined for screen:', this.currentScreen);
            }
        },

        /**
         * Handle $ button action based on current screen
         */
        handleDollarAction() {
            const actions = {
                dashboard: () => this.updateBalance(),
                projection: () => this.editFunding(),
                accounts: () => this.updateBalance(),
                settings: () => this.updateSettings()
            };

            const action = actions[this.currentScreen];
            if (action) {
                action();
            } else {
                console.warn('No $ action defined for screen:', this.currentScreen);
            }
        },

        /**
         * Add event (dashboard context)
         */
        addEvent() {
            // TODO PR2 Stage 4: Implement event creation
            console.log('Add event - Dashboard context');
            alert('Add Event - Coming in Stage 4 (CRUD)');
        },

        /**
         * Add event to current story (projection context)
         */
        addEventToStory() {
            // TODO PR2 Stage 4: Implement add to story
            console.log('Add to story - Projection context, view:', this.currentView);

            if (this.currentView === 'all' || this.currentView === 'baseline') {
                alert('Please select a specific story first');
                return;
            }

            const story = this.stories.find(s => s.id === this.currentView);
            alert(`Add Event to Story: ${story ? story.name : 'Unknown'} - Coming in Stage 4 (CRUD)`);
        },

        /**
         * Update account balance (dashboard/accounts context)
         */
        updateBalance() {
            // TODO PR2 Stage 4: Implement balance update
            console.log('Update balance - Current screen:', this.currentScreen);
            alert('Update Balance - Coming in Stage 4 (CRUD)');
        },

        /**
         * Edit story funding (projection context)
         */
        editFunding() {
            // TODO PR2 Stage 4: Implement funding edit
            console.log('Edit funding - Projection context, view:', this.currentView);

            if (this.currentView === 'all' || this.currentView === 'baseline') {
                alert('Please select a specific story first');
                return;
            }

            const story = this.stories.find(s => s.id === this.currentView);
            alert(`Edit Funding: ${story ? story.name : 'Unknown'} - Coming in Stage 4 (CRUD)`);
        },

        // ===== FORMATTING HELPERS =====

        /**
         * Format currency (wrapper for utils)
         */
        formatCurrency(amount, currency) {
            return formatCurrency(amount, currency);
        },

        /**
         * Format date (wrapper for utils)
         */
        formatDate(date) {
            return formatDate(date);
        },

        /**
         * Format date range (wrapper for utils)
         */
        formatDateRange(startDate, endDate) {
            return formatDateRange(startDate, endDate);
        },

        /**
         * Format relative time (wrapper for utils)
         */
        formatRelativeTime(date) {
            return formatRelativeTime(date);
        },

        /**
         * Check if date is today (wrapper for utils)
         */
        isToday(date) {
            return isToday(date);
        },

        /**
         * Check if date is in past (wrapper for utils)
         */
        isPast(date) {
            return isPast(date);
        },

        /**
         * Get drift class (positive/negative)
         * Compares accounts total with projected balance
         */
        getDriftClass() {
            const drift = this.accountsTotal - this.projectionToday;
            const driftPercent = Math.abs(drift) / Math.max(Math.abs(this.projectionToday), 1) * 100;

            if (driftPercent < 5) return 'positive';  // 0-5%: on track
            if (driftPercent < 10) return 'warning';  // 5-10%: amber
            return 'negative';  // >10%: red
        },

        /**
         * Format drift amount
         * Shows difference between accounts total and projected
         */
        formatDrift() {
            const drift = this.accountsTotal - this.projectionToday;
            const sign = drift >= 0 ? '+' : '';
            return sign + formatCurrency(drift, this.settings.base_currency);
        },

        // ===== MODE DISPLAY HELPERS =====

        /**
         * Get mode display text for Settings screen
         * @returns {string} Mode display text
         */
        getModeDisplay() {
            const modes = {
                'full': 'Full (Offline-capable)',
                'sync-only': 'Sync-Only (Online required)',
                'basic': 'Basic (Limited)'
            };
            return modes[this.storageMode] || 'Unknown';
        },

        /**
         * Get capabilities display HTML for Settings screen
         * @returns {string} HTML string with checkmarks/crosses
         */
        getCapabilitiesDisplay() {
            const offline = this.storageMode === 'full';
            const sync = this.storageMode !== 'basic';

            const offlineIcon = offline ? '<span class="checkmark">✓</span>' : '<span class="crossmark">✗</span>';
            const syncIcon = sync ? '<span class="checkmark">✓</span>' : '<span class="crossmark">✗</span>';

            return `${offlineIcon} Offline sync &nbsp;&nbsp; ${syncIcon} Conflict detection`;
        },

        /**
         * Get storage type display for Settings screen
         * @returns {string} Storage type text
         */
        getStorageDisplay() {
            const storageTypes = {
                'full': `IndexedDB (Dexie ${Dexie.version})`,
                'sync-only': 'Memory (cleared on refresh)',
                'basic': 'Memory (cleared on refresh)'
            };
            return storageTypes[this.storageMode] || 'Unknown';
        },

        // ===== AUTH =====

        /**
         * Check if user is authenticated
         * Verifies token with backend
         */
        async checkAuth() {
            const token = localStorage.getItem('auth_token');
            console.log('[AUTH] Checking authentication, token present:', !!token);

            if (!token) {
                console.log('[AUTH] No token found');
                this.isAuthenticated = false;
                return;
            }

            try {
                // Verify token with backend
                console.log('[AUTH] Verifying token with /api/auth/me');
                const response = await fetch('/api/auth/me', {
                    headers: {
                        'Authorization': `Bearer ${token}`
                    }
                });

                console.log('[AUTH] Token verification response status:', response.status);

                if (response.ok) {
                    const user = await response.json();
                    this.user = user;
                    this.isAuthenticated = true;
                    console.log('[AUTH] Authenticated as:', user.username);
                } else {
                    // Token invalid or expired
                    console.log('[AUTH] Token verification failed - clearing auth');
                    this.isAuthenticated = false;
                    localStorage.removeItem('auth_token');
                    localStorage.removeItem('user');
                }
            } catch (error) {
                console.error('[AUTH] Auth check error:', error);
                this.isAuthenticated = false;
                localStorage.removeItem('auth_token');
                localStorage.removeItem('user');
            }
        },

        /**
         * Handle login form submission
         */
        async handleLogin() {
            this.loginError = '';
            this.isLoggingIn = true;

            try {
                const response = await fetch('/api/auth/login', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        username: this.loginForm.username,
                        password: this.loginForm.password
                    })
                });

                if (response.ok) {
                    const data = await response.json();

                    // Store token and user info
                    localStorage.setItem('auth_token', data.access_token);
                    localStorage.setItem('user', JSON.stringify(data.user));

                    this.user = data.user;
                    this.isAuthenticated = true;

                    // Initialize app components (without re-checking auth)
                    this.setDefaultProjectionDates();
                    await storage.init();

                    // Sync storage mode to reactive property
                    this.storageMode = storage.mode;

                    if (storage.mode === 'basic') {
                        document.body.classList.add('mode-3-active');
                    }

                    await this.loadData();
                    await this.updateSyncQueueCount();

                    // Auto-sync if there are pending changes
                    if (this.syncQueueCount > 0) {
                        await this.manualSync();
                    }
                } else {
                    const error = await response.json();
                    this.loginError = error.detail || 'Invalid credentials';
                }
            } catch (error) {
                console.error('Login failed:', error);
                this.loginError = 'Connection error. Please try again.';
            } finally {
                this.isLoggingIn = false;
            }
        },

        /**
         * Logout user
         */
        logout() {
            clearAuth();
            // Reload page to reset all state and show login screen
            window.location.reload();
        }
    };
};
