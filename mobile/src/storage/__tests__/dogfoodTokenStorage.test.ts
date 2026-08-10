import { beforeEach, describe, expect, it, vi } from 'vitest';

import { getDogfoodToken, saveDogfoodToken } from '../mobileStorage';

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

vi.mock('react-native', () => ({ Platform: { OS: 'ios' } }));
vi.mock('expo-secure-store', () => nativeStore);
vi.mock('@react-native-async-storage/async-storage', () => ({
  default: {
    getItem: vi.fn(),
    setItem: vi.fn(),
    removeItem: vi.fn(),
  },
}));

describe('native dogfood token storage', () => {
  beforeEach(() => {
    nativeStore.values.clear();
    vi.clearAllMocks();
  });

  it('persists the token using a SecureStore-compatible key', async () => {
    await expect(saveDogfoodToken('  local-secret  ')).resolves.toBeUndefined();

    expect(await getDogfoodToken()).toBe('local-secret');
    expect([...nativeStore.values.keys()]).toEqual([
      'ai-life-planner.dogfood-token.v1',
    ]);
  });
});
