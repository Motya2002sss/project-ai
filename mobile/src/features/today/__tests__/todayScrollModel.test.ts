import { describe, expect, it } from 'vitest';

import {
  currentTimelineKey,
  timelineAutoScrollOffset,
} from '../todayScrollModel';
import type { TodayModel } from '../models';

function model(variant: 'current' | 'upcoming'): TodayModel {
  return {
    state: 'normal',
    dateLabel: 'Понедельник · 10 августа',
    focusText: '',
    dayRange: '07:30 — 00:00',
    completedCount: 0,
    totalCount: 1,
    progressLabel: 'Сегодня 0 из 1',
    progressFraction: 0,
    weekProgressLabel: null,
    directionTitles: [],
    planVersion: 2,
    unscheduled: [],
    rows: [
      {
        id: 42,
        taskId: 7,
        title: 'Длинная русская строка текущего действия',
        time: '19:30',
        endTime: '20:15',
        label: variant === 'current' ? 'Сейчас · до 20:15' : null,
        meta: null,
        goalContext: null,
        itemType: 'task',
        kind: 'action',
        variant,
        isCompletable: true,
      },
    ],
  };
}

describe('today timeline auto-scroll', () => {
  it('uses the authoritative current row and date as a stable scroll key', () => {
    expect(currentTimelineKey(model('current'))).toBe(
      'Понедельник · 10 августа:2:42',
    );
    expect(currentTimelineKey(model('upcoming'))).toBeNull();
  });

  it('allows a corrected plan version to scroll to the authoritative row again', () => {
    expect(currentTimelineKey(model('current'))).not.toBe(
      currentTimelineKey({ ...model('current'), planVersion: 3 }),
    );
  });

  it('places the current row below the top edge without negative offsets', () => {
    expect(timelineAutoScrollOffset(560)).toBe(536);
    expect(timelineAutoScrollOffset(12)).toBe(0);
  });
});
