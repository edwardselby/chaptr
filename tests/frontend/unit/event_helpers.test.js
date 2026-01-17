/**
 * Unit tests for CHAPTR event helper functions
 *
 * Tests pure functions from static/js/event-helpers.js
 */

import { describe, it, expect, beforeEach } from 'vitest';
import {
  calculateRateToBase,
  createOpeningBalanceEventData,
  createRecurringInstanceData,
  generateInstancesForWindow,
} from '../../../static/js/event-helpers.js';

describe('calculateRateToBase', () => {
  const mockSettings = {
    base_currency: 'GBP',
    rates: {
      'USD': 0.79,
      'EUR': 0.85,
      'CAD': 0.58
    }
  };

  it('returns 1.0 when currency matches base currency', () => {
    expect(calculateRateToBase('GBP', mockSettings)).toBe(1.0);
  });

  it('returns correct rate for currency in settings', () => {
    expect(calculateRateToBase('USD', mockSettings)).toBe(0.79);
    expect(calculateRateToBase('EUR', mockSettings)).toBe(0.85);
    expect(calculateRateToBase('CAD', mockSettings)).toBe(0.58);
  });

  it('returns 1.0 fallback for currency not in settings', () => {
    expect(calculateRateToBase('JPY', mockSettings)).toBe(1.0);
    expect(calculateRateToBase('AUD', mockSettings)).toBe(1.0);
  });

  it('returns 1.0 fallback when settings is null', () => {
    expect(calculateRateToBase('USD', null)).toBe(1.0);
  });

  it('returns 1.0 fallback when settings is undefined', () => {
    expect(calculateRateToBase('USD', undefined)).toBe(1.0);
  });

  it('returns 1.0 fallback when settings has no rates', () => {
    const noRatesSettings = { base_currency: 'GBP' };
    expect(calculateRateToBase('USD', noRatesSettings)).toBe(1.0);
  });
});

describe('createOpeningBalanceEventData', () => {
  const mockSettings = {
    base_currency: 'GBP',
    rates: { 'USD': 0.79 }
  };

  it('creates opening balance event with correct fields', () => {
    const account = {
      id: 'acc-123',
      current_balance: 1000,
      currency: 'GBP',
      is_default: true
    };

    const event = createOpeningBalanceEventData(account, mockSettings);

    expect(event).toBeDefined();
    expect(event.id).toBeDefined();
    expect(event.description).toBe('opening balance');
    expect(event.amount).toBe(1000);
    expect(event.currency).toBe('GBP');
    expect(event.rate_to_base).toBe(1.0);
    expect(event.account_id).toBe('acc-123');
    expect(event.story_id).toBeNull();
    expect(event.is_baseline).toBe(true);
    expect(event.is_hypothetical).toBe(false);
    expect(event.is_opening_balance).toBe(true);
    expect(event.is_auto_adjustment).toBe(false);
    expect(event.is_transfer).toBe(false);
    expect(event.recurring_rule_id).toBeNull();
  });

  it('returns null for zero balance', () => {
    const account = {
      id: 'acc-123',
      current_balance: 0,
      currency: 'GBP',
      is_default: true
    };

    const event = createOpeningBalanceEventData(account, mockSettings);
    expect(event).toBeNull();
  });

  it('allows negative balance (overdraft)', () => {
    const account = {
      id: 'acc-123',
      current_balance: -500,
      currency: 'GBP',
      is_default: false
    };

    const event = createOpeningBalanceEventData(account, mockSettings);

    expect(event).toBeDefined();
    expect(event.amount).toBe(-500);
    expect(event.is_baseline).toBe(false);
  });

  it('inherits is_baseline from account.is_default', () => {
    const defaultAccount = {
      id: 'acc-123',
      current_balance: 1000,
      currency: 'GBP',
      is_default: true
    };

    const nonDefaultAccount = {
      id: 'acc-456',
      current_balance: 500,
      currency: 'USD',
      is_default: false
    };

    const event1 = createOpeningBalanceEventData(defaultAccount, mockSettings);
    const event2 = createOpeningBalanceEventData(nonDefaultAccount, mockSettings);

    expect(event1.is_baseline).toBe(true);
    expect(event2.is_baseline).toBe(false);
  });

  it('uses correct exchange rate for non-base currency', () => {
    const account = {
      id: 'acc-123',
      current_balance: 1000,
      currency: 'USD',
      is_default: true
    };

    const event = createOpeningBalanceEventData(account, mockSettings);

    expect(event.currency).toBe('USD');
    expect(event.rate_to_base).toBe(0.79);
  });

  it('generates unique UUID for each event', () => {
    const account = {
      id: 'acc-123',
      current_balance: 1000,
      currency: 'GBP',
      is_default: true
    };

    const event1 = createOpeningBalanceEventData(account, mockSettings);
    const event2 = createOpeningBalanceEventData(account, mockSettings);

    expect(event1.id).not.toBe(event2.id);
  });
});

describe('createRecurringInstanceData', () => {
  const mockSettings = {
    base_currency: 'GBP',
    rates: { 'USD': 0.79 }
  };

  const mockRule = {
    id: 'rule-123',
    description: 'Monthly salary',
    amount: 3000,
    currency: 'GBP',
    account_id: 'acc-456',
    frequency: 'monthly',
    day: 1,
    start_date: '2025-01-01',
    end_date: null
  };

  it('creates recurring instance with correct fields', () => {
    const date = new Date(2025, 5, 15); // Jun 15, 2025

    const event = createRecurringInstanceData(mockRule, date, mockSettings, false);

    expect(event).toBeDefined();
    expect(event.id).toBeDefined();
    expect(event.event_date).toBe('2025-06-15');
    expect(event.description).toBe('Monthly salary');
    expect(event.amount).toBe(3000);
    expect(event.currency).toBe('GBP');
    expect(event.rate_to_base).toBe(1.0);
    expect(event.account_id).toBe('acc-456');
    expect(event.story_id).toBeNull();
    expect(event.is_baseline).toBe(false);
    expect(event.is_hypothetical).toBe(false);
    expect(event.is_opening_balance).toBe(false);
    expect(event.is_auto_adjustment).toBe(false);
    expect(event.is_transfer).toBe(false);
    expect(event.recurring_rule_id).toBe('rule-123');
  });

  it('links to recurring_rule_id', () => {
    const date = new Date(2025, 5, 15);
    const event = createRecurringInstanceData(mockRule, date, mockSettings, false);

    expect(event.recurring_rule_id).toBe('rule-123');
  });

  it('sets story_id to null (recurring events not tied to stories)', () => {
    const date = new Date(2025, 5, 15);
    const event = createRecurringInstanceData(mockRule, date, mockSettings, false);

    expect(event.story_id).toBeNull();
  });

  it('respects isBaseline parameter', () => {
    const date = new Date(2025, 5, 15);

    const baselineEvent = createRecurringInstanceData(mockRule, date, mockSettings, true);
    const nonBaselineEvent = createRecurringInstanceData(mockRule, date, mockSettings, false);

    expect(baselineEvent.is_baseline).toBe(true);
    expect(nonBaselineEvent.is_baseline).toBe(false);
  });

  it('uses correct exchange rate for non-base currency', () => {
    const usdRule = {
      ...mockRule,
      currency: 'USD'
    };

    const date = new Date(2025, 5, 15);
    const event = createRecurringInstanceData(usdRule, date, mockSettings, false);

    expect(event.currency).toBe('USD');
    expect(event.rate_to_base).toBe(0.79);
  });

  it('generates unique UUID for each instance', () => {
    const date = new Date(2025, 5, 15);

    const event1 = createRecurringInstanceData(mockRule, date, mockSettings, false);
    const event2 = createRecurringInstanceData(mockRule, date, mockSettings, false);

    expect(event1.id).not.toBe(event2.id);
  });
});

describe('generateInstancesForWindow', () => {
  const mockSettings = {
    base_currency: 'GBP',
    rates: {}
  };

  it('generates correct dates for weekly rule (Monday)', () => {
    const weeklyRule = {
      id: 'rule-weekly',
      description: 'Weekly meeting',
      amount: 100,
      currency: 'GBP',
      account_id: 'acc-123',
      frequency: 'weekly',
      day: 1, // Monday
      start_date: '2025-01-01',
      end_date: null
    };

    const instances = generateInstancesForWindow(weeklyRule, 30, mockSettings, false);

    // Should generate ~4-5 Mondays in a 60-day window (±30 days)
    expect(instances.length).toBeGreaterThanOrEqual(4);
    expect(instances.length).toBeLessThanOrEqual(9);

    // All instances should be Mondays
    instances.forEach(instance => {
      const date = new Date(instance.event_date + 'T00:00:00');
      const dayOfWeek = date.getDay();
      expect(dayOfWeek).toBe(1); // Monday
    });
  });

  it('generates correct dates for monthly rule (1st of month)', () => {
    const monthlyRule = {
      id: 'rule-monthly',
      description: 'Monthly rent',
      amount: -1200,
      currency: 'GBP',
      account_id: 'acc-123',
      frequency: 'monthly',
      day: 1, // 1st of month
      start_date: '2025-01-01',
      end_date: null
    };

    const instances = generateInstancesForWindow(monthlyRule, 30, mockSettings, false);

    // Should generate 1-2 instances (1st of current month and maybe next/previous)
    expect(instances.length).toBeGreaterThanOrEqual(1);
    expect(instances.length).toBeLessThanOrEqual(3);

    // All instances should be on the 1st of the month
    instances.forEach(instance => {
      const date = new Date(instance.event_date + 'T00:00:00');
      expect(date.getDate()).toBe(1);
    });
  });

  it('generates correct dates for annual rule', () => {
    const annualRule = {
      id: 'rule-annual',
      description: 'Birthday',
      amount: 500,
      currency: 'GBP',
      account_id: 'acc-123',
      frequency: 'annual',
      day: 15, // 15th of start month
      start_date: '2025-06-15', // June 15
      end_date: null
    };

    const instances = generateInstancesForWindow(annualRule, 60, mockSettings, false);

    // Should generate 0-1 instances (June 15 if in window)
    expect(instances.length).toBeGreaterThanOrEqual(0);
    expect(instances.length).toBeLessThanOrEqual(1);

    if (instances.length > 0) {
      const instance = instances[0];
      const date = new Date(instance.event_date + 'T00:00:00');
      expect(date.getMonth()).toBe(5); // June (0-indexed)
      expect(date.getDate()).toBe(15);
    }
  });

  it('respects rule start_date', () => {
    const futureRule = {
      id: 'rule-future',
      description: 'Future event',
      amount: 100,
      currency: 'GBP',
      account_id: 'acc-123',
      frequency: 'weekly',
      day: 1,
      start_date: '2030-01-01', // Far in future
      end_date: null
    };

    const instances = generateInstancesForWindow(futureRule, 30, mockSettings, false);

    // Should generate 0 instances (rule starts in future)
    expect(instances.length).toBe(0);
  });

  it('respects rule end_date', () => {
    const pastRule = {
      id: 'rule-past',
      description: 'Past event',
      amount: 100,
      currency: 'GBP',
      account_id: 'acc-123',
      frequency: 'weekly',
      day: 1,
      start_date: '2020-01-01',
      end_date: '2020-12-31' // Ended in past
    };

    const instances = generateInstancesForWindow(pastRule, 30, mockSettings, false);

    // Should generate 0 instances (rule ended in past)
    expect(instances.length).toBe(0);
  });

  it('returns empty array if rule outside window', () => {
    const noOverlapRule = {
      id: 'rule-no-overlap',
      description: 'No overlap',
      amount: 100,
      currency: 'GBP',
      account_id: 'acc-123',
      frequency: 'weekly',
      day: 1,
      start_date: '2030-01-01',
      end_date: '2030-12-31'
    };

    const instances = generateInstancesForWindow(noOverlapRule, 30, mockSettings, false);

    expect(instances).toEqual([]);
  });

  it('all instances have recurring_rule_id set', () => {
    const weeklyRule = {
      id: 'rule-weekly',
      description: 'Weekly event',
      amount: 100,
      currency: 'GBP',
      account_id: 'acc-123',
      frequency: 'weekly',
      day: 1,
      start_date: '2025-01-01',
      end_date: null
    };

    const instances = generateInstancesForWindow(weeklyRule, 30, mockSettings, false);

    instances.forEach(instance => {
      expect(instance.recurring_rule_id).toBe('rule-weekly');
    });
  });

  it('respects isBaseline parameter for all instances', () => {
    const weeklyRule = {
      id: 'rule-weekly',
      description: 'Weekly event',
      amount: 100,
      currency: 'GBP',
      account_id: 'acc-123',
      frequency: 'weekly',
      day: 1,
      start_date: '2025-01-01',
      end_date: null
    };

    const baselineInstances = generateInstancesForWindow(weeklyRule, 30, mockSettings, true);
    const nonBaselineInstances = generateInstancesForWindow(weeklyRule, 30, mockSettings, false);

    baselineInstances.forEach(instance => {
      expect(instance.is_baseline).toBe(true);
    });

    nonBaselineInstances.forEach(instance => {
      expect(instance.is_baseline).toBe(false);
    });
  });
});
