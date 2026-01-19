/**
 * Unit tests for currency display logic
 *
 * Tests the availableCurrencies and displayRates computed properties
 * that filter rates based on user's accounts.
 */

import { describe, it, expect, beforeEach } from 'vitest';

/**
 * Mock component with currency display logic
 * Mirrors the implementation in app.js
 */
class MockCurrencyComponent {
    constructor() {
        this.settings = { base_currency: 'GBP', rates: {} };
        this.accounts = [];
    }

    /**
     * Get unique currencies from user's accounts
     *
     * Always includes base currency, plus currencies from all accounts.
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
    }

    /**
     * Filter rates to only show currencies user has accounts for
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
    }
}

describe('Currency Display', () => {
    let component;

    beforeEach(() => {
        component = new MockCurrencyComponent();
    });

    describe('availableCurrencies', () => {
        it('should include base currency when no accounts exist', () => {
            component.settings = { base_currency: 'GBP', rates: {} };
            component.accounts = [];

            expect(component.availableCurrencies).toContain('GBP');
            expect(component.availableCurrencies.length).toBe(1);
        });

        it('should default to GBP when settings are undefined', () => {
            component.settings = undefined;
            component.accounts = [];

            expect(component.availableCurrencies).toContain('GBP');
        });

        it('should include currencies from accounts', () => {
            component.settings = { base_currency: 'GBP', rates: {} };
            component.accounts = [
                { id: '1', name: 'USD Account', currency: 'USD' },
                { id: '2', name: 'EUR Account', currency: 'EUR' }
            ];

            const currencies = component.availableCurrencies;
            expect(currencies).toContain('GBP');
            expect(currencies).toContain('USD');
            expect(currencies).toContain('EUR');
            expect(currencies.length).toBe(3);
        });

        it('should deduplicate currencies from multiple accounts', () => {
            component.settings = { base_currency: 'GBP', rates: {} };
            component.accounts = [
                { id: '1', name: 'USD Account 1', currency: 'USD' },
                { id: '2', name: 'USD Account 2', currency: 'USD' },
                { id: '3', name: 'GBP Account', currency: 'GBP' }
            ];

            const currencies = component.availableCurrencies;
            expect(currencies).toContain('GBP');
            expect(currencies).toContain('USD');
            expect(currencies.length).toBe(2);
        });

        it('should handle accounts without currency field', () => {
            component.settings = { base_currency: 'GBP', rates: {} };
            component.accounts = [
                { id: '1', name: 'Account without currency' },
                { id: '2', name: 'USD Account', currency: 'USD' }
            ];

            const currencies = component.availableCurrencies;
            expect(currencies).toContain('GBP');
            expect(currencies).toContain('USD');
            expect(currencies.length).toBe(2);
        });
    });

    describe('displayRates', () => {
        it('should return empty object when no rates exist', () => {
            component.settings = { base_currency: 'GBP', rates: {} };
            component.accounts = [];

            expect(component.displayRates).toEqual({});
        });

        it('should filter rates to only available currencies', () => {
            component.settings = {
                base_currency: 'GBP',
                rates: {
                    'GBP': 1.0,
                    'USD': 1.27,
                    'EUR': 1.17,
                    'CAD': 1.76,
                    'JPY': 189.5
                }
            };
            component.accounts = [
                { id: '1', name: 'USD Account', currency: 'USD' }
            ];

            const rates = component.displayRates;

            // Should only show GBP (base) and USD (from account)
            expect(rates).toHaveProperty('GBP');
            expect(rates).toHaveProperty('USD');
            expect(rates).not.toHaveProperty('EUR');
            expect(rates).not.toHaveProperty('CAD');
            expect(rates).not.toHaveProperty('JPY');
        });

        it('should include all account currencies in rates', () => {
            component.settings = {
                base_currency: 'GBP',
                rates: {
                    'GBP': 1.0,
                    'USD': 1.27,
                    'EUR': 1.17,
                    'CAD': 1.76
                }
            };
            component.accounts = [
                { id: '1', name: 'USD Account', currency: 'USD' },
                { id: '2', name: 'EUR Account', currency: 'EUR' }
            ];

            const rates = component.displayRates;

            expect(rates).toEqual({
                'GBP': 1.0,
                'USD': 1.27,
                'EUR': 1.17
            });
        });

        it('should handle missing rate for account currency', () => {
            component.settings = {
                base_currency: 'GBP',
                rates: {
                    'GBP': 1.0,
                    'USD': 1.27
                }
            };
            component.accounts = [
                { id: '1', name: 'PLN Account', currency: 'PLN' }  // PLN not in rates
            ];

            const rates = component.displayRates;

            // Should only show GBP (available but PLN rate doesn't exist)
            expect(rates).toHaveProperty('GBP');
            expect(rates).not.toHaveProperty('PLN');
        });

        it('should preserve rate values exactly', () => {
            component.settings = {
                base_currency: 'GBP',
                rates: {
                    'GBP': 1.0,
                    'USD': '1.2734',  // String value
                    'EUR': 1.1678    // Number value
                }
            };
            component.accounts = [
                { id: '1', currency: 'USD' },
                { id: '2', currency: 'EUR' }
            ];

            const rates = component.displayRates;

            expect(rates['GBP']).toBe(1.0);
            expect(rates['USD']).toBe('1.2734');
            expect(rates['EUR']).toBe(1.1678);
        });

        it('should handle undefined settings gracefully', () => {
            component.settings = undefined;
            component.accounts = [];

            expect(component.displayRates).toEqual({});
        });

        it('should handle null rates gracefully', () => {
            component.settings = { base_currency: 'GBP', rates: null };
            component.accounts = [];

            expect(component.displayRates).toEqual({});
        });
    });

    describe('currency flow integration', () => {
        it('should work with typical new user setup', () => {
            // New user with just base currency
            component.settings = {
                base_currency: 'GBP',
                rates: { 'GBP': 1.0, 'USD': 1.27, 'EUR': 1.17 }
            };
            component.accounts = [];

            // Only GBP should be available
            expect(component.availableCurrencies).toEqual(['GBP']);
            expect(component.displayRates).toEqual({ 'GBP': 1.0 });
        });

        it('should update when user adds foreign currency account', () => {
            component.settings = {
                base_currency: 'GBP',
                rates: { 'GBP': 1.0, 'USD': 1.27, 'EUR': 1.17 }
            };
            component.accounts = [];

            // Initially only GBP
            expect(component.displayRates).toEqual({ 'GBP': 1.0 });

            // User creates USD account
            component.accounts = [{ id: '1', name: 'USD Savings', currency: 'USD' }];

            // Now USD should be visible
            expect(component.availableCurrencies).toContain('USD');
            expect(component.displayRates).toEqual({
                'GBP': 1.0,
                'USD': 1.27
            });
        });

        it('should work with multiple foreign currency accounts', () => {
            component.settings = {
                base_currency: 'GBP',
                rates: {
                    'GBP': 1.0,
                    'USD': 1.27,
                    'EUR': 1.17,
                    'CAD': 1.76,
                    'AUD': 1.92,
                    'JPY': 189.5
                }
            };
            component.accounts = [
                { id: '1', name: 'Main UK', currency: 'GBP' },
                { id: '2', name: 'US Savings', currency: 'USD' },
                { id: '3', name: 'EU Travel', currency: 'EUR' }
            ];

            expect(component.availableCurrencies.sort()).toEqual(['EUR', 'GBP', 'USD']);
            expect(Object.keys(component.displayRates).sort()).toEqual(['EUR', 'GBP', 'USD']);
        });
    });
});
