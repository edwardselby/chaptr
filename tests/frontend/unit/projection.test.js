/**
 * Unit tests for CHAPTR projection engine functions
 *
 * Tests pure calculation functions from static/js/projection.js
 */

import { describe, it, expect } from 'vitest';
import {
  convertToBaseCurrency,
  convertFromBaseCurrency,
} from '../../../static/js/projection.js';

describe('convertToBaseCurrency', () => {
  it('converts amount using rate', () => {
    expect(convertToBaseCurrency(100, 0.79)).toBe(79);
    expect(convertToBaseCurrency(1000, 0.85)).toBe(850);
    expect(convertToBaseCurrency(50, 1.25)).toBe(62.5);
  });

  it('rounds to 2 decimal places', () => {
    expect(convertToBaseCurrency(100, 0.123456)).toBe(12.35);
    expect(convertToBaseCurrency(777, 0.888)).toBe(689.98); // 777 * 0.888 = 689.976
    expect(convertToBaseCurrency(33.33, 1.111)).toBe(37.03);
  });

  it('handles negative amounts correctly', () => {
    expect(convertToBaseCurrency(-100, 0.79)).toBe(-79);
    expect(convertToBaseCurrency(-500, 1.5)).toBe(-750);
  });

  it('handles rate = 1.0 (no conversion)', () => {
    expect(convertToBaseCurrency(1000, 1.0)).toBe(1000);
    expect(convertToBaseCurrency(12.34, 1.0)).toBe(12.34);
  });

  it('handles zero amount', () => {
    expect(convertToBaseCurrency(0, 0.79)).toBe(0);
    expect(convertToBaseCurrency(0, 1.5)).toBe(0);
  });

  it('handles very small rates', () => {
    expect(convertToBaseCurrency(1000, 0.01)).toBe(10);
    expect(convertToBaseCurrency(100, 0.001)).toBe(0.1);
  });

  it('handles very large rates', () => {
    expect(convertToBaseCurrency(100, 10.5)).toBe(1050);
    expect(convertToBaseCurrency(50, 100)).toBe(5000);
  });
});

describe('convertFromBaseCurrency', () => {
  const rates = {
    'USD': 0.79,
    'EUR': 0.85,
    'CAD': 0.58,
    'JPY': 0.0065
  };

  it('returns baseAmount when displayCurrency matches baseCurrency', () => {
    expect(convertFromBaseCurrency(1000, 'GBP', 'GBP', rates)).toBe(1000);
    expect(convertFromBaseCurrency(12.34, 'USD', 'USD', rates)).toBe(12.34);
  });

  it('converts using rate from rates object', () => {
    expect(convertFromBaseCurrency(100, 'USD', 'GBP', rates)).toBe(79);
    expect(convertFromBaseCurrency(1000, 'EUR', 'GBP', rates)).toBe(850);
    expect(convertFromBaseCurrency(500, 'CAD', 'GBP', rates)).toBe(290);
  });

  it('rounds to 2 decimal places', () => {
    expect(convertFromBaseCurrency(777, 'USD', 'GBP', rates)).toBe(613.83); // 777 * 0.79 = 613.83
    expect(convertFromBaseCurrency(333.33, 'EUR', 'GBP', rates)).toBe(283.33);
  });

  it('uses 1.0 fallback for missing currency', () => {
    expect(convertFromBaseCurrency(1000, 'AUD', 'GBP', rates)).toBe(1000);
    expect(convertFromBaseCurrency(500, 'NZD', 'GBP', rates)).toBe(500);
  });

  it('handles negative amounts correctly', () => {
    expect(convertFromBaseCurrency(-100, 'USD', 'GBP', rates)).toBe(-79);
    expect(convertFromBaseCurrency(-500, 'EUR', 'GBP', rates)).toBe(-425);
  });

  it('handles zero amount', () => {
    expect(convertFromBaseCurrency(0, 'USD', 'GBP', rates)).toBe(0);
    expect(convertFromBaseCurrency(0, 'EUR', 'GBP', rates)).toBe(0);
  });

  it('handles very small rates correctly', () => {
    expect(convertFromBaseCurrency(1000, 'JPY', 'GBP', rates)).toBe(6.5);
    expect(convertFromBaseCurrency(10000, 'JPY', 'GBP', rates)).toBe(65);
  });

  it('handles empty rates object gracefully', () => {
    const emptyRates = {};
    expect(convertFromBaseCurrency(1000, 'USD', 'GBP', emptyRates)).toBe(1000);
    expect(convertFromBaseCurrency(500, 'EUR', 'GBP', emptyRates)).toBe(500);
  });
});
