import type { RuntimeValidator } from './validation';
import type {
  CalendarDayDto,
  CalendarDayItemDto,
  CalendarMonthDto,
  CalendarWeekDto,
} from '../features/calendar/calendarTypes';

export interface CalendarJsonRequester {
  request<T>(path: string, init?: RequestInit, validator?: RuntimeValidator<T>): Promise<T>;
}

export class CalendarApi {
  constructor(private readonly client: CalendarJsonRequester) {}

  getDay(date: string): Promise<CalendarDayDto> {
    requireDate(date);
    return this.client.request(`/api/v2/calendar/day?date=${date}`, undefined, isCalendarDayDto);
  }

  getWeek(start: string): Promise<CalendarWeekDto> {
    const value = requireDate(start);
    if (value.getUTCDay() !== 1) throw new RangeError('Week must start on Monday');
    return this.client.request(`/api/v2/calendar/week?start=${start}`, undefined, isCalendarWeekDto);
  }

  getMonth(month: string): Promise<CalendarMonthDto> {
    const value = requireDate(month);
    if (value.getUTCDate() !== 1) throw new RangeError('Month must start on day one');
    return this.client.request(`/api/v2/calendar/month?month=${month}`, undefined, isCalendarMonthDto);
  }
}

const DAY_KEYS = ['date', 'timezone', 'materialized', 'plan_version', 'summary', 'items', 'busy_intervals', 'free_intervals', 'cursor'];
const ITEM_KEYS = ['item_id', 'task_id', 'title', 'kind', 'status', 'start_at', 'end_at', 'unscheduled_reason'];

function record(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}
function exact(value: Record<string, unknown>, keys: string[]): boolean {
  return Object.keys(value).length === keys.length && keys.every((key) => key in value);
}
function text(value: unknown): value is string { return typeof value === 'string'; }
function nullableText(value: unknown): value is string | null { return value === null || text(value); }
function integer(value: unknown): value is number { return Number.isInteger(value) && Number(value) >= 0; }
function list(value: unknown, check: (item: unknown) => boolean): value is unknown[] {
  return Array.isArray(value) && value.every(check);
}
function interval(value: unknown): value is { start_at: string; end_at: string } {
  return record(value) && exact(value, ['start_at', 'end_at']) && instant(value.start_at) && instant(value.end_at);
}
function item(value: unknown): value is CalendarDayItemDto {
  return record(value) && exact(value, ITEM_KEYS) && integer(value.item_id) &&
    (value.task_id === null || integer(value.task_id)) && text(value.title) &&
    text(value.kind) && text(value.status) && nullableInstant(value.start_at) &&
    nullableInstant(value.end_at) && (value.start_at === null) === (value.end_at === null) &&
    nullableText(value.unscheduled_reason);
}

export function isCalendarDayDto(value: unknown): value is CalendarDayDto {
  return record(value) && exact(value, DAY_KEYS) && validDate(value.date) &&
    text(value.timezone) && typeof value.materialized === 'boolean' &&
    (value.plan_version === null || integer(value.plan_version)) && nullableText(value.summary) &&
    list(value.items, item) && list(value.busy_intervals, interval) &&
    list(value.free_intervals, interval) && text(value.cursor);
}

export function isCalendarWeekDto(value: unknown): value is CalendarWeekDto {
  if (!record(value) || !exact(value, ['start', 'end', 'timezone', 'days', 'commitment_load', 'cursor'])) return false;
  const day = (candidate: unknown) => record(candidate) &&
    exact(candidate, ['date', 'materialized', 'plan_version', 'scheduled_count', 'unscheduled_count', 'completed_count', 'items']) &&
    validDate(candidate.date) && typeof candidate.materialized === 'boolean' &&
    (candidate.plan_version === null || integer(candidate.plan_version)) &&
    integer(candidate.scheduled_count) && integer(candidate.unscheduled_count) &&
    integer(candidate.completed_count) && list(candidate.items, item);
  const load = (candidate: unknown) => record(candidate) &&
    exact(candidate, ['commitment_id', 'title', 'target_minutes', 'target_sessions', 'scheduled_minutes', 'scheduled_sessions', 'completed_minutes', 'completed_sessions', 'remaining_minutes']) &&
    text(candidate.commitment_id) && text(candidate.title) &&
    ['target_minutes', 'target_sessions', 'scheduled_minutes', 'scheduled_sessions', 'completed_minutes', 'completed_sessions', 'remaining_minutes'].every((key) => integer(candidate[key]));
  return validDate(value.start) && validDate(value.end) && text(value.timezone) &&
    Array.isArray(value.days) && value.days.length === 7 && value.days.every(day) &&
    Array.isArray(value.commitment_load) && value.commitment_load.every(load) && text(value.cursor);
}

export function isCalendarMonthDto(value: unknown): value is CalendarMonthDto {
  if (!record(value) || !exact(value, ['month', 'timezone', 'milestones', 'deadlines', 'life_modes', 'measurements', 'tension', 'cursor'])) return false;
  const milestone = (x: unknown) => record(x) && exact(x, ['milestone_id', 'goal_id', 'title', 'occurred_at', 'status']) && ['milestone_id', 'goal_id', 'title', 'status'].every((key) => text(x[key])) && instant(x.occurred_at);
  const deadline = (x: unknown) => record(x) && exact(x, ['goal_id', 'title', 'date']) && text(x.goal_id) && text(x.title) && validDate(x.date);
  const mode = (x: unknown) => record(x) && exact(x, ['mode_id', 'mode', 'starts_at', 'ends_at']) && text(x.mode_id) && text(x.mode) && instant(x.starts_at) && instant(x.ends_at);
  const measurement = (x: unknown) => record(x) && exact(x, ['goal_id', 'occurred_at', 'value', 'unit']) && text(x.goal_id) && instant(x.occurred_at) && text(x.value) && text(x.unit) && /^-?\d+(?:\.\d+)?$/.test(x.value);
  const tension = value.tension;
  return validDate(value.month) && text(value.timezone) && list(value.milestones, milestone) &&
    list(value.deadlines, deadline) && list(value.life_modes, mode) &&
    list(value.measurements, measurement) && record(tension) &&
    exact(tension, ['materialized_days', 'scheduled_minutes', 'unscheduled_items', 'busy_minutes']) &&
    ['materialized_days', 'scheduled_minutes', 'unscheduled_items', 'busy_minutes'].every((key) => integer(tension[key])) && text(value.cursor);
}

function validDate(value: unknown): value is string {
  if (!text(value) || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const parsed = new Date(`${value}T00:00:00Z`);
  return !Number.isNaN(parsed.valueOf()) && parsed.toISOString().slice(0, 10) === value;
}

function instant(value: unknown): value is string {
  return text(value) && !Number.isNaN(new Date(value).valueOf()) && /(?:Z|[+-]\d{2}:\d{2})$/.test(value);
}

function nullableInstant(value: unknown): value is string | null {
  return value === null || instant(value);
}

function requireDate(value: string): Date {
  if (!validDate(value)) throw new RangeError('Expected YYYY-MM-DD');
  return new Date(`${value}T00:00:00Z`);
}
