import { describe, expect, it } from 'vitest';

import type { DaySnapshotDto } from '../../api/types';
import { decodeSnapshot, encodeSnapshot } from '../snapshotCodec';

const snapshot = {
  date: '2026-08-10',
  focus_text: 'Сначала — задача.',
  progress: { done: 0, total: 0 },
  scheduled_items: [],
  unscheduled_items: [],
  completed_items: [],
  current_item: null,
  completed_count: 0,
  total_count: 0,
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
    id: 0,
    date: '2026-08-10',
    summary: null,
    focus_text: 'Сначала — задача.',
    energy_level: null,
    budget_limit: null,
    status: 'draft',
    version: 0,
    items: [],
  },
  plan_version: 0,
} satisfies DaySnapshotDto;

describe('snapshot cache codec', () => {
  it('round-trips the versioned minimal cache envelope', () => {
    expect(decodeSnapshot(encodeSnapshot(snapshot))).toEqual(snapshot);
  });

  it('rejects malformed or unknown cache versions', () => {
    expect(decodeSnapshot('{"schemaVersion":2,"snapshot":{}}')).toBeNull();
    expect(decodeSnapshot('not json')).toBeNull();
  });

  it('rejects a cache envelope with corrupt nested DTOs', () => {
    expect(
      decodeSnapshot(
        JSON.stringify({
          schemaVersion: 1,
          snapshot: { ...snapshot, plan: { ...snapshot.plan, items: [null] } },
        }),
      ),
    ).toBeNull();
  });
});
