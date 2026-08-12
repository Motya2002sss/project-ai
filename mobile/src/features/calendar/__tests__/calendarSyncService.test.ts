import { describe, expect, it } from 'vitest';

import {
  CalendarSyncCoordinator,
  calendarSyncWeekRange,
  runCalendarBusySync,
  type CalendarAdapter,
  type CalendarSyncTransport,
} from '../calendarSyncService';

const range = {
  startAt: '2026-08-10T00:00:00Z',
  endAt: '2026-08-17T00:00:00Z',
};

function transport(calls: unknown[]): CalendarSyncTransport {
  return {
    async getState(deviceId, provider) {
      calls.push(['state', deviceId, provider]);
      return { status: 'ready', version: 3, client_revision: 8, covered_calendar_ids: [] };
    },
    async putBusyBlocks(payload) {
      calls.push(['sync', payload]);
      return { version: 4, client_revision: 9, affected_dates: ['2026-08-12'], replan_required: true };
    },
  };
}

describe('privacy-safe Apple Calendar sync', () => {
  it('builds user-visible week bounds in the device timezone including DST', () => {
    expect(calendarSyncWeekRange('2026-08-12', 'Europe/Moscow')).toEqual({
      startAt: '2026-08-09T21:00:00.000Z',
      endAt: '2026-08-16T21:00:00.000Z',
    });
    expect(calendarSyncWeekRange('2026-03-04', 'America/New_York')).toEqual({
      startAt: '2026-03-02T05:00:00.000Z',
      endAt: '2026-03-09T04:00:00.000Z',
    });
  });
  it('stops honestly when read permission is denied', async () => {
    const calls: unknown[] = [];
    const adapter: CalendarAdapter = {
      requestReadPermission: async () => 'denied',
      readBusyIntervals: async () => { throw new Error('must not read'); },
    };

    await expect(runCalendarBusySync({ adapter, transport: transport(calls), deviceId: 'iphone-1', timezone: 'Europe/Moscow', requestId: 'sync-1', range })).resolves.toEqual({ status: 'permission_denied' });
    expect(calls).toEqual([]);
  });

  it('sends only busy facts and stable identities without titles or notes', async () => {
    const calls: unknown[] = [];
    const adapter: CalendarAdapter = {
      requestReadPermission: async () => 'granted',
      async readBusyIntervals() {
        return {
          calendarIds: ['work', 'personal'],
          intervals: [{
            calendarExternalId: 'personal', eventExternalId: 'event-1',
            occurrenceExternalId: 'event-1@2026-08-12T09:00:00Z',
            startAt: '2026-08-12T09:00:00Z', endAt: '2026-08-12T10:00:00Z',
            sourceRevision: 'rev-2',
          }],
        };
      },
    };

    const result = await runCalendarBusySync({ adapter, transport: transport(calls), deviceId: 'iphone-1', timezone: 'Europe/Moscow', requestId: 'sync-1', range });

    expect(result).toMatchObject({ status: 'synced', version: 4, replanRequired: true });
    expect(calls[1]).toEqual(['sync', {
      request_id: 'sync-1', device_id: 'iphone-1', provider: 'apple',
      client_revision: 9, expected_version: 3,
      range_start: range.startAt, range_end: range.endAt,
      device_timezone: 'Europe/Moscow',
      calendar_external_ids: ['personal', 'work'], removed_calendar_external_ids: [],
      busy_blocks: [{
        calendar_external_id: 'personal', external_id: 'event-1',
        occurrence_external_id: 'event-1@2026-08-12T09:00:00Z',
        occurrence_start: '2026-08-12T09:00:00Z', occurrence_end: '2026-08-12T10:00:00Z',
        source_revision: 'rev-2',
      }],
    }]);
    expect(JSON.stringify(calls)).not.toMatch(/title|notes|location/);
  });

  it('rejects duplicate occurrence identities before backend mutation', async () => {
    const calls: unknown[] = [];
    const occurrence = {
      calendarExternalId: 'personal', eventExternalId: 'event-1', occurrenceExternalId: 'same',
      startAt: '2026-08-12T09:00:00Z', endAt: '2026-08-12T10:00:00Z', sourceRevision: '1',
    };
    const adapter: CalendarAdapter = {
      requestReadPermission: async () => 'granted',
      readBusyIntervals: async () => ({ calendarIds: ['personal'], intervals: [occurrence, occurrence] }),
    };

    await expect(runCalendarBusySync({ adapter, transport: transport(calls), deviceId: 'iphone-1', timezone: 'UTC', requestId: 'sync-dup', range })).rejects.toThrow('duplicate_calendar_occurrence');
    expect(calls).toEqual([['state', 'iphone-1', 'apple']]);
  });

  it('explicitly revokes calendars no longer returned by EventKit', async () => {
    const calls: unknown[] = [];
    const syncTransport: CalendarSyncTransport = {
      getState: async () => ({
        status: 'ready', version: 2, client_revision: 4,
        covered_calendar_ids: ['deleted-calendar', 'personal'],
      }),
      async putBusyBlocks(payload) {
        calls.push(payload);
        return { version: 3, client_revision: 5, affected_dates: [], replan_required: false };
      },
    };
    const adapter: CalendarAdapter = {
      requestReadPermission: async () => 'granted',
      readBusyIntervals: async () => ({ calendarIds: ['personal'], intervals: [] }),
    };

    await runCalendarBusySync({ adapter, transport: syncTransport, deviceId: 'iphone-1', timezone: 'UTC', requestId: 'sync-delete', range });

    expect(calls[0]).toMatchObject({
      calendar_external_ids: ['personal'],
      removed_calendar_external_ids: ['deleted-calendar'],
    });
  });

  it('retries a lost response with the exact same payload and request id', async () => {
    const payloads: unknown[] = [];
    let attempt = 0;
    const adapter: CalendarAdapter = {
      requestReadPermission: async () => 'granted',
      readBusyIntervals: async () => ({ calendarIds: ['personal'], intervals: [] }),
    };
    const coordinator = new CalendarSyncCoordinator();
    const syncTransport: CalendarSyncTransport = {
      getState: async () => ({ status: 'ready', version: 3, client_revision: 8, covered_calendar_ids: [] }),
      async putBusyBlocks(payload) {
        payloads.push(payload);
        attempt += 1;
        if (attempt === 1) throw new Error('response_lost');
        return { version: 4, client_revision: 9, affected_dates: [], replan_required: false };
      },
    };
    const input = { adapter, transport: syncTransport, deviceId: 'iphone-1', timezone: 'UTC', requestId: 'stable-request', range };

    await expect(coordinator.run(input)).rejects.toThrow('response_lost');
    await expect(coordinator.run(input)).resolves.toMatchObject({ status: 'synced', version: 4 });

    expect(payloads).toHaveLength(2);
    expect(payloads[1]).toEqual(payloads[0]);
  });
});
