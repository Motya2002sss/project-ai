import AsyncStorage from '@react-native-async-storage/async-storage';
import * as SecureStore from 'expo-secure-store';
import { Platform } from 'react-native';

import type { DaySnapshotDto } from '../api/types';
import { MobileCache } from './cache';

const dogfoodTokenKey = 'ai-life-planner:dogfood-token:v1';
const cache = new MobileCache(AsyncStorage);

export async function loadCachedSnapshot(): Promise<DaySnapshotDto | null> {
  return cache.loadSnapshot();
}

export async function saveCachedSnapshot(snapshot: DaySnapshotDto): Promise<void> {
  await cache.saveSnapshot(snapshot);
}

export async function loadCaptureDraft(): Promise<string> {
  return cache.loadDraft();
}

export async function saveCaptureDraft(value: string): Promise<void> {
  await cache.saveDraft(value);
}

export async function getDogfoodToken(): Promise<string | null> {
  if (Platform.OS === 'web') {
    if (process.env.NODE_ENV === 'production') return null;
    return AsyncStorage.getItem(dogfoodTokenKey);
  }
  return SecureStore.getItemAsync(dogfoodTokenKey);
}

export async function saveDogfoodToken(value: string): Promise<void> {
  const token = value.trim();
  if (Platform.OS === 'web') {
    if (process.env.NODE_ENV === 'production') return;
    if (token) await AsyncStorage.setItem(dogfoodTokenKey, token);
    else await AsyncStorage.removeItem(dogfoodTokenKey);
    return;
  }
  if (token) await SecureStore.setItemAsync(dogfoodTokenKey, token);
  else await SecureStore.deleteItemAsync(dogfoodTokenKey);
}
