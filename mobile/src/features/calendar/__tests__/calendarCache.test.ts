import { describe, expect, it } from 'vitest';

import { CalendarCache, type CalendarStorage } from '../calendarCache';
import {
  calendarDayFixture,
  calendarMonthFixture,
  calendarWeekFixture,
} from './calendarFixtures';

class MemoryStorage implements CalendarStorage {
  readonly values = new Map<string, string>();
  async getItem(key: string) { return this.values.get(key) ?? null; }
  async setItem(key: string, value: string) { this.values.set(key, value); }
  async removeItem(key: string) { this.values.delete(key); }
}

describe('CalendarCache', () => {
  it('keeps calendar reads scoped to the authenticated public user', async () => {
    const storage = new MemoryStorage();
    const first = new CalendarCache(storage, 'user/a');
    const second = new CalendarCache(storage, 'user/b');
    const snapshot = {
      day: calendarDayFixture,
      week: calendarWeekFixture,
      month: calendarMonthFixture,
    };

    await first.save(snapshot);

    expect(await first.load()).toEqual(snapshot);
    expect(await second.load()).toBeNull();
    expect([...storage.values.keys()]).toEqual([
      'ai-life-planner:user:user%2Fa:calendar:v2',
    ]);
  });

  it('removes malformed data instead of rendering invented calendar state', async () => {
    const storage = new MemoryStorage();
    const cache = new CalendarCache(storage, 'user-a');
    storage.values.set(
      'ai-life-planner:user:user-a:calendar:v2',
      JSON.stringify({ week: { days: [{ title: 'fake' }] } }),
    );

    expect(await cache.load()).toBeNull();
    expect(storage.values.size).toBe(0);
  });
});
