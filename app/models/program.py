from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
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


class GoalMilestone(Base):
    __tablename__ = "goal_milestones"
    __table_args__ = (
        UniqueConstraint("goal_id", "position", name="uq_goal_milestone_position"),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid4
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    goal_id: Mapped[int] = mapped_column(
        ForeignKey("goals.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    criteria: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    weight: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
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

    goal = relationship("Goal", back_populates="milestones")


class Program(Base):
    __tablename__ = "programs"
    __table_args__ = (
        CheckConstraint(
            "minimum_minutes_week >= 0 AND "
            "minimum_minutes_week <= comfortable_minutes_week AND "
            "comfortable_minutes_week <= maximum_minutes_week",
            name="ck_program_weekly_load",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid4
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    goal_id: Mapped[int] = mapped_column(
        ForeignKey("goals.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    minimum_minutes_week: Mapped[int] = mapped_column(Integer, nullable=False)
    comfortable_minutes_week: Mapped[int] = mapped_column(Integer, nullable=False)
    maximum_minutes_week: Mapped[int] = mapped_column(Integer, nullable=False)
    adaptation_rules: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
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

    goal = relationship("Goal", back_populates="programs")
    phases = relationship(
        "ProgramPhase", back_populates="program", cascade="all, delete-orphan"
    )
    commitments = relationship(
        "WeeklyCommitment", back_populates="program", cascade="all, delete-orphan"
    )
    tasks = relationship("Task", back_populates="program")
    evidence = relationship("Evidence", back_populates="program")


class ProgramPhase(Base):
    __tablename__ = "program_phases"
    __table_args__ = (
        UniqueConstraint("program_id", "position", name="uq_program_phase_position"),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid4
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    program_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("programs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="planned")
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    configuration: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    program = relationship("Program", back_populates="phases")
    commitments = relationship("WeeklyCommitment", back_populates="phase")


class WeeklyCommitment(Base):
    __tablename__ = "weekly_commitments"
    __table_args__ = (
        CheckConstraint(
            "target_minutes_week >= 0 AND target_sessions_week >= 0 AND "
            "minimum_block_minutes > 0 AND recovery_gap_minutes >= 0",
            name="ck_weekly_commitment_load",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid4
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    goal_id: Mapped[int] = mapped_column(
        ForeignKey("goals.id", ondelete="CASCADE"), nullable=False, index=True
    )
    program_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("programs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    phase_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("program_phases.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    target_minutes_week: Mapped[int] = mapped_column(Integer, nullable=False)
    target_sessions_week: Mapped[int] = mapped_column(Integer, nullable=False)
    minimum_block_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    allowed_weekdays: Mapped[list[int]] = mapped_column(JSON, nullable=False)
    preferred_window: Mapped[str | None] = mapped_column(String(32), nullable=True)
    splittable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    recovery_gap_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
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

    program = relationship("Program", back_populates="commitments")
    phase = relationship("ProgramPhase", back_populates="commitments")
    tasks = relationship("Task", back_populates="commitment")
    evidence = relationship("Evidence", back_populates="commitment")
