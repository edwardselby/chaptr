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
        syncButtonSpinner: false,
        syncQueueCount: 0, // Track pending changes for UI indicator
        showAccountModal: false,
        showStoryModal: false,
        showEventModal: false,
        showUserModal: false,
        showHelpModal: false,
        showBalanceModal: false,
        showDatabaseToolsModal: false,
        accountForm: {},
        storyForm: {},
        eventForm: {},
        userForm: {},
        settingsForm: {},
        balanceForm: {
            account_id: '',
            projected_balance: 0,
            actual_balance: 0,
            drift: null,
            currency: 'GBP'
        },
        accountsTotal: 0,

        // Story Management
        storySearchFilter: '',
        filteredStories: [],

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

                // Initialize filtered stories (show all non-archived by default)
                this.filteredStories = this.stories.filter(s => !s.is_archived);

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
                const todayEvent = projection.find(row => !row.isGap && row.event_date >= todayStr);
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
                            e.event_date >= story.start_date &&
                            e.event_date <= story.end_date
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
         * Uses /api/sync/full endpoint to get current database state
         */
        async fullSync() {
            try {
                this.isSyncing = true;

                const response = await apiRequest('/api/sync/full', {
                    method: 'GET'
                });

                if (!response.ok) {
                    throw new Error('Full sync failed');
                }

                const data = await response.json();

                // Populate database with full dataset
                await db.transaction('rw', [db.accounts, db.stories, db.events, db.recurring_rules, db.settings, db.sync_meta], async () => {
                    // Put all accounts
                    for (const account of data.accounts || []) {
                        await db.accounts.put(account);
                    }

                    // Put all stories
                    for (const story of data.stories || []) {
                        await db.stories.put(story);
                    }

                    // Put all events
                    for (const event of data.events || []) {
                        await db.events.put(event);
                    }

                    // Put all recurring rules
                    for (const rule of data.recurring_rules || []) {
                        await db.recurring_rules.put(rule);
                    }

                    // Update settings
                    if (data.settings) {
                        await db.settings.put(data.settings);
                    }

                    // CRITICAL: Store sync timestamp to prevent re-downloading old change_log entries
                    if (data.sync_timestamp) {
                        await db.sync_meta.put({ id: 'lastSyncAt', value: data.sync_timestamp });
                    }
                });

                // Reload data into Alpine state
                await this.loadData();

                console.log('[CHAPTR] Full sync complete - timestamp updated to', data.sync_timestamp);
            } catch (error) {
                console.error('[CHAPTR] Full sync error:', error);
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

                await this.loadData();
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
            const previousScreen = this.currentScreen;
            this.currentScreen = screen;

            // Update projection when viewing projection screen
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
         * Navigate to Projection view filtered by story
         * Used when clicking a story in the Dashboard stories panel
         * @param {string} storyId - Story UUID
         */
        navigateToStoryProjection(storyId) {
            this.setView(storyId);
            this.switchScreen('projection');
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
                // Calculate virtual drift rows for pending reconciliations
                const virtualDrifts = this.calculatePendingDrifts();

                this.projectionRows = await calculateProjection(
                    this.projectionStartDate,
                    this.projectionEndDate,
                    this.currentView,
                    this.currentView !== 'all' && this.currentView !== 'baseline' ? this.currentView : null,
                    this.displayCurrency,
                    virtualDrifts
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
                    goal_amount: story.goal_amount || '0',
                    is_archived: story.is_archived
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
                        String(parseFloat(this.storyForm.funding_amount || 0)) : null,
                    goal_type: this.storyForm.goal_type,
                    goal_amount: this.storyForm.goal_type !== 'none' ?
                        String(parseFloat(this.storyForm.goal_amount || 0)) : null
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
         * Navigate to stories management screen
         */
        openStoriesManage() {
            this.switchScreen('stories');
            this.filterStories(); // Populate filtered list
        },

        /**
         * Filter stories by search query
         * Updates filteredStories based on storySearchFilter
         */
        filterStories() {
            const query = this.storySearchFilter.toLowerCase();

            if (!query) {
                // No search query - show all non-archived stories
                this.filteredStories = this.stories.filter(s => !s.is_archived);
            } else {
                // Filter by name (excluding archived)
                this.filteredStories = this.stories.filter(s =>
                    !s.is_archived &&
                    s.name.toLowerCase().includes(query)
                );
            }
        },

        /**
         * Archive or unarchive a story
         * @param {string} storyId - Story UUID
         */
        async archiveStory(storyId) {
            const story = this.stories.find(s => s.id === storyId);
            if (!story) return;

            const action = story.is_archived ? 'Unarchive' : 'Archive';
            const confirmMessage = story.is_archived
                ? `Unarchive "${story.name}"?\n\nIt will be visible again.`
                : `Archive "${story.name}"?\n\nIt will be hidden but not deleted.`;

            if (!confirm(confirmMessage)) {
                return;
            }

            try {
                await this.updateStory(storyId, { is_archived: !story.is_archived });
                await this.loadData();
                this.filterStories(); // Refresh filtered list
            } catch (error) {
                console.error(`Error ${action.toLowerCase()}ing story:`, error);
                alert(`Failed to ${action.toLowerCase()} story: ` + error.message);
            }
        },

        /**
         * Get account name by ID
         * Helper for displaying account names in UI
         * @param {string} accountId - Account UUID
         * @returns {string} Account name or 'Unknown'
         */
        getAccountName(accountId) {
            const account = this.accounts.find(a => a.id === accountId);
            return account ? account.name : 'Unknown';
        },

        /**
         * Get View All summary data for Dashboard
         * Returns total projected balance across all stories + baseline
         * @returns {object} { balance: number }
         */
        getViewAllSummary() {
            // Use projectionToday which already includes all stories + baseline
            return {
                balance: this.projectionToday || 0
            };
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
                event_date: eventData.event_date,
                account_id: accountId,
                currency: currency,
                rate_to_base: rate_to_base,
                story_id: eventData.story_id || null,
                is_baseline: eventData.is_baseline || false,
                is_hypothetical: eventData.is_hypothetical || false,
                created_at: now,
                updated_at: now
            };

            // 1. Optimistic Dexie write
            await db.events.add(event);

            // 2. Queue for sync
            await db.queueChange('event', localId, 'create', event);

            console.log(`[CHAPTR] Created event with entity_id: ${localId} (queued for sync)`);

            // 3. Reload data
            await this.loadData();
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
            await this.loadData();
        },

        /**
         * Delete event (CRUD implementation)
         * @param {string} eventId - Event UUID
         */
        async deleteEvent(eventId) {
            const event = this.events.find(e => e.id === eventId);
            if (!event) return;

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
            await this.loadData();
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
                await this.loadData();
            } catch (error) {
                console.error('Error restoring backup:', error);
                alert('Failed to restore backup: ' + error.message);
            }

            event.target.value = '';
        },

        /**
         * Trigger manual sync with spinner and conflict detection
         */
        async triggerManualSync() {
            if (this.isSyncing) return;

            this.isSyncing = true;
            this.syncButtonSpinner = true; // Show spinner

            try {
                const queueCount = await this.updateSyncQueueCount();

                if (queueCount === 0) {
                    showToast('No changes to sync', 'info');
                    return;
                }

                // Perform sync
                await this.fullSync();

                // Check for conflicts after sync
                if (storage.mode === 'full') {
                    const conflicts = await db.conflicts.count();
                    if (conflicts > 0) {
                        showToast(
                            `⚠ ${conflicts} conflict${conflicts > 1 ? 's' : ''} detected. Review in Settings.`,
                            'warning'
                        );
                    } else {
                        showToast(`✓ Synced ${queueCount} change${queueCount > 1 ? 's' : ''}`, 'success');
                    }
                } else {
                    showToast(`✓ Sync complete`, 'success');
                }

            } catch (error) {
                console.error('Sync error:', error);
                alert('Failed to sync: ' + error.message);
            } finally {
                this.isSyncing = false;
                this.syncButtonSpinner = false; // Hide spinner
                await this.updateSyncQueueCount(); // Refresh count
            }
        },

        /**
         * Clear sync queue (Mode 1 only)
         *
         * Clears all pending sync queue items without syncing to server.
         * Also deletes any entities that were created locally but never synced.
         * Useful for development/testing to clear stale queue items.
         */
        async clearSyncQueue() {
            if (!confirm('Clear all pending sync items?\n\nThis will delete unsynced entities (events, accounts, etc.) and cannot be undone.')) {
                return;
            }

            try {
                const count = await storage.clearSyncQueue();
                await this.updateSyncQueueCount();

                // Recalculate projection to reflect deletion of unsynced entities
                // This ensures drift updates correctly
                if (this.currentScreen === 'dashboard') {
                    await this.updateProjectionRows();
                }

                showToast(`Cleared ${count} pending sync items`, 'success');
            } catch (error) {
                console.error('Clear queue error:', error);
                showToast('Failed to clear sync queue', 'error');
            }
        },

        /**
         * Clear local database and force full resync
         *
         * Non-destructive escape hatch for when sync gets out of sync.
         * Clears all local data and re-downloads everything from server.
         * User login and settings are preserved.
         */
        async clearDatabaseAndResync() {
            try {
                this.isSyncing = true;
                showToast('Clearing local database...', 'info');

                // Clear all local data (preserves users and settings)
                await db.clearAllData();
                console.log('[CHAPTR] Local database cleared');

                // Clear reactive state immediately
                this.accounts = [];
                this.stories = [];
                this.events = [];
                this.projectionRows = [];
                console.log('[CHAPTR] Reactive state cleared');

                // Trigger full sync to re-download all data
                showToast('Resyncing from server...', 'info');
                await this.fullSync();

                console.log('[CHAPTR] Database reset complete');
                showToast('Database reset complete', 'success');
            } catch (error) {
                console.error('[CHAPTR] Clear database error:', error);
                showToast('Failed to reset database', 'error');
            } finally {
                this.isSyncing = false;
                this.showDatabaseToolsModal = false;
            }
        },

        /**
         * Clear local database AND server change log, then resync
         *
         * User-specific reset that clears both local data and this user's
         * change log entries on the server. Other users are unaffected.
         */
        async clearDatabaseAndChangeLog() {
            try {
                this.isSyncing = true;
                showToast('Clearing local database and change log...', 'info');

                // Clear all local data
                await db.clearAllData();
                this.accounts = [];
                this.stories = [];
                this.events = [];
                this.projectionRows = [];

                // Clear user's change log on server
                const response = await apiRequest('/api/admin/clear-changelog', {
                    method: 'POST'
                });

                if (!response.ok) {
                    throw new Error('Failed to clear change log');
                }

                const data = await response.json();
                console.log('[CHAPTR] Cleared change log:', data.deleted_count, 'entries');

                // Trigger full sync
                showToast('Resyncing from server...', 'info');
                await this.fullSync();

                showToast(`Reset complete - cleared ${data.deleted_count} change log entries`, 'success');
            } catch (error) {
                console.error('[CHAPTR] Clear database + changelog error:', error);
                showToast('Failed to reset database and change log', 'error');
            } finally {
                this.isSyncing = false;
                this.showDatabaseToolsModal = false;
            }
        },

        /**
         * Nuclear reset - wipes entire database (all users)
         *
         * 🔴 DESTRUCTIVE OPERATION 🔴
         * Development only. Requires password confirmation.
         */
        async nuclearReset() {
            const password = prompt(
                '🔴 NUCLEAR RESET - ALL DATA WILL BE DELETED\n\n' +
                'This will permanently delete:\n' +
                '• ALL accounts, stories, events (all users)\n' +
                '• ALL change log history\n' +
                '• ALL conflicts\n\n' +
                'Only users and settings are preserved.\n\n' +
                'Enter password to confirm:'
            );

            if (!password) {
                return; // User cancelled
            }

            try {
                this.isSyncing = true;
                showToast('Executing nuclear reset...', 'info');

                // Call nuclear reset endpoint with password
                const response = await apiRequest('/api/admin/nuclear-reset', {
                    method: 'POST',
                    body: JSON.stringify({ password })
                });

                if (!response.ok) {
                    const error = await response.json();
                    throw new Error(error.detail || 'Nuclear reset failed');
                }

                const data = await response.json();
                console.log('[CHAPTR] Nuclear reset complete:', data);

                // Clear local database
                await db.clearAllData();
                this.accounts = [];
                this.stories = [];
                this.events = [];
                this.projectionRows = [];

                // Resync (will get empty state)
                await this.fullSync();

                showToast('Nuclear reset complete - all data wiped', 'success');
            } catch (error) {
                console.error('[CHAPTR] Nuclear reset error:', error);
                showToast(error.message || 'Nuclear reset failed', 'error');
            } finally {
                this.isSyncing = false;
                this.showDatabaseToolsModal = false;
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
         * Add event (dashboard context - auto-select story by date)
         * Finds story covering today's date, prefers smallest range if multiple overlap
         */
        addEvent() {
            // Find story covering today's date
            const today = new Date().toISOString().split('T')[0];
            const coveringStories = this.stories.filter(s =>
                !s.is_archived &&
                s.start_date <= today &&
                (!s.end_date || s.end_date >= today)
            );

            let selectedStory = null;

            if (coveringStories.length === 1) {
                // Only one story covers today - auto-select it
                selectedStory = coveringStories[0];
            } else if (coveringStories.length > 1) {
                // Multiple stories cover today - prefer smallest date range
                selectedStory = coveringStories.reduce((smallest, story) => {
                    const storyRange = story.end_date
                        ? new Date(story.end_date) - new Date(story.start_date)
                        : Infinity;
                    const smallestRange = smallest.end_date
                        ? new Date(smallest.end_date) - new Date(smallest.start_date)
                        : Infinity;

                    return storyRange < smallestRange ? story : smallest;
                });
            }

            // Open modal with auto-selected story (or baseline if none)
            if (selectedStory) {
                console.log(`[CHAPTR] Auto-selected story: ${selectedStory.name}`);
                this.openEventModalForStory(selectedStory.id);
            } else {
                // No story covers today - create baseline event
                console.log('[CHAPTR] No story covers today - creating baseline event');
                this.openEventModal();
            }
        },

        /**
         * Add event to current story (projection context)
         */
        addEventToStory() {
            if (this.currentView === 'all' || this.currentView === 'baseline') {
                alert('Please select a specific story first');
                return;
            }
            this.openEventModalForStory(this.currentView);
        },

        /**
         * Update account balance (dashboard/accounts context)
         * Opens the balance reconciliation modal
         */
        updateBalance() {
            this.openBalanceModal();
        },

        /**
         * Open balance reconciliation modal
         * Triggered by $ button in command bar
         */
        openBalanceModal() {
            // Pre-select first account if only one exists
            const activeAccounts = this.accounts.filter(a => !a.is_archived);

            this.balanceForm = {
                account_id: activeAccounts.length === 1 ? activeAccounts[0].id : '',
                projected_balance: 0,
                actual_balance: 0,
                drift: null,
                currency: this.settings.base_currency || 'GBP'
            };

            if (this.balanceForm.account_id) {
                this.calculateBalanceDrift();
            }

            this.showBalanceModal = true;
        },

        /**
         * Calculate projected balance and drift
         * Called when account selected or actual balance changed
         */
        calculateBalanceDrift() {
            if (!this.balanceForm.account_id) {
                this.balanceForm.drift = null;
                return;
            }

            const account = this.accounts.find(a => a.id === this.balanceForm.account_id);
            if (!account) return;

            this.balanceForm.currency = account.currency;

            // Calculate projected balance for this account at today's date
            const today = new Date().toISOString().split('T')[0];
            const projectedBalance = this.calculateAccountBalance(account.id, today);

            this.balanceForm.projected_balance = projectedBalance;

            // Calculate drift if actual balance entered
            if (this.balanceForm.actual_balance !== null && this.balanceForm.actual_balance !== '') {
                this.balanceForm.drift = parseFloat(this.balanceForm.actual_balance) - projectedBalance;
            } else {
                this.balanceForm.drift = null;
            }
        },

        /**
         * Calculate account balance at specific date
         * @param {string} accountId - Account UUID
         * @param {string} date - Date in YYYY-MM-DD format
         * @return {number} Projected balance
         */
        calculateAccountBalance(accountId, date) {
            const account = this.accounts.find(a => a.id === accountId);
            if (!account) return 0;

            // Start with account's current balance
            let balance = account.current_balance;

            // Add all events for this account up to date
            const accountEvents = this.events.filter(e =>
                e.account_id === accountId &&
                e.event_date <= date
            );

            for (const event of accountEvents) {
                balance += event.amount;
            }

            return balance;
        },

        /**
         * Calculate drift for accounts pending reconciliation
         * Returns virtual drift rows for display in projection
         *
         * Per refactored spec: Frontend displays drift without persisting events.
         * Server creates authoritative [auto] events on sync.
         *
         * @returns {Array} Array of virtual drift row objects
         */
        calculatePendingDrifts() {
            const today = new Date().toISOString().split('T')[0];
            const virtualRows = [];

            // Find accounts with pending_reconciliation = true
            const pendingAccounts = this.accounts.filter(a => a.pending_reconciliation === true);

            for (const account of pendingAccounts) {
                // Calculate projected balance for this account at today
                const projectedBalance = this.calculateAccountBalance(account.id, today);

                // Compare to actual balance
                const actualBalance = account.current_balance;
                const drift = actualBalance - projectedBalance;

                // Only create virtual row if drift is significant (> 0.01)
                if (Math.abs(drift) > 0.01) {
                    virtualRows.push({
                        id: `virtual-drift-${account.id}`,
                        date: today,
                        description: `pending adjustment for ${account.name}`,
                        amount: drift,
                        balance: actualBalance, // Balance after drift adjustment
                        account_id: account.id,
                        currency: account.currency,
                        source: '[pending sync]',
                        isDrift: true,
                        isVirtual: true,
                        isGap: false,
                        driftDetails: {
                            accountName: account.name,
                            projectedBalance,
                            actualBalance,
                            drift
                        }
                    });
                }
            }

            return virtualRows;
        },

        /**
         * Save balance update - creates changelog event for sync
         */
        async saveBalanceUpdate() {
            if (this.balanceForm.drift === 0) {
                this.showBalanceModal = false;
                return;
            }

            try {
                // Update local account current_balance and mark for reconciliation
                const account = this.accounts.find(a => a.id === this.balanceForm.account_id);
                if (!account) {
                    throw new Error('Account not found');
                }

                const updatedAccount = {
                    ...account,
                    current_balance: parseFloat(this.balanceForm.actual_balance),
                    pending_reconciliation: true, // Mark for reconciliation per spec
                    updated_at: new Date().toISOString()
                };

                if (storage.mode === 'full') {
                    // Get base_updated_at for conflict detection
                    const baseUpdatedAt = account.updated_at;

                    // Update account in Dexie
                    await db.accounts.put(updatedAccount);

                    // Queue account update for sync
                    await db.queueChange(
                        'account',
                        account.id,
                        'update',
                        updatedAccount,
                        baseUpdatedAt
                    );
                } else {
                    // Mode 0: Direct update without sync
                    Object.assign(account, updatedAccount);
                }

                // Reload data to reflect changes
                await this.loadData();
                await this.updateDashboardProjection();

                this.showBalanceModal = false;

                // Show notification
                const driftText = this.balanceForm.drift > 0
                    ? `+${formatCurrency(this.balanceForm.drift, this.balanceForm.currency)}`
                    : formatCurrency(this.balanceForm.drift, this.balanceForm.currency);
                showToast(`Balance updated. Drift: ${driftText} - Reconciliation will run on next trigger.`, 'success');

            } catch (error) {
                console.error('Error updating balance:', error);
                alert('Failed to update balance: ' + error.message);
            }
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


        // ===== EVENT MODAL METHODS =====

        /**
         * Open event modal for adding new event (dashboard context - baseline auto-assign)
         */
        openEventModal() {
            const today = new Date().toISOString().split('T')[0];

            this.eventForm = {
                date: today,
                description: '',
                amount: 0,
                account_id: '', // Will resolve via hierarchy
                currency: this.settings.base_currency || 'GBP',
                story_id: '', // Empty = baseline
                is_baseline: true,
                is_hypothetical: false
            };

            this.showEventModal = true;
        },

        /**
         * Open event modal for adding event to current story (projection context)
         * @param {string} storyId - Story UUID (from currentView)
         */
        openEventModalForStory(storyId) {
            const story = this.stories.find(s => s.id === storyId);
            if (!story) {
                alert('Story not found');
                return;
            }

            const today = new Date().toISOString().split('T')[0];

            // Use story date range if today falls outside
            let defaultDate = today;
            if (today < story.start_date) {
                defaultDate = story.start_date;
            } else if (story.end_date && today > story.end_date) {
                defaultDate = story.end_date;
            }

            // Get default account for currency fallback
            const defaultAccount = story.default_account_id
                ? this.accounts.find(a => a.id === story.default_account_id)
                : null;

            this.eventForm = {
                date: defaultDate,
                description: '',
                amount: 0,
                account_id: story.default_account_id || '',
                currency: story.display_currency || (defaultAccount ? defaultAccount.currency : null) || this.settings.base_currency || 'GBP',
                story_id: storyId,
                is_baseline: false,
                is_hypothetical: false
            };

            this.showEventModal = true;
        },

        /**
         * View event details for editing (opens edit modal)
         * @param {string} eventId - Event UUID
         */
        viewEventDetails(eventId) {
            if (!eventId) {
                console.error('viewEventDetails called without eventId');
                return;
            }

            const event = this.events.find(e => e.id === eventId);
            if (!event) {
                console.error('Event not found:', eventId);
                return;
            }

            this.eventForm = {
                id: event.id,
                event_date: event.event_date,
                description: event.description,
                amount: event.amount,
                account_id: event.account_id,
                currency: event.currency,
                story_id: event.story_id || '',
                is_baseline: event.is_baseline,
                is_hypothetical: event.is_hypothetical,
                updated_at: event.updated_at
            };

            this.showEventModal = true;
        },

        /**
         * Save event (create or update) with validation
         */
        async saveEvent() {
            // Validation: Required fields
            if (!this.eventForm.event_date) {
                alert('Event date is required');
                return;
            }

            if (!this.eventForm.description || this.eventForm.description.trim() === '') {
                alert('Description is required');
                return;
            }

            if (this.eventForm.amount === null || this.eventForm.amount === undefined) {
                alert('Amount is required');
                return;
            }

            // Validation: Currency format
            if (this.eventForm.currency && !/^[A-Z]{3}$/.test(this.eventForm.currency)) {
                alert('Currency must be a 3-letter code (e.g., GBP, USD)');
                return;
            }

            // Validation: Event date within story range
            if (this.eventForm.story_id && this.eventForm.story_id !== 'auto') {
                const story = this.stories.find(s => s.id === this.eventForm.story_id);
                if (story) {
                    const eventDate = this.eventForm.event_date;

                    if (eventDate < story.start_date) {
                        showToast(
                            `Event date must be within story period (${formatDate(story.start_date)} - ${story.end_date ? formatDate(story.end_date) : 'Ongoing'})`,
                            'error'
                        );
                        return;
                    }

                    if (story.end_date && eventDate > story.end_date) {
                        showToast(
                            `Event date must be within story period (${formatDate(story.start_date)} - ${formatDate(story.end_date)})`,
                            'error'
                        );
                        return;
                    }
                }
            }

            // Validation: Baseline XOR Story
            if (this.eventForm.is_baseline && this.eventForm.story_id) {
                alert('Event cannot be both baseline and assigned to a story');
                return;
            }

            // Validation: Account resolution
            const resolvedAccountId = this.resolveAccountId(
                this.eventForm.account_id || null,
                this.eventForm.story_id || null
            );

            if (!resolvedAccountId) {
                alert('No account available. Please create an account first or select one manually.');
                return;
            }

            try {
                const isEdit = !!this.eventForm.id;

                const eventData = {
                    event_date: this.eventForm.event_date,
                    description: this.eventForm.description.trim(),
                    amount: parseFloat(this.eventForm.amount),
                    account_id: resolvedAccountId,
                    currency: this.eventForm.currency || this.settings.base_currency || 'GBP',
                    story_id: this.eventForm.story_id || null,
                    is_baseline: !this.eventForm.story_id,
                    is_hypothetical: this.eventForm.is_hypothetical || false
                };

                if (isEdit) {
                    await this.updateEvent(this.eventForm.id, eventData);
                } else {
                    await this.createEvent(eventData);
                }

                this.showEventModal = false;

            } catch (error) {
                console.error('Error saving event:', error);
                alert('Failed to save event: ' + error.message);
            }
        },

        /**
         * Delete event from modal with confirmation
         */
        async deleteEventFromModal() {
            if (!confirm(`Delete event "${this.eventForm.description}"?\n\nThis will affect all projections.`)) {
                return;
            }

            try {
                await this.deleteEvent(this.eventForm.id);
                this.showEventModal = false;
            } catch (error) {
                console.error('Error deleting event:', error);
                alert('Failed to delete event: ' + error.message);
            }
        },

        /**
         * Get account hierarchy hint text for form
         * Shows which account will be used based on current selections
         */
        getAccountHierarchyHint() {
            if (this.eventForm.account_id) {
                const account = this.accounts.find(a => a.id === this.eventForm.account_id);
                return account ? `Will use: ${account.name}` : 'Selected account';
            }

            if (this.eventForm.story_id) {
                const story = this.stories.find(s => s.id === this.eventForm.story_id);
                if (story && story.default_account_id) {
                    const account = this.accounts.find(a => a.id === story.default_account_id);
                    if (account) {
                        return `Will use story default: ${account.name}`;
                    }
                }
            }

            const defaultAccount = this.accounts.find(a => a.is_default && !a.is_archived);
            if (defaultAccount) {
                return `Will use global default: ${defaultAccount.name}`;
            }

            return '⚠ No default account available - please select one';
        },

        /**
         * Handle story selection change
         * Auto-updates account and currency based on story defaults
         */
        handleStoryChange() {
            const storyId = this.eventForm.story_id;

            this.eventForm.is_baseline = !storyId;

            if (storyId) {
                const story = this.stories.find(s => s.id === storyId);
                if (story) {
                    if (!this.eventForm.account_id && story.default_account_id) {
                        this.eventForm.account_id = story.default_account_id;

                        const account = this.accounts.find(a => a.id === story.default_account_id);
                        if (account) {
                            this.eventForm.currency = account.currency;
                        }
                    }

                    if (story.display_currency && !this.eventForm.currency) {
                        this.eventForm.currency = story.display_currency;
                    }
                }
            }
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
