from sqlalchemy import BigInteger, DateTime, String, Time, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    telegram_id: Mapped[int | None] = mapped_column(BigInteger, unique=True, index=True, nullable=True)
    external_id: Mapped[str | None] = mapped_column(String(255), unique=True, index=True, nullable=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    timezone: Mapped[str] = mapped_column(String(64), default="UTC", nullable=False)

    work_start_time: Mapped[Time | None] = mapped_column(Time, nullable=True)
    work_end_time: Mapped[Time | None] = mapped_column(Time, nullable=True)
    sleep_time: Mapped[Time | None] = mapped_column(Time, nullable=True)

    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    goals = relationship("Goal", back_populates="user", cascade="all, delete-orphan")
    tasks = relationship("Task", back_populates="user", cascade="all, delete-orphan")
    day_plans = relationship("DayPlan", back_populates="user", cascade="all, delete-orphan")
