import { describe, expect, it } from 'vitest';

import type { DaySnapshotDto, PlanDiffDto } from '../../../api/types';
import { mapPlanDiff } from '../planDiffMapper';

const snapshot = {
  date: '2026-08-10',
  focus_text: 'Сначала — Зал.',
  progress: { done: 0, total: 1 },
  scheduled_items: [],
  unscheduled_items: [],
  completed_items: [],
  current_item: null,
  completed_count: 0,
  total_count: 1,
  day_context: {
    energy_level: null,
    budget_limit: null,
    work_override_mode: null,
    work_start_time: null,
    work_end_time: null,
  },
  tasks: [
    {
      id: 7,
      title: 'Купить продукты',
      priority: 'medium',
      estimated_minutes: 30,
      target_date: '2026-08-10',
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
    },
  ],
  goals: [],
  routines: [],
  plan: {
    id: 1,
    date: '2026-08-10',
    summary: null,
    focus_text: 'Сначала — Зал.',
    energy_level: null,
    budget_limit: null,
    status: 'active',
    version: 2,
    items: [],
  },
  plan_version: 2,
} satisfies DaySnapshotDto;

describe('mapPlanDiff', () => {
  it('renders only factual structured changes returned by the backend', () => {
    const diff: PlanDiffDto = {
      availability_change: 'Работа → до 20:00',
      moved_plan_items: [
        {
          task_id: 9,
          title: 'Зал',
          old_start: '18:30:00',
          new_start: '20:30:00',
        },
      ],
      created_task_ids: [7],
    };

    expect(mapPlanDiff(diff, snapshot)).toEqual([
      { title: 'Работа → до 20:00', detail: null },
      { title: 'Зал', detail: '18:30 → 20:30' },
      { title: 'Добавлено', detail: 'Купить продукты' },
    ]);
  });

  it('does not invent a diff when structured fields are empty', () => {
    expect(mapPlanDiff({}, snapshot)).toEqual([]);
  });

  it('summarizes structured task ids that belong to another day', () => {
    expect(mapPlanDiff({ created_task_ids: [99] }, snapshot)).toEqual([
      { title: 'Добавлено', detail: '1 задача' },
    ]);
  });

  it('maps task and routine id lists only when the snapshot supplies titles', () => {
    const taskTemplate = snapshot.tasks[0]!;
    const richSnapshot: DaySnapshotDto = {
      ...snapshot,
      tasks: [
        taskTemplate,
        { ...taskTemplate, id: 8, title: 'Закончить отчёт', status: 'done' },
        { ...taskTemplate, id: 9, title: 'Старый созвон', status: 'cancelled' },
        { ...taskTemplate, id: 10, title: 'Позвонить врачу' },
      ],
      routines: [
        {
          id: 11,
          title: 'Вечерняя растяжка',
          cadence: 'daily',
          weekdays: [],
          fixed_time: null,
          preferred_window: 'evening',
          estimated_minutes: 12,
          start_date: '2026-08-10',
          end_date: null,
          active: true,
        },
      ],
    };

    expect(
      mapPlanDiff(
        {
          updated_task_ids: [7],
          completed_task_ids: [8],
          cancelled_task_ids: [9],
          unscheduled_task_ids: [10, 999],
          created_routine_ids: [11],
        },
        richSnapshot,
      ),
    ).toEqual([
      { title: 'Обновлено', detail: 'Купить продукты' },
      { title: 'Выполнено', detail: 'Закончить отчёт' },
      { title: 'Отменено', detail: 'Старый созвон' },
      { title: 'Без времени', detail: 'Позвонить врачу' },
      { title: 'Без времени', detail: '1 задача' },
      { title: 'Добавлено в распорядок', detail: 'Вечерняя растяжка' },
    ]);
  });
});
