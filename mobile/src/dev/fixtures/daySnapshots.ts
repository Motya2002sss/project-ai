import type {
  CaptureState,
} from '../../features/planner/plannerReducer';
import type {
  DaySnapshotDto,
  PlanDiffDto,
  PlanItemDto,
  TaskDto,
} from '../../api/types';

function planItem(
  id: number,
  title: string,
  start: string,
  end: string,
  status: 'planned' | 'done' = 'planned',
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

function task(item: PlanItemDto, estimatedMinutes: number): TaskDto {
  return {
    id: item.task_id!,
    title: item.title,
    priority: 'medium',
    estimated_minutes: estimatedMinutes,
    target_date: '2026-08-10',
    scheduling_type: 'flexible',
    fixed_start: null,
    fixed_end: null,
    preferred_window: null,
    earliest_start: null,
    latest_end: null,
    deadline: null,
    is_locked: false,
    status: item.status === 'done' ? 'done' : 'planned',
    routine_id: null,
    occurrence_date: null,
  };
}

const completed = planItem(
  1,
  'Согласовать архитектуру мобильного клиента',
  '15:00:00',
  '15:45:00',
  'done',
);
const current = planItem(2, 'Архитектура модуля', '16:30:00', '18:00:00');
const workout = planItem(3, 'Силовая тренировка', '19:30:00', '20:25:00');
const dinner = planItem(4, 'Ужин', '20:45:00', '21:15:00');

export const normalDaySnapshot: DaySnapshotDto = {
  date: '2026-08-10',
  focus_text: 'Сначала — Архитектура модуля.',
  progress: { done: 1, total: 4 },
  scheduled_items: [completed, current, workout, dinner],
  unscheduled_items: [],
  completed_items: [completed],
  current_item: current,
  completed_count: 1,
  total_count: 4,
  day_context: {
    energy_level: null,
    budget_limit: null,
    work_override_mode: 'busy',
    work_start_time: '10:00:00',
    work_end_time: '18:00:00',
  },
  tasks: [
    task(completed, 45),
    task(current, 90),
    task(workout, 55),
    task(dinner, 30),
  ],
  goals: [],
  routines: [],
  plan: {
    id: 21,
    date: '2026-08-10',
    summary: 'Работа, тренировка и спокойный вечер',
    focus_text: 'Сначала — Архитектура модуля.',
    energy_level: null,
    budget_limit: null,
    status: 'active',
    version: 7,
    items: [completed, current, workout, dinner],
  },
  plan_version: 7,
};

const doneItems = normalDaySnapshot.scheduled_items.map((item) => ({
  ...item,
  status: 'done',
}));

export const allDoneDaySnapshot: DaySnapshotDto = {
  ...normalDaySnapshot,
  progress: { done: 4, total: 4 },
  scheduled_items: doneItems,
  completed_items: doneItems,
  current_item: null,
  completed_count: 4,
  tasks: normalDaySnapshot.tasks.map((value) => ({ ...value, status: 'done' })),
  plan: { ...normalDaySnapshot.plan, items: doneItems, version: 8 },
  plan_version: 8,
};

export const appliedPlanDiff: PlanDiffDto = {
  availability_change: 'Работа → до 20:00',
  moved_plan_items: [
    {
      task_id: 3,
      title: 'Силовая тренировка',
      old_start: '19:30:00',
      new_start: '20:30:00',
    },
  ],
};

export const captureStates: Record<
  'processing' | 'clarification' | 'confirmation' | 'conflict',
  CaptureState
> = {
  processing: {
    status: 'submitting',
    requestId: 'dev-processing',
    operation: {
      kind: 'capture',
      text: 'Сегодня задержусь на работе до 20',
    },
    slow: true,
  },
  clarification: {
    status: 'clarification',
    value: {
      id: 'dev-clarification',
      question: 'Что именно добавить?',
      options: [
        { id: 'one_time', label: 'Разовая задача', value: 'разовая задача' },
        { id: 'routine', label: 'Ежедневная привычка', value: 'привычка' },
        { id: 'capability', label: 'Учёт питания', value: 'учёт питания' },
      ],
      free_text_allowed: true,
      expires_at: '2026-08-10T22:00:00Z',
    },
  },
  confirmation: {
    status: 'confirmation',
    value: {
      id: 'dev-confirmation',
      title: 'Применить изменение?',
      summary: 'Чтобы освободить вечер, план изменится так:',
      changes: {
        moved_plan_items: [
          {
            task_id: 3,
            title: 'Силовая тренировка',
            old_start: '19:30:00',
            new_start: '20:30:00',
          },
        ],
      },
      options: [
        { id: 'apply', label: 'Применить', value: 'применить' },
        { id: 'cancel', label: 'Оставить как есть', value: 'отмена' },
      ],
      expires_at: '2026-08-10T22:00:00Z',
      base_plan_version: 7,
    },
  },
  conflict: {
    status: 'conflict',
    value: {
      id: 'dev-conflict',
      title: 'Время уже занято',
      message: '19:00 уже занят созвоном.',
      options: [
        { id: 'choose_time', label: 'Выбрать другое время', value: 'другое время' },
        { id: 'cancel', label: 'Оставить как есть', value: 'отмена' },
      ],
      expires_at: '2026-08-10T22:00:00Z',
    },
  },
};
