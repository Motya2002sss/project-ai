from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ResourceBudget(Base):
    __tablename__ = "resource_budgets"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    weekly_available_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    available_days: Mapped[list[int]] = mapped_column(JSON, nullable=False)
    minimum_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    comfortable_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    maximum_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    free_evenings: Mapped[list[int]] = mapped_column(JSON, nullable=False, default=list)
    preferred_windows: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    money_budget: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    conflict_priority: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reserve_percent: Mapped[int] = mapped_column(Integer, nullable=False, default=20)
    allocatable_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    allocation: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    user = relationship("User", back_populates="resource_budget")


class OnboardingPreview(Base):
    __tablename__ = "onboarding_previews"

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid4
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    narrative: Mapped[str | None] = mapped_column(Text, nullable=True)
    narrative_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    structured_summary: Mapped[dict] = mapped_column(JSON, nullable=False)
    goal_candidates: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    resource_budget: Mapped[dict] = mapped_column(JSON, nullable=False)
    allocation: Mapped[dict] = mapped_column(JSON, nullable=False)
    clarification: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    applied_at: Mapped[datetime | None] = mapped_column(
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

    user = relationship("User", back_populates="onboarding_previews")
    requests = relationship(
        "OnboardingRequestReceipt",
        back_populates="preview",
        cascade="all, delete-orphan",
    )


class OnboardingRequestReceipt(Base):
    __tablename__ = "onboarding_request_receipts"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "request_id", name="uq_onboarding_request_user_request"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    preview_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("onboarding_previews.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    request_id: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    preview = relationship("OnboardingPreview", back_populates="requests")
