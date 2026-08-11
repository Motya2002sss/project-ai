import { describe, expect, it, vi } from 'vitest';

import { AuthApi, AuthApiError } from '../authApi';

function json(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

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
});
