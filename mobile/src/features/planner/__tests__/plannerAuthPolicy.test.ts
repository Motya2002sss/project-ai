import { describe, expect, it } from 'vitest';

import { resolveDogfoodRuntimeEnabled } from '../../../config/environment';
import {
  isPlannerIdentityResolving,
  resolvePlannerAccess,
} from '../plannerAuthPolicy';

describe('planner auth policy', () => {
  it('does not load a cache or Today before cold-start refresh has a user scope', () => {
    expect(isPlannerIdentityResolving('hydrating', false)).toBe(true);
    expect(isPlannerIdentityResolving('refreshing', false)).toBe(true);
  });

  it('retains the known user scope during an in-app token rotation', () => {
    expect(isPlannerIdentityResolving('refreshing', true)).toBe(false);
    expect(isPlannerIdentityResolving('authenticated', true)).toBe(false);
    expect(isPlannerIdentityResolving('revoked', false)).toBe(false);
  });

  it('locks Planner until it has an authenticated owner or an explicit dogfood token', () => {
    expect(
      resolvePlannerAccess('hydrating', null, true, true),
    ).toEqual({ kind: 'locked', scope: null });
    expect(
      resolvePlannerAccess('unauthenticated', null, true, false),
    ).toEqual({ kind: 'locked', scope: null });
    expect(
      resolvePlannerAccess('unauthenticated', null, true, true),
    ).toEqual({ kind: 'dogfood', scope: 'dogfood' });
    expect(
      resolvePlannerAccess('expired', 'public-user', false, false),
    ).toEqual({ kind: 'production', scope: 'public-user' });
    expect(
      resolvePlannerAccess('unauthenticated', null, false, true),
    ).toEqual({ kind: 'locked', scope: null });
  });

  it('enables dogfood only with an explicit development build flag', () => {
    expect(resolveDogfoodRuntimeEnabled('development', 'true')).toBe(true);
    expect(resolveDogfoodRuntimeEnabled('development', undefined)).toBe(false);
    expect(resolveDogfoodRuntimeEnabled('development', 'TRUE')).toBe(false);
    expect(resolveDogfoodRuntimeEnabled(undefined, 'true')).toBe(false);
    expect(resolveDogfoodRuntimeEnabled('test', 'true')).toBe(false);
    expect(resolveDogfoodRuntimeEnabled('production', 'true')).toBe(false);
  });
});
