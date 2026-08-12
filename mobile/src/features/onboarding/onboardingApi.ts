import { ApiClient } from '../../api/client';
import type {
  OnboardingAllocation,
  OnboardingClarification,
  OnboardingPreview,
  OnboardingStructuredSummary,
  ResourceBudget,
} from './onboardingReducer';

export interface OnboardingPreviewInput {
  requestId: string;
  narrative: string;
  resourceBudget: ResourceBudget;
  previewId?: string;
  expectedVersion?: number;
}

export interface OnboardingApplyInput {
  previewId: string;
  expectedVersion: number;
}

export interface OnboardingServerState {
  status: 'not_started' | 'in_progress' | 'completed';
  preview: OnboardingPreview | null;
}

interface PreviewDto {
  id: string;
  status: 'clarification_required' | 'ready' | 'applied';
  version: number;
  structured_summary: Record<string, unknown>;
  goal_candidates: string[];
  resource_budget: Record<string, unknown>;
  allocation: Record<string, unknown>;
  clarification: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

interface StateDto {
  status: 'not_started' | 'in_progress' | 'completed';
  preview: PreviewDto | null;
}

export class OnboardingApi {
  constructor(private readonly client: ApiClient) {}

  async getState(): Promise<OnboardingServerState> {
    const value = await this.client.request<StateDto>(
      '/api/v2/onboarding',
      {},
      isStateDto,
    );
    return {
      status: value.status,
      preview: value.preview ? toPreview(value.preview) : null,
    };
  }

  async preview(input: OnboardingPreviewInput): Promise<OnboardingPreview> {
    const value = await this.client.request<PreviewDto>(
      '/api/v2/onboarding/preview',
      {
        method: 'POST',
        body: JSON.stringify({
          request_id: input.requestId,
          narrative: input.narrative,
          resource_budget: toResourceBudgetDto(input.resourceBudget),
          ...(input.previewId ? { preview_id: input.previewId } : {}),
          ...(input.expectedVersion != null
            ? { expected_version: input.expectedVersion }
            : {}),
        }),
      },
      isPreviewDto,
    );
    return toPreview(value);
  }

  async apply(input: OnboardingApplyInput): Promise<OnboardingPreview> {
    const value = await this.client.request<PreviewDto>(
      '/api/v2/onboarding/apply',
      {
        method: 'POST',
        body: JSON.stringify({
          preview_id: input.previewId,
          expected_version: input.expectedVersion,
        }),
      },
      isPreviewDto,
    );
    return toPreview(value);
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function isPreviewDto(value: unknown): value is PreviewDto {
  if (!isRecord(value)) return false;
  return (
    typeof value.id === 'string' &&
    (value.status === 'clarification_required' ||
      value.status === 'ready' ||
      value.status === 'applied') &&
    Number.isInteger(value.version) &&
    isRecord(value.structured_summary) &&
    Array.isArray(value.goal_candidates) &&
    value.goal_candidates.every((title) => typeof title === 'string') &&
    isRecord(value.resource_budget) &&
    isRecord(value.allocation) &&
    (value.clarification === null || isRecord(value.clarification)) &&
    typeof value.created_at === 'string' &&
    typeof value.updated_at === 'string'
  );
}

function isStateDto(value: unknown): value is StateDto {
  return (
    isRecord(value) &&
    (value.status === 'not_started' ||
      value.status === 'in_progress' ||
      value.status === 'completed') &&
    (value.preview === null || isPreviewDto(value.preview))
  );
}

function numberValue(record: Record<string, unknown>, key: string): number {
  const value = record[key];
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    throw new Error(`Invalid onboarding field: ${key}`);
  }
  return value;
}

function nullableString(
  record: Record<string, unknown>,
  key: string,
): string | null {
  const value = record[key];
  return typeof value === 'string' ? value : null;
}

function numberList(record: Record<string, unknown>, key: string): number[] {
  const value = record[key];
  return Array.isArray(value)
    ? value.filter((item): item is number => typeof item === 'number')
    : [];
}

function stringRecord(
  record: Record<string, unknown>,
  key: string,
): Record<string, string> {
  const value = record[key];
  if (!isRecord(value)) return {};
  return Object.fromEntries(
    Object.entries(value).filter(
      (entry): entry is [string, string] => typeof entry[1] === 'string',
    ),
  );
}

function toStructuredSummary(
  value: Record<string, unknown>,
): OnboardingStructuredSummary {
  return {
    workStart: nullableString(value, 'work_start'),
    workEnd: nullableString(value, 'work_end'),
    sleepTime: nullableString(value, 'sleep_time'),
    availableDays: numberList(value, 'available_days'),
    freeEvenings: numberList(value, 'free_evenings'),
    preferredWindows: stringRecord(value, 'preferred_windows'),
  };
}

function toResourceBudget(value: Record<string, unknown>): ResourceBudget {
  return {
    weeklyAvailableMinutes: numberValue(value, 'weekly_available_minutes'),
    availableDays: numberList(value, 'available_days'),
    minimumMinutes: numberValue(value, 'minimum_minutes'),
    comfortableMinutes: numberValue(value, 'comfortable_minutes'),
    maximumMinutes: numberValue(value, 'maximum_minutes'),
    freeEvenings: numberList(value, 'free_evenings'),
    preferredWindows: stringRecord(value, 'preferred_windows'),
    moneyBudget: nullableString(value, 'money_budget'),
    conflictPriority: nullableString(value, 'conflict_priority'),
    reservePercent: numberValue(value, 'reserve_percent'),
  };
}

function toAllocation(value: Record<string, unknown>): OnboardingAllocation {
  const rawGoals = value.goals;
  const goals = Array.isArray(rawGoals)
    ? rawGoals.flatMap((goal) => {
        if (!isRecord(goal) || typeof goal.title !== 'string') return [];
        return [
          {
            title: goal.title,
            minutes: numberValue(goal, 'minutes'),
            percent: numberValue(goal, 'percent'),
          },
        ];
      })
    : [];
  return {
    reservedMinutes: numberValue(value, 'reserved_minutes'),
    reservePercent: numberValue(value, 'reserve_percent'),
    allocatableMinutes: numberValue(value, 'allocatable_minutes'),
    plannedMinutes: numberValue(value, 'planned_minutes'),
    goals,
  };
}

function toClarification(
  value: Record<string, unknown> | null,
): OnboardingClarification | null {
  if (!value || typeof value.id !== 'string' || typeof value.question !== 'string') {
    return null;
  }
  return {
    id: value.id,
    question: value.question,
    allowsFreeText: value.allows_free_text === true,
  };
}

function toPreview(value: PreviewDto): OnboardingPreview {
  return {
    id: value.id,
    status: value.status,
    version: value.version,
    structuredSummary: toStructuredSummary(value.structured_summary),
    goalCandidates: value.goal_candidates.slice(0, 3),
    resourceBudget: toResourceBudget(value.resource_budget),
    allocation: toAllocation(value.allocation),
    clarification: toClarification(value.clarification),
  };
}

function toResourceBudgetDto(value: ResourceBudget): Record<string, unknown> {
  return {
    weekly_available_minutes: value.weeklyAvailableMinutes,
    available_days: value.availableDays,
    minimum_minutes: value.minimumMinutes,
    comfortable_minutes: value.comfortableMinutes,
    maximum_minutes: value.maximumMinutes,
    free_evenings: value.freeEvenings,
    preferred_windows: value.preferredWindows,
    money_budget: value.moneyBudget,
    conflict_priority: value.conflictPriority,
    reserve_percent: value.reservePercent,
  };
}
