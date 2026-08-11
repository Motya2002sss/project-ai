from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    JSON,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PlanChange(Base):
    __tablename__ = "plan_changes"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "request_id", name="uq_plan_change_user_request"
        ),
        CheckConstraint(
            "status IN ('applied', 'undone')",
            name="ck_plan_change_status",
        ),
        Index(
            "ix_plan_changes_user_created_id",
            "user_id",
            "created_at",
            "id",
        ),
        Index(
            "ix_plan_changes_user_status_expires",
            "user_id",
            "status",
            "expires_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid4
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    request_id: Mapped[str] = mapped_column(String(128), nullable=False)
    reason: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    base_versions: Mapped[dict] = mapped_column(JSON, nullable=False)
    result_versions: Mapped[dict] = mapped_column(JSON, nullable=False)
    affected_dates: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    forward_payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    inverse_payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    undone_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
