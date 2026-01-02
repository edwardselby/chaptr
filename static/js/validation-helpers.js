/**
 * CHAPTR - Validation Helpers Module
 *
 * Centralized validation functions for HTML5 + business logic validation
 * across all forms in the CHAPTR application.
 *
 * @module validation-helpers
 */

export const ValidationHelpers = {
    /**
     * Reset all error flags in an error object
     *
     * @param {Object} errorObject - Error tracking object with boolean flags
     * @example
     * const errors = { name: true, email: true };
     * resetFormErrors(errors); // { name: false, email: false }
     */
    resetFormErrors(errorObject) {
        Object.keys(errorObject).forEach(key => {
            errorObject[key] = false;
        });
    },

    /**
     * Validate HTML5 form constraints and map failures to error object
     *
     * Uses form.checkValidity() to trigger native HTML5 validation,
     * then maps failed inputs to the error tracking object by parsing
     * the x-model attribute to extract field names.
     *
     * @param {HTMLFormElement} formElement - The form element to validate
     * @param {Object} errorObject - Error tracking object
     * @returns {boolean} true if form is valid, false otherwise
     *
     * @example
     * const form = this.$refs.accountFormElement;
     * const isValid = validateHTML5(form, this.accountFormErrors);
     */
    validateHTML5(formElement, errorObject) {
        const isValid = formElement.checkValidity();

        if (!isValid) {
            const inputs = formElement.querySelectorAll('input, select, textarea');

            inputs.forEach(input => {
                if (!input.validity.valid) {
                    // Extract field name from x-model attribute
                    // e.g., "accountForm.name" => "name"
                    // Handles nested paths (form.nested.field) and simple bindings (username)
                    const xModel = input.getAttribute('x-model');
                    if (xModel) {
                        const fieldName = xModel.includes('.')
                            ? xModel.split('.').pop()  // Get last segment (handles nested paths)
                            : xModel;  // Handle simple bindings without dots
                        if (fieldName && Object.prototype.hasOwnProperty.call(errorObject, fieldName)) {
                            errorObject[fieldName] = true;
                        }
                    }
                }
            });
        }

        return isValid;
    },

    /**
     * Validate custom dropdown selection (non-HTML5 inputs)
     *
     * Custom dropdowns don't trigger HTML5 validation, so we validate
     * them manually. Checks if a value is selected when required.
     *
     * @param {string} value - Selected value from dropdown
     * @param {string} fieldName - Name of field in error object
     * @param {Object} errorObject - Error tracking object
     * @param {boolean} [isRequired=true] - Whether the field is required
     * @returns {boolean} true if valid, false otherwise
     *
     * @example
     * validateCustomDropdown(
     *     balanceForm.account_id,
     *     'account_id',
     *     balanceFormErrors,
     *     true
     * );
     */
    validateCustomDropdown(value, fieldName, errorObject, isRequired = true) {
        if (isRequired && (value === null || value === undefined || value === '')) {
            errorObject[fieldName] = true;
            return false;
        }
        return true;
    },

    /**
     * Validate date range (end date must be >= start date)
     *
     * @param {string} startDate - Start date (ISO format)
     * @param {string} endDate - End date (ISO format)
     * @param {Object} errorObject - Error tracking object
     * @param {string} [errorField='end_date'] - Which field to mark as invalid
     * @returns {boolean} true if valid, false otherwise
     *
     * @example
     * validateDateRange(
     *     storyForm.start_date,
     *     storyForm.end_date,
     *     storyFormErrors,
     *     'end_date'
     * );
     */
    validateDateRange(startDate, endDate, errorObject, errorField = 'end_date') {
        if (endDate && startDate && endDate < startDate) {
            errorObject[errorField] = true;
            return false;
        }
        return true;
    },

    /**
     * Validate currency code pattern (3 uppercase letters)
     *
     * @param {string} value - Currency code to validate
     * @param {Object} errorObject - Error tracking object
     * @param {string} fieldName - Name of field in error object
     * @returns {boolean} true if valid, false otherwise
     *
     * @example
     * validateCurrencyCode('GBP', accountFormErrors, 'currency'); // true
     * validateCurrencyCode('gb', accountFormErrors, 'currency'); // false
     */
    validateCurrencyCode(value, errorObject, fieldName) {
        if (value && !/^[A-Z]{3}$/.test(value)) {
            errorObject[fieldName] = true;
            return false;
        }
        return true;
    },

    /**
     * Validate conditional required field
     *
     * Field is only required when a condition is met. Useful for
     * fields that depend on other field values.
     *
     * @param {boolean} condition - Whether the field is required
     * @param {*} value - Field value
     * @param {Object} errorObject - Error tracking object
     * @param {string} fieldName - Name of field in error object
     * @returns {boolean} true if valid, false otherwise
     *
     * @example
     * // funding_amount only required when mode is 'fixed'
     * validateConditionalRequired(
     *     storyForm.funding_mode === 'fixed',
     *     storyForm.funding_amount,
     *     storyFormErrors,
     *     'funding_amount'
     * );
     */
    validateConditionalRequired(condition, value, errorObject, fieldName) {
        if (condition && (value === null || value === undefined || value === '')) {
            errorObject[fieldName] = true;
            return false;
        }
        return true;
    },

    /**
     * Count total errors in error object
     *
     * @param {Object} errorObject - Error tracking object
     * @returns {number} Number of fields with errors
     *
     * @example
     * const count = countErrors(accountFormErrors); // 2
     * showNotification(`Please fix ${count} field(s)`, 'error');
     */
    countErrors(errorObject) {
        return Object.values(errorObject).filter(Boolean).length;
    }
};
