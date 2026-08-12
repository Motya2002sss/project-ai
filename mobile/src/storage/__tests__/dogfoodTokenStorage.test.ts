import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  getDogfoodToken,
  loadCachedSnapshot,
  saveDogfoodToken,
} from '../mobileStorage';

const nativeStore = vi.hoisted(() => {
  const values = new Map<string, string>();
  return {
    values,
    getItemAsync: vi.fn(async (key: string) => values.get(key) ?? null),
    setItemAsync: vi.fn(async (key: string, value: string) => {
      if (!/^[A-Za-z0-9._-]+$/.test(key)) {
        throw new Error('SecureStore key contains unsupported characters');
      }
      values.set(key, value);
    }),
    deleteItemAsync: vi.fn(async (key: string) => {
      values.delete(key);
    }),
  };
});

const publicStore = vi.hoisted(() => ({
  getItem: vi.fn<(key: string) => Promise<string | null>>(),
  setItem: vi.fn<(key: string, value: string) => Promise<void>>(),
  removeItem: vi.fn<(key: string) => Promise<void>>(),
}));

vi.mock('react-native', () => ({ Platform: { OS: 'ios' } }));
vi.mock('expo-secure-store', () => nativeStore);
vi.mock('@react-native-async-storage/async-storage', () => ({
  default: publicStore,
}));

describe('native dogfood token storage', () => {
  beforeEach(() => {
    nativeStore.values.clear();
    vi.clearAllMocks();
    publicStore.getItem.mockResolvedValue(null);
    publicStore.setItem.mockResolvedValue(undefined);
    publicStore.removeItem.mockResolvedValue(undefined);
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('persists the token using a SecureStore-compatible key', async () => {
    await expect(saveDogfoodToken('  local-secret  ')).resolves.toBeUndefined();

    expect(await getDogfoodToken()).toBe('local-secret');
    expect([...nativeStore.values.keys()]).toEqual([
      'ai-life-planner.dogfood-token.v1',
    ]);
  });

  it('fails closed when a native token read never settles', async () => {
    vi.useFakeTimers();
    nativeStore.getItemAsync.mockImplementationOnce(
      () => new Promise<string | null>(() => undefined),
    );
    let settled = false;
    const token = getDogfoodToken();
    void token.finally(() => {
      settled = true;
    });

    await vi.advanceTimersByTimeAsync(5_000);
    await Promise.resolve();

    expect(settled).toBe(true);
    await expect(token).resolves.toBeNull();
  });

  it('bounds a never-settling AsyncStorage cache read without deleting cached data', async () => {
    vi.useFakeTimers();
    publicStore.getItem.mockImplementationOnce(
      () => new Promise<string | null>(() => undefined),
    );
    let settled = false;
    const load = loadCachedSnapshot('deadline-user').catch(
      (error: unknown) => error,
    );
    void load.finally(() => {
      settled = true;
    });

    await vi.advanceTimersByTimeAsync(5_000);
    await Promise.resolve();

    expect(settled).toBe(true);
    await expect(load).resolves.toBeInstanceOf(Error);
    expect(publicStore.removeItem).not.toHaveBeenCalled();
  });
});
