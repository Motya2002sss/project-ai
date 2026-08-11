from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, DateTime, String, Time, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    public_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        default=uuid4,
        unique=True,
        index=True,
        nullable=False,
    )
    telegram_id: Mapped[int | None] = mapped_column(BigInteger, unique=True, index=True, nullable=True)
    external_id: Mapped[str | None] = mapped_column(String(255), unique=True, index=True, nullable=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    timezone: Mapped[str] = mapped_column(String(64), default="UTC", nullable=False)

    work_start_time: Mapped[Time | None] = mapped_column(Time, nullable=True)
    work_end_time: Mapped[Time | None] = mapped_column(Time, nullable=True)
    sleep_time: Mapped[Time | None] = mapped_column(Time, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    goals = relationship("Goal", back_populates="user", cascade="all, delete-orphan")
    tasks = relationship("Task", back_populates="user", cascade="all, delete-orphan")
    routines = relationship("Routine", back_populates="user", cascade="all, delete-orphan")
    day_plans = relationship("DayPlan", back_populates="user", cascade="all, delete-orphan")
    auth_identities = relationship(
        "AuthIdentity", back_populates="user", cascade="all, delete-orphan"
    )
    app_sessions = relationship(
        "AppSession", back_populates="user", cascade="all, delete-orphan"
    )
    resource_budget = relationship(
        "ResourceBudget",
        back_populates="user",
        cascade="all, delete-orphan",
        uselist=False,
    )
    onboarding_previews = relationship(
        "OnboardingPreview", back_populates="user", cascade="all, delete-orphan"
    )
    goal_milestones = relationship("GoalMilestone", cascade="all, delete-orphan")
    programs = relationship("Program", cascade="all, delete-orphan")
    program_phases = relationship("ProgramPhase", cascade="all, delete-orphan")
    weekly_commitments = relationship(
        "WeeklyCommitment", cascade="all, delete-orphan"
    )
    evidence = relationship("Evidence", cascade="all, delete-orphan")
    metric_observations = relationship(
        "MetricObservation", cascade="all, delete-orphan"
    )
    goal_progress_snapshots = relationship(
        "GoalProgressSnapshot", cascade="all, delete-orphan"
    )
