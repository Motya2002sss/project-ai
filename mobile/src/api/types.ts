export type MessageStatus =
  | 'applied'
  | 'clarification_required'
  | 'confirmation_required'
  | 'conflict'
  | 'no_change'
  | 'unsupported_capability'
  | 'failed'
  | 'needs_clarification';

export type MessageReason = 'request_in_progress';
export type TaskStatus = 'planned' | 'done';
export type StoredTaskStatus = TaskStatus | 'cancelled';

export interface DayProgressDto {
  done: number;
  total: number;
}

export interface DayContextDto {
  energy_level: string | null;
  budget_limit: number | null;
  work_override_mode: string | null;
  work_start_time: string | null;
  work_end_time: string | null;
}

export interface PlanItemDto {
  id: number;
  task_id: number | null;
  title: string;
  item_type: string;
  status: string;
  start_time: string | null;
  end_time: string | null;
  unscheduled_reason: string | null;
}

export interface PlanDto {
  id: number;
  date: string;
  summary: string | null;
  focus_text: string;
  energy_level: string | null;
  budget_limit: number | null;
  status: string;
  version: number;
  items: PlanItemDto[];
}

export interface TaskDto {
  id: number;
  title: string;
  priority: string;
  estimated_minutes: number | null;
  target_date: string;
  scheduling_type: string;
  fixed_start: string | null;
  fixed_end: string | null;
  preferred_window: string | null;
  earliest_start: string | null;
  latest_end: string | null;
  deadline: string | null;
  is_locked: boolean;
  status: StoredTaskStatus;
  routine_id: number | null;
  occurrence_date: string | null;
}

export interface GoalDto {
  id: number;
  title: string;
  category: string;
  priority: string;
  status: string;
}

export interface RoutineDto {
  id: number;
  title: string;
  cadence: string;
  weekdays: number[];
  fixed_time: string | null;
  preferred_window: string | null;
  estimated_minutes: number | null;
  start_date: string;
  end_date: string | null;
  active: boolean;
}

export interface DaySnapshotDto {
  date: string;
  focus_text: string;
  progress: DayProgressDto;
  scheduled_items: PlanItemDto[];
  unscheduled_items: PlanItemDto[];
  completed_items: PlanItemDto[];
  current_item: PlanItemDto | null;
  completed_count: number;
  total_count: number;
  day_context: DayContextDto;
  tasks: TaskDto[];
  goals: GoalDto[];
  routines: RoutineDto[];
  plan: PlanDto;
  plan_version: number;
}

export interface MovedPlanItemDto {
  task_id: number;
  title: string;
  old_start: string;
  new_start: string;
}

export interface PlanDiffDto {
  created_task_ids?: number[];
  updated_task_ids?: number[];
  completed_task_ids?: number[];
  cancelled_task_ids?: number[];
  moved_plan_items?: MovedPlanItemDto[];
  unscheduled_task_ids?: number[];
  created_routine_ids?: number[];
  availability_change?: string | null;
  conflict?: string | null;
  clarification?: string | null;
}

export interface InteractionOptionDto {
  id: string;
  label: string;
  value: string;
}

export interface ClarificationDto {
  id: string;
  question: string;
  options: InteractionOptionDto[];
  free_text_allowed: boolean;
  expires_at: string;
}

export interface ConfirmationDto {
  id: string;
  title: string;
  summary: string;
  changes: PlanDiffDto;
  options: InteractionOptionDto[];
  expires_at: string;
  base_plan_version: number | null;
}

export interface ConflictDto {
  id: string | null;
  title: string;
  message: string;
  options: InteractionOptionDto[];
  expires_at: string | null;
}

export interface MobileActionResponseDto {
  request_id: string;
  status: MessageStatus;
  reason: MessageReason | null;
  reply_text: string;
  retryable: boolean;
  plan_diff: PlanDiffDto;
  clarification: ClarificationDto | null;
  confirmation: ConfirmationDto | null;
  conflict: ConflictDto | null;
  day_snapshot: DaySnapshotDto;
}

export interface MobileTaskMutationResponseDto {
  status: 'applied' | 'no_change';
  task: TaskDto;
  plan_diff: PlanDiffDto;
  day_snapshot: DaySnapshotDto;
}

export interface CaptureRequestDto {
  request_id: string;
  text: string;
}

export interface InteractionResponseRequestDto {
  request_id: string;
  text?: string;
  option_id?: string;
}

export interface TaskStatusRequestDto {
  status: TaskStatus;
}
