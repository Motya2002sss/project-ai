import { describe, expect, it } from 'vitest';

import {
  buildGoalDetailsModel,
  buildPathScreenModel,
  mergeEvidence,
} from '../pathModel';
import { firstGoal, pathResponse } from './pathFixtures';

describe('authoritative Path model', () => {
  it('keeps server order, caps the screen at three goals, and never invents a percentage', () => {
    const responseWithIrrelevantTasks = {
      ...pathResponse,
      tasks: [{ status: 'done' }, { status: 'done' }],
    };

    const model = buildPathScreenModel({
      response: responseWithIrrelevantTasks,
      status: 'ready',
      source: 'network',
    });

    expect(model.state).toBe('ready');
    if (model.state !== 'ready') throw new Error('expected ready');
    expect(model.goals.map((goal) => goal.id)).toEqual([
      '44cf1138-6258-4b5f-b96f-8514bcbb7ed5',
      '44cf1138-6258-4b5f-b96f-8514bcbb7ed2',
      '44cf1138-6258-4b5f-b96f-8514bcbb7ed3',
    ]);
    expect(model.goals[0]?.percentage).toBeNull();
    expect(model.goals[0]?.progressLabel).toBe('Недостаточно данных');
    expect(model.goals[0]?.progressExplanation).toBe(
      'Процент появится после накопления данных для проверяемой формулы.',
    );
  });

  it('maps the complete Goal → milestone → phase → next step → evidence sequence and long copy', () => {
    const model = buildPathScreenModel({
      response: { goals: [firstGoal] },
      status: 'ready',
      source: 'network',
    });

    if (model.state !== 'ready') throw new Error('expected ready');
    expect(model.goals[0]).toMatchObject({
      title:
        'Подготовиться к первому полумарафону спокойно, без перегрузки и с устойчивым недельным ритмом',
      percentage: null,
      milestones: [
        {
          title: 'Бегать три раза в неделю без резкого увеличения нагрузки',
          status: 'active',
        },
      ],
      currentPhase: { title: 'Основа', programName: 'Базовый цикл' },
      nextStep: { title: 'Лёгкий бег', detail: '3 раза · 120 минут в неделю' },
      recentEvidence: [
        { id: '6840cf59-a92b-49f7-9121-bb539c611c90', value: '30 minutes' },
      ],
    });
    expect(model.goals[0]?.accessibilityLabel).toContain(
      'Недостаточно данных',
    );
    expect(model.goals[0]?.accessibilityLabel).toContain('Лёгкий бег');
  });

  it('presents the persisted server percentage without recomputing it', () => {
    const model = buildPathScreenModel({
      response: {
        goals: [
          {
            ...firstGoal,
            progress: {
              ...firstGoal.progress,
              percentage: '50.0000',
              reason: null,
              confidence: 'medium',
            },
            formula: {
              strategy: 'consistency',
              label: 'Регулярность',
              explanation:
                'Фактические минуты относительно запланированных минут.',
            },
          },
        ],
      },
      status: 'ready',
      source: 'network',
    });

    if (model.state !== 'ready') throw new Error('expected ready');
    expect(model.goals[0]?.percentage).toBe(50);
    expect(model.goals[0]?.progressLabel).toBe('50%');
    expect(model.goals[0]?.progressExplanation).toBe(
      'Фактические минуты относительно запланированных минут.',
    );
  });

  it('renders loading, empty, hard error, and cached-offline states truthfully', () => {
    expect(
      buildPathScreenModel({ response: null, status: 'loading', source: null }),
    ).toEqual({ state: 'loading' });
    expect(
      buildPathScreenModel({
        response: { goals: [] },
        status: 'ready',
        source: 'network',
      }),
    ).toEqual({ state: 'empty', cached: false, notice: null });
    expect(
      buildPathScreenModel({
        response: null,
        status: 'error',
        source: null,
        errorMessage: 'Не удалось загрузить путь.',
      }),
    ).toEqual({ state: 'error', message: 'Не удалось загрузить путь.' });

    const cached = buildPathScreenModel({
      response: { goals: [firstGoal] },
      status: 'error',
      source: 'cache',
      errorMessage: 'Нет соединения.',
    });
    expect(cached.state).toBe('ready');
    if (cached.state !== 'ready') throw new Error('expected ready');
    expect(cached.cached).toBe(true);
    expect(cached.notice).toBe(
      'Сохранено на устройстве · не удалось обновить',
    );

    const staleNetwork = buildPathScreenModel({
      response: { goals: [firstGoal] },
      status: 'error',
      source: 'network',
      errorMessage: 'Нет соединения.',
    });
    expect(staleNetwork.state).toBe('ready');
    if (staleNetwork.state !== 'ready') throw new Error('expected ready');
    expect(staleNetwork.notice).toBe(
      'Не удалось обновить · показаны последние данные',
    );
  });
});

describe('Goal Details model', () => {
  it('exposes authoritative fields and paginated evidence without fake actions', () => {
    const model = buildGoalDetailsModel(firstGoal, firstGoal.recent_evidence, {
      cached: false,
      hasMoreEvidence: true,
    });

    expect(model).toMatchObject({
      id: firstGoal.goal.public_id,
      statusLabel: 'Активна',
      outcomeLabel: 'Регулярность',
      deadline: '2026-11-01',
      allocation: '180 минут в неделю',
      evidence: [{ value: '30 minutes' }],
      hasMoreEvidence: true,
      cached: false,
    });
    expect(model.actions).toEqual([]);
  });

  it('appends cursor pages in server order and removes overlap by evidence id', () => {
    expect(
      mergeEvidence(firstGoal.recent_evidence, [
        firstGoal.recent_evidence[0]!,
        {
          ...firstGoal.recent_evidence[0]!,
          id: '6840cf59-a92b-49f7-9121-bb539c611c91',
          occurred_at: '2026-08-10T18:30:00Z',
        },
      ]).map((item) => item.id),
    ).toEqual([
      '6840cf59-a92b-49f7-9121-bb539c611c90',
      '6840cf59-a92b-49f7-9121-bb539c611c91',
    ]);
  });
});
