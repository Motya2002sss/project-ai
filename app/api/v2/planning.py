from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.orm import Session

from app.api.v2.dependencies import AuthenticatedRequest, get_authenticated_request
from app.db.session import get_db
from app.services.plan_change_service import (
    PlanChangeConflict,
    PlanMutationResult,
    TemporaryModeRequest,
    apply_replan,
    undo_plan_change,
)


TemporaryModeKind = Literal[
    "normal",
    "workload",
    "recovery",
    "sick",
    "travel",
    "vacation",
    "low_sleep",
    "focus_sprint",
]
ReplanReason = Literal[
    "calendar_sync",
    "temporary_mode",
    "capacity_change",
    "manual",
]
PlanVersion = Annotated[
    int,
    Field(strict=True, ge=0, le=2_147_483_647),
]


class BlockedIntervalInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start: datetime
    end: datetime

    @model_validator(mode="after")
    def validate_interval(self):
        if (
            self.start.tzinfo is None
            or self.start.utcoffset() is None
            or self.end.tzinfo is None
            or self.end.utcoffset() is None
        ):
            raise ValueError("blocked intervals must include a timezone")
        if self.end <= self.start:
            raise ValueError("blocked interval end must follow start")
        return self


class TemporaryModeConstraintsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    blocked_intervals: list[BlockedIntervalInput] = Field(
        default_factory=list,
        max_length=32,
    )
    max_flexible_minutes: int | None = Field(default=None, ge=0, le=1020)
    reserve_minutes: int | None = Field(default=None, ge=0, le=1020)


class TemporaryModeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: TemporaryModeKind
    starts_at: datetime
    ends_at: datetime
    constraints: TemporaryModeConstraintsInput = Field(
        default_factory=TemporaryModeConstraintsInput
    )

    @model_validator(mode="after")
    def validate_interval(self):
        if (
            self.starts_at.tzinfo is None
            or self.starts_at.utcoffset() is None
            or self.ends_at.tzinfo is None
            or self.ends_at.utcoffset() is None
        ):
            raise ValueError("temporary mode timestamps must include a timezone")
        if self.ends_at <= self.starts_at:
            raise ValueError("temporary mode end must follow start")
        return self


class ReplanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(min_length=1, max_length=128)
    base_versions: dict[date, PlanVersion]
    affected_dates: list[date] = Field(min_length=1, max_length=14)
    reason: ReplanReason
    temporary_mode: TemporaryModeInput | None = None

    @model_validator(mode="after")
    def validate_versions(self):
        if len(set(self.affected_dates)) != len(self.affected_dates):
            raise ValueError("affected dates must be unique")
        if set(self.base_versions) != set(self.affected_dates):
            raise ValueError("base versions must match affected dates")
        if any(isinstance(value, bool) or value < 0 for value in self.base_versions.values()):
            raise ValueError("base versions must be non-negative integers")
        if self.reason == "temporary_mode" and self.temporary_mode is None:
            raise ValueError("temporary_mode reason requires temporary_mode")
        if self.temporary_mode is not None and self.reason != "temporary_mode":
            raise ValueError("temporary_mode payload requires temporary_mode reason")
        return self


class UndoRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(min_length=1, max_length=128)
    expected_version: PlanVersion | dict[date, PlanVersion]


class MovedPlacementResponse(BaseModel):
    date: date
    task_id: int
    old_start: str
    old_end: str
    new_start: str
    new_end: str


class UnscheduledPlacementResponse(BaseModel):
    date: date
    task_id: int
    reason: str


class ScheduledPlacementResponse(BaseModel):
    date: date
    task_id: int
    start: str
    end: str


class FactualPlanDiffResponse(BaseModel):
    moved: list[MovedPlacementResponse] = Field(default_factory=list)
    unscheduled: list[UnscheduledPlacementResponse] = Field(default_factory=list)
    scheduled: list[ScheduledPlacementResponse] = Field(default_factory=list)


class PlacementSnapshotResponse(BaseModel):
    placement_id: int
    task_id: int
    start_time: str | None
    end_time: str | None
    status: str
    unscheduled_reason: str | None


class PlanDaySnapshotResponse(BaseModel):
    date: date
    version: int = Field(ge=0)
    status: str
    items: list[PlacementSnapshotResponse] = Field(default_factory=list)


class PlanMutationResponse(BaseModel):
    status: Literal["applied", "no_change", "undone"]
    request_id: str
    change_id: UUID
    reason: str
    base_versions: dict[str, int]
    result_versions: dict[str, int]
    affected_dates: list[str]
    plan_diff: FactualPlanDiffResponse
    snapshots: list[PlanDaySnapshotResponse]
    expires_at: datetime | None


router = APIRouter(prefix="/planning", tags=["planning-v2"])


@router.post("/replan", response_model=PlanMutationResponse)
def replan(
    request: ReplanRequest,
    authenticated: AuthenticatedRequest = Depends(get_authenticated_request),
    db: Session = Depends(get_db),
) -> PlanMutationResult:
    temporary_mode = None
    if request.temporary_mode is not None:
        mode = request.temporary_mode
        temporary_mode = TemporaryModeRequest(
            mode=mode.mode,
            starts_at=mode.starts_at,
            ends_at=mode.ends_at,
            constraints=mode.constraints.model_dump(mode="json", exclude_none=True),
        )
    try:
        return apply_replan(
            db,
            user=authenticated.user,
            request_id=request.request_id,
            base_versions=request.base_versions,
            affected_dates=request.affected_dates,
            reason=request.reason,
            temporary_mode=temporary_mode,
        )
    except PlanChangeConflict as error:
        raise _http_conflict(error) from error


@router.post(
    "/plan-changes/{change_id}/undo",
    response_model=PlanMutationResponse,
)
def undo_change(
    change_id: UUID,
    request: UndoRequest,
    authenticated: AuthenticatedRequest = Depends(get_authenticated_request),
    db: Session = Depends(get_db),
) -> PlanMutationResult:
    try:
        return undo_plan_change(
            db,
            user=authenticated.user,
            change_id=change_id,
            request_id=request.request_id,
            expected_version=request.expected_version,
        )
    except PlanChangeConflict as error:
        raise _http_conflict(error) from error


def _http_conflict(error: PlanChangeConflict) -> HTTPException:
    status_code = (
        status.HTTP_404_NOT_FOUND
        if error.code == "change_not_found"
        else status.HTTP_409_CONFLICT
    )
    return HTTPException(
        status_code=status_code,
        detail={"code": error.code, **error.details},
    )
