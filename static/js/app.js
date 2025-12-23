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

        // UI State
        isSyncing: false,
        showAccountModal: false,
        showEventModal: false,
        accountForm: {},
        eventForm: {},

        // Projection State
        currentView: 'all',
        displayCurrency: null,
        projectionStartDate: null,
        projectionEndDate: null,
        projectionStartingBalance: 0,
        projectionRows: [],
        projectionToday: 0,
        projectionEndOfMonth: 0,

        // Expanded gaps tracking
        expandedGaps: new Set(),

        // ===== LIFECYCLE =====

        /**
         * Initialize app on mount
         */
        async init() {
            console.log('CHAPTR initializing...');

            // Load user from localStorage
            await this.loadUser();

            // Load data (from Dexie or sync)
            await this.loadData();

            // Set initial projection dates
            this.setDefaultProjectionDates();

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
                    console.log('No local data - triggering full sync...');
                    await this.fullSync();
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
                const settingsDoc = await db.settings.get(1);
                this.settings = settingsDoc || { base_currency: 'GBP' };

                console.log(`Loaded: ${this.accounts.length} accounts, ${this.stories.length} stories, ${this.events.length} events`);

                // Update dashboard projection summary
                await this.updateDashboardProjection();
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
        switchScreen(screen) {
            this.currentScreen = screen;
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
        viewStoryProjection(storyId) {
            this.currentView = storyId;
            this.currentScreen = 'projection';
        },

        /**
         * Set projection view (all, baseline, or story ID)
         * @param {string} view - View identifier
         */
        setView(view) {
            this.currentView = view;
            // Reset display currency when switching views
            if (view !== 'all') {
                this.displayCurrency = null;
            }
        },

        /**
         * Toggle display currency (for ALL view only)
         */
        toggleDisplayCurrency() {
            if (this.currentView !== 'all') return;

            // Cycle through available currencies
            const currencies = ['GBP', 'USD', 'EUR', 'CAD'];
            const currentIndex = currencies.indexOf(this.displayCurrency || this.settings.base_currency);
            const nextIndex = (currentIndex + 1) % currencies.length;
            this.displayCurrency = currencies[nextIndex];
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
            // If no goal, show lifecycle status
            if (!story.goal_type || !story.goal_amount) {
                return this.getStoryLifecycleStatus(story);
            }

            // Calculate based on goal type
            // Note: This is a synchronous approximation for dashboard display
            // Real calculation would require async projection, which is too expensive per story
            const goalAmount = parseFloat(story.goal_amount || 0);

            if (story.goal_type === 'spend_up_to') {
                // For now, show goal amount - will be calculated properly in projection view
                const currency = story.display_currency || this.settings.base_currency || 'GBP';
                return `SPEND UP TO ${formatCurrency(goalAmount, currency)}`;
            } else if (story.goal_type === 'end_with_at_least') {
                const currency = story.display_currency || this.settings.base_currency || 'GBP';
                return `END WITH ${formatCurrency(goalAmount, currency)}`;
            }

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

        // Account CRUD operations will be added in PR2

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
         */
        getDriftClass() {
            // TODO: Calculate drift
            return 'positive';
        },

        /**
         * Format drift amount
         */
        formatDrift() {
            // TODO: Calculate drift
            return '+£50';
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
