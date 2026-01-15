/**
 * Unit tests for projection date range logic in app.js
 *
 * Tests dynamic date range adjustment based on view type:
 * - Story views: Use story's actual start_date and end_date
 * - Baseline view: Use baseline_display_months setting (default 3 months)
 * - ALL view: Show 12 months from today
 *
 * Related to app.js:576-653 - setDefaultProjectionDates() and setView()
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';

// Mock date utilities
const toLocalISODate = (date) => {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
};

/**
 * Mock Alpine.js component data structure
 */
class MockAppComponent {
  constructor() {
    this.currentView = 'all';
    this.projectionStartDate = null;
    this.projectionEndDate = null;
    this.stories = [];
    this.settings = { baseline_display_months: 3 };
    this.expandedGaps = new Set();
    this.displayCurrency = null;
  }

  /**
   * Set default projection date range (today to +12 months)
   * Matches app.js:576-586
   */
  setDefaultProjectionDates() {
    const today = new Date();
    const nextYear = new Date(today);
    nextYear.setFullYear(nextYear.getFullYear() + 1);

    this.projectionStartDate = toLocalISODate(today);
    this.projectionEndDate = toLocalISODate(nextYear);
  }

  /**
   * Set view and adjust projection date range dynamically
   * Matches app.js:612-653
   */
  async setView(view) {
    this.currentView = view;

    // Clear expanded gaps to prevent memory leak across view changes
    this.expandedGaps.clear();

    // Reset display currency when switching views
    if (view !== 'all') {
      this.displayCurrency = null;
    }

    // Adjust projection date range based on view
    if (view !== 'all' && view !== 'baseline') {
      // Story view - use story's date range
      const story = this.stories.find(s => s.id === view);
      if (story) {
        this.projectionStartDate = story.start_date;
        // Use story end_date if set, otherwise default to 1 year from start
        this.projectionEndDate = story.end_date || toLocalISODate(new Date(new Date(story.start_date).setFullYear(new Date(story.start_date).getFullYear() + 1)));
      }
    } else if (view === 'baseline') {
      // Baseline view - use baseline_display_months setting
      const today = new Date();
      const endDate = new Date(today);
      const months = this.settings.baseline_display_months || 3;
      endDate.setMonth(endDate.getMonth() + months);

      this.projectionStartDate = toLocalISODate(today);
      this.projectionEndDate = toLocalISODate(endDate);
    } else {
      // ALL view - show 12 months from today
      const today = new Date();
      const nextYear = new Date(today);
      nextYear.setFullYear(nextYear.getFullYear() + 1);

      this.projectionStartDate = toLocalISODate(today);
      this.projectionEndDate = toLocalISODate(nextYear);
    }

    // updateProjectionRows() would be called here in production
    // For testing, we skip it since we only care about date range logic
  }
}

describe('setDefaultProjectionDates', () => {
  let app;
  let today;
  let nextYear;

  beforeEach(() => {
    app = new MockAppComponent();
    today = new Date();
    nextYear = new Date(today);
    nextYear.setFullYear(nextYear.getFullYear() + 1);
  });

  it('sets projection range to 12 months by default', () => {
    app.setDefaultProjectionDates();

    expect(app.projectionStartDate).toBe(toLocalISODate(today));
    expect(app.projectionEndDate).toBe(toLocalISODate(nextYear));
  });

  it('starts from today', () => {
    app.setDefaultProjectionDates();

    const expectedStart = toLocalISODate(today);
    expect(app.projectionStartDate).toBe(expectedStart);
  });

  it('ends at exactly 12 months from today', () => {
    app.setDefaultProjectionDates();

    const expectedEnd = toLocalISODate(nextYear);
    expect(app.projectionEndDate).toBe(expectedEnd);
  });
});

describe('setView - ALL view', () => {
  let app;
  let today;
  let nextYear;

  beforeEach(() => {
    app = new MockAppComponent();
    today = new Date();
    nextYear = new Date(today);
    nextYear.setFullYear(nextYear.getFullYear() + 1);
  });

  it('sets 12 month range for ALL view', async () => {
    await app.setView('all');

    expect(app.projectionStartDate).toBe(toLocalISODate(today));
    expect(app.projectionEndDate).toBe(toLocalISODate(nextYear));
  });

  it('clears expanded gaps when switching to ALL view', async () => {
    app.expandedGaps.add('gap-1');
    app.expandedGaps.add('gap-2');

    await app.setView('all');

    expect(app.expandedGaps.size).toBe(0);
  });

  it('keeps displayCurrency when in ALL view', async () => {
    app.displayCurrency = 'USD';

    await app.setView('all');

    expect(app.displayCurrency).toBe('USD');
  });
});

describe('setView - Baseline view', () => {
  let app;
  let today;

  beforeEach(() => {
    app = new MockAppComponent();
    today = new Date();
  });

  it('uses default 3 months for baseline view', async () => {
    app.settings.baseline_display_months = 3;

    await app.setView('baseline');

    const endDate = new Date(today);
    endDate.setMonth(endDate.getMonth() + 3);

    expect(app.projectionStartDate).toBe(toLocalISODate(today));
    expect(app.projectionEndDate).toBe(toLocalISODate(endDate));
  });

  it('respects custom baseline_display_months setting', async () => {
    app.settings.baseline_display_months = 6;

    await app.setView('baseline');

    const endDate = new Date(today);
    endDate.setMonth(endDate.getMonth() + 6);

    expect(app.projectionStartDate).toBe(toLocalISODate(today));
    expect(app.projectionEndDate).toBe(toLocalISODate(endDate));
  });

  it('handles 1 month baseline setting', async () => {
    app.settings.baseline_display_months = 1;

    await app.setView('baseline');

    const endDate = new Date(today);
    endDate.setMonth(endDate.getMonth() + 1);

    expect(app.projectionStartDate).toBe(toLocalISODate(today));
    expect(app.projectionEndDate).toBe(toLocalISODate(endDate));
  });

  it('handles 12 month baseline setting', async () => {
    app.settings.baseline_display_months = 12;

    await app.setView('baseline');

    const endDate = new Date(today);
    endDate.setMonth(endDate.getMonth() + 12);

    expect(app.projectionStartDate).toBe(toLocalISODate(today));
    expect(app.projectionEndDate).toBe(toLocalISODate(endDate));
  });

  it('uses default 3 months if baseline_display_months is undefined', async () => {
    app.settings.baseline_display_months = undefined;

    await app.setView('baseline');

    const endDate = new Date(today);
    endDate.setMonth(endDate.getMonth() + 3);

    expect(app.projectionStartDate).toBe(toLocalISODate(today));
    expect(app.projectionEndDate).toBe(toLocalISODate(endDate));
  });

  it('resets displayCurrency when switching to baseline', async () => {
    app.displayCurrency = 'USD';

    await app.setView('baseline');

    expect(app.displayCurrency).toBeNull();
  });

  it('clears expanded gaps when switching to baseline', async () => {
    app.expandedGaps.add('gap-1');

    await app.setView('baseline');

    expect(app.expandedGaps.size).toBe(0);
  });
});

describe('setView - Story view', () => {
  let app;

  beforeEach(() => {
    app = new MockAppComponent();
    app.stories = [
      {
        id: 'story-1',
        name: 'Canada Ski Trip',
        start_date: '2026-01-15',
        end_date: '2026-01-30'
      },
      {
        id: 'story-2',
        name: 'House Renovation',
        start_date: '2026-03-01',
        end_date: '2026-12-31'
      },
      {
        id: 'story-3',
        name: 'No End Date Story',
        start_date: '2026-06-01',
        end_date: null  // No end date set
      }
    ];
  });

  it('uses story date range for story view', async () => {
    await app.setView('story-1');

    expect(app.projectionStartDate).toBe('2026-01-15');
    expect(app.projectionEndDate).toBe('2026-01-30');
  });

  it('uses story start and end dates correctly', async () => {
    await app.setView('story-2');

    expect(app.projectionStartDate).toBe('2026-03-01');
    expect(app.projectionEndDate).toBe('2026-12-31');
  });

  it('defaults to +1 year if story has no end_date', async () => {
    await app.setView('story-3');

    expect(app.projectionStartDate).toBe('2026-06-01');

    // End date should be 1 year after start
    const expectedEnd = new Date('2026-06-01');
    expectedEnd.setFullYear(expectedEnd.getFullYear() + 1);
    expect(app.projectionEndDate).toBe(toLocalISODate(expectedEnd));
  });

  it('resets displayCurrency when switching to story view', async () => {
    app.displayCurrency = 'USD';

    await app.setView('story-1');

    expect(app.displayCurrency).toBeNull();
  });

  it('clears expanded gaps when switching to story view', async () => {
    app.expandedGaps.add('gap-1');

    await app.setView('story-1');

    expect(app.expandedGaps.size).toBe(0);
  });
});

describe('setView - View switching scenarios', () => {
  let app;
  let today;

  beforeEach(() => {
    app = new MockAppComponent();
    today = new Date();
    app.stories = [
      {
        id: 'story-1',
        name: 'Test Story',
        start_date: '2026-01-15',
        end_date: '2026-01-30'
      }
    ];
  });

  it('switches from ALL to baseline correctly', async () => {
    await app.setView('all');
    expect(app.currentView).toBe('all');

    await app.setView('baseline');
    expect(app.currentView).toBe('baseline');

    const endDate = new Date(today);
    endDate.setMonth(endDate.getMonth() + 3);
    expect(app.projectionEndDate).toBe(toLocalISODate(endDate));
  });

  it('switches from baseline to story correctly', async () => {
    await app.setView('baseline');
    expect(app.currentView).toBe('baseline');

    await app.setView('story-1');
    expect(app.currentView).toBe('story-1');
    expect(app.projectionStartDate).toBe('2026-01-15');
    expect(app.projectionEndDate).toBe('2026-01-30');
  });

  it('switches from story back to ALL correctly', async () => {
    await app.setView('story-1');
    expect(app.currentView).toBe('story-1');

    await app.setView('all');
    expect(app.currentView).toBe('all');

    const nextYear = new Date(today);
    nextYear.setFullYear(nextYear.getFullYear() + 1);
    expect(app.projectionEndDate).toBe(toLocalISODate(nextYear));
  });

  it('clears state correctly when switching between any views', async () => {
    app.expandedGaps.add('gap-1');
    app.displayCurrency = 'USD';

    await app.setView('story-1');

    expect(app.expandedGaps.size).toBe(0);
    expect(app.displayCurrency).toBeNull();
  });
});

describe('Edge cases and error handling', () => {
  let app;

  beforeEach(() => {
    app = new MockAppComponent();
  });

  it('handles missing story gracefully', async () => {
    app.stories = [];

    await app.setView('nonexistent-story');

    // Should not crash, currentView should be set
    expect(app.currentView).toBe('nonexistent-story');
  });

  it('handles empty stories array', async () => {
    app.stories = [];

    await app.setView('all');

    expect(app.currentView).toBe('all');
    expect(app.projectionStartDate).toBeDefined();
    expect(app.projectionEndDate).toBeDefined();
  });

  it('handles missing settings object', async () => {
    app.settings = {};

    await app.setView('baseline');

    // Should default to 3 months
    const today = new Date();
    const endDate = new Date(today);
    endDate.setMonth(endDate.getMonth() + 3);

    expect(app.projectionEndDate).toBe(toLocalISODate(endDate));
  });
});
