/**
 * Unit tests for dropdown-factories.js
 *
 * Tests dropdown factory functions for Alpine.js components:
 * - settingsDropdown: Persistent dropdowns in settings screens
 * - modalDropdown: Dynamic dropdowns in modals/forms
 *
 * CRITICAL: Dropdowns are core UI components - bugs cause poor UX
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { settingsDropdown, modalDropdown } from '../../../static/js/dropdown-factories.js';


// ============================================================================
// settingsDropdown Tests
// ============================================================================

describe('settingsDropdown', () => {
    describe('Parameter Validation', () => {
        it('should throw error when dropdownId is empty string', () => {
            expect(() => settingsDropdown('', [], () => null, () => {}))
                .toThrow('dropdownId must be a non-empty string');
        });

        it('should throw error when dropdownId is not a string', () => {
            expect(() => settingsDropdown(123, [], () => null, () => {}))
                .toThrow('dropdownId must be a non-empty string');
        });

        it('should throw error when dropdownId is null', () => {
            expect(() => settingsDropdown(null, [], () => null, () => {}))
                .toThrow('dropdownId must be a non-empty string');
        });

        it('should throw error when dropdownId is undefined', () => {
            expect(() => settingsDropdown(undefined, [], () => null, () => {}))
                .toThrow('dropdownId must be a non-empty string');
        });

        it('should throw error when options is not an array', () => {
            expect(() => settingsDropdown('test-id', 'not-array', () => null, () => {}))
                .toThrow('options must be an array');
        });

        it('should throw error when options is null', () => {
            expect(() => settingsDropdown('test-id', null, () => null, () => {}))
                .toThrow('options must be an array');
        });

        it('should throw error when getSelected is not a function', () => {
            expect(() => settingsDropdown('test-id', [], 'not-function', () => {}))
                .toThrow('getSelected must be a function');
        });

        it('should throw error when onSelect is not a function', () => {
            expect(() => settingsDropdown('test-id', [], () => null, 'not-function'))
                .toThrow('onSelect must be a function');
        });

        it('should accept valid parameters', () => {
            const dropdown = settingsDropdown('valid-id', [], () => null, () => {});
            expect(dropdown).toBeDefined();
            expect(dropdown.dropdownId).toBe('valid-id');
        });
    });

    describe('Initial State', () => {
        it('should initialize with open=false', () => {
            const dropdown = settingsDropdown('test', [], () => null, () => {});
            expect(dropdown.open).toBe(false);
        });

        it('should store provided options', () => {
            const options = [
                { value: 'GBP', label: 'British Pound' },
                { value: 'USD', label: 'US Dollar' }
            ];
            const dropdown = settingsDropdown('test', options, () => null, () => {});
            expect(dropdown.options).toEqual(options);
        });

        it('should store dropdownId', () => {
            const dropdown = settingsDropdown('currency-dropdown', [], () => null, () => {});
            expect(dropdown.dropdownId).toBe('currency-dropdown');
        });
    });

    describe('getSelectedLabel', () => {
        it('should return matching option label', () => {
            const options = [
                { value: 'GBP', label: 'British Pound' },
                { value: 'USD', label: 'US Dollar' }
            ];
            const dropdown = settingsDropdown('test', options, () => 'GBP', () => {});

            expect(dropdown.getSelectedLabel()).toBe('British Pound');
        });

        it('should return "Select..." when no match found', () => {
            const options = [
                { value: 'GBP', label: 'British Pound' }
            ];
            const dropdown = settingsDropdown('test', options, () => 'EUR', () => {});

            expect(dropdown.getSelectedLabel()).toBe('Select...');
        });

        it('should return "Select..." when getSelected returns null', () => {
            const options = [
                { value: 'GBP', label: 'British Pound' }
            ];
            const dropdown = settingsDropdown('test', options, () => null, () => {});

            expect(dropdown.getSelectedLabel()).toBe('Select...');
        });

        it('should return "Select..." when getSelected returns undefined', () => {
            const options = [
                { value: 'GBP', label: 'British Pound' }
            ];
            const dropdown = settingsDropdown('test', options, () => undefined, () => {});

            expect(dropdown.getSelectedLabel()).toBe('Select...');
        });

        it('should handle getSelected throwing error gracefully', () => {
            const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

            const dropdown = settingsDropdown('test', [], () => {
                throw new Error('Test error');
            }, () => {});

            expect(dropdown.getSelectedLabel()).toBe('Select...');
            expect(consoleSpy).toHaveBeenCalled();

            consoleSpy.mockRestore();
        });

        it('should handle options with value 0 (falsy but valid)', () => {
            const options = [
                { value: 0, label: 'Zero Option' },
                { value: 1, label: 'One Option' }
            ];
            const dropdown = settingsDropdown('test', options, () => 0, () => {});

            expect(dropdown.getSelectedLabel()).toBe('Zero Option');
        });

        it('should handle options with value "" (empty string)', () => {
            const options = [
                { value: '', label: 'Empty Option' },
                { value: 'non-empty', label: 'Non-Empty Option' }
            ];
            const dropdown = settingsDropdown('test', options, () => '', () => {});

            expect(dropdown.getSelectedLabel()).toBe('Empty Option');
        });
    });

    describe('selectOption', () => {
        it('should call onSelect with selected value', () => {
            const onSelectMock = vi.fn();
            const dropdown = settingsDropdown('test', [], () => null, onSelectMock);

            dropdown.selectOption('GBP');

            expect(onSelectMock).toHaveBeenCalledWith('GBP');
        });

        it('should close dropdown after selection', () => {
            const dropdown = settingsDropdown('test', [], () => null, () => {});
            dropdown.open = true;

            dropdown.selectOption('GBP');

            expect(dropdown.open).toBe(false);
        });

        it('should handle onSelect throwing error gracefully', () => {
            const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

            const dropdown = settingsDropdown('test', [], () => null, () => {
                throw new Error('Selection error');
            });
            dropdown.open = true;

            // Should not throw
            expect(() => dropdown.selectOption('GBP')).not.toThrow();
            expect(consoleSpy).toHaveBeenCalled();

            consoleSpy.mockRestore();
        });
    });

    describe('toggleOpen', () => {
        it('should toggle open state from false to true', () => {
            const dropdown = settingsDropdown('test', [], () => null, () => {});
            dropdown.$dispatch = vi.fn();
            dropdown.open = false;

            dropdown.toggleOpen();

            expect(dropdown.open).toBe(true);
        });

        it('should toggle open state from true to false', () => {
            const dropdown = settingsDropdown('test', [], () => null, () => {});
            dropdown.$dispatch = vi.fn();
            dropdown.open = true;

            dropdown.toggleOpen();

            expect(dropdown.open).toBe(false);
        });

        it('should dispatch dropdown-opened event when opening', () => {
            const dropdown = settingsDropdown('test-id', [], () => null, () => {});
            dropdown.$dispatch = vi.fn();
            dropdown.open = false;

            dropdown.toggleOpen();

            expect(dropdown.$dispatch).toHaveBeenCalledWith('dropdown-opened', { id: 'test-id' });
        });

        it('should NOT dispatch event when closing', () => {
            const dropdown = settingsDropdown('test-id', [], () => null, () => {});
            dropdown.$dispatch = vi.fn();
            dropdown.open = true;

            dropdown.toggleOpen();

            expect(dropdown.$dispatch).not.toHaveBeenCalled();
        });
    });
});


// ============================================================================
// modalDropdown Tests
// ============================================================================

describe('modalDropdown', () => {
    describe('Parameter Validation', () => {
        it('should throw error when options is null', () => {
            expect(() => modalDropdown(null, () => null, () => {}))
                .toThrow('options must be an array or function');
        });

        it('should throw error when options is string', () => {
            expect(() => modalDropdown('invalid', () => null, () => {}))
                .toThrow('options must be an array or function');
        });

        it('should throw error when options is number', () => {
            expect(() => modalDropdown(123, () => null, () => {}))
                .toThrow('options must be an array or function');
        });

        it('should throw error when getSelected is not a function', () => {
            expect(() => modalDropdown([], 'not-function', () => {}))
                .toThrow('getSelected must be a function');
        });

        it('should throw error when onSelect is not a function', () => {
            expect(() => modalDropdown([], () => null, 'not-function'))
                .toThrow('onSelect must be a function');
        });

        it('should accept array options', () => {
            const dropdown = modalDropdown([], () => null, () => {});
            expect(dropdown).toBeDefined();
        });

        it('should accept function options', () => {
            const dropdown = modalDropdown(() => [], () => null, () => {});
            expect(dropdown).toBeDefined();
        });
    });

    describe('options getter', () => {
        it('should return static array options directly', () => {
            const options = [
                { value: 'a', label: 'Option A' },
                { value: 'b', label: 'Option B' }
            ];
            const dropdown = modalDropdown(options, () => null, () => {});

            expect(dropdown.options).toEqual(options);
        });

        it('should call function options and return result', () => {
            const optionsFn = vi.fn(() => [
                { value: 'dynamic', label: 'Dynamic Option' }
            ]);
            const dropdown = modalDropdown(optionsFn, () => null, () => {});

            expect(dropdown.options).toEqual([{ value: 'dynamic', label: 'Dynamic Option' }]);
            expect(optionsFn).toHaveBeenCalled();
        });

        it('should return empty array when function returns non-array', () => {
            const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

            const dropdown = modalDropdown(() => 'not-array', () => null, () => {});

            expect(dropdown.options).toEqual([]);

            consoleSpy.mockRestore();
        });

        it('should return empty array when function throws error', () => {
            const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

            const dropdown = modalDropdown(() => {
                throw new Error('Options error');
            }, () => null, () => {});

            expect(dropdown.options).toEqual([]);
            expect(consoleSpy).toHaveBeenCalled();

            consoleSpy.mockRestore();
        });

        it('should return empty array when function returns null', () => {
            const dropdown = modalDropdown(() => null, () => null, () => {});
            expect(dropdown.options).toEqual([]);
        });
    });

    describe('selectedValue getter', () => {
        it('should return value from getSelected function', () => {
            const dropdown = modalDropdown([], () => 'selected-value', () => {});
            expect(dropdown.selectedValue).toBe('selected-value');
        });

        it('should return null when getSelected throws error', () => {
            const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

            const dropdown = modalDropdown([], () => {
                throw new Error('Selection error');
            }, () => {});

            expect(dropdown.selectedValue).toBeNull();
            expect(consoleSpy).toHaveBeenCalled();

            consoleSpy.mockRestore();
        });

        it('should handle getSelected returning 0 (falsy but valid)', () => {
            const dropdown = modalDropdown([], () => 0, () => {});
            expect(dropdown.selectedValue).toBe(0);
        });

        it('should handle getSelected returning false', () => {
            const dropdown = modalDropdown([], () => false, () => {});
            expect(dropdown.selectedValue).toBe(false);
        });
    });

    describe('hasError getter', () => {
        it('should return false when no errorState provided', () => {
            const dropdown = modalDropdown([], () => null, () => {}, 'Select...', null);
            expect(dropdown.hasError).toBe(false);
        });

        it('should return false when errorState is missing errorObject', () => {
            const dropdown = modalDropdown([], () => null, () => {}, 'Select...', {
                fieldName: 'currency'
            });
            expect(dropdown.hasError).toBe(false);
        });

        it('should return false when errorState is missing fieldName', () => {
            const dropdown = modalDropdown([], () => null, () => {}, 'Select...', {
                errorObject: { currency: true }
            });
            expect(dropdown.hasError).toBe(false);
        });

        it('should return true when field has error', () => {
            const errorObject = { currency: true, amount: false };
            const dropdown = modalDropdown([], () => null, () => {}, 'Select...', {
                errorObject,
                fieldName: 'currency'
            });
            expect(dropdown.hasError).toBe(true);
        });

        it('should return false when field has no error', () => {
            const errorObject = { currency: false, amount: true };
            const dropdown = modalDropdown([], () => null, () => {}, 'Select...', {
                errorObject,
                fieldName: 'currency'
            });
            expect(dropdown.hasError).toBe(false);
        });

        it('should handle error checking throwing exception', () => {
            const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

            const dropdown = modalDropdown([], () => null, () => {}, 'Select...', {
                errorObject: {
                    get currency() {
                        throw new Error('Access error');
                    }
                },
                fieldName: 'currency'
            });

            expect(dropdown.hasError).toBe(false);
            expect(consoleSpy).toHaveBeenCalled();

            consoleSpy.mockRestore();
        });
    });

    describe('getSelectedLabel', () => {
        it('should return matching option label', () => {
            const options = [
                { value: 'GBP', label: 'British Pound' },
                { value: 'USD', label: 'US Dollar' }
            ];
            const dropdown = modalDropdown(options, () => 'USD', () => {});

            expect(dropdown.getSelectedLabel()).toBe('US Dollar');
        });

        it('should return default label when no match', () => {
            const options = [{ value: 'GBP', label: 'British Pound' }];
            const dropdown = modalDropdown(options, () => 'EUR', () => {}, 'Choose currency');

            expect(dropdown.getSelectedLabel()).toBe('Choose currency');
        });

        it('should use "Select..." as default label', () => {
            const dropdown = modalDropdown([], () => null, () => {});
            expect(dropdown.getSelectedLabel()).toBe('Select...');
        });

        it('should use custom default label', () => {
            const dropdown = modalDropdown([], () => null, () => {}, 'Pick one');
            expect(dropdown.getSelectedLabel()).toBe('Pick one');
        });

        it('should handle label lookup throwing error', () => {
            const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

            // This tests when options getter returns invalid data
            const dropdown = modalDropdown(() => {
                throw new Error('Options error');
            }, () => null, () => {}, 'Default');

            expect(dropdown.getSelectedLabel()).toBe('Default');

            consoleSpy.mockRestore();
        });
    });

    describe('selectOption', () => {
        it('should call onSelect with value', () => {
            const onSelectMock = vi.fn();
            const dropdown = modalDropdown([], () => null, onSelectMock);

            dropdown.selectOption('EUR');

            expect(onSelectMock).toHaveBeenCalledWith('EUR');
        });

        it('should clear validation error on selection', () => {
            const errorObject = { currency: true };
            const onSelectMock = vi.fn();
            const dropdown = modalDropdown([], () => null, onSelectMock, 'Select...', {
                errorObject,
                fieldName: 'currency'
            });

            dropdown.selectOption('GBP');

            expect(errorObject.currency).toBe(false);
        });

        it('should handle onSelect throwing error gracefully', () => {
            const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

            const dropdown = modalDropdown([], () => null, () => {
                throw new Error('Selection error');
            });

            expect(() => dropdown.selectOption('GBP')).not.toThrow();
            expect(consoleSpy).toHaveBeenCalled();

            consoleSpy.mockRestore();
        });

        it('should not throw when errorState is null', () => {
            const onSelectMock = vi.fn();
            const dropdown = modalDropdown([], () => null, onSelectMock, 'Select...', null);

            expect(() => dropdown.selectOption('GBP')).not.toThrow();
            expect(onSelectMock).toHaveBeenCalledWith('GBP');
        });

        it('should not throw when errorState is missing fields', () => {
            const onSelectMock = vi.fn();
            const dropdown = modalDropdown([], () => null, onSelectMock, 'Select...', {});

            expect(() => dropdown.selectOption('GBP')).not.toThrow();
            expect(onSelectMock).toHaveBeenCalledWith('GBP');
        });
    });

    describe('Dynamic Options', () => {
        it('should re-evaluate options function on each access', () => {
            let callCount = 0;
            const optionsFn = vi.fn(() => {
                callCount++;
                return [{ value: callCount, label: `Option ${callCount}` }];
            });

            const dropdown = modalDropdown(optionsFn, () => null, () => {});

            // First access
            dropdown.options;
            expect(optionsFn).toHaveBeenCalledTimes(1);

            // Second access
            dropdown.options;
            expect(optionsFn).toHaveBeenCalledTimes(2);
        });

        it('should reflect changes in dynamic options', () => {
            let options = [{ value: 'a', label: 'A' }];

            const dropdown = modalDropdown(() => options, () => null, () => {});

            expect(dropdown.options).toEqual([{ value: 'a', label: 'A' }]);

            // Update options
            options = [{ value: 'b', label: 'B' }];

            expect(dropdown.options).toEqual([{ value: 'b', label: 'B' }]);
        });
    });
});


// ============================================================================
// Edge Cases and Integration Scenarios
// ============================================================================

describe('Dropdown Edge Cases', () => {
    describe('Unicode and Special Characters', () => {
        it('should handle unicode characters in labels', () => {
            const options = [
                { value: 'GBP', label: '£ British Pound' },
                { value: 'EUR', label: '€ Euro' },
                { value: 'JPY', label: '¥ Japanese Yen' }
            ];
            const dropdown = settingsDropdown('test', options, () => 'EUR', () => {});

            expect(dropdown.getSelectedLabel()).toBe('€ Euro');
        });

        it('should handle emoji in labels', () => {
            const options = [
                { value: 'good', label: '👍 Good' },
                { value: 'bad', label: '👎 Bad' }
            ];
            const dropdown = modalDropdown(options, () => 'good', () => {});

            expect(dropdown.getSelectedLabel()).toBe('👍 Good');
        });
    });

    describe('Large Datasets', () => {
        it('should handle large options array', () => {
            const options = Array.from({ length: 1000 }, (_, i) => ({
                value: `option-${i}`,
                label: `Option ${i}`
            }));

            const dropdown = settingsDropdown('test', options, () => 'option-500', () => {});

            expect(dropdown.getSelectedLabel()).toBe('Option 500');
        });
    });

    describe('Strict Equality', () => {
        it('should use strict equality for value matching', () => {
            const options = [
                { value: 1, label: 'Number 1' },
                { value: '1', label: 'String 1' }
            ];
            const dropdown = modalDropdown(options, () => 1, () => {});

            expect(dropdown.getSelectedLabel()).toBe('Number 1');
        });

        it('should differentiate null and undefined', () => {
            const options = [
                { value: null, label: 'Null Value' },
                { value: undefined, label: 'Undefined Value' }
            ];
            const dropdown = modalDropdown(options, () => null, () => {});

            expect(dropdown.getSelectedLabel()).toBe('Null Value');
        });
    });

    describe('Object Values', () => {
        it('should handle object values (by reference)', () => {
            const objA = { id: 1 };
            const objB = { id: 2 };
            const options = [
                { value: objA, label: 'Object A' },
                { value: objB, label: 'Object B' }
            ];

            // Same reference should match
            const dropdown = modalDropdown(options, () => objA, () => {});
            expect(dropdown.getSelectedLabel()).toBe('Object A');
        });

        it('should NOT match different objects with same content', () => {
            const objA = { id: 1 };
            const options = [
                { value: objA, label: 'Object A' }
            ];

            // Different object with same content should NOT match
            const dropdown = modalDropdown(options, () => ({ id: 1 }), () => {}, 'No Match');
            expect(dropdown.getSelectedLabel()).toBe('No Match');
        });
    });
});
