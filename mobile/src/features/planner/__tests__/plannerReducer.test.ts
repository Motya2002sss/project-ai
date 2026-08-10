import { describe, expect, it } from 'vitest';

import type { DaySnapshotDto } from '../../../api/types';
import {
  initialPlannerState,
  plannerReducer,
  retryDescriptor,
  type PlannerAction,
} from '../plannerReducer';

const snapshot = {
  date: '2026-08-10',
  focus_text: 'Сначала — Подготовить презентацию.',
  progress: { done: 0, total: 1 },
  scheduled_items: [],
  unscheduled_items: [],
  completed_items: [],
  current_item: null,
  completed_count: 0,
  total_count: 1,
  day_context: {
    energy_level: null,
    budget_limit: null,
    work_override_mode: null,
    work_start_time: null,
    work_end_time: null,
  },
  tasks: [],
  goals: [],
  routines: [],
  plan: {
    id: 1,
    date: '2026-08-10',
    summary: null,
    focus_text: 'Сначала — Подготовить презентацию.',
    energy_level: null,
    budget_limit: null,
    status: 'active',
    version: 1,
    items: [],
  },
  plan_version: 1,
} satisfies DaySnapshotDto;

function reduce(action: PlannerAction) {
  return plannerReducer(initialPlannerState, action);
}

describe('plannerReducer capture lifecycle', () => {
  it('starts exactly one capture submit while a request is active', () => {
    const start: PlannerAction = {
      type: 'capture/requestStarted',
      requestId: 'capture-1',
      operation: { kind: 'capture', text: 'Сегодня задержусь на работе до 20' },
    };
    const submitting = reduce(start);

    expect(submitting.capture.status).toBe('submitting');
    expect(plannerReducer(submitting, { ...start, requestId: 'capture-2' })).toBe(
      submitting,
    );
  });

  it('ignores a response from a stale request', () => {
    const submitting = reduce({
      type: 'capture/requestStarted',
      requestId: 'current-request',
      operation: { kind: 'capture', text: 'Изменение' },
    });

    const result = plannerReducer(submitting, {
      type: 'capture/responseReceived',
      requestId: 'stale-request',
      response: {
        request_id: 'stale-request',
        status: 'applied',
        reason: null,
        reply_text: 'План обновлён.',
        retryable: false,
        plan_diff: {},
        clarification: null,
        confirmation: null,
        conflict: null,
        day_snapshot: snapshot,
      },
      explicitCancel: false,
    });

    expect(result).toBe(submitting);
  });

  it('atomically replaces the snapshot and clears the draft after applied', () => {
    const editing = plannerReducer(
      { ...initialPlannerState, draft: 'Изменение' },
      { type: 'capture/requestStarted', requestId: 'capture-1', operation: { kind: 'capture', text: 'Изменение' } },
    );

    const result = plannerReducer(editing, {
      type: 'capture/responseReceived',
      requestId: 'capture-1',
      response: {
        request_id: 'capture-1',
        status: 'applied',
        reason: null,
        reply_text: 'План обновлён.',
        retryable: false,
        plan_diff: { availability_change: 'Работа → до 20:00' },
        clarification: null,
        confirmation: null,
        conflict: null,
        day_snapshot: snapshot,
      },
      explicitCancel: false,
    });

    expect(result.today.snapshot).toBe(snapshot);
    expect(result.draft).toBe('');
    expect(result.capture.status).toBe('success');
  });

  it('keeps the draft and retry descriptor after a recoverable error', () => {
    const operation = { kind: 'capture' as const, text: 'Изменение' };
    const submitting = plannerReducer(
      { ...initialPlannerState, draft: operation.text },
      { type: 'capture/requestStarted', requestId: 'capture-1', operation },
    );

    const result = plannerReducer(submitting, {
      type: 'capture/requestFailed',
      requestId: 'capture-1',
      message: 'Текст сохранён.',
      retryable: true,
    });

    expect(result.draft).toBe(operation.text);
    expect(result.capture).toEqual({
      status: 'error',
      message: 'Текст сохранён.',
      retryable: true,
      requestId: 'capture-1',
      operation,
    });
    expect(retryDescriptor(result.capture)).toEqual({
      requestId: 'capture-1',
      operation,
      explicitCancel: false,
    });
  });

  it('marks only the matching active request as slow', () => {
    const submitting = reduce({
      type: 'capture/requestStarted',
      requestId: 'capture-1',
      operation: { kind: 'capture', text: 'Изменение' },
    });

    expect(
      plannerReducer(submitting, {
        type: 'capture/requestSlow',
        requestId: 'stale',
      }),
    ).toBe(submitting);
    expect(
      plannerReducer(submitting, {
        type: 'capture/requestSlow',
        requestId: 'capture-1',
      }).capture,
    ).toMatchObject({ status: 'submitting', slow: true });
  });

  it('retries an explicit interaction cancel with the same semantic flag', () => {
    const operation = {
      kind: 'interaction' as const,
      interactionId: 'interaction-1',
      optionId: 'cancel',
      text: 'Оставить как есть',
    };
    const submitting = reduce({
      type: 'capture/requestStarted',
      requestId: 'cancel-1',
      operation,
    });
    const failed = plannerReducer(submitting, {
      type: 'capture/requestFailed',
      requestId: 'cancel-1',
      message: 'Повторить',
      retryable: true,
    });

    expect(retryDescriptor(failed.capture)).toEqual({
      requestId: 'cancel-1',
      operation,
      explicitCancel: true,
    });
  });

  it.each([
    ['clarification_required', 'clarification'],
    ['confirmation_required', 'confirmation'],
    ['conflict', 'conflict'],
  ] as const)('maps %s to the %s terminal state', (status, expected) => {
    const submitting = reduce({
      type: 'capture/requestStarted',
      requestId: 'capture-1',
      operation: { kind: 'capture', text: 'Неоднозначно' },
    });
    const interaction = {
      id: 'interaction-1',
      options: [],
      expires_at: '2026-08-10T20:00:00Z',
    };

    const result = plannerReducer(submitting, {
      type: 'capture/responseReceived',
      requestId: 'capture-1',
      explicitCancel: false,
      response: {
        request_id: 'capture-1',
        status,
        reason: null,
        reply_text: 'Нужно уточнение.',
        retryable: false,
        plan_diff: {},
        clarification:
          status === 'clarification_required'
            ? {
                ...interaction,
                question: 'Что именно добавить?',
                free_text_allowed: true,
              }
            : null,
        confirmation:
          status === 'confirmation_required'
            ? {
                ...interaction,
                title: 'Применить изменение?',
                summary: 'Задача → завтра',
                changes: {},
                base_plan_version: 1,
              }
            : null,
        conflict:
          status === 'conflict'
            ? {
                ...interaction,
                title: 'Время занято',
                message: '19:00 уже занят созвоном.',
              }
            : null,
        day_snapshot: snapshot,
      },
    });

    expect(result.capture.status).toBe(expected);
    expect(result.draft).toBe('');
  });

  it('continues an interaction with its own request id and applies its snapshot', () => {
    const submitting = plannerReducer(
      { ...initialPlannerState, draft: 'добавь бжу' },
      {
        type: 'capture/requestStarted',
        requestId: 'answer-1',
        operation: {
          kind: 'interaction',
          interactionId: 'interaction-1',
          optionId: 'one_time',
          text: 'разовая задача',
        },
      },
    );

    const result = plannerReducer(submitting, {
      type: 'capture/responseReceived',
      requestId: 'answer-1',
      explicitCancel: false,
      response: {
        request_id: 'answer-1',
        status: 'applied',
        reason: null,
        reply_text: 'Добавлено.',
        retryable: false,
        plan_diff: { created_task_ids: [1] },
        clarification: null,
        confirmation: null,
        conflict: null,
        day_snapshot: { ...snapshot, plan_version: 2 },
      },
    });

    expect(result.today.snapshot?.plan_version).toBe(2);
    expect(result.draft).toBe('');
  });

  it('clears a retained draft only after an explicit server-side cancel response', () => {
    const submitting = plannerReducer(
      { ...initialPlannerState, draft: 'Не применять' },
      {
        type: 'capture/requestStarted',
        requestId: 'cancel-1',
        operation: {
          kind: 'interaction',
          interactionId: 'interaction-1',
          optionId: 'cancel',
          text: 'Оставить как есть',
        },
      },
    );

    const result = plannerReducer(submitting, {
      type: 'capture/responseReceived',
      requestId: 'cancel-1',
      explicitCancel: true,
      response: {
        request_id: 'cancel-1',
        status: 'no_change',
        reason: null,
        reply_text: 'Оставил как есть.',
        retryable: false,
        plan_diff: {},
        clarification: null,
        confirmation: null,
        conflict: null,
        day_snapshot: snapshot,
      },
    });

    expect(result.draft).toBe('');
    expect(result.capture).toMatchObject({ status: 'success', didChange: false });
  });
});

describe('plannerReducer cached-first ordering', () => {
  it('preserves an offline error when cache hydration finishes after the failed refresh', () => {
    const refreshing = reduce({ type: 'today/refreshStarted' });
    const failed = plannerReducer(refreshing, {
      type: 'today/refreshFailed',
      message: 'Нет соединения.',
      retryable: true,
    });
    const hydrated = plannerReducer(failed, {
      type: 'today/cacheLoaded',
      snapshot,
    });

    expect(hydrated.today).toMatchObject({
      snapshot,
      source: 'cache',
      refreshing: false,
      error: { message: 'Нет соединения.', retryable: true },
    });
  });

  it('keeps the refresh indicator while cache hydration wins the first race', () => {
    const refreshing = reduce({ type: 'today/refreshStarted' });
    const hydrated = plannerReducer(refreshing, {
      type: 'today/cacheLoaded',
      snapshot,
    });

    expect(hydrated.today).toMatchObject({
      snapshot,
      source: 'cache',
      refreshing: true,
      error: null,
    });
  });
});

describe('plannerReducer task completion', () => {
  it('adds one optimistic status and blocks a duplicate tap', () => {
    const start: PlannerAction = {
      type: 'task/requestStarted',
      taskId: 42,
      operationId: 'task-1',
      targetStatus: 'done',
    };
    const pending = reduce(start);

    expect(pending.completion.pendingByTask[42]).toEqual({
      operationId: 'task-1',
      targetStatus: 'done',
    });
    expect(
      plannerReducer(pending, { ...start, operationId: 'task-duplicate' }),
    ).toBe(pending);
  });

  it('replaces the snapshot after confirmed completion', () => {
    const pending = reduce({
      type: 'task/requestStarted',
      taskId: 42,
      operationId: 'task-1',
      targetStatus: 'done',
    });
    const serverSnapshot = { ...snapshot, plan_version: 2 };

    const result = plannerReducer(pending, {
      type: 'task/requestSucceeded',
      taskId: 42,
      operationId: 'task-1',
      snapshot: serverSnapshot,
    });

    expect(result.today.snapshot).toBe(serverSnapshot);
    expect(result.completion.pendingByTask[42]).toBeUndefined();
  });

  it('rolls back optimistic status on failure and ignores a stale failure', () => {
    const pending = reduce({
      type: 'task/requestStarted',
      taskId: 42,
      operationId: 'task-1',
      targetStatus: 'done',
    });
    const stale = plannerReducer(pending, {
      type: 'task/requestFailed',
      taskId: 42,
      operationId: 'stale-task',
      message: 'Не удалось сохранить. Повторить',
      retryable: true,
    });
    const failed = plannerReducer(pending, {
      type: 'task/requestFailed',
      taskId: 42,
      operationId: 'task-1',
      message: 'Не удалось сохранить. Повторить',
      retryable: true,
    });

    expect(stale).toBe(pending);
    expect(failed.completion.pendingByTask[42]).toBeUndefined();
    expect(failed.completion.error).toEqual({
      taskId: 42,
      targetStatus: 'done',
      message: 'Не удалось сохранить. Повторить',
      retryable: true,
    });
  });
});
