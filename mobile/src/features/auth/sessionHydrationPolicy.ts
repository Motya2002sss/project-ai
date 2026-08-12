import type { AuthenticatedUser } from './authReducer';

export function cachedIdentityForScope(
  publicId: string | null,
  source: 'current' | 'legacy',
): AuthenticatedUser | null {
  if (source !== 'current' || !publicId?.trim()) return null;
  return {
    publicId,
    name: null,
    email: null,
    timezone: 'UTC',
  };
}

export async function loadCredentialsForPlatform<T>(
  platform: string,
  loadNativeCredentials: () => Promise<T | null>,
  reportStorageUnavailable: () => void = () => undefined,
): Promise<T | null> {
  if (platform === 'web') return null;
  try {
    return await loadNativeCredentials();
  } catch {
    reportStorageUnavailable();
    return null;
  }
}
