/**
 * CHAPTR - Validation Helpers Unit Tests
 *
 * Comprehensive test coverage for validation-helpers.js module
 * Tests all 6 exported validation functions with edge cases
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { ValidationHelpers } from '../../../static/js/validation-helpers.js';

/**
 * Test Utilities - DOM Element Creation
 */

/**
 * Create a form element with inputs (real HTML5 validation)
 */
function createMockForm(fieldValues, isValid) {
    const form = document.createElement('form');

    Object.entries(fieldValues).forEach(([name, value]) => {
        const input = document.createElement('input');
        input.setAttribute('x-model', `accountForm.${name}`);
        input.value = value;
        // Set required attribute to trigger validation
        if (!isValid) {
            input.setAttribute('required', '');
            input.value = ''; // Empty value makes it invalid
        }
        form.appendChild(input);
    });

    return form;
}

/**
 * Create a single input element with x-model attribute
 */
function createInput(xModelValue, isValid) {
    const input = document.createElement('input');
    if (xModelValue) input.setAttribute('x-model', xModelValue);
    // Set required attribute to make it invalid when needed
    if (!isValid) {
        input.setAttribute('required', '');
        input.value = ''; // Empty value = invalid
    }
    return input;
}

/**
 * Create a form from array of inputs
 */
function createForm(inputs, isValid) {
    const form = document.createElement('form');
    inputs.forEach(input => form.appendChild(input));
    return form;
}

/**
 * Create select element (for querySelectorAll tests)
 */
function createSelect(xModelValue, isValid) {
    const select = document.createElement('select');
    if (xModelValue) select.setAttribute('x-model', xModelValue);
    // Set required attribute to make it invalid when needed
    if (!isValid) {
        select.setAttribute('required', '');
        // Don't add any options, so it's invalid
    }
    return select;
}

/**
 * Create textarea element (for querySelectorAll tests)
 */
function createTextarea(xModelValue, isValid) {
    const textarea = document.createElement('textarea');
    if (xModelValue) textarea.setAttribute('x-model', xModelValue);
    // Set required attribute to make it invalid when needed
    if (!isValid) {
        textarea.setAttribute('required', '');
        textarea.value = ''; // Empty value = invalid
    }
    return textarea;
}

/**
 * Helper to test validateHTML5 with DOM attachment
 */
function testValidateHTML5(form, errorObject) {
    document.body.appendChild(form);
    const result = ValidationHelpers.validateHTML5(form, errorObject);
    document.body.removeChild(form);
    return result;
}

/**
 * Validation Helpers Test Suite
 */
describe('ValidationHelpers Module', () => {
    /**
     * Test 1: resetFormErrors(errorObject)
     */
    describe('resetFormErrors', () => {
        it('should reset all error flags to false', () => {
            const errors = { name: true, email: true, age: true };
            ValidationHelpers.resetFormErrors(errors);
            expect(errors).toEqual({ name: false, email: false, age: false });
        });

        it('should handle empty error object', () => {
            const errors = {};
            ValidationHelpers.resetFormErrors(errors);
            expect(errors).toEqual({});
        });

        it('should not add new properties', () => {
            const errors = { name: true };
            ValidationHelpers.resetFormErrors(errors);
            expect(Object.keys(errors)).toEqual(['name']);
        });
    });

    /**
     * Test 2: validateHTML5(formElement, errorObject)
     */
    describe('validateHTML5', () => {
        // Basic Validation
        it('should return true for valid form', () => {
            const form = createMockForm({ name: 'valid', email: 'test@example.com' }, true);
            const errors = { name: false, email: false };
            const result = ValidationHelpers.validateHTML5(form, errors);
            expect(result).toBe(true);
            expect(errors).toEqual({ name: false, email: false });
        });

        it('should return false for invalid form', () => {
            const form = createMockForm({ name: '', email: 'invalid' }, false);
            const errors = { name: false, email: false };
            const result = ValidationHelpers.validateHTML5(form, errors);
            expect(result).toBe(false);
        });

        it('should ignore fields not in error object', () => {
            const input = createInput('x-model="accountForm.unknownField"', false);
            const form = createForm([input], false);
            const errors = { name: false };
            ValidationHelpers.validateHTML5(form, errors);
            expect(errors.name).toBe(false); // shouldn't change
        });

        // Edge Cases
        it('should handle inputs without x-model attribute', () => {
            const input = createInput(null, false);
            const form = createForm([input], false);
            const errors = { name: false };
            expect(() => ValidationHelpers.validateHTML5(form, errors)).not.toThrow();
        });

        // Security
        it('should use safe hasOwnProperty check', () => {
            const errorObject = Object.create(null); // null prototype
            errorObject.name = false;
            const input = createInput('x-model="accountForm.name"', false);
            const form = createForm([input], false);
            expect(() => ValidationHelpers.validateHTML5(form, errorObject)).not.toThrow();
        });

        // Additional edge cases
        it('should handle form with no inputs', () => {
            const form = createForm([], true);
            const errors = { name: false };
            const result = ValidationHelpers.validateHTML5(form, errors);
            expect(result).toBe(true);
        });

        it('should handle x-model with spaces (trimmed)', () => {
            const input = createInput('x-model="  form.field  "', false);
            const form = createForm([input], false);
            const errors = { field: false };
            ValidationHelpers.validateHTML5(form, errors);
            // Should not throw, behavior depends on trim implementation
            expect(() => ValidationHelpers.validateHTML5(form, errors)).not.toThrow();
        });

    });

    /**
     * Test 3: validateCustomDropdown(value, fieldName, errorObject, isRequired)
     */
    describe('validateCustomDropdown', () => {
        it('should return true for valid required dropdown with value', () => {
            const errors = { account: false };
            const result = ValidationHelpers.validateCustomDropdown('acc-123', 'account', errors, true);
            expect(result).toBe(true);
            expect(errors.account).toBe(false);
        });

        it('should return false for empty required dropdown', () => {
            const errors = { account: false };
            const result = ValidationHelpers.validateCustomDropdown('', 'account', errors, true);
            expect(result).toBe(false);
            expect(errors.account).toBe(true);
        });

        it('should return false for null required dropdown', () => {
            const errors = { account: false };
            const result = ValidationHelpers.validateCustomDropdown(null, 'account', errors, true);
            expect(result).toBe(false);
            expect(errors.account).toBe(true);
        });

        it('should return false for undefined required dropdown', () => {
            const errors = { account: false };
            const result = ValidationHelpers.validateCustomDropdown(undefined, 'account', errors, true);
            expect(result).toBe(false);
            expect(errors.account).toBe(true);
        });

        it('should return true for empty optional dropdown', () => {
            const errors = { account: false };
            const result = ValidationHelpers.validateCustomDropdown('', 'account', errors, false);
            expect(result).toBe(true);
            expect(errors.account).toBe(false);
        });

        it('should return true for null optional dropdown', () => {
            const errors = { account: false };
            const result = ValidationHelpers.validateCustomDropdown(null, 'account', errors, false);
            expect(result).toBe(true);
            expect(errors.account).toBe(false);
        });

        it('should handle numeric values (account IDs)', () => {
            const errors = { account: false };
            const result = ValidationHelpers.validateCustomDropdown(123, 'account', errors, true);
            expect(result).toBe(true);
            expect(errors.account).toBe(false);
        });

        it('should handle zero as a valid value', () => {
            const errors = { index: false };
            const result = ValidationHelpers.validateCustomDropdown(0, 'index', errors, true);
            expect(result).toBe(true);
            expect(errors.index).toBe(false);
        });
    });

    /**
     * Test 4: validateDateRange(startDate, endDate, errorObject, errorField)
     */
    describe('validateDateRange', () => {
        it('should return true when end date is after start date', () => {
            const errors = { end_date: false };
            const result = ValidationHelpers.validateDateRange('2024-01-01', '2024-01-31', errors);
            expect(result).toBe(true);
            expect(errors.end_date).toBe(false);
        });

        it('should return false when end date is before start date', () => {
            const errors = { end_date: false };
            const result = ValidationHelpers.validateDateRange('2024-01-31', '2024-01-01', errors);
            expect(result).toBe(false);
            expect(errors.end_date).toBe(true);
        });

        it('should return true when dates are equal', () => {
            const errors = { end_date: false };
            const result = ValidationHelpers.validateDateRange('2024-01-15', '2024-01-15', errors);
            expect(result).toBe(true);
            expect(errors.end_date).toBe(false);
        });

        it('should return true when end date is null (ongoing)', () => {
            const errors = { end_date: false };
            const result = ValidationHelpers.validateDateRange('2024-01-01', null, errors);
            expect(result).toBe(true);
            expect(errors.end_date).toBe(false);
        });

        it('should return true when end date is empty string', () => {
            const errors = { end_date: false };
            const result = ValidationHelpers.validateDateRange('2024-01-01', '', errors);
            expect(result).toBe(true);
            expect(errors.end_date).toBe(false);
        });

        it('should return true when start date is null', () => {
            const errors = { end_date: false };
            const result = ValidationHelpers.validateDateRange(null, '2024-01-31', errors);
            expect(result).toBe(true);
            expect(errors.end_date).toBe(false);
        });

        it('should allow custom error field name', () => {
            const errors = { custom_field: false };
            const result = ValidationHelpers.validateDateRange('2024-01-31', '2024-01-01', errors, 'custom_field');
            expect(result).toBe(false);
            expect(errors.custom_field).toBe(true);
        });

        it('should handle ISO date-time strings', () => {
            const errors = { end_date: false };
            const result = ValidationHelpers.validateDateRange(
                '2024-01-01T10:00:00Z',
                '2024-01-01T09:00:00Z',
                errors
            );
            expect(result).toBe(false);
            expect(errors.end_date).toBe(true);
        });

        it('should compare dates as strings (lexicographic)', () => {
            const errors = { end_date: false };
            const result = ValidationHelpers.validateDateRange('2024-01-09', '2024-01-10', errors);
            expect(result).toBe(true);
        });

        it('should handle date objects', () => {
            const errors = { end_date: false };
            const start = new Date('2024-01-01');
            const end = new Date('2024-01-31');
            const result = ValidationHelpers.validateDateRange(start, end, errors);
            expect(result).toBe(true);
        });
    });

    /**
     * Test 5: validateCurrencyCode(value, errorObject, fieldName)
     */
    describe('validateCurrencyCode', () => {
        it('should return true for valid uppercase currency codes', () => {
            const errors = { currency: false };
            const result = ValidationHelpers.validateCurrencyCode('GBP', errors, 'currency');
            expect(result).toBe(true);
            expect(errors.currency).toBe(false);
        });

        it('should return false for lowercase currency codes', () => {
            const errors = { currency: false };
            const result = ValidationHelpers.validateCurrencyCode('gbp', errors, 'currency');
            expect(result).toBe(false);
            expect(errors.currency).toBe(true);
        });

        it('should return false for mixed case currency codes', () => {
            const errors = { currency: false };
            const result = ValidationHelpers.validateCurrencyCode('Gbp', errors, 'currency');
            expect(result).toBe(false);
            expect(errors.currency).toBe(true);
        });

        it('should return false for codes with less than 3 characters', () => {
            const errors = { currency: false };
            const result = ValidationHelpers.validateCurrencyCode('GB', errors, 'currency');
            expect(result).toBe(false);
            expect(errors.currency).toBe(true);
        });

        it('should return false for codes with more than 3 characters', () => {
            const errors = { currency: false };
            const result = ValidationHelpers.validateCurrencyCode('GBPP', errors, 'currency');
            expect(result).toBe(false);
            expect(errors.currency).toBe(true);
        });

        it('should return false for codes with numbers', () => {
            const errors = { currency: false };
            const result = ValidationHelpers.validateCurrencyCode('GB1', errors, 'currency');
            expect(result).toBe(false);
            expect(errors.currency).toBe(true);
        });

        it('should return false for codes with special characters', () => {
            const errors = { currency: false };
            const result = ValidationHelpers.validateCurrencyCode('GB$', errors, 'currency');
            expect(result).toBe(false);
            expect(errors.currency).toBe(true);
        });

        it('should return true for empty/null values (optional field)', () => {
            const errors = { currency: false };
            expect(ValidationHelpers.validateCurrencyCode('', errors, 'currency')).toBe(true);
            expect(ValidationHelpers.validateCurrencyCode(null, errors, 'currency')).toBe(true);
            expect(ValidationHelpers.validateCurrencyCode(undefined, errors, 'currency')).toBe(true);
        });

        it('should validate common currency codes', () => {
            const errors = { currency: false };
            const validCodes = ['USD', 'EUR', 'JPY', 'CAD', 'AUD', 'CHF'];
            validCodes.forEach(code => {
                expect(ValidationHelpers.validateCurrencyCode(code, errors, 'currency')).toBe(true);
            });
        });
    });

    /**
     * Test 6: validateConditionalRequired(condition, value, errorObject, fieldName)
     */
    describe('validateConditionalRequired', () => {
        it('should return true when condition is false', () => {
            const errors = { funding_amount: false };
            const result = ValidationHelpers.validateConditionalRequired(false, '', errors, 'funding_amount');
            expect(result).toBe(true);
            expect(errors.funding_amount).toBe(false);
        });

        it('should return true when condition is true and value provided', () => {
            const errors = { funding_amount: false };
            const result = ValidationHelpers.validateConditionalRequired(true, '1000', errors, 'funding_amount');
            expect(result).toBe(true);
            expect(errors.funding_amount).toBe(false);
        });

        it('should return false when condition is true and value is empty string', () => {
            const errors = { funding_amount: false };
            const result = ValidationHelpers.validateConditionalRequired(true, '', errors, 'funding_amount');
            expect(result).toBe(false);
            expect(errors.funding_amount).toBe(true);
        });

        it('should return false when condition is true and value is null', () => {
            const errors = { funding_amount: false };
            const result = ValidationHelpers.validateConditionalRequired(true, null, errors, 'funding_amount');
            expect(result).toBe(false);
            expect(errors.funding_amount).toBe(true);
        });

        it('should return false when condition is true and value is undefined', () => {
            const errors = { funding_amount: false };
            const result = ValidationHelpers.validateConditionalRequired(true, undefined, errors, 'funding_amount');
            expect(result).toBe(false);
            expect(errors.funding_amount).toBe(true);
        });

        it('should handle numeric zero as a valid value', () => {
            const errors = { funding_amount: false };
            const result = ValidationHelpers.validateConditionalRequired(true, 0, errors, 'funding_amount');
            expect(result).toBe(true);
            expect(errors.funding_amount).toBe(false);
        });

        it('should handle boolean false as a valid value', () => {
            const errors = { is_enabled: false };
            const result = ValidationHelpers.validateConditionalRequired(true, false, errors, 'is_enabled');
            expect(result).toBe(true);
            expect(errors.is_enabled).toBe(false);
        });

        it('should handle complex conditions (Story funding mode example)', () => {
            const errors = { funding_amount: false };
            const fundingMode = 'fixed';
            const condition = fundingMode === 'fixed' || fundingMode === 'projected_plus';
            const result = ValidationHelpers.validateConditionalRequired(condition, '', errors, 'funding_amount');
            expect(result).toBe(false);
            expect(errors.funding_amount).toBe(true);
        });
    });

    /**
     * Test 7: countErrors(errorObject)
     */
    describe('countErrors', () => {
        it('should count errors correctly', () => {
            const errors = { name: true, email: true, phone: false, age: true };
            expect(ValidationHelpers.countErrors(errors)).toBe(3);
        });

        it('should return 0 for object with no errors', () => {
            const errors = { name: false, email: false, phone: false };
            expect(ValidationHelpers.countErrors(errors)).toBe(0);
        });

        it('should return 0 for empty object', () => {
            expect(ValidationHelpers.countErrors({})).toBe(0);
        });

        it('should handle mixed truthy/falsy values', () => {
            const errors = {
                field1: true,      // 1
                field2: false,
                field3: 1,         // truthy, counts as error
                field4: 0,
                field5: 'error',   // truthy, counts as error
                field6: '',
                field7: null
            };
            expect(ValidationHelpers.countErrors(errors)).toBe(3);
        });
    });
});
