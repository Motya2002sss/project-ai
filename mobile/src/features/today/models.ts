export type TodayState = 'normal' | 'empty' | 'allDone';
export type TimelineVariant = 'past' | 'current' | 'upcoming' | 'completed';
export type TimelineItemKind =
  | 'anchor'
  | 'fixed'
  | 'action'
  | 'meal'
  | 'commute'
  | 'free'
  | 'recovery'
  | 'sleep'
  | 'other';

export interface TimelineRowModel {
  id: number;
  taskId: number | null;
  title: string;
  time: string | null;
  endTime: string | null;
  label: string | null;
  meta: string | null;
  goalContext: string | null;
  itemType: string;
  kind: TimelineItemKind;
  variant: TimelineVariant;
  isCompletable: boolean;
}

export interface TodayModel {
  state: TodayState;
  dateLabel: string;
  focusText: string;
  dayRange: string | null;
  rows: TimelineRowModel[];
  unscheduled: TimelineRowModel[];
  completedCount: number;
  totalCount: number;
  progressLabel: string;
  progressFraction: number;
  weekProgressLabel: string | null;
  directionTitles: string[];
  planVersion: number;
}
