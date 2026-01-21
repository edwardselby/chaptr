/**
 * CHAPTR - Account Balance Toggle Unit Tests
 *
 * Tests for the account balance sign toggle feature:
 * - Balance class determination (positive/negative styling)
 * - Sign application logic (balanceIsNegative → stored value)
 * - Smart defaults based on account type
 * - Credit card warning thresholds
 */

import { describe, it, expect } from 'vitest';
import {
    getBalanceClass,
    applyBalanceSign,
    getDefaultSignForAccountType,
    parseBalanceForForm
} from '../../../static/js/modules/formatting.js';


// ============================================================================
// Balance Class Tests (Visual Styling)
// ============================================================================

describe('getBalanceClass', () => {
    describe('checking accounts', () => {
        it('returns positive for positive balance', () => {
            const account = {
                current_balance: 1000,
                account_type: 'checking'
            };
            expect(getBalanceClass(account)).toBe('positive');
        });

        it('returns positive for zero balance', () => {
            const account = {
                current_balance: 0,
                account_type: 'checking'
            };
            expect(getBalanceClass(account)).toBe('positive');
        });

        it('returns negative for negative balance (overdraft)', () => {
            const account = {
                current_balance: -50,
                account_type: 'checking'
            };
            expect(getBalanceClass(account)).toBe('negative');
        });

        it('handles string balance values', () => {
            const account = {
                current_balance: '1500.50',
                account_type: 'checking'
            };
            expect(getBalanceClass(account)).toBe('positive');
        });
    });

    describe('savings accounts', () => {
        it('returns positive for positive balance', () => {
            const account = {
                current_balance: 5000,
                account_type: 'savings'
            };
            expect(getBalanceClass(account)).toBe('positive');
        });

        it('returns negative for negative balance', () => {
            const account = {
                current_balance: -100,
                account_type: 'savings'
            };
            expect(getBalanceClass(account)).toBe('negative');
        });
    });

    describe('credit card accounts', () => {
        it('returns positive when balance within limit (normal usage)', () => {
            // Owe £500 with £1000 limit = within limit = green
            const account = {
                current_balance: -500,
                account_type: 'credit_card',
                credit_limit: 1000
            };
            expect(getBalanceClass(account)).toBe('positive');
        });

        it('returns positive when balance exactly at limit', () => {
            // Owe £1000 with £1000 limit = at limit = green
            const account = {
                current_balance: -1000,
                account_type: 'credit_card',
                credit_limit: 1000
            };
            expect(getBalanceClass(account)).toBe('positive');
        });

        it('returns negative when balance exceeds limit', () => {
            // Owe £1100 with £1000 limit = over limit = red
            const account = {
                current_balance: -1100,
                account_type: 'credit_card',
                credit_limit: 1000
            };
            expect(getBalanceClass(account)).toBe('negative');
        });

        it('returns positive for zero balance (no debt)', () => {
            const account = {
                current_balance: 0,
                account_type: 'credit_card',
                credit_limit: 1000
            };
            expect(getBalanceClass(account)).toBe('positive');
        });

        it('returns positive for positive balance (overpayment)', () => {
            // Overpaid, credit on account = positive = green
            const account = {
                current_balance: 50,
                account_type: 'credit_card',
                credit_limit: 1000
            };
            expect(getBalanceClass(account)).toBe('positive');
        });

        it('handles missing credit_limit (treats as 0)', () => {
            // No limit = any negative balance is over limit
            const account = {
                current_balance: -100,
                account_type: 'credit_card'
                // credit_limit not set
            };
            expect(getBalanceClass(account)).toBe('negative');
        });

        it('handles string balance and limit values', () => {
            const account = {
                current_balance: '-900',
                account_type: 'credit_card',
                credit_limit: '1350'
            };
            expect(getBalanceClass(account)).toBe('positive');
        });
    });

    describe('edge cases', () => {
        it('handles undefined account_type (defaults to checking behavior)', () => {
            const account = {
                current_balance: -50
                // account_type not set
            };
            expect(getBalanceClass(account)).toBe('negative');
        });

        it('handles null balance', () => {
            const account = {
                current_balance: null,
                account_type: 'checking'
            };
            expect(getBalanceClass(account)).toBe('positive'); // 0 is positive
        });

        it('handles undefined balance', () => {
            const account = {
                account_type: 'checking'
                // current_balance not set
            };
            expect(getBalanceClass(account)).toBe('positive'); // 0 is positive
        });
    });
});


// ============================================================================
// Balance Sign Application Tests
// ============================================================================

describe('applyBalanceSign', () => {
    describe('positive sign (isNegative = false)', () => {
        it('returns positive value unchanged', () => {
            expect(applyBalanceSign(1000, false)).toBe(1000);
        });

        it('converts negative input to positive', () => {
            expect(applyBalanceSign(-500, false)).toBe(500);
        });

        it('handles zero', () => {
            expect(applyBalanceSign(0, false)).toBe(0);
        });

        it('handles decimal values', () => {
            expect(applyBalanceSign(1234.56, false)).toBe(1234.56);
        });
    });

    describe('negative sign (isNegative = true)', () => {
        it('negates positive value', () => {
            expect(applyBalanceSign(1000, true)).toBe(-1000);
        });

        it('keeps negative input as negative', () => {
            expect(applyBalanceSign(-500, true)).toBe(-500);
        });

        it('handles zero (stays zero)', () => {
            // Note: -0 and 0 are equal with == but Object.is treats them differently
            // For practical purposes, both -0 and 0 behave the same
            const result = applyBalanceSign(0, true);
            expect(result == 0).toBe(true);
            expect(Math.abs(result)).toBe(0);
        });

        it('handles decimal values', () => {
            expect(applyBalanceSign(1234.56, true)).toBe(-1234.56);
        });
    });

    describe('edge cases', () => {
        it('handles null input', () => {
            expect(applyBalanceSign(null, false)).toBe(0);
            expect(applyBalanceSign(null, true)).toBe(-0);
        });

        it('handles undefined input', () => {
            expect(applyBalanceSign(undefined, false)).toBe(0);
        });

        it('handles string input', () => {
            expect(applyBalanceSign('500', false)).toBe(500);
            expect(applyBalanceSign('500', true)).toBe(-500);
        });
    });
});


// ============================================================================
// Smart Default Tests
// ============================================================================

describe('getDefaultSignForAccountType', () => {
    it('returns false (positive) for checking accounts', () => {
        expect(getDefaultSignForAccountType('checking')).toBe(false);
    });

    it('returns false (positive) for savings accounts', () => {
        expect(getDefaultSignForAccountType('savings')).toBe(false);
    });

    it('returns true (negative) for credit card accounts', () => {
        expect(getDefaultSignForAccountType('credit_card')).toBe(true);
    });

    it('returns false for undefined account type', () => {
        expect(getDefaultSignForAccountType(undefined)).toBe(false);
    });

    it('returns false for unknown account type', () => {
        expect(getDefaultSignForAccountType('unknown')).toBe(false);
    });
});


// ============================================================================
// Form Parsing Tests (Edit Mode)
// ============================================================================

describe('parseBalanceForForm', () => {
    describe('positive balances', () => {
        it('parses positive balance correctly', () => {
            const result = parseBalanceForForm(1000);
            expect(result.absoluteValue).toBe(1000);
            expect(result.isNegative).toBe(false);
        });

        it('parses zero as not negative', () => {
            const result = parseBalanceForForm(0);
            expect(result.absoluteValue).toBe(0);
            expect(result.isNegative).toBe(false);
        });
    });

    describe('negative balances', () => {
        it('parses negative balance correctly', () => {
            const result = parseBalanceForForm(-500);
            expect(result.absoluteValue).toBe(500);
            expect(result.isNegative).toBe(true);
        });

        it('parses large negative balance', () => {
            const result = parseBalanceForForm(-12345.67);
            expect(result.absoluteValue).toBe(12345.67);
            expect(result.isNegative).toBe(true);
        });
    });

    describe('string values', () => {
        it('parses positive string balance', () => {
            const result = parseBalanceForForm('1500.50');
            expect(result.absoluteValue).toBe(1500.50);
            expect(result.isNegative).toBe(false);
        });

        it('parses negative string balance', () => {
            const result = parseBalanceForForm('-900');
            expect(result.absoluteValue).toBe(900);
            expect(result.isNegative).toBe(true);
        });
    });

    describe('edge cases', () => {
        it('handles null', () => {
            const result = parseBalanceForForm(null);
            expect(result.absoluteValue).toBe(0);
            expect(result.isNegative).toBe(false);
        });

        it('handles undefined', () => {
            const result = parseBalanceForForm(undefined);
            expect(result.absoluteValue).toBe(0);
            expect(result.isNegative).toBe(false);
        });
    });
});


// ============================================================================
// Integration Scenarios
// ============================================================================

describe('Account Balance Toggle Integration Scenarios', () => {
    describe('creating a credit card account', () => {
        it('user enters 900, toggle negative → stored as -900', () => {
            // User flow: Select credit_card → auto-switch to negative → enter 900
            const userInput = 900;
            const isNegative = getDefaultSignForAccountType('credit_card');
            const storedValue = applyBalanceSign(userInput, isNegative);

            expect(isNegative).toBe(true);
            expect(storedValue).toBe(-900);
        });

        it('stored -900 with 1350 limit shows as green', () => {
            const account = {
                current_balance: -900,
                account_type: 'credit_card',
                credit_limit: 1350
            };
            expect(getBalanceClass(account)).toBe('positive');
        });
    });

    describe('editing an existing credit card account', () => {
        it('loads -900 balance into form correctly', () => {
            const existingBalance = -900;
            const { absoluteValue, isNegative } = parseBalanceForForm(existingBalance);

            expect(absoluteValue).toBe(900);
            expect(isNegative).toBe(true);
        });

        it('user changes to 1000, saves as -1000', () => {
            // User edits the 900 to 1000, keeping toggle on negative
            const userInput = 1000;
            const isNegative = true;
            const storedValue = applyBalanceSign(userInput, isNegative);

            expect(storedValue).toBe(-1000);
        });
    });

    describe('creating a checking account', () => {
        it('user enters 2500, toggle positive → stored as 2500', () => {
            const userInput = 2500;
            const isNegative = getDefaultSignForAccountType('checking');
            const storedValue = applyBalanceSign(userInput, isNegative);

            expect(isNegative).toBe(false);
            expect(storedValue).toBe(2500);
        });

        it('user enters 50, toggle negative (overdraft) → stored as -50', () => {
            const userInput = 50;
            const isNegative = true; // User manually switched to negative
            const storedValue = applyBalanceSign(userInput, isNegative);

            expect(storedValue).toBe(-50);
        });
    });

    describe('switching account type in form', () => {
        it('switching to credit_card changes default sign to negative', () => {
            // Simulate: User has checking selected, switches to credit_card
            const oldDefault = getDefaultSignForAccountType('checking');
            const newDefault = getDefaultSignForAccountType('credit_card');

            expect(oldDefault).toBe(false);
            expect(newDefault).toBe(true);
        });

        it('switching from credit_card to savings changes default to positive', () => {
            const oldDefault = getDefaultSignForAccountType('credit_card');
            const newDefault = getDefaultSignForAccountType('savings');

            expect(oldDefault).toBe(true);
            expect(newDefault).toBe(false);
        });
    });

    describe('balance reconciliation modal', () => {
        it('selecting credit card account sets toggle to negative', () => {
            // User selects a credit card account in balance modal
            const creditCardAccount = { account_type: 'credit_card' };
            const defaultSign = getDefaultSignForAccountType(creditCardAccount.account_type);

            expect(defaultSign).toBe(true); // negative
        });

        it('selecting checking account sets toggle to positive', () => {
            // User selects a checking account in balance modal
            const checkingAccount = { account_type: 'checking' };
            const defaultSign = getDefaultSignForAccountType(checkingAccount.account_type);

            expect(defaultSign).toBe(false); // positive
        });

        it('calculates drift correctly with positive actual balance', () => {
            // Projected: £1000, Actual: £950 (positive) → Drift: -£50
            const projectedBalance = 1000;
            const actualBalance = 950;
            const isNegative = false;

            const signedActual = applyBalanceSign(actualBalance, isNegative);
            const drift = signedActual - projectedBalance;

            expect(signedActual).toBe(950);
            expect(drift).toBe(-50);
        });

        it('calculates drift correctly with negative actual balance (overdraft)', () => {
            // Projected: £100, Actual: -£50 (overdraft) → Drift: -£150
            const projectedBalance = 100;
            const actualBalance = 50;
            const isNegative = true;

            const signedActual = applyBalanceSign(actualBalance, isNegative);
            const drift = signedActual - projectedBalance;

            expect(signedActual).toBe(-50);
            expect(drift).toBe(-150);
        });

        it('calculates drift correctly for credit card', () => {
            // Projected: -£500, Actual: -£600 (owe more) → Drift: -£100
            const projectedBalance = -500;
            const actualBalance = 600;
            const isNegative = true; // Credit card, user owes money

            const signedActual = applyBalanceSign(actualBalance, isNegative);
            const drift = signedActual - projectedBalance;

            expect(signedActual).toBe(-600);
            expect(drift).toBe(-100);
        });

        it('calculates drift correctly for credit card paying off debt', () => {
            // Projected: -£500, Actual: -£300 (paid some off) → Drift: +£200
            const projectedBalance = -500;
            const actualBalance = 300;
            const isNegative = true;

            const signedActual = applyBalanceSign(actualBalance, isNegative);
            const drift = signedActual - projectedBalance;

            expect(signedActual).toBe(-300);
            expect(drift).toBe(200);
        });
    });
});
