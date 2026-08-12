import type { TodayModel } from './models';

const currentRowTopInset = 24;

export function currentTimelineKey(model: TodayModel | null): string | null {
  if (!model) return null;
  const current = model.rows.find((row) => row.variant === 'current');
  return current
    ? `${model.dateLabel}:${model.planVersion}:${current.id}`
    : null;
}

export function timelineAutoScrollOffset(rowY: number): number {
  return Math.max(0, rowY - currentRowTopInset);
}
