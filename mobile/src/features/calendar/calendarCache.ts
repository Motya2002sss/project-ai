import {
  isCalendarDayDto,
  isCalendarMonthDto,
  isCalendarWeekDto,
} from '../../api/calendarApi';
import { defaultStorageTimeoutMs, withStorageDeadline } from '../../storage/storageDeadline';
import type { CalendarCacheSnapshot } from './calendarTypes';

export interface CalendarStorage {
  getItem(key: string): Promise<string | null>;
  setItem(key: string, value: string): Promise<void>;
  removeItem(key: string): Promise<void>;
}

export class CalendarCache {
  private readonly key: string;
  constructor(
    private readonly storage: CalendarStorage,
    publicUserId: string,
    private readonly timeoutMs = defaultStorageTimeoutMs,
  ) {
    if (!publicUserId.trim()) throw new Error('publicUserId is required');
    this.key = `ai-life-planner:user:${encodeURIComponent(publicUserId)}:calendar:v2`;
  }

  async load(): Promise<CalendarCacheSnapshot | null> {
    const encoded = await withStorageDeadline(this.storage.getItem(this.key), this.timeoutMs);
    if (encoded === null) return null;
    try {
      const value: unknown = JSON.parse(encoded);
      if (isSnapshot(value)) return value;
    } catch { /* malformed cache is removed below */ }
    await withStorageDeadline(this.storage.removeItem(this.key), this.timeoutMs);
    return null;
  }

  async save(snapshot: CalendarCacheSnapshot): Promise<void> {
    await withStorageDeadline(this.storage.setItem(this.key, JSON.stringify(snapshot)), this.timeoutMs);
  }
}

function isSnapshot(value: unknown): value is CalendarCacheSnapshot {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) return false;
  const candidate = value as Record<string, unknown>;
  return Object.keys(candidate).length === 3 &&
    (candidate.day === null || isCalendarDayDto(candidate.day)) &&
    (candidate.week === null || isCalendarWeekDto(candidate.week)) &&
    (candidate.month === null || isCalendarMonthDto(candidate.month));
}
