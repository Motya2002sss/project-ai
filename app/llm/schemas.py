import re
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


Intent = Literal[
    "set_work_schedule",
    "set_day_availability",
    "create_task",
    "create_event",
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
TaskOperation = Literal["create", "update", "cancel", "complete"]
SchedulingType = Literal["fixed", "flexible", "unscheduled"]
PreferredWindow = Literal["morning", "afternoon", "evening", "anytime"]
WorkContext = Literal["permanent", "day", "off", "ambiguous"]

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
    operation: TaskOperation = "create"
    scheduling_type: SchedulingType | None = None
    target_date: str | None = None
    fixed_start: str | None = None
    fixed_end: str | None = None
    preferred_window: PreferredWindow | None = None
    earliest_start: str | None = None
    latest_end: str | None = None
    deadline: datetime | None = None
    priority: Priority = Field(default="medium")
    estimated_minutes: int | None = Field(default=None, ge=1, le=1440)
    duration_delta_minutes: int | None = Field(default=None, ge=1, le=1440)
    referenced_task_title: str | None = Field(default=None, max_length=255)
    recurrence_hint: str | None = Field(default=None, max_length=255)
    needs_clarification: bool = False
    clarification_reason: str | None = Field(default=None, max_length=500)

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

    @field_validator("duration_delta_minutes", mode="before")
    @classmethod
    def normalize_duration_delta_minutes(cls, value):
        return _empty_to_none(value)

    @field_validator("target_date", mode="before")
    @classmethod
    def normalize_target_date(cls, value):
        value = _empty_to_none(value)

        if value is None:
            return None

        if isinstance(value, date):
            return value.isoformat()

        normalized = str(value).strip().lower()

        if normalized in {"today", "tomorrow"}:
            return normalized

        date.fromisoformat(normalized)
        return normalized

    @field_validator("fixed_start", "fixed_end", "earliest_start", "latest_end", mode="before")
    @classmethod
    def normalize_task_times(cls, value):
        value = _empty_to_none(value)

        if value is None:
            return None

        if isinstance(value, int):
            value = f"{value:02d}:00"
        elif isinstance(value, str):
            value = value.strip()

            if re.fullmatch(r"\d{1,2}", value):
                value = f"{int(value):02d}:00"
            else:
                match = re.fullmatch(r"(\d{1,2}):(\d{1,2})", value)

                if match:
                    value = f"{int(match.group(1)):02d}:{int(match.group(2)):02d}"

        return value

    @field_validator("fixed_start", "fixed_end", "earliest_start", "latest_end")
    @classmethod
    def validate_task_time(cls, value: str | None) -> str | None:
        if value is None:
            return None

        if not TIME_RE.match(value):
            raise ValueError("time must use HH:MM format")

        hour, minute = value.split(":")

        if int(hour) > 23 or int(minute) > 59:
            raise ValueError("time is out of range")

        return value

    @field_validator(
        "referenced_task_title",
        "recurrence_hint",
        "clarification_reason",
        mode="before",
    )
    @classmethod
    def normalize_optional_task_text(cls, value):
        value = _empty_to_none(value)

        if value is None:
            return None

        return str(value).strip()

    @model_validator(mode="after")
    def infer_scheduling_type(self):
        if self.scheduling_type is None and self.operation == "create":
            self.scheduling_type = "fixed" if self.fixed_start else "flexible"

        return self


class ParsedUserMessage(BaseModel):
    model_config = ConfigDict(extra="ignore")

    intent: Intent = "add_tasks"

    date: DateValue | None = None
    work_start: str | None = None
    work_until: str | None = None
    work_context: WorkContext | None = None
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
