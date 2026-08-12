export interface GoalPathGoalDto {
  public_id: string;
  title: string;
  life_area: string | null;
  outcome_type: string | null;
  baseline_value: string | null;
  current_value: string | null;
  target_value: string | null;
  metric_unit: string | null;
  deadline: string | null;
  intensity: string | null;
  allocation_minutes_week: number | null;
  status: string;
  version: number;
}

export interface GoalProgressDto {
  strategy: 'metric' | 'milestone' | 'consistency' | 'unknown';
  percentage: string | null;
  components: Record<string, unknown>;
  reason: string | null;
  formula_version: string;
  forecast_date: string | null;
  confidence: 'low' | 'medium' | 'high';
}

export interface FormulaExplanationDto {
  strategy: string;
  label: string;
  explanation: string;
}

export interface MilestoneSummaryDto {
  id: string;
  title: string;
  description: string | null;
  position: number;
  weight: string | null;
  status: string;
  completed_at: string | null;
}

export interface ProgramSummaryDto {
  id: string;
  name: string;
  status: string;
  minimum_minutes_week: number;
  comfortable_minutes_week: number;
  maximum_minutes_week: number;
  version: number;
}

export interface PhaseSummaryDto {
  id: string;
  title: string;
  position: number;
  status: string;
  start_date: string | null;
  end_date: string | null;
}

export interface NextStepSummaryDto {
  commitment_id: string;
  title: string;
  target_minutes_week: number;
  target_sessions_week: number;
  minimum_block_minutes: number;
  allowed_weekdays: number[];
  preferred_window: string | null;
}

export interface EvidenceSummaryDto {
  id: string;
  evidence_type: string;
  quantity: string | null;
  unit: string | null;
  occurred_at: string;
}

export interface GoalPathDto {
  goal: GoalPathGoalDto;
  progress: GoalProgressDto;
  formula: FormulaExplanationDto;
  milestones: MilestoneSummaryDto[];
  current_program: ProgramSummaryDto | null;
  current_phase: PhaseSummaryDto | null;
  next_step: NextStepSummaryDto | null;
  recent_evidence: EvidenceSummaryDto[];
}

export interface PathResponseDto {
  goals: GoalPathDto[];
}

export interface EvidencePageDto {
  items: EvidenceSummaryDto[];
  next_cursor: string | null;
}
