/**
 * CHAPTR - Form Validation Integration Tests
 *
 * Integration tests for HTML5 validation system with real forms
 * Tests validateHTML5 function with actual form elements
 */

import { describe, it, expect, beforeEach } from 'vitest';
import { ValidationHelpers } from '../../../static/js/validation-helpers.js';

describe('Form Validation Integration - validateHTML5', () => {
    /**
     * Test 1: should map HTML5 validation failures to error object
     * Tests that invalid fields are correctly mapped to error object
     */
    it('should map HTML5 validation failures to error object', () => {
        // Create a real form with required fields
        const form = document.createElement('form');

        // Add input with x-model and required (should fail validation)
        const nameInput = document.createElement('input');
        nameInput.setAttribute('x-model', 'accountForm.name');
        nameInput.setAttribute('required', '');
        nameInput.value = ''; // Empty = invalid
        form.appendChild(nameInput);

        // Add another field that's not in error object (should be ignored)
        const emailInput = document.createElement('input');
        emailInput.setAttribute('x-model', 'accountForm.email');
        emailInput.setAttribute('required', '');
        emailInput.value = ''; // Empty = invalid
        form.appendChild(emailInput);

        // Attach to DOM for HTML5 validation to work
        document.body.appendChild(form);

        const errors = { name: false, email: false };
        const result = ValidationHelpers.validateHTML5(form, errors);

        // Clean up
        document.body.removeChild(form);

        // Form should be invalid
        expect(result).toBe(false);

        // Name field should have error
        expect(errors.name).toBe(true);

        // Email field should have error
        expect(errors.email).toBe(true);
    });

    /**
     * Test 2: should handle multiple invalid fields
     * Tests that multiple invalid fields are all mapped correctly
     */
    it('should handle multiple invalid fields', () => {
        const form = document.createElement('form');

        // Add three inputs - two invalid, one valid
        const nameInput = document.createElement('input');
        nameInput.setAttribute('x-model', 'accountForm.name');
        nameInput.setAttribute('required', '');
        nameInput.value = ''; // Invalid
        form.appendChild(nameInput);

        const emailInput = document.createElement('input');
        emailInput.setAttribute('x-model', 'accountForm.email');
        emailInput.setAttribute('required', '');
        emailInput.value = ''; // Invalid
        form.appendChild(emailInput);

        const phoneInput = document.createElement('input');
        phoneInput.setAttribute('x-model', 'accountForm.phone');
        phoneInput.value = 'valid'; // Valid (not required)
        form.appendChild(phoneInput);

        document.body.appendChild(form);

        const errors = { name: false, email: false, phone: false };
        const result = ValidationHelpers.validateHTML5(form, errors);

        document.body.removeChild(form);

        // Form should be invalid
        expect(result).toBe(false);

        // Invalid fields should have errors
        expect(errors.name).toBe(true);
        expect(errors.email).toBe(true);

        // Valid field should not have error
        expect(errors.phone).toBe(false);
    });

    /**
     * Test 3: should parse x-model with dot notation (accountForm.name)
     * Tests standard dot notation parsing
     */
    it('should parse x-model with dot notation (accountForm.name)', () => {
        const form = document.createElement('form');

        const input = document.createElement('input');
        input.setAttribute('x-model', 'accountForm.name');
        input.setAttribute('required', '');
        input.value = ''; // Invalid
        form.appendChild(input);

        document.body.appendChild(form);

        const errors = { name: false };
        ValidationHelpers.validateHTML5(form, errors);

        document.body.removeChild(form);

        expect(errors.name).toBe(true);
    });

    /**
     * Test 4: should parse x-model with nested paths (form.nested.field)
     * Tests deeply nested x-model attribute parsing
     */
    it('should parse x-model with nested paths (form.nested.field)', () => {
        const form = document.createElement('form');

        const input = document.createElement('input');
        input.setAttribute('x-model', 'form.nested.field');
        input.setAttribute('required', '');
        input.value = ''; // Invalid
        form.appendChild(input);

        document.body.appendChild(form);

        const errors = { field: false };
        ValidationHelpers.validateHTML5(form, errors);

        document.body.removeChild(form);

        expect(errors.field).toBe(true);
    });

    /**
     * Test 5: should parse x-model without dots (username)
     * Tests simple x-model without dot notation
     */
    it('should parse x-model without dots (username)', () => {
        const form = document.createElement('form');

        const input = document.createElement('input');
        input.setAttribute('x-model', 'username');
        input.setAttribute('required', '');
        input.value = ''; // Invalid
        form.appendChild(input);

        document.body.appendChild(form);

        const errors = { username: false };
        ValidationHelpers.validateHTML5(form, errors);

        document.body.removeChild(form);

        expect(errors.username).toBe(true);
    });

    /**
     * Test 6: should handle mixed valid/invalid inputs
     * Tests combination of valid and invalid fields
     */
    it('should handle mixed valid/invalid inputs', () => {
        const form = document.createElement('form');

        const validInput = document.createElement('input');
        validInput.setAttribute('x-model', 'form.valid');
        validInput.value = 'has value'; // Valid (not required)
        form.appendChild(validInput);

        const invalidInput = document.createElement('input');
        invalidInput.setAttribute('x-model', 'form.invalid');
        invalidInput.setAttribute('required', '');
        invalidInput.value = ''; // Invalid
        form.appendChild(invalidInput);

        document.body.appendChild(form);

        const errors = { valid: false, invalid: false };
        ValidationHelpers.validateHTML5(form, errors);

        document.body.removeChild(form);

        expect(errors.valid).toBe(false);
        expect(errors.invalid).toBe(true);
    });

    /**
     * Test 7: should query all form input types (input, select, textarea)
     * Tests that validateHTML5 checks all form element types
     */
    it('should query all form input types (input, select, textarea)', () => {
        const form = document.createElement('form');

        const input = document.createElement('input');
        input.setAttribute('x-model', 'form.input');
        input.setAttribute('required', '');
        input.value = ''; // Invalid
        form.appendChild(input);

        const select = document.createElement('select');
        select.setAttribute('x-model', 'form.select');
        select.setAttribute('required', '');
        // Empty select = invalid
        form.appendChild(select);

        const textarea = document.createElement('textarea');
        textarea.setAttribute('x-model', 'form.textarea');
        textarea.setAttribute('required', '');
        textarea.value = ''; // Invalid
        form.appendChild(textarea);

        document.body.appendChild(form);

        const errors = { input: false, select: false, textarea: false };
        ValidationHelpers.validateHTML5(form, errors);

        document.body.removeChild(form);

        expect(errors.input).toBe(true);
        expect(errors.select).toBe(true);
        expect(errors.textarea).toBe(true);
    });

    /**
     * Test 8: should handle deeply nested x-model paths
     * Tests very deeply nested attribute paths
     */
    it('should handle deeply nested x-model paths', () => {
        const form = document.createElement('form');

        const input = document.createElement('input');
        input.setAttribute('x-model', 'app.module.form.nested.field');
        input.setAttribute('required', '');
        input.value = ''; // Invalid
        form.appendChild(input);

        document.body.appendChild(form);

        const errors = { field: false };
        ValidationHelpers.validateHTML5(form, errors);

        document.body.removeChild(form);

        expect(errors.field).toBe(true);
    });
});
