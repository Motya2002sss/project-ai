export type OnboardingStep =
  | 'welcome'
  | 'apple_sign_in'
  | 'narrative'
  | 'processing'
  | 'clarification'
  | 'resource_budget'
  | 'preview'
  | 'applying'
  | 'completed';

export interface ResourceBudget {
  weeklyAvailableMinutes: number;
  availableDays: number[];
  minimumMinutes: number;
  comfortableMinutes: number;
  maximumMinutes: number;
  freeEvenings: number[];
  preferredWindows: Record<string, string>;
  moneyBudget: string | null;
  conflictPriority: string | null;
  reservePercent: number;
}

export const defaultResourceBudget: ResourceBudget = {
  weeklyAvailableMinutes: 600,
  availableDays: [1, 3, 5],
  minimumMinutes: 180,
  comfortableMinutes: 360,
  maximumMinutes: 480,
  freeEvenings: [1, 3],
  preferredWindows: {},
  moneyBudget: null,
  conflictPriority: null,
  reservePercent: 20,
};

export interface OnboardingStructuredSummary {
  workStart: string | null;
  workEnd: string | null;
  sleepTime: string | null;
  availableDays: number[];
  freeEvenings: number[];
  preferredWindows?: Record<string, string>;
}

export interface GoalAllocation {
  title: string;
  minutes: number;
  percent: number;
}

export interface OnboardingAllocation {
  reservedMinutes: number;
  reservePercent: number;
  allocatableMinutes: number;
  plannedMinutes: number;
  goals: GoalAllocation[];
}

export interface OnboardingClarification {
  id: string;
  question: string;
  allowsFreeText: boolean;
}

export interface OnboardingPreview {
  id: string;
  status: 'clarification_required' | 'ready' | 'applied';
  version: number;
  structuredSummary: OnboardingStructuredSummary;
  goalCandidates: string[];
  resourceBudget: ResourceBudget;
  allocation: OnboardingAllocation;
  clarification: OnboardingClarification | null;
}

export type OnboardingRequestOrigin = 'narrative' | 'resource_budget';

export interface PendingOnboardingRequest {
  requestId: string;
  origin: OnboardingRequestOrigin;
}

export interface OnboardingState {
  step: OnboardingStep;
  narrative: string;
  clarificationAnswer: string;
  resourceBudget: ResourceBudget;
  budgetConfirmed: boolean;
  preview: OnboardingPreview | null;
  pendingRequest: PendingOnboardingRequest | null;
  retryRequestId: string | null;
  retryOrigin: OnboardingRequestOrigin | null;
  error: { reason: 'offline' | 'server' | 'authentication'; message: string } | null;
}

export interface RecoverableOnboardingDraft {
  narrative: string;
  clarificationAnswer: string;
  resourceBudget: ResourceBudget;
  budgetConfirmed: boolean;
}

export type OnboardingAction =
  | { type: 'welcome/continued' }
  | { type: 'auth/succeeded' }
  | { type: 'narrative/changed'; value: string }
  | { type: 'clarification/changed'; value: string }
  | { type: 'clarification/continued' }
  | { type: 'draft/hydrated'; draft: RecoverableOnboardingDraft }
  | {
      type: 'server/restored';
      preview: OnboardingPreview;
      editing: boolean;
    }
  | { type: 'budget/changed'; value: Partial<ResourceBudget> }
  | {
      type: 'preview/submitted';
      requestId: string;
      origin: OnboardingRequestOrigin;
    }
  | {
      type: 'preview/received';
      requestId: string;
      preview: OnboardingPreview;
    }
  | {
      type: 'request/failed';
      requestId: string;
      reason: 'offline' | 'server' | 'authentication';
      message: string;
    }
  | { type: 'request/retried' }
  | { type: 'preview/editRequested' }
  | { type: 'apply/submitted' }
  | { type: 'apply/succeeded'; preview: OnboardingPreview }
  | { type: 'apply/failed'; message: string }
  | { type: 'navigation/back' }
  | { type: 'app/backgrounded' };

export function createInitialOnboardingState(
  step: OnboardingStep = 'welcome',
): OnboardingState {
  return {
    step,
    narrative: '',
    clarificationAnswer: '',
    resourceBudget: { ...defaultResourceBudget },
    budgetConfirmed: false,
    preview: null,
    pendingRequest: null,
    retryRequestId: null,
    retryOrigin: null,
    error: null,
  };
}

function normalizedPreview(preview: OnboardingPreview): OnboardingPreview {
  const allowedTitles = preview.goalCandidates.slice(0, 3);
  const allowedKeys = new Set(
    allowedTitles.map((title) => title.toLocaleLowerCase()),
  );
  return {
    ...preview,
    goalCandidates: allowedTitles,
    allocation: {
      ...preview.allocation,
      goals: preview.allocation.goals
        .filter((goal) => allowedKeys.has(goal.title.toLocaleLowerCase()))
        .slice(0, 3),
    },
  };
}

export function canPresentPaywall(state: OnboardingState): boolean {
  return state.step === 'preview' || state.step === 'applying' || state.step === 'completed';
}

export function previewIdentityForMutation(
  preview: OnboardingPreview | null,
): { previewId?: string; expectedVersion?: number } {
  if (!preview || preview.status === 'applied') return {};
  return { previewId: preview.id, expectedVersion: preview.version };
}

export function validateResourceBudget(budget: ResourceBudget): string | null {
  if (budget.weeklyAvailableMinutes < 30) {
    return 'Укажите хотя бы 30 минут доступного времени в неделю.';
  }
  if (budget.availableDays.length === 0) {
    return 'Выберите хотя бы один доступный день.';
  }
  if (
    budget.freeEvenings.some(
      (day) => !budget.availableDays.includes(day),
    )
  ) {
    return 'Свободные вечера должны входить в доступные дни.';
  }
  if (
    budget.minimumMinutes < 0 ||
    budget.minimumMinutes > budget.comfortableMinutes ||
    budget.comfortableMinutes > budget.maximumMinutes
  ) {
    return 'Минимальный, комфортный и максимальный объём должны идти по возрастанию.';
  }
  const allocatable = Math.floor(
    (budget.weeklyAvailableMinutes * (100 - budget.reservePercent)) / 100,
  );
  if (budget.maximumMinutes > allocatable) {
    return `Максимальный объём должен помещаться с учётом резерва ${budget.reservePercent}%.`;
  }
  return null;
}

export function onboardingReducer(
  state: OnboardingState,
  action: OnboardingAction,
): OnboardingState {
  switch (action.type) {
    case 'welcome/continued':
      return state.step === 'welcome'
        ? { ...state, step: 'apple_sign_in', error: null }
        : state;
    case 'auth/succeeded':
      return state.step === 'apple_sign_in' || state.step === 'welcome'
        ? { ...state, step: 'narrative', error: null }
        : state;
    case 'narrative/changed':
      return { ...state, narrative: action.value, error: null };
    case 'clarification/changed':
      return { ...state, clarificationAnswer: action.value, error: null };
    case 'clarification/continued':
      if (state.step !== 'clarification' || !state.clarificationAnswer.trim()) {
        return state;
      }
      return { ...state, step: 'resource_budget', error: null };
    case 'draft/hydrated':
      return {
        ...state,
        narrative: action.draft.narrative,
        clarificationAnswer: action.draft.clarificationAnswer,
        resourceBudget: action.draft.resourceBudget,
        budgetConfirmed: action.draft.budgetConfirmed,
      };
    case 'server/restored': {
      const preview = normalizedPreview(action.preview);
      const restoredStep: OnboardingStep = action.editing
        ? 'narrative'
        : preview.status === 'applied'
          ? 'completed'
          : preview.status === 'clarification_required'
            ? 'clarification'
            : 'preview';
      return {
        ...state,
        step: restoredStep,
        preview,
        resourceBudget: preview.resourceBudget,
        budgetConfirmed: preview.status !== 'clarification_required',
        error: null,
      };
    }
    case 'budget/changed':
      return {
        ...state,
        resourceBudget: { ...state.resourceBudget, ...action.value },
        error: null,
      };
    case 'preview/submitted':
      if (state.step === 'processing' || state.step === 'applying') return state;
      return {
        ...state,
        step: 'processing',
        pendingRequest: {
          requestId: action.requestId,
          origin: action.origin,
        },
        retryRequestId: null,
        retryOrigin: null,
        error: null,
      };
    case 'preview/received': {
      if (state.pendingRequest?.requestId !== action.requestId) return state;
      const preview = normalizedPreview(action.preview);
      if (preview.status === 'applied') {
        return {
          ...state,
          step: 'completed',
          preview,
          budgetConfirmed: true,
          pendingRequest: null,
          error: null,
        };
      }
      if (preview.status === 'clarification_required') {
        return {
          ...state,
          step: 'clarification',
          preview,
          pendingRequest: null,
          error: null,
        };
      }
      const budgetConfirmed =
        state.budgetConfirmed || state.pendingRequest.origin === 'resource_budget';
      return {
        ...state,
        step: budgetConfirmed ? 'preview' : 'resource_budget',
        preview,
        resourceBudget: preview.resourceBudget,
        budgetConfirmed,
        pendingRequest: null,
        error: null,
      };
    }
    case 'request/failed':
      if (state.pendingRequest?.requestId !== action.requestId) return state;
      return {
        ...state,
        step:
          state.pendingRequest.origin === 'resource_budget'
            ? 'resource_budget'
            : 'narrative',
        retryRequestId: action.requestId,
        retryOrigin: state.pendingRequest.origin,
        pendingRequest: null,
        error: { reason: action.reason, message: action.message },
      };
    case 'request/retried':
      if (!state.retryRequestId || !state.retryOrigin) return state;
      return {
        ...state,
        step: 'processing',
        pendingRequest: {
          requestId: state.retryRequestId,
          origin: state.retryOrigin,
        },
        error: null,
      };
    case 'preview/editRequested':
      if (state.step !== 'preview') return state;
      return { ...state, step: 'narrative', error: null };
    case 'apply/submitted':
      if (state.step !== 'preview') return state;
      return { ...state, step: 'applying', error: null };
    case 'apply/succeeded':
      if (state.step !== 'applying') return state;
      return {
        ...state,
        step: 'completed',
        preview: normalizedPreview(action.preview),
        error: null,
      };
    case 'apply/failed':
      if (state.step !== 'applying') return state;
      return {
        ...state,
        step: 'preview',
        error: { reason: 'server', message: action.message },
      };
    case 'navigation/back':
      if (state.step === 'apple_sign_in') return { ...state, step: 'welcome' };
      if (state.step === 'narrative') return { ...state, step: 'apple_sign_in' };
      if (state.step === 'clarification') return { ...state, step: 'narrative' };
      if (state.step === 'resource_budget') {
        return {
          ...state,
          step: state.preview?.clarification ? 'clarification' : 'narrative',
        };
      }
      if (state.step === 'preview') return { ...state, step: 'narrative' };
      return state;
    case 'app/backgrounded':
      return state;
    default:
      return state;
  }
}
