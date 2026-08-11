import AsyncStorage from '@react-native-async-storage/async-storage';
import * as SecureStore from 'expo-secure-store';
import { Platform } from 'react-native';

import type { DaySnapshotDto } from '../api/types';
import { DOGFOOD_CACHE_SCOPE, MobileCache } from './cache';

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
  return cacheFor(publicUserId).loadSnapshot();
}

export async function saveCachedSnapshot(
  snapshot: DaySnapshotDto,
  publicUserId = DOGFOOD_CACHE_SCOPE,
): Promise<void> {
  await cacheFor(publicUserId).saveSnapshot(snapshot);
}

export async function loadCaptureDraft(
  publicUserId = DOGFOOD_CACHE_SCOPE,
): Promise<string> {
  return cacheFor(publicUserId).loadDraft();
}

export async function saveCaptureDraft(
  value: string,
  publicUserId = DOGFOOD_CACHE_SCOPE,
): Promise<void> {
  await cacheFor(publicUserId).saveDraft(value);
}

export async function clearUserData(publicUserId: string): Promise<void> {
  await cacheFor(publicUserId).clearUserData();
  caches.delete(publicUserId);
}

export async function getDogfoodToken(): Promise<string | null> {
  if (process.env.NODE_ENV === 'production') return null;
  if (Platform.OS === 'web') {
    return AsyncStorage.getItem(webDogfoodTokenKey);
  }
  return SecureStore.getItemAsync(nativeDogfoodTokenKey);
}

export async function saveDogfoodToken(value: string): Promise<void> {
  const token = value.trim();
  if (process.env.NODE_ENV === 'production') return;
  if (Platform.OS === 'web') {
    if (token) await AsyncStorage.setItem(webDogfoodTokenKey, token);
    else await AsyncStorage.removeItem(webDogfoodTokenKey);
    return;
  }
  if (token) await SecureStore.setItemAsync(nativeDogfoodTokenKey, token);
  else await SecureStore.deleteItemAsync(nativeDogfoodTokenKey);
}
