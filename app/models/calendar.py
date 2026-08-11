from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CalendarBusyBlock(Base):
    __tablename__ = "calendar_busy_blocks"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "device_id",
            "provider",
            "calendar_external_id",
            "occurrence_external_id",
            name="uq_calendar_busy_stable_occurrence",
        ),
        CheckConstraint(
            "occurrence_end > occurrence_start",
            name="ck_calendar_busy_positive_interval",
        ),
        Index(
            "ix_calendar_busy_user_interval_deleted",
            "user_id",
            "occurrence_start",
            "occurrence_end",
            "deleted_at",
        ),
        Index(
            "ix_calendar_busy_sync_scope_interval",
            "user_id",
            "device_id",
            "provider",
            "calendar_external_id",
            "occurrence_start",
            "occurrence_end",
            "deleted_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid4
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    device_id: Mapped[str] = mapped_column(String(128), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    calendar_external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    occurrence_external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    occurrence_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    occurrence_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    device_timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    source_revision: Mapped[str] = mapped_column(String(128), nullable=False)
    last_seen_client_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class CalendarSyncState(Base):
    __tablename__ = "calendar_sync_states"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "device_id",
            "provider",
            name="uq_calendar_sync_state_scope",
        ),
        CheckConstraint(
            "version >= 1 AND client_revision >= 1",
            name="ck_calendar_sync_state_versions",
        ),
        CheckConstraint(
            "range_end > range_start",
            name="ck_calendar_sync_state_positive_range",
        ),
        Index(
            "ix_calendar_sync_states_user_device_provider",
            "user_id",
            "device_id",
            "provider",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid4
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    device_id: Mapped[str] = mapped_column(String(128), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    client_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    range_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    range_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    device_timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    covered_calendar_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    last_synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class TemporaryLifeMode(Base):
    __tablename__ = "temporary_life_modes"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "request_id", name="uq_temporary_mode_user_request"
        ),
        CheckConstraint(
            "ends_at > starts_at",
            name="ck_temporary_mode_positive_interval",
        ),
        CheckConstraint(
            "mode IN ('normal', 'workload', 'recovery', 'sick', 'travel', "
            "'vacation', 'low_sleep', 'focus_sprint')",
            name="ck_temporary_mode_kind",
        ),
        CheckConstraint(
            "status IN ('active', 'cancelled', 'completed')",
            name="ck_temporary_mode_status",
        ),
        Index(
            "ix_temporary_modes_user_interval",
            "user_id",
            "starts_at",
            "ends_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid4
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    request_id: Mapped[str] = mapped_column(String(128), nullable=False)
    mode: Mapped[str] = mapped_column(String(32), nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    constraints: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
