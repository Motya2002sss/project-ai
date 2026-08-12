import type {
  CalendarDayDto,
  CalendarMonthDto,
  CalendarWeekDto,
} from '../calendarTypes';

export const calendarDayFixture: CalendarDayDto = {
  date: '2026-08-12',
  timezone: 'Europe/Moscow',
  materialized: true,
  plan_version: 4,
  summary: 'Сохранить спокойный темп',
  items: [
    {
      item_id: 1,
      task_id: 10,
      title: 'Очень длинная русская строка для проверки переноса без обрезания смысла',
      kind: 'task',
      status: 'planned',
      start_at: '2026-08-12T07:00:00Z',
      end_at: '2026-08-12T08:00:00Z',
      unscheduled_reason: null,
    },
    {
      item_id: 2,
      task_id: null,
      title: 'Восстановление',
      kind: 'recovery',
      status: 'planned',
      start_at: '2026-08-12T09:00:00Z',
      end_at: '2026-08-12T09:30:00Z',
      unscheduled_reason: null,
    },
  ],
  busy_intervals: [
    { start_at: '2026-08-12T08:00:00Z', end_at: '2026-08-12T09:00:00Z' },
  ],
  free_intervals: [
    { start_at: '2026-08-12T09:30:00Z', end_at: '2026-08-12T20:00:00Z' },
  ],
  cursor: 'day-cursor',
};

export const calendarWeekFixture: CalendarWeekDto = {
  start: '2026-08-10',
  end: '2026-08-16',
  timezone: 'Europe/Moscow',
  days: Array.from({ length: 7 }, (_, index) => ({
    date: `2026-08-${String(10 + index).padStart(2, '0')}`,
    materialized: index === 2,
    plan_version: index === 2 ? 4 : null,
    scheduled_count: index === 2 ? 2 : 0,
    unscheduled_count: 0,
    completed_count: 0,
    items: index === 2 ? calendarDayFixture.items : [],
  })),
  commitment_load: [
    {
      commitment_id: 'commitment-1',
      title: 'Практика архитектуры',
      target_minutes: 120,
      target_sessions: 2,
      scheduled_minutes: 60,
      scheduled_sessions: 1,
      completed_minutes: 30,
      completed_sessions: 1,
      remaining_minutes: 60,
    },
  ],
  cursor: 'week-cursor',
};

export const calendarMonthFixture: CalendarMonthDto = {
  month: '2026-08-01',
  timezone: 'Europe/Moscow',
  milestones: [
    {
      milestone_id: 'milestone-1',
      goal_id: 'goal-1',
      title: 'Пробный экзамен пройден',
      occurred_at: '2026-08-20T09:00:00Z',
      status: 'completed',
    },
  ],
  deadlines: [{ goal_id: 'goal-1', title: 'Сдать экзамен', date: '2026-08-28' }],
  life_modes: [
    {
      mode_id: 'mode-1',
      mode: 'travel',
      starts_at: '2026-08-22T03:00:00Z',
      ends_at: '2026-08-25T17:00:00Z',
    },
  ],
  measurements: [
    {
      goal_id: 'goal-1',
      occurred_at: '2026-08-18T04:00:00Z',
      value: '72.5000',
      unit: 'kg',
    },
  ],
  tension: {
    materialized_days: 8,
    scheduled_minutes: 840,
    unscheduled_items: 1,
    busy_minutes: 620,
  },
  cursor: 'month-cursor',
};
