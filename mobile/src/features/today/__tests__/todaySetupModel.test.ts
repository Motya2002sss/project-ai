import { describe, expect, it } from 'vitest';

import { shouldOfferTodaySetup } from '../todaySetupModel';

describe('shouldOfferTodaySetup', () => {
  it('offers setup when the API address is missing', () => {
    expect(shouldOfferTodaySetup('', null)).toBe(true);
  });

  it('offers setup when access is not configured', () => {
    expect(
      shouldOfferTodaySetup(
        'https://planner.example.test',
        'Доступ к плану не настроен.',
      ),
    ).toBe(true);
  });

  it('does not replace a normal network retry with setup', () => {
    expect(
      shouldOfferTodaySetup(
        'https://planner.example.test',
        'Нет соединения. План дня не загрузился.',
      ),
    ).toBe(false);
  });
});
