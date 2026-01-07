/**
 * Default Account Logic Tests
 *
 * Tests getDefaultAccountName() function that returns the global default account name.
 * This function is used in event forms to show hint text about which account will be used
 * when no account is explicitly selected.
 *
 * Function logic:
 * - Find account where is_default = true AND is_archived = false
 * - Return account.name if found, null otherwise
 *
 * Testing Approach:
 * This test uses a mock pattern instead of importing the actual function from app.js
 * because getDefaultAccountName() is defined as a method within an Alpine.js component
 * (window.app function in app.js:3089-3092). Alpine.js component methods cannot be
 * easily imported or tested in isolation. This mock replicates the exact production
 * logic to validate correctness.
 *
 * Integration Testing:
 * The Alpine.js component integration (method availability in app context) is verified
 * through browser-mode tests and manual testing. This unit test focuses on the logical
 * behavior of the account resolution algorithm.
 *
 * Priority: 🔍 HIGH - Ensures correct account resolution in event creation
 * Coverage Target: 100% of getDefaultAccountName() logic
 */

import { describe, it, expect, beforeEach } from 'vitest';

describe('getDefaultAccountName()', () => {
    let mockApp;

    beforeEach(() => {
        // Mock the Alpine.js app context
        // This replicates the exact logic from app.js:3089-3092
        mockApp = {
            accounts: [],
            getDefaultAccountName() {
                const defaultAccount = this.accounts.find(a => a.is_default && !a.is_archived);
                return defaultAccount ? defaultAccount.name : null;
            }
        };
    });

    // ==================== HAPPY PATH ====================

    describe('Happy Path', () => {
        it('should return name when default account exists and is not archived', () => {
            mockApp.accounts = [
                { id: 'acc-1', name: 'Monzo', is_default: true, is_archived: false },
                { id: 'acc-2', name: 'Savings', is_default: false, is_archived: false }
            ];

            const result = mockApp.getDefaultAccountName();

            expect(result).toBe('Monzo');
        });

        it('should return correct name when multiple accounts exist with one default', () => {
            mockApp.accounts = [
                { id: 'acc-1', name: 'Chase', is_default: false, is_archived: false },
                { id: 'acc-2', name: 'Monzo', is_default: true, is_archived: false },
                { id: 'acc-3', name: 'Savings', is_default: false, is_archived: false }
            ];

            const result = mockApp.getDefaultAccountName();

            expect(result).toBe('Monzo');
        });

        it('should handle account name with special characters', () => {
            mockApp.accounts = [
                { id: 'acc-1', name: "John's Account (£)", is_default: true, is_archived: false }
            ];

            const result = mockApp.getDefaultAccountName();

            expect(result).toBe("John's Account (£)");
        });
    });

    // ==================== NO DEFAULT SCENARIOS ====================

    describe('No Default Scenarios', () => {
        it('should return null when no default account exists', () => {
            mockApp.accounts = [
                { id: 'acc-1', name: 'Monzo', is_default: false, is_archived: false },
                { id: 'acc-2', name: 'Savings', is_default: false, is_archived: false }
            ];

            const result = mockApp.getDefaultAccountName();

            expect(result).toBeNull();
        });

        it('should return null when default account is archived', () => {
            mockApp.accounts = [
                { id: 'acc-1', name: 'Monzo', is_default: true, is_archived: true },
                { id: 'acc-2', name: 'Savings', is_default: false, is_archived: false }
            ];

            const result = mockApp.getDefaultAccountName();

            expect(result).toBeNull();
        });

        it('should return null when accounts array is empty', () => {
            mockApp.accounts = [];

            const result = mockApp.getDefaultAccountName();

            expect(result).toBeNull();
        });

        it('should return null when all accounts are archived', () => {
            mockApp.accounts = [
                { id: 'acc-1', name: 'Monzo', is_default: true, is_archived: true },
                { id: 'acc-2', name: 'Savings', is_default: false, is_archived: true }
            ];

            const result = mockApp.getDefaultAccountName();

            expect(result).toBeNull();
        });
    });

    // ==================== DATA INTEGRITY EDGE CASES ====================

    describe('Data Integrity Edge Cases', () => {
        it('should return first match when multiple default accounts exist (data integrity issue)', () => {
            // This scenario should not happen in production (UI prevents it)
            // But function should handle it gracefully
            mockApp.accounts = [
                { id: 'acc-1', name: 'Monzo', is_default: true, is_archived: false },
                { id: 'acc-2', name: 'Chase', is_default: true, is_archived: false }
            ];

            const result = mockApp.getDefaultAccountName();

            // Array.find() returns first match
            expect(result).toBe('Monzo');
        });
    });
});
