import type { AuthStatus } from './authReducer';

export type AppArea =
  | 'app'
  | 'dogfood_setup'
  | 'sign_in'
  | 'onboarding'
  | 'onboarding_preview';

export type DogfoodAccess = 'checking' | 'allowed' | 'denied';
export type GateOnboardingStatus =
  | 'unknown'
  | 'checking'
  | 'not_started'
  | 'in_progress'
  | 'completed'
  | 'failed';

export type AppGateDecision =
  | { kind: 'allow' }
  | { kind: 'loading' }
  | { kind: 'blocked' }
  | { kind: 'redirect'; href: '/' | '/sign-in' | '/onboarding' };

interface AppGateInput {
  authStatus: AuthStatus;
  currentArea: AppArea;
  dogfoodAccess: DogfoodAccess;
  dogfoodRuntimeEnabled?: boolean;
  offlineIdentityAvailable?: boolean;
  onboardingStatus: GateOnboardingStatus;
}

const dogfoodAccessListeners = new Set<() => void>();

export function subscribeDogfoodAccessChanges(
  developmentEnabled: boolean,
  listener: () => void,
): () => void {
  if (!developmentEnabled) return () => undefined;
  dogfoodAccessListeners.add(listener);
  return () => {
    dogfoodAccessListeners.delete(listener);
  };
}

export function notifyDogfoodAccessChanged(
  developmentEnabled: boolean,
): void {
  if (!developmentEnabled) return;
  for (const listener of [...dogfoodAccessListeners]) listener();
}

export function decideAppGate(input: AppGateInput): AppGateDecision {
  if (input.authStatus === 'hydrating' || input.authStatus === 'refreshing') {
    return { kind: 'loading' };
  }

  if (input.authStatus === 'expired' && input.offlineIdentityAvailable) {
    return { kind: 'allow' };
  }

  if (input.authStatus !== 'authenticated') {
    if (input.dogfoodAccess === 'checking') return { kind: 'loading' };
    if (input.dogfoodAccess === 'allowed') return { kind: 'allow' };
    if (
      input.dogfoodRuntimeEnabled &&
      input.currentArea === 'dogfood_setup'
    ) {
      return { kind: 'allow' };
    }
    if (
      input.currentArea === 'sign_in' ||
      input.currentArea === 'onboarding'
    ) {
      return { kind: 'allow' };
    }
    return { kind: 'redirect', href: '/sign-in' };
  }

  if (
    input.currentArea === 'onboarding' ||
    input.currentArea === 'onboarding_preview'
  ) {
    return { kind: 'allow' };
  }

  if (
    input.onboardingStatus === 'unknown' ||
    input.onboardingStatus === 'checking'
  ) {
    return { kind: 'loading' };
  }
  if (input.onboardingStatus === 'failed') return { kind: 'blocked' };
  if (input.onboardingStatus !== 'completed') {
    return { kind: 'redirect', href: '/onboarding' };
  }
  if (input.currentArea === 'sign_in') {
    return { kind: 'redirect', href: '/' };
  }
  return { kind: 'allow' };
}

export function appAreaFromSegment(segment: string | undefined): AppArea {
  if (segment === 'sign-in') return 'sign_in';
  if (segment === 'setup') return 'dogfood_setup';
  if (segment === 'onboarding') return 'onboarding';
  if (segment === 'onboarding-preview') return 'onboarding_preview';
  return 'app';
}

export function shouldRevalidateOnboarding(
  previousArea: AppArea,
  currentArea: AppArea,
): boolean {
  return (
    currentArea === 'app' &&
    (previousArea === 'onboarding' || previousArea === 'onboarding_preview')
  );
}
