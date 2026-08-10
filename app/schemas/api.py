from datetime import date, datetime, time
from typing import Literal

from pydantic import BaseModel, Field


MessageSource = Literal[
    "web_text",
    "telegram_text",
    "telegram_voice_transcript",
    "voice_transcript",
    "ios_text",
    "ios_voice_transcript",
]
DateSelector = Literal["today", "tomorrow"]
TaskStatus = Literal["planned", "done"]
StoredTaskStatus = Literal["planned", "done", "cancelled"]
MessageStatus = Literal[
    "applied",
    "clarification_required",
    "confirmation_required",
    "conflict",
    "no_change",
    "unsupported_capability",
    "failed",
    "needs_clarification",
]


class MessageRequest(BaseModel):
    user_external_id: str = Field(min_length=1, max_length=255)
    text: str = Field(min_length=1, max_length=4000)
    source: MessageSource = "web_text"
    request_id: str | None = Field(default=None, min_length=1, max_length=128)
    interaction_id: str | None = Field(default=None, min_length=1, max_length=36)
    option_id: str | None = Field(default=None, min_length=1, max_length=64)


class TaskDoneRequest(BaseModel):
    user_external_id: str = Field(min_length=1, max_length=255)


class TaskStatusRequest(BaseModel):
    user_external_id: str = Field(min_length=1, max_length=255)
    status: TaskStatus


class TaskResponse(BaseModel):
    id: int
    title: str
    priority: str
    estimated_minutes: int | None
    target_date: date
    scheduling_type: str
    fixed_start: time | None
    fixed_end: time | None
    preferred_window: str | None
    earliest_start: time | None
    latest_end: time | None
    deadline: datetime | None
    is_locked: bool
    status: StoredTaskStatus
    routine_id: int | None = None
    occurrence_date: date | None = None


class GoalResponse(BaseModel):
    id: int
    title: str
    category: str
    priority: str
    status: str


class RoutineResponse(BaseModel):
    id: int
    title: str
    cadence: str
    weekdays: list[int] = Field(default_factory=list)
    fixed_time: time | None = None
    preferred_window: str | None = None
    estimated_minutes: int | None = None
    start_date: date
    end_date: date | None = None
    active: bool


class ProfileResponse(BaseModel):
    user_external_id: str
    name: str | None
    timezone: str
    work_start_time: time | None
    work_end_time: time | None
    sleep_time: time | None


class PlanItemResponse(BaseModel):
    id: int
    task_id: int | None
    title: str
    item_type: str
    status: str
    start_time: time | None
    end_time: time | None
    unscheduled_reason: str | None = None


class PlanResponse(BaseModel):
    id: int
    date: date
    summary: str | None
    focus_text: str = Field(min_length=1, max_length=180)
    energy_level: str | None
    budget_limit: int | None
    status: str
    version: int = Field(ge=0)
    items: list[PlanItemResponse] = Field(default_factory=list)


class MovedPlanItemResponse(BaseModel):
    task_id: int
    title: str
    old_start: time
    new_start: time


class PlanDiffResponse(BaseModel):
    created_task_ids: list[int] = Field(default_factory=list)
    updated_task_ids: list[int] = Field(default_factory=list)
    completed_task_ids: list[int] = Field(default_factory=list)
    cancelled_task_ids: list[int] = Field(default_factory=list)
    moved_plan_items: list[MovedPlanItemResponse] = Field(default_factory=list)
    unscheduled_task_ids: list[int] = Field(default_factory=list)
    created_routine_ids: list[int] = Field(default_factory=list)
    availability_change: str | None = None
    conflict: str | None = None
    clarification: str | None = None


class InteractionOptionResponse(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=160)
    value: str = Field(min_length=1, max_length=255)


class ClarificationResponse(BaseModel):
    id: str
    question: str
    options: list[InteractionOptionResponse] = Field(default_factory=list)
    free_text_allowed: bool = True
    expires_at: datetime


class ConfirmationResponse(BaseModel):
    id: str
    title: str
    summary: str
    changes: PlanDiffResponse = Field(default_factory=PlanDiffResponse)
    options: list[InteractionOptionResponse] = Field(default_factory=list)
    expires_at: datetime
    base_plan_version: int | None = None


class ConflictResponse(BaseModel):
    id: str | None = None
    title: str = "Не удалось встроить изменение"
    message: str
    options: list[InteractionOptionResponse] = Field(default_factory=list)
    expires_at: datetime | None = None


class DayProgressResponse(BaseModel):
    done: int = Field(ge=0)
    total: int = Field(ge=0)


class DayContextResponse(BaseModel):
    energy_level: str | None = None
    budget_limit: int | None = None
    work_override_mode: str | None = None
    work_start_time: time | None = None
    work_end_time: time | None = None


class DaySnapshotResponse(BaseModel):
    date: date
    focus_text: str = Field(min_length=1, max_length=180)
    progress: DayProgressResponse
    scheduled_items: list[PlanItemResponse] = Field(default_factory=list)
    unscheduled_items: list[PlanItemResponse] = Field(default_factory=list)
    completed_items: list[PlanItemResponse] = Field(default_factory=list)
    current_item: PlanItemResponse | None = None
    completed_count: int = Field(ge=0)
    total_count: int = Field(ge=0)
    day_context: DayContextResponse
    tasks: list[TaskResponse] = Field(default_factory=list)
    goals: list[GoalResponse] = Field(default_factory=list)
    routines: list[RoutineResponse] = Field(default_factory=list)
    plan: PlanResponse
    plan_version: int = Field(ge=0)


class MessageResponse(BaseModel):
    request_id: str | None = None
    user_external_id: str
    source: MessageSource
    intent: str
    parsed: dict
    status: MessageStatus = "applied"
    needs_clarification: bool = False
    clarification_question: str | None = None
    reply_text: str
    summary: str | None = None
    affected_tasks: list[TaskResponse] = Field(default_factory=list)
    affected_goals: list[GoalResponse] = Field(default_factory=list)
    affected_routines: list[RoutineResponse] = Field(default_factory=list)
    profile: ProfileResponse | None = None
    plan_summary: PlanResponse | None = None
    plan_diff: PlanDiffResponse = Field(default_factory=PlanDiffResponse)
    clarification: ClarificationResponse | None = None
    confirmation: ConfirmationResponse | None = None
    conflict_details: ConflictResponse | None = None
    day_snapshot: DaySnapshotResponse | None = None
