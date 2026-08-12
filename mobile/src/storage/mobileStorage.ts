import AsyncStorage from '@react-native-async-storage/async-storage';
import * as SecureStore from 'expo-secure-store';
import { Platform } from 'react-native';

import type { DaySnapshotDto } from '../api/types';
import { DOGFOOD_CACHE_SCOPE, MobileCache } from './cache';
import { withStorageDeadline } from './storageDeadline';

const nativeDogfoodTokenKey = 'ai-life-planner.dogfood-token.v1';
const webDogfoodTokenKey = 'ai-life-planner:dogfood-token:v1';
const caches = new Map<string, MobileCache>();

function cacheFor(publicUserId: string): MobileCache {
  const existing = caches.get(publicUserId);
  if (existing) return existing;
  const cache = new MobileCache(AsyncStorage, publicUserId);
  caches.set(publicUserId, cache);
  return cache;
}

export async function loadCachedSnapshot(
  publicUserId = DOGFOOD_CACHE_SCOPE,
): Promise<DaySnapshotDto | null> {
  return withStorageDeadline(cacheFor(publicUserId).loadSnapshot());
}

export async function saveCachedSnapshot(
  snapshot: DaySnapshotDto,
  publicUserId = DOGFOOD_CACHE_SCOPE,
): Promise<void> {
  await withStorageDeadline(
    cacheFor(publicUserId).saveSnapshot(snapshot),
  );
}

export async function loadCaptureDraft(
  publicUserId = DOGFOOD_CACHE_SCOPE,
): Promise<string> {
  return withStorageDeadline(cacheFor(publicUserId).loadDraft());
}

export async function saveCaptureDraft(
  value: string,
  publicUserId = DOGFOOD_CACHE_SCOPE,
): Promise<void> {
  await withStorageDeadline(cacheFor(publicUserId).saveDraft(value));
}

export async function clearUserData(publicUserId: string): Promise<void> {
  await withStorageDeadline(cacheFor(publicUserId).clearUserData());
  caches.delete(publicUserId);
}

export async function getDogfoodToken(): Promise<string | null> {
  if (process.env.NODE_ENV === 'production') return null;
  try {
    if (Platform.OS === 'web') {
      return await withStorageDeadline(
        AsyncStorage.getItem(webDogfoodTokenKey),
      );
    }
    return await withStorageDeadline(
      SecureStore.getItemAsync(nativeDogfoodTokenKey),
    );
  } catch {
    return null;
  }
}

export async function saveDogfoodToken(value: string): Promise<void> {
  const token = value.trim();
  if (process.env.NODE_ENV === 'production') return;
  if (Platform.OS === 'web') {
    if (token) {
      await withStorageDeadline(
        AsyncStorage.setItem(webDogfoodTokenKey, token),
      );
    } else {
      await withStorageDeadline(
        AsyncStorage.removeItem(webDogfoodTokenKey),
      );
    }
    return;
  }
  if (token) {
    await withStorageDeadline(
      SecureStore.setItemAsync(nativeDogfoodTokenKey, token),
    );
  } else {
    await withStorageDeadline(
      SecureStore.deleteItemAsync(nativeDogfoodTokenKey),
    );
  }
}
