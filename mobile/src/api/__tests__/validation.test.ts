import { describe, expect, it } from 'vitest';

import { normalDaySnapshot } from '../../dev/fixtures/daySnapshots';
import {
  isDaySnapshotDto,
  isMobileActionResponseDto,
  isMobileTaskMutationResponseDto,
} from '../validation';

describe('mobile API runtime validation', () => {
  it('accepts a complete canonical day snapshot', () => {
    expect(isDaySnapshotDto(normalDaySnapshot)).toBe(true);
  });

  it('rejects nested snapshot drift instead of trusting top-level arrays', () => {
    expect(
      isDaySnapshotDto({
        ...normalDaySnapshot,
        plan: { ...normalDaySnapshot.plan, items: [null] },
      }),
    ).toBe(false);
  });

  it('validates the optional task-to-goal link used by Today context', () => {
    const linked = {
      ...normalDaySnapshot,
      tasks: normalDaySnapshot.tasks.map((task, index) => ({
        ...task,
        goal_id: index === 0 ? 42 : null,
      })),
    };

    expect(isDaySnapshotDto(linked)).toBe(true);
    expect(
      isDaySnapshotDto({
        ...linked,
        tasks: [{ ...linked.tasks[0], goal_id: 'another-user-goal' }],
      }),
    ).toBe(false);
  });

  it('validates snapshot time and weekly progress when the server provides them', () => {
    expect(
      isDaySnapshotDto({
        ...normalDaySnapshot,
        as_of: '2026-08-11T19:45:00+03:00',
        week_progress: { done: 3, total: 7 },
      }),
    ).toBe(true);
    expect(
      isDaySnapshotDto({ ...normalDaySnapshot, as_of: 42 }),
    ).toBe(false);
    expect(
      isDaySnapshotDto({
        ...normalDaySnapshot,
        week_progress: { done: '3', total: 7 },
      }),
    ).toBe(false);
  });

  it('validates action and task mutation envelopes including nested snapshots', () => {
    const action = {
      request_id: 'capture-1',
      status: 'applied',
      reason: null,
      reply_text: 'Готово.',
      retryable: false,
      plan_diff: { created_task_ids: [1] },
      clarification: null,
      confirmation: null,
      conflict: null,
      day_snapshot: normalDaySnapshot,
    };
    const taskMutation = {
      status: 'applied',
      task: normalDaySnapshot.tasks[0],
      plan_diff: { completed_task_ids: [1] },
      day_snapshot: normalDaySnapshot,
    };

    expect(isMobileActionResponseDto(action)).toBe(true);
    expect(isMobileTaskMutationResponseDto(taskMutation)).toBe(true);
    expect(
      isMobileActionResponseDto({
        ...action,
        day_snapshot: { ...normalDaySnapshot, tasks: [null] },
      }),
    ).toBe(false);
  });
});
