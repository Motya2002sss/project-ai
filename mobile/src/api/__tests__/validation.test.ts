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
