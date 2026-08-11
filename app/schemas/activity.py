from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.progress import ProgressResult


WorkoutSetStatus = Literal["planned", "completed", "skipped"]


class WorkoutSetFactInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    set_id: UUID
    actual_weight: Decimal | None = Field(default=None, ge=0)
    actual_reps: int | None = Field(default=None, ge=0)
    actual_rpe: Decimal | None = Field(default=None, ge=0, le=10)
    completion_status: WorkoutSetStatus
    note: str | None = Field(default=None, max_length=1000)


class WorkoutDraftRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(min_length=1, max_length=128)
    recorded_at: datetime
    sets: list[WorkoutSetFactInput] = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def validate_request(self):
        _require_aware(self.recorded_at)
        _require_unique_set_ids(self.sets)
        return self


class WorkoutFinishRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(min_length=1, max_length=128)
    started_at: datetime
    finished_at: datetime
    sets: list[WorkoutSetFactInput] = Field(default_factory=list, max_length=200)

    @model_validator(mode="after")
    def validate_request(self):
        _require_aware(self.started_at)
        _require_aware(self.finished_at)
        if self.finished_at < self.started_at:
            raise ValueError("finished_at must not precede started_at")
        if (self.finished_at - self.started_at).total_seconds() > 24 * 60 * 60:
            raise ValueError("workout duration exceeds 24 hours")
        _require_unique_set_ids(self.sets)
        return self


class WorkoutSetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    position: int
    planned_weight: Decimal | None
    planned_reps: int | None
    planned_rpe: Decimal | None
    actual_weight: Decimal | None
    actual_reps: int | None
    actual_rpe: Decimal | None
    weight_unit: str
    completion_status: str
    note: str | None


class WorkoutExerciseResponse(BaseModel):
    id: UUID
    name: str
    position: int
    note: str | None
    sets: list[WorkoutSetResponse]


class WorkoutSnapshotResponse(BaseModel):
    task_id: int
    task_status: str
    exercises: list[WorkoutExerciseResponse]


class WorkoutMutationResponse(BaseModel):
    state: Literal["draft", "final"]
    workout: WorkoutSnapshotResponse
    evidence_id: UUID | None = None
    elapsed_minutes: int | None = Field(default=None, ge=0)
    progress: ProgressResult | None = None
    report_required: Literal[False] = False


NutritionAdherence = Literal["on_plan", "partly", "off_plan", "not_recorded"]


class NutritionLogRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(min_length=1, max_length=128)
    occurred_at: datetime
    goal_id: UUID | None = None
    task_id: int | None = Field(default=None, ge=1)
    program_id: UUID | None = None
    meal_note: str | None = Field(default=None, max_length=2000)
    adherence: NutritionAdherence | None = None
    calories: Decimal | None = Field(default=None, ge=0)
    protein_grams: Decimal | None = Field(default=None, ge=0)
    fat_grams: Decimal | None = Field(default=None, ge=0)
    carbohydrate_grams: Decimal | None = Field(default=None, ge=0)
    target_calories: Decimal | None = Field(default=None, ge=0)
    target_protein_grams: Decimal | None = Field(default=None, ge=0)
    target_fat_grams: Decimal | None = Field(default=None, ge=0)
    target_carbohydrate_grams: Decimal | None = Field(default=None, ge=0)
    weight_observation: Decimal | None = Field(default=None, gt=0)
    weight_unit: str = Field(default="kg", min_length=1, max_length=16)

    @model_validator(mode="after")
    def validate_request(self):
        _require_aware(self.occurred_at)
        observed = (
            self.meal_note,
            self.adherence,
            self.calories,
            self.protein_grams,
            self.fat_grams,
            self.carbohydrate_grams,
            self.target_calories,
            self.target_protein_grams,
            self.target_fat_grams,
            self.target_carbohydrate_grams,
            self.weight_observation,
        )
        if all(value is None for value in observed):
            raise ValueError("nutrition log requires at least one factual value")
        return self


class NutritionLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    occurred_at: datetime
    meal_note: str | None
    adherence: str | None
    calories: Decimal | None
    protein_grams: Decimal | None
    fat_grams: Decimal | None
    carbohydrate_grams: Decimal | None
    target_calories: Decimal | None
    target_protein_grams: Decimal | None
    target_fat_grams: Decimal | None
    target_carbohydrate_grams: Decimal | None
    weight_observation: Decimal | None
    weight_unit: str


class WeightTrendResponse(BaseModel):
    current: Decimal
    previous: Decimal | None
    delta: Decimal | None
    unit: str


class NutritionMutationResponse(BaseModel):
    log: NutritionLogResponse
    weight_trend: WeightTrendResponse | None = None
    progress: ProgressResult | None = None
    report_required: Literal[False] = False


class LearningLogRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(min_length=1, max_length=128)
    occurred_at: datetime
    goal_id: UUID | None = None
    task_id: int | None = Field(default=None, ge=1)
    program_id: UUID | None = None
    resource_id: UUID | None = None
    competency: str | None = Field(default=None, max_length=255)
    pages_completed: int | None = Field(default=None, ge=0)
    minutes_spent: int | None = Field(default=None, ge=0, le=1440)
    exercises_completed: int | None = Field(default=None, ge=0)
    projects_completed: int | None = Field(default=None, ge=0)
    note: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def validate_request(self):
        _require_aware(self.occurred_at)
        facts = (
            self.pages_completed,
            self.minutes_spent,
            self.exercises_completed,
            self.projects_completed,
        )
        if not any(value is not None and value > 0 for value in facts):
            raise ValueError("learning log requires a positive factual result")
        return self


class LearningSessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    learning_resource_id: UUID | None
    occurred_at: datetime
    competency: str | None
    pages_completed: int | None
    minutes_spent: int | None
    exercises_completed: int | None
    projects_completed: int | None
    note: str | None


class LearningMutationResponse(BaseModel):
    session: LearningSessionResponse
    evidence_id: UUID | None = None
    task_status: str | None = None
    progress: ProgressResult | None = None
    report_required: Literal[False] = False


class ProgramAdaptationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(min_length=1, max_length=128)
    prompt: str = Field(min_length=1, max_length=1500)


class ProgramScheduleAdaptation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["schedule"]
    weekday: int = Field(strict=True, ge=1, le=7)


class ProgramSessionDurationAdaptation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["session_duration"]
    minutes: int = Field(strict=True, ge=5, le=360)


class ProgramFrequencyAdaptation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["weekly_frequency"]
    sessions_per_week: int = Field(strict=True, ge=1, le=14)


class WorkoutLoadAdaptation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["exercise_load"]
    exercise: str = Field(min_length=1, max_length=255)
    weight_delta: Decimal = Field(
        gt=Decimal("-500"),
        lt=Decimal("500"),
        max_digits=6,
        decimal_places=2,
        allow_inf_nan=False,
        strict=True,
    )
    weight_unit: Literal["kg", "lb"]


class WorkoutVolumeAdaptation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["exercise_volume"]
    exercise: str = Field(min_length=1, max_length=255)
    sets_delta: int | None = Field(default=None, strict=True, ge=-10, le=10)
    reps_delta: int | None = Field(default=None, strict=True, ge=-50, le=50)

    @model_validator(mode="after")
    def require_nonzero_volume_change(self):
        values = (self.sets_delta, self.reps_delta)
        if all(value in (None, 0) for value in values):
            raise ValueError("volume adaptation requires a non-zero delta")
        return self


class ProgramRecoveryAdaptation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["recovery_gap"]
    minutes: int = Field(strict=True, ge=0, le=10_080)


ProgramAdaptationChange = Annotated[
    ProgramScheduleAdaptation
    | ProgramSessionDurationAdaptation
    | ProgramFrequencyAdaptation
    | WorkoutLoadAdaptation
    | WorkoutVolumeAdaptation
    | ProgramRecoveryAdaptation,
    Field(discriminator="kind"),
]


class ProgramAdaptationCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str = Field(min_length=1, max_length=500)
    rationale: str | None = Field(default=None, max_length=1000)
    changes: list[ProgramAdaptationChange] = Field(min_length=1, max_length=20)


class ProgramAdaptationResponse(BaseModel):
    status: Literal["refused", "confirmation_required"]
    confirmation_required: bool
    reason: str | None = None
    safe_message: str | None = None
    base_version: int | None = None
    candidate: ProgramAdaptationCandidate | None = None


class ProgramAdaptationUnavailableResponse(BaseModel):
    status: Literal["unavailable"] = "unavailable"
    reason: Literal["adaptation_provider_unavailable"] = (
        "adaptation_provider_unavailable"
    )
    retryable: Literal[True] = True
    safe_message: str = (
        "Корректировка программы временно недоступна. Попробуйте позже."
    )


def _require_aware(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must include a timezone")


def _require_unique_set_ids(items: list[WorkoutSetFactInput]) -> None:
    ids = [item.set_id for item in items]
    if len(ids) != len(set(ids)):
        raise ValueError("set ids must be unique")
