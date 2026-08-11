import { describe, expect, it, vi } from 'vitest';

import {
  authReducer,
  initialAuthState,
  type AuthenticatedUser,
} from '../authReducer';
import { SessionRefreshCoordinator } from '../../../api/authApi';
import {
  SessionScopeStorage,
  SessionVault,
  type PublicKeyValueStorage,
  type SecureKeyValueStorage,
} from '../../../storage/sessionStorage';

vi.mock('expo-secure-store', () => ({}));
vi.mock('@react-native-async-storage/async-storage', () => ({
  default: {
    getItem: vi.fn(),
    setItem: vi.fn(),
    removeItem: vi.fn(),
  },
}));

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
      user: null,
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

  async getItemAsync(key: string) {
    return this.values.get(key) ?? null;
  }

  async setItemAsync(key: string, value: string) {
    this.values.set(key, value);
  }

  async deleteItemAsync(key: string) {
    this.values.delete(key);
  }
}

describe('SessionVault', () => {
  it('stores only access and refresh credentials and clears both', async () => {
    const secureStore = new MemorySecureStore();
    const vault = new SessionVault(secureStore);

    await vault.save({ accessToken: 'access-secret', refreshToken: 'refresh-secret' });

    expect([...secureStore.values.entries()]).toEqual([
      ['ai-life-planner.access-token.v1', 'access-secret'],
      ['ai-life-planner.refresh-token.v1', 'refresh-secret'],
    ]);
    await expect(vault.load()).resolves.toEqual({
      accessToken: 'access-secret',
      refreshToken: 'refresh-secret',
    });

    await vault.clear();
    expect(secureStore.values.size).toBe(0);
  });

  it('rejects a partial credential pair and removes the orphan', async () => {
    const secureStore = new MemorySecureStore();
    secureStore.values.set('ai-life-planner.access-token.v1', 'orphan');
    const vault = new SessionVault(secureStore);

    await expect(vault.load()).resolves.toBeNull();
    expect(secureStore.values.size).toBe(0);
  });
});

class MemoryPublicStore implements PublicKeyValueStorage {
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

describe('SessionScopeStorage', () => {
  it('retains only the non-secret public user scope needed for cold-start cleanup', async () => {
    const storage = new MemoryPublicStore();
    const scopes = new SessionScopeStorage(storage);

    await scopes.save(user.publicId);

    expect([...storage.values.entries()]).toEqual([
      ['ai-life-planner:current-user-scope:v1', user.publicId],
    ]);
    await expect(scopes.load()).resolves.toBe(user.publicId);
    await scopes.clear();
    await expect(scopes.load()).resolves.toBeNull();
  });
});
