from datetime import date
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


ProgressStrategy = Literal["metric", "milestone", "consistency", "unknown"]
ProgressConfidence = Literal["low", "medium", "high"]


class ProgressResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    strategy: ProgressStrategy
    percentage: Decimal | None = Field(default=None, ge=0, le=100)
    components: dict[str, Any]
    reason: str | None = None
    formula_version: str = "progress-v1"
    forecast_date: date | None = None
    confidence: ProgressConfidence = "low"
