import type {
  CalendarDayDto,
  CalendarDayItemDto,
  CalendarMonthDto,
  CalendarWeekDto,
} from './calendarTypes';

export type CalendarMode = 'day' | 'week' | 'month';

interface ModelInput {
  mode: CalendarMode;
  selectedDate: string;
  width: number;
  day: CalendarDayDto | null;
  week: CalendarWeekDto | null;
  month: CalendarMonthDto | null;
  status: 'loading' | 'ready' | 'error';
  source: 'cache' | 'network' | null;
  errorMessage?: string;
}

export type CalendarScreenModel =
  | { state: 'loading' }
  | { state: 'error'; message: string }
  | {
      state: 'ready'; compact: boolean; notice: string | null; rangeLabel: string;
      weekDays: { date: string; label: string; day: string; selected: boolean; hasPlan: boolean; completed: boolean }[];
      selectedItems: { id: number; title: string; timeLabel: string; kindLabel: string; completed: boolean }[];
      emptyMessage: string | null; freeLabel: string | null;
      commitments: { id: string; title: string; detail: string }[];
      monthFacts: { id: string; dateLabel: string; title: string; kind: string }[];
      monthSummary: string; actions: [];
    };

export function buildCalendarScreenModel(input: ModelInput): CalendarScreenModel {
  const relevant = input.mode === 'month' ? input.month : input.week;
  if (!relevant && input.status === 'loading') return { state: 'loading' };
  if (!relevant) return { state: 'error', message: input.errorMessage ?? 'Не удалось загрузить календарь.' };
  const notice = input.status === 'error'
    ? input.source === 'cache'
      ? 'Сохранено на устройстве · не удалось обновить'
      : 'Не удалось обновить · показаны последние данные'
    : null;
  const selected = input.week?.days.find((day) => day.date === input.selectedDate);
  const selectedItems = (input.day?.date === input.selectedDate ? [
    ...input.day.items.map(
      (item) => mapItem(item, input.day!.timezone),
    ),
    ...input.day.busy_intervals.map((interval, index) => mapInterval(
      interval, input.day!.timezone, -1 - index, 'Занято', 'Внешний календарь',
    )),
    ...input.day.free_intervals.map((interval, index) => mapInterval(
      interval, input.day!.timezone, -1001 - index, 'Свободно', 'Свободное окно',
    )),
  ].sort((a, b) => a.sortKey.localeCompare(b.sortKey)) : (selected?.items ?? []).map(
    (item) => mapItem(item, input.week?.timezone ?? input.day?.timezone ?? 'UTC'),
  )).map(({ sortKey: _sortKey, ...item }) => item);
  const monthFacts = input.month ? buildMonthFacts(input.month) : [];
  return {
    state: 'ready', compact: input.width <= 375, notice,
    rangeLabel: input.mode === 'month'
      ? formatMonth(input.month?.month ?? monthForDate(input.selectedDate))
      : input.mode === 'day'
        ? longDate(input.selectedDate)
        : `${shortDate(input.week!.start)} — ${shortDate(input.week!.end)}`,
    weekDays: (input.week?.days ?? []).map((day) => ({
      date: day.date,
      label: weekday(day.date),
      day: day.date.slice(8),
      selected: day.date === input.selectedDate,
      hasPlan: day.materialized,
      completed: day.scheduled_count > 0 && day.completed_count === day.scheduled_count,
    })),
    selectedItems,
    emptyMessage: selectedItems.length === 0 ? 'На этот день ничего не запланировано' : null,
    freeLabel: input.day?.date === input.selectedDate && input.day.free_intervals.length > 0
      ? `Свободно ${durationLabel(input.day.free_intervals)}` : null,
    commitments: (input.week?.commitment_load ?? []).map((item) => ({
      id: item.commitment_id,
      title: item.title,
      detail: `${item.scheduled_minutes} из ${item.target_minutes} мин · осталось ${item.remaining_minutes}`,
    })),
    monthFacts,
    monthSummary: input.month
      ? `${input.month.tension.materialized_days} дней с планом · ${hoursLabel(input.month.tension.scheduled_minutes)} запланировано`
      : '',
    actions: [],
  };
}

export function mondayForDate(value: string): string {
  const date = isoDate(value);
  const shift = (date.getUTCDay() + 6) % 7;
  date.setUTCDate(date.getUTCDate() - shift);
  return date.toISOString().slice(0, 10);
}

export function monthForDate(value: string): string { return `${value.slice(0, 7)}-01`; }

function mapItem(item: CalendarDayItemDto, timezone: string) {
  const labels: Record<string, string> = { recovery: 'Восстановление', sleep: 'Сон', anchor: 'Опора дня', task: 'План' };
  return {
    id: item.item_id, title: item.title,
    timeLabel: item.start_at && item.end_at ? `${clock(item.start_at, timezone)} — ${clock(item.end_at, timezone)}` : 'Без времени',
    kindLabel: labels[item.kind] ?? 'План', completed: item.status === 'done',
    sortKey: item.start_at ?? '9999',
  };
}

function mapInterval(
  interval: { start_at: string; end_at: string },
  timezone: string,
  id: number,
  title: string,
  kindLabel: string,
) {
  return {
    id,
    title,
    timeLabel: `${clock(interval.start_at, timezone)} — ${clock(interval.end_at, timezone)}`,
    kindLabel,
    completed: false,
    sortKey: interval.start_at,
  };
}

function buildMonthFacts(month: CalendarMonthDto) {
  return [
    ...month.measurements.map((item) => ({ id: `measurement-${item.goal_id}-${item.occurred_at}`, dateLabel: shortDate(item.occurred_at.slice(0, 10)), title: `${item.value} ${item.unit}`, kind: 'Измерение', sortKey: item.occurred_at })),
    ...month.milestones.map((item) => ({ id: item.milestone_id, dateLabel: shortDate(item.occurred_at.slice(0, 10)), title: item.title, kind: 'Этап', sortKey: item.occurred_at })),
    ...month.life_modes.map((item) => ({ id: item.mode_id, dateLabel: `${shortDate(item.starts_at.slice(0, 10))} — ${shortDate(item.ends_at.slice(0, 10))}`, title: modeLabel(item.mode), kind: 'Режим', sortKey: item.starts_at })),
    ...month.deadlines.map((item) => ({ id: `deadline-${item.goal_id}`, dateLabel: shortDate(item.date), title: item.title, kind: 'Срок', sortKey: item.date })),
  ].sort((a, b) => a.sortKey.localeCompare(b.sortKey)).map(({ sortKey: _sortKey, ...item }) => item);
}

function isoDate(value: string): Date { return new Date(`${value}T00:00:00Z`); }
function weekday(value: string): string { return new Intl.DateTimeFormat('ru-RU', { weekday: 'short', timeZone: 'UTC' }).format(isoDate(value)).replace('.', '').toUpperCase(); }
function shortDate(value: string): string { return new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'short', timeZone: 'UTC' }).format(isoDate(value)).replace('.', ''); }
function longDate(value: string): string { const formatted = new Intl.DateTimeFormat('ru-RU', { weekday: 'long', day: 'numeric', month: 'long', timeZone: 'UTC' }).format(isoDate(value)); return formatted[0]!.toUpperCase() + formatted.slice(1); }
function formatMonth(value: string): string { const text = new Intl.DateTimeFormat('ru-RU', { month: 'long', year: 'numeric', timeZone: 'UTC' }).format(isoDate(value)); return text[0]!.toUpperCase() + text.slice(1); }
function clock(value: string, timeZone: string): string { return new Intl.DateTimeFormat('ru-RU', { hour: '2-digit', minute: '2-digit', hour12: false, timeZone }).format(new Date(value)); }
function modeLabel(mode: string): string { return ({ travel: 'Поездка', vacation: 'Отпуск', recovery: 'Восстановление', sick: 'Бережный режим', workload: 'Высокая нагрузка', low_sleep: 'Мало сна', focus_sprint: 'Фокус' } as Record<string, string>)[mode] ?? 'Особый режим'; }
function durationLabel(intervals: { start_at: string; end_at: string }[]): string { return hoursLabel(intervals.reduce((sum, item) => sum + Math.max(0, (new Date(item.end_at).valueOf() - new Date(item.start_at).valueOf()) / 60000), 0)); }
function hoursLabel(minutes: number): string { const hours = Math.floor(minutes / 60); const rest = Math.round(minutes % 60); return rest ? `${hours} ч ${rest} мин` : `${hours} ч`; }
