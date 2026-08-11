from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel

from app.schemas.goals import GoalResponse
from app.schemas.progress import ProgressResult


class FormulaExplanation(BaseModel):
    strategy: str
    label: str
    explanation: str


class MilestoneSummary(BaseModel):
    id: UUID
    title: str
    description: str | None
    position: int
    weight: Decimal | None
    status: str
    completed_at: datetime | None


class ProgramSummary(BaseModel):
    id: UUID
    name: str
    status: str
    minimum_minutes_week: int
    comfortable_minutes_week: int
    maximum_minutes_week: int
    version: int


class PhaseSummary(BaseModel):
    id: UUID
    title: str
    position: int
    status: str
    start_date: date | None
    end_date: date | None


class NextStepSummary(BaseModel):
    commitment_id: UUID
    title: str
    target_minutes_week: int
    target_sessions_week: int
    minimum_block_minutes: int
    allowed_weekdays: list[int]
    preferred_window: str | None


class EvidenceSummary(BaseModel):
    id: UUID
    evidence_type: str
    quantity: Decimal | None
    unit: str | None
    occurred_at: datetime


class GoalPathResponse(BaseModel):
    goal: GoalResponse
    progress: ProgressResult
    formula: FormulaExplanation
    milestones: list[MilestoneSummary]
    current_program: ProgramSummary | None
    current_phase: PhaseSummary | None
    next_step: NextStepSummary | None
    recent_evidence: list[EvidenceSummary]


class PathResponse(BaseModel):
    goals: list[GoalPathResponse]


class EvidencePageResponse(BaseModel):
    items: list[EvidenceSummary]
    next_cursor: str | None
