import type {
  DaySnapshotDto,
  PlanItemDto,
  TaskDto,
  TaskStatus,
} from '../../api/types';
import type {
  TimelineItemKind,
  TimelineRowModel,
  TimelineVariant,
  TodayModel,
  TodayState,
} from './models';

const russianDateFormatter = new Intl.DateTimeFormat('ru-RU', {
  weekday: 'long',
  day: 'numeric',
  month: 'long',
  timeZone: 'UTC',
});

const unscheduledReasonCopy: Readonly<Record<string, string>> = {
  preferred_window_passed: 'Предпочтённое время уже прошло',
  no_available_slot: 'Нет подходящего свободного окна',
  fixed_time_conflict: 'Конфликт фиксированного времени',
  fixed_time_passed: 'Указанное время уже прошло',
  missing_fixed_time: 'Нужно уточнить время',
  needs_clarification: 'Нужно уточнение',
  missing_duration: 'Не указана длительность',
  outside_day_bounds: 'Время вне границ дня',
  completed_without_time: 'Выполнено без времени',
};

const lifeAreaCopy: Readonly<Record<string, string>> = {
  body: 'Тело',
  career: 'Карьера',
  mind: 'Ум',
  personal: 'Личное',
  relationships: 'Отношения',
  finance: 'Финансы',
};

function formatDate(date: string): string {
  const formatted = russianDateFormatter.format(new Date(`${date}T12:00:00Z`));
  const [weekday = '', rest = ''] = formatted.split(', ');
  return `${weekday.charAt(0).toUpperCase()}${weekday.slice(1)} · ${rest}`;
}

export function formatTime(value: string | null): string | null {
  if (!value) return null;
  return value.slice(0, 5);
}

function taskMeta(item: PlanItemDto, task: TaskDto | undefined): string | null {
  if (item.unscheduled_reason) {
    return (
      unscheduledReasonCopy[item.unscheduled_reason] ??
      'Нужно уточнить планирование'
    );
  }
  if (task?.estimated_minutes) return `${task.estimated_minutes} минут`;
  return null;
}

function rowVariant(
  item: PlanItemDto,
  currentItemId: number | null,
  isBeforeCurrent: boolean,
  effectiveStatus: string,
): TimelineVariant {
  if (effectiveStatus === 'done') return 'completed';
  if (item.id === currentItemId) return 'current';
  if (isBeforeCurrent) return 'past';
  return 'upcoming';
}

function timeMinutes(value: string | null | undefined): number | null {
  if (!value) return null;
  const [rawHour, rawMinute] = value.split(':');
  if (rawHour === undefined || rawMinute === undefined) return null;
  const hour = Number(rawHour);
  const minute = Number(rawMinute);
  if (!Number.isFinite(hour) || !Number.isFinite(minute)) return null;
  return hour * 60 + minute;
}

function snapshotClockMinutes(snapshot: DaySnapshotDto): number | null {
  if (!snapshot.as_of || snapshot.as_of.slice(0, 10) !== snapshot.date) {
    return null;
  }
  return timeMinutes(snapshot.as_of.slice(11, 16));
}

function timelineKind(itemType: string): TimelineItemKind {
  switch (itemType) {
    case 'wake':
    case 'routine':
    case 'routine_anchor':
      return 'anchor';
    case 'fixed_event':
    case 'work':
      return 'fixed';
    case 'meal':
    case 'nutrition':
      return 'meal';
    case 'commute':
    case 'buffer':
      return 'commute';
    case 'free':
    case 'free_time':
      return 'free';
    case 'recovery':
    case 'rest':
      return 'recovery';
    case 'sleep':
      return 'sleep';
    case 'task':
    case 'planner_action':
    case 'workout':
    case 'learning':
      return 'action';
    default:
      return 'other';
  }
}

function taskGoalContext(
  task: TaskDto | undefined,
  goalById: Map<number, DaySnapshotDto['goals'][number]>,
): string | null {
  if (task?.goal_id == null) return null;
  const goal = goalById.get(task.goal_id);
  if (!goal) return null;
  const area = lifeAreaCopy[goal.category] ?? goal.category;
  return `${area} · ${goal.title}`;
}

function mapItem(
  item: PlanItemDto,
  taskById: Map<number, TaskDto>,
  goalById: Map<number, DaySnapshotDto['goals'][number]>,
  currentItemId: number | null,
  isBeforeCurrent: boolean,
  completionOverrides: Readonly<Record<number, TaskStatus>>,
): TimelineRowModel {
  const effectiveStatus =
    item.task_id === null
      ? item.status
      : (completionOverrides[item.task_id] ?? item.status);
  const variant = rowVariant(
    item,
    currentItemId,
    isBeforeCurrent,
    effectiveStatus,
  );
  const endTime = formatTime(item.end_time);
  const task = item.task_id === null ? undefined : taskById.get(item.task_id);
  return {
    id: item.id,
    taskId: item.task_id,
    title: item.title,
    time: formatTime(item.start_time),
    endTime,
    label:
      variant === 'current' ? `Сейчас${endTime ? ` · до ${endTime}` : ''}` : null,
    meta: taskMeta(item, task),
    goalContext: taskGoalContext(task, goalById),
    itemType: item.item_type,
    kind: timelineKind(item.item_type),
    variant,
    isCompletable: item.task_id !== null && item.status !== 'cancelled',
  };
}

function dayRange(rows: TimelineRowModel[]): string | null {
  const firstTime = rows.find((row) => row.time)?.time ?? null;
  let lastTime: string | null = null;
  for (const row of rows) {
    if (row.endTime) lastTime = row.endTime;
  }
  return firstTime && lastTime ? `${firstTime} — ${lastTime}` : null;
}

function todayState(snapshot: DaySnapshotDto): TodayState {
  if (snapshot.total_count > 0 && snapshot.completed_count >= snapshot.total_count) {
    return 'allDone';
  }
  if (
    snapshot.total_count === 0 &&
    snapshot.scheduled_items.length === 0 &&
    snapshot.unscheduled_items.length === 0
  ) {
    return 'empty';
  }
  return 'normal';
}

function optimisticCompletedCount(
  snapshot: DaySnapshotDto,
  completionOverrides: Readonly<Record<number, TaskStatus>>,
  baseCount = snapshot.completed_count,
  totalCount = snapshot.total_count,
): number {
  let count = baseCount;
  const taskById = new Map(snapshot.tasks.map((task) => [task.id, task]));
  for (const [rawTaskId, targetStatus] of Object.entries(completionOverrides)) {
    const task = taskById.get(Number(rawTaskId));
    if (!task || task.status === targetStatus) continue;
    count += targetStatus === 'done' ? 1 : -1;
  }
  return Math.min(totalCount, Math.max(0, count));
}

export function mapDaySnapshot(
  snapshot: DaySnapshotDto,
  completionOverrides: Readonly<Record<number, TaskStatus>> = {},
): TodayModel {
  const taskById = new Map(snapshot.tasks.map((task) => [task.id, task]));
  const goalById = new Map(snapshot.goals.map((goal) => [goal.id, goal]));
  const currentItemId = snapshot.current_item?.id ?? null;
  const currentIndex = snapshot.scheduled_items.findIndex(
    (item) => item.id === currentItemId,
  );
  const snapshotMinutes = snapshotClockMinutes(snapshot);
  const rows = snapshot.scheduled_items.map((item, index) =>
    mapItem(
      item,
      taskById,
      goalById,
      currentItemId,
      currentIndex >= 0
        ? index < currentIndex
        : snapshotMinutes !== null &&
            (timeMinutes(item.end_time) ?? Number.POSITIVE_INFINITY) <=
              snapshotMinutes,
      completionOverrides,
    ),
  );
  const unscheduled = snapshot.unscheduled_items.map((item) =>
    mapItem(
      item,
      taskById,
      goalById,
      currentItemId,
      false,
      completionOverrides,
    ),
  );
  const completedCount = optimisticCompletedCount(snapshot, completionOverrides);
  const totalCount = snapshot.total_count;
  const weekProgress = snapshot.week_progress;
  const weekDoneCount = weekProgress
    ? optimisticCompletedCount(
        snapshot,
        completionOverrides,
        weekProgress.done,
        weekProgress.total,
      )
    : 0;

  return {
    state: todayState(snapshot),
    dateLabel: formatDate(snapshot.date),
    focusText: snapshot.focus_text,
    dayRange: dayRange(rows),
    rows,
    unscheduled,
    completedCount,
    totalCount,
    progressLabel:
      totalCount > 0
        ? `Сегодня ${completedCount} из ${totalCount}`
        : 'Сегодня без задач',
    progressFraction:
      totalCount > 0 ? Math.min(1, Math.max(0, completedCount / totalCount)) : 0,
    weekProgressLabel:
      weekProgress && weekProgress.total > 0
        ? `Неделя ${weekDoneCount} из ${weekProgress.total}`
        : null,
    directionTitles: snapshot.goals.slice(0, 3).map((goal) => goal.title),
    planVersion: snapshot.plan_version,
  };
}
