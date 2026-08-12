import type {
  RecoverableOnboardingDraft,
  ResourceBudget,
} from './onboardingReducer';
import {
  defaultStorageTimeoutMs,
  withStorageDeadline,
} from '../../storage/storageDeadline';

export interface OnboardingKeyValueStorage {
  getItem(key: string): Promise<string | null>;
  setItem(key: string, value: string): Promise<void>;
  removeItem(key: string): Promise<void>;
}

export type OnboardingDraft = RecoverableOnboardingDraft;

export class OnboardingDraftStore {
  private readonly key: string;

  constructor(
    private readonly storage: OnboardingKeyValueStorage,
    publicUserId: string,
    private readonly timeoutMs = defaultStorageTimeoutMs,
  ) {
    if (!publicUserId.trim()) throw new Error('publicUserId is required');
    this.key = `ai-life-planner:user:${encodeURIComponent(publicUserId)}:onboarding:v2`;
  }

  async load(): Promise<OnboardingDraft | null> {
    const raw = await withStorageDeadline(
      this.storage.getItem(this.key),
      this.timeoutMs,
    );
    if (!raw) return null;
    try {
      const parsed = JSON.parse(raw) as OnboardingDraft;
      if (
        typeof parsed.narrative !== 'string' ||
        typeof parsed.clarificationAnswer !== 'string' ||
        typeof parsed.budgetConfirmed !== 'boolean' ||
        !isResourceBudget(parsed.resourceBudget)
      ) {
        await withStorageDeadline(
          this.storage.removeItem(this.key),
          this.timeoutMs,
        );
        return null;
      }
      return parsed;
    } catch {
      await withStorageDeadline(
        this.storage.removeItem(this.key),
        this.timeoutMs,
      );
      return null;
    }
  }

  save(draft: OnboardingDraft): Promise<void> {
    return withStorageDeadline(
      this.storage.setItem(this.key, JSON.stringify(draft)),
      this.timeoutMs,
    );
  }

  clear(): Promise<void> {
    return withStorageDeadline(
      this.storage.removeItem(this.key),
      this.timeoutMs,
    );
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value);
}

function isDayList(value: unknown): value is number[] {
  return (
    Array.isArray(value) &&
    value.every(
      (day) => Number.isInteger(day) && Number(day) >= 1 && Number(day) <= 7,
    )
  );
}

function isResourceBudget(value: unknown): value is ResourceBudget {
  if (!isRecord(value)) return false;
  const preferredWindows = value.preferredWindows;
  return (
    isFiniteNumber(value.weeklyAvailableMinutes) &&
    isDayList(value.availableDays) &&
    isFiniteNumber(value.minimumMinutes) &&
    isFiniteNumber(value.comfortableMinutes) &&
    isFiniteNumber(value.maximumMinutes) &&
    isDayList(value.freeEvenings) &&
    isRecord(preferredWindows) &&
    Object.values(preferredWindows).every((item) => typeof item === 'string') &&
    (value.moneyBudget === null || typeof value.moneyBudget === 'string') &&
    (value.conflictPriority === null ||
      typeof value.conflictPriority === 'string') &&
    isFiniteNumber(value.reservePercent)
  );
}
