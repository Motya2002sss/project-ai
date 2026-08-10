import { describe, expect, it } from 'vitest';

import type { DaySnapshotDto, PlanItemDto, TaskDto } from '../../../api/types';
import { mapDaySnapshot } from '../todayMapper';

function item(
  id: number,
  title: string,
  start: string | null,
  end: string | null,
  status = 'planned',
): PlanItemDto {
  return {
    id,
    task_id: id,
    title,
    item_type: 'task',
    status,
    start_time: start,
    end_time: end,
    unscheduled_reason: null,
  };
}

function task(id: number, title: string, status: 'planned' | 'done'): TaskDto {
  return {
    id,
    title,
    priority: 'medium',
    estimated_minutes: 45,
    target_date: '2026-08-10',
    scheduling_type: 'flexible',
    fixed_start: null,
    fixed_end: null,
    preferred_window: null,
    earliest_start: null,
    latest_end: null,
    deadline: null,
    is_locked: false,
    status,
    routine_id: null,
    occurrence_date: null,
  };
}

function snapshot(overrides: Partial<DaySnapshotDto> = {}): DaySnapshotDto {
  const completed = item(1, 'Завершённое действие', '15:00:00', '15:30:00', 'done');
  const current = item(2, 'Текущее действие', '16:30:00', '18:00:00');
  const upcoming = item(3, 'Следующее действие', '19:30:00', '20:15:00');
  const scheduled = [completed, current, upcoming];
  return {
    date: '2026-08-10',
    focus_text: 'Сначала — Текущее действие.',
    progress: { done: 1, total: 3 },
    scheduled_items: scheduled,
    unscheduled_items: [],
    completed_items: [completed],
    current_item: current,
    completed_count: 1,
    total_count: 3,
    day_context: {
      energy_level: null,
      budget_limit: null,
      work_override_mode: null,
      work_start_time: null,
      work_end_time: null,
    },
    tasks: [
      task(1, completed.title, 'done'),
      task(2, current.title, 'planned'),
      task(3, upcoming.title, 'planned'),
    ],
    goals: [],
    routines: [],
    plan: {
      id: 10,
      date: '2026-08-10',
      summary: null,
      focus_text: 'Сначала — Текущее действие.',
      energy_level: null,
      budget_limit: null,
      status: 'active',
      version: 4,
      items: scheduled,
    },
    plan_version: 4,
    ...overrides,
  };
}

describe('mapDaySnapshot', () => {
  it('preserves authoritative order and maps server-owned row states', () => {
    const model = mapDaySnapshot(snapshot());

    expect(model.state).toBe('normal');
    expect(model.dateLabel).toBe('Понедельник · 10 августа');
    expect(model.dayRange).toBe('15:00 — 20:15');
    expect(model.rows.map((row) => row.title)).toEqual([
      'Завершённое действие',
      'Текущее действие',
      'Следующее действие',
    ]);
    expect(model.rows.map((row) => row.variant)).toEqual([
      'completed',
      'current',
      'upcoming',
    ]);
    expect(model.rows[1]?.label).toBe('Сейчас · до 18:00');
  });

  it('maps unscheduled items without inventing a time or placement', () => {
    const unscheduled = {
      ...item(4, 'Нужно уточнить время', null, null),
      unscheduled_reason: 'no_available_slot',
    };
    const model = mapDaySnapshot(
      snapshot({ unscheduled_items: [unscheduled], total_count: 4 }),
    );

    expect(model.unscheduled).toEqual([
      expect.objectContaining({
        title: 'Нужно уточнить время',
        time: null,
        meta: 'Нет подходящего свободного окна',
      }),
    ]);
  });

  it('never exposes an unknown backend reason as user-facing copy', () => {
    const unscheduled = {
      ...item(4, 'Нужно уточнить время', null, null),
      unscheduled_reason: 'capacity',
    };
    const model = mapDaySnapshot(
      snapshot({ unscheduled_items: [unscheduled], total_count: 4 }),
    );

    expect(model.unscheduled[0]?.meta).toBe('Нужно уточнить планирование');
  });

  it('turns canonical unscheduled reason codes into user-facing copy', () => {
    const unscheduled = {
      ...item(4, 'Записать БЖУ', null, null),
      unscheduled_reason: 'missing_duration',
    };
    const model = mapDaySnapshot(
      snapshot({ unscheduled_items: [unscheduled], total_count: 4 }),
    );

    expect(model.unscheduled[0]?.meta).toBe('Не указана длительность');
  });

  it('labels an unscheduled completed item without exposing its reason code', () => {
    const completed = {
      ...item(4, 'Записать БЖУ', null, null, 'done'),
      unscheduled_reason: 'completed_without_time',
    };
    const model = mapDaySnapshot(
      snapshot({
        scheduled_items: [],
        unscheduled_items: [completed],
        completed_items: [completed],
        current_item: null,
        completed_count: 1,
        total_count: 1,
      }),
    );

    expect(model.unscheduled[0]?.meta).toBe('Выполнено без времени');
  });

  it('reports all done while retaining completed temporal rows', () => {
    const completed = item(1, 'Последнее действие', '20:00:00', '20:30:00', 'done');
    const model = mapDaySnapshot(
      snapshot({
        scheduled_items: [completed],
        completed_items: [completed],
        current_item: null,
        completed_count: 1,
        total_count: 1,
        progress: { done: 1, total: 1 },
      }),
    );

    expect(model.state).toBe('allDone');
    expect(model.rows).toEqual([
      expect.objectContaining({ title: 'Последнее действие', variant: 'completed' }),
    ]);
  });

  it('reports an honest empty day without fake tasks', () => {
    const model = mapDaySnapshot(
      snapshot({
        scheduled_items: [],
        unscheduled_items: [],
        completed_items: [],
        current_item: null,
        completed_count: 0,
        total_count: 0,
        progress: { done: 0, total: 0 },
        tasks: [],
      }),
    );

    expect(model.state).toBe('empty');
    expect(model.rows).toEqual([]);
  });

  it('uses a pending completion only as a temporary visual override', () => {
    const source = snapshot();
    const model = mapDaySnapshot(source, { 2: 'done' });

    expect(model.rows[1]?.variant).toBe('completed');
    expect(source.scheduled_items[1]?.status).toBe('planned');
  });
});
