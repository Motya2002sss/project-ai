import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  AppleAuthFlowError,
  resolveAppleDeviceMetadata,
  runAppleSignIn,
  type AppleAuthorizationAdapter,
} from '../appleAuthAdapter';

vi.mock('react-native', () => ({ Platform: { OS: 'ios', Version: '19.0' } }));
vi.mock('@react-native-async-storage/async-storage', () => ({ default: {} }));
vi.mock('expo-apple-authentication', () => ({}));
vi.mock('expo-crypto', () => ({}));

afterEach(() => {
  vi.useRealTimers();
});

describe('runAppleSignIn', () => {
  it('uses one server challenge for the native credential and backend exchange', async () => {
    const events: unknown[] = [];
    const native: AppleAuthorizationAdapter = {
      async isSupported() {
        return true;
      },
      async authorize(challenge) {
        events.push(['native', challenge]);
        return {
          identityToken: 'apple-identity-token',
          fullName: 'Матвей Иванов',
        };
      },
    };

    const result = await runAppleSignIn({
      device: {
        deviceId: 'iphone-1',
        platform: 'ios',
        osVersion: '19.0',
      },
      native,
      async createChallenge(deviceId) {
        events.push(['challenge', deviceId]);
        return { state: 'server-state', nonce: 'server-nonce' };
      },
      async exchange(input) {
        events.push(['exchange', input]);
        return { publicId: 'public-user' };
      },
    });

    expect(result).toEqual({ publicId: 'public-user' });
    expect(events).toEqual([
      ['challenge', 'iphone-1'],
      ['native', { state: 'server-state', nonce: 'server-nonce' }],
      [
        'exchange',
        {
          identityToken: 'apple-identity-token',
          state: 'server-state',
          nonce: 'server-nonce',
          name: 'Матвей Иванов',
          device: {
            deviceId: 'iphone-1',
            platform: 'ios',
            osVersion: '19.0',
          },
        },
      ],
    ]);
  });

  it('bounds a never-settling device identifier read before Apple sign-in', async () => {
    vi.useFakeTimers();
    const setItem = vi.fn(async () => undefined);
    const metadata = resolveAppleDeviceMetadata({
      storage: {
        getItem: () => new Promise<string | null>(() => undefined),
        setItem,
      },
      createDeviceId: () => 'new-device-id',
      platform: 'ios',
      osVersion: '19.0',
      timeoutMs: 25,
    }).catch((error: unknown) => error);

    await vi.advanceTimersByTimeAsync(25);

    await expect(metadata).resolves.toBeInstanceOf(Error);
    expect(setItem).not.toHaveBeenCalled();
  });

  it('fails honestly on web or unsupported devices before challenge or exchange', async () => {
    let challenged = false;
    let exchanged = false;

    const error = await runAppleSignIn({
      device: { deviceId: 'web-1', platform: 'web' },
      native: {
        async isSupported() {
          return false;
        },
        async authorize() {
          throw new Error('must not authorize');
        },
      },
      async createChallenge() {
        challenged = true;
        return { state: 'state', nonce: 'nonce' };
      },
      async exchange() {
        exchanged = true;
        return { publicId: 'fake' };
      },
    }).catch((reason: unknown) => reason);

    expect(error).toBeInstanceOf(AppleAuthFlowError);
    expect(error).toMatchObject({ reason: 'unsupported' });
    expect(challenged).toBe(false);
    expect(exchanged).toBe(false);
  });

  it('does not exchange a cancelled or tokenless native authorization', async () => {
    let exchanged = false;
    const native: AppleAuthorizationAdapter = {
      async isSupported() {
        return true;
      },
      async authorize() {
        throw new AppleAuthFlowError('cancelled');
      },
    };

    const error = await runAppleSignIn({
      device: { deviceId: 'iphone-1', platform: 'ios' },
      native,
      async createChallenge() {
        return { state: 'state', nonce: 'nonce' };
      },
      async exchange() {
        exchanged = true;
        return { publicId: 'fake' };
      },
    }).catch((reason: unknown) => reason);

    expect(error).toMatchObject({ reason: 'cancelled' });
    expect(exchanged).toBe(false);
  });
});
