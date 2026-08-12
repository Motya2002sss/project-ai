import type {
  GoalPathDto,
  PathResponseDto,
} from '../pathTypes';

export const firstGoal: GoalPathDto = {
  goal: {
    public_id: '44cf1138-6258-4b5f-b96f-8514bcbb7ed5',
    title:
      'Подготовиться к первому полумарафону спокойно, без перегрузки и с устойчивым недельным ритмом',
    life_area: 'body',
    outcome_type: 'consistency',
    baseline_value: null,
    current_value: null,
    target_value: null,
    metric_unit: null,
    deadline: '2026-11-01',
    intensity: 'comfortable',
    allocation_minutes_week: 180,
    status: 'active',
    version: 2,
  },
  progress: {
    strategy: 'consistency',
    percentage: null,
    components: {},
    reason: 'not_calculated',
    formula_version: 'progress-v1',
    forecast_date: null,
    confidence: 'low',
  },
  formula: {
    strategy: 'consistency',
    label: 'Недостаточно данных',
    explanation:
      'Процент появится после накопления данных для проверяемой формулы.',
  },
  milestones: [
    {
      id: 'a06f1e60-e47a-4a9e-8325-a9ce54db24b0',
      title: 'Бегать три раза в неделю без резкого увеличения нагрузки',
      description:
        'Сохранять комфортный темп и учитывать восстановление между тренировками.',
      position: 1,
      weight: null,
      status: 'active',
      completed_at: null,
    },
  ],
  current_program: {
    id: 'f6889c40-a14e-4f73-a26c-cfa48f7609b4',
    name: 'Базовый цикл',
    status: 'active',
    minimum_minutes_week: 90,
    comfortable_minutes_week: 180,
    maximum_minutes_week: 240,
    version: 1,
  },
  current_phase: {
    id: '28c2f6e1-ae78-4197-aef1-5fb0c3156da2',
    title: 'Основа',
    position: 1,
    status: 'active',
    start_date: '2026-08-01',
    end_date: '2026-09-01',
  },
  next_step: {
    commitment_id: '28d09d72-c3d8-4188-8078-fc7800b89599',
    title: 'Лёгкий бег',
    target_minutes_week: 120,
    target_sessions_week: 3,
    minimum_block_minutes: 30,
    allowed_weekdays: [1, 3, 5],
    preferred_window: 'evening',
  },
  recent_evidence: [
    {
      id: '6840cf59-a92b-49f7-9121-bb539c611c90',
      evidence_type: 'partial',
      quantity: '30.0000',
      unit: 'minutes',
      occurred_at: '2026-08-11T18:30:00Z',
    },
  ],
};

function goalAt(index: number): GoalPathDto {
  return {
    ...firstGoal,
    goal: {
      ...firstGoal.goal,
      public_id: `44cf1138-6258-4b5f-b96f-8514bcbb7ed${index}`,
      title: `Цель ${index}`,
    },
    milestones: [],
    current_phase: null,
    next_step: null,
    recent_evidence: [],
  };
}

export const pathResponse: PathResponseDto = {
  goals: [firstGoal, goalAt(2), goalAt(3), goalAt(4)],
};
