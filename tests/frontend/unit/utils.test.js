/**
 * Unit tests for CHAPTR utility functions
 *
 * Tests pure utility functions from static/js/utils.js
 */

import { describe, it, expect } from 'vitest';
import {
  formatCurrency,
  toLocalISODate,
  formatDate,
  formatDateRange,
  daysBetween,
  colorForAmount,
  generateUUID,
  parseISODate,
  isToday,
  isPast,
  getModeAwareErrorMessage,
} from '../../../static/js/utils.js';

describe('formatCurrency', () => {
  it('formats positive GBP amounts correctly', () => {
    expect(formatCurrency(1000, 'GBP')).toBe('£1,000');
    expect(formatCurrency(250, 'GBP')).toBe('£250');
    expect(formatCurrency(0, 'GBP')).toBe('£0');
  });

  it('formats negative amounts with sign', () => {
    expect(formatCurrency(-500, 'GBP')).toBe('-£500');
    expect(formatCurrency(-1250, 'USD')).toBe('-$1,250');
  });

  it('uses correct currency symbols', () => {
    expect(formatCurrency(100, 'GBP')).toBe('£100');
    expect(formatCurrency(100, 'USD')).toBe('$100');
    expect(formatCurrency(100, 'EUR')).toBe('€100');
    expect(formatCurrency(100, 'CAD')).toBe('$100');
  });

  it('falls back to currency code for unknown currencies', () => {
    expect(formatCurrency(100, 'JPY')).toBe('JPY100');
  });

  it('uses GBP as default currency', () => {
    expect(formatCurrency(500)).toBe('£500');
  });

  it('rounds to nearest whole number', () => {
    expect(formatCurrency(1234.56, 'GBP')).toBe('£1,235');
    expect(formatCurrency(999.99, 'USD')).toBe('$1,000');
  });

  // Edge case tests
  it('handles invalid currency codes', () => {
    expect(formatCurrency(100, null)).toBe('null100');
    expect(formatCurrency(100, '')).toBe('100');
  });
});

describe('toLocalISODate', () => {
  it('formats dates as YYYY-MM-DD', () => {
    const date = new Date(2025, 11, 31); // Dec 31, 2025 (month is 0-indexed)
    expect(toLocalISODate(date)).toBe('2025-12-31');
  });

  it('pads single-digit months and days with zeros', () => {
    const date = new Date(2025, 0, 5); // Jan 5, 2025
    expect(toLocalISODate(date)).toBe('2025-01-05');
  });

  it('handles leap years correctly', () => {
    const date = new Date(2024, 1, 29); // Feb 29, 2024
    expect(toLocalISODate(date)).toBe('2024-02-29');
  });
});

describe('formatDate', () => {
  it('formats dates as "Mon DD"', () => {
    expect(formatDate('2025-06-15')).toBe('Jun 15');
    expect(formatDate('2025-03-20')).toBe('Mar 20');
    expect(formatDate('2025-12-31')).toBe('Dec 31');
  });

  it('handles Date objects', () => {
    const date = new Date(2025, 11, 25); // Dec 25, 2025
    expect(formatDate(date)).toBe('Dec 25');
  });

  it('returns empty string for null/undefined', () => {
    expect(formatDate(null)).toBe('');
    expect(formatDate(undefined)).toBe('');
    expect(formatDate('')).toBe('');
  });

  it('handles invalid dates', () => {
    expect(formatDate('invalid-date')).toBe('');
  });
});

describe('formatDateRange', () => {
  it('formats date ranges with arrow', () => {
    expect(formatDateRange('2025-06-01', '2025-06-30')).toBe('Jun 1 → Jun 30');
    expect(formatDateRange('2025-01-01', '2025-12-31')).toBe('Jan 1 → Dec 31');
  });

  it('returns empty string for missing dates', () => {
    expect(formatDateRange('', '2025-12-31')).toBe('');
    expect(formatDateRange('2025-12-31', '')).toBe('');
    expect(formatDateRange('', '')).toBe('');
  });
});

describe('daysBetween', () => {
  it('calculates days between two dates', () => {
    expect(daysBetween('2025-01-01', '2025-01-10')).toBe(9);
    expect(daysBetween('2025-01-15', '2025-01-20')).toBe(5);
  });

  it('returns 0 for same date', () => {
    expect(daysBetween('2025-12-31', '2025-12-31')).toBe(0);
  });

  it('handles negative ranges (end before start)', () => {
    expect(daysBetween('2025-01-10', '2025-01-01')).toBe(-9);
  });

  it('handles month boundaries', () => {
    expect(daysBetween('2025-01-31', '2025-02-01')).toBe(1);
  });

  it('handles year boundaries', () => {
    expect(daysBetween('2024-12-31', '2025-01-01')).toBe(1);
  });

  // Edge case tests (documenting current behavior)
  it('throws error on null dates (current behavior)', () => {
    // Note: parseISODate doesn't validate input, will throw on null
    expect(() => daysBetween(null, '2025-01-01')).toThrow();
  });

  it('handles invalid date strings (returns NaN)', () => {
    const result = daysBetween('invalid', '2025-01-01');
    // Result will be NaN due to invalid date parsing
    expect(isNaN(result)).toBe(true);
  });
});

describe('colorForAmount', () => {
  it('returns "positive" for positive amounts', () => {
    expect(colorForAmount(100)).toBe('positive');
    expect(colorForAmount(0.01)).toBe('positive');
  });

  it('returns "positive" for zero', () => {
    expect(colorForAmount(0)).toBe('positive');
  });

  it('returns "negative" for negative amounts', () => {
    expect(colorForAmount(-100)).toBe('negative');
    expect(colorForAmount(-0.01)).toBe('negative');
  });
});

describe('generateUUID', () => {
  it('generates valid UUID v4 format', () => {
    const uuid = generateUUID();
    // UUID v4 format: xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx
    const uuidRegex = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
    expect(uuid).toMatch(uuidRegex);
  });

  it('generates unique UUIDs', () => {
    const uuid1 = generateUUID();
    const uuid2 = generateUUID();
    expect(uuid1).not.toBe(uuid2);
  });

  it('has correct length', () => {
    const uuid = generateUUID();
    expect(uuid.length).toBe(36); // 32 hex chars + 4 hyphens
  });

  // Edge case test
  it('generates multiple unique UUIDs consistently', () => {
    const uuids = new Set();
    for (let i = 0; i < 100; i++) {
      uuids.add(generateUUID());
    }
    // All 100 should be unique
    expect(uuids.size).toBe(100);
  });
});

describe('parseISODate', () => {
  it('parses ISO date strings to Date objects', () => {
    const date = parseISODate('2025-12-31');
    expect(date).toBeInstanceOf(Date);
    expect(date.getFullYear()).toBe(2025);
    expect(date.getMonth()).toBe(11); // December (0-indexed)
    expect(date.getDate()).toBe(31);
  });

  it('parses dates at local midnight', () => {
    const date = parseISODate('2025-06-15');
    expect(date.getHours()).toBe(0);
    expect(date.getMinutes()).toBe(0);
    expect(date.getSeconds()).toBe(0);
  });
});

describe('isToday', () => {
  it('returns true for today\'s date', () => {
    const today = new Date();
    const year = today.getFullYear();
    const month = String(today.getMonth() + 1).padStart(2, '0');
    const day = String(today.getDate()).padStart(2, '0');
    const todayISO = `${year}-${month}-${day}`;

    expect(isToday(todayISO)).toBe(true);
  });

  it('returns false for yesterday', () => {
    const yesterday = new Date();
    yesterday.setDate(yesterday.getDate() - 1);
    const year = yesterday.getFullYear();
    const month = String(yesterday.getMonth() + 1).padStart(2, '0');
    const day = String(yesterday.getDate()).padStart(2, '0');
    const yesterdayISO = `${year}-${month}-${day}`;

    expect(isToday(yesterdayISO)).toBe(false);
  });

  it('returns false for tomorrow', () => {
    const tomorrow = new Date();
    tomorrow.setDate(tomorrow.getDate() + 1);
    const year = tomorrow.getFullYear();
    const month = String(tomorrow.getMonth() + 1).padStart(2, '0');
    const day = String(tomorrow.getDate()).padStart(2, '0');
    const tomorrowISO = `${year}-${month}-${day}`;

    expect(isToday(tomorrowISO)).toBe(false);
  });

  it('returns false for dates far in the past', () => {
    expect(isToday('2020-01-01')).toBe(false);
    expect(isToday('1990-12-31')).toBe(false);
  });

  it('returns false for dates far in the future', () => {
    expect(isToday('2030-12-31')).toBe(false);
    expect(isToday('2100-01-01')).toBe(false);
  });
});

describe('isPast', () => {
  it('returns true for yesterday', () => {
    const yesterday = new Date();
    yesterday.setDate(yesterday.getDate() - 1);
    const year = yesterday.getFullYear();
    const month = String(yesterday.getMonth() + 1).padStart(2, '0');
    const day = String(yesterday.getDate()).padStart(2, '0');
    const yesterdayISO = `${year}-${month}-${day}`;

    expect(isPast(yesterdayISO)).toBe(true);
  });

  it('returns false for today (boundary case)', () => {
    const today = new Date();
    const year = today.getFullYear();
    const month = String(today.getMonth() + 1).padStart(2, '0');
    const day = String(today.getDate()).padStart(2, '0');
    const todayISO = `${year}-${month}-${day}`;

    expect(isPast(todayISO)).toBe(false);
  });

  it('returns false for tomorrow', () => {
    const tomorrow = new Date();
    tomorrow.setDate(tomorrow.getDate() + 1);
    const year = tomorrow.getFullYear();
    const month = String(tomorrow.getMonth() + 1).padStart(2, '0');
    const day = String(tomorrow.getDate()).padStart(2, '0');
    const tomorrowISO = `${year}-${month}-${day}`;

    expect(isPast(tomorrowISO)).toBe(false);
  });

  it('returns true for dates last year', () => {
    expect(isPast('2020-01-01')).toBe(true);
    expect(isPast('2024-01-01')).toBe(true);
  });

  it('returns false for dates next year', () => {
    expect(isPast('2030-12-31')).toBe(false);
    expect(isPast('2100-01-01')).toBe(false);
  });
});

describe('getModeAwareErrorMessage', () => {
  it('returns correct message for "full" mode', () => {
    const msg = getModeAwareErrorMessage('full', 'save account');
    expect(msg).toBe('Failed to save account. Changes queued for sync.');
  });

  it('returns correct message for "sync-only" mode', () => {
    const msg = getModeAwareErrorMessage('sync-only', 'delete event');
    expect(msg).toBe('Failed to delete event. Please check connection and try again.');
  });

  it('returns correct message for "basic" mode', () => {
    const msg = getModeAwareErrorMessage('basic', 'update story');
    expect(msg).toBe('Failed to update story. Refresh and retry.');
  });

  it('returns generic message for unknown mode', () => {
    const msg = getModeAwareErrorMessage('invalid-mode', 'do something');
    expect(msg).toBe('Failed to do something.');
  });

  it('handles null mode gracefully', () => {
    const msg = getModeAwareErrorMessage(null, 'save data');
    expect(msg).toBe('Failed to save data.');
  });

  it('handles undefined mode gracefully', () => {
    const msg = getModeAwareErrorMessage(undefined, 'load data');
    expect(msg).toBe('Failed to load data.');
  });
});
