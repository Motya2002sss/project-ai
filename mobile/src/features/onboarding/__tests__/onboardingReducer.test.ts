import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  canPresentPaywall,
  createInitialOnboardingState,
  defaultResourceBudget,
  onboardingReducer,
  previewIdentityForMutation,
  type OnboardingState,
  validateResourceBudget,
  type OnboardingPreview,
} from '../onboardingReducer';
import {
  OnboardingDraftStore,
  type OnboardingKeyValueStorage,
} from '../onboardingDraftStorage';
import { MobileCache } from '../../../storage/cache';

afterEach(() => {
  vi.useRealTimers();
});

const clarificationPreview: OnboardingPreview = {
  id: 'preview-1',
  status: 'clarification_required',
  version: 1,
  structuredSummary: {
    workStart: '10:00',
    workEnd: '19:00',
    sleepTime: '00:00',
    availableDays: [1, 3, 5],
    freeEvenings: [1, 3],
  },
  goalCandidates: [],
  resourceBudget: defaultResourceBudget,
  allocation: {
    reservedMinutes: 120,
    reservePercent: 20,
    allocatableMinutes: 480,
    plannedMinutes: 0,
    goals: [],
  },
  clarification: {
    id: 'primary_goals',
    question: 'Какие результаты вы хотите получить в первую очередь?',
    allowsFreeText: true,
  },
};

const readyPreview: OnboardingPreview = {
  ...clarificationPreview,
  status: 'ready',
  version: 2,
  goalCandidates: [
    'Стать senior backend-разработчиком',
    'Набрать вес до 78 кг',
    'Сесть на шпагат',
  ],
  allocation: {
    ...clarificationPreview.allocation,
    plannedMinutes: 360,
    goals: [
      {
        title: 'Стать senior backend-разработчиком',
        minutes: 120,
        percent: 34,
      },
      { title: 'Набрать вес до 78 кг', minutes: 120, percent: 33 },
      { title: 'Сесть на шпагат', minutes: 120, percent: 33 },
    ],
  },
  clarification: null,
};

describe('onboardingReducer', () => {
  it('moves from welcome through Apple, narrative, clarification, budget, preview and applied Today', () => {
    let state = createInitialOnboardingState();

    expect(state.step).toBe('welcome');
    expect(canPresentPaywall(state)).toBe(false);

    state = onboardingReducer(state, { type: 'welcome/continued' });
    expect(state.step).toBe('apple_sign_in');

    state = onboardingReducer(state, { type: 'auth/succeeded' });
    expect(state.step).toBe('narrative');

    state = onboardingReducer(state, {
      type: 'narrative/changed',
      value:
        'Работаю с 10 до 19, дорога по часу. Ложусь около полуночи.',
    });
    state = onboardingReducer(state, {
      type: 'preview/submitted',
      requestId: 'request-1',
      origin: 'narrative',
    });
    expect(state.step).toBe('processing');

    state = onboardingReducer(state, {
      type: 'preview/received',
      requestId: 'request-1',
      preview: clarificationPreview,
    });
    expect(state.step).toBe('clarification');

    state = onboardingReducer(state, {
      type: 'clarification/changed',
      value:
        'Хочу стать senior backend-разработчиком, набрать вес и сесть на шпагат',
    });
    state = onboardingReducer(state, { type: 'clarification/continued' });
    expect(state.step).toBe('resource_budget');

    state = onboardingReducer(state, {
      type: 'preview/submitted',
      requestId: 'request-2',
      origin: 'resource_budget',
    });
    state = onboardingReducer(state, {
      type: 'preview/received',
      requestId: 'request-2',
      preview: readyPreview,
    });
    expect(state.step).toBe('preview');
    expect(canPresentPaywall(state)).toBe(true);

    state = onboardingReducer(state, { type: 'apply/submitted' });
    expect(state.step).toBe('applying');
    state = onboardingReducer(state, {
      type: 'apply/succeeded',
      preview: { ...readyPreview, status: 'applied' },
    });
    expect(state.step).toBe('completed');
  });

  it('retains the narrative when the app backgrounds and after an offline failure', () => {
    let state = createInitialOnboardingState('narrative');
    state = onboardingReducer(state, {
      type: 'narrative/changed',
      value: 'Очень длинный русский рассказ о работе, семье и целях',
    });
    state = onboardingReducer(state, { type: 'app/backgrounded' });
    state = onboardingReducer(state, {
      type: 'preview/submitted',
      requestId: 'stable-request',
      origin: 'narrative',
    });
    state = onboardingReducer(state, {
      type: 'request/failed',
      requestId: 'stable-request',
      reason: 'offline',
      message: 'Нет связи. Рассказ сохранён.',
    });

    expect(state.step).toBe('narrative');
    expect(state.narrative).toContain('семье и целях');
    expect(state.retryRequestId).toBe('stable-request');
    expect(state.error).toMatchObject({ reason: 'offline' });

    state = onboardingReducer(state, { type: 'request/retried' });
    expect(state.step).toBe('processing');
    expect(state.pendingRequest?.requestId).toBe('stable-request');
  });

  it('ignores duplicate submits while the first request or apply is in flight', () => {
    const processing = onboardingReducer(
      {
        ...createInitialOnboardingState('narrative'),
        narrative: 'Хочу развиваться в backend-разработке',
      },
      {
        type: 'preview/submitted',
        requestId: 'first',
        origin: 'narrative',
      },
    );

    expect(
      onboardingReducer(processing, {
        type: 'preview/submitted',
        requestId: 'duplicate',
        origin: 'narrative',
      }),
    ).toBe(processing);

    const applying = onboardingReducer(
      {
        ...processing,
        step: 'preview',
        preview: readyPreview,
        pendingRequest: null,
      },
      { type: 'apply/submitted' },
    );
    expect(onboardingReducer(applying, { type: 'apply/submitted' })).toBe(
      applying,
    );
  });

  it('supports back and correction without losing the server preview version', () => {
    let state: OnboardingState = {
      ...createInitialOnboardingState('preview'),
      narrative: 'Первоначальный рассказ',
      preview: readyPreview,
      budgetConfirmed: true,
    };

    state = onboardingReducer(state, { type: 'preview/editRequested' });
    expect(state).toMatchObject({
      step: 'narrative',
      narrative: 'Первоначальный рассказ',
      preview: { id: 'preview-1', version: 2 },
      budgetConfirmed: true,
    });

    state = onboardingReducer(state, { type: 'navigation/back' });
    expect(state.step).toBe('apple_sign_in');
  });

  it('never presents more than three active goal candidates from a response', () => {
    const processing = onboardingReducer(
      {
        ...createInitialOnboardingState('narrative'),
        narrative: 'Четыре направления',
        budgetConfirmed: true,
      },
      {
        type: 'preview/submitted',
        requestId: 'request-cap',
        origin: 'narrative',
      },
    );
    const state = onboardingReducer(processing, {
      type: 'preview/received',
      requestId: 'request-cap',
      preview: {
        ...readyPreview,
        goalCandidates: ['Первая', 'Вторая', 'Третья', 'Четвёртая'],
      },
    });

    expect(state.preview?.goalCandidates).toEqual([
      'Первая',
      'Вторая',
      'Третья',
    ]);
  });

  it('keeps paywall unavailable before a personalized preview exists', () => {
    const steps = [
      createInitialOnboardingState(),
      createInitialOnboardingState('apple_sign_in'),
      createInitialOnboardingState('narrative'),
      createInitialOnboardingState('resource_budget'),
    ];

    expect(steps.every((state) => !canPresentPaywall(state))).toBe(true);
  });

  it('restores a user-scoped draft and an authoritative preview after relaunch', () => {
    let state = createInitialOnboardingState('narrative');
    state = onboardingReducer(state, {
      type: 'draft/hydrated',
      draft: {
        narrative: 'Сохранённый рассказ после фонового режима',
        clarificationAnswer: 'Три цели',
        resourceBudget: {
          ...defaultResourceBudget,
          weeklyAvailableMinutes: 720,
        },
        budgetConfirmed: true,
      },
    });
    state = onboardingReducer(state, {
      type: 'server/restored',
      preview: readyPreview,
      editing: false,
    });

    expect(state).toMatchObject({
      step: 'preview',
      narrative: 'Сохранённый рассказ после фонового режима',
      preview: { id: 'preview-1', version: 2 },
      budgetConfirmed: true,
    });

    state = onboardingReducer(state, {
      type: 'server/restored',
      preview: readyPreview,
      editing: true,
    });
    expect(state.step).toBe('narrative');
  });

  it('opens an applied onboarding as a fresh correction without mutating it', () => {
    const appliedPreview: OnboardingPreview = {
      ...readyPreview,
      status: 'applied',
      version: 3,
    };
    const state = onboardingReducer(createInitialOnboardingState('narrative'), {
      type: 'server/restored',
      preview: appliedPreview,
      editing: true,
    });

    expect(state).toMatchObject({
      step: 'narrative',
      preview: { id: 'preview-1', status: 'applied', version: 3 },
      resourceBudget: appliedPreview.resourceBudget,
    });
    expect(previewIdentityForMutation(state.preview)).toEqual({});
    expect(previewIdentityForMutation(readyPreview)).toEqual({
      previewId: 'preview-1',
      expectedVersion: 2,
    });
  });

  it('updates a real resource budget and rejects impossible capacity', () => {
    let state = createInitialOnboardingState('resource_budget');
    state = onboardingReducer(state, {
      type: 'budget/changed',
      value: {
        weeklyAvailableMinutes: 480,
        availableDays: [2, 4],
        freeEvenings: [2, 4],
        minimumMinutes: 120,
        comfortableMinutes: 240,
        maximumMinutes: 360,
      },
    });

    expect(state.resourceBudget).toMatchObject({
      weeklyAvailableMinutes: 480,
      availableDays: [2, 4],
      comfortableMinutes: 240,
    });
    expect(validateResourceBudget(state.resourceBudget)).toBeNull();
    expect(
      validateResourceBudget({
        ...state.resourceBudget,
        maximumMinutes: 420,
      }),
    ).toBe('Максимальный объём должен помещаться с учётом резерва 20%.');
  });

  it('keeps the authoritative preview visible when apply fails', () => {
    let state: OnboardingState = {
      ...createInitialOnboardingState('preview'),
      preview: readyPreview,
      budgetConfirmed: true,
    };
    state = onboardingReducer(state, { type: 'apply/submitted' });
    state = onboardingReducer(state, {
      type: 'apply/failed',
      message: 'Не удалось начать. Попробуйте ещё раз.',
    });

    expect(state.step).toBe('preview');
    expect(state.preview?.id).toBe('preview-1');
    expect(state.error?.message).toContain('Попробуйте');
  });
});

class MemoryStorage implements OnboardingKeyValueStorage {
  readonly values = new Map<string, string>();

  async getItem(key: string) {
    return this.values.get(key) ?? null;
  }

  async setItem(key: string, value: string) {
    this.values.set(key, value);
  }

  async removeItem(key: string) {
    this.values.delete(key);
  }
}

describe('OnboardingDraftStore', () => {
  it('rejects and removes a corrupt or old resource budget shape', async () => {
    const storage = new MemoryStorage();
    const drafts = new OnboardingDraftStore(storage, 'corrupt-user');
    storage.values.set(
      'ai-life-planner:user:corrupt-user:onboarding:v2',
      JSON.stringify({
        narrative: 'Старый рассказ',
        clarificationAnswer: '',
        budgetConfirmed: false,
        resourceBudget: { weeklyAvailableMinutes: 600 },
      }),
    );

    await expect(drafts.load()).resolves.toBeNull();
    expect(storage.values.size).toBe(0);
  });

  it('namespaces recoverable drafts by public user and clears only that user', async () => {
    const storage = new MemoryStorage();
    const first = new OnboardingDraftStore(storage, 'user-one');
    const second = new OnboardingDraftStore(storage, 'user-two');
    const draft = {
      narrative: 'Работаю с десяти и хочу три раза ходить в зал',
      clarificationAnswer: '',
      resourceBudget: defaultResourceBudget,
      budgetConfirmed: false,
    };

    await first.save(draft);
    await second.save({ ...draft, narrative: 'Другой пользователь' });
    await first.clear();

    await expect(first.load()).resolves.toBeNull();
    await expect(second.load()).resolves.toMatchObject({
      narrative: 'Другой пользователь',
    });
    expect([...storage.values.keys()]).toEqual([
      'ai-life-planner:user:user-two:onboarding:v2',
    ]);
  });

  it('is removed by the canonical user-data cleanup used on logout and deletion', async () => {
    const storage = new MemoryStorage();
    const drafts = new OnboardingDraftStore(storage, 'private-user');
    const cache = new MobileCache(storage, 'private-user');

    await drafts.save({
      narrative: 'Чувствительный рассказ о распорядке',
      clarificationAnswer: 'Личные цели',
      resourceBudget: defaultResourceBudget,
      budgetConfirmed: false,
    });
    await cache.clearUserData();

    await expect(drafts.load()).resolves.toBeNull();
  });

  it('bounds a never-settling draft read without purging the recoverable draft', async () => {
    vi.useFakeTimers();
    const removeItem = vi.fn(async () => undefined);
    const drafts = new OnboardingDraftStore(
      {
        getItem: () => new Promise<string | null>(() => undefined),
        setItem: async () => undefined,
        removeItem,
      },
      'private-user',
      25,
    );
    const load = drafts.load().catch((error: unknown) => error);

    await vi.advanceTimersByTimeAsync(25);

    await expect(load).resolves.toBeInstanceOf(Error);
    expect(removeItem).not.toHaveBeenCalled();
  });
});
