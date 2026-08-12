import { afterEach, describe, expect, it, vi } from 'vitest';

import type { PublicPathStorage } from '../pathCache';
import { PathCache } from '../pathCache';
import { pathResponse } from './pathFixtures';

afterEach(() => {
  vi.useRealTimers();
});

class MemoryStorage implements PublicPathStorage {
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

describe('PathCache', () => {
  it('keeps production Path responses in the user-scoped key cleared by MobileCache', async () => {
    const storage = new MemoryStorage();
    const first = new PathCache(storage, 'user/a');
    const second = new PathCache(storage, 'user/b');

    await first.save(pathResponse);

    expect(await first.load()).toEqual(pathResponse);
    expect(await second.load()).toBeNull();
    expect([...storage.values.keys()]).toEqual([
      'ai-life-planner:user:user%2Fa:goals:v2',
    ]);
  });

  it('discards malformed cached responses instead of presenting them as authoritative', async () => {
    const storage = new MemoryStorage();
    const cache = new PathCache(storage, 'user-a');
    storage.values.set(
      'ai-life-planner:user:user-a:goals:v2',
      JSON.stringify({ goals: [{ percentage: 88 }] }),
    );

    expect(await cache.load()).toBeNull();
    expect(storage.values.size).toBe(0);
  });

  it('removes a server-unavailable goal from the cached Path response', async () => {
    const storage = new MemoryStorage();
    const cache = new PathCache(storage, 'user-a');
    await cache.save(pathResponse);

    await cache.removeGoal(pathResponse.goals[0]!.goal.public_id);

    expect((await cache.load())?.goals.map((item) => item.goal.public_id)).toEqual(
      pathResponse.goals.slice(1).map((item) => item.goal.public_id),
    );
  });

  it('bounds a never-settling cache read without purging the user scope', async () => {
    vi.useFakeTimers();
    const removeItem = vi.fn(async () => undefined);
    const cache = new PathCache(
      {
        getItem: () => new Promise<string | null>(() => undefined),
        setItem: async () => undefined,
        removeItem,
      },
      'user-a',
      25,
    );
    const load = cache.load().catch((error: unknown) => error);

    await vi.advanceTimersByTimeAsync(25);

    await expect(load).resolves.toBeInstanceOf(Error);
    expect(removeItem).not.toHaveBeenCalled();
  });
});
