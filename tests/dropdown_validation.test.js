/**
 * CHAPTR - Dropdown Validation Integration Tests
 *
 * Tests custom dropdown components with error state integration
 * Covers modalDropdown and settingsDropdown from dropdown-factories.js
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { modalDropdown, settingsDropdown } from '../static/js/dropdown-factories.js';

describe('Dropdown Validation Integration', () => {
    describe('modalDropdown with errorState', () => {
        let errorObject;
        let selectedValue;
        let onSelectSpy;

        beforeEach(() => {
            errorObject = { account_id: false };
            selectedValue = '';
            onSelectSpy = vi.fn((value) => { selectedValue = value; });
        });

        it('should have hasError=false initially', () => {
            const dropdown = modalDropdown(
                [{ value: '1', label: 'Account 1' }],
                () => selectedValue,
                onSelectSpy,
                'Select...',
                { errorObject, fieldName: 'account_id' }
            );

            expect(dropdown.hasError).toBe(false);
        });

        it('should have hasError=true when error flag set', () => {
            errorObject.account_id = true;

            const dropdown = modalDropdown(
                [{ value: '1', label: 'Account 1' }],
                () => selectedValue,
                onSelectSpy,
                'Select...',
                { errorObject, fieldName: 'account_id' }
            );

            expect(dropdown.hasError).toBe(true);
        });

        it('should clear error on selectOption', () => {
            errorObject.account_id = true;

            const dropdown = modalDropdown(
                [{ value: '1', label: 'Account 1' }],
                () => selectedValue,
                onSelectSpy,
                'Select...',
                { errorObject, fieldName: 'account_id' }
            );

            dropdown.selectOption('1');

            expect(errorObject.account_id).toBe(false);
            expect(onSelectSpy).toHaveBeenCalledWith('1');
        });

        it('should handle null errorState gracefully', () => {
            const dropdown = modalDropdown(
                [{ value: '1', label: 'Account 1' }],
                () => selectedValue,
                onSelectSpy,
                'Select...',
                null
            );

            expect(dropdown.hasError).toBe(false);
            dropdown.selectOption('1'); // Should not throw
            expect(onSelectSpy).toHaveBeenCalledWith('1');
        });

        it('should handle missing fieldName in errorObject', () => {
            const dropdown = modalDropdown(
                [{ value: '1', label: 'Account 1' }],
                () => selectedValue,
                onSelectSpy,
                'Select...',
                { errorObject: { other_field: false }, fieldName: 'account_id' }
            );

            expect(dropdown.hasError).toBe(false);
        });

        it('should return correct selectedValue from getter', () => {
            selectedValue = '123';

            const dropdown = modalDropdown(
                [{ value: '123', label: 'Account 123' }],
                () => selectedValue,
                onSelectSpy,
                'Select...',
                { errorObject, fieldName: 'account_id' }
            );

            expect(dropdown.selectedValue).toBe('123');
        });

        it('should return correct label for selected value', () => {
            selectedValue = '123';

            const dropdown = modalDropdown(
                [
                    { value: '123', label: 'Account 123' },
                    { value: '456', label: 'Account 456' }
                ],
                () => selectedValue,
                onSelectSpy,
                'Select...',
                { errorObject, fieldName: 'account_id' }
            );

            expect(dropdown.getSelectedLabel()).toBe('Account 123');
        });

        it('should return default label when nothing selected', () => {
            selectedValue = '';

            const dropdown = modalDropdown(
                [{ value: '123', label: 'Account 123' }],
                () => selectedValue,
                onSelectSpy,
                'Custom Default',
                { errorObject, fieldName: 'account_id' }
            );

            expect(dropdown.getSelectedLabel()).toBe('Custom Default');
        });
    });

    describe('settingsDropdown (no errorState)', () => {
        let selectedValue;
        let onSelectSpy;

        beforeEach(() => {
            selectedValue = 'option1';
            onSelectSpy = vi.fn((value) => { selectedValue = value; });
        });

        it('should return correct selected label', () => {
            const dropdown = settingsDropdown(
                'test-dropdown',
                [
                    { value: 'option1', label: 'Option 1' },
                    { value: 'option2', label: 'Option 2' }
                ],
                () => selectedValue,
                onSelectSpy
            );

            expect(dropdown.getSelectedLabel()).toBe('Option 1');
        });

        it('should call onSelect when option selected', () => {
            const dropdown = settingsDropdown(
                'test-dropdown',
                [
                    { value: 'option1', label: 'Option 1' },
                    { value: 'option2', label: 'Option 2' }
                ],
                () => selectedValue,
                onSelectSpy
            );

            dropdown.selectOption('option2');

            expect(onSelectSpy).toHaveBeenCalledWith('option2');
        });

        it('should close dropdown after selection', () => {
            const dropdown = settingsDropdown(
                'test-dropdown',
                [
                    { value: 'option1', label: 'Option 1' },
                    { value: 'option2', label: 'Option 2' }
                ],
                () => selectedValue,
                onSelectSpy
            );

            dropdown.open = true;
            dropdown.selectOption('option2');

            expect(dropdown.open).toBe(false);
        });
    });
});
