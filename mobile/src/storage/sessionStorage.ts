import * as SecureStore from 'expo-secure-store';

import {
  defaultStorageTimeoutMs,
  withStorageDeadline,
} from './storageDeadline';

export { StorageDeadlineError } from './storageDeadline';

export interface SessionCredentials {
  accessToken: string;
  refreshToken: string;
}

export interface LoadedSession {
  source: 'current' | 'legacy';
  publicUserId: string | null;
  credentials: SessionCredentials;
}

export interface SecureKeyValueStorage {
  getItemAsync(key: string): Promise<string | null>;
  setItemAsync(key: string, value: string): Promise<void>;
  deleteItemAsync(key: string): Promise<void>;
}

const accessTokenKey = 'ai-life-planner.access-token.v1';
const refreshTokenKey = 'ai-life-planner.refresh-token.v1';
const sessionEnvelopeKey = 'ai-life-planner.session.v2';

export class SessionVault {
  private physicalTail: Promise<void> = Promise.resolve();

  constructor(
    private readonly storage: SecureKeyValueStorage,
    private readonly timeoutMs = defaultStorageTimeoutMs,
  ) {}

  load(): Promise<LoadedSession | null> {
    return withStorageDeadline(
      this.enqueuePhysical(async () => {
        const encodedEnvelope = await this.storage.getItemAsync(
          sessionEnvelopeKey,
        );
        if (encodedEnvelope !== null) {
          const envelope = decodeSessionEnvelope(encodedEnvelope);
          if (envelope) return envelope;
          await this.deleteKeys(
            [sessionEnvelopeKey, accessTokenKey, refreshTokenKey],
            true,
          );
          return null;
        }

        const [accessToken, refreshToken] = await Promise.all([
          this.storage.getItemAsync(accessTokenKey),
          this.storage.getItemAsync(refreshTokenKey),
        ]);
        if (!accessToken || !refreshToken) {
          if (accessToken || refreshToken) {
            await this.deleteKeys([accessTokenKey, refreshTokenKey], true);
          }
          return null;
        }
        return {
          source: 'legacy',
          publicUserId: null,
          credentials: { accessToken, refreshToken },
        };
      }),
      this.timeoutMs,
    );
  }

  save(
    publicUserId: string,
    credentials: SessionCredentials,
  ): Promise<void> {
    if (
      !publicUserId.trim() ||
      !credentials.accessToken.trim() ||
      !credentials.refreshToken.trim()
    ) {
      return Promise.reject(new Error('Complete session envelope is required'));
    }
    return withStorageDeadline(
      this.enqueuePhysical(async () => {
        await this.storage.setItemAsync(
          sessionEnvelopeKey,
          JSON.stringify({
            version: 2,
            publicUserId,
            accessToken: credentials.accessToken,
            refreshToken: credentials.refreshToken,
          }),
        );
        await this.deleteKeys([accessTokenKey, refreshTokenKey], false);
      }),
      this.timeoutMs,
    );
  }

  clear(): Promise<void> {
    return withStorageDeadline(
      this.enqueuePhysical(() =>
        this.deleteKeys(
          [sessionEnvelopeKey, accessTokenKey, refreshTokenKey],
          true,
        ),
      ),
      this.timeoutMs,
    );
  }

  private async deleteKeys(
    keys: readonly string[],
    throwOnFailure: boolean,
  ): Promise<void> {
    const results = await Promise.allSettled(
      keys.map((key) => this.storage.deleteItemAsync(key)),
    );
    if (!throwOnFailure) return;
    const failed = results.find(
      (result): result is PromiseRejectedResult =>
        result.status === 'rejected',
    );
    if (failed) throw failed.reason;
  }

  private enqueuePhysical<T>(operation: () => Promise<T>): Promise<T> {
    const result = this.physicalTail.then(operation);
    this.physicalTail = result.then(
      () => undefined,
      () => undefined,
    );
    return result;
  }
}

function decodeSessionEnvelope(value: string): LoadedSession | null {
  try {
    const payload: unknown = JSON.parse(value);
    if (
      typeof payload !== 'object' ||
      payload === null ||
      !('version' in payload) ||
      payload.version !== 2 ||
      !('publicUserId' in payload) ||
      typeof payload.publicUserId !== 'string' ||
      !payload.publicUserId.trim() ||
      !('accessToken' in payload) ||
      typeof payload.accessToken !== 'string' ||
      !payload.accessToken.trim() ||
      !('refreshToken' in payload) ||
      typeof payload.refreshToken !== 'string' ||
      !payload.refreshToken.trim()
    ) {
      return null;
    }
    return {
      source: 'current',
      publicUserId: payload.publicUserId,
      credentials: {
        accessToken: payload.accessToken,
        refreshToken: payload.refreshToken,
      },
    };
  } catch {
    return null;
  }
}

export const sessionVault = new SessionVault(SecureStore);
