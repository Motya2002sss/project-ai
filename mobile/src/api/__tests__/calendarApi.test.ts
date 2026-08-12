import { describe, expect, it } from 'vitest';

import {
  CalendarApi,
  isCalendarDayDto,
  isCalendarMonthDto,
  isCalendarWeekDto,
  type CalendarJsonRequester,
} from '../calendarApi';
import {
  calendarDayFixture,
  calendarMonthFixture,
  calendarWeekFixture,
} from '../../features/calendar/__tests__/calendarFixtures';

describe('CalendarApi production boundary', () => {
  it('uses canonical read-only v2 paths and runtime validators', async () => {
    const calls: string[] = [];
    const client: CalendarJsonRequester = {
      async request<T>(
        path: string,
        _init?: RequestInit,
        validator?: (value: unknown) => value is T,
      ): Promise<T> {
        calls.push(path);
        const payload: unknown = path.includes('/day?')
          ? calendarDayFixture
          : path.includes('/week?')
            ? calendarWeekFixture
            : calendarMonthFixture;
        if (!validator?.(payload)) throw new Error('invalid fixture');
        return payload as T;
      },
    };
    const api = new CalendarApi(client);

    await api.getDay('2026-08-12');
    await api.getWeek('2026-08-10');
    await api.getMonth('2026-08-01');

    expect(calls).toEqual([
      '/api/v2/calendar/day?date=2026-08-12',
      '/api/v2/calendar/week?start=2026-08-10',
      '/api/v2/calendar/month?month=2026-08-01',
    ]);
  });

  it('accepts complete contracts and rejects private or malformed shapes', () => {
    expect(isCalendarDayDto(calendarDayFixture)).toBe(true);
    expect(isCalendarWeekDto(calendarWeekFixture)).toBe(true);
    expect(isCalendarMonthDto(calendarMonthFixture)).toBe(true);
    expect(
      isCalendarDayDto({
        ...calendarDayFixture,
        busy_intervals: [{ ...calendarDayFixture.busy_intervals[0], title: 'Личное' }],
      }),
    ).toBe(false);
    expect(
      isCalendarDayDto({
        ...calendarDayFixture,
        items: [{ ...calendarDayFixture.items[0], end_at: null }],
      }),
    ).toBe(false);
    expect(
      isCalendarWeekDto({ ...calendarWeekFixture, days: calendarWeekFixture.days.slice(0, 6) }),
    ).toBe(false);
    expect(
      isCalendarMonthDto({ ...calendarMonthFixture, measurements: [{ value: 72.5 }] }),
    ).toBe(false);
  });

  it('rejects non-canonical date parameters before transport', async () => {
    const api = new CalendarApi({ request: async <T>() => calendarDayFixture as T });

    expect(() => api.getDay('12.08.2026')).toThrow(RangeError);
    expect(() => api.getWeek('2026-08-11')).toThrow(RangeError);
    expect(() => api.getMonth('2026-08-02')).toThrow(RangeError);
  });
});
