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
    parseISODate,
    apiRequest,
    getClientId,
    clearAuth,
    generateUUID,
    showToast,
    toLocalISODate
} from './utils.js';

import { db } from './db.js';
import { storage } from './storage-adapter.js';
import { calculateProjection } from './projection.js';
import { createOpeningBalanceEventData, generateRecurringInstances } from './event-helpers.js';
import { applyDerivedChange, applyDerivedChangesBatch } from './queue-helpers.js';
import { ValidationHelpers } from './validation-helpers.js';

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

        // Sync Configuration Constants
        SYNC_TIMEOUT_MS: 30000,        // Maximum 30 seconds for sync operation
        MIN_SPINNER_DURATION_MS: 1000, // Minimum 1 second for spinner visibility

        // Auto-Sync State
        autoSyncTimerId: null,         // Timer ID for auto-sync
        autoSyncPending: false,        // Sync pending while tab was hidden
        autoSyncCountdown: '',         // Countdown display string (e.g., "4:32")
        countdownTimerId: null,        // Timer ID for countdown display updates

        // Notification State
        currentNotification: null,      // { message: string, type: string }
        notificationTimeout: null,       // Timeout ID for auto-dismiss

        // Reconciliation State
        needsProjectionRefresh: false,  // Flag to refresh projection after reconciliation

        showAccountModal: false,
        showStoryModal: false,
        showEventModal: false,
        showUserModal: false,
        showHelpModal: false,
        showBalanceModal: false,
        showDatabaseToolsModal: false,
        showConfirmModal: false,
        showInputModal: false,
        showPasswordModal: false,
        confirmModalData: {
            title: '',
            message: '',
            confirmText: 'Confirm',
            confirmStyle: 'primary', // 'primary' or 'danger'
            onConfirm: null
        },
        inputModalData: {
            title: '',
            message: '',
            placeholder: '',
            inputValue: '',
            inputType: 'text', // 'text' or 'number'
            pattern: null, // Regex pattern for validation
            onSubmit: null,
            validator: null // Custom validation function
        },
        passwordModalData: {
            title: '',
            message: '',
            placeholder: '',
            passwordValue: '',
            onSubmit: null
        },
        accountForm: {},
        storyForm: {},
        eventForm: {},
        eventFormErrors: {
            description: false,
            amount: false,
            account: false,
            event_date: false,
            currency: false,
            frequency: false,
            day: false,
            start_date: false
        },
        accountFormErrors: {
            name: false,
            currency: false,
            current_balance: false
        },
        storyFormErrors: {
            name: false,
            start_date: false,
            end_date: false,
            funding_amount: false,
            goal_amount: false,
            display_currency: false
        },
        balanceFormErrors: {
            account_id: false,
            actual_balance: false
        },
        loginFormErrors: {
            username: false,
            password: false
        },
        userForm: {
            id: null,
            username: '',
            role: 'user',
            password: '',
            current_password: ''
        },
        userFormErrors: {
            username: false,
            password: false,
            current_password: false
        },
        userModalMode: 'create', // 'create' | 'edit' | 'self'
        settingsForm: {},
        balanceForm: {
            account_id: '',
            projected_balance: 0,
            actual_balance: 0,
            drift: null,
            currency: 'GBP'
        },
        accountsTotal: 0,
        accountSearchFilter: '',

        // Story Management
        storySearchFilter: '',
        filteredStories: [],
        showArchivedStories: false,

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

        // Conflict resolution
        showConflictModal: false,
        conflicts: [],
        currentConflict: null,
        currentConflictIndex: 0,

        // ===== LIFECYCLE =====

        /**
         * Initialize app on mount
         */
        async init() {
            console.log('CHAPTR initializing...');

            // DEFENSIVE: Reset sync state on initialization (catches stuck spinners from crashes/refresh)
            this.isSyncing = false;
            this.syncButtonSpinner = false;

            // Check authentication first
            await this.checkAuth();

            // If not authenticated, stop here (login screen will show)
            if (!this.isAuthenticated) {
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

            // Start auto-sync timer based on settings
            this.startAutoSyncTimer();

            // Check for unresolved conflicts
            await this.checkForConflicts();

            // Setup network reconnection handler - auto-retry sync when online
            window.addEventListener('online', async () => {
                await this.updateSyncQueueCount();
                if (this.syncQueueCount > 0) {
                    await this.manualSync();
                }
            });

            // DEFENSIVE: Reset spinner if page becomes visible (catches tab switching/background)
            // Also handles auto-sync pause/resume on tab visibility
            document.addEventListener('visibilitychange', () => {
                if (!document.hidden && this.syncButtonSpinner) {
                    console.warn('Page became visible with spinner active - resetting sync state');
                    this.isSyncing = false;
                    this.syncButtonSpinner = false;
                }
                // Handle auto-sync pause/resume
                this.handleAutoSyncVisibilityChange();
            });

            // DEFENSIVE: Reset spinner before page unload (catches navigation/refresh)
            window.addEventListener('beforeunload', () => {
                this.isSyncing = false;
                this.syncButtonSpinner = false;
            });

            // Expose notification method globally for utils.js and storage-adapter.js
            window.showNotification = this.showNotification.bind(this);

            // Setup ESC key handler to close modals (with debounce to prevent double-close)
            // Encapsulated in closure to avoid scope pollution
            const appContext = this; // Capture Alpine context
            window.addEventListener('keydown', (() => {
                let escDebounceTimer = null; // Enclosed in closure
                return (event) => {
                    if (event.key === 'Escape' && !escDebounceTimer) {
                        // Find and close the topmost modal
                        const modalPriority = [
                            'showPasswordModal',
                            'showInputModal',
                            'showConfirmModal',
                            'showConflictModal',
                            'showDatabaseToolsModal',
                            'showBalanceModal',
                            'showHelpModal',
                            'showUserModal',
                            'showEventModal',
                            'showStoryModal',
                            'showAccountModal'
                        ];

                        for (const modalName of modalPriority) {
                            if (appContext[modalName] === true) {
                                appContext[modalName] = false;
                                break; // Only close one modal per ESC press
                            }
                        }

                        // Debounce 250ms to prevent accidental double-close
                        escDebounceTimer = setTimeout(() => {
                            escDebounceTimer = null;
                        }, 250);
                    }
                };
            })());

            // Prevent scroll wheel from changing number input values
            document.addEventListener('wheel', (event) => {
                if (event.target.type === 'number') {
                    event.target.blur();
                }
            }, { passive: true });

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
                this.users = []; // Users loaded from admin API for admins
                this.settings = await storage.getSettings() || { base_currency: 'GBP' };

                // Load users from admin API if user is admin or super_admin
                if (['admin', 'super_admin'].includes(this.user?.role)) {
                    try {
                        const response = await apiRequest('/api/admin/users', { method: 'GET' });
                        if (response.ok) {
                            this.users = await response.json();
                        } else {
                            console.warn('Failed to load users:', response.status);
                            this.users = [];
                        }
                    } catch (error) {
                        console.warn('Failed to load users (admin only):', error);
                        this.users = [];
                    }
                }

                // Initialize settings form
                this.settingsForm = {
                    ...this.settings,
                    rates: this.settings.rates || {}
                };

                // Initialize filtered stories (show all non-archived by default)
                this.filteredStories = this.stories.filter(s => !s.is_archived);

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
                    toLocalISODate(today),
                    toLocalISODate(endOfMonth),
                    'all',
                    null,
                    this.settings.base_currency,
                    [],
                    this.settings
                );

                // Find today's balance (first event on or after today, or last past event)
                const todayStr = toLocalISODate(today);
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

                    // Defensive check for NaN goal amount
                    if (isNaN(goalAmount) || goalAmount === 0) {
                        console.warn(`[Story Status] Invalid goal amount for story ${story.name}: goal_amount=${story.goal_amount}, parsed=${goalAmount}`);
                        this.storyStatuses[story.id] = this.getStoryLifecycleStatus(story);
                        continue;
                    }

                    if (story.goal_type === 'spend_up_to') {
                        // Calculate total spending in this story
                        const storyEvents = this.events.filter(e =>
                            e.story_id === story.id &&
                            e.amount < 0 &&
                            e.event_date >= story.start_date &&
                            e.event_date <= story.end_date
                        );

                        const totalSpent = Math.abs(storyEvents.reduce((sum, e) => sum + parseFloat(e.amount || 0), 0));
                        const remaining = goalAmount - totalSpent;

                        // Defensive check for NaN remaining
                        if (isNaN(remaining)) {
                            this.storyStatuses[story.id] = this.getStoryLifecycleStatus(story);
                            continue;
                        }

                        if (remaining >= 0) {
                            this.storyStatuses[story.id] = `[OK] ${formatCurrency(remaining, currency)} LEFT`;
                        } else {
                            this.storyStatuses[story.id] = `[!!] ${formatCurrency(Math.abs(remaining), currency)} OVER`;
                        }
                    } else if (story.goal_type === 'end_with_at_least') {
                        // Run projection to story end date
                        try {
                            const projection = await calculateProjection(
                                story.start_date,
                                story.end_date,
                                story.id,
                                story.id,
                                currency,
                                [],
                                this.settings
                            );

                            const lastEvent = projection.filter(row => !row.isGap).pop();
                            const endingBalance = lastEvent ? parseFloat(lastEvent.balance || 0) : 0;
                            const difference = endingBalance - goalAmount;

                            // Defensive check for NaN difference
                            if (isNaN(difference)) {
                                this.storyStatuses[story.id] = this.getStoryLifecycleStatus(story);
                                continue;
                            }

                            if (difference >= 0) {
                                this.storyStatuses[story.id] = `[OK] ${formatCurrency(difference, currency)} OVER`;
                            } else {
                                this.storyStatuses[story.id] = `[!!] ${formatCurrency(Math.abs(difference), currency)} SHORT`;
                            }
                        } catch (error) {
                            console.error(`Error calculating status for story ${story.id}:`, error);
                            // Fallback to lifecycle status on error
                            this.storyStatuses[story.id] = this.getStoryLifecycleStatus(story);
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

                // Set flag to refresh projection
                this.needsProjectionRefresh = true;
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
                // Refresh projection if sync occurred while on another screen
                if (this.needsProjectionRefresh) {
                    this.needsProjectionRefresh = false;
                }

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

        /**
         * Get unique currencies from user's accounts
         *
         * Always includes base currency, plus currencies from all accounts.
         * Used to filter which rates are displayed in settings.
         *
         * @returns {string[]} Array of currency codes
         */
        get availableCurrencies() {
            const currencies = new Set([this.settings?.base_currency || 'GBP']);
            for (const account of this.accounts) {
                if (account.currency) {
                    currencies.add(account.currency);
                }
            }
            return Array.from(currencies);
        },

        /**
         * Filter rates to only show currencies user has accounts for
         *
         * Returns rates dictionary filtered to availableCurrencies.
         * Used in settings screen for read-only rates display.
         *
         * @returns {Object} Filtered rates dictionary
         */
        get displayRates() {
            const available = this.availableCurrencies;
            const rates = {};
            for (const [currency, rate] of Object.entries(this.settings?.rates || {})) {
                if (available.includes(currency)) {
                    rates[currency] = rate;
                }
            }
            return rates;
        },

        // ===== PROJECTION =====

        /**
         * Set default projection date range (today to +12 months)
         */
        setDefaultProjectionDates() {
            const today = new Date();
            const nextYear = new Date(today);
            nextYear.setFullYear(nextYear.getFullYear() + 1);

            this.projectionStartDate = toLocalISODate(today);
            this.projectionEndDate = toLocalISODate(nextYear);
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

            // Clear expanded gaps to prevent memory leak across view changes
            this.expandedGaps.clear();

            // Reset display currency when switching views
            if (view !== 'all') {
                this.displayCurrency = null;
            }

            // Adjust projection date range based on view
            if (view !== 'all' && view !== 'baseline') {
                // Story view - use story's date range
                const story = this.stories.find(s => s.id === view);
                if (story) {
                    this.projectionStartDate = story.start_date;
                    // Use story end_date if set, otherwise default to 1 year from start
                    this.projectionEndDate = story.end_date || toLocalISODate(new Date(new Date(story.start_date).setFullYear(new Date(story.start_date).getFullYear() + 1)));
                }
            } else if (view === 'baseline') {
                // Baseline view - use baseline_display_months setting
                const today = new Date();
                const endDate = new Date(today);
                const months = this.settings.baseline_display_months || 3;
                endDate.setMonth(endDate.getMonth() + months);

                this.projectionStartDate = toLocalISODate(today);
                this.projectionEndDate = toLocalISODate(endDate);
            } else {
                // ALL view - show 12 months from today
                const today = new Date();
                const nextYear = new Date(today);
                nextYear.setFullYear(nextYear.getFullYear() + 1);

                this.projectionStartDate = toLocalISODate(today);
                this.projectionEndDate = toLocalISODate(nextYear);
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
                    virtualDrifts,
                    this.settings  // ← Pass the already-loaded settings!
                );

                // Extract starting balance from first actual event (skip gap indicators)
                const firstEvent = this.projectionRows.find(row => !row.isGap && !row.isHistoricalGap);
                if (firstEvent) {
                    // Starting balance is the balance of the first event minus its amount
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
            const today = toLocalISODate(new Date());
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
            const today = toLocalISODate(new Date());

            // Lifecycle-based classes
            if (story.end_date < today) {
                return 'status-past';
            } else if (story.start_date > today) {
                return 'status-upcoming';
            }

            // Active story - check calculated status for color
            const status = this.getStoryStatus(story);

            // Bad states: [!!] indicator (OVER budget or SHORT of goal)
            if (status.includes('[!!]')) {
                return 'status-warn';
            }

            // Good states: [OK] indicator (LEFT in budget or OVER goal target)
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
         * Get accounts total in display currency (or base currency if no display currency set)
         * @returns {number} Total of all accounts in display currency
         */
        getAccountsTotalDisplay() {
            const baseCurrency = this.settings.base_currency;
            const displayCurrency = this.displayCurrency;

            // accountsTotal is already in base currency
            let total = this.accountsTotal;

            // Convert to display currency if needed
            if (displayCurrency && displayCurrency !== baseCurrency) {
                const displayRate = this.settings.rates[displayCurrency] || 1.0;
                total = Math.round(total * displayRate * 100) / 100;
            }

            return total;
        },

        /**
         * Get currency code for accounts total display
         * @returns {string} Display currency code or base currency code
         */
        getAccountsTotalCurrency() {
            return this.displayCurrency || this.settings.base_currency;
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
                this.showNotification('Syncing...', 'info');

                const result = await storage.manualSync();

                if (result.conflicts && result.conflicts > 0) {
                    this.showNotification(`${result.conflicts} sync conflicts`, 'warning');
                } else if (result.applied && result.applied > 0) {
                    this.showNotification(this.formatSyncResult(result), 'success');
                }

                // Update queue count
                await this.updateSyncQueueCount();

                // Reload data to reflect server changes
                await this.loadData();

                // Show conflict resolution modal if conflicts exist
                await this.checkForConflicts();

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
            ValidationHelpers.resetFormErrors(this.accountFormErrors);
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
            ValidationHelpers.resetFormErrors(this.accountFormErrors);
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
            // Reset errors
            ValidationHelpers.resetFormErrors(this.accountFormErrors);

            // HTML5 validation
            const form = this.$refs.accountFormElement;
            if (!form) {
                console.error('Account form ref not found');
                return;
            }

            if (!ValidationHelpers.validateHTML5(form, this.accountFormErrors)) {
                const count = ValidationHelpers.countErrors(this.accountFormErrors);
                this.showNotification(`Please fix ${count} field(s)`, 'error');
                return;
            }

            // Business logic: currency pattern validation
            if (!ValidationHelpers.validateCurrencyCode(
                this.accountForm.currency,
                this.accountFormErrors,
                'currency'
            )) {
                this.showNotification('Invalid currency code (must be 3 uppercase letters)', 'error');
                return;
            }

            // Business logic: default account uniqueness
            const isEdit = !!this.accountForm.id;
            if (this.accountForm.is_default) {
                const existingDefault = this.accounts.find(a =>
                    a.is_default && (!isEdit || a.id !== this.accountForm.id)
                );
                if (existingDefault) {
                    this.showNotification(
                        `Cannot set as default. "${existingDefault.name}" is already the default account. Please unset it first.`,
                        'error'
                    );
                    return;
                }
            }

            // Existing save logic
            try {
                if (isEdit) {
                    await this.updateAccount();
                } else {
                    await this.createAccount();
                }

                this.showAccountModal = false;

            } catch (error) {
                console.error('Error saving account:', error);
                this.showNotification('Save failed', 'error');
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
            const createdAccount = await storage.createAccount(accountData);

            // Queue-as-state: Create opening balance event if non-zero balance
            // No mode check needed - queue-helpers handles this uniformly
            if (parseFloat(accountData.current_balance) !== 0) {
                // Use pure function to create event data
                const openingEventData = createOpeningBalanceEventData(createdAccount, this.settings);

                if (openingEventData) {
                    // Apply as derived change (marked _derived_from: 'account_creation')
                    await applyDerivedChange(
                        {
                            entity_type: 'event',
                            entity_id: openingEventData.id,
                            action: 'create',
                            data: openingEventData,
                            base_updated_at: null
                        },
                        {
                            _derived_from: 'account_creation',
                            dependencies: [createdAccount.id]
                        }
                    );
                }
            }

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
            const newBalance = parseFloat(this.accountForm.current_balance || 0);

            // Check if balance changed to trigger reconciliation
            const currentAccount = this.accounts.find(a => a.id === accountId);
            const balanceChanged = currentAccount && parseFloat(currentAccount.current_balance) !== newBalance;

            const updates = {
                name: this.accountForm.name,
                currency: this.accountForm.currency.toUpperCase(),
                current_balance: String(newBalance),
                is_default: this.accountForm.is_default || false
            };

            // If balance changed, set flag to trigger server-side adjustment
            if (balanceChanged) {
                updates.pending_reconciliation = true;
            }

            // Use storage adapter (handles all 3 modes)
            await storage.updateAccount(accountId, updates);

            // Update sync queue count for UI indicator
            await this.updateSyncQueueCount();

            // Reload data
            await this.loadData();
        },

        /**
         * Delete account (via storage adapter)
         * Requires typing account name for confirmation (case-insensitive)
         */
        async deleteAccount() {
            const accountName = this.accountForm.name;

            // Prompt user to type account name for confirmation
            const userInput = window.prompt(
                `⚠️  DELETE ACCOUNT\n\nTo confirm deletion, please type the account name:\n\n"${accountName}"\n\nThis action cannot be undone.`
            );

            // Check if user cancelled or input doesn't match (case-insensitive)
            if (!userInput || userInput.trim().toLowerCase() !== accountName.toLowerCase()) {
                if (userInput !== null) {
                    // User tried but got it wrong
                    this.showNotification('Account name did not match. Deletion cancelled.', 'error');
                }
                return; // Exit without deleting
            }

            // Name matched - proceed with deletion
            try {
                const accountId = this.accountForm.id;

                // Use storage adapter (handles all 3 modes)
                await storage.deleteAccount(accountId);

                // Update sync queue count for UI indicator
                await this.updateSyncQueueCount();

                this.showAccountModal = false;

                // Reload data
                await this.loadData();

                this.showNotification('Account deleted', 'success');

            } catch (error) {
                console.error('Error deleting account:', error);
                this.showNotification('Delete failed', 'error');
            }
        },

        // ===== STORIES =====

        /**
         * Open story modal for adding new story
         */
        openStoryModal() {
            ValidationHelpers.resetFormErrors(this.storyFormErrors);
            this.storyForm = {
                name: '',
                start_date: toLocalISODate(new Date()),
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
            ValidationHelpers.resetFormErrors(this.storyFormErrors);
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
            // Reset errors
            ValidationHelpers.resetFormErrors(this.storyFormErrors);

            // HTML5 validation
            const form = this.$refs.storyFormElement;
            if (!form) {
                console.error('Story form ref not found');
                return;
            }

            if (!ValidationHelpers.validateHTML5(form, this.storyFormErrors)) {
                const count = ValidationHelpers.countErrors(this.storyFormErrors);
                this.showNotification(`Please fix ${count} field(s)`, 'error');
                return;
            }

            // Cross-field validation: end_date >= start_date
            if (!ValidationHelpers.validateDateRange(
                this.storyForm.start_date,
                this.storyForm.end_date,
                this.storyFormErrors,
                'end_date'
            )) {
                this.showNotification('End date must be after start date', 'error');
                return;
            }

            // Conditional required: funding_amount
            const fundingRequired =
                this.storyForm.funding_mode === 'fixed' ||
                this.storyForm.funding_mode === 'projected_plus';

            if (!ValidationHelpers.validateConditionalRequired(
                fundingRequired,
                this.storyForm.funding_amount,
                this.storyFormErrors,
                'funding_amount'
            )) {
                this.showNotification('Funding amount required for this funding mode', 'error');
                return;
            }

            // Conditional required: goal_amount
            const goalRequired =
                this.storyForm.goal_type &&
                this.storyForm.goal_type !== 'none';

            if (!ValidationHelpers.validateConditionalRequired(
                goalRequired,
                this.storyForm.goal_amount,
                this.storyFormErrors,
                'goal_amount'
            )) {
                this.showNotification('Goal amount required when goal type is set', 'error');
                return;
            }

            // Optional currency validation
            if (this.storyForm.display_currency &&
                !ValidationHelpers.validateCurrencyCode(
                    this.storyForm.display_currency,
                    this.storyFormErrors,
                    'display_currency'
                )) {
                this.showNotification('Invalid currency code (must be 3 uppercase letters)', 'error');
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
                this.showNotification('Save failed', 'error');
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
                this.showNotification('Delete failed', 'error');
            }
        },

        /**
         * Archive/unarchive story from modal
         */
        async archiveStoryFromModal() {
            const storyId = this.storyForm.id;
            const storyName = this.storyForm.name;
            const isArchived = this.storyForm.is_archived;
            const action = isArchived ? 'Unarchive' : 'Archive';
            const confirmMessage = isArchived
                ? `Unarchive "${storyName}"?\n\nIt will be visible in the active stories list.`
                : `Archive "${storyName}"?\n\nIt will be moved to the archived section.`;

            this.showConfirm(
                `${action} Story`,
                confirmMessage,
                async () => {
                    try {
                        await this.updateStory(storyId, { is_archived: !isArchived });
                        await this.loadData();
                        this.filterStories();
                        this.showStoryModal = false;
                        this.showNotification(`Story ${action.toLowerCase()}d`, 'success');
                    } catch (error) {
                        console.error(`Error ${action.toLowerCase()}ing story:`, error);
                        this.showNotification(`${action} failed`, 'error');
                    }
                },
                action,
                'warning'
            );
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
         * Get archived stories sorted by updated_at (most recently archived first)
         * Also filters by search query if present
         * @returns {Array} Archived stories sorted by date
         */
        getArchivedStories() {
            const query = this.storySearchFilter.toLowerCase();
            return this.stories
                .filter(s => s.is_archived && (!query || s.name.toLowerCase().includes(query)))
                .sort((a, b) => new Date(b.updated_at) - new Date(a.updated_at));
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

            this.showConfirm(
                `${action} Story`,
                confirmMessage,
                async () => {
                    try {
                        await this.updateStory(storyId, { is_archived: !story.is_archived });
                        await this.loadData();
                        this.filterStories(); // Refresh filtered list
                    } catch (error) {
                        console.error(`Error ${action.toLowerCase()}ing story:`, error);
                        this.showNotification(`${action} failed`, 'error');
                    }
                },
                action,
                'danger'
            );
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
         * Get filtered accounts (non-archived) based on search query
         * @returns {Array} Filtered accounts
         */
        getFilteredAccounts() {
            const query = this.accountSearchFilter.toLowerCase();
            return this.accounts.filter(a =>
                !a.is_archived &&
                (!query || a.name.toLowerCase().includes(query))
            );
        },

        /**
         * Get projected balance for an account in 30 days
         * @param {string} accountId - Account UUID
         * @returns {number} Projected balance at 30 days
         */
        getAccountProjection30Days(accountId) {
            const account = this.accounts.find(a => a.id === accountId);
            if (!account) return 0;

            // Calculate date 30 days from today
            const today = new Date();
            const targetDate = toLocalISODate(new Date(today.getTime() + 30 * 24 * 60 * 60 * 1000));

            // Get events for this account in the next 30 days
            const accountEvents = this.events.filter(e =>
                e.account_id === accountId &&
                !e.is_hypothetical &&
                e.event_date >= toLocalISODate(today) &&
                e.event_date <= targetDate
            );

            // Sum up events to get projected change
            const totalChange = accountEvents.reduce((sum, event) => {
                return sum + parseFloat(event.amount || 0);
            }, 0);

            // Parse balance as float to avoid string concatenation
            return parseFloat(account.current_balance || 0) + totalChange;
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

            const confirmMsg = associatedEvents.length > 0
                ? `Delete story "${story.name}"?\n\nThis will also delete ${associatedEvents.length} associated event(s).`
                : `Delete story "${story.name}"?`;

            this.showConfirm(
                'Delete Story',
                confirmMsg,
                async () => {
                    // Delete associated events if any
                    if (associatedEvents.length > 0) {
                        for (const event of associatedEvents) {
                            await this.deleteEvent(event.id);
                        }
                    }

                    await this.performStoryDeletion(storyId, story);
                },
                'Delete',
                'danger'
            );
        },

        async performStoryDeletion(storyId, story) {

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
                this.showNotification('Account required', 'error');
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

            // 3. Reload data
            await this.loadData();
        },

        // ===== SETTINGS =====

        /**
         * Open user modal for adding new user (admin only)
         */
        openUserModal() {
            this.userModalMode = 'create';
            this.userForm = {
                id: null,
                username: '',
                role: 'user',
                password: '',
                current_password: ''
            };
            this.userFormErrors = {
                username: false,
                password: false,
                current_password: false
            };
            this.showUserModal = true;
        },

        /**
         * Open user modal for editing own profile (self-service)
         */
        openMyAccountModal() {
            this.userModalMode = 'self';
            this.userForm = {
                id: this.user?.id,
                username: this.user?.username || '',
                role: this.user?.role || 'user',
                password: '',
                current_password: ''
            };
            this.userFormErrors = {
                username: false,
                password: false,
                current_password: false
            };
            this.showUserModal = true;
        },

        /**
         * Edit existing user (admin only)
         * @param {string} userId - User UUID
         */
        editUser(userId) {
            const user = this.users.find(u => u.id === userId);
            if (user) {
                this.userModalMode = 'edit';
                this.userForm = {
                    id: user.id,
                    username: user.username,
                    role: user.role,
                    password: '',
                    current_password: ''
                };
                this.userFormErrors = {
                    username: false,
                    password: false,
                    current_password: false
                };
                this.showUserModal = true;
            }
        },

        /**
         * Save user (dispatch to create/update based on mode)
         */
        async saveUser() {
            // Reset errors
            this.userFormErrors = {
                username: false,
                password: false,
                current_password: false
            };

            // Validate username
            if (!this.userForm.username || this.userForm.username.trim() === '') {
                this.userFormErrors.username = true;
                return;
            }

            // For create mode, password is required
            if (this.userModalMode === 'create' && !this.userForm.password) {
                this.userFormErrors.password = true;
                return;
            }

            // For self-service with password change, current_password is required
            if (this.userModalMode === 'self' && this.userForm.password && !this.userForm.current_password) {
                this.userFormErrors.current_password = true;
                return;
            }

            try {
                if (this.userModalMode === 'create') {
                    await this.createUser();
                } else if (this.userModalMode === 'edit') {
                    await this.updateUser();
                } else if (this.userModalMode === 'self') {
                    await this.updateMyAccount();
                }
                this.showUserModal = false;
                this.showNotification('User saved', 'success');
            } catch (error) {
                console.error('Error saving user:', error);
                this.showNotification(error.message || 'Save failed', 'error');
            }
        },

        /**
         * Create new user (admin only)
         */
        async createUser() {
            const data = {
                username: this.userForm.username.trim(),
                role: this.userForm.role || 'user',
                password: this.userForm.password
            };

            await apiRequest('/api/admin/users', {
                method: 'POST',
                body: JSON.stringify(data)
            });

            await this.loadData();
        },

        /**
         * Update existing user (admin only)
         */
        async updateUser() {
            const data = {
                username: this.userForm.username.trim(),
                role: this.userForm.role
            };

            // Only include password if provided
            if (this.userForm.password) {
                data.password = this.userForm.password;
            }

            await apiRequest(`/api/admin/users/${this.userForm.id}`, {
                method: 'PUT',
                body: JSON.stringify(data)
            });

            await this.loadData();
        },

        /**
         * Update own profile (self-service)
         */
        async updateMyAccount() {
            const data = {
                username: this.userForm.username.trim()
            };

            // Only include password if provided
            if (this.userForm.password) {
                data.password = this.userForm.password;
                data.current_password = this.userForm.current_password;
            }

            const updatedUser = await apiRequest('/api/auth/me', {
                method: 'PUT',
                body: JSON.stringify(data)
            });

            // Update local user state
            if (updatedUser) {
                this.user = {
                    id: updatedUser.id,
                    username: updatedUser.username,
                    role: updatedUser.role,
                    tenant_id: updatedUser.tenant_id
                };
            }
        },

        /**
         * Delete user with type-username confirmation (admin only)
         * @param {string} userId - User UUID
         */
        async deleteUser(userId) {
            const user = this.users.find(u => u.id === userId);
            if (!user) return;

            // Prevent deleting yourself
            if (user.id === this.user?.id) {
                this.showNotification('Cannot delete your own account', 'error');
                return;
            }

            this.showInput(
                'Confirm Delete',
                `Type "${user.username}" to confirm deletion:`,
                async (typed) => {
                    if (typed === user.username) {
                        try {
                            await apiRequest(`/api/admin/users/${userId}`, {
                                method: 'DELETE'
                            });
                            this.showUserModal = false;
                            this.showNotification('User deleted', 'success');
                            await this.loadData();
                        } catch (error) {
                            console.error('Error deleting user:', error);
                            this.showNotification(error.message || 'Delete failed', 'error');
                        }
                    } else {
                        this.showNotification('Username did not match', 'error');
                    }
                },
                '',
                null,
                (value) => {
                    if (value !== user.username) {
                        return `Type "${user.username}" exactly to confirm`;
                    }
                    return null;
                }
            );
        },

        /**
         * Update settings (preferences, sync interval, etc.)
         */
        async updateSettings() {
            try {
                // Convert Alpine Proxy to plain object (IndexedDB can't store Proxies)
                const plainSettings = JSON.parse(JSON.stringify(this.settingsForm));

                // Save settings via storage adapter
                const updated = await storage.updateSettings(plainSettings);

                // Update local settings object
                this.settings = updated;

                // Update settings form to reflect saved state
                this.settingsForm = {
                    ...updated,
                    rates: updated.rates || {}
                };

                // Restart auto-sync timer with new interval (force reset countdown)
                this.startAutoSyncTimer(true);

            } catch (error) {
                console.error('Error updating settings:', error);
                this.showNotification('Update failed', 'error');
            }
        },

        /**
         * Download backup as JSON
         *
         * Backup includes tenant_id for isolation - restores are only allowed
         * for the same tenant to prevent cross-tenant data leakage.
         */
        async downloadBackup() {
            try {
                // Gather all data with tenant isolation
                const backup = {
                    version: '1.1',
                    exported_at: new Date().toISOString(),
                    tenant_id: this.user?.tenant_id || null,
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
                link.download = `chaptr-backup-${toLocalISODate(new Date())}.json`;
                link.click();
                URL.revokeObjectURL(url);
            } catch (error) {
                console.error('Error downloading backup:', error);
                this.showNotification('Download failed', 'error');
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
                this.showNotification(`File too large (max ${maxSizeMB}MB)`, 'error');
                event.target.value = '';
                return;
            }

            this.showConfirm(
                '⚠️ Restore Backup',
                'This will OVERWRITE all existing data.\n\nAll current accounts, stories, and events will be replaced.\n\nContinue?',
                async () => {
                    try {
                        await this.performBackupRestore(file, event);
                    } catch (error) {
                        console.error('Restore error:', error);
                        this.showNotification(error.message || 'Restore failed', 'error');
                    }
                },
                'Restore',
                'danger'
            );
        },

        async performBackupRestore(file, event) {
            try {
                const text = await file.text();
                const backup = JSON.parse(text);

                // Comprehensive backup validation
                if (!backup.version || typeof backup.version !== 'string') {
                    throw new Error('Invalid backup: missing or invalid version');
                }

                // Tenant isolation check for v1.1+ backups
                // Prevents restoring another tenant's data
                if (backup.version !== '1.0' && backup.tenant_id) {
                    const currentTenantId = this.user?.tenant_id;
                    if (currentTenantId && backup.tenant_id !== currentTenantId) {
                        throw new Error('Cannot restore: backup belongs to a different tenant');
                    }
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

                this.showNotification('Backup restored', 'success');
                await this.loadData();
            } catch (error) {
                console.error('Error restoring backup:', error);
                this.showNotification('Restore failed', 'error');
            }

            event.target.value = '';
        },

        /**
         * Trigger manual sync with spinner and conflict detection
         */
        async triggerManualSync() {
            if (this.isSyncing) return;

            // DEFENSIVE FIX: Check queue before starting spinner to avoid early return bypassing minimum duration
            await this.updateSyncQueueCount();

            if (this.syncQueueCount === 0) {
                this.showNotification('Nothing to sync', 'info');
                return;
            }

            // Start spinner and track start time
            this.isSyncing = true;
            this.syncButtonSpinner = true;
            const spinnerStartTime = Date.now();

            // DEFENSIVE: Timeout guard - force sync to complete within configured timeout
            const timeoutPromise = new Promise((_, reject) => {
                setTimeout(() => reject(new Error('Sync timeout after 30s')), this.SYNC_TIMEOUT_MS);
            });

            try {
                // Perform incremental sync with timeout guard
                const syncPromise = (async () => {
                    const result = await storage.manualSync();

                    // Check for unresolved conflicts after sync (auto-resolved conflicts are suppressed)
                    const unresolvedConflicts = await db.getUnresolvedConflicts();
                    if (unresolvedConflicts.length > 0) {
                        this.showNotification(`${unresolvedConflicts.length} sync conflicts`, 'warning');
                    } else if (result.applied && result.applied > 0) {
                        this.showNotification(this.formatSyncResult(result), 'success');
                    } else {
                        this.showNotification('Already in sync', 'success');
                    }

                    // Reload data to reflect server changes
                    await this.loadData();

                    // Show conflict resolution modal if conflicts exist
                    await this.checkForConflicts();
                })();

                await Promise.race([syncPromise, timeoutPromise]);

            } catch (error) {
                console.error('Sync error:', error);
                if (error.message === 'Sync timeout after 30s') {
                    this.showNotification('Sync timeout', 'error');
                } else {
                    this.showNotification('Sync failed', 'error');
                }
            } finally {
                // Ensure spinner shows for minimum configured duration
                const elapsed = Date.now() - spinnerStartTime;
                if (elapsed < this.MIN_SPINNER_DURATION_MS) {
                    await new Promise(resolve => setTimeout(resolve, this.MIN_SPINNER_DURATION_MS - elapsed));
                }

                this.isSyncing = false;
                this.syncButtonSpinner = false;
                await this.updateSyncQueueCount(); // Refresh count

                // Reset auto-sync countdown after sync
                this.resetAutoSyncTimer();
            }
        },

        /**
         * Normalize auto_sync_interval to seconds
         *
         * Handles migration from milliseconds (old format) to seconds (new format).
         * Values > 86400 are assumed to be milliseconds and are converted.
         *
         * @param {number} value - Raw interval value from settings
         * @returns {number} - Interval in seconds (0 = off)
         */
        normalizeAutoSyncInterval(value) {
            if (!value || value <= 0) return 0;
            // If value > 86400 (1 day in seconds), assume it's milliseconds
            if (value > 86400) {
                return Math.round(value / 1000);
            }
            return value;
        },

        /**
         * Format sync interval for display
         *
         * @param {number} seconds - Interval in seconds
         * @returns {string} - Formatted interval (e.g., "1m", "5m", "1h", "1d")
         */
        formatSyncInterval(seconds) {
            if (seconds === 60) return '1m';
            if (seconds === 300) return '5m';
            if (seconds === 3600) return '1h';
            if (seconds === 86400) return '1d';
            if (seconds >= 86400) return `${Math.round(seconds / 86400)}d`;
            if (seconds >= 3600) return `${Math.round(seconds / 3600)}h`;
            if (seconds >= 60) return `${Math.round(seconds / 60)}m`;
            return `${seconds}s`;
        },

        /**
         * Format countdown for display (mm:ss or ss)
         *
         * @param {number} seconds - Remaining seconds
         * @returns {string} - Formatted countdown (e.g., "4:32" or "45")
         */
        formatCountdown(seconds) {
            if (seconds <= 0) return '';
            if (seconds < 60) return `${seconds}`;
            const mins = Math.floor(seconds / 60);
            const secs = seconds % 60;
            return `${mins}:${secs.toString().padStart(2, '0')}`;
        },

        /**
         * Format sync result for notification display
         *
         * Returns entity-aware message when single type, generic "changes" for mixed types.
         * Examples: "Synced 3 events", "Synced 1 account", "Synced 5 changes"
         *
         * @param {Object} result - Sync result with applied count and appliedByType breakdown
         * @param {number} result.applied - Total number of applied changes
         * @param {Object} result.appliedByType - Breakdown by entity type (e.g., { event: 3, account: 1 })
         * @returns {string} - Formatted message for notification
         */
        formatSyncResult(result) {
            if (!result.applied || result.applied === 0) {
                return 'Already in sync';
            }

            const typeLabels = {
                event: { singular: 'event', plural: 'events' },
                account: { singular: 'account', plural: 'accounts' },
                story: { singular: 'story', plural: 'stories' },
                recurring_rule: { singular: 'rule', plural: 'rules' },
                settings: { singular: 'settings', plural: 'settings' }
            };

            const types = Object.keys(result.appliedByType || {});

            // Single entity type: show specific label
            if (types.length === 1) {
                const type = types[0];
                const count = result.appliedByType[type];
                const labels = typeLabels[type] || { singular: type, plural: type + 's' };
                const label = count === 1 ? labels.singular : labels.plural;
                return `Synced ${count} ${label}`;
            }

            // Multiple types: use generic "changes"
            return `Synced ${result.applied} changes`;
        },

        /**
         * Get stored next sync timestamp from localStorage
         * @returns {number|null} - Timestamp in ms or null
         */
        getStoredNextSyncTime() {
            try {
                const stored = localStorage.getItem('chaptr_next_auto_sync');
                return stored ? parseInt(stored, 10) : null;
            } catch (e) {
                return null;
            }
        },

        /**
         * Store next sync timestamp in localStorage
         * @param {number} timestamp - Timestamp in ms
         */
        setStoredNextSyncTime(timestamp) {
            try {
                if (timestamp) {
                    localStorage.setItem('chaptr_next_auto_sync', timestamp.toString());
                } else {
                    localStorage.removeItem('chaptr_next_auto_sync');
                }
            } catch (e) {
                // localStorage not available
            }
        },

        /**
         * Start auto-sync timer
         *
         * Sets up periodic sync based on settings.auto_sync_interval.
         * If tab is hidden when timer fires, queues sync for when tab becomes visible.
         * Persists next sync time to localStorage for countdown continuity across refreshes.
         *
         * @param {boolean} forceReset - If true, ignores stored time and starts fresh (use when interval changes)
         */
        startAutoSyncTimer(forceReset = false) {
            this.stopAutoSyncTimer(); // Clear any existing timer

            const intervalSeconds = this.normalizeAutoSyncInterval(this.settings.auto_sync_interval);
            if (!intervalSeconds || intervalSeconds <= 0) {
                console.log('[CHAPTR] Auto-sync disabled');
                this.autoSyncCountdown = '';
                this.setStoredNextSyncTime(null);
                return;
            }

            const intervalMs = intervalSeconds * 1000;
            const now = Date.now();
            let nextSyncTime;

            if (forceReset) {
                // User changed interval - start fresh
                nextSyncTime = now + intervalMs;
                this.setStoredNextSyncTime(nextSyncTime);
                console.log(`[CHAPTR] Auto-sync interval changed to ${intervalSeconds}s`);
            } else {
                // Check if we have a stored next sync time that's still valid
                nextSyncTime = this.getStoredNextSyncTime();

                if (!nextSyncTime || nextSyncTime <= now) {
                    // Set new next sync time
                    nextSyncTime = now + intervalMs;
                    this.setStoredNextSyncTime(nextSyncTime);
                }
            }

            // Calculate initial delay (time until stored next sync)
            const initialDelay = Math.max(0, nextSyncTime - now);

            console.log(`[CHAPTR] Starting auto-sync timer: ${intervalSeconds}s (first in ${Math.round(initialDelay / 1000)}s)`);

            // Start countdown display
            this.startCountdownDisplay();

            // Use setTimeout for first sync to honor stored time, then setInterval
            const scheduleNextSync = async () => {
                // Update next sync time for future
                const newNextSyncTime = Date.now() + intervalMs;
                this.setStoredNextSyncTime(newNextSyncTime);

                // Skip if offline or already syncing
                if (!navigator.onLine || this.isSyncing) {
                    console.log('[CHAPTR] Auto-sync skipped (offline/syncing)');
                    return;
                }

                // Check if there's anything to sync
                const queueCount = await db.sync_queue.count();
                if (queueCount === 0) {
                    console.log('[CHAPTR] Auto-sync: nothing to sync');
                    return;
                }

                // If tab is hidden, queue sync for when user returns
                if (document.hidden) {
                    this.autoSyncPending = true;
                    console.log(`[CHAPTR] Auto-sync queued (${queueCount} pending, tab hidden)`);
                    return;
                }

                console.log(`[CHAPTR] Auto-sync triggered (${queueCount} pending)`);
                await this.triggerManualSync();
            };

            // First sync after initial delay
            this.autoSyncTimerId = setTimeout(async () => {
                await scheduleNextSync();

                // Then set up regular interval
                this.autoSyncTimerId = setInterval(scheduleNextSync, intervalMs);
            }, initialDelay);
        },

        /**
         * Start countdown display update interval
         */
        startCountdownDisplay() {
            this.stopCountdownDisplay();

            // Update countdown every second
            this.countdownTimerId = setInterval(() => {
                const nextSyncTime = this.getStoredNextSyncTime();
                if (!nextSyncTime) {
                    this.autoSyncCountdown = '';
                    return;
                }

                const remainingMs = nextSyncTime - Date.now();
                if (remainingMs <= 0) {
                    this.autoSyncCountdown = '';
                    return;
                }

                this.autoSyncCountdown = this.formatCountdown(Math.ceil(remainingMs / 1000));
            }, 1000);

            // Initial update
            const nextSyncTime = this.getStoredNextSyncTime();
            if (nextSyncTime) {
                const remainingMs = nextSyncTime - Date.now();
                this.autoSyncCountdown = remainingMs > 0 ? this.formatCountdown(Math.ceil(remainingMs / 1000)) : '';
            }
        },

        /**
         * Stop countdown display update interval
         */
        stopCountdownDisplay() {
            if (this.countdownTimerId) {
                clearInterval(this.countdownTimerId);
                this.countdownTimerId = null;
            }
            this.autoSyncCountdown = '';
        },

        /**
         * Stop auto-sync timer
         */
        stopAutoSyncTimer() {
            if (this.autoSyncTimerId) {
                clearInterval(this.autoSyncTimerId);
                clearTimeout(this.autoSyncTimerId); // Could be either
                this.autoSyncTimerId = null;
                console.log('[CHAPTR] Auto-sync timer stopped');
            }
            this.stopCountdownDisplay();
        },

        /**
         * Handle visibility change for auto-sync
         *
         * When tab becomes visible and sync was pending, triggers sync immediately.
         */
        async handleAutoSyncVisibilityChange() {
            if (!document.hidden && this.autoSyncPending) {
                console.log('[CHAPTR] Tab visible - triggering pending auto-sync');
                this.autoSyncPending = false;
                await this.triggerManualSync();
            }
        },

        /**
         * Reset auto-sync timer after manual sync
         *
         * Called after a successful sync to reset the countdown.
         */
        resetAutoSyncTimer() {
            const intervalSeconds = this.normalizeAutoSyncInterval(this.settings.auto_sync_interval);
            if (intervalSeconds > 0) {
                const nextSyncTime = Date.now() + (intervalSeconds * 1000);
                this.setStoredNextSyncTime(nextSyncTime);
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
            this.showConfirm(
                'Clear Sync Queue',
                'Clear all pending sync items?\n\nThis will delete unsynced entities (events, accounts, etc.) and cannot be undone.',
                async () => {
                    try {
                        const count = await storage.clearSyncQueue();
                        await this.updateSyncQueueCount();

                        // Recalculate projection to reflect deletion of unsynced entities
                        // This ensures drift updates correctly
                        if (this.currentScreen === 'dashboard') {
                            await this.updateProjectionRows();
                        }

                        this.showNotification('Queue cleared', 'success');
                    } catch (error) {
                        console.error('Clear queue error:', error);
                        this.showNotification('Clear failed', 'error');
                    }
                },
                'Clear',
                'danger'
            );
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

                // Clear all local data (preserves users and settings)
                await db.clearAllData();

                // Clear reactive state immediately
                this.accounts = [];
                this.stories = [];
                this.events = [];
                this.projectionRows = [];

                // Trigger full sync to re-download all data
                await this.fullSync();
            } catch (error) {
                console.error('[CHAPTR] Clear database error:', error);
                this.showNotification('Reset failed', 'error');
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

                // Trigger full sync
                await this.fullSync();
            } catch (error) {
                console.error('[CHAPTR] Clear database + changelog error:', error);
                this.showNotification('Reset failed', 'error');
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
            this.showPassword(
                '🔴 NUCLEAR RESET',
                'This will permanently delete:\n' +
                '• ALL accounts, stories, events (all users)\n' +
                '• ALL change log history\n' +
                '• ALL conflicts\n\n' +
                'Only users and settings are preserved.\n\n' +
                'Enter password to confirm:',
                async (password) => {
                    try {
                        this.isSyncing = true;
                        this.showNotification('Resetting...', 'info');

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

                        // Clear local database
                        await db.clearAllData();
                        this.accounts = [];
                        this.stories = [];
                        this.events = [];
                        this.projectionRows = [];

                        // Resync (will get empty state)
                        await this.fullSync();
                    } catch (error) {
                        console.error('[CHAPTR] Nuclear reset error:', error);
                        this.showNotification(error.message || 'Nuclear reset failed', 'error');
                    } finally {
                        this.isSyncing = false;
                        this.showDatabaseToolsModal = false;
                    }
                },
                'Enter admin password'
            );
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
                stories: 'Story',
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
                stories: () => this.openStoryModal(),
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
            const today = toLocalISODate(new Date());
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
                        ? parseISODate(story.end_date) - parseISODate(story.start_date)
                        : Infinity;
                    const smallestRange = smallest.end_date
                        ? parseISODate(smallest.end_date) - parseISODate(smallest.start_date)
                        : Infinity;

                    return storyRange < smallestRange ? story : smallest;
                });
            }

            // Open modal with auto-selected story (or baseline if none)
            if (selectedStory) {
                this.openEventModalForStory(selectedStory.id);
            } else {
                // No story covers today - create baseline event
                this.openEventModal();
            }
        },

        /**
         * Add event to current story (projection context)
         */
        addEventToStory() {
            if (this.currentView === 'all' || this.currentView === 'baseline') {
                this.showNotification('Select story first', 'error');
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
            // Reset validation errors
            ValidationHelpers.resetFormErrors(this.balanceFormErrors);

            // Pre-select first account if only one exists
            const activeAccounts = this.accounts.filter(a => !a.is_archived);

            this.balanceForm = {
                account_id: activeAccounts.length === 1 ? activeAccounts[0].id : '',
                projected_balance: 0,
                actual_balance: '',  // Empty so user can type immediately without deleting
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
            const today = toLocalISODate(new Date());
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

            // If balance has been manually updated, start from that snapshot
            // and only include events AFTER the update
            if (account.balance_updated_at) {
                const balanceDate = account.balance_updated_at.split('T')[0]; // YYYY-MM-DD

                let balance = parseFloat(account.current_balance || 0);

                // Add events that occurred AFTER the last balance update
                const accountEvents = this.events.filter(e =>
                    e.account_id === accountId &&
                    e.event_date > balanceDate &&
                    e.event_date <= date &&
                    !e.is_opening_balance // Never include opening balance when starting from manual update
                );

                for (const event of accountEvents) {
                    balance += event.amount;
                }

                return balance;
            }

            // No manual update yet - calculate from opening balance event
            let balance = 0;

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
         * Calculate pending drifts (REMOVED - queue-as-state architecture)
         *
         * Old architecture: Virtual drift rows based on pending_reconciliation flag
         * New architecture: Real optimistic adjustment events created immediately
         *
         * With queue-as-state, adjustment events are REAL events in Dexie with
         * _optimistic: true flag. No virtual rows or pending_reconciliation needed.
         *
         * Keeping stub for backward compatibility with existing callers.
         * @returns {Array} Empty array (no virtual drifts)
         */
        calculatePendingDrifts() {
            return []; // Queue-as-state: Real events, not virtual rows
        },

        /**
         * Save balance update - creates optimistic adjustment event (queue-as-state)
         * Server may override with authoritative version via conflict resolution
         */
        async saveBalanceUpdate() {
            // Reset errors
            ValidationHelpers.resetFormErrors(this.balanceFormErrors);

            // Custom dropdown validation for account selection
            if (!ValidationHelpers.validateCustomDropdown(
                this.balanceForm.account_id,
                'account_id',
                this.balanceFormErrors,
                true
            )) {
                this.showNotification('Please select an account', 'error');
                return;
            }

            // Validate actual_balance is provided
            if (this.balanceForm.actual_balance === null ||
                this.balanceForm.actual_balance === undefined ||
                this.balanceForm.actual_balance === '') {
                this.balanceFormErrors.actual_balance = true;
                this.showNotification('Please enter the actual balance', 'error');
                return;
            }

            // If drift is zero, no adjustment needed
            if (this.balanceForm.drift === 0) {
                this.showNotification('Balance matches projection - no adjustment needed', 'info');
                this.showBalanceModal = false;
                return;
            }

            try {
                const account = this.accounts.find(a => a.id === this.balanceForm.account_id);
                if (!account) {
                    this.showNotification('Account not found', 'error');
                    return;
                }

                const drift = this.balanceForm.drift;
                const now = new Date().toISOString();
                const today = toLocalISODate(new Date());

                // Queue-as-state: Create REAL adjustment event marked as optimistic
                // Server will reconcile and may override with authoritative version
                const adjustmentEvent = {
                    id: generateUUID(),
                    event_date: today,
                    description: 'balance adjustment',
                    amount: drift,
                    currency: account.currency,
                    rate_to_base: this.settings.rates?.[account.currency] || 1.0,
                    account_id: account.id,
                    story_id: null,
                    is_baseline: true,
                    is_hypothetical: false,
                    is_opening_balance: false,
                    is_auto_adjustment: true,
                    is_transfer: false,
                    recurring_rule_id: null,
                    created_at: now,
                    updated_at: now
                };

                // Apply as derived change with optimistic flag
                await applyDerivedChange(
                    {
                        entity_type: 'event',
                        entity_id: adjustmentEvent.id,
                        action: 'create',
                        data: adjustmentEvent,
                        base_updated_at: null
                    },
                    {
                        _derived_from: 'balance_reconciliation',
                        dependencies: [account.id],
                        _optimistic: true  // Server may override with authoritative version
                    }
                );

                // Update account balance and set pending_reconciliation flag
                // Server will see this flag during reconciliation phase and create authoritative adjustment
                const updates = {
                    current_balance: parseFloat(this.balanceForm.actual_balance),
                    balance_updated_at: now,
                    updated_at: now,
                    pending_reconciliation: true  // Trigger server-side adjustment creation
                };

                await storage.updateAccount(account.id, updates);

                this.showBalanceModal = false;

                // Reload to show adjustment event in projection
                await this.loadData();
                await this.updateDashboardProjection();

                this.showNotification('Balance updated', 'success');

            } catch (error) {
                console.error('Error updating balance:', error);
                this.showNotification('Update failed', 'error');
            }
        },

        /**
         * Edit story funding (projection context)
         */
        editFunding() {
            if (this.currentView === 'all' || this.currentView === 'baseline') {
                this.showNotification('Select story first', 'error');
                return;
            }

            const story = this.stories.find(s => s.id === this.currentView);
            this.showNotification('Coming soon', 'info');
        },


        // ===== DATE HELPER FUNCTIONS =====

        /**
         * Set date field to yesterday
         * @param {string} formField - Form field path (e.g., 'eventForm.event_date')
         */
        setDateToYesterday(formField) {
            const date = new Date();
            date.setDate(date.getDate() - 1);
            const [form, field] = formField.split('.');
            this[form][field] = toLocalISODate(date);
        },

        /**
         * Set date field to today
         * @param {string} formField - Form field path (e.g., 'eventForm.event_date')
         */
        setDateToToday(formField) {
            const [form, field] = formField.split('.');
            this[form][field] = toLocalISODate(new Date());
        },

        /**
         * Set date field to tomorrow
         * @param {string} formField - Form field path (e.g., 'eventForm.event_date')
         */
        setDateToTomorrow(formField) {
            const date = new Date();
            date.setDate(date.getDate() + 1);
            const [form, field] = formField.split('.');
            this[form][field] = toLocalISODate(date);
        },

        // ===== EVENT MODAL METHODS =====

        /**
         * Open event modal for adding new event (dashboard context - baseline auto-assign)
         */
        openEventModal() {
            const today = toLocalISODate(new Date());

            // Reset validation errors
            this.eventFormErrors.account = false;

            this.eventForm = {
                id: null,
                event_date: today,
                description: '',
                amount: 0,
                amountIsNegative: true, // Default to expense (deduction)
                account_id: '', // Will resolve via hierarchy
                currency: this.settings.base_currency || 'GBP',
                story_id: '', // Empty = baseline
                is_baseline: true,
                is_hypothetical: false,

                // Recurring fields
                is_recurring: false,
                frequency: '',
                day: null,
                start_date: today,
                end_date: '',
                anniversary_date: ''
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
                this.showNotification('Story not found', 'error');
                return;
            }

            // Reset validation errors
            this.eventFormErrors.account = false;

            const today = toLocalISODate(new Date());

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
                id: null,
                event_date: defaultDate,
                description: '',
                amount: 0,
                amountIsNegative: true, // Default to expense (deduction)
                account_id: story.default_account_id || '',
                currency: story.display_currency || (defaultAccount ? defaultAccount.currency : null) || this.settings.base_currency || 'GBP',
                story_id: storyId,
                is_baseline: false,
                is_hypothetical: false,

                // Recurring fields
                is_recurring: false,
                frequency: '',
                day: null,
                start_date: defaultDate,
                end_date: '',
                anniversary_date: ''
            };

            this.showEventModal = true;
        },

        /**
         * View event details for editing (opens edit modal)
         * @param {string} eventId - Event UUID
         */
        async viewEventDetails(eventId) {
            if (!eventId) {
                console.error('viewEventDetails called without eventId');
                return;
            }

            const event = this.events.find(e => e.id === eventId);
            if (!event) {
                console.error('Event not found:', eventId);
                return;
            }

            // Queue-as-state: All recurring instances are real events (no phantom conversion needed)
            // Normal event editing
            this.eventForm = {
                id: event.id,
                event_date: event.event_date,
                description: event.description,
                amount: Math.abs(event.amount), // Store as absolute value
                amountIsNegative: event.amount < 0, // Track sign separately
                account_id: event.account_id,
                currency: event.currency,
                story_id: event.story_id || '',
                is_baseline: event.is_baseline,
                is_hypothetical: event.is_hypothetical,
                updated_at: event.updated_at,

                // Recurring fields (always false for event editing)
                is_recurring: false,
                frequency: '',
                day: null,
                start_date: event.event_date,
                end_date: '',
                anniversary_date: ''
            };

            this.showEventModal = true;
        },

        /**
         * View recurring rule details (opens for editing)
         * @param {string} recurringRuleId - Recurring rule UUID
         */
        async viewRecurringRule(recurringRuleId) {
            if (!recurringRuleId) {
                console.error('viewRecurringRule called without recurringRuleId');
                return;
            }

            const rule = await db.recurring_rules.get(recurringRuleId);

            if (rule) {
                await this.editRecurringRule(rule);
            } else {
                this.showNotification('Recurring rule not found', 'error');
            }
        },

        /**
         * Edit recurring rule (opens modal with rule data)
         * @param {Object} rule - Recurring rule object
         */
        async editRecurringRule(rule) {
            // Populate anniversary_date for annual recurring rules
            let anniversaryDate = '';
            if (rule.frequency === 'annual' && rule.start_date) {
                // Use start_date as the anniversary date (contains month/day)
                anniversaryDate = rule.start_date;
            }

            // Populate form with existing rule data
            this.eventForm = {
                id: rule.id,
                event_date: '',  // Not used for recurring
                description: rule.description,
                amount: Math.abs(rule.amount), // Store as absolute value
                amountIsNegative: rule.amount < 0, // Track sign separately
                account_id: rule.account_id,
                currency: rule.currency,
                story_id: '',  // Recurring rules don't have stories
                is_baseline: false,  // Not used for recurring
                is_hypothetical: false,  // Not used for recurring
                updated_at: rule.updated_at,

                // Set recurring mode
                is_recurring: true,
                frequency: rule.frequency,
                day: rule.day,
                start_date: rule.start_date,
                end_date: rule.end_date || '',
                anniversary_date: anniversaryDate
            };

            this.showEventModal = true;
        },

        /**
         * Save event (create or update) with validation
         * Uses HTML5 Constraint Validation API + custom business logic
         */
        async saveEvent() {
            // Reset validation errors
            ValidationHelpers.resetFormErrors(this.eventFormErrors);

            // HTML5 validation
            const form = this.$refs.eventFormElement;
            if (!form) {
                console.error('Event form ref not found');
                return;
            }

            if (!ValidationHelpers.validateHTML5(form, this.eventFormErrors)) {
                const count = ValidationHelpers.countErrors(this.eventFormErrors);
                this.showNotification(`Please fix ${count} field(s)`, 'error');
                return;
            }

            // Custom business logic validations (beyond HTML5)
            if (this.accounts.length === 0) {
                this.eventFormErrors.account = true;
                this.showNotification('No accounts exist. Create an account before creating events.', 'error');
                return;
            }

            // Validation for Simple Events
            if (!this.eventForm.is_recurring) {
                if (!this.eventForm.event_date) {
                    this.showNotification('Date required', 'error');
                    return;
                }
            }

            // Validation for Recurring Events
            if (this.eventForm.is_recurring) {
                if (!this.eventForm.frequency) {
                    this.showNotification('Frequency required for recurring events', 'error');
                    return;
                }

                if (!this.eventForm.day) {
                    this.showNotification('Day required for recurring events', 'error');
                    return;
                }

                if (!this.eventForm.start_date) {
                    this.showNotification('Start date required for recurring events', 'error');
                    return;
                }

                // Validate day range based on frequency
                if (this.eventForm.frequency === 'weekly' && (this.eventForm.day < 1 || this.eventForm.day > 7)) {
                    this.showNotification('Day must be 1-7 for weekly events', 'error');
                    return;
                }

                if (this.eventForm.frequency === 'monthly' && (this.eventForm.day < 1 || this.eventForm.day > 31)) {
                    this.showNotification('Day must be 1-31 for monthly events', 'error');
                    return;
                }

                if (this.eventForm.frequency === 'annual' && (this.eventForm.day < 1 || this.eventForm.day > 31)) {
                    this.showNotification('Day must be 1-31 for annual events', 'error');
                    return;
                }

                // Route to recurring rule creation or update
                const isEdit = !!this.eventForm.id;
                try {
                    if (isEdit) {
                        await this.updateRecurringRule();
                    } else {
                        await this.createRecurringRule();
                    }
                    this.showEventModal = false;
                } catch (error) {
                    console.error('Error saving recurring rule:', error);
                    this.showNotification('Save failed', 'error');
                }
                return;
            }

            // Validation: Event date within story range
            if (this.eventForm.story_id && this.eventForm.story_id !== 'auto') {
                const story = this.stories.find(s => s.id === this.eventForm.story_id);
                if (story) {
                    const eventDate = this.eventForm.event_date;

                    if (eventDate < story.start_date) {
                        this.showNotification('Date outside story', 'error');
                        return;
                    }

                    if (story.end_date && eventDate > story.end_date) {
                        this.showNotification('Date outside story', 'error');
                        return;
                    }
                }
            }

            // Validation: Baseline XOR Story
            if (this.eventForm.is_baseline && this.eventForm.story_id) {
                this.showNotification('Baseline/story conflict', 'error');
                return;
            }

            // Validation: Account resolution
            const resolvedAccountId = this.resolveAccountId(
                this.eventForm.account_id || null,
                this.eventForm.story_id || null
            );

            if (!resolvedAccountId) {
                this.showNotification('Account required', 'error');
                return;
            }

            try {
                const isEdit = !!this.eventForm.id;

                // Apply sign based on amountIsNegative flag
                const signedAmount = this.eventForm.amountIsNegative
                    ? -Math.abs(parseFloat(this.eventForm.amount))
                    : Math.abs(parseFloat(this.eventForm.amount));

                const eventData = {
                    event_date: this.eventForm.event_date,
                    description: this.eventForm.description.trim(),
                    amount: signedAmount,
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

                // Refresh projection to show new/updated event
                await this.updateDashboardProjection();

            } catch (error) {
                console.error('Error saving event:', error);
                this.showNotification('Save failed', 'error');
            }
        },

        /**
         * Delete event from modal with confirmation
         */
        async deleteEventFromModal() {
            this.showConfirm(
                'Delete Event',
                `Delete event "${this.eventForm.description}"?\n\nThis will affect all projections.`,
                async () => {
                    try {
                        await this.deleteEvent(this.eventForm.id);
                        this.showEventModal = false;
                    } catch (error) {
                        console.error('Error deleting event:', error);
                        this.showNotification('Delete failed', 'error');
                    }
                },
                'Delete',
                'danger'
            );
        },

        /**
         * Create recurring rule from eventForm
         */
        async createRecurringRule() {
            // Validation: Account resolution
            const resolvedAccountId = this.resolveAccountId(
                this.eventForm.account_id || null,
                null  // Recurring rules don't have stories
            );

            if (!resolvedAccountId) {
                this.showNotification('Account required', 'error');
                throw new Error('No account resolved');
            }

            // Apply sign based on amountIsNegative flag
            const signedAmount = this.eventForm.amountIsNegative
                ? -Math.abs(parseFloat(this.eventForm.amount))
                : Math.abs(parseFloat(this.eventForm.amount));

            const ruleData = {
                description: this.eventForm.description.trim(),
                amount: signedAmount,
                currency: this.eventForm.currency || this.settings.base_currency || 'GBP',
                account_id: resolvedAccountId,
                frequency: this.eventForm.frequency,
                day: parseInt(this.eventForm.day),
                start_date: this.eventForm.start_date,
                end_date: this.eventForm.end_date || null
            };

            // Use storage adapter (handles all 3 modes)
            const createdRule = await storage.createRecurringRule(ruleData);

            // Queue-as-state: Generate recurring instances for ±30 days
            // Lookup account to determine baseline status
            const account = await db.accounts.get(resolvedAccountId);
            const isBaseline = account ? (account.is_default || false) : false;

            // Generate instances
            const instances = generateRecurringInstances(createdRule, this.settings, isBaseline, 30);

            if (instances.length > 0) {
                // Convert to change objects for batch application
                const changes = instances.map(instanceData => ({
                    entity_type: 'event',
                    entity_id: instanceData.id,
                    action: 'create',
                    data: instanceData,
                    base_updated_at: null
                }));

                // Apply all instances as derived changes
                await applyDerivedChangesBatch(changes, {
                    _derived_from: 'recurring_rule_creation',
                    dependencies: [createdRule.id]
                });
            }

            this.showNotification('Recurring rule created', 'success');

            // Reload data to show new rule and generated events
            await this.loadData();
            await this.updateDashboardProjection();
        },

        /**
         * Update recurring rule with instance regeneration
         */
        async updateRecurringRule() {
            // Validation: Account resolution
            const resolvedAccountId = this.resolveAccountId(
                this.eventForm.account_id || null,
                null  // Recurring rules don't have stories
            );

            if (!resolvedAccountId) {
                this.showNotification('Account required', 'error');
                throw new Error('No account resolved');
            }

            // Apply sign based on amountIsNegative flag
            const signedAmount = this.eventForm.amountIsNegative
                ? -Math.abs(parseFloat(this.eventForm.amount))
                : Math.abs(parseFloat(this.eventForm.amount));

            const ruleData = {
                description: this.eventForm.description.trim(),
                amount: signedAmount,
                currency: this.eventForm.currency || this.settings.base_currency || 'GBP',
                account_id: resolvedAccountId,
                frequency: this.eventForm.frequency,
                day: parseInt(this.eventForm.day),
                start_date: this.eventForm.start_date,
                end_date: this.eventForm.end_date || null
            };

            // Use storage adapter (handles all 3 modes)
            const updatedRule = await storage.updateRecurringRule(this.eventForm.id, ruleData);

            // CRITICAL FIX: Check if rule still exists (could be deleted server-side during conflict)
            if (!updatedRule) {
                this.showNotification('Recurring rule was deleted', 'error');
                this.showEventModal = false;
                await this.loadData();
                return;
            }

            // Queue-as-state: Delete future unedited instances and regenerate
            const today = toLocalISODate(new Date());

            // Find future unedited instances for this rule
            const futureInstances = await db.events
                .where('recurring_rule_id').equals(this.eventForm.id)
                .and(e => e.event_date >= today)
                .and(e => e.created_at === e.updated_at)  // Unedited only
                .toArray();

            // Delete future unedited instances
            for (const instance of futureInstances) {
                await db.events.delete(instance.id);
                await db.sync_queue.where({ entity_id: instance.id }).delete();
            }

            // Regenerate instances for ±30 days
            const account = await db.accounts.get(resolvedAccountId);
            const isBaseline = account ? (account.is_default || false) : false;

            const instances = generateRecurringInstances(updatedRule, this.settings, isBaseline, 30);

            if (instances.length > 0) {
                // Convert to change objects for batch application
                const changes = instances.map(instanceData => ({
                    entity_type: 'event',
                    entity_id: instanceData.id,
                    action: 'create',
                    data: instanceData,
                    base_updated_at: null
                }));

                // Apply all instances as derived changes
                await applyDerivedChangesBatch(changes, {
                    _derived_from: 'recurring_rule_creation',
                    dependencies: [updatedRule.id]
                });
            }

            this.showNotification('Recurring rule updated', 'success');

            // Reload data to show updated rule and regenerated events
            await this.loadData();
            await this.updateDashboardProjection();
        },

        /**
         * Delete recurring rule from modal with confirmation
         */
        async deleteRecurringRuleFromModal() {
            if (!this.eventForm.id) return;

            try {
                // Calculate how many future events will be deleted
                const today = toLocalISODate(new Date());
                const futureCount = await db.events.where('recurring_rule_id')
                    .equals(this.eventForm.id)
                    .and(e => e.event_date >= today)
                    .and(e => e.created_at === e.updated_at)  // Unedited only
                    .count();

                const message = futureCount > 0
                    ? `Delete this recurring rule and ${futureCount} future unedited event(s)? Past events and manually edited events will be preserved.`
                    : `Delete this recurring rule? (No future events to remove)`;

                this.showConfirm(
                    'Delete Recurring Rule',
                    message,
                    async () => {
                        try {
                            // Use storage adapter (handles all 3 modes)
                            await storage.deleteRecurringRule(this.eventForm.id);

                            // Queue-as-state: Delete future unedited instances locally
                            // (preserves past instances and manually edited future instances)
                            await this.deleteFutureRecurringEvents(this.eventForm.id);

                            this.showNotification('Recurring rule deleted', 'success');
                            this.showEventModal = false;
                            await this.loadData();
                            await this.updateDashboardProjection();
                        } catch (error) {
                            console.error('Error deleting recurring rule:', error);
                            this.showNotification('Delete failed', 'error');
                        }
                    },
                    'Delete',
                    'danger'
                );
            } catch (error) {
                console.error('Error calculating future events:', error);
                this.showNotification('Error preparing delete', 'error');
            }
        },

        /**
         * Delete future unedited recurring events for a rule
         * @param {string} recurringRuleId - Recurring rule UUID
         */
        async deleteFutureRecurringEvents(recurringRuleId) {
            const today = toLocalISODate(new Date());

            // Get future unedited events
            const futureEvents = await db.events.where('recurring_rule_id')
                .equals(recurringRuleId)
                .and(e => e.event_date >= today)
                .and(e => e.created_at === e.updated_at)
                .toArray();

            // Delete each one
            for (const event of futureEvents) {
                await db.events.delete(event.id);
                // Queue deletion for sync
                await db.queueChange('event', event.id, 'delete', null, event.updated_at);
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
         * Get default account name for event form hint
         * Returns the name of the global default account or null if none exists
         */
        getDefaultAccountName() {
            const defaultAccount = this.accounts.find(a => a.is_default && !a.is_archived);
            return defaultAccount ? defaultAccount.name : null;
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
         * Format datetime for conflict display
         * @param {string} dateTimeStr - ISO datetime string
         * @returns {string} Formatted datetime (e.g., "Jan 15, 14:30")
         */
        formatDateTime(dateTimeStr) {
            if (!dateTimeStr) return '';
            const date = new Date(dateTimeStr);
            if (isNaN(date.getTime())) return '';

            const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                           'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
            const month = months[date.getMonth()];
            const day = date.getDate();
            const hours = String(date.getHours()).padStart(2, '0');
            const minutes = String(date.getMinutes()).padStart(2, '0');

            return `${month} ${day}, ${hours}:${minutes}`;
        },

        /**
         * Determine if version is newer based on updated_at timestamp
         * @param {object} version - Version object with updated_at field
         * @param {object} otherVersion - Other version to compare against
         * @returns {boolean} True if this version is newer
         */
        isNewerVersion(version, otherVersion) {
            if (!version?.updated_at || !otherVersion?.updated_at) return false;
            const versionTime = new Date(version.updated_at).getTime();
            const otherTime = new Date(otherVersion.updated_at).getTime();
            return versionTime > otherTime;
        },

        /**
         * Check if a specific field differs between conflict versions
         * Used for inline highlighting in conflict modals
         * @param {string} fieldKey - The field name to compare
         * @returns {boolean} True if values differ
         */
        isConflictFieldDifferent(fieldKey) {
            if (!this.currentConflict) return false;
            const server = this.currentConflict.server_version;
            const client = this.currentConflict.client_version;
            if (!server || !client) return false;

            const serverVal = server[fieldKey];
            const clientVal = client[fieldKey];

            // Handle null/undefined equivalence
            const isNullish1 = serverVal === null || serverVal === undefined;
            const isNullish2 = clientVal === null || clientVal === undefined;
            if (isNullish1 && isNullish2) return false;
            if (isNullish1 !== isNullish2) return true;

            // Compare values
            return serverVal !== clientVal;
        },

        /**
         * Format relative time (wrapper for utils)
         */
        formatRelativeTime(date) {
            return formatRelativeTime(date);
        },

        /**
         * Trigger reconciliation for all pending accounts
         */
        /**
         * Trigger reconciliation (DEPRECATED - queue-as-state architecture)
         *
         * Old architecture: Frontend set pending_reconciliation flag, triggered server reconciliation
         * New architecture: Frontend creates optimistic adjustment events, server processes during sync
         *
         * Keeping stub for backward compatibility. Can be removed entirely.
         */
        async triggerReconciliation() {
            // DEPRECATED: Queue-as-state handles this via optimistic events
            return;
        },

        /**
         * Check for unresolved conflicts on app load (Task 110)
         */
        async checkForConflicts() {
            this.conflicts = await db.getUnresolvedConflicts();

            if (this.conflicts.length > 0) {

                // Enrich conflicts with full entity data from IndexedDB
                // This fixes the issue where client_version may only contain partial update data
                for (const conflict of this.conflicts) {
                    // For edit_edit conflicts, client_version might be partial update data
                    // Try to get full entity from IndexedDB to display complete information
                    if (conflict.conflict_type === 'edit_edit' && conflict.entity_id) {
                        let fullEntity = null;

                        if (conflict.entity_type === 'event') {
                            fullEntity = await db.events.get(conflict.entity_id);
                        } else if (conflict.entity_type === 'account') {
                            fullEntity = await db.accounts.get(conflict.entity_id);
                        } else if (conflict.entity_type === 'story') {
                            fullEntity = await db.stories.get(conflict.entity_id);
                        }

                        if (fullEntity) {
                            // Merge full entity data with client_version to ensure all fields are present
                            conflict.client_version = { ...fullEntity, ...conflict.client_version };
                        }
                    }
                    // Note: server_version should already be complete from backend
                }

                this.currentConflictIndex = 0;
                this.currentConflict = this.conflicts[0];
                this.showConflictModal = true;
            }
        },

        /**
         * Resolve conflict by choosing version (Tasks 115-119)
         */
        async resolveConflict(choice) {
            if (!this.currentConflict) return;

            const conflict = this.currentConflict;

            // Task 115: Determine selected version
            let selectedVersion;
            if (choice === 'keep_mine') {
                selectedVersion = conflict.client_version;
            } else {
                selectedVersion = conflict.server_version;
            }

            try {
                // Task 116: Update local Dexie with selected version
                if (selectedVersion) {
                    // CRITICAL: When resolving conflicts, use server's current timestamp as base
                    // to tell server "I know your current version, overwrite it with my choice"
                    const baseUpdatedAt = conflict.server_version?.updated_at;

                    // CRITICAL: For "Keep Theirs", preserve server timestamp
                    // For "Keep Mine", use NEW timestamp to ensure monotonic increasing timestamps
                    const resolvedTimestamp = choice === 'keep_theirs'
                        ? selectedVersion.updated_at  // Keep server's timestamp
                        : new Date().toISOString();   // Fresh timestamp for client version

                    // Ensure object has 'id' field (Dexie primary key)
                    // Backend conflicts use MongoDB _id, need to convert
                    // Also serialize MongoDB types (Decimal128, ObjectId) to plain JS values
                    const entityData = {
                        ...selectedVersion,
                        id: selectedVersion.id || conflict.entity_id,  // Use entity_id as fallback
                        updated_at: resolvedTimestamp
                    };

                    // Entity-specific field serialization
                    if (conflict.entity_type === 'event') {
                        // Convert MongoDB Decimal128 to number for events
                        entityData.amount = parseFloat(selectedVersion.amount);
                        entityData.rate_to_base = parseFloat(selectedVersion.rate_to_base || 1.0);
                        // Ensure IDs are strings (convert MongoDB ObjectId if needed)
                        entityData.account_id = selectedVersion.account_id ? String(selectedVersion.account_id) : null;
                        entityData.story_id = selectedVersion.story_id ? String(selectedVersion.story_id) : null;
                        entityData.recurring_rule_id = selectedVersion.recurring_rule_id ? String(selectedVersion.recurring_rule_id) : null;
                    } else if (conflict.entity_type === 'account') {
                        // Convert MongoDB Decimal128 to number for accounts
                        entityData.current_balance = parseFloat(selectedVersion.current_balance);
                        entityData.rate_to_base = parseFloat(selectedVersion.rate_to_base || 1.0);
                    } else if (conflict.entity_type === 'story') {
                        // Stories may have funding_amount and goal_amount as Decimal128
                        if (selectedVersion.funding_amount) {
                            entityData.funding_amount = parseFloat(selectedVersion.funding_amount);
                        }
                        if (selectedVersion.goal_amount) {
                            entityData.goal_amount = parseFloat(selectedVersion.goal_amount);
                        }
                        // Ensure IDs are strings
                        entityData.default_account_id = selectedVersion.default_account_id ? String(selectedVersion.default_account_id) : null;
                    }

                    // Remove MongoDB _id field if present (not needed in Dexie)
                    delete entityData._id;

                    // Update entity in appropriate Dexie table
                    if (conflict.entity_type === 'event') {
                        await db.events.put(entityData);
                    } else if (conflict.entity_type === 'account') {
                        await db.accounts.put(entityData);
                    } else if (conflict.entity_type === 'story') {
                        await db.stories.put(entityData);
                    }

                    // CRITICAL: Clear all existing queue items for this entity first
                    // Multiple edits before sync create multiple queue items, all conflicting
                    // We must clear them before queueing the resolution
                    await db.sync_queue
                        .where({ entity_type: conflict.entity_type, entity_id: conflict.entity_id })
                        .delete();

                    // Task 117: Queue resolution for sync ONLY if keeping client version
                    // If keeping server version, server already has it - no need to sync back
                    if (choice === 'keep_mine') {
                        await db.queueChange(
                            conflict.entity_type,
                            conflict.entity_id,
                            'update',
                            entityData,  // Use serialized version, not original
                            baseUpdatedAt // Use server's timestamp to avoid conflict detection
                        );
                    }
                    // If keeping server version, no sync needed - just resolved locally
                } else {
                    // Selected version is null (delete case - keep_mine on delete/edit conflict)
                    // Null guard: Use server version's timestamp if it exists
                    const baseUpdatedAt = conflict.server_version?.updated_at || conflict.client_version?.updated_at;

                    // Delete from appropriate Dexie table
                    if (conflict.entity_type === 'event') {
                        await db.events.delete(conflict.entity_id);
                    } else if (conflict.entity_type === 'account') {
                        await db.accounts.delete(conflict.entity_id);
                    } else if (conflict.entity_type === 'story') {
                        await db.stories.delete(conflict.entity_id);
                    }

                    // CRITICAL: Clear all existing queue items for this entity first
                    await db.sync_queue
                        .where({ entity_type: conflict.entity_type, entity_id: conflict.entity_id })
                        .delete();

                    await db.queueChange(
                        conflict.entity_type,
                        conflict.entity_id,
                        'delete',
                        null,
                        baseUpdatedAt
                    );
                }

                // Task 118: Mark conflict as resolved
                await db.resolveConflict(conflict.id);

                // Task 119: Process next conflict if multiple exist
                this.currentConflictIndex++;
                if (this.currentConflictIndex < this.conflicts.length) {
                    this.currentConflict = this.conflicts[this.currentConflictIndex];
                } else {
                    // All conflicts resolved
                    this.closeConflictModal();
                    this.showNotification('All conflicts resolved', 'success');

                    // Reload data to reflect changes
                    await this.loadData();
                    await this.updateDashboardProjection();

                    // Trigger sync to send resolved changes
                    await this.manualSync();
                }
            } catch (error) {
                console.error('Error resolving conflict:', error);
                this.showNotification('Resolution failed', 'error');
            }
        },

        /**
         * Close conflict resolution modal
         */
        closeConflictModal() {
            this.showConflictModal = false;
            this.currentConflict = null;
            this.conflicts = [];
            this.currentConflictIndex = 0;
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

            // Positive drift (more money than expected) = green
            // Negative drift (less money than expected) = red
            return drift >= 0 ? 'positive' : 'negative';
        },

        /**
         * Format drift amount with directional arrow
         * Shows difference between accounts total and projected
         */
        formatDrift() {
            const drift = this.accountsTotal - this.projectionToday;
            const arrow = drift >= 0 ? '↑' : '↓';
            return arrow + ' ' + formatCurrency(Math.abs(drift), this.settings.base_currency);
        },

        // ===== NOTIFICATION SYSTEM =====

        /**
         * Show inline notification in header
         * @param {string} message - Short message (~3 words max)
         * @param {string} type - Type: 'info' | 'success' | 'warning' | 'error'
         * @param {number} duration - Duration in ms (default: 10000)
         */
        showNotification(message, type = 'info', duration = 10000) {
            // Clear existing timeout
            if (this.notificationTimeout) {
                clearTimeout(this.notificationTimeout);
                this.notificationTimeout = null;
            }

            // Set new notification (replaces previous)
            this.currentNotification = { message, type };

            // Auto-dismiss
            this.notificationTimeout = setTimeout(() => {
                this.currentNotification = null;
                this.notificationTimeout = null;
            }, duration);
        },

        /**
         * Clear notification immediately
         */
        clearNotification() {
            if (this.notificationTimeout) {
                clearTimeout(this.notificationTimeout);
                this.notificationTimeout = null;
            }
            this.currentNotification = null;
        },

        // ===== MODAL SYSTEM =====

        /**
         * Show confirmation modal
         * @param {string} title - Modal title
         * @param {string} message - Confirmation message (supports newlines)
         * @param {function} onConfirm - Callback function when confirmed
         * @param {string} confirmText - Text for confirm button (default: 'Confirm')
         * @param {string} confirmStyle - Button style: 'primary' or 'danger' (default: 'primary')
         */
        showConfirm(title, message, onConfirm, confirmText = 'Confirm', confirmStyle = 'primary') {
            this.confirmModalData = {
                title,
                message,
                confirmText,
                confirmStyle,
                onConfirm
            };
            this.showConfirmModal = true;
        },

        /**
         * Execute confirmation action and close modal
         */
        confirmAction() {
            if (this.confirmModalData.onConfirm) {
                this.confirmModalData.onConfirm();
            }
            this.closeConfirmModal();
        },

        /**
         * Close confirmation modal and reset state
         */
        closeConfirmModal() {
            this.showConfirmModal = false;
            this.confirmModalData = {
                title: '',
                message: '',
                confirmText: 'Confirm',
                confirmStyle: 'primary',
                onConfirm: null
            };
        },

        /**
         * Show input modal
         * @param {string} title - Modal title
         * @param {string} message - Instruction message
         * @param {function} onSubmit - Callback function with input value
         * @param {string} placeholder - Input placeholder text
         * @param {string} pattern - Regex pattern for HTML validation
         * @param {function} validator - Custom validation function (returns error message or null)
         */
        showInput(title, message, onSubmit, placeholder = '', pattern = null, validator = null) {
            this.inputModalData = {
                title,
                message,
                placeholder,
                inputValue: '',
                pattern,
                onSubmit,
                validator
            };
            this.showInputModal = true;
        },

        /**
         * Submit input value with validation
         */
        submitInput() {
            const value = this.inputModalData.inputValue.trim();

            // Check for empty input
            if (!value) {
                this.showNotification('Input required', 'error');
                return;
            }

            // Validate with custom validator if provided
            if (this.inputModalData.validator) {
                const validationError = this.inputModalData.validator(value);
                if (validationError) {
                    this.showNotification(validationError, 'error');
                    return;
                }
            }

            // Call callback with value
            if (this.inputModalData.onSubmit) {
                this.inputModalData.onSubmit(value);
            }

            this.closeInputModal();
        },

        /**
         * Close input modal and reset state
         */
        closeInputModal() {
            this.showInputModal = false;
            this.inputModalData = {
                title: '',
                message: '',
                placeholder: '',
                inputValue: '',
                pattern: null,
                onSubmit: null,
                validator: null
            };
        },

        /**
         * Show password modal
         * @param {string} title - Modal title
         * @param {string} message - Warning/instruction message
         * @param {function} onSubmit - Callback function with password value
         * @param {string} placeholder - Input placeholder text
         */
        showPassword(title, message, onSubmit, placeholder = '') {
            this.passwordModalData = {
                title,
                message,
                placeholder,
                passwordValue: '',
                onSubmit
            };
            this.showPasswordModal = true;
        },

        /**
         * Submit password with validation
         */
        submitPassword() {
            const password = this.passwordModalData.passwordValue;

            if (!password) {
                this.showNotification('Password required', 'error');
                return;
            }

            if (this.passwordModalData.onSubmit) {
                this.passwordModalData.onSubmit(password);
            }

            this.closePasswordModal();
        },

        /**
         * Close password modal and reset state
         */
        closePasswordModal() {
            this.showPasswordModal = false;
            this.passwordModalData = {
                title: '',
                message: '',
                placeholder: '',
                passwordValue: '',
                onSubmit: null
            };
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
         * Verifies token with backend (online) or uses cached user data (offline)
         *
         * Offline-first approach:
         * - If offline with cached user data, proceed without server verification
         * - If online, verify token with server
         * - When back online with expired token, API calls will return 401 and trigger re-login
         */
        async checkAuth() {
            const token = localStorage.getItem('auth_token');
            const cachedUser = localStorage.getItem('user');

            if (!token) {
                this.isAuthenticated = false;
                return;
            }

            // Offline-first: If offline and we have cached user data, trust it
            // Token validation will happen when back online via API calls
            if (!navigator.onLine && cachedUser) {
                try {
                    this.user = JSON.parse(cachedUser);
                    this.isAuthenticated = true;
                    return;
                } catch (e) {
                    console.warn('[AUTH] Failed to parse cached user data');
                }
            }

            // Online: Verify token with backend
            try {
                const response = await fetch('/api/auth/me', {
                    headers: {
                        'Authorization': `Bearer ${token}`
                    }
                });

                if (response.ok) {
                    const user = await response.json();
                    this.user = user;
                    this.isAuthenticated = true;
                    // Cache user data for offline use
                    localStorage.setItem('user', JSON.stringify(user));
                } else {
                    // Token invalid or expired
                    this.isAuthenticated = false;
                    localStorage.removeItem('auth_token');
                    localStorage.removeItem('user');
                }
            } catch (error) {
                // Network error - check if we can use cached data
                console.warn('[AUTH] Network error during auth check:', error.message);

                if (cachedUser) {
                    try {
                        this.user = JSON.parse(cachedUser);
                        this.isAuthenticated = true;
                        return;
                    } catch (e) {
                        console.warn('[AUTH] Failed to parse cached user data');
                    }
                }

                // No cached data available - must be online to authenticate
                this.isAuthenticated = false;
            }
        },

        /**
         * Handle login form submission
         */
        async handleLogin() {
            // Reset errors
            ValidationHelpers.resetFormErrors(this.loginFormErrors);
            this.loginError = '';

            // HTML5 validation
            const form = this.$refs.loginFormElement;
            if (!form) {
                console.error('Login form ref not found');
                return;
            }

            if (!ValidationHelpers.validateHTML5(form, this.loginFormErrors)) {
                const count = ValidationHelpers.countErrors(this.loginFormErrors);
                this.loginError = `Please fix ${count} field(s)`;
                return;
            }

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

                    // Check if tenant has changed - clear database if so
                    // This prevents data leakage when different tenants use the same device
                    const storedTenantId = await db.getTenantId();
                    const newTenantId = data.user.tenant_id;

                    if (storedTenantId && storedTenantId !== newTenantId) {
                        console.log('[CHAPTR] Tenant changed, clearing local database...');
                        await db.clearAllData();
                    }

                    // Store current tenant_id for future comparisons
                    await db.setTenantId(newTenantId);

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
            // Stop auto-sync timer before logout
            this.stopAutoSyncTimer();
            clearAuth();
            // Reload page to reset all state and show login screen
            window.location.reload();
        }
    };
};
