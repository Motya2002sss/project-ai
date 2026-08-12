import { describe, expect, it } from 'vitest';

import {
  goalDetailsDataReducer,
  initialGoalDetailsDataState,
  initialPathDataState,
  goalDetailsStateForScope,
  pathDataStateForScope,
  pathDataReducer,
  resolvePathCacheScope,
} from '../pathDataState';
import { firstGoal, pathResponse } from './pathFixtures';

describe('Path screen data state', () => {
  it('never trusts a stale AsyncStorage scope without a bound auth identity', () => {
    expect(resolvePathCacheScope('hydrating', null, 'stored-user')).toBeNull();
    expect(resolvePathCacheScope('expired', null, 'stored-user')).toBeNull();
    expect(
      resolvePathCacheScope('authenticated', 'fresh-user', 'stored-user'),
    ).toBe('fresh-user');
    expect(resolvePathCacheScope('unauthenticated', null, 'stored-user')).toBeNull();
    expect(resolvePathCacheScope('revoked', null, 'stored-user')).toBeNull();
  });

  it('keeps a user-scoped cached response visible when refresh fails', () => {
    const cached = pathDataReducer(initialPathDataState, {
      type: 'cache/loaded',
      response: pathResponse,
    });
    const failed = pathDataReducer(cached, {
      type: 'refresh/failed',
      message: 'Нет соединения.',
    });

    expect(failed).toEqual({
      scope: null,
      response: pathResponse,
      status: 'error',
      source: 'cache',
      errorMessage: 'Нет соединения.',
    });
  });

  it('replaces cached data with the fresh authoritative response', () => {
    const cached = pathDataReducer(initialPathDataState, {
      type: 'cache/loaded',
      response: pathResponse,
    });
    const freshResponse = { goals: [firstGoal] };

    expect(
      pathDataReducer(cached, {
        type: 'refresh/succeeded',
        response: freshResponse,
      }),
    ).toEqual({
      scope: null,
      response: freshResponse,
      status: 'ready',
      source: 'network',
      errorMessage: null,
    });
  });

  it('drops the previous user response when the production identity changes', () => {
    const ready = pathDataReducer(initialPathDataState, {
      type: 'refresh/succeeded',
      response: pathResponse,
    });

    expect(
      pathDataReducer(ready, { type: 'scope/changed', scope: 'user-b' }),
    ).toEqual({ ...initialPathDataState, scope: 'user-b' });
  });

  it('projects an empty state synchronously before a different user effect runs', () => {
    const userA = pathDataReducer(
      pathDataReducer(initialPathDataState, {
        type: 'scope/changed',
        scope: 'user-a',
      }),
      { type: 'refresh/succeeded', response: pathResponse },
    );

    expect(pathDataStateForScope(userA, 'user-b')).toEqual({
      ...initialPathDataState,
      scope: 'user-b',
    });
  });
});

describe('Goal Details data state', () => {
  it('keeps cached goal and recent evidence available after an offline failure', () => {
    const cached = goalDetailsDataReducer(initialGoalDetailsDataState, {
      type: 'cache/loaded',
      detail: firstGoal,
    });
    const failed = goalDetailsDataReducer(cached, {
      type: 'detail/failed',
      message: 'Нет соединения.',
    });

    expect(failed.detail).toBe(firstGoal);
    expect(failed.source).toBe('cache');
    expect(failed.status).toBe('error');
    expect(failed.evidence).toEqual(firstGoal.recent_evidence);
  });

  it('removes cached goal data when the authoritative server says it is unavailable', () => {
    const cached = goalDetailsDataReducer(initialGoalDetailsDataState, {
      type: 'cache/loaded',
      detail: firstGoal,
    });

    expect(
      goalDetailsDataReducer(cached, {
        type: 'detail/unavailable',
        message: 'Цель больше недоступна.',
      }),
    ).toEqual({
      ...initialGoalDetailsDataState,
      status: 'error',
      errorMessage: 'Цель больше недоступна.',
    });
  });

  it('replaces recent evidence with the first page, then appends a cursor page without duplicates', () => {
    const detailReady = goalDetailsDataReducer(initialGoalDetailsDataState, {
      type: 'detail/succeeded',
      detail: firstGoal,
    });
    const firstPage = goalDetailsDataReducer(detailReady, {
      type: 'evidence/succeeded',
      mode: 'replace',
      items: firstGoal.recent_evidence,
      nextCursor: 'cursor-2',
    });
    const nextEvidence = {
      ...firstGoal.recent_evidence[0]!,
      id: '6840cf59-a92b-49f7-9121-bb539c611c91',
    };
    const nextPage = goalDetailsDataReducer(firstPage, {
      type: 'evidence/succeeded',
      mode: 'append',
      items: [firstGoal.recent_evidence[0]!, nextEvidence],
      nextCursor: null,
    });

    expect(nextPage.evidence.map((item) => item.id)).toEqual([
      '6840cf59-a92b-49f7-9121-bb539c611c90',
      '6840cf59-a92b-49f7-9121-bb539c611c91',
    ]);
    expect(nextPage.nextCursor).toBeNull();
    expect(nextPage.evidenceStatus).toBe('ready');
  });

  it('drops cached goal details when the production identity changes', () => {
    const cached = goalDetailsDataReducer(initialGoalDetailsDataState, {
      type: 'cache/loaded',
      detail: firstGoal,
    });

    expect(
      goalDetailsDataReducer(cached, {
        type: 'scope/changed',
        scope: 'user-b',
      }),
    ).toEqual({ ...initialGoalDetailsDataState, scope: 'user-b' });
  });

  it('never commits the previous account goal for a new scope frame', () => {
    const userA = goalDetailsDataReducer(
      goalDetailsDataReducer(initialGoalDetailsDataState, {
        type: 'scope/changed',
        scope: 'user-a',
      }),
      { type: 'cache/loaded', detail: firstGoal },
    );

    expect(goalDetailsStateForScope(userA, 'user-b')).toEqual({
      ...initialGoalDetailsDataState,
      scope: 'user-b',
    });
  });
});
