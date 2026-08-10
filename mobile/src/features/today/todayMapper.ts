import type {
  DaySnapshotDto,
  PlanItemDto,
  TaskDto,
  TaskStatus,
} from '../../api/types';
import type {
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
  effectiveStatus: string,
): TimelineVariant {
  if (effectiveStatus === 'done') return 'completed';
  if (item.id === currentItemId) return 'current';
  return 'upcoming';
}

function mapItem(
  item: PlanItemDto,
  taskById: Map<number, TaskDto>,
  currentItemId: number | null,
  completionOverrides: Readonly<Record<number, TaskStatus>>,
): TimelineRowModel {
  const effectiveStatus =
    item.task_id === null
      ? item.status
      : (completionOverrides[item.task_id] ?? item.status);
  const variant = rowVariant(item, currentItemId, effectiveStatus);
  const endTime = formatTime(item.end_time);
  return {
    id: item.id,
    taskId: item.task_id,
    title: item.title,
    time: formatTime(item.start_time),
    endTime,
    label:
      variant === 'current' ? `Сейчас${endTime ? ` · до ${endTime}` : ''}` : null,
    meta: taskMeta(
      item,
      item.task_id === null ? undefined : taskById.get(item.task_id),
    ),
    itemType: item.item_type,
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

export function mapDaySnapshot(
  snapshot: DaySnapshotDto,
  completionOverrides: Readonly<Record<number, TaskStatus>> = {},
): TodayModel {
  const taskById = new Map(snapshot.tasks.map((task) => [task.id, task]));
  const currentItemId = snapshot.current_item?.id ?? null;
  const rows = snapshot.scheduled_items.map((item) =>
    mapItem(item, taskById, currentItemId, completionOverrides),
  );
  const unscheduled = snapshot.unscheduled_items.map((item) =>
    mapItem(item, taskById, currentItemId, completionOverrides),
  );

  return {
    state: todayState(snapshot),
    dateLabel: formatDate(snapshot.date),
    focusText: snapshot.focus_text,
    dayRange: dayRange(rows),
    rows,
    unscheduled,
    completedCount: snapshot.completed_count,
    totalCount: snapshot.total_count,
    planVersion: snapshot.plan_version,
  };
}
