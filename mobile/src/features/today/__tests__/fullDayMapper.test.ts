import { describe, expect, it } from 'vitest';

import type {
  DaySnapshotDto,
  GoalDto,
  PlanItemDto,
  TaskDto,
} from '../../../api/types';
import { mapDaySnapshot } from '../todayMapper';

function planItem(
  id: number,
  title: string,
  itemType: string,
  start: string,
  end: string,
  taskId: number | null = null,
): PlanItemDto {
  return {
    id,
    task_id: taskId,
    title,
    item_type: itemType,
    status: 'planned',
    start_time: start,
    end_time: end,
    unscheduled_reason: null,
  };
}

function task(
  id: number,
  title: string,
  goalId: number | null,
): TaskDto & { goal_id: number | null } {
  return {
    id,
    goal_id: goalId,
    title,
    priority: 'medium',
    estimated_minutes: 45,
    target_date: '2026-08-11',
    scheduling_type: 'flexible',
    fixed_start: null,
    fixed_end: null,
    preferred_window: null,
    earliest_start: null,
    latest_end: null,
    deadline: null,
    is_locked: false,
    status: 'planned',
    routine_id: null,
    occurrence_date: null,
  };
}

const goals: GoalDto[] = [
  {
    id: 10,
    title: 'Набрать вес до 78 кг без резких ограничений',
    category: 'body',
    priority: 'high',
    status: 'active',
  },
  {
    id: 11,
    title: 'Стать senior backend-разработчиком',
    category: 'career',
    priority: 'medium',
    status: 'active',
  },
  {
    id: 12,
    title: 'Прочитать 24 содержательные книги за год',
    category: 'mind',
    priority: 'low',
    status: 'active',
  },
  {
    id: 13,
    title: 'Четвёртая цель не должна перегружать Today',
    category: 'personal',
    priority: 'low',
    status: 'active',
  },
];

function fullDaySnapshot(): DaySnapshotDto {
  const items = [
    planItem(1, 'Подъём', 'wake', '07:30:00', '07:40:00'),
    planItem(2, 'Завтрак', 'meal', '08:00:00', '08:25:00'),
    planItem(3, 'Дорога в офис', 'commute', '08:40:00', '09:40:00'),
    planItem(4, 'Работа', 'work', '10:00:00', '18:00:00'),
    planItem(5, 'Силовая тренировка', 'workout', '19:30:00', '20:30:00', 5),
    planItem(
      6,
      'Разобрать проектирование распределённых систем и сделать подробный конспект',
      'learning',
      '21:00:00',
      '22:00:00',
      6,
    ),
    planItem(7, 'Свободное время', 'free_time', '22:00:00', '23:20:00'),
    planItem(8, 'Сон', 'sleep', '23:45:00', '23:59:00'),
  ];
  return {
    date: '2026-08-11',
    as_of: '2026-08-11T19:45:00+03:00',
    focus_text: 'Спокойно пройти полный день без перегруза.',
    progress: { done: 1, total: 2 },
    week_progress: { done: 3, total: 7 },
    scheduled_items: items,
    unscheduled_items: [],
    completed_items: [],
    current_item: items[4]!,
    completed_count: 1,
    total_count: 2,
    day_context: {
      energy_level: 'normal',
      budget_limit: null,
      work_override_mode: null,
      work_start_time: '10:00:00',
      work_end_time: '18:00:00',
    },
    tasks: [
      task(5, items[4]!.title, 10),
      task(6, items[5]!.title, 11),
    ],
    goals,
    routines: [],
    plan: {
      id: 1,
      date: '2026-08-11',
      summary: 'Рабочий день, тренировка и обучение',
      focus_text: 'Спокойно пройти полный день без перегруза.',
      energy_level: 'normal',
      budget_limit: null,
      status: 'active',
      version: 8,
      items,
    },
    plan_version: 8,
  };
}

describe('full-day Today model', () => {
  it('renders every authoritative block in order without inventing micro-actions', () => {
    const source = fullDaySnapshot();
    const model = mapDaySnapshot(source);

    expect(model.rows.map((row) => row.title)).toEqual(
      source.scheduled_items.map((item) => item.title),
    );
    expect(model.rows.map((row) => row.kind)).toEqual([
      'anchor',
      'meal',
      'commute',
      'fixed',
      'action',
      'action',
      'free',
      'sleep',
    ]);
    expect(model.rows).toHaveLength(8);
  });

  it('uses the authoritative current item to dim earlier planned blocks', () => {
    const model = mapDaySnapshot(fullDaySnapshot());

    expect(model.rows.map((row) => row.variant)).toEqual([
      'past',
      'past',
      'past',
      'past',
      'current',
      'upcoming',
      'upcoming',
      'upcoming',
    ]);
    expect(model.rows[4]?.label).toBe('Сейчас · до 20:30');
  });

  it('shows factual goal context and keeps long Russian copy intact', () => {
    const source = fullDaySnapshot();
    const model = mapDaySnapshot(source);

    expect(model.rows[4]?.goalContext).toBe(
      'Тело · Набрать вес до 78 кг без резких ограничений',
    );
    expect(model.rows[5]?.goalContext).toBe(
      'Карьера · Стать senior backend-разработчиком',
    );
    expect(model.rows[5]?.title).toBe(source.scheduled_items[5]?.title);
    expect(model.directionTitles).toEqual(goals.slice(0, 3).map((goal) => goal.title));
  });

  it('derives only presentation progress from authoritative counters', () => {
    const model = mapDaySnapshot(fullDaySnapshot());

    expect(model.progressLabel).toBe('Сегодня 1 из 2');
    expect(model.progressFraction).toBe(0.5);
    expect(model.weekProgressLabel).toBe('Неделя 3 из 7');
  });

  it('reflects an optimistic checkbox only until the authoritative snapshot arrives', () => {
    const source = fullDaySnapshot();
    const optimistic = mapDaySnapshot(source, { 5: 'done' });
    const rolledBack = mapDaySnapshot(source);

    expect(optimistic.progressLabel).toBe('Сегодня 2 из 2');
    expect(optimistic.progressFraction).toBe(1);
    expect(optimistic.weekProgressLabel).toBe('Неделя 4 из 7');
    expect(rolledBack.progressLabel).toBe('Сегодня 1 из 2');
    expect(rolledBack.weekProgressLabel).toBe('Неделя 3 из 7');
    expect(source.completed_count).toBe(1);
  });

  it('keeps zero-task progress finite and honest', () => {
    const source = fullDaySnapshot();
    const model = mapDaySnapshot({
      ...source,
      progress: { done: 0, total: 0 },
      completed_count: 0,
      total_count: 0,
    });

    expect(model.progressLabel).toBe('Сегодня без задач');
    expect(model.progressFraction).toBe(0);
  });
});
