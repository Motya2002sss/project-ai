export interface BudgetHoursDraft {
  text: string;
  minutes: number;
}

export function applyBudgetHoursDraft(
  text: string,
  currentMinutes: number,
): BudgetHoursDraft {
  if (!/^\d*(?:[.,]\d*)?$/.test(text)) {
    return { text, minutes: currentMinutes };
  }
  const normalized = text.replace(',', '.');
  const hours = Number(normalized);
  return {
    text,
    minutes: Number.isFinite(hours)
      ? Math.max(0, Math.round(hours * 60))
      : currentMinutes,
  };
}

export function formatBudgetHours(minutes: number): string {
  const hours = minutes / 60;
  return Number.isInteger(hours) ? String(hours) : hours.toFixed(1);
}
