"""add minimal routines

Revision ID: d6f4a82c1b09
Revises: c4d2e7a91f30
Create Date: 2026-08-04 00:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d6f4a82c1b09"
down_revision: Union[str, None] = "c4d2e7a91f30"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "routines",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("cadence", sa.String(length=32), nullable=False),
        sa.Column("weekdays", sa.JSON(), nullable=False),
        sa.Column("fixed_time", sa.Time(), nullable=True),
        sa.Column("preferred_window", sa.String(length=32), nullable=True),
        sa.Column("estimated_minutes", sa.Integer(), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_routines_user_id"), "routines", ["user_id"], unique=False)
    op.add_column("tasks", sa.Column("routine_id", sa.Integer(), nullable=True))
    op.add_column("tasks", sa.Column("occurrence_date", sa.Date(), nullable=True))
    op.create_foreign_key(
        "fk_tasks_routine_id_routines",
        "tasks",
        "routines",
        ["routine_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(op.f("ix_tasks_routine_id"), "tasks", ["routine_id"], unique=False)
    op.create_unique_constraint(
        "uq_tasks_routine_occurrence",
        "tasks",
        ["routine_id", "occurrence_date"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_tasks_routine_occurrence", "tasks", type_="unique")
    op.drop_index(op.f("ix_tasks_routine_id"), table_name="tasks")
    op.drop_constraint("fk_tasks_routine_id_routines", "tasks", type_="foreignkey")
    op.drop_column("tasks", "occurrence_date")
    op.drop_column("tasks", "routine_id")
    op.drop_index(op.f("ix_routines_user_id"), table_name="routines")
    op.drop_table("routines")
