from datetime import date, datetime, time

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text, Time, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    goal_id: Mapped[int | None] = mapped_column(ForeignKey("goals.id", ondelete="SET NULL"), nullable=True, index=True)

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    priority: Mapped[str] = mapped_column(String(32), nullable=False, default="medium")
    estimated_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    target_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    scheduling_type: Mapped[str] = mapped_column(String(32), nullable=False, default="flexible")
    fixed_start: Mapped[time | None] = mapped_column(Time, nullable=True)
    fixed_end: Mapped[time | None] = mapped_column(Time, nullable=True)
    preferred_window: Mapped[str | None] = mapped_column(String(32), nullable=True)
    earliest_start: Mapped[time | None] = mapped_column(Time, nullable=True)
    latest_end: Mapped[time | None] = mapped_column(Time, nullable=True)
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_locked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="planned")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    user = relationship("User", back_populates="tasks")
    goal = relationship("Goal", back_populates="tasks")
    plan_items = relationship("PlanItem", back_populates="task")
