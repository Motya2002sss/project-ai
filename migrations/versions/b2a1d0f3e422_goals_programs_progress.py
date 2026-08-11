"""add goal programs evidence and progress

Revision ID: b2a1d0f3e422
Revises: a8e7f6d5c4b3
Create Date: 2026-08-11 15:00:00.000000
"""

from typing import Sequence, Union
from uuid import uuid4

from alembic import op
import sqlalchemy as sa


revision: str = "b2a1d0f3e422"
down_revision: Union[str, None] = "a8e7f6d5c4b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("goals", sa.Column("public_id", sa.Uuid(), nullable=True))
    op.add_column("goals", sa.Column("life_area", sa.String(length=64), nullable=True))
    op.add_column("goals", sa.Column("outcome_type", sa.String(length=32), nullable=True))
    op.add_column("goals", sa.Column("baseline_value", sa.Numeric(16, 4), nullable=True))
    op.add_column("goals", sa.Column("current_value", sa.Numeric(16, 4), nullable=True))
    op.add_column("goals", sa.Column("target_value", sa.Numeric(16, 4), nullable=True))
    op.add_column("goals", sa.Column("metric_unit", sa.String(length=64), nullable=True))
    op.add_column("goals", sa.Column("deadline", sa.Date(), nullable=True))
    op.add_column("goals", sa.Column("intensity", sa.String(length=32), nullable=True))
    op.add_column("goals", sa.Column("allocation_minutes_week", sa.Integer(), nullable=True))
    op.add_column(
        "goals",
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
    )
    op.add_column(
        "goals",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    connection = op.get_bind()
    goal_ids = connection.execute(sa.text("SELECT id FROM goals")).scalars()
    for goal_id in goal_ids:
        connection.execute(
            sa.text("UPDATE goals SET public_id = :public_id WHERE id = :goal_id"),
            {"public_id": uuid4(), "goal_id": goal_id},
        )
    op.alter_column("goals", "public_id", nullable=False)
    op.create_index("ix_goals_public_id", "goals", ["public_id"], unique=True)

    op.create_table(
        "goal_milestones",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("goal_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("criteria", sa.JSON(), nullable=False),
        sa.Column("weight", sa.Numeric(8, 4), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
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
        sa.ForeignKeyConstraint(["goal_id"], ["goals.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("goal_id", "position", name="uq_goal_milestone_position"),
    )
    op.create_index("ix_goal_milestones_user_id", "goal_milestones", ["user_id"])
    op.create_index("ix_goal_milestones_goal_id", "goal_milestones", ["goal_id"])

    op.create_table(
        "programs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("goal_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("minimum_minutes_week", sa.Integer(), nullable=False),
        sa.Column("comfortable_minutes_week", sa.Integer(), nullable=False),
        sa.Column("maximum_minutes_week", sa.Integer(), nullable=False),
        sa.Column("adaptation_rules", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
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
            "minimum_minutes_week >= 0 AND "
            "minimum_minutes_week <= comfortable_minutes_week AND "
            "comfortable_minutes_week <= maximum_minutes_week",
            name="ck_program_weekly_load",
        ),
        sa.ForeignKeyConstraint(["goal_id"], ["goals.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_programs_user_id", "programs", ["user_id"])
    op.create_index("ix_programs_goal_id", "programs", ["goal_id"])

    op.create_table(
        "program_phases",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("program_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("configuration", sa.JSON(), nullable=False),
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
        sa.ForeignKeyConstraint(["program_id"], ["programs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("program_id", "position", name="uq_program_phase_position"),
    )
    op.create_index("ix_program_phases_user_id", "program_phases", ["user_id"])
    op.create_index("ix_program_phases_program_id", "program_phases", ["program_id"])

    op.create_table(
        "weekly_commitments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("goal_id", sa.Integer(), nullable=False),
        sa.Column("program_id", sa.Uuid(), nullable=False),
        sa.Column("phase_id", sa.Uuid(), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("target_minutes_week", sa.Integer(), nullable=False),
        sa.Column("target_sessions_week", sa.Integer(), nullable=False),
        sa.Column("minimum_block_minutes", sa.Integer(), nullable=False),
        sa.Column("allowed_weekdays", sa.JSON(), nullable=False),
        sa.Column("preferred_window", sa.String(length=32), nullable=True),
        sa.Column("splittable", sa.Boolean(), nullable=False),
        sa.Column("recovery_gap_minutes", sa.Integer(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
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
            "target_minutes_week >= 0 AND target_sessions_week >= 0 AND "
            "minimum_block_minutes > 0 AND recovery_gap_minutes >= 0",
            name="ck_weekly_commitment_load",
        ),
        sa.ForeignKeyConstraint(["goal_id"], ["goals.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["phase_id"], ["program_phases.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["program_id"], ["programs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_weekly_commitments_user_id", "weekly_commitments", ["user_id"])
    op.create_index("ix_weekly_commitments_goal_id", "weekly_commitments", ["goal_id"])
    op.create_index("ix_weekly_commitments_program_id", "weekly_commitments", ["program_id"])
    op.create_index("ix_weekly_commitments_phase_id", "weekly_commitments", ["phase_id"])

    op.add_column("tasks", sa.Column("program_id", sa.Uuid(), nullable=True))
    op.add_column("tasks", sa.Column("commitment_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_tasks_program_id", "tasks", "programs", ["program_id"], ["id"], ondelete="SET NULL"
    )
    op.create_foreign_key(
        "fk_tasks_commitment_id",
        "tasks",
        "weekly_commitments",
        ["commitment_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_tasks_program_id", "tasks", ["program_id"])
    op.create_index("ix_tasks_commitment_id", "tasks", ["commitment_id"])

    op.create_table(
        "evidence",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("goal_id", sa.Integer(), nullable=False),
        sa.Column("program_id", sa.Uuid(), nullable=True),
        sa.Column("commitment_id", sa.Uuid(), nullable=True),
        sa.Column("task_id", sa.Integer(), nullable=True),
        sa.Column("request_id", sa.String(length=128), nullable=False),
        sa.Column("evidence_type", sa.String(length=32), nullable=False),
        sa.Column("quantity", sa.Numeric(16, 4), nullable=True),
        sa.Column("unit", sa.String(length=64), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("attributes", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["commitment_id"], ["weekly_commitments.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["goal_id"], ["goals.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["program_id"], ["programs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "request_id", name="uq_evidence_user_request"),
    )
    op.create_index("ix_evidence_user_id", "evidence", ["user_id"])
    op.create_index("ix_evidence_goal_id", "evidence", ["goal_id"])
    op.create_index("ix_evidence_program_id", "evidence", ["program_id"])
    op.create_index("ix_evidence_commitment_id", "evidence", ["commitment_id"])
    op.create_index("ix_evidence_task_id", "evidence", ["task_id"])
    op.create_index("ix_evidence_user_occurred", "evidence", ["user_id", "occurred_at"])

    op.create_table(
        "metric_observations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("goal_id", sa.Integer(), nullable=False),
        sa.Column("request_id", sa.String(length=128), nullable=False),
        sa.Column("value", sa.Numeric(16, 4), nullable=False),
        sa.Column("unit", sa.String(length=64), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["goal_id"], ["goals.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "request_id", name="uq_metric_observation_user_request"
        ),
    )
    op.create_index("ix_metric_observations_user_id", "metric_observations", ["user_id"])
    op.create_index("ix_metric_observations_goal_id", "metric_observations", ["goal_id"])
    op.create_index(
        "ix_metric_observations_user_occurred",
        "metric_observations",
        ["user_id", "occurred_at"],
    )

    op.create_table(
        "goal_progress_snapshots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("goal_id", sa.Integer(), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("strategy", sa.String(length=32), nullable=False),
        sa.Column("percentage", sa.Numeric(7, 4), nullable=True),
        sa.Column("components", sa.JSON(), nullable=False),
        sa.Column("reason", sa.String(length=64), nullable=True),
        sa.Column("formula_version", sa.String(length=32), nullable=False),
        sa.Column("forecast_date", sa.Date(), nullable=True),
        sa.Column("confidence", sa.String(length=16), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["goal_id"], ["goals.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_goal_progress_snapshots_user_id", "goal_progress_snapshots", ["user_id"])
    op.create_index("ix_goal_progress_snapshots_goal_id", "goal_progress_snapshots", ["goal_id"])
    op.create_index(
        "ix_goal_progress_user_as_of", "goal_progress_snapshots", ["user_id", "as_of"]
    )
    op.create_index(
        "ix_goal_progress_goal_as_of", "goal_progress_snapshots", ["goal_id", "as_of"]
    )


def downgrade() -> None:
    op.drop_index("ix_goal_progress_goal_as_of", table_name="goal_progress_snapshots")
    op.drop_index("ix_goal_progress_user_as_of", table_name="goal_progress_snapshots")
    op.drop_index("ix_goal_progress_snapshots_goal_id", table_name="goal_progress_snapshots")
    op.drop_index("ix_goal_progress_snapshots_user_id", table_name="goal_progress_snapshots")
    op.drop_table("goal_progress_snapshots")
    op.drop_index("ix_metric_observations_user_occurred", table_name="metric_observations")
    op.drop_index("ix_metric_observations_goal_id", table_name="metric_observations")
    op.drop_index("ix_metric_observations_user_id", table_name="metric_observations")
    op.drop_table("metric_observations")
    op.drop_index("ix_evidence_user_occurred", table_name="evidence")
    op.drop_index("ix_evidence_task_id", table_name="evidence")
    op.drop_index("ix_evidence_commitment_id", table_name="evidence")
    op.drop_index("ix_evidence_program_id", table_name="evidence")
    op.drop_index("ix_evidence_goal_id", table_name="evidence")
    op.drop_index("ix_evidence_user_id", table_name="evidence")
    op.drop_table("evidence")
    op.drop_index("ix_tasks_commitment_id", table_name="tasks")
    op.drop_index("ix_tasks_program_id", table_name="tasks")
    op.drop_constraint("fk_tasks_commitment_id", "tasks", type_="foreignkey")
    op.drop_constraint("fk_tasks_program_id", "tasks", type_="foreignkey")
    op.drop_column("tasks", "commitment_id")
    op.drop_column("tasks", "program_id")
    op.drop_index("ix_weekly_commitments_phase_id", table_name="weekly_commitments")
    op.drop_index("ix_weekly_commitments_program_id", table_name="weekly_commitments")
    op.drop_index("ix_weekly_commitments_goal_id", table_name="weekly_commitments")
    op.drop_index("ix_weekly_commitments_user_id", table_name="weekly_commitments")
    op.drop_table("weekly_commitments")
    op.drop_index("ix_program_phases_program_id", table_name="program_phases")
    op.drop_index("ix_program_phases_user_id", table_name="program_phases")
    op.drop_table("program_phases")
    op.drop_index("ix_programs_goal_id", table_name="programs")
    op.drop_index("ix_programs_user_id", table_name="programs")
    op.drop_table("programs")
    op.drop_index("ix_goal_milestones_goal_id", table_name="goal_milestones")
    op.drop_index("ix_goal_milestones_user_id", table_name="goal_milestones")
    op.drop_table("goal_milestones")
    op.drop_index("ix_goals_public_id", table_name="goals")
    op.drop_column("goals", "updated_at")
    op.drop_column("goals", "version")
    op.drop_column("goals", "allocation_minutes_week")
    op.drop_column("goals", "intensity")
    op.drop_column("goals", "deadline")
    op.drop_column("goals", "metric_unit")
    op.drop_column("goals", "target_value")
    op.drop_column("goals", "current_value")
    op.drop_column("goals", "baseline_value")
    op.drop_column("goals", "outcome_type")
    op.drop_column("goals", "life_area")
    op.drop_column("goals", "public_id")
