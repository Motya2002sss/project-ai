from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class WorkoutExercise(Base):
    __tablename__ = "workout_exercises"
    __table_args__ = (
        UniqueConstraint(
            "task_id",
            "position",
            name="uq_workout_exercise_task_position",
        ),
        CheckConstraint("position > 0", name="ck_workout_exercise_position"),
        Index(
            "ix_workout_exercises_user_task_position",
            "user_id",
            "task_id",
            "position",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid4
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    goal_id: Mapped[int | None] = mapped_column(
        ForeignKey("goals.id", ondelete="SET NULL"), nullable=True, index=True
    )
    task_id: Mapped[int] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    program_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("programs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    evidence_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("evidence.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    note: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    sets = relationship(
        "WorkoutSet",
        back_populates="exercise",
        cascade="all, delete-orphan",
        order_by="WorkoutSet.position",
    )


class WorkoutSet(Base):
    __tablename__ = "workout_sets"
    __table_args__ = (
        UniqueConstraint(
            "workout_exercise_id",
            "position",
            name="uq_workout_set_exercise_position",
        ),
        CheckConstraint("position > 0", name="ck_workout_set_position"),
        CheckConstraint(
            "(planned_weight IS NULL OR planned_weight >= 0) AND "
            "(actual_weight IS NULL OR actual_weight >= 0) AND "
            "(planned_reps IS NULL OR planned_reps >= 0) AND "
            "(actual_reps IS NULL OR actual_reps >= 0)",
            name="ck_workout_set_nonnegative_facts",
        ),
        CheckConstraint(
            "(planned_rpe IS NULL OR (planned_rpe >= 0 AND planned_rpe <= 10)) "
            "AND (actual_rpe IS NULL OR (actual_rpe >= 0 AND actual_rpe <= 10))",
            name="ck_workout_set_rpe_range",
        ),
        CheckConstraint(
            "completion_status IN ('planned', 'completed', 'skipped')",
            name="ck_workout_set_completion_status",
        ),
        Index(
            "ix_workout_sets_user_exercise_position",
            "user_id",
            "workout_exercise_id",
            "position",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid4
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    workout_exercise_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("workout_exercises.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    planned_weight: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 3), nullable=True
    )
    planned_reps: Mapped[int | None] = mapped_column(Integer, nullable=True)
    planned_rpe: Mapped[Decimal | None] = mapped_column(Numeric(4, 2), nullable=True)
    actual_weight: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 3), nullable=True
    )
    actual_reps: Mapped[int | None] = mapped_column(Integer, nullable=True)
    actual_rpe: Mapped[Decimal | None] = mapped_column(Numeric(4, 2), nullable=True)
    weight_unit: Mapped[str] = mapped_column(
        String(16), nullable=False, default="kg"
    )
    completion_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="planned"
    )
    note: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(
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

    exercise = relationship("WorkoutExercise", back_populates="sets")


class NutritionLog(Base):
    __tablename__ = "nutrition_logs"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "request_id", name="uq_nutrition_log_user_request"
        ),
        CheckConstraint(
            "(calories IS NULL OR calories >= 0) AND "
            "(protein_grams IS NULL OR protein_grams >= 0) AND "
            "(fat_grams IS NULL OR fat_grams >= 0) AND "
            "(carbohydrate_grams IS NULL OR carbohydrate_grams >= 0) AND "
            "(target_calories IS NULL OR target_calories >= 0) AND "
            "(target_protein_grams IS NULL OR target_protein_grams >= 0) AND "
            "(target_fat_grams IS NULL OR target_fat_grams >= 0) AND "
            "(target_carbohydrate_grams IS NULL OR target_carbohydrate_grams >= 0) "
            "AND (weight_observation IS NULL OR weight_observation > 0)",
            name="ck_nutrition_log_nonnegative_facts",
        ),
        CheckConstraint(
            "adherence IS NULL OR adherence IN "
            "('on_plan', 'partly', 'off_plan', 'not_recorded')",
            name="ck_nutrition_log_adherence",
        ),
        Index(
            "ix_nutrition_logs_user_occurred_id",
            "user_id",
            "occurred_at",
            "id",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid4
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    goal_id: Mapped[int | None] = mapped_column(
        ForeignKey("goals.id", ondelete="SET NULL"), nullable=True, index=True
    )
    task_id: Mapped[int | None] = mapped_column(
        ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True, index=True
    )
    program_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("programs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    evidence_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("evidence.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    request_id: Mapped[str] = mapped_column(String(128), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    meal_note: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    adherence: Mapped[str | None] = mapped_column(String(32), nullable=True)
    calories: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    protein_grams: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2), nullable=True
    )
    fat_grams: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    carbohydrate_grams: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2), nullable=True
    )
    target_calories: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2), nullable=True
    )
    target_protein_grams: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2), nullable=True
    )
    target_fat_grams: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2), nullable=True
    )
    target_carbohydrate_grams: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2), nullable=True
    )
    weight_observation: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 3), nullable=True
    )
    weight_unit: Mapped[str] = mapped_column(
        String(16), nullable=False, default="kg"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class LearningResource(Base):
    __tablename__ = "learning_resources"
    __table_args__ = (
        CheckConstraint(
            "(total_pages IS NULL OR total_pages >= 0) AND "
            "(total_minutes IS NULL OR total_minutes >= 0) AND "
            "(total_exercises IS NULL OR total_exercises >= 0) AND "
            "(total_projects IS NULL OR total_projects >= 0)",
            name="ck_learning_resource_nonnegative_totals",
        ),
        Index(
            "ix_learning_resources_user_goal",
            "user_id",
            "goal_id",
        ),
        Index(
            "ix_learning_resources_user_program",
            "user_id",
            "program_id",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid4
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    goal_id: Mapped[int | None] = mapped_column(
        ForeignKey("goals.id", ondelete="SET NULL"), nullable=True, index=True
    )
    program_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("programs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(32), nullable=False)
    competency: Mapped[str | None] = mapped_column(String(255), nullable=True)
    total_pages: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_exercises: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_projects: Mapped[int | None] = mapped_column(Integer, nullable=True)
    note: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    sessions = relationship(
        "LearningSession",
        back_populates="resource",
        passive_deletes=True,
    )


class LearningSession(Base):
    __tablename__ = "learning_sessions"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "request_id", name="uq_learning_session_user_request"
        ),
        CheckConstraint(
            "(pages_completed IS NULL OR pages_completed >= 0) AND "
            "(minutes_spent IS NULL OR minutes_spent >= 0) AND "
            "(exercises_completed IS NULL OR exercises_completed >= 0) AND "
            "(projects_completed IS NULL OR projects_completed >= 0)",
            name="ck_learning_session_nonnegative_facts",
        ),
        Index(
            "ix_learning_sessions_user_occurred_id",
            "user_id",
            "occurred_at",
            "id",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid4
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    goal_id: Mapped[int | None] = mapped_column(
        ForeignKey("goals.id", ondelete="SET NULL"), nullable=True, index=True
    )
    task_id: Mapped[int | None] = mapped_column(
        ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True, index=True
    )
    program_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("programs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    learning_resource_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("learning_resources.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    milestone_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("goal_milestones.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    evidence_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("evidence.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    request_id: Mapped[str] = mapped_column(String(128), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    competency: Mapped[str | None] = mapped_column(String(255), nullable=True)
    pages_completed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    minutes_spent: Mapped[int | None] = mapped_column(Integer, nullable=True)
    exercises_completed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    projects_completed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    note: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    resource = relationship("LearningResource", back_populates="sessions")
