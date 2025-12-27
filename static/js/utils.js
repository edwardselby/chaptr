/**
 * CHAPTR - Utility Functions
 *
 * Helper functions for formatting, API calls, and common operations
 */

/**
 * Format currency amount with symbol
 * @param {number} amount - Amount to format
 * @param {string} currency - Currency code (GBP, USD, EUR, CAD)
 * @returns {string} Formatted currency string
 */
export function formatCurrency(amount, currency = 'GBP') {
    const symbols = {
        'GBP': '£',
        'USD': '$',
        'EUR': '€',
        'CAD': '$'
    };

    const symbol = symbols[currency] || currency;
    const formatted = Math.abs(amount).toLocaleString('en-GB', {
        minimumFractionDigits: 0,
        maximumFractionDigits: 0
    });

    const sign = amount < 0 ? '-' : '';
    return `${sign}${symbol}${formatted}`;
}

/**
 * Get local date as YYYY-MM-DD string (no timezone conversion)
 * @param {Date} date - Date object
 * @returns {string} ISO date string in local timezone (e.g., "2025-12-26")
 */
export function toLocalISODate(date) {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
}

/**
 * Format date for display
 * @param {string|Date} dateStr - ISO date string or Date object
 * @returns {string} Formatted date (e.g., "Dec 18")
 */
export function formatDate(dateStr) {
    const date = typeof dateStr === 'string' ? new Date(dateStr) : dateStr;
    const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                   'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    return `${months[date.getMonth()]} ${date.getDate()}`;
}

/**
 * Format date range for display
 * @param {string} startDate - ISO date string
 * @param {string} endDate - ISO date string
 * @returns {string} Formatted range (e.g., "Dec 18 → Jan 18")
 */
export function formatDateRange(startDate, endDate) {
    if (!startDate || !endDate) return '';
    return `${formatDate(startDate)} → ${formatDate(endDate)}`;
}

/**
 * Format relative time (e.g., "2h ago", "3d ago")
 * @param {string} dateStr - ISO date string
 * @returns {string} Relative time string
 */
export function formatRelativeTime(dateStr) {
    const date = new Date(dateStr);
    const now = new Date();
    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    return `${diffDays}d ago`;
}

/**
 * Parse ISO date string to Date object
 * @param {string} dateStr - ISO date string (YYYY-MM-DD)
 * @returns {Date} Date object
 */
export function parseISODate(dateStr) {
    return new Date(dateStr + 'T00:00:00');
}

/**
 * Check if date is today
 * @param {string} dateStr - ISO date string
 * @returns {boolean} True if date is today
 */
export function isToday(dateStr) {
    const date = parseISODate(dateStr);
    const today = new Date();
    return date.toDateString() === today.toDateString();
}

/**
 * Check if date is in the past
 * @param {string} dateStr - ISO date string
 * @returns {boolean} True if date is in the past
 */
export function isPast(dateStr) {
    const date = parseISODate(dateStr);
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    return date < today;
}

/**
 * Calculate days between two dates
 * @param {string} startDate - ISO date string
 * @param {string} endDate - ISO date string
 * @returns {number} Number of days
 */
export function daysBetween(startDate, endDate) {
    const start = parseISODate(startDate);
    const end = parseISODate(endDate);
    const diffMs = end - start;
    return Math.floor(diffMs / 86400000);
}

/**
 * Get color class for amount (positive/negative)
 * @param {number} amount - Amount value
 * @returns {string} CSS class name
 */
export function colorForAmount(amount) {
    return amount >= 0 ? 'positive' : 'negative';
}

/**
 * Generate UUID v4
 * @returns {string} UUID string
 */
export function generateUUID() {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
        const r = Math.random() * 16 | 0;
        const v = c === 'x' ? r : (r & 0x3 | 0x8);
        return v.toString(16);
    });
}

/**
 * Get or create client ID for this device
 * @returns {Promise<string>} Client ID
 */
export async function getClientId() {
    let clientId = localStorage.getItem('client_id');
    if (!clientId) {
        clientId = generateUUID();
        localStorage.setItem('client_id', clientId);
    }
    return clientId;
}

/**
 * Make authenticated API request
 * @param {string} url - API endpoint URL
 * @param {object} options - Fetch options
 * @returns {Promise<Response>} Fetch response
 */
export async function apiRequest(url, options = {}) {
    const token = localStorage.getItem('auth_token');
    const headers = {
        'Content-Type': 'application/json',
        ...options.headers
    };

    if (token) {
        headers['Authorization'] = `Bearer ${token}`;
    }

    const response = await fetch(url, { ...options, headers });

    // Handle 401 Unauthorized - clear auth and reload to show login screen
    if (response.status === 401) {
        clearAuth();
        window.location.reload();
        throw new Error('Unauthorized');
    }

    return response;
}

/**
 * Store JWT token
 * @param {string} token - JWT token
 */
export function storeToken(token) {
    localStorage.setItem('auth_token', token);
}

/**
 * Get stored JWT token
 * @returns {string|null} JWT token or null
 */
export function getToken() {
    return localStorage.getItem('auth_token');
}

/**
 * Clear authentication (logout)
 */
export function clearAuth() {
    localStorage.removeItem('auth_token');
    localStorage.removeItem('user');
}

/**
 * Check if user is authenticated
 * @returns {boolean} True if JWT token exists
 */
export function isAuthenticated() {
    return !!getToken();
}

/**
 * Show toast notification
 *
 * @param {string} message - Message to display
 * @param {string} type - Toast type: 'success' | 'error' | 'warning' | 'info'
 * @param {number} duration - Duration in ms (default: 3000)
 */
export function showToast(message, type = 'info', duration = 3000) {
    // Create toast container if it doesn't exist
    let container = document.getElementById('toast-container');
    if (!container) {
        container = document.createElement('div');
        container.id = 'toast-container';
        container.className = 'toast-container';
        document.body.appendChild(container);
    }

    // Create toast element
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;

    // Add to container
    container.appendChild(toast);

    // Trigger animation
    setTimeout(() => toast.classList.add('show'), 10);

    // Remove after duration
    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => toast.remove(), 300); // Wait for fade out
    }, duration);
}

/**
 * Get mode-aware error message
 *
 * Returns appropriate error message based on current storage mode.
 *
 * @param {string} mode - Current storage mode ('full' | 'sync-only' | 'basic')
 * @param {string} operation - Operation that failed (e.g., 'save account')
 * @returns {string} Mode-aware error message
 */
export function getModeAwareErrorMessage(mode, operation) {
    const messages = {
        'full': `Failed to ${operation}. Changes queued for sync.`,
        'sync-only': `Failed to ${operation}. Please check connection and try again.`,
        'basic': `Failed to ${operation}. Refresh and retry.`
    };

    return messages[mode] || `Failed to ${operation}.`;
}

/**
 * Alias for getClientId() for backward compatibility
 * @returns {Promise<string>} Client ID
 */
export const generateClientId = getClientId;
