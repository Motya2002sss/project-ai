from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Goal(Base):
    __tablename__ = "goals"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    public_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        default=uuid4,
        nullable=False,
        unique=True,
        index=True,
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False, default="personal")
    priority: Mapped[str] = mapped_column(String(32), nullable=False, default="medium")
    target_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    life_area: Mapped[str | None] = mapped_column(String(64), nullable=True)
    outcome_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    baseline_value: Mapped[Decimal | None] = mapped_column(Numeric(16, 4), nullable=True)
    current_value: Mapped[Decimal | None] = mapped_column(Numeric(16, 4), nullable=True)
    target_value: Mapped[Decimal | None] = mapped_column(Numeric(16, 4), nullable=True)
    metric_unit: Mapped[str | None] = mapped_column(String(64), nullable=True)
    deadline: Mapped[date | None] = mapped_column(Date, nullable=True)
    intensity: Mapped[str | None] = mapped_column(String(32), nullable=True)
    allocation_minutes_week: Mapped[int | None] = mapped_column(Integer, nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    user = relationship("User", back_populates="goals")
    tasks = relationship("Task", back_populates="goal")
    milestones = relationship(
        "GoalMilestone", back_populates="goal", cascade="all, delete-orphan"
    )
    programs = relationship(
        "Program", back_populates="goal", cascade="all, delete-orphan"
    )
    evidence = relationship(
        "Evidence", back_populates="goal", cascade="all, delete-orphan"
    )
    metric_observations = relationship(
        "MetricObservation", back_populates="goal", cascade="all, delete-orphan"
    )
    progress_snapshots = relationship(
        "GoalProgressSnapshot", back_populates="goal", cascade="all, delete-orphan"
    )
