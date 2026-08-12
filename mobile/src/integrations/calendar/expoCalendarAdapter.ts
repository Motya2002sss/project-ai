import type { CalendarAdapter, CalendarBusyInterval, CalendarPermission } from './calendarAdapter';

interface ExpoCalendarRecord { id: string; entityType?: string }
interface ExpoEventRecord {
  id: string;
  calendarId: string;
  startDate: string | Date;
  endDate: string | Date;
  originalStartDate?: string | Date;
  lastModifiedDate?: string | Date;
  availability?: string;
  status?: string;
}

export interface ExpoCalendarModule {
  requestCalendarPermissionsAsync(): Promise<{ status: string }>;
  getCalendarsAsync(entityType?: string): Promise<ExpoCalendarRecord[]>;
  getEventsAsync(calendarIds: string[], startDate: Date, endDate: Date): Promise<ExpoEventRecord[]>;
}

export class ExpoCalendarAdapter implements CalendarAdapter {
  constructor(
    private readonly calendar: ExpoCalendarModule,
    private readonly platform: string = 'ios',
  ) {}

  async requestReadPermission(): Promise<CalendarPermission> {
    if (this.platform !== 'ios') return 'unavailable';
    const response = await this.calendar.requestCalendarPermissionsAsync();
    return response.status === 'granted' ? 'granted' : 'denied';
  }

  async readBusyIntervals(range: { startAt: string; endAt: string }) {
    const startAt = new Date(range.startAt);
    const endAt = new Date(range.endAt);
    if (Number.isNaN(startAt.valueOf()) || Number.isNaN(endAt.valueOf()) || endAt <= startAt) {
      throw new Error('invalid_calendar_range');
    }
    const calendars = await this.calendar.getCalendarsAsync('event');
    const calendarIds = calendars
      .filter((calendar) => calendar.entityType === undefined || calendar.entityType === 'event')
      .map((calendar) => calendar.id)
      .sort();
    if (calendarIds.length === 0) return { calendarIds, intervals: [] };
    const events = await this.calendar.getEventsAsync(calendarIds, startAt, endAt);
    const intervals: CalendarBusyInterval[] = events
      .filter((event) => event.status !== 'canceled' && event.availability !== 'free')
      .map((event) => mapEvent(event))
      .sort((first, second) => first.startAt.localeCompare(second.startAt));
    return { calendarIds, intervals };
  }
}

export async function createExpoCalendarAdapter(): Promise<CalendarAdapter> {
  const [{ Platform }, Calendar] = await Promise.all([
    import('react-native'),
    import('expo-calendar'),
  ]);
  return new ExpoCalendarAdapter(Calendar, Platform.OS);
}

function mapEvent(event: ExpoEventRecord): CalendarBusyInterval {
  const startAt = iso(event.startDate);
  return {
    calendarExternalId: event.calendarId,
    eventExternalId: event.id,
    occurrenceExternalId: `${event.id}@${startAt}`,
    startAt,
    endAt: iso(event.endDate),
    sourceRevision: event.lastModifiedDate ? iso(event.lastModifiedDate) : `${startAt}/${iso(event.endDate)}`,
  };
}

function iso(value: string | Date): string {
  const parsed = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(parsed.valueOf())) throw new Error('invalid_calendar_event_time');
  return parsed.toISOString();
}
