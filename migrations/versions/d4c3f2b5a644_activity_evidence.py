"""add workout nutrition and learning facts

Revision ID: d4c3f2b5a644
Revises: c3d2e1f4a5b6
Create Date: 2026-08-11 19:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "d4c3f2b5a644"
down_revision: Union[str, None] = "c3d2e1f4a5b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "workout_exercises",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("goal_id", sa.Integer(), nullable=True),
        sa.Column("task_id", sa.Integer(), nullable=False),
        sa.Column("program_id", sa.Uuid(), nullable=True),
        sa.Column("evidence_id", sa.Uuid(), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("note", sa.String(length=1000), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("position > 0", name="ck_workout_exercise_position"),
        sa.ForeignKeyConstraint(
            ["evidence_id"], ["evidence.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["goal_id"], ["goals.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["program_id"], ["programs.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "task_id",
            "position",
            name="uq_workout_exercise_task_position",
        ),
    )
    op.create_index(
        "ix_workout_exercises_user_id", "workout_exercises", ["user_id"]
    )
    op.create_index(
        "ix_workout_exercises_goal_id", "workout_exercises", ["goal_id"]
    )
    op.create_index(
        "ix_workout_exercises_task_id", "workout_exercises", ["task_id"]
    )
    op.create_index(
        "ix_workout_exercises_program_id", "workout_exercises", ["program_id"]
    )
    op.create_index(
        "ix_workout_exercises_evidence_id", "workout_exercises", ["evidence_id"]
    )
    op.create_index(
        "ix_workout_exercises_user_task_position",
        "workout_exercises",
        ["user_id", "task_id", "position"],
    )

    op.create_table(
        "workout_sets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("workout_exercise_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("planned_weight", sa.Numeric(10, 3), nullable=True),
        sa.Column("planned_reps", sa.Integer(), nullable=True),
        sa.Column("planned_rpe", sa.Numeric(4, 2), nullable=True),
        sa.Column("actual_weight", sa.Numeric(10, 3), nullable=True),
        sa.Column("actual_reps", sa.Integer(), nullable=True),
        sa.Column("actual_rpe", sa.Numeric(4, 2), nullable=True),
        sa.Column("weight_unit", sa.String(length=16), nullable=False),
        sa.Column("completion_status", sa.String(length=16), nullable=False),
        sa.Column("note", sa.String(length=1000), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("position > 0", name="ck_workout_set_position"),
        sa.CheckConstraint(
            "(planned_weight IS NULL OR planned_weight >= 0) AND "
            "(actual_weight IS NULL OR actual_weight >= 0) AND "
            "(planned_reps IS NULL OR planned_reps >= 0) AND "
            "(actual_reps IS NULL OR actual_reps >= 0)",
            name="ck_workout_set_nonnegative_facts",
        ),
        sa.CheckConstraint(
            "(planned_rpe IS NULL OR (planned_rpe >= 0 AND planned_rpe <= 10)) "
            "AND (actual_rpe IS NULL OR (actual_rpe >= 0 AND actual_rpe <= 10))",
            name="ck_workout_set_rpe_range",
        ),
        sa.CheckConstraint(
            "completion_status IN ('planned', 'completed', 'skipped')",
            name="ck_workout_set_completion_status",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["workout_exercise_id"],
            ["workout_exercises.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workout_exercise_id",
            "position",
            name="uq_workout_set_exercise_position",
        ),
    )
    op.create_index("ix_workout_sets_user_id", "workout_sets", ["user_id"])
    op.create_index(
        "ix_workout_sets_workout_exercise_id",
        "workout_sets",
        ["workout_exercise_id"],
    )
    op.create_index(
        "ix_workout_sets_user_exercise_position",
        "workout_sets",
        ["user_id", "workout_exercise_id", "position"],
    )

    op.create_table(
        "nutrition_logs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("goal_id", sa.Integer(), nullable=True),
        sa.Column("task_id", sa.Integer(), nullable=True),
        sa.Column("program_id", sa.Uuid(), nullable=True),
        sa.Column("evidence_id", sa.Uuid(), nullable=True),
        sa.Column("request_id", sa.String(length=128), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("meal_note", sa.String(length=2000), nullable=True),
        sa.Column("adherence", sa.String(length=32), nullable=True),
        sa.Column("calories", sa.Numeric(10, 2), nullable=True),
        sa.Column("protein_grams", sa.Numeric(10, 2), nullable=True),
        sa.Column("fat_grams", sa.Numeric(10, 2), nullable=True),
        sa.Column("carbohydrate_grams", sa.Numeric(10, 2), nullable=True),
        sa.Column("target_calories", sa.Numeric(10, 2), nullable=True),
        sa.Column("target_protein_grams", sa.Numeric(10, 2), nullable=True),
        sa.Column("target_fat_grams", sa.Numeric(10, 2), nullable=True),
        sa.Column("target_carbohydrate_grams", sa.Numeric(10, 2), nullable=True),
        sa.Column("weight_observation", sa.Numeric(10, 3), nullable=True),
        sa.Column("weight_unit", sa.String(length=16), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
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
        sa.CheckConstraint(
            "adherence IS NULL OR adherence IN "
            "('on_plan', 'partly', 'off_plan', 'not_recorded')",
            name="ck_nutrition_log_adherence",
        ),
        sa.ForeignKeyConstraint(
            ["evidence_id"], ["evidence.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["goal_id"], ["goals.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["program_id"], ["programs.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "request_id", name="uq_nutrition_log_user_request"
        ),
    )
    op.create_index("ix_nutrition_logs_user_id", "nutrition_logs", ["user_id"])
    op.create_index("ix_nutrition_logs_goal_id", "nutrition_logs", ["goal_id"])
    op.create_index("ix_nutrition_logs_task_id", "nutrition_logs", ["task_id"])
    op.create_index(
        "ix_nutrition_logs_program_id", "nutrition_logs", ["program_id"]
    )
    op.create_index(
        "ix_nutrition_logs_evidence_id", "nutrition_logs", ["evidence_id"]
    )
    op.create_index(
        "ix_nutrition_logs_user_occurred_id",
        "nutrition_logs",
        ["user_id", "occurred_at", "id"],
    )

    op.create_table(
        "learning_resources",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("goal_id", sa.Integer(), nullable=True),
        sa.Column("program_id", sa.Uuid(), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("resource_type", sa.String(length=32), nullable=False),
        sa.Column("competency", sa.String(length=255), nullable=True),
        sa.Column("total_pages", sa.Integer(), nullable=True),
        sa.Column("total_minutes", sa.Integer(), nullable=True),
        sa.Column("total_exercises", sa.Integer(), nullable=True),
        sa.Column("total_projects", sa.Integer(), nullable=True),
        sa.Column("note", sa.String(length=1000), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(total_pages IS NULL OR total_pages >= 0) AND "
            "(total_minutes IS NULL OR total_minutes >= 0) AND "
            "(total_exercises IS NULL OR total_exercises >= 0) AND "
            "(total_projects IS NULL OR total_projects >= 0)",
            name="ck_learning_resource_nonnegative_totals",
        ),
        sa.ForeignKeyConstraint(["goal_id"], ["goals.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["program_id"], ["programs.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_learning_resources_user_id", "learning_resources", ["user_id"]
    )
    op.create_index(
        "ix_learning_resources_goal_id", "learning_resources", ["goal_id"]
    )
    op.create_index(
        "ix_learning_resources_program_id", "learning_resources", ["program_id"]
    )
    op.create_index(
        "ix_learning_resources_user_goal",
        "learning_resources",
        ["user_id", "goal_id"],
    )
    op.create_index(
        "ix_learning_resources_user_program",
        "learning_resources",
        ["user_id", "program_id"],
    )

    op.create_table(
        "learning_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("goal_id", sa.Integer(), nullable=True),
        sa.Column("task_id", sa.Integer(), nullable=True),
        sa.Column("program_id", sa.Uuid(), nullable=True),
        sa.Column("learning_resource_id", sa.Uuid(), nullable=True),
        sa.Column("milestone_id", sa.Uuid(), nullable=True),
        sa.Column("evidence_id", sa.Uuid(), nullable=True),
        sa.Column("request_id", sa.String(length=128), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("competency", sa.String(length=255), nullable=True),
        sa.Column("pages_completed", sa.Integer(), nullable=True),
        sa.Column("minutes_spent", sa.Integer(), nullable=True),
        sa.Column("exercises_completed", sa.Integer(), nullable=True),
        sa.Column("projects_completed", sa.Integer(), nullable=True),
        sa.Column("note", sa.String(length=1000), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(pages_completed IS NULL OR pages_completed >= 0) AND "
            "(minutes_spent IS NULL OR minutes_spent >= 0) AND "
            "(exercises_completed IS NULL OR exercises_completed >= 0) AND "
            "(projects_completed IS NULL OR projects_completed >= 0)",
            name="ck_learning_session_nonnegative_facts",
        ),
        sa.ForeignKeyConstraint(
            ["evidence_id"], ["evidence.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["goal_id"], ["goals.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["learning_resource_id"],
            ["learning_resources.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["milestone_id"], ["goal_milestones.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["program_id"], ["programs.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "request_id", name="uq_learning_session_user_request"
        ),
    )
    op.create_index(
        "ix_learning_sessions_user_id", "learning_sessions", ["user_id"]
    )
    op.create_index(
        "ix_learning_sessions_goal_id", "learning_sessions", ["goal_id"]
    )
    op.create_index(
        "ix_learning_sessions_task_id", "learning_sessions", ["task_id"]
    )
    op.create_index(
        "ix_learning_sessions_program_id", "learning_sessions", ["program_id"]
    )
    op.create_index(
        "ix_learning_sessions_learning_resource_id",
        "learning_sessions",
        ["learning_resource_id"],
    )
    op.create_index(
        "ix_learning_sessions_milestone_id", "learning_sessions", ["milestone_id"]
    )
    op.create_index(
        "ix_learning_sessions_evidence_id", "learning_sessions", ["evidence_id"]
    )
    op.create_index(
        "ix_learning_sessions_user_occurred_id",
        "learning_sessions",
        ["user_id", "occurred_at", "id"],
    )


def downgrade() -> None:
    op.drop_table("learning_sessions")
    op.drop_table("learning_resources")
    op.drop_table("nutrition_logs")
    op.drop_table("workout_sets")
    op.drop_table("workout_exercises")
