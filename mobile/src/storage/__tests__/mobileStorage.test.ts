import { describe, expect, it } from 'vitest';

import type { DaySnapshotDto } from '../../api/types';
import { MobileCache, type KeyValueStorage } from '../cache';

class MemoryStorage implements KeyValueStorage {
  readonly values = new Map<string, string>();

  async getItem(key: string) {
    return this.values.get(key) ?? null;
  }

  async setItem(key: string, value: string) {
    this.values.set(key, value);
  }

  async removeItem(key: string) {
    this.values.delete(key);
  }
}

const snapshot = {
  date: '2026-08-10',
  focus_text: 'Сначала — задача.',
  progress: { done: 0, total: 0 },
  scheduled_items: [],
  unscheduled_items: [],
  completed_items: [],
  current_item: null,
  completed_count: 0,
  total_count: 0,
  day_context: {
    energy_level: null,
    budget_limit: null,
    work_override_mode: null,
    work_start_time: null,
    work_end_time: null,
  },
  tasks: [],
  goals: [],
  routines: [],
  plan: {
    id: 0,
    date: '2026-08-10',
    summary: null,
    focus_text: 'Сначала — задача.',
    energy_level: null,
    budget_limit: null,
    status: 'draft',
    version: 0,
    items: [],
  },
  plan_version: 0,
} satisfies DaySnapshotDto;

describe('MobileCache', () => {
  it('restores the exact multiline capture draft after a new cache instance', async () => {
    const storage = new MemoryStorage();
    await new MobileCache(storage).saveDraft('Первая строка\nВторая строка');

    expect(await new MobileCache(storage).loadDraft()).toBe(
      'Первая строка\nВторая строка',
    );
  });

  it('removes a draft only when the successful flow writes an empty value', async () => {
    const storage = new MemoryStorage();
    const cache = new MobileCache(storage);
    await cache.saveDraft('Сохранить меня');
    await cache.saveDraft('');

    expect(await cache.loadDraft()).toBe('');
    expect(storage.values.size).toBe(0);
  });

  it('restores the last authoritative snapshot', async () => {
    const storage = new MemoryStorage();
    const cache = new MobileCache(storage);
    await cache.saveSnapshot(snapshot);

    expect(await cache.loadSnapshot()).toEqual(snapshot);
  });
});
