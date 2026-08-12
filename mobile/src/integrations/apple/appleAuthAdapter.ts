import type { AppleSignInInput } from '../../api/authApi';
import {
  defaultStorageTimeoutMs,
  withStorageDeadline,
} from '../../storage/storageDeadline';

export interface AppleChallenge {
  state: string;
  nonce: string;
}

export interface AppleAuthorizationCredential {
  identityToken: string;
  fullName?: string;
}

export interface AppleAuthorizationAdapter {
  isSupported(): Promise<boolean>;
  authorize(challenge: AppleChallenge): Promise<AppleAuthorizationCredential>;
}

export interface AppleDeviceMetadata {
  deviceId: string;
  deviceName?: string;
  platform?: string;
  osVersion?: string;
}

export type AppleAuthFlowErrorReason =
  | 'unsupported'
  | 'cancelled'
  | 'missing_identity_token'
  | 'authorization_failed';

export class AppleAuthFlowError extends Error {
  constructor(readonly reason: AppleAuthFlowErrorReason) {
    super('Apple authentication failed');
  }
}

interface AppleSignInDependencies<TResult> {
  device: AppleDeviceMetadata;
  native: AppleAuthorizationAdapter;
  createChallenge(deviceId: string): Promise<AppleChallenge>;
  exchange(input: AppleSignInInput): Promise<TResult>;
}

export async function runAppleSignIn<TResult>(
  dependencies: AppleSignInDependencies<TResult>,
): Promise<TResult> {
  if (!(await dependencies.native.isSupported())) {
    throw new AppleAuthFlowError('unsupported');
  }
  const challenge = await dependencies.createChallenge(
    dependencies.device.deviceId,
  );
  const credential = await dependencies.native.authorize(challenge);
  if (!credential.identityToken) {
    throw new AppleAuthFlowError('missing_identity_token');
  }
  return dependencies.exchange({
    identityToken: credential.identityToken,
    state: challenge.state,
    nonce: challenge.nonce,
    ...(credential.fullName ? { name: credential.fullName } : {}),
    device: dependencies.device,
  });
}

const deviceIdKey = 'ai-life-planner:apple-device-id:v1';

export interface AppleDeviceMetadataStorage {
  getItem(key: string): Promise<string | null>;
  setItem(key: string, value: string): Promise<void>;
}

interface AppleDeviceMetadataDependencies {
  storage: AppleDeviceMetadataStorage;
  createDeviceId: () => string;
  platform: string;
  osVersion: string;
  timeoutMs?: number;
}

export async function resolveAppleDeviceMetadata(
  dependencies: AppleDeviceMetadataDependencies,
): Promise<AppleDeviceMetadata> {
  const timeoutMs = dependencies.timeoutMs ?? defaultStorageTimeoutMs;
  let deviceId = await withStorageDeadline(
    dependencies.storage.getItem(deviceIdKey),
    timeoutMs,
  );
  if (!deviceId) {
    deviceId = dependencies.createDeviceId();
    await withStorageDeadline(
      dependencies.storage.setItem(deviceIdKey, deviceId),
      timeoutMs,
    );
  }
  return {
    deviceId,
    platform: dependencies.platform,
    osVersion: dependencies.osVersion,
  };
}

export async function getAppleDeviceMetadata(): Promise<AppleDeviceMetadata> {
  const [{ default: AsyncStorage }, Crypto, { Platform }] = await Promise.all([
    import('@react-native-async-storage/async-storage'),
    import('expo-crypto'),
    import('react-native'),
  ]);
  return resolveAppleDeviceMetadata({
    storage: AsyncStorage,
    createDeviceId: () => Crypto.randomUUID(),
    platform: Platform.OS,
    osVersion: String(Platform.Version),
  });
}

export async function createNativeAppleAuthorizationAdapter(): Promise<AppleAuthorizationAdapter> {
  const { Platform } = await import('react-native');
  if (Platform.OS !== 'ios') return unsupportedAdapter;
  const AppleAuthentication = await import('expo-apple-authentication');
  return {
    isSupported: () => AppleAuthentication.isAvailableAsync(),
    async authorize(challenge) {
      try {
        const credential = await AppleAuthentication.signInAsync({
          requestedScopes: [
            AppleAuthentication.AppleAuthenticationScope.FULL_NAME,
            AppleAuthentication.AppleAuthenticationScope.EMAIL,
          ],
          state: challenge.state,
          nonce: challenge.nonce,
        });
        if (!credential.identityToken) {
          throw new AppleAuthFlowError('missing_identity_token');
        }
        const parts = [credential.fullName?.givenName, credential.fullName?.familyName]
          .filter((part): part is string => Boolean(part?.trim()))
          .map((part) => part.trim());
        return {
          identityToken: credential.identityToken,
          ...(parts.length ? { fullName: parts.join(' ') } : {}),
        };
      } catch (error: unknown) {
        if (error instanceof AppleAuthFlowError) throw error;
        if (
          typeof error === 'object' &&
          error !== null &&
          'code' in error &&
          error.code === 'ERR_REQUEST_CANCELED'
        ) {
          throw new AppleAuthFlowError('cancelled');
        }
        throw new AppleAuthFlowError('authorization_failed');
      }
    },
  };
}

const unsupportedAdapter: AppleAuthorizationAdapter = {
  async isSupported() {
    return false;
  },
  async authorize() {
    throw new AppleAuthFlowError('unsupported');
  },
};
