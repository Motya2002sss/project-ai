export type CalendarPermission = 'granted' | 'denied' | 'unavailable';

export interface CalendarBusyInterval {
  calendarExternalId: string;
  eventExternalId: string;
  occurrenceExternalId: string;
  startAt: string;
  endAt: string;
  sourceRevision: string;
}

export interface CalendarAdapter {
  requestReadPermission(): Promise<CalendarPermission>;
  readBusyIntervals(range: { startAt: string; endAt: string }): Promise<{
    calendarIds: string[];
    intervals: CalendarBusyInterval[];
  }>;
}

interface CalendarSyncState {
  status: 'not_started' | 'ready';
  version: number;
  client_revision: number;
  covered_calendar_ids: string[];
}

export interface CalendarSyncPayload {
  request_id: string;
  device_id: string;
  provider: 'apple';
  client_revision: number;
  expected_version: number;
  range_start: string;
  range_end: string;
  device_timezone: string;
  calendar_external_ids: string[];
  removed_calendar_external_ids: string[];
  busy_blocks: {
    calendar_external_id: string;
    external_id: string;
    occurrence_external_id: string;
    occurrence_start: string;
    occurrence_end: string;
    source_revision: string;
  }[];
}

export interface CalendarSyncTransport {
  getState(deviceId: string, provider: 'apple'): Promise<CalendarSyncState>;
  putBusyBlocks(payload: CalendarSyncPayload): Promise<{
    version: number;
    client_revision: number;
    affected_dates: string[];
    replan_required: boolean;
  }>;
}

interface RunCalendarBusySyncInput {
  adapter: CalendarAdapter;
  transport: CalendarSyncTransport;
  deviceId: string;
  timezone: string;
  requestId: string;
  range: { startAt: string; endAt: string };
}

export class CalendarSyncCoordinator {
  private pending: {
    requestId: string;
    payload: CalendarSyncPayload;
    transport: CalendarSyncTransport;
  } | null = null;

  async run(input: RunCalendarBusySyncInput) {
    if (this.pending?.requestId === input.requestId) {
      const result = mapSyncResult(
        await this.pending.transport.putBusyBlocks(this.pending.payload),
      );
      this.pending = null;
      return result;
    }
    const permission = await input.adapter.requestReadPermission();
    if (permission !== 'granted') return { status: 'permission_denied' as const };
    const payload = await buildSyncPayload(input);
    this.pending = { requestId: input.requestId, payload, transport: input.transport };
    try {
      const result = mapSyncResult(await input.transport.putBusyBlocks(payload));
      this.pending = null;
      return result;
    } catch (error) {
      throw error;
    }
  }
}

export async function runCalendarBusySync(input: RunCalendarBusySyncInput) {
  const permission = await input.adapter.requestReadPermission();
  if (permission !== 'granted') return { status: 'permission_denied' as const };

  const payload = await buildSyncPayload(input);
  return mapSyncResult(await input.transport.putBusyBlocks(payload));
}

export function calendarSyncWeekRange(
  selectedDate: string,
  timezone: string,
): { startAt: string; endAt: string } {
  const selected = new Date(`${selectedDate}T12:00:00Z`);
  if (Number.isNaN(selected.valueOf())) throw new Error('invalid_calendar_date');
  const weekday = (selected.getUTCDay() + 6) % 7;
  selected.setUTCDate(selected.getUTCDate() - weekday);
  const monday = selected.toISOString().slice(0, 10);
  const next = new Date(`${monday}T12:00:00Z`);
  next.setUTCDate(next.getUTCDate() + 7);
  return {
    startAt: zonedMidnightUtc(monday, timezone).toISOString(),
    endAt: zonedMidnightUtc(next.toISOString().slice(0, 10), timezone).toISOString(),
  };
}

function zonedMidnightUtc(dateValue: string, timezone: string): Date {
  const [year, month, day] = dateValue.split('-').map(Number) as [number, number, number];
  const probe = new Date(Date.UTC(year, month - 1, day, 12));
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: timezone,
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23',
  }).formatToParts(probe);
  const values = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  const represented = Date.UTC(
    Number(values.year), Number(values.month) - 1, Number(values.day),
    Number(values.hour), Number(values.minute), Number(values.second),
  );
  const offset = represented - probe.valueOf();
  return new Date(Date.UTC(year, month - 1, day) - offset);
}

async function buildSyncPayload(
  input: RunCalendarBusySyncInput,
): Promise<CalendarSyncPayload> {
  const state = await input.transport.getState(input.deviceId, 'apple');
  const read = await input.adapter.readBusyIntervals(input.range);
  const calendarIds = [...new Set(read.calendarIds)].sort();
  const identities = new Set<string>();
  const busyBlocks = read.intervals.map((interval) => {
    const key = `${interval.calendarExternalId}\u0000${interval.occurrenceExternalId}`;
    if (identities.has(key)) throw new Error('duplicate_calendar_occurrence');
    identities.add(key);
    if (!calendarIds.includes(interval.calendarExternalId)) {
      throw new Error('calendar_occurrence_outside_scope');
    }
    validateInterval(interval.startAt, interval.endAt);
    return {
      calendar_external_id: interval.calendarExternalId,
      external_id: interval.eventExternalId,
      occurrence_external_id: interval.occurrenceExternalId,
      occurrence_start: interval.startAt,
      occurrence_end: interval.endAt,
      source_revision: interval.sourceRevision,
    };
  });
  return {
    request_id: input.requestId,
    device_id: input.deviceId,
    provider: 'apple',
    client_revision: state.client_revision + 1,
    expected_version: state.version,
    range_start: input.range.startAt,
    range_end: input.range.endAt,
    device_timezone: input.timezone,
    calendar_external_ids: calendarIds,
    removed_calendar_external_ids: state.covered_calendar_ids
      .filter((calendarId) => !calendarIds.includes(calendarId))
      .sort(),
    busy_blocks: busyBlocks,
  };
}

function mapSyncResult(result: Awaited<ReturnType<CalendarSyncTransport['putBusyBlocks']>>) {
  return {
    status: 'synced' as const,
    version: result.version,
    affectedDates: result.affected_dates,
    replanRequired: result.replan_required,
  };
}

function validateInterval(start: string, end: string): void {
  const startAt = new Date(start);
  const endAt = new Date(end);
  if (
    Number.isNaN(startAt.valueOf()) ||
    Number.isNaN(endAt.valueOf()) ||
    endAt <= startAt
  ) {
    throw new Error('invalid_calendar_interval');
  }
}
