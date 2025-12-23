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
    clearAuth
} from './utils.js';

import { db } from './db.js';
import { calculateProjection } from './projection.js';

/**
 * Main Alpine.js app component
 * @returns {object} Alpine.js component
 */
window.app = function() {
    return {
        // ===== STATE =====

        // Navigation
        currentScreen: 'dashboard',

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
        showAccountModal: false,
        showEventModal: false,
        showUserModal: false,
        accountForm: {},
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

            // Set initial projection dates FIRST (before any rendering happens)
            this.setDefaultProjectionDates();

            // Load user from localStorage
            await this.loadUser();

            // Load data (from Dexie or sync)
            await this.loadData();

            console.log('CHAPTR ready!');
        },

        /**
         * Load user from localStorage or API
         */
        async loadUser() {
            const storedUser = localStorage.getItem('user');
            if (storedUser) {
                this.user = JSON.parse(storedUser);
            }
        },

        /**
         * Load data from Dexie or trigger full sync
         */
        async loadData() {
            try {
                // Check if Dexie has data
                const accountCount = await db.accounts.count();

                if (accountCount === 0) {
                    console.log('No local data - Phase 3 sync not implemented yet');
                    // Phase 3: await this.fullSync();

                    // For now, just load empty data
                    await this.loadFromDexie();
                } else {
                    console.log('Loading from Dexie...');
                    await this.loadFromDexie();
                }
            } catch (error) {
                console.error('Error loading data:', error);
            }
        },

        /**
         * Load data from Dexie
         */
        async loadFromDexie() {
            try {
                this.stories = await db.stories.toArray();
                this.accounts = await db.accounts.toArray();
                this.events = await db.events.toArray();
                this.users = await db.users.toArray();
                const settingsDoc = await db.settings.get(1);
                this.settings = settingsDoc || { base_currency: 'GBP' };

                // Initialize settings form
                this.settingsForm = { ...this.settings };

                console.log(`Loaded: ${this.accounts.length} accounts, ${this.stories.length} stories, ${this.events.length} events`);

                // Update dashboard projection summary
                await this.updateDashboardProjection();

                // Calculate story goal statuses
                await this.calculateStoryStatuses();

                // Calculate accounts total
                this.calculateAccountsTotal();
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
                // For PR2, this will integrate with Dexie + API
                // For now, just close modal
                console.log('Save account:', this.accountForm);
                this.showAccountModal = false;

                // TODO PR2: Implement CRUD
                // - Write to Dexie
                // - Call API endpoint
                // - Reload data

            } catch (error) {
                console.error('Error saving account:', error);
                alert('Failed to save account');
            }
        },

        /**
         * Delete account
         */
        async deleteAccount() {
            if (!confirm(`Delete account "${this.accountForm.name}"?`)) {
                return;
            }

            try {
                // For PR2, this will integrate with Dexie + API
                console.log('Delete account:', this.accountForm.id);
                this.showAccountModal = false;

                // TODO PR2: Implement delete
                // - Mark as archived in Dexie
                // - Call API endpoint
                // - Reload data

            } catch (error) {
                console.error('Error deleting account:', error);
                alert('Failed to delete account');
            }
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

            if (!confirm('⚠ This will OVERWRITE all existing data. Continue?')) {
                event.target.value = '';
                return;
            }

            try {
                const text = await file.text();
                const backup = JSON.parse(text);

                // Validate backup structure
                if (!backup.version || !backup.accounts) {
                    throw new Error('Invalid backup file format');
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
        }

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

        // ===== AUTH =====

        /**
         * Logout user
         */
        logout() {
            clearAuth();
            this.user = null;
            window.location.href = '/login';
        }
    };
};
