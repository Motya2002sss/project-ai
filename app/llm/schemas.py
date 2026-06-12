from pydantic import BaseModel, Field


class ParsedTask(BaseModel):
    title: str
    priority: str = Field(default="medium")
    estimated_minutes: int | None = None


class ParsedUserMessage(BaseModel):
    intent: str = "add_tasks"

    date: str | None = None
    work_start: str | None = None
    work_until: str | None = None
    sleep_time: str | None = None
    budget_limit: int | None = None
    energy_level: str | None = None

    done_task_title: str | None = None
    done_task_titles: list[str] = Field(default_factory=list)
    skipped_task_titles: list[str] = Field(default_factory=list)

    tasks: list[ParsedTask] = Field(default_factory=list)

    raw_text: str | None = None
