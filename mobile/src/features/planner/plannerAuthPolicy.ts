import type { AuthStatus } from '../auth/authReducer';
import { DOGFOOD_CACHE_SCOPE } from '../../storage/cache';

export type PlannerAccess =
  | { kind: 'production'; scope: string }
  | { kind: 'dogfood'; scope: typeof DOGFOOD_CACHE_SCOPE }
  | { kind: 'locked'; scope: null };

export function resolvePlannerAccess(
  authStatus: AuthStatus,
  authenticatedPublicUserId: string | null,
  dogfoodEnabled: boolean,
  dogfoodTokenAvailable: boolean,
): PlannerAccess {
  if (authenticatedPublicUserId) {
    return { kind: 'production', scope: authenticatedPublicUserId };
  }
  if (isPlannerIdentityResolving(authStatus, false)) {
    return { kind: 'locked', scope: null };
  }
  if (dogfoodEnabled && dogfoodTokenAvailable) {
    return { kind: 'dogfood', scope: DOGFOOD_CACHE_SCOPE };
  }
  return { kind: 'locked', scope: null };
}

export function isPlannerIdentityResolving(
  authStatus: AuthStatus,
  hasUser: boolean,
): boolean {
  return (
    authStatus === 'hydrating' || (authStatus === 'refreshing' && !hasUser)
  );
}
