import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  authReducer,
  initialAuthState,
  type AuthenticatedUser,
} from '../authReducer';
import { SessionRefreshCoordinator } from '../../../api/authApi';
import {
  SessionVault,
  VolatileSessionStore,
  type SecureKeyValueStorage,
} from '../../../storage/sessionStorage';
import {
  cachedIdentityForScope,
  loadCredentialsForPlatform,
} from '../sessionHydrationPolicy';

vi.mock('expo-secure-store', () => ({}));

afterEach(() => {
  vi.useRealTimers();
});

const user: AuthenticatedUser = {
  publicId: '20d7c006-d7e4-4d46-ac5a-2f704033a607',
  name: 'Матвей',
  email: null,
  timezone: 'Europe/Moscow',
};

describe('authReducer', () => {
  it('hydrates a cold launch into an authenticated account', () => {
    const hydrated = authReducer(initialAuthState, {
      type: 'hydrate/authenticated',
      user,
    });

    expect(hydrated).toEqual({ status: 'authenticated', user, error: null });
  });

  it('represents unauthenticated, refreshing, expired and revoked sessions explicitly', () => {
    const unauthenticated = authReducer(initialAuthState, {
      type: 'hydrate/unauthenticated',
    });
    const refreshing = authReducer(
      { status: 'authenticated', user, error: null },
      { type: 'refresh/started' },
    );
    const expired = authReducer(refreshing, {
      type: 'session/expired',
      message: 'Сессия истекла',
    });
    const revoked = authReducer(
      { status: 'authenticated', user, error: null },
      { type: 'session/revoked' },
    );

    expect(unauthenticated.status).toBe('unauthenticated');
    expect(refreshing).toMatchObject({ status: 'refreshing', user });
    expect(expired).toEqual({
      status: 'expired',
      user,
      error: 'Сессия истекла',
    });
    expect(revoked).toEqual({ status: 'revoked', user: null, error: null });
  });

  it('clears in-memory identity on logout and account deletion', () => {
    const authenticated = { status: 'authenticated', user, error: null } as const;

    expect(authReducer(authenticated, { type: 'logout/completed' })).toEqual({
      status: 'unauthenticated',
      user: null,
      error: null,
    });
    expect(authReducer(authenticated, { type: 'account/deleted' })).toEqual({
      status: 'unauthenticated',
      user: null,
      error: null,
    });
  });
});

describe('SessionRefreshCoordinator', () => {
  it('shares one refresh request between simultaneous authentication failures', async () => {
    let release!: () => void;
    const wait = new Promise<void>((resolve) => {
      release = resolve;
    });
    const refresh = vi.fn(async () => {
      await wait;
      return 'rotated-access-token';
    });
    const coordinator = new SessionRefreshCoordinator(refresh);

    const first = coordinator.refresh();
    const second = coordinator.refresh();
    release();

    await expect(Promise.all([first, second])).resolves.toEqual([
      'rotated-access-token',
      'rotated-access-token',
    ]);
    expect(refresh).toHaveBeenCalledTimes(1);
  });

  it('starts a new refresh only after the previous flight settles', async () => {
    const refresh = vi.fn(async () => `access-${refresh.mock.calls.length}`);
    const coordinator = new SessionRefreshCoordinator(refresh);

    await expect(coordinator.refresh()).resolves.toBe('access-1');
    await expect(coordinator.refresh()).resolves.toBe('access-2');
    expect(refresh).toHaveBeenCalledTimes(2);
  });
});

class MemorySecureStore implements SecureKeyValueStorage {
  readonly values = new Map<string, string>();
  readonly setItemCalls: [string, string][] = [];
  failNextSet = false;

  async getItemAsync(key: string) {
    return this.values.get(key) ?? null;
  }

  async setItemAsync(key: string, value: string) {
    this.setItemCalls.push([key, value]);
    if (this.failNextSet) {
      this.failNextSet = false;
      throw new Error('SecureStore write failed');
    }
    this.values.set(key, value);
  }

  async deleteItemAsync(key: string) {
    this.values.delete(key);
  }
}

describe('SessionVault', () => {
  it('keeps a development session available without native storage', () => {
    const store = new VolatileSessionStore();
    store.save(user.publicId, {
      accessToken: 'dogfood-access',
      refreshToken: 'dogfood-refresh',
    });

    expect(store.load()).toMatchObject({
      publicUserId: user.publicId,
      credentials: { accessToken: 'dogfood-access' },
    });
    store.clear();
    expect(store.load()).toBeNull();
  });

  it('atomically binds credentials and public identity in one versioned envelope', async () => {
    const secureStore = new MemorySecureStore();
    const vault = new SessionVault(secureStore);

    await vault.save(user.publicId, {
      accessToken: 'access-secret',
      refreshToken: 'refresh-secret',
    });

    expect([...secureStore.values.entries()]).toEqual([
      [
        'ai-life-planner.session.v2',
        JSON.stringify({
          version: 2,
          publicUserId: user.publicId,
          accessToken: 'access-secret',
          refreshToken: 'refresh-secret',
        }),
      ],
    ]);
    await expect(vault.load()).resolves.toEqual({
      source: 'current',
      publicUserId: user.publicId,
      credentials: {
        accessToken: 'access-secret',
        refreshToken: 'refresh-secret',
      },
    });

    await vault.clear();
    expect(secureStore.values.size).toBe(0);
  });

  it('keeps the previous account envelope when an account-switch write fails', async () => {
    const secureStore = new MemorySecureStore();
    const vault = new SessionVault(secureStore);
    await vault.save('user-a', {
      accessToken: 'access-a',
      refreshToken: 'refresh-a',
    });
    secureStore.failNextSet = true;

    await expect(
      vault.save('user-b', {
        accessToken: 'access-b',
        refreshToken: 'refresh-b',
      }),
    ).rejects.toThrow('SecureStore write failed');

    await expect(vault.load()).resolves.toMatchObject({
      source: 'current',
      publicUserId: 'user-a',
      credentials: { accessToken: 'access-a', refreshToken: 'refresh-a' },
    });
  });

  it('replaces the complete account envelope without mixing account fields', async () => {
    const secureStore = new MemorySecureStore();
    const vault = new SessionVault(secureStore);
    await vault.save('user-a', {
      accessToken: 'access-a',
      refreshToken: 'refresh-a',
    });
    await vault.save('user-b', {
      accessToken: 'access-b',
      refreshToken: 'refresh-b',
    });

    expect(secureStore.setItemCalls).toHaveLength(2);
    expect(secureStore.values.size).toBe(1);
    await expect(vault.load()).resolves.toMatchObject({
      publicUserId: 'user-b',
      credentials: { accessToken: 'access-b', refreshToken: 'refresh-b' },
    });
  });

  it('loads a complete legacy pair as unbound until the server resolves its owner', async () => {
    const secureStore = new MemorySecureStore();
    secureStore.values.set(
      'ai-life-planner.access-token.v1',
      'legacy-access',
    );
    secureStore.values.set(
      'ai-life-planner.refresh-token.v1',
      'legacy-refresh',
    );
    const vault = new SessionVault(secureStore);

    await expect(vault.load()).resolves.toEqual({
      source: 'legacy',
      publicUserId: null,
      credentials: {
        accessToken: 'legacy-access',
        refreshToken: 'legacy-refresh',
      },
    });
    expect(secureStore.setItemCalls).toHaveLength(0);
  });

  it('migrates a verified legacy pair into one identity-bound envelope', async () => {
    const secureStore = new MemorySecureStore();
    secureStore.values.set(
      'ai-life-planner.access-token.v1',
      'legacy-access',
    );
    secureStore.values.set(
      'ai-life-planner.refresh-token.v1',
      'legacy-refresh',
    );
    const vault = new SessionVault(secureStore);
    const legacy = await vault.load();

    expect(legacy).toMatchObject({ source: 'legacy', publicUserId: null });
    await vault.save(user.publicId, legacy!.credentials);

    expect([...secureStore.values.keys()]).toEqual([
      'ai-life-planner.session.v2',
    ]);
    await expect(vault.load()).resolves.toEqual({
      source: 'current',
      publicUserId: user.publicId,
      credentials: {
        accessToken: 'legacy-access',
        refreshToken: 'legacy-refresh',
      },
    });
  });

  it('rejects a partial credential pair and removes the orphan', async () => {
    const secureStore = new MemorySecureStore();
    secureStore.values.set('ai-life-planner.access-token.v1', 'orphan');
    const vault = new SessionVault(secureStore);

    await expect(vault.load()).resolves.toBeNull();
    expect(secureStore.values.size).toBe(0);
  });

  it('rejects a malformed current envelope instead of falling back to stale legacy secrets', async () => {
    const secureStore = new MemorySecureStore();
    secureStore.values.set('ai-life-planner.session.v2', '{bad json');
    secureStore.values.set('ai-life-planner.access-token.v1', 'stale-access');
    secureStore.values.set('ai-life-planner.refresh-token.v1', 'stale-refresh');
    const vault = new SessionVault(secureStore);

    await expect(vault.load()).resolves.toBeNull();
    expect(secureStore.values.size).toBe(0);
  });

  it('bounds a never-settling SecureStore read', async () => {
    vi.useFakeTimers();
    const deleteItemAsync = vi.fn(async () => undefined);
    const vault = new SessionVault(
      {
        getItemAsync: () => new Promise<string | null>(() => undefined),
        setItemAsync: async () => undefined,
        deleteItemAsync,
      },
      25,
    );
    let settled = false;
    const load = vault.load().catch((error: unknown) => error);
    void load.finally(() => {
      settled = true;
    });

    await vi.advanceTimersByTimeAsync(25);
    await Promise.resolve();

    expect(settled).toBe(true);
    await expect(load).resolves.toBeInstanceOf(Error);
    expect(deleteItemAsync).not.toHaveBeenCalled();
  });

  it('keeps a timed-out physical save ahead of a newer clear', async () => {
    vi.useFakeTimers();
    const values = new Map<string, string>();
    const events: string[] = [];
    let releaseSet!: () => void;
    const waitForSet = new Promise<void>((resolve) => {
      releaseSet = resolve;
    });
    const vault = new SessionVault(
      {
        async getItemAsync(key) {
          return values.get(key) ?? null;
        },
        async setItemAsync(key, value) {
          events.push(`set:start:${key}`);
          await waitForSet;
          values.set(key, value);
          events.push(`set:end:${key}`);
        },
        async deleteItemAsync(key) {
          events.push(`delete:${key}`);
          values.delete(key);
        },
      },
      25,
    );
    const save = vault
      .save('user-a', { accessToken: 'access-a', refreshToken: 'refresh-a' })
      .catch((error: unknown) => error);

    await vi.advanceTimersByTimeAsync(25);
    await expect(save).resolves.toBeInstanceOf(Error);
    const clear = vault.clear();
    await Promise.resolve();

    expect(events).toEqual(['set:start:ai-life-planner.session.v2']);
    releaseSet();
    await expect(clear).resolves.toBeUndefined();
    expect(values.size).toBe(0);
    expect(events.indexOf('delete:ai-life-planner.session.v2')).toBeGreaterThan(
      events.indexOf('set:end:ai-life-planner.session.v2'),
    );
  });

  it('keeps a timed-out physical clear ahead of a newer account save', async () => {
    vi.useFakeTimers();
    const values = new Map<string, string>([
      [
        'ai-life-planner.session.v2',
        JSON.stringify({
          version: 2,
          publicUserId: 'user-a',
          accessToken: 'access-a',
          refreshToken: 'refresh-a',
        }),
      ],
    ]);
    const events: string[] = [];
    let releaseDelete!: () => void;
    const waitForDelete = new Promise<void>((resolve) => {
      releaseDelete = resolve;
    });
    let delayedCurrentDelete = true;
    const vault = new SessionVault(
      {
        async getItemAsync(key) {
          return values.get(key) ?? null;
        },
        async setItemAsync(key, value) {
          events.push(`set:${key}`);
          values.set(key, value);
        },
        async deleteItemAsync(key) {
          events.push(`delete:start:${key}`);
          if (key === 'ai-life-planner.session.v2' && delayedCurrentDelete) {
            delayedCurrentDelete = false;
            await waitForDelete;
          }
          values.delete(key);
          events.push(`delete:end:${key}`);
        },
      },
      25,
    );
    const clear = vault.clear().catch((error: unknown) => error);

    await vi.advanceTimersByTimeAsync(25);
    await expect(clear).resolves.toBeInstanceOf(Error);
    const save = vault.save('user-b', {
      accessToken: 'access-b',
      refreshToken: 'refresh-b',
    });
    await Promise.resolve();

    expect(events).not.toContain('set:ai-life-planner.session.v2');
    releaseDelete();
    await expect(save).resolves.toBeUndefined();
    await expect(vault.load()).resolves.toMatchObject({
      publicUserId: 'user-b',
      credentials: { accessToken: 'access-b', refreshToken: 'refresh-b' },
    });
  });

  it('bounds callers while a truly never-settling physical mutation keeps newer writes locked', async () => {
    vi.useFakeTimers();
    const deleteItemAsync = vi.fn(async () => undefined);
    const vault = new SessionVault(
      {
        getItemAsync: async () => null,
        setItemAsync: () => new Promise<void>(() => undefined),
        deleteItemAsync,
      },
      25,
    );
    const save = vault
      .save('user-a', { accessToken: 'access-a', refreshToken: 'refresh-a' })
      .catch((error: unknown) => error);

    await vi.advanceTimersByTimeAsync(25);
    await expect(save).resolves.toBeInstanceOf(Error);
    const clear = vault.clear().catch((error: unknown) => error);
    await vi.advanceTimersByTimeAsync(25);

    await expect(clear).resolves.toBeInstanceOf(Error);
    expect(deleteItemAsync).not.toHaveBeenCalled();
  });
});

describe('session hydration platform policy', () => {
  it('uses only a public scope bound inside the current secure envelope', () => {
    expect(cachedIdentityForScope(user.publicId, 'current')).toEqual({
      publicId: user.publicId,
      name: null,
      email: null,
      timezone: 'UTC',
    });
    expect(cachedIdentityForScope(user.publicId, 'legacy')).toBeNull();
    expect(cachedIdentityForScope(null, 'current')).toBeNull();
  });

  it('carries the stored public scope through a cold-start refresh', () => {
    const cached = cachedIdentityForScope(user.publicId, 'current')!;
    const offline = authReducer(initialAuthState, {
      type: 'session/expired',
      message: 'Проверяю сессию',
      user: cached,
    });
    const refreshing = authReducer(offline, { type: 'refresh/started' });

    expect(refreshing).toMatchObject({ status: 'refreshing', user: cached });
  });

  it('does not invoke the native SecureStore vault in web text mode', async () => {
    let nativeVaultCalled = false;
    const loadNativeVault = async () => {
      nativeVaultCalled = true;
      throw new Error('native SecureStore must not run on web');
    };

    await expect(
      loadCredentialsForPlatform('web', loadNativeVault),
    ).resolves.toBeNull();
    expect(nativeVaultCalled).toBe(false);
  });

  it('hydrates credentials from SecureStore on iOS', async () => {
    await expect(
      loadCredentialsForPlatform('ios', async () => ({
        accessToken: 'access',
        refreshToken: 'refresh',
      })),
    ).resolves.toEqual({ accessToken: 'access', refreshToken: 'refresh' });
  });

  it('contains a transient SecureStore read failure during cold-start hydration', async () => {
    const reportUnavailable = vi.fn();

    await expect(
      loadCredentialsForPlatform('ios', async () => {
        throw new Error('SecureStore temporarily unavailable');
      }, reportUnavailable),
    ).resolves.toBeNull();
    expect(reportUnavailable).toHaveBeenCalledTimes(1);
  });
});
