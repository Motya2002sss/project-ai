import type { GoalDto } from '../../api/types';

export interface PathGoalModel {
  id: number;
  title: string;
}

export interface PathModel {
  state: 'empty' | 'ready';
  goals: PathGoalModel[];
}

export function buildPathModel(goals: GoalDto[]): PathModel {
  const activeGoals = goals
    .filter((goal) => goal.status === 'active')
    .map(({ id, title }) => ({ id, title }));

  return {
    state: activeGoals.length > 0 ? 'ready' : 'empty',
    goals: activeGoals,
  };
}
