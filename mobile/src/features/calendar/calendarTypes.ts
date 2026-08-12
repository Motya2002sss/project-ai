export interface CalendarIntervalDto {
  start_at: string;
  end_at: string;
}

export interface CalendarDayItemDto {
  item_id: number;
  task_id: number | null;
  title: string;
  kind: string;
  status: string;
  start_at: string | null;
  end_at: string | null;
  unscheduled_reason: string | null;
}

export interface CalendarDayDto {
  date: string;
  timezone: string;
  materialized: boolean;
  plan_version: number | null;
  summary: string | null;
  items: CalendarDayItemDto[];
  busy_intervals: CalendarIntervalDto[];
  free_intervals: CalendarIntervalDto[];
  cursor: string;
}

export interface CalendarDaySummaryDto {
  date: string;
  materialized: boolean;
  plan_version: number | null;
  scheduled_count: number;
  unscheduled_count: number;
  completed_count: number;
  items: CalendarDayItemDto[];
}

export interface CalendarCommitmentLoadDto {
  commitment_id: string;
  title: string;
  target_minutes: number;
  target_sessions: number;
  scheduled_minutes: number;
  scheduled_sessions: number;
  completed_minutes: number;
  completed_sessions: number;
  remaining_minutes: number;
}

export interface CalendarWeekDto {
  start: string;
  end: string;
  timezone: string;
  days: CalendarDaySummaryDto[];
  commitment_load: CalendarCommitmentLoadDto[];
  cursor: string;
}

export interface CalendarMonthDto {
  month: string;
  timezone: string;
  milestones: {
    milestone_id: string;
    goal_id: string;
    title: string;
    occurred_at: string;
    status: string;
  }[];
  deadlines: { goal_id: string; title: string; date: string }[];
  life_modes: {
    mode_id: string;
    mode: string;
    starts_at: string;
    ends_at: string;
  }[];
  measurements: {
    goal_id: string;
    occurred_at: string;
    value: string;
    unit: string;
  }[];
  tension: {
    materialized_days: number;
    scheduled_minutes: number;
    unscheduled_items: number;
    busy_minutes: number;
  };
  cursor: string;
}

export interface CalendarCacheSnapshot {
  day: CalendarDayDto | null;
  week: CalendarWeekDto | null;
  month: CalendarMonthDto | null;
}
