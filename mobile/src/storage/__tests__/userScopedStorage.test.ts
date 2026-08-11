import { describe, expect, it } from 'vitest';

import type { DaySnapshotDto } from '../../api/types';
import {
  DOGFOOD_CACHE_SCOPE,
  MobileCache,
  type KeyValueStorage,
} from '../cache';
import { encodeSnapshot } from '../snapshotCodec';

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

function snapshot(date: string): DaySnapshotDto {
  return {
    date,
    focus_text: `Фокус ${date}`,
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
      date,
      summary: null,
      focus_text: `Фокус ${date}`,
      energy_level: null,
      budget_limit: null,
      status: 'draft',
      version: 0,
      items: [],
    },
    plan_version: 0,
  };
}

describe('user-scoped mobile storage', () => {
  it('never exposes Today or draft data across two accounts', async () => {
    const storage = new MemoryStorage();
    const first = new MobileCache(storage, 'user-a');
    const second = new MobileCache(storage, 'user-b');
    await first.saveSnapshot(snapshot('2026-08-11'));
    await first.saveDraft('Личный текст первого пользователя');

    expect(await second.loadSnapshot()).toBeNull();
    expect(await second.loadDraft()).toBe('');

    await second.saveSnapshot(snapshot('2026-08-12'));
    await second.saveDraft('Текст второго пользователя');
    expect((await first.loadSnapshot())?.date).toBe('2026-08-11');
    expect(await first.loadDraft()).toBe('Личный текст первого пользователя');
  });

  it('clears every known key for only the requested user on logout or deletion', async () => {
    const storage = new MemoryStorage();
    const first = new MobileCache(storage, 'user-a');
    const second = new MobileCache(storage, 'user-b');
    await first.saveSnapshot(snapshot('2026-08-11'));
    await first.saveDraft('Удалить');
    await second.saveSnapshot(snapshot('2026-08-12'));
    await second.saveDraft('Оставить');

    await first.clearUserData();

    expect(await first.loadSnapshot()).toBeNull();
    expect(await first.loadDraft()).toBe('');
    expect((await second.loadSnapshot())?.date).toBe('2026-08-12');
    expect(await second.loadDraft()).toBe('Оставить');
  });

  it('migrates legacy P0 data only into the explicit dogfood namespace', async () => {
    const storage = new MemoryStorage();
    storage.values.set(
      'ai-life-planner:today:v1',
      encodeSnapshot(snapshot('2026-08-10')),
    );
    storage.values.set('ai-life-planner:capture-draft:v1', 'Legacy draft');

    const productionUser = new MobileCache(storage, 'production-user');
    expect(await productionUser.loadSnapshot()).toBeNull();
    expect(await productionUser.loadDraft()).toBe('');

    const dogfood = new MobileCache(storage, DOGFOOD_CACHE_SCOPE);
    expect((await dogfood.loadSnapshot())?.date).toBe('2026-08-10');
    expect(await dogfood.loadDraft()).toBe('Legacy draft');
    expect(storage.values.has('ai-life-planner:today:v1')).toBe(false);
    expect(storage.values.has('ai-life-planner:capture-draft:v1')).toBe(false);
  });
});
