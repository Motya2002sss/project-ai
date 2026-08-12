import { describe, expect, it } from 'vitest';

import {
  applyBudgetHoursDraft,
  formatBudgetHours,
} from '../budgetInput';

describe('resource budget decimal input', () => {
  it('preserves an intermediate decimal separator while typing', () => {
    expect(applyBudgetHoursDraft('1,', 60)).toEqual({
      text: '1,',
      minutes: 60,
    });
    expect(applyBudgetHoursDraft('1,5', 60)).toEqual({
      text: '1,5',
      minutes: 90,
    });
  });

  it('ignores invalid characters and formats committed minutes', () => {
    expect(applyBudgetHoursDraft('1,5ч', 60)).toEqual({
      text: '1,5ч',
      minutes: 60,
    });
    expect(formatBudgetHours(90)).toBe('1.5');
  });
});
