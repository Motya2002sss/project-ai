import { describe, expect, it, vi } from 'vitest';

import { ExpoCalendarAdapter, type ExpoCalendarModule } from '../expoCalendarAdapter';

vi.mock('react-native', () => ({ Platform: { OS: 'ios', Version: '19.0' } }));
vi.mock('expo-calendar', () => ({}));

function module(overrides: Partial<ExpoCalendarModule> = {}): ExpoCalendarModule {
  return {
    async requestCalendarPermissionsAsync() { return { status: 'granted' }; },
    async getCalendarsAsync() {
      return [{ id: 'personal', entityType: 'event' }, { id: 'reminders', entityType: 'reminder' }];
    },
    async getEventsAsync() {
      return [{
        id: 'event-1', calendarId: 'personal', title: 'Секретная встреча',
        notes: 'не отправлять', location: 'дом', startDate: '2026-08-12T09:00:00Z',
        endDate: '2026-08-12T10:00:00Z', originalStartDate: '2026-08-12T09:00:00Z',
        lastModifiedDate: '2026-08-11T14:00:00Z', availability: 'busy', status: 'confirmed',
      }];
    },
    ...overrides,
  };
}

describe('ExpoCalendarAdapter', () => {
  it('maps only non-cancelled busy events to stable privacy-safe facts', async () => {
    const adapter = new ExpoCalendarAdapter(module());

    const result = await adapter.readBusyIntervals({
      startAt: '2026-08-10T00:00:00Z', endAt: '2026-08-17T00:00:00Z',
    });

    expect(result).toEqual({
      calendarIds: ['personal'],
      intervals: [{
        calendarExternalId: 'personal', eventExternalId: 'event-1',
        occurrenceExternalId: 'event-1@2026-08-12T09:00:00.000Z',
        startAt: '2026-08-12T09:00:00.000Z', endAt: '2026-08-12T10:00:00.000Z',
        sourceRevision: '2026-08-11T14:00:00.000Z',
      }],
    });
    expect(JSON.stringify(result)).not.toMatch(/Секретная|notes|location|дом/);
  });

  it('excludes free and cancelled events and returns permission states honestly', async () => {
    const adapter = new ExpoCalendarAdapter(module({
      requestCalendarPermissionsAsync: async () => ({ status: 'denied' }),
      getEventsAsync: async () => [
        { id: 'free', calendarId: 'personal', startDate: '2026-08-12T09:00:00Z', endDate: '2026-08-12T10:00:00Z', availability: 'free', status: 'confirmed' },
        { id: 'cancelled', calendarId: 'personal', startDate: '2026-08-12T11:00:00Z', endDate: '2026-08-12T12:00:00Z', availability: 'busy', status: 'canceled' },
      ],
    }));

    await expect(adapter.requestReadPermission()).resolves.toBe('denied');
    await expect(adapter.readBusyIntervals({ startAt: '2026-08-10T00:00:00Z', endAt: '2026-08-17T00:00:00Z' })).resolves.toEqual({ calendarIds: ['personal'], intervals: [] });
  });

  it('uses the concrete occurrence start for recurring events with the same event id', async () => {
    const adapter = new ExpoCalendarAdapter(module({
      getEventsAsync: async () => [
        { id: 'series-1', calendarId: 'personal', startDate: '2026-08-12T09:00:00Z', endDate: '2026-08-12T10:00:00Z', originalStartDate: '2026-08-01T09:00:00Z', availability: 'busy', status: 'confirmed' },
        { id: 'series-1', calendarId: 'personal', startDate: '2026-08-14T09:00:00Z', endDate: '2026-08-14T10:00:00Z', originalStartDate: '2026-08-01T09:00:00Z', availability: 'busy', status: 'confirmed' },
      ],
    }));

    const result = await adapter.readBusyIntervals({ startAt: '2026-08-10T00:00:00Z', endAt: '2026-08-17T00:00:00Z' });

    expect(result.intervals.map((item) => item.occurrenceExternalId)).toEqual([
      'series-1@2026-08-12T09:00:00.000Z',
      'series-1@2026-08-14T09:00:00.000Z',
    ]);
  });

  it('is unavailable outside iOS without requesting native permissions', async () => {
    let requested = false;
    const adapter = new ExpoCalendarAdapter(module({
      requestCalendarPermissionsAsync: async () => { requested = true; return { status: 'granted' }; },
    }), 'web');

    await expect(adapter.requestReadPermission()).resolves.toBe('unavailable');
    expect(requested).toBe(false);
  });
});
