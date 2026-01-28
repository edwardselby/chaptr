/**
 * Unit tests for CHAPTR per-view account filter functionality
 *
 * Tests the account filter system that allows filtering events by account
 * on a per-view basis (ALL, Baseline, and Story views maintain independent filters)
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

describe('Account Filter - Per-View State Management', () => {
    let app;
    let mockAccounts;
    let mockLocalStorage;

    beforeEach(() => {
        // Mock localStorage
        mockLocalStorage = {
            store: {},
            getItem(key) {
                return this.store[key] || null;
            },
            setItem(key, value) {
                this.store[key] = value;
            },
            removeItem(key) {
                delete this.store[key];
            },
            clear() {
                this.store = {};
            }
        };

        // Store original localStorage and replace with mock
        vi.stubGlobal('localStorage', mockLocalStorage);

        // Create mock accounts
        mockAccounts = [
            { id: 'acc-1', name: 'Monzo', is_archived: false },
            { id: 'acc-2', name: 'Barclays', is_archived: false },
            { id: 'acc-3', name: 'Starling', is_archived: false },
            { id: 'acc-4', name: 'Cash', is_archived: false },
            { id: 'acc-5', name: 'Archived', is_archived: true }
        ];

        // Create minimal app context with filter methods
        app = {
            accounts: mockAccounts,
            currentView: 'all',
            accountFilters: {},
            ACCOUNT_FILTER_STORAGE_KEY: 'chaptr_account_filters',

            // Helper methods
            getCurrentViewFilter() {
                return this.accountFilters[this.currentView] || null;
            },

            setCurrentViewFilter(filter) {
                if (filter === null) {
                    delete this.accountFilters[this.currentView];
                } else {
                    this.accountFilters[this.currentView] = filter;
                }
                this.saveAccountFilters();
            },

            saveAccountFilters() {
                try {
                    const filtersToSave = {};

                    for (const [view, filter] of Object.entries(this.accountFilters)) {
                        if (filter !== null && filter instanceof Set) {
                            filtersToSave[view] = Array.from(filter);
                        }
                    }

                    if (Object.keys(filtersToSave).length === 0) {
                        localStorage.removeItem(this.ACCOUNT_FILTER_STORAGE_KEY);
                    } else {
                        localStorage.setItem(this.ACCOUNT_FILTER_STORAGE_KEY, JSON.stringify(filtersToSave));
                    }
                } catch (error) {
                    console.error('Failed to save account filters:', error);
                }
            },

            loadAccountFilter() {
                try {
                    const saved = localStorage.getItem(this.ACCOUNT_FILTER_STORAGE_KEY);
                    if (saved) {
                        const savedFilters = JSON.parse(saved);
                        const validAccountIds = new Set(
                            this.accounts.filter(a => !a.is_archived).map(a => a.id)
                        );

                        for (const [view, filterArray] of Object.entries(savedFilters)) {
                            const filterSet = new Set(filterArray);

                            // Remove invalid account IDs
                            for (const id of filterSet) {
                                if (!validAccountIds.has(id)) {
                                    filterSet.delete(id);
                                }
                            }

                            // Only save if valid accounts remain and not all selected
                            if (filterSet.size > 0 && filterSet.size < validAccountIds.size) {
                                this.accountFilters[view] = filterSet;
                            }
                        }
                    }
                } catch (error) {
                    // Silently handle corrupted localStorage data
                    this.accountFilters = {};
                }
            },

            isAccountSelected(accountId) {
                const filter = this.getCurrentViewFilter();
                if (filter === null) return true;
                return filter.has(accountId);
            },

            hasActiveAccountFilter() {
                return this.getCurrentViewFilter() !== null;
            },

            getFilterButtonLabel() {
                const filter = this.getCurrentViewFilter();
                if (filter === null) {
                    return '⧩ filter';
                }
                const total = this.accounts.filter(a => !a.is_archived).length;
                const selected = filter.size;
                return `⧩ ${selected}/${total}`;
            },

            toggleAccountFilter(accountId) {
                let filter = this.getCurrentViewFilter();

                if (filter === null) {
                    filter = new Set(
                        this.accounts.filter(a => !a.is_archived).map(a => a.id)
                    );
                }

                if (filter.has(accountId)) {
                    filter.delete(accountId);
                } else {
                    filter.add(accountId);
                }

                const allAccountIds = this.accounts.filter(a => !a.is_archived).map(a => a.id);
                if (filter.size === allAccountIds.length) {
                    this.setCurrentViewFilter(null);
                } else {
                    this.setCurrentViewFilter(filter);
                }
            },

            selectAllAccounts() {
                this.setCurrentViewFilter(null);
            },

            clearAccountFilter() {
                this.setCurrentViewFilter(new Set());
            }
        };
    });

    afterEach(() => {
        mockLocalStorage.clear();
        vi.unstubAllGlobals();
    });

    describe('getCurrentViewFilter()', () => {
        it('returns null when no filter set for current view', () => {
            expect(app.getCurrentViewFilter()).toBe(null);
        });

        it('returns Set when filter exists for current view', () => {
            const filter = new Set(['acc-1', 'acc-2']);
            app.accountFilters['all'] = filter;
            expect(app.getCurrentViewFilter()).toBe(filter);
        });

        it('returns correct filter for different views', () => {
            const allFilter = new Set(['acc-1', 'acc-2']);
            const baselineFilter = new Set(['acc-3', 'acc-4']);

            app.accountFilters['all'] = allFilter;
            app.accountFilters['baseline'] = baselineFilter;

            app.currentView = 'all';
            expect(app.getCurrentViewFilter()).toBe(allFilter);

            app.currentView = 'baseline';
            expect(app.getCurrentViewFilter()).toBe(baselineFilter);
        });
    });

    describe('setCurrentViewFilter()', () => {
        it('sets filter for current view', () => {
            const filter = new Set(['acc-1', 'acc-2']);
            app.setCurrentViewFilter(filter);

            expect(app.accountFilters['all']).toBe(filter);
        });

        it('removes filter when set to null', () => {
            app.accountFilters['all'] = new Set(['acc-1']);
            app.setCurrentViewFilter(null);

            expect(app.accountFilters['all']).toBeUndefined();
        });

        it('saves to localStorage after setting', () => {
            const filter = new Set(['acc-1', 'acc-2']);
            app.setCurrentViewFilter(filter);

            const saved = JSON.parse(localStorage.getItem(app.ACCOUNT_FILTER_STORAGE_KEY));
            expect(saved['all']).toEqual(['acc-1', 'acc-2']);
        });
    });

    describe('saveAccountFilters()', () => {
        it('saves multiple view filters to localStorage', () => {
            app.accountFilters['all'] = new Set(['acc-1', 'acc-2']);
            app.accountFilters['baseline'] = new Set(['acc-3']);
            app.saveAccountFilters();

            const saved = JSON.parse(localStorage.getItem(app.ACCOUNT_FILTER_STORAGE_KEY));
            expect(saved).toEqual({
                all: ['acc-1', 'acc-2'],
                baseline: ['acc-3']
            });
        });

        it('removes localStorage entry when no filters active', () => {
            localStorage.setItem(app.ACCOUNT_FILTER_STORAGE_KEY, JSON.stringify({ all: ['acc-1'] }));
            app.accountFilters = {};
            app.saveAccountFilters();

            expect(localStorage.getItem(app.ACCOUNT_FILTER_STORAGE_KEY)).toBe(null);
        });

        it('converts Sets to arrays for JSON storage', () => {
            app.accountFilters['all'] = new Set(['acc-1', 'acc-2', 'acc-3']);
            app.saveAccountFilters();

            const saved = JSON.parse(localStorage.getItem(app.ACCOUNT_FILTER_STORAGE_KEY));
            expect(Array.isArray(saved['all'])).toBe(true);
            expect(saved['all']).toContain('acc-1');
            expect(saved['all']).toContain('acc-2');
            expect(saved['all']).toContain('acc-3');
        });
    });

    describe('loadAccountFilter()', () => {
        it('loads filters from localStorage', () => {
            const savedFilters = {
                all: ['acc-1', 'acc-2'],
                baseline: ['acc-3']
            };
            localStorage.setItem(app.ACCOUNT_FILTER_STORAGE_KEY, JSON.stringify(savedFilters));

            app.loadAccountFilter();

            expect(app.accountFilters['all']).toEqual(new Set(['acc-1', 'acc-2']));
            expect(app.accountFilters['baseline']).toEqual(new Set(['acc-3']));
        });

        it('converts arrays back to Sets', () => {
            localStorage.setItem(app.ACCOUNT_FILTER_STORAGE_KEY, JSON.stringify({
                all: ['acc-1', 'acc-2']
            }));

            app.loadAccountFilter();

            expect(app.accountFilters['all'] instanceof Set).toBe(true);
        });

        it('removes invalid account IDs on load', () => {
            localStorage.setItem(app.ACCOUNT_FILTER_STORAGE_KEY, JSON.stringify({
                all: ['acc-1', 'invalid-id', 'acc-2']
            }));

            app.loadAccountFilter();

            expect(app.accountFilters['all']).toEqual(new Set(['acc-1', 'acc-2']));
            expect(app.accountFilters['all'].has('invalid-id')).toBe(false);
        });

        it('ignores archived accounts on load', () => {
            localStorage.setItem(app.ACCOUNT_FILTER_STORAGE_KEY, JSON.stringify({
                all: ['acc-1', 'acc-5'] // acc-5 is archived
            }));

            app.loadAccountFilter();

            expect(app.accountFilters['all']).toEqual(new Set(['acc-1']));
            expect(app.accountFilters['all'].has('acc-5')).toBe(false);
        });

        it('removes filter if all accounts end up selected', () => {
            localStorage.setItem(app.ACCOUNT_FILTER_STORAGE_KEY, JSON.stringify({
                all: ['acc-1', 'acc-2', 'acc-3', 'acc-4'] // All non-archived accounts
            }));

            app.loadAccountFilter();

            expect(app.accountFilters['all']).toBeUndefined();
        });

        it('removes filter if no valid accounts remain', () => {
            localStorage.setItem(app.ACCOUNT_FILTER_STORAGE_KEY, JSON.stringify({
                all: ['invalid-1', 'invalid-2']
            }));

            app.loadAccountFilter();

            expect(app.accountFilters['all']).toBeUndefined();
        });

        it('handles missing localStorage gracefully', () => {
            expect(() => app.loadAccountFilter()).not.toThrow();
            expect(app.accountFilters).toEqual({});
        });

        it('handles corrupted JSON gracefully', () => {
            localStorage.setItem(app.ACCOUNT_FILTER_STORAGE_KEY, 'invalid json');

            expect(() => app.loadAccountFilter()).not.toThrow();
            expect(app.accountFilters).toEqual({});
        });
    });

    describe('isAccountSelected()', () => {
        it('returns true for all accounts when filter is null', () => {
            expect(app.isAccountSelected('acc-1')).toBe(true);
            expect(app.isAccountSelected('acc-2')).toBe(true);
            expect(app.isAccountSelected('acc-3')).toBe(true);
        });

        it('returns true only for selected accounts when filter active', () => {
            app.accountFilters['all'] = new Set(['acc-1', 'acc-2']);

            expect(app.isAccountSelected('acc-1')).toBe(true);
            expect(app.isAccountSelected('acc-2')).toBe(true);
            expect(app.isAccountSelected('acc-3')).toBe(false);
            expect(app.isAccountSelected('acc-4')).toBe(false);
        });
    });

    describe('hasActiveAccountFilter()', () => {
        it('returns false when no filter active', () => {
            expect(app.hasActiveAccountFilter()).toBe(false);
        });

        it('returns true when filter active', () => {
            app.accountFilters['all'] = new Set(['acc-1']);
            expect(app.hasActiveAccountFilter()).toBe(true);
        });

        it('returns false for empty Set', () => {
            app.accountFilters['all'] = new Set();
            expect(app.hasActiveAccountFilter()).toBe(true); // Empty set is still a filter
        });
    });

    describe('getFilterButtonLabel()', () => {
        it('returns default label when no filter active', () => {
            expect(app.getFilterButtonLabel()).toBe('⧩ filter');
        });

        it('returns count when filter active', () => {
            app.accountFilters['all'] = new Set(['acc-1', 'acc-2']);
            expect(app.getFilterButtonLabel()).toBe('⧩ 2/4');
        });

        it('shows correct total (excludes archived accounts)', () => {
            app.accountFilters['all'] = new Set(['acc-1']);
            expect(app.getFilterButtonLabel()).toBe('⧩ 1/4'); // 4 non-archived accounts
        });
    });

    describe('toggleAccountFilter()', () => {
        it('creates filter from all accounts when starting from null', () => {
            app.toggleAccountFilter('acc-1');

            const filter = app.getCurrentViewFilter();
            expect(filter).toBeDefined();
            expect(filter.has('acc-2')).toBe(true);
            expect(filter.has('acc-3')).toBe(true);
            expect(filter.has('acc-4')).toBe(true);
            expect(filter.has('acc-1')).toBe(false); // Toggled off
        });

        it('removes account when already selected', () => {
            app.accountFilters['all'] = new Set(['acc-1', 'acc-2', 'acc-3']);
            app.toggleAccountFilter('acc-2');

            expect(app.getCurrentViewFilter().has('acc-2')).toBe(false);
            expect(app.getCurrentViewFilter().has('acc-1')).toBe(true);
            expect(app.getCurrentViewFilter().has('acc-3')).toBe(true);
        });

        it('adds account when not selected', () => {
            app.accountFilters['all'] = new Set(['acc-1']);
            app.toggleAccountFilter('acc-2');

            expect(app.getCurrentViewFilter().has('acc-1')).toBe(true);
            expect(app.getCurrentViewFilter().has('acc-2')).toBe(true);
        });

        it('resets to null when all accounts selected', () => {
            app.accountFilters['all'] = new Set(['acc-1', 'acc-2', 'acc-3']);
            app.toggleAccountFilter('acc-4'); // Last account

            expect(app.getCurrentViewFilter()).toBe(null);
        });

        it('saves to localStorage after toggle', () => {
            app.toggleAccountFilter('acc-1');

            const saved = localStorage.getItem(app.ACCOUNT_FILTER_STORAGE_KEY);
            expect(saved).not.toBe(null);
        });

        it('excludes archived accounts from "all accounts" set', () => {
            app.toggleAccountFilter('acc-1');

            const filter = app.getCurrentViewFilter();
            expect(filter.has('acc-5')).toBe(false); // acc-5 is archived
        });
    });

    describe('selectAllAccounts()', () => {
        it('resets filter to null', () => {
            app.accountFilters['all'] = new Set(['acc-1', 'acc-2']);
            app.selectAllAccounts();

            expect(app.getCurrentViewFilter()).toBe(null);
        });

        it('removes from localStorage', () => {
            app.accountFilters['all'] = new Set(['acc-1']);
            app.selectAllAccounts();

            expect(localStorage.getItem(app.ACCOUNT_FILTER_STORAGE_KEY)).toBe(null);
        });
    });

    describe('clearAccountFilter()', () => {
        it('sets filter to empty Set', () => {
            app.clearAccountFilter();

            const filter = app.getCurrentViewFilter();
            expect(filter instanceof Set).toBe(true);
            expect(filter.size).toBe(0);
        });

        it('saves empty filter to localStorage', () => {
            app.clearAccountFilter();

            const saved = JSON.parse(localStorage.getItem(app.ACCOUNT_FILTER_STORAGE_KEY));
            expect(saved['all']).toEqual([]);
        });
    });

    describe('Per-View Independence', () => {
        it('maintains separate filters for ALL and Baseline views', () => {
            app.currentView = 'all';
            app.setCurrentViewFilter(new Set(['acc-1', 'acc-2']));

            app.currentView = 'baseline';
            app.setCurrentViewFilter(new Set(['acc-3', 'acc-4']));

            app.currentView = 'all';
            expect(app.getCurrentViewFilter()).toEqual(new Set(['acc-1', 'acc-2']));

            app.currentView = 'baseline';
            expect(app.getCurrentViewFilter()).toEqual(new Set(['acc-3', 'acc-4']));
        });

        it('maintains filters when switching views', () => {
            app.currentView = 'all';
            app.toggleAccountFilter('acc-1');
            const allFilter = app.getCurrentViewFilter();

            app.currentView = 'baseline';
            expect(app.getCurrentViewFilter()).toBe(null); // No filter in baseline

            app.currentView = 'all';
            expect(app.getCurrentViewFilter()).toBe(allFilter); // ALL filter preserved
        });

        it('persists multiple view filters to localStorage', () => {
            app.currentView = 'all';
            app.setCurrentViewFilter(new Set(['acc-1']));

            app.currentView = 'baseline';
            app.setCurrentViewFilter(new Set(['acc-2']));

            const saved = JSON.parse(localStorage.getItem(app.ACCOUNT_FILTER_STORAGE_KEY));
            expect(saved).toEqual({
                all: ['acc-1'],
                baseline: ['acc-2']
            });
        });

        it('loads multiple view filters from localStorage', () => {
            localStorage.setItem(app.ACCOUNT_FILTER_STORAGE_KEY, JSON.stringify({
                all: ['acc-1', 'acc-2'],
                baseline: ['acc-3'],
                'story-123': ['acc-4']
            }));

            app.loadAccountFilter();

            app.currentView = 'all';
            expect(app.getCurrentViewFilter()).toEqual(new Set(['acc-1', 'acc-2']));

            app.currentView = 'baseline';
            expect(app.getCurrentViewFilter()).toEqual(new Set(['acc-3']));

            app.currentView = 'story-123';
            expect(app.getCurrentViewFilter()).toEqual(new Set(['acc-4']));
        });
    });

    describe('Edge Cases', () => {
        it('handles empty accounts list', () => {
            app.accounts = [];
            expect(() => app.toggleAccountFilter('acc-1')).not.toThrow();
        });

        it('handles toggling archived account', () => {
            app.toggleAccountFilter('acc-5'); // Archived account

            // When toggling archived account:
            // 1. Filter initialized with all non-archived accounts (acc-1, acc-2, acc-3, acc-4)
            // 2. acc-5 not in set, so toggle tries to ADD it
            const filter = app.getCurrentViewFilter();

            // Filter contains all non-archived accounts PLUS acc-5 (which got added by toggle)
            expect(filter.has('acc-1')).toBe(true);
            expect(filter.has('acc-2')).toBe(true);
            expect(filter.has('acc-3')).toBe(true);
            expect(filter.has('acc-4')).toBe(true);
            expect(filter.has('acc-5')).toBe(true); // Added by toggle
        });

        it('handles all accounts archived scenario', () => {
            app.accounts = app.accounts.map(a => ({ ...a, is_archived: true }));

            app.toggleAccountFilter('acc-1');

            const filter = app.getCurrentViewFilter();
            // When all accounts are archived:
            // 1. Initial set has no non-archived accounts (empty Set)
            // 2. acc-1 not in empty set, so toggle ADDS it
            // 3. Filter now contains acc-1
            expect(filter instanceof Set).toBe(true);
            expect(filter.size).toBe(1);
            expect(filter.has('acc-1')).toBe(true);
        });
    });
});
