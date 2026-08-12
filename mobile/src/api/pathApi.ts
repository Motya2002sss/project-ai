import type { RuntimeValidator } from './validation';
import type {
  EvidencePageDto,
  EvidenceSummaryDto,
  GoalPathDto,
  GoalPathGoalDto,
  GoalProgressDto,
  MilestoneSummaryDto,
  NextStepSummaryDto,
  PathResponseDto,
  PhaseSummaryDto,
  ProgramSummaryDto,
} from '../features/path/pathTypes';

export interface PathJsonRequester {
  request<T>(
    path: string,
    init?: RequestInit,
    validator?: RuntimeValidator<T>,
  ): Promise<T>;
}

export interface EvidencePageRequest {
  limit?: number;
  cursor?: string;
}

export class PathApi {
  constructor(private readonly client: PathJsonRequester) {}

  getPath(): Promise<PathResponseDto> {
    return this.client.request<PathResponseDto>(
      '/api/v2/path',
      undefined,
      isPathResponseDto,
    );
  }

  getGoal(publicId: string): Promise<GoalPathDto> {
    return this.client.request<GoalPathDto>(
      `/api/v2/goals/${encodeURIComponent(publicId)}`,
      undefined,
      isGoalPathDto,
    );
  }

  async getEvidence(
    publicId: string,
    request: EvidencePageRequest = {},
  ): Promise<EvidencePageDto> {
    const limit = request.limit ?? 20;
    if (!Number.isInteger(limit) || limit < 1 || limit > 50) {
      throw new RangeError('Evidence limit must be an integer from 1 to 50');
    }
    const cursor = request.cursor
      ? `&cursor=${encodeURIComponent(request.cursor)}`
      : '';
    return this.client.request<EvidencePageDto>(
      `/api/v2/goals/${encodeURIComponent(publicId)}/evidence?limit=${limit}${cursor}`,
      undefined,
      isEvidencePageDto,
    );
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function isString(value: unknown): value is string {
  return typeof value === 'string';
}

function isNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value);
}

function isInteger(value: unknown): value is number {
  return isNumber(value) && Number.isInteger(value);
}

function isNullableString(value: unknown): value is string | null {
  return value === null || isString(value);
}

function isDecimalString(value: unknown): value is string {
  return (
    isString(value) &&
    /^-?\d+(?:\.\d+)?$/.test(value) &&
    Number.isFinite(Number(value))
  );
}

function isNullableDecimal(value: unknown): value is string | null {
  return value === null || isDecimalString(value);
}

function isArrayOf<T>(
  value: unknown,
  validator: RuntimeValidator<T>,
): value is T[] {
  return Array.isArray(value) && value.every(validator);
}

function isGoal(value: unknown): value is GoalPathGoalDto {
  if (!isRecord(value)) return false;
  return (
    isString(value.public_id) &&
    value.public_id.length > 0 &&
    isString(value.title) &&
    isNullableString(value.life_area) &&
    isNullableString(value.outcome_type) &&
    isNullableDecimal(value.baseline_value) &&
    isNullableDecimal(value.current_value) &&
    isNullableDecimal(value.target_value) &&
    isNullableString(value.metric_unit) &&
    isNullableString(value.deadline) &&
    isNullableString(value.intensity) &&
    (value.allocation_minutes_week === null ||
      isInteger(value.allocation_minutes_week)) &&
    isString(value.status) &&
    isInteger(value.version)
  );
}

function isProgress(value: unknown): value is GoalProgressDto {
  if (!isRecord(value)) return false;
  const strategies = new Set(['metric', 'milestone', 'consistency', 'unknown']);
  const confidences = new Set(['low', 'medium', 'high']);
  const percentage = value.percentage;
  return (
    isString(value.strategy) &&
    strategies.has(value.strategy) &&
    (percentage === null ||
      (isDecimalString(percentage) &&
        Number(percentage) >= 0 &&
        Number(percentage) <= 100)) &&
    isRecord(value.components) &&
    isNullableString(value.reason) &&
    isString(value.formula_version) &&
    isNullableString(value.forecast_date) &&
    isString(value.confidence) &&
    confidences.has(value.confidence)
  );
}

function isFormula(value: unknown): boolean {
  return (
    isRecord(value) &&
    isString(value.strategy) &&
    isString(value.label) &&
    isString(value.explanation)
  );
}

function isMilestone(value: unknown): value is MilestoneSummaryDto {
  return (
    isRecord(value) &&
    isString(value.id) &&
    isString(value.title) &&
    isNullableString(value.description) &&
    isInteger(value.position) &&
    isNullableDecimal(value.weight) &&
    isString(value.status) &&
    isNullableString(value.completed_at)
  );
}

function isProgram(value: unknown): value is ProgramSummaryDto {
  return (
    isRecord(value) &&
    isString(value.id) &&
    isString(value.name) &&
    isString(value.status) &&
    isInteger(value.minimum_minutes_week) &&
    isInteger(value.comfortable_minutes_week) &&
    isInteger(value.maximum_minutes_week) &&
    isInteger(value.version)
  );
}

function isPhase(value: unknown): value is PhaseSummaryDto {
  return (
    isRecord(value) &&
    isString(value.id) &&
    isString(value.title) &&
    isInteger(value.position) &&
    isString(value.status) &&
    isNullableString(value.start_date) &&
    isNullableString(value.end_date)
  );
}

function isNextStep(value: unknown): value is NextStepSummaryDto {
  return (
    isRecord(value) &&
    isString(value.commitment_id) &&
    isString(value.title) &&
    isInteger(value.target_minutes_week) &&
    isInteger(value.target_sessions_week) &&
    isInteger(value.minimum_block_minutes) &&
    isArrayOf(value.allowed_weekdays, isInteger) &&
    isNullableString(value.preferred_window)
  );
}

function isEvidence(value: unknown): value is EvidenceSummaryDto {
  return (
    isRecord(value) &&
    isString(value.id) &&
    isString(value.evidence_type) &&
    isNullableDecimal(value.quantity) &&
    isNullableString(value.unit) &&
    isString(value.occurred_at)
  );
}

export function isGoalPathDto(value: unknown): value is GoalPathDto {
  if (!isRecord(value)) return false;
  return (
    isGoal(value.goal) &&
    isProgress(value.progress) &&
    isFormula(value.formula) &&
    isArrayOf(value.milestones, isMilestone) &&
    (value.current_program === null || isProgram(value.current_program)) &&
    (value.current_phase === null || isPhase(value.current_phase)) &&
    (value.next_step === null || isNextStep(value.next_step)) &&
    isArrayOf(value.recent_evidence, isEvidence)
  );
}

export function isPathResponseDto(value: unknown): value is PathResponseDto {
  return isRecord(value) && isArrayOf(value.goals, isGoalPathDto);
}

export function isEvidencePageDto(value: unknown): value is EvidencePageDto {
  return (
    isRecord(value) &&
    isArrayOf(value.items, isEvidence) &&
    isNullableString(value.next_cursor)
  );
}
