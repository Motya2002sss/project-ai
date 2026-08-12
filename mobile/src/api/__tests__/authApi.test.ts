import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  AuthApi,
  AuthApiError,
  AuthOperationCoordinator,
  finalizeProvenSessionRevocation,
  isProvenSessionRevocation,
} from '../authApi';

function json(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

afterEach(() => {
  vi.useRealTimers();
});

describe('AuthApi', () => {
  it('sends the Apple credential without any client-owned user identity', async () => {
    const fetchImpl = vi.fn(
      async (_input: string | URL | Request, _init?: RequestInit) =>
        json({
        access_token: 'access',
        refresh_token: 'refresh',
        user: {
          public_id: 'public-user',
          name: 'Матвей',
          email: null,
          timezone: 'Europe/Moscow',
        },
        }),
    );
    const api = new AuthApi({ baseUrl: 'https://api.example.test/', fetchImpl });

    const result = await api.signInWithApple({
      identityToken: 'identity-secret',
      state: 'state',
      nonce: 'nonce',
      name: 'Матвей',
      device: { deviceId: 'iphone-1', platform: 'ios', osVersion: '19.0' },
    });

    expect(result).toEqual({
      credentials: { accessToken: 'access', refreshToken: 'refresh' },
      user: {
        publicId: 'public-user',
        name: 'Матвей',
        email: null,
        timezone: 'Europe/Moscow',
      },
    });
    const [url, init] = fetchImpl.mock.calls[0]!;
    expect(url).toBe('https://api.example.test/api/v2/auth/apple');
    const body = JSON.parse(String(init?.body)) as Record<string, unknown>;
    expect(body).toMatchObject({
      identity_token: 'identity-secret',
      state: 'state',
      nonce: 'nonce',
      device: { device_id: 'iphone-1', platform: 'ios', os_version: '19.0' },
    });
    expect(body).not.toHaveProperty('user_id');
    expect(body).not.toHaveProperty('user_external_id');
  });

  it('maps rotation credentials and authenticates me with the access bearer', async () => {
    const fetchImpl = vi
      .fn(async (_input: string | URL | Request, _init?: RequestInit) => json({}))
      .mockResolvedValueOnce(
        json({ access_token: 'rotated-access', refresh_token: 'rotated-refresh' }),
      )
      .mockResolvedValueOnce(
        json({
          public_id: 'public-user',
          name: null,
          email: null,
          timezone: 'UTC',
        }),
      );
    const api = new AuthApi({ baseUrl: 'https://api.example.test', fetchImpl });

    await expect(api.refresh('old-refresh')).resolves.toEqual({
      accessToken: 'rotated-access',
      refreshToken: 'rotated-refresh',
    });
    await expect(api.me('rotated-access')).resolves.toMatchObject({
      publicId: 'public-user',
    });

    expect(JSON.parse(String(fetchImpl.mock.calls[0]![1]?.body))).toEqual({
      refresh_token: 'old-refresh',
    });
    expect(fetchImpl.mock.calls[1]![1]?.headers).toMatchObject({
      Authorization: 'Bearer rotated-access',
    });
  });

  it('returns a typed status without exposing backend error text', async () => {
    const api = new AuthApi({
      baseUrl: 'https://api.example.test',
      fetchImpl: async () => json({ detail: 'secret backend detail' }, 401),
    });

    const error = await api.refresh('revoked').catch((reason: unknown) => reason);

    expect(error).toBeInstanceOf(AuthApiError);
    expect(error).toMatchObject({ status: 401 });
    expect(String(error)).not.toContain('secret backend detail');
  });

  it('aborts and settles an auth request at its bounded deadline', async () => {
    vi.useFakeTimers();
    let transportSignal: AbortSignal | null = null;
    const api = new AuthApi({
      baseUrl: 'https://api.example.test',
      timeoutMs: 25,
      fetchImpl: async (_input, init) => {
        transportSignal = init?.signal ?? null;
        return new Promise<Response>(() => undefined);
      },
    });
    let settled = false;
    const request = api.me('access-token').catch((error: unknown) => error);
    void request.finally(() => {
      settled = true;
    });

    await vi.advanceTimersByTimeAsync(25);
    await Promise.resolve();

    expect((transportSignal as AbortSignal | null)?.aborted).toBe(true);
    expect(settled).toBe(true);
    await expect(request).resolves.toBeInstanceOf(AuthApiError);
  });

  it('purges a local session only for a proven 401 revocation', () => {
    expect(isProvenSessionRevocation(new AuthApiError(401))).toBe(true);
    expect(isProvenSessionRevocation(new AuthApiError(500))).toBe(false);
    expect(isProvenSessionRevocation(new AuthApiError(200))).toBe(false);
    expect(isProvenSessionRevocation(new AuthApiError(null))).toBe(false);
    expect(isProvenSessionRevocation(new TypeError('offline'))).toBe(false);
  });

  it('serializes secure mutations and rejects stale auth epochs', async () => {
    const coordinator = new AuthOperationCoordinator();
    const events: string[] = [];
    let release!: () => void;
    const wait = new Promise<void>((resolve) => {
      release = resolve;
    });
    const refreshEpoch = coordinator.currentEpoch();
    const activeRefresh = coordinator.runIfCurrent(refreshEpoch, async () => {
      events.push('refresh-started');
      await wait;
      events.push('refresh-write');
      return 'rotated';
    });
    await Promise.resolve();
    const queuedRefresh = coordinator.runIfCurrent(refreshEpoch, async () => {
      events.push('stale-refresh-write');
      return 'stale';
    });
    const logoutEpoch = coordinator.invalidate();
    const logoutClear = coordinator.runIfCurrent(logoutEpoch, async () => {
      events.push('logout-clear');
      return undefined;
    });

    release();

    await expect(activeRefresh).resolves.toMatchObject({ current: false });
    await expect(queuedRefresh).resolves.toEqual({ current: false, value: null });
    await expect(logoutClear).resolves.toMatchObject({ current: true });
    expect(events).toEqual([
      'refresh-started',
      'refresh-write',
      'logout-clear',
    ]);
  });

  it('blocks a stale 401 recovery that starts after logout begins', async () => {
    const coordinator = new AuthOperationCoordinator();
    const requestEpoch = coordinator.captureRecoveryEpoch();

    const logoutEpoch = coordinator.blockRecovery();

    expect(requestEpoch).toBe(0);
    expect(logoutEpoch).toBe(1);
    expect(coordinator.captureRecoveryEpoch()).toBeNull();
    expect(coordinator.authorizeRecovery(requestEpoch!)).toBe(false);

    const signInEpoch = coordinator.invalidate();
    expect(coordinator.captureRecoveryEpoch()).toBeNull();
    expect(coordinator.authorizeRecovery(signInEpoch)).toBe(true);
    expect(coordinator.captureRecoveryEpoch()).toBe(signInEpoch);
  });

  it('publishes terminal revocation even when secure clearing fails', async () => {
    const coordinator = new AuthOperationCoordinator();
    const publishRevoked = vi.fn();

    await finalizeProvenSessionRevocation(
      coordinator,
      async () => {
        throw new Error('SecureStore unavailable');
      },
      publishRevoked,
    );

    expect(publishRevoked).toHaveBeenCalledTimes(1);
    expect(coordinator.captureRecoveryEpoch()).toBeNull();
  });
});
