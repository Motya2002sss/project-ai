from datetime import date, datetime, timedelta, timezone
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, model_validator


MAX_SYNC_RANGE = timedelta(days=62)
MAX_BUSY_BLOCK_DURATION = timedelta(days=31)
MAX_SYNC_PAST = timedelta(days=31)
MAX_SYNC_FUTURE = timedelta(days=366)
MAX_CLIENT_REVISION = 2_147_483_647


class CalendarBusyBlockInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    calendar_external_id: str = Field(min_length=1, max_length=255)
    external_id: str = Field(min_length=1, max_length=255)
    occurrence_external_id: str = Field(min_length=1, max_length=255)
    occurrence_start: datetime
    occurrence_end: datetime
    source_revision: str = Field(min_length=1, max_length=128)

    @model_validator(mode="after")
    def validate_interval(self):
        _require_aware(self.occurrence_start)
        _require_aware(self.occurrence_end)
        try:
            duration = self.occurrence_end - self.occurrence_start
        except OverflowError as error:
            raise ValueError("busy block timestamps are outside supported bounds") from error
        if duration <= timedelta(0):
            raise ValueError("occurrence_end must follow occurrence_start")
        if duration > MAX_BUSY_BLOCK_DURATION:
            raise ValueError("busy block exceeds maximum duration")
        return self


class CalendarSyncBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(min_length=1, max_length=128)
    device_id: str = Field(min_length=1, max_length=128)
    provider: str = Field(
        min_length=1,
        max_length=32,
        pattern=r"^[a-z0-9_-]+$",
    )
    client_revision: int = Field(ge=1, le=MAX_CLIENT_REVISION)
    range_start: datetime
    range_end: datetime
    device_timezone: str = Field(min_length=1, max_length=64)
    calendar_external_ids: list[str] = Field(default_factory=list, max_length=50)
    removed_calendar_external_ids: list[str] = Field(
        default_factory=list,
        max_length=50,
    )
    busy_blocks: list[CalendarBusyBlockInput] = Field(
        default_factory=list,
        max_length=1000,
    )

    @model_validator(mode="after")
    def validate_batch(self):
        _require_aware(self.range_start)
        _require_aware(self.range_end)
        try:
            if self.range_end <= self.range_start:
                raise ValueError("range_end must follow range_start")
            if self.range_end - self.range_start > MAX_SYNC_RANGE:
                raise ValueError("calendar sync range exceeds 62 days")
        except OverflowError as error:
            raise ValueError("calendar sync timestamps are outside supported bounds") from error
        try:
            ZoneInfo(self.device_timezone)
        except ZoneInfoNotFoundError as error:
            raise ValueError("unknown device timezone") from error
        now = _utc_now()
        try:
            range_start_utc = self.range_start.astimezone(timezone.utc)
            range_end_utc = self.range_end.astimezone(timezone.utc)
        except (OverflowError, ValueError) as error:
            raise ValueError("calendar sync timestamps are outside supported bounds") from error
        if (
            range_start_utc < now - MAX_SYNC_PAST
            or range_end_utc > now + MAX_SYNC_FUTURE
        ):
            raise ValueError("calendar sync range is outside the allowed horizon")
        normalized_calendars = _normalize_calendar_ids(
            self.calendar_external_ids,
            label="calendar external ids",
        )
        removed_calendars = _normalize_calendar_ids(
            self.removed_calendar_external_ids,
            label="removed calendar external ids",
        )
        if not normalized_calendars and not removed_calendars:
            raise ValueError("calendar sync requires an included or removed calendar")
        if set(normalized_calendars) & set(removed_calendars):
            raise ValueError("included and removed calendars must be disjoint")
        if len(set(normalized_calendars) | set(removed_calendars)) > 50:
            raise ValueError("calendar sync scope exceeds 50 calendars")
        self.calendar_external_ids = normalized_calendars
        self.removed_calendar_external_ids = removed_calendars
        covered = set(self.calendar_external_ids)
        identities: set[tuple[str, str]] = set()
        for block in self.busy_blocks:
            if block.calendar_external_id not in covered:
                raise ValueError("busy block calendar is outside sync scope")
            if not (
                block.occurrence_end > self.range_start
                and block.occurrence_start < self.range_end
            ):
                raise ValueError("busy block is outside sync range")
            identity = (
                block.calendar_external_id,
                block.occurrence_external_id,
            )
            if identity in identities:
                raise ValueError("busy occurrence identities must be unique")
            identities.add(identity)
        return self


class CalendarBusyBlocksRequest(CalendarSyncBatch):
    expected_version: int = Field(ge=0)


class CalendarSyncResult(BaseModel):
    version: int = Field(ge=1)
    client_revision: int = Field(ge=1)
    created_count: int = Field(ge=0)
    updated_count: int = Field(ge=0)
    tombstoned_count: int = Field(ge=0)
    unchanged_count: int = Field(ge=0)
    affected_dates: list[date]
    replan_required: bool
    synced_at: datetime


class CalendarSyncStateResponse(BaseModel):
    status: Literal["not_started", "ready"]
    device_id: str
    provider: str
    version: int = Field(ge=0)
    client_revision: int = Field(ge=0)
    range_start: datetime | None = None
    range_end: datetime | None = None
    device_timezone: str | None = None
    covered_calendar_ids: list[str] = Field(default_factory=list)
    last_synced_at: datetime | None = None


def _require_aware(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("calendar timestamps must include a timezone")


def _normalize_calendar_ids(values: list[str], *, label: str) -> list[str]:
    normalized = [item.strip() for item in values]
    if any(not item or len(item) > 255 for item in normalized):
        raise ValueError(f"invalid {label}")
    if len(set(normalized)) != len(normalized):
        raise ValueError(f"{label} must be unique")
    return sorted(normalized)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)
