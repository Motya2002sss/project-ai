import { describe, expect, it } from 'vitest';

import {
  isEvidencePageDto,
  isGoalPathDto,
  isPathResponseDto,
  PathApi,
  type PathJsonRequester,
} from '../pathApi';
import { firstGoal, pathResponse } from '../../features/path/__tests__/pathFixtures';

describe('PathApi production v2 boundary', () => {
  it('uses only authenticated read routes and safely encodes ids and cursors', async () => {
    const calls: [string, RequestInit | undefined][] = [];
    const client: PathJsonRequester = {
      async request<T>(
        path: string,
        init?: RequestInit,
        validator?: (value: unknown) => value is T,
      ): Promise<T> {
        calls.push([path, init]);
        const payload: unknown =
          path === '/api/v2/path'
            ? pathResponse
            : path.includes('/evidence')
              ? { items: [], next_cursor: null }
              : firstGoal;
        if (!validator?.(payload)) throw new Error('missing runtime validator');
        return payload;
      },
    };
    const api = new PathApi(client);

    await api.getPath();
    await api.getGoal('goal/unsafe');
    await api.getEvidence('goal/unsafe', {
      limit: 20,
      cursor: 'opaque+/=',
    });

    expect(calls).toEqual([
      ['/api/v2/path', undefined],
      ['/api/v2/goals/goal%2Funsafe', undefined],
      [
        '/api/v2/goals/goal%2Funsafe/evidence?limit=20&cursor=opaque%2B%2F%3D',
        undefined,
      ],
    ]);
  });

  it('accepts the complete backend contract and rejects malformed progress or cursor pages', () => {
    expect(isPathResponseDto(pathResponse)).toBe(true);
    expect(isGoalPathDto(firstGoal)).toBe(true);
    expect(
      isPathResponseDto({
        goals: [
          {
            ...firstGoal,
            progress: { ...firstGoal.progress, percentage: '101.0000' },
          },
        ],
      }),
    ).toBe(false);
    expect(
      isEvidencePageDto({
        items: firstGoal.recent_evidence,
        next_cursor: null,
      }),
    ).toBe(true);
    expect(
      isEvidencePageDto({ items: firstGoal.recent_evidence, next_cursor: 12 }),
    ).toBe(false);
  });

  it('rejects evidence limits outside the backend 1…50 contract', async () => {
    const api = new PathApi({
      request: async <T>() => ({ items: [], next_cursor: null }) as T,
    });

    await expect(api.getEvidence(firstGoal.goal.public_id, { limit: 0 })).rejects.toThrow(
      RangeError,
    );
    await expect(api.getEvidence(firstGoal.goal.public_id, { limit: 51 })).rejects.toThrow(
      RangeError,
    );
  });
});
