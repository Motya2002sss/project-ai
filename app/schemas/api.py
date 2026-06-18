from datetime import date, time
from typing import Literal

from pydantic import BaseModel, Field


MessageSource = Literal["web_text", "telegram_text", "telegram_voice_transcript"]
DateSelector = Literal["today", "tomorrow"]


class MessageRequest(BaseModel):
    user_external_id: str = Field(min_length=1, max_length=255)
    text: str = Field(min_length=1, max_length=4000)
    source: MessageSource = "web_text"


class TaskResponse(BaseModel):
    id: int
    title: str
    priority: str
    estimated_minutes: int | None
    target_date: date
    status: str


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


class PlanResponse(BaseModel):
    id: int
    date: date
    summary: str | None
    energy_level: str | None
    budget_limit: int | None
    status: str
    items: list[PlanItemResponse] = Field(default_factory=list)


class MessageResponse(BaseModel):
    user_external_id: str
    source: MessageSource
    intent: str
    parsed: dict
    reply_text: str
    summary: str | None = None
    affected_tasks: list[TaskResponse] = Field(default_factory=list)
    affected_goals: list[GoalResponse] = Field(default_factory=list)
    profile: ProfileResponse | None = None
    plan_summary: PlanResponse | None = None
