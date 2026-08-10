export type TodayState = 'normal' | 'empty' | 'allDone';
export type TimelineVariant = 'current' | 'upcoming' | 'completed';

export interface TimelineRowModel {
  id: number;
  taskId: number | null;
  title: string;
  time: string | null;
  endTime: string | null;
  label: string | null;
  meta: string | null;
  itemType: string;
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
  planVersion: number;
}
