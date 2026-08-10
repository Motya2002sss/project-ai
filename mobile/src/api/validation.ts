import type {
  ClarificationDto,
  ConfirmationDto,
  ConflictDto,
  DaySnapshotDto,
  GoalDto,
  InteractionOptionDto,
  MobileActionResponseDto,
  MobileTaskMutationResponseDto,
  MovedPlanItemDto,
  PlanDiffDto,
  PlanDto,
  PlanItemDto,
  RoutineDto,
  TaskDto,
} from './types';

export type RuntimeValidator<T> = (value: unknown) => value is T;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function isString(value: unknown): value is string {
  return typeof value === 'string';
}

function isNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value);
}

function isBoolean(value: unknown): value is boolean {
  return typeof value === 'boolean';
}

function isNullableString(value: unknown): value is string | null {
  return value === null || isString(value);
}

function isNullableNumber(value: unknown): value is number | null {
  return value === null || isNumber(value);
}

function isArrayOf<T>(
  value: unknown,
  validator: RuntimeValidator<T>,
): value is T[] {
  return Array.isArray(value) && value.every(validator);
}

function isNumberArray(value: unknown): value is number[] {
  return isArrayOf(value, isNumber);
}

function isPlanItemDto(value: unknown): value is PlanItemDto {
  if (!isRecord(value)) return false;
  return (
    isNumber(value.id) &&
    isNullableNumber(value.task_id) &&
    isString(value.title) &&
    isString(value.item_type) &&
    isString(value.status) &&
    isNullableString(value.start_time) &&
    isNullableString(value.end_time) &&
    isNullableString(value.unscheduled_reason)
  );
}

function isTaskDto(value: unknown): value is TaskDto {
  if (!isRecord(value)) return false;
  return (
    isNumber(value.id) &&
    isString(value.title) &&
    isString(value.priority) &&
    isNullableNumber(value.estimated_minutes) &&
    isString(value.target_date) &&
    isString(value.scheduling_type) &&
    isNullableString(value.fixed_start) &&
    isNullableString(value.fixed_end) &&
    isNullableString(value.preferred_window) &&
    isNullableString(value.earliest_start) &&
    isNullableString(value.latest_end) &&
    isNullableString(value.deadline) &&
    isBoolean(value.is_locked) &&
    (value.status === 'planned' ||
      value.status === 'done' ||
      value.status === 'cancelled') &&
    isNullableNumber(value.routine_id) &&
    isNullableString(value.occurrence_date)
  );
}

function isGoalDto(value: unknown): value is GoalDto {
  if (!isRecord(value)) return false;
  return (
    isNumber(value.id) &&
    isString(value.title) &&
    isString(value.category) &&
    isString(value.priority) &&
    isString(value.status)
  );
}

function isRoutineDto(value: unknown): value is RoutineDto {
  if (!isRecord(value)) return false;
  return (
    isNumber(value.id) &&
    isString(value.title) &&
    isString(value.cadence) &&
    isNumberArray(value.weekdays) &&
    isNullableString(value.fixed_time) &&
    isNullableString(value.preferred_window) &&
    isNullableNumber(value.estimated_minutes) &&
    isString(value.start_date) &&
    isNullableString(value.end_date) &&
    isBoolean(value.active)
  );
}

function isPlanDto(value: unknown): value is PlanDto {
  if (!isRecord(value)) return false;
  return (
    isNumber(value.id) &&
    isString(value.date) &&
    isNullableString(value.summary) &&
    isString(value.focus_text) &&
    isNullableString(value.energy_level) &&
    isNullableNumber(value.budget_limit) &&
    isString(value.status) &&
    isNumber(value.version) &&
    isArrayOf(value.items, isPlanItemDto)
  );
}

export function isDaySnapshotDto(value: unknown): value is DaySnapshotDto {
  if (!isRecord(value)) return false;
  if (!isRecord(value.progress) || !isRecord(value.day_context)) return false;
  return (
    isString(value.date) &&
    isString(value.focus_text) &&
    isNumber(value.progress.done) &&
    isNumber(value.progress.total) &&
    isArrayOf(value.scheduled_items, isPlanItemDto) &&
    isArrayOf(value.unscheduled_items, isPlanItemDto) &&
    isArrayOf(value.completed_items, isPlanItemDto) &&
    (value.current_item === null || isPlanItemDto(value.current_item)) &&
    isNumber(value.completed_count) &&
    isNumber(value.total_count) &&
    isNullableString(value.day_context.energy_level) &&
    isNullableNumber(value.day_context.budget_limit) &&
    isNullableString(value.day_context.work_override_mode) &&
    isNullableString(value.day_context.work_start_time) &&
    isNullableString(value.day_context.work_end_time) &&
    isArrayOf(value.tasks, isTaskDto) &&
    isArrayOf(value.goals, isGoalDto) &&
    isArrayOf(value.routines, isRoutineDto) &&
    isPlanDto(value.plan) &&
    isNumber(value.plan_version)
  );
}

function hasOptionalNumberArray(
  record: Record<string, unknown>,
  key: string,
): boolean {
  return record[key] === undefined || isNumberArray(record[key]);
}

function isPlanDiffDto(value: unknown): value is PlanDiffDto {
  if (!isRecord(value)) return false;
  const moved = value.moved_plan_items;
  return (
    hasOptionalNumberArray(value, 'created_task_ids') &&
    hasOptionalNumberArray(value, 'updated_task_ids') &&
    hasOptionalNumberArray(value, 'completed_task_ids') &&
    hasOptionalNumberArray(value, 'cancelled_task_ids') &&
    hasOptionalNumberArray(value, 'unscheduled_task_ids') &&
    hasOptionalNumberArray(value, 'created_routine_ids') &&
    (moved === undefined ||
      isArrayOf(moved, (item): item is MovedPlanItemDto => {
        if (!isRecord(item)) return false;
        return (
          isNumber(item.task_id) &&
          isString(item.title) &&
          isString(item.old_start) &&
          isString(item.new_start)
        );
      })) &&
    (value.availability_change === undefined ||
      isNullableString(value.availability_change)) &&
    (value.conflict === undefined || isNullableString(value.conflict)) &&
    (value.clarification === undefined || isNullableString(value.clarification))
  );
}

function isInteractionOptionDto(value: unknown): value is InteractionOptionDto {
  if (!isRecord(value)) return false;
  return isString(value.id) && isString(value.label) && isString(value.value);
}

function isClarificationDto(value: unknown): value is ClarificationDto {
  if (!isRecord(value)) return false;
  return (
    isString(value.id) &&
    isString(value.question) &&
    isArrayOf(value.options, isInteractionOptionDto) &&
    isBoolean(value.free_text_allowed) &&
    isString(value.expires_at)
  );
}

function isConfirmationDto(value: unknown): value is ConfirmationDto {
  if (!isRecord(value)) return false;
  return (
    isString(value.id) &&
    isString(value.title) &&
    isString(value.summary) &&
    isPlanDiffDto(value.changes) &&
    isArrayOf(value.options, isInteractionOptionDto) &&
    isString(value.expires_at) &&
    isNullableNumber(value.base_plan_version)
  );
}

function isConflictDto(value: unknown): value is ConflictDto {
  if (!isRecord(value)) return false;
  return (
    isNullableString(value.id) &&
    isString(value.title) &&
    isString(value.message) &&
    isArrayOf(value.options, isInteractionOptionDto) &&
    isNullableString(value.expires_at)
  );
}

export function isMobileActionResponseDto(
  value: unknown,
): value is MobileActionResponseDto {
  if (!isRecord(value)) return false;
  const statuses = new Set([
    'applied',
    'clarification_required',
    'confirmation_required',
    'conflict',
    'no_change',
    'unsupported_capability',
    'failed',
    'needs_clarification',
  ]);
  const baseIsValid =
    isString(value.request_id) &&
    isString(value.status) &&
    statuses.has(value.status) &&
    (value.reason === null || value.reason === 'request_in_progress') &&
    isString(value.reply_text) &&
    isBoolean(value.retryable) &&
    isPlanDiffDto(value.plan_diff) &&
    (value.clarification === null || isClarificationDto(value.clarification)) &&
    (value.confirmation === null || isConfirmationDto(value.confirmation)) &&
    (value.conflict === null || isConflictDto(value.conflict)) &&
    isDaySnapshotDto(value.day_snapshot);
  if (!baseIsValid) return false;
  if (
    value.status === 'clarification_required' ||
    value.status === 'needs_clarification'
  ) {
    return value.clarification !== null;
  }
  if (value.status === 'confirmation_required') return value.confirmation !== null;
  if (value.status === 'conflict') return value.conflict !== null;
  return true;
}

export function isMobileTaskMutationResponseDto(
  value: unknown,
): value is MobileTaskMutationResponseDto {
  if (!isRecord(value)) return false;
  return (
    (value.status === 'applied' || value.status === 'no_change') &&
    isTaskDto(value.task) &&
    isPlanDiffDto(value.plan_diff) &&
    isDaySnapshotDto(value.day_snapshot)
  );
}
