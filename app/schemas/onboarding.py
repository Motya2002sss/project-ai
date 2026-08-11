from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


OnboardingStatus = Literal[
    "not_started", "clarification_required", "ready", "applied"
]


class ResourceBudgetInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    weekly_available_minutes: int = Field(ge=30, le=10080)
    available_days: list[int] = Field(min_length=1, max_length=7)
    minimum_minutes: int = Field(ge=0, le=10080)
    comfortable_minutes: int = Field(ge=0, le=10080)
    maximum_minutes: int = Field(ge=0, le=10080)
    free_evenings: list[int] = Field(default_factory=list, max_length=7)
    preferred_windows: dict[str, str] = Field(default_factory=dict)
    money_budget: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    conflict_priority: str | None = Field(default=None, max_length=255)
    reserve_percent: int = Field(default=20, ge=0, le=80)

    @model_validator(mode="after")
    def validate_capacity(self):
        self.available_days = sorted(set(self.available_days))
        self.free_evenings = sorted(set(self.free_evenings))
        if any(day < 1 or day > 7 for day in self.available_days):
            raise ValueError("available_days must use ISO weekdays 1-7")
        if any(day < 1 or day > 7 for day in self.free_evenings):
            raise ValueError("free_evenings must use ISO weekdays 1-7")
        if not set(self.free_evenings).issubset(self.available_days):
            raise ValueError("free_evenings must be available days")
        allocatable = self.weekly_available_minutes * (100 - self.reserve_percent) // 100
        if not (
            self.minimum_minutes
            <= self.comfortable_minutes
            <= self.maximum_minutes
            <= allocatable
        ):
            raise ValueError(
                "minimum, comfortable and maximum minutes must fit allocatable capacity"
            )
        return self


class OnboardingPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(min_length=1, max_length=128)
    narrative: str = Field(min_length=1, max_length=12000)
    resource_budget: ResourceBudgetInput
    preview_id: UUID | None = None
    expected_version: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def correction_requires_version(self):
        if (self.preview_id is None) != (self.expected_version is None):
            raise ValueError("preview_id and expected_version must be provided together")
        return self


class OnboardingApplyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    preview_id: UUID
    expected_version: int = Field(ge=1)


class OnboardingPreviewResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    status: Literal["clarification_required", "ready", "applied"]
    version: int
    structured_summary: dict
    goal_candidates: list[str]
    resource_budget: dict
    allocation: dict
    clarification: dict | None
    created_at: datetime
    updated_at: datetime


class OnboardingStateResponse(BaseModel):
    status: Literal["not_started", "in_progress", "completed"]
    preview: OnboardingPreviewResponse | None
