export const apiBaseUrl = process.env.EXPO_PUBLIC_API_BASE_URL?.trim() ?? '';

export function resolveDogfoodRuntimeEnabled(
  nodeEnvironment: string | undefined,
  explicitFlag: string | undefined,
): boolean {
  return nodeEnvironment === 'development' && explicitFlag === 'true';
}

export const dogfoodRuntimeEnabled = resolveDogfoodRuntimeEnabled(
  process.env.NODE_ENV,
  process.env.EXPO_PUBLIC_ENABLE_DOGFOOD,
);

export const captureTimeoutMs = 15_000;
export const slowCaptureDelayMs = 5_000;
