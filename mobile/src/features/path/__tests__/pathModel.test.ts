import { describe, expect, it } from 'vitest';

import type { GoalDto } from '../../../api/types';
import { buildPathModel } from '../pathModel';

const goals: GoalDto[] = [
  {
    id: 2,
    title: 'Набрать 6 кг',
    category: 'health',
    priority: 'medium',
    status: 'active',
  },
  {
    id: 3,
    title: 'Архивная цель',
    category: 'other',
    priority: 'low',
    status: 'completed',
  },
];

describe('buildPathModel', () => {
  it('keeps authoritative active goals in server order without fake progress', () => {
    expect(buildPathModel(goals)).toEqual({
      state: 'ready',
      goals: [{ id: 2, title: 'Набрать 6 кг' }],
    });
  });

  it('returns an honest empty state when there are no active goals', () => {
    expect(buildPathModel([])).toEqual({ state: 'empty', goals: [] });
    expect(buildPathModel([goals[1]!])).toEqual({
      state: 'empty',
      goals: [],
    });
  });
});
