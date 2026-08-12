import { describe, expect, it } from 'vitest';

import {
  appAreaFromSegment,
  decideAppGate,
  notifyDogfoodAccessChanged,
  subscribeDogfoodAccessChanges,
  shouldRevalidateOnboarding,
} from '../appGate';

describe('decideAppGate', () => {
  it('keeps private content covered while auth hydrates', () => {
    expect(
      decideAppGate({
        authStatus: 'hydrating',
        currentArea: 'app',
        dogfoodAccess: 'checking',
        onboardingStatus: 'unknown',
      }),
    ).toEqual({ kind: 'loading' });
  });

  it('allows a known account to read its cache when validation is offline', () => {
    expect(
      decideAppGate({
        authStatus: 'expired',
        currentArea: 'app',
        dogfoodAccess: 'denied',
        offlineIdentityAvailable: true,
        onboardingStatus: 'unknown',
      }),
    ).toEqual({ kind: 'allow' });
    expect(
      decideAppGate({
        authStatus: 'expired',
        currentArea: 'app',
        dogfoodAccess: 'denied',
        offlineIdentityAvailable: false,
        onboardingStatus: 'unknown',
      }),
    ).toEqual({ kind: 'redirect', href: '/sign-in' });
  });

  it('routes an unauthenticated production user to Sign in with Apple', () => {
    expect(
      decideAppGate({
        authStatus: 'unauthenticated',
        currentArea: 'app',
        dogfoodAccess: 'denied',
        onboardingStatus: 'unknown',
      }),
    ).toEqual({ kind: 'redirect', href: '/sign-in' });
  });

  it('allows an explicitly configured development dogfood session', () => {
    expect(
      decideAppGate({
        authStatus: 'unauthenticated',
        currentArea: 'app',
        dogfoodAccess: 'allowed',
        onboardingStatus: 'unknown',
      }),
    ).toEqual({ kind: 'allow' });
  });

  it('opens token setup only in a development dogfood runtime', () => {
    expect(appAreaFromSegment('setup')).toBe('dogfood_setup');
    expect(
      decideAppGate({
        authStatus: 'unauthenticated',
        currentArea: 'dogfood_setup',
        dogfoodAccess: 'denied',
        dogfoodRuntimeEnabled: true,
        onboardingStatus: 'unknown',
      }),
    ).toEqual({ kind: 'allow' });
    expect(
      decideAppGate({
        authStatus: 'unauthenticated',
        currentArea: 'dogfood_setup',
        dogfoodAccess: 'denied',
        dogfoodRuntimeEnabled: false,
        onboardingStatus: 'unknown',
      }),
    ).toEqual({ kind: 'redirect', href: '/sign-in' });
  });

  it('routes an authenticated new user through onboarding', () => {
    expect(
      decideAppGate({
        authStatus: 'authenticated',
        currentArea: 'app',
        dogfoodAccess: 'denied',
        onboardingStatus: 'not_started',
      }),
    ).toEqual({ kind: 'redirect', href: '/onboarding' });
  });

  it('does not invent completion while onboarding state is loading or failed', () => {
    expect(
      decideAppGate({
        authStatus: 'authenticated',
        currentArea: 'app',
        dogfoodAccess: 'denied',
        onboardingStatus: 'checking',
      }),
    ).toEqual({ kind: 'loading' });
    expect(
      decideAppGate({
        authStatus: 'authenticated',
        currentArea: 'app',
        dogfoodAccess: 'denied',
        onboardingStatus: 'failed',
      }),
    ).toEqual({ kind: 'blocked' });
  });

  it('allows the onboarding routes while onboarding is unfinished', () => {
    expect(
      decideAppGate({
        authStatus: 'authenticated',
        currentArea: 'onboarding',
        dogfoodAccess: 'denied',
        onboardingStatus: 'in_progress',
      }),
    ).toEqual({ kind: 'allow' });
  });

  it('sends a completed signed-in user away from the sign-in route', () => {
    expect(
      decideAppGate({
        authStatus: 'authenticated',
        currentArea: 'sign_in',
        dogfoodAccess: 'denied',
        onboardingStatus: 'completed',
      }),
    ).toEqual({ kind: 'redirect', href: '/' });
  });

  it('covers the app while authoritative onboarding is re-read after apply', () => {
    expect(
      shouldRevalidateOnboarding('onboarding_preview', 'app'),
    ).toBe(true);
    expect(shouldRevalidateOnboarding('app', 'app')).toBe(false);
    expect(shouldRevalidateOnboarding('onboarding', 'onboarding_preview')).toBe(
      false,
    );
  });

  it('allows a completed user to revisit onboarding for an explicit correction', () => {
    expect(
      decideAppGate({
        authStatus: 'authenticated',
        currentArea: 'onboarding',
        dogfoodAccess: 'denied',
        onboardingStatus: 'completed',
      }),
    ).toEqual({ kind: 'allow' });
  });

  it('notifies the gate after setup saves development access and stays inert in production', () => {
    let developmentNotifications = 0;
    let productionNotifications = 0;
    const unsubscribeDevelopment = subscribeDogfoodAccessChanges(true, () => {
      developmentNotifications += 1;
    });
    const unsubscribeProduction = subscribeDogfoodAccessChanges(false, () => {
      productionNotifications += 1;
    });

    notifyDogfoodAccessChanged(false);
    notifyDogfoodAccessChanged(true);
    expect(developmentNotifications).toBe(1);
    expect(productionNotifications).toBe(0);

    unsubscribeDevelopment();
    unsubscribeProduction();
    notifyDogfoodAccessChanged(true);
    expect(developmentNotifications).toBe(1);
  });
});
