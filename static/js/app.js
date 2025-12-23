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
            } catch (error) {
                console.error('Error loading from Dexie:', error);
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
            try {
                await db.transaction('rw', [db.accounts, db.stories, db.events, db.settings], async () => {
                    for (const change of serverChanges) {
                        const table = change.entity_type + 's'; // accounts, stories, events

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
            // TODO: Calculate from projection
            return '✓ £130 LEFT';
        },

        /**
         * Get story status CSS class
         * @param {object} story - Story object
         * @returns {string} CSS class name
         */
        getStoryStatusClass(story) {
            // TODO: Determine from actual spend vs goal
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
