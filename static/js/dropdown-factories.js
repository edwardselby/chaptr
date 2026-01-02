/**
 * CHAPTR - Dropdown Factory Functions
 *
 * Production-ready reusable dropdown components for Alpine.js
 * These must be available before Alpine initializes
 */

/**
 * Settings page dropdown factory
 * Used for persistent dropdowns in settings screens
 *
 * @param {string} dropdownId - Unique ID for this dropdown instance
 * @param {Array<{value: any, label: string}>} options - Array of option objects
 * @param {Function} getSelected - Function that returns current selected value
 * @param {Function} onSelect - Callback when option is selected
 * @returns {object} Alpine.js component
 * @throws {Error} If required parameters are invalid
 */
export const settingsDropdown = (dropdownId, options, getSelected, onSelect) => {
    // Validate required parameters
    if (!dropdownId || typeof dropdownId !== 'string') {
        throw new Error('settingsDropdown: dropdownId must be a non-empty string');
    }
    if (!Array.isArray(options)) {
        throw new Error('settingsDropdown: options must be an array');
    }
    if (typeof getSelected !== 'function') {
        throw new Error('settingsDropdown: getSelected must be a function');
    }
    if (typeof onSelect !== 'function') {
        throw new Error('settingsDropdown: onSelect must be a function');
    }

    return {
        dropdownId,
        open: false,
        options,

        getSelectedLabel() {
            try {
                const selectedValue = getSelected();
                const opt = this.options?.find(o => o.value === selectedValue);
                return opt?.label ?? 'Select...';
            } catch (error) {
                console.error(`[Dropdown ${this.dropdownId}] Error getting selected label:`, error);
                return 'Select...';
            }
        },

        selectOption(value) {
            try {
                onSelect(value);
                this.open = false;
            } catch (error) {
                console.error(`[Dropdown ${this.dropdownId}] Error selecting option:`, error);
            }
        },

        toggleOpen() {
            this.open = !this.open;
            if (this.open) {
                this.$dispatch('dropdown-opened', { id: this.dropdownId });
            }
        }
    };
};

/**
 * Modal dropdown factory
 * Used for dynamic dropdowns in modals and forms
 * Supports both static options and dynamic option functions
 *
 * @param {Array<{value: any, label: string}>|Function} options - Static array or function returning options
 * @param {Function} getSelected - Function that returns current selected value
 * @param {Function} onSelect - Callback when option is selected
 * @param {string} [defaultLabel='Select...'] - Label shown when nothing selected
 * @param {object} [errorState=null] - Optional validation state { errorObject, fieldName }
 * @returns {object} Alpine.js component
 * @throws {Error} If required parameters are invalid
 */
export const modalDropdown = (options, getSelected, onSelect, defaultLabel = 'Select...', errorState = null) => {
    // Validate required parameters
    if (!options || (typeof options !== 'function' && !Array.isArray(options))) {
        throw new Error('modalDropdown: options must be an array or function');
    }
    if (typeof getSelected !== 'function') {
        throw new Error('modalDropdown: getSelected must be a function');
    }
    if (typeof onSelect !== 'function') {
        throw new Error('modalDropdown: onSelect must be a function');
    }

    return {
        get options() {
            try {
                const result = typeof options === 'function' ? options() : options;
                return Array.isArray(result) ? result : [];
            } catch (error) {
                console.error('[Modal Dropdown] Error evaluating options:', error);
                return [];
            }
        },

        get selectedValue() {
            try {
                return getSelected();
            } catch (error) {
                console.error('[Modal Dropdown] Error getting selected value:', error);
                return null;
            }
        },

        get hasError() {
            try {
                // Only access the specific property we need (limits reactivity tracking)
                if (!errorState || !errorState.errorObject || !errorState.fieldName) {
                    return false;
                }
                const fieldName = errorState.fieldName;
                return Boolean(errorState.errorObject[fieldName]);
            } catch (error) {
                console.error('[Modal Dropdown] Error checking error state:', error);
                return false;
            }
        },

        getSelectedLabel() {
            try {
                const opt = this.options?.find(o => o.value === this.selectedValue);
                return opt?.label ?? defaultLabel;
            } catch (error) {
                console.error('[Modal Dropdown] Error getting selected label:', error);
                return defaultLabel;
            }
        },

        selectOption(value) {
            try {
                onSelect(value);
                // Clear validation error when user selects an option
                if (errorState && errorState.errorObject && errorState.fieldName) {
                    errorState.errorObject[errorState.fieldName] = false;
                }
            } catch (error) {
                console.error('[Modal Dropdown] Error selecting option:', error);
            }
        }
    };
};
