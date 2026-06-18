import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


Intent = Literal[
    "update_profile",
    "show_profile",
    "update_goals",
    "show_goals",
    "suggest_goal_tasks",
    "add_tasks",
    "show_tasks",
    "show_plan",
    "mark_done",
    "daily_summary",
    "clear_tasks",
    "reschedule",
]

DateValue = Literal["today", "tomorrow"]
EnergyLevel = Literal["low", "medium", "high"]
Priority = Literal["low", "medium", "high"]

TIME_RE = re.compile(r"^\d{2}:\d{2}$")


def _empty_to_none(value):
    if isinstance(value, str):
        value = value.strip()

        if value == "" or value.lower() in {"null", "none"}:
            return None

    return value


class ParsedTask(BaseModel):
    model_config = ConfigDict(extra="ignore")

    title: str = Field(min_length=1, max_length=255)
    priority: Priority = Field(default="medium")
    estimated_minutes: int | None = Field(default=None, ge=1, le=1440)

    @field_validator("title", mode="before")
    @classmethod
    def strip_title(cls, value) -> str:
        return str(value).strip()

    @field_validator("priority", mode="before")
    @classmethod
    def normalize_priority(cls, value):
        return _empty_to_none(value) or "medium"

    @field_validator("estimated_minutes", mode="before")
    @classmethod
    def normalize_estimated_minutes(cls, value):
        return _empty_to_none(value)


class ParsedUserMessage(BaseModel):
    model_config = ConfigDict(extra="ignore")

    intent: Intent = "add_tasks"

    date: DateValue | None = None
    work_start: str | None = None
    work_until: str | None = None
    sleep_time: str | None = None
    budget_limit: int | None = Field(default=None, ge=0)
    energy_level: EnergyLevel | None = None

    done_task_title: str | None = None
    done_task_titles: list[str] = Field(default_factory=list)
    skipped_task_titles: list[str] = Field(default_factory=list)

    goals: list[str] = Field(default_factory=list)
    tasks: list[ParsedTask] = Field(default_factory=list)

    raw_text: str | None = None

    parser_provider: str = "mock"
    used_fallback: bool = False
    fallback_reason: str | None = None

    @field_validator("date", "energy_level", "work_start", "work_until", "sleep_time", mode="before")
    @classmethod
    def normalize_optional_strings(cls, value):
        return _empty_to_none(value)

    @field_validator("work_start", "work_until", "sleep_time")
    @classmethod
    def validate_time(cls, value: str | None) -> str | None:
        if value is None:
            return None

        if not TIME_RE.match(value):
            raise ValueError("time must use HH:MM format")

        hour, minute = value.split(":")

        if int(hour) > 23 or int(minute) > 59:
            raise ValueError("time is out of range")

        return value

    @field_validator("budget_limit", mode="before")
    @classmethod
    def normalize_budget_limit(cls, value):
        return _empty_to_none(value)

    @field_validator("done_task_title", "raw_text", "fallback_reason", mode="before")
    @classmethod
    def normalize_optional_text(cls, value):
        if value is None:
            return None

        value = str(value).strip()

        return value or None

    @field_validator("goals", "done_task_titles", "skipped_task_titles", mode="before")
    @classmethod
    def normalize_string_list(cls, value):
        if value is None:
            return []

        if not isinstance(value, list):
            return value

        cleaned = []

        for item in value:
            text = str(item).strip()

            if text:
                cleaned.append(text[:255])

        return cleaned
