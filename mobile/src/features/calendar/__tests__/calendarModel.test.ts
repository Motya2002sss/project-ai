import { describe, expect, it } from 'vitest';

import { buildCalendarScreenModel, mondayForDate, monthForDate } from '../calendarModel';
import {
  calendarDayFixture,
  calendarMonthFixture,
  calendarWeekFixture,
} from './calendarFixtures';

describe('authoritative Calendar screen model', () => {
  it('builds a seven-day thread and selected-day rows without local scheduling', () => {
    const model = buildCalendarScreenModel({
      mode: 'week',
      selectedDate: '2026-08-12',
      width: 390,
      day: calendarDayFixture,
      week: calendarWeekFixture,
      month: calendarMonthFixture,
      status: 'ready',
      source: 'network',
    });

    expect(model.state).toBe('ready');
    if (model.state !== 'ready') throw new Error('expected ready');
    expect(model.compact).toBe(false);
    expect(model.weekDays).toHaveLength(7);
    expect(model.weekDays[2]).toMatchObject({ label: 'СР', day: '12', selected: true });
    expect(model.selectedItems.map((item) => item.title)).toEqual([
      calendarDayFixture.items[0]!.title,
      'Занято',
      calendarDayFixture.items[1]!.title,
      'Свободно',
    ]);
    expect(model.selectedItems[0]?.timeLabel).toBe('10:00 — 11:00');
    expect(model.selectedItems[1]?.kindLabel).toBe('Внешний календарь');
    expect(model.selectedItems[2]?.kindLabel).toBe('Восстановление');
    expect(model.selectedItems[3]?.kindLabel).toBe('Свободное окно');
    expect(model.actions).toEqual([]);
  });

  it('keeps long Russian copy, compact widths, empty and cached states truthful', () => {
    const compact = buildCalendarScreenModel({
      mode: 'week',
      selectedDate: '2026-08-10',
      width: 360,
      day: null,
      week: calendarWeekFixture,
      month: null,
      status: 'error',
      source: 'cache',
      errorMessage: 'Нет соединения.',
    });
    expect(compact.state).toBe('ready');
    if (compact.state !== 'ready') throw new Error('expected ready');
    expect(compact.compact).toBe(true);
    expect(compact.notice).toBe('Сохранено на устройстве · не удалось обновить');
    expect(compact.emptyMessage).toBe('На этот день ничего не запланировано');

    expect(
      buildCalendarScreenModel({
        mode: 'week',
        selectedDate: '2026-08-12',
        width: 430,
        day: null,
        week: null,
        month: null,
        status: 'loading',
        source: null,
      }),
    ).toEqual({ state: 'loading' });
  });

  it('shows Month high-level facts only and never derives tiny tasks', () => {
    const model = buildCalendarScreenModel({
      mode: 'month',
      selectedDate: '2026-08-12',
      width: 375,
      day: calendarDayFixture,
      week: calendarWeekFixture,
      month: calendarMonthFixture,
      status: 'ready',
      source: 'network',
    });

    if (model.state !== 'ready') throw new Error('expected ready');
    expect(model.monthFacts.map((fact) => fact.title)).toEqual([
      '72.5000 kg',
      'Пробный экзамен пройден',
      'Поездка',
      'Сдать экзамен',
    ]);
    expect(JSON.stringify(model.monthFacts)).not.toContain(
      calendarDayFixture.items[0]!.title,
    );
    expect(model.monthSummary).toBe('8 дней с планом · 14 ч запланировано');
  });

  it('derives canonical Monday and first-of-month request boundaries', () => {
    expect(mondayForDate('2026-08-12')).toBe('2026-08-10');
    expect(mondayForDate('2026-08-16')).toBe('2026-08-10');
    expect(monthForDate('2026-08-12')).toBe('2026-08-01');
  });
});
