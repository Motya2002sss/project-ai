import AsyncStorage from '@react-native-async-storage/async-storage';
import * as SecureStore from 'expo-secure-store';

export interface SessionCredentials {
  accessToken: string;
  refreshToken: string;
}

export interface SecureKeyValueStorage {
  getItemAsync(key: string): Promise<string | null>;
  setItemAsync(key: string, value: string): Promise<void>;
  deleteItemAsync(key: string): Promise<void>;
}

export interface PublicKeyValueStorage {
  getItem(key: string): Promise<string | null>;
  setItem(key: string, value: string): Promise<void>;
  removeItem(key: string): Promise<void>;
}

const accessTokenKey = 'ai-life-planner.access-token.v1';
const refreshTokenKey = 'ai-life-planner.refresh-token.v1';
const currentUserScopeKey = 'ai-life-planner:current-user-scope:v1';

export class SessionVault {
  constructor(private readonly storage: SecureKeyValueStorage) {}

  async load(): Promise<SessionCredentials | null> {
    const [accessToken, refreshToken] = await Promise.all([
      this.storage.getItemAsync(accessTokenKey),
      this.storage.getItemAsync(refreshTokenKey),
    ]);
    if (!accessToken || !refreshToken) {
      if (accessToken || refreshToken) await this.clear();
      return null;
    }
    return { accessToken, refreshToken };
  }

  async save(credentials: SessionCredentials): Promise<void> {
    await Promise.all([
      this.storage.setItemAsync(accessTokenKey, credentials.accessToken),
      this.storage.setItemAsync(refreshTokenKey, credentials.refreshToken),
    ]);
  }

  async clear(): Promise<void> {
    await Promise.all([
      this.storage.deleteItemAsync(accessTokenKey),
      this.storage.deleteItemAsync(refreshTokenKey),
    ]);
  }
}

export class SessionScopeStorage {
  constructor(private readonly storage: PublicKeyValueStorage) {}

  load(): Promise<string | null> {
    return this.storage.getItem(currentUserScopeKey);
  }

  async save(publicUserId: string): Promise<void> {
    if (!publicUserId.trim()) throw new Error('publicUserId is required');
    await this.storage.setItem(currentUserScopeKey, publicUserId);
  }

  async clear(): Promise<void> {
    await this.storage.removeItem(currentUserScopeKey);
  }
}

export const sessionVault = new SessionVault(SecureStore);
export const sessionScopeStorage = new SessionScopeStorage(AsyncStorage);
