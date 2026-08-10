from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.api import (
    ClarificationResponse,
    ConfirmationResponse,
    ConflictResponse,
    DaySnapshotResponse,
    MessageReason,
    MessageStatus,
    PlanDiffResponse,
    TaskResponse,
    TaskStatus,
)


class MobileCaptureRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=4000)
    request_id: str = Field(min_length=1, max_length=128)


class MobileInteractionResponseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(min_length=1, max_length=128)
    text: str = Field(default="", max_length=4000)
    option_id: str | None = Field(default=None, min_length=1, max_length=64)

    @model_validator(mode="after")
    def require_option_or_text(self):
        if not self.option_id and not self.text.strip():
            raise ValueError("option_id or text is required")
        return self


class MobileTaskStatusRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: TaskStatus


class MobileActionResponse(BaseModel):
    request_id: str
    status: MessageStatus
    reason: MessageReason | None = None
    reply_text: str
    retryable: bool = False
    plan_diff: PlanDiffResponse = Field(default_factory=PlanDiffResponse)
    clarification: ClarificationResponse | None = None
    confirmation: ConfirmationResponse | None = None
    conflict: ConflictResponse | None = None
    day_snapshot: DaySnapshotResponse


class MobileTaskMutationResponse(BaseModel):
    status: Literal["applied", "no_change"]
    task: TaskResponse
    plan_diff: PlanDiffResponse = Field(default_factory=PlanDiffResponse)
    day_snapshot: DaySnapshotResponse
