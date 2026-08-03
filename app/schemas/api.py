from datetime import date, datetime, time
from typing import Literal

from pydantic import BaseModel, Field


MessageSource = Literal["web_text", "telegram_text", "telegram_voice_transcript"]
DateSelector = Literal["today", "tomorrow"]
TaskStatus = Literal["planned", "done"]
StoredTaskStatus = Literal["planned", "done", "cancelled"]
MessageStatus = Literal["applied", "needs_clarification", "conflict"]


class MessageRequest(BaseModel):
    user_external_id: str = Field(min_length=1, max_length=255)
    text: str = Field(min_length=1, max_length=4000)
    source: MessageSource = "web_text"


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


class GoalResponse(BaseModel):
    id: int
    title: str
    category: str
    priority: str
    status: str


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
    conflict: str | None = None
    clarification: str | None = None


class MessageResponse(BaseModel):
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
    profile: ProfileResponse | None = None
    plan_summary: PlanResponse | None = None
    plan_diff: PlanDiffResponse = Field(default_factory=PlanDiffResponse)
