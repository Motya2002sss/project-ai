from pydantic import BaseModel, Field


class ParsedTask(BaseModel):
    title: str
    priority: str = Field(default="medium")
    estimated_minutes: int | None = None


class ParsedUserMessage(BaseModel):
    date: str | None = None
    work_until: str | None = None
    budget_limit: int | None = None
    energy_level: str | None = None
    tasks: list[ParsedTask] = Field(default_factory=list)
    raw_text: str | None = None
