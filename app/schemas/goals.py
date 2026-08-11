from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.progress import ProgressResult


OutcomeType = Literal["metric", "milestone", "consistency"]
GoalStatus = Literal["active", "paused", "completed", "archived"]


class GoalCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=255)
    life_area: str = Field(min_length=1, max_length=64)
    outcome_type: OutcomeType
    baseline_value: Decimal | None = None
    target_value: Decimal | None = None
    metric_unit: str | None = Field(default=None, min_length=1, max_length=64)
    deadline: date | None = None
    intensity: str | None = Field(default=None, max_length=32)
    allocation_minutes_week: int | None = Field(default=None, ge=0, le=10080)

    @model_validator(mode="after")
    def validate_metric_outcome(self):
        if self.outcome_type == "metric" and (
            self.baseline_value is None
            or self.target_value is None
            or self.metric_unit is None
        ):
            raise ValueError("metric goals require baseline, target and unit")
        if (
            self.outcome_type == "metric"
            and self.baseline_value == self.target_value
        ):
            raise ValueError("metric target must differ from baseline")
        return self


class GoalUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(min_length=1, max_length=128)
    expected_version: int = Field(ge=1)
    confirmation: bool = False
    title: str | None = Field(default=None, min_length=1, max_length=255)
    life_area: str | None = Field(default=None, min_length=1, max_length=64)
    baseline_value: Decimal | None = None
    target_value: Decimal | None = None
    metric_unit: str | None = Field(default=None, min_length=1, max_length=64)
    deadline: date | None = None
    intensity: str | None = Field(default=None, max_length=32)
    allocation_minutes_week: int | None = Field(default=None, ge=0, le=10080)


class GoalVersionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(min_length=1, max_length=128)
    expected_version: int = Field(ge=1)


class GoalDeleteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(min_length=1, max_length=128)
    expected_version: int = Field(ge=1)
    confirmation: Literal["DELETE"]


class GoalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    public_id: UUID
    title: str
    life_area: str | None
    outcome_type: str | None
    baseline_value: Decimal | None
    current_value: Decimal | None
    target_value: Decimal | None
    metric_unit: str | None
    deadline: date | None
    intensity: str | None
    allocation_minutes_week: int | None
    status: str
    version: int


class GoalMutationResponse(BaseModel):
    goal: GoalResponse
    progress: ProgressResult


class EvidenceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(min_length=1, max_length=128)
    evidence_type: Literal["session", "completion", "partial", "result", "note"]
    quantity: Decimal | None = Field(default=None, ge=0)
    unit: str | None = Field(default=None, min_length=1, max_length=64)
    occurred_at: datetime
    note: str | None = Field(default=None, max_length=1000)
    program_id: UUID | None = None
    commitment_id: UUID | None = None
    task_id: int | None = Field(default=None, ge=1)
    attributes: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def quantity_and_unit_are_paired(self):
        if (self.quantity is None) != (self.unit is None):
            raise ValueError("quantity and unit must be provided together")
        if self.evidence_type == "partial" and self.quantity is None:
            raise ValueError("partial evidence requires a quantity")
        return self


class MetricObservationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(min_length=1, max_length=128)
    value: Decimal
    unit: str = Field(min_length=1, max_length=64)
    occurred_at: datetime
    source: Literal["manual", "import", "device"]
    note: str | None = Field(default=None, max_length=1000)


class EvidenceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    evidence_type: str
    quantity: Decimal | None
    unit: str | None
    occurred_at: datetime


class MetricObservationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    value: Decimal
    unit: str
    occurred_at: datetime
    source: str


class EvidenceMutationResponse(BaseModel):
    goal: GoalResponse
    evidence: EvidenceResponse
    progress: ProgressResult


class ObservationMutationResponse(BaseModel):
    goal: GoalResponse
    observation: MetricObservationResponse
    progress: ProgressResult


class MilestoneCompleteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(min_length=1, max_length=128)
    expected_version: int = Field(ge=1)
    confirmation: bool
    occurred_at: datetime


class ProgramMilestoneInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=1000)
    position: int = Field(ge=1, le=100)
    criteria: dict = Field(default_factory=lambda: {"kind": "manual_confirmation"})
    weight: Decimal | None = Field(default=None, gt=0)


class ProgramPhaseInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=255)
    position: int = Field(ge=1, le=100)
    start_date: date | None = None
    end_date: date | None = None
    configuration: dict = Field(default_factory=dict)


class ProgramCommitmentInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=255)
    phase_position: int | None = Field(default=None, ge=1, le=100)
    target_minutes_week: int = Field(ge=0, le=10080)
    target_sessions_week: int = Field(ge=0, le=100)
    minimum_block_minutes: int = Field(ge=1, le=1440)
    allowed_weekdays: list[int] = Field(min_length=1, max_length=7)
    preferred_window: Literal["morning", "afternoon", "evening", "anytime"] | None = None
    splittable: bool = True
    recovery_gap_minutes: int = Field(default=0, ge=0, le=1440)

    @model_validator(mode="after")
    def normalize_weekdays(self):
        self.allowed_weekdays = sorted(set(self.allowed_weekdays))
        if any(day < 1 or day > 7 for day in self.allowed_weekdays):
            raise ValueError("allowed_weekdays must use ISO weekdays 1-7")
        if self.target_minutes_week == 0 and self.target_sessions_week == 0:
            raise ValueError("commitment requires minutes or sessions")
        minimum_load = max(1, self.target_sessions_week) * self.minimum_block_minutes
        if 0 < self.target_minutes_week < minimum_load:
            raise ValueError(
                "target_minutes_week cannot cover the requested minimum blocks"
            )
        return self


class ProgramProposalInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=255)
    minimum_minutes_week: int = Field(ge=0, le=10080)
    comfortable_minutes_week: int = Field(ge=0, le=10080)
    maximum_minutes_week: int = Field(ge=0, le=10080)
    adaptation_rules: dict = Field(default_factory=dict)
    milestones: list[ProgramMilestoneInput] = Field(default_factory=list, max_length=50)
    phases: list[ProgramPhaseInput] = Field(default_factory=list, max_length=50)
    commitments: list[ProgramCommitmentInput] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def validate_structure(self):
        if not (
            self.minimum_minutes_week
            <= self.comfortable_minutes_week
            <= self.maximum_minutes_week
        ):
            raise ValueError("program weekly load must be ordered")
        milestone_positions = [item.position for item in self.milestones]
        phase_positions = [item.position for item in self.phases]
        if len(set(milestone_positions)) != len(milestone_positions):
            raise ValueError("milestone positions must be unique")
        if len(set(phase_positions)) != len(phase_positions):
            raise ValueError("phase positions must be unique")
        known_phases = set(phase_positions)
        if any(
            item.phase_position is not None and item.phase_position not in known_phases
            for item in self.commitments
        ):
            raise ValueError("commitment references an unknown phase")
        committed_minutes = sum(
            max(
                item.target_minutes_week,
                item.target_sessions_week * item.minimum_block_minutes,
            )
            for item in self.commitments
        )
        if committed_minutes > self.comfortable_minutes_week:
            raise ValueError("commitments exceed comfortable program load")
        return self


class ProgramApplyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(min_length=1, max_length=128)
    expected_goal_version: int = Field(ge=1)
    confirmation: bool
    proposal: ProgramProposalInput


class ProgramResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    status: str
    minimum_minutes_week: int
    comfortable_minutes_week: int
    maximum_minutes_week: int
    version: int


class ProgramMutationResponse(BaseModel):
    goal: GoalResponse
    program: ProgramResponse
    progress: ProgressResult
