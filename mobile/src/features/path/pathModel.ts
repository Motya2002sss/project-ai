import type {
  EvidenceSummaryDto,
  GoalPathDto,
  MilestoneSummaryDto,
  PathResponseDto,
} from './pathTypes';

export interface EvidenceModel {
  id: string;
  type: string;
  typeLabel: string;
  value: string | null;
  occurredAt: string;
}

export interface PathMilestoneModel {
  id: string;
  title: string;
  description: string | null;
  position: number;
  status: string;
  statusLabel: string;
}

export interface PathGoalModel {
  id: string;
  title: string;
  percentage: number | null;
  progressLabel: string;
  progressExplanation: string;
  progressReason: string | null;
  confidence: string;
  forecastDate: string | null;
  milestones: PathMilestoneModel[];
  currentPhase: {
    title: string;
    programName: string | null;
    dateRange: string | null;
  } | null;
  nextStep: { title: string; detail: string } | null;
  recentEvidence: EvidenceModel[];
  accessibilityLabel: string;
}

export type PathScreenModel =
  | { state: 'loading' }
  | { state: 'error'; message: string }
  | { state: 'empty'; cached: boolean; notice: string | null }
  | {
      state: 'ready';
      goals: PathGoalModel[];
      cached: boolean;
      notice: string | null;
    };

interface BuildPathScreenModelInput {
  response: PathResponseDto | null;
  status: 'loading' | 'ready' | 'error';
  source: 'network' | 'cache' | null;
  errorMessage?: string;
}

export interface GoalDetailsModel extends PathGoalModel {
  statusLabel: string;
  lifeArea: string | null;
  outcomeLabel: string;
  baseline: string | null;
  currentValue: string | null;
  target: string | null;
  metricUnit: string | null;
  deadline: string | null;
  intensity: string | null;
  allocation: string | null;
  program: {
    name: string;
    minimum: string;
    comfortable: string;
    maximum: string;
  } | null;
  evidence: EvidenceModel[];
  hasMoreEvidence: boolean;
  cached: boolean;
  actions: [];
}

export function buildPathScreenModel({
  response,
  status,
  source,
  errorMessage,
}: BuildPathScreenModelInput): PathScreenModel {
  if (!response) {
    if (status === 'loading') return { state: 'loading' };
    return {
      state: 'error',
      message: errorMessage ?? 'Не удалось загрузить путь.',
    };
  }

  const cached = source === 'cache';
  const notice = cached
    ? status === 'error'
      ? 'Сохранено на устройстве · не удалось обновить'
      : status === 'loading'
        ? 'Сохранено на устройстве · обновляю'
        : 'Сохранено на устройстве'
    : status === 'error'
      ? 'Не удалось обновить · показаны последние данные'
      : null;
  const goals = response.goals.slice(0, 3).map(mapGoalPath);
  if (goals.length === 0) return { state: 'empty', cached, notice };
  return { state: 'ready', goals, cached, notice };
}

export function buildGoalDetailsModel(
  detail: GoalPathDto,
  evidence: EvidenceSummaryDto[],
  options: { cached: boolean; hasMoreEvidence: boolean },
): GoalDetailsModel {
  const pathGoal = mapGoalPath(detail);
  const unit = detail.goal.metric_unit;
  return {
    ...pathGoal,
    statusLabel: statusLabel(detail.goal.status),
    lifeArea: detail.goal.life_area,
    outcomeLabel: outcomeLabel(detail.goal.outcome_type),
    baseline: metricValue(detail.goal.baseline_value, unit),
    currentValue: metricValue(detail.goal.current_value, unit),
    target: metricValue(detail.goal.target_value, unit),
    metricUnit: unit,
    deadline: detail.goal.deadline,
    intensity: detail.goal.intensity,
    allocation:
      detail.goal.allocation_minutes_week === null
        ? null
        : `${detail.goal.allocation_minutes_week} минут в неделю`,
    program: detail.current_program
      ? {
          name: detail.current_program.name,
          minimum: `${detail.current_program.minimum_minutes_week} мин/нед`,
          comfortable: `${detail.current_program.comfortable_minutes_week} мин/нед`,
          maximum: `${detail.current_program.maximum_minutes_week} мин/нед`,
        }
      : null,
    evidence: evidence.map(mapEvidence),
    hasMoreEvidence: options.hasMoreEvidence,
    cached: options.cached,
    actions: [],
  };
}

export function mergeEvidence(
  current: EvidenceSummaryDto[],
  incoming: EvidenceSummaryDto[],
): EvidenceSummaryDto[] {
  const seen = new Set(current.map((item) => item.id));
  const merged = [...current];
  for (const item of incoming) {
    if (seen.has(item.id)) continue;
    seen.add(item.id);
    merged.push(item);
  }
  return merged;
}

function mapGoalPath(item: GoalPathDto): PathGoalModel {
  const percentage =
    item.progress.percentage === null
      ? null
      : Number(item.progress.percentage);
  const progressLabel =
    percentage === null
      ? item.formula.label
      : `${formatDecimal(item.progress.percentage!)}%`;
  const milestones = item.milestones.map(mapMilestone);
  const currentPhase = item.current_phase
    ? {
        title: item.current_phase.title,
        programName: item.current_program?.name ?? null,
        dateRange: formatDateRange(
          item.current_phase.start_date,
          item.current_phase.end_date,
        ),
      }
    : null;
  const nextStep = item.next_step
    ? {
        title: item.next_step.title,
        detail: `${item.next_step.target_sessions_week} раза · ${item.next_step.target_minutes_week} минут в неделю`,
      }
    : null;
  const recentEvidence = item.recent_evidence.map(mapEvidence);
  const accessibilityParts = [
    item.goal.title,
    percentage === null
      ? progressLabel
      : `Прогресс ${formatDecimal(item.progress.percentage!)} процентов`,
    nextStep ? `Следующий шаг: ${nextStep.title}` : null,
    recentEvidence[0]
      ? `Последнее подтверждение: ${recentEvidence[0].typeLabel}${recentEvidence[0].value ? `, ${recentEvidence[0].value}` : ''}`
      : null,
    'Открыть цель',
  ].filter((part): part is string => Boolean(part));

  return {
    id: item.goal.public_id,
    title: item.goal.title,
    percentage,
    progressLabel,
    progressExplanation: item.formula.explanation,
    progressReason: item.progress.reason,
    confidence: item.progress.confidence,
    forecastDate: item.progress.forecast_date,
    milestones,
    currentPhase,
    nextStep,
    recentEvidence,
    accessibilityLabel: accessibilityParts.join('. '),
  };
}

function mapMilestone(item: MilestoneSummaryDto): PathMilestoneModel {
  return {
    id: item.id,
    title: item.title,
    description: item.description,
    position: item.position,
    status: item.status,
    statusLabel: milestoneStatusLabel(item.status),
  };
}

function mapEvidence(item: EvidenceSummaryDto): EvidenceModel {
  return {
    id: item.id,
    type: item.evidence_type,
    typeLabel: evidenceTypeLabel(item.evidence_type),
    value:
      item.quantity === null || item.unit === null
        ? null
        : `${formatDecimal(item.quantity)} ${item.unit}`,
    occurredAt: item.occurred_at,
  };
}

function formatDecimal(value: string): string {
  const normalized = value.replace(/\.0+$/, '').replace(/(\.\d*?)0+$/, '$1');
  return normalized.replace('.', ',');
}

function metricValue(value: string | null, unit: string | null): string | null {
  if (value === null) return null;
  return `${formatDecimal(value)}${unit ? ` ${unit}` : ''}`;
}

function formatDateRange(start: string | null, end: string | null): string | null {
  if (start && end) return `${start} — ${end}`;
  return start ?? end;
}

function statusLabel(status: string): string {
  if (status === 'active') return 'Активна';
  if (status === 'paused') return 'На паузе';
  if (status === 'completed') return 'Завершена';
  if (status === 'archived') return 'В архиве';
  return status;
}

function milestoneStatusLabel(status: string): string {
  if (status === 'completed') return 'Пройден';
  if (status === 'active') return 'Текущий этап';
  if (status === 'planned') return 'Впереди';
  return status;
}

function outcomeLabel(outcomeType: string | null): string {
  if (outcomeType === 'metric') return 'Измеримый результат';
  if (outcomeType === 'milestone') return 'Этапы пути';
  if (outcomeType === 'consistency') return 'Регулярность';
  return 'Формула не определена';
}

function evidenceTypeLabel(type: string): string {
  if (type === 'session') return 'Сессия';
  if (type === 'completion') return 'Выполнено';
  if (type === 'partial') return 'Частичный результат';
  if (type === 'result') return 'Результат';
  if (type === 'note') return 'Факт';
  return type;
}
