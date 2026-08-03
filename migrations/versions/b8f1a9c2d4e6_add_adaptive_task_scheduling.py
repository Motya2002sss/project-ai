"""add adaptive task scheduling

Revision ID: b8f1a9c2d4e6
Revises: 7a9d4b1c2e33
Create Date: 2026-08-03 23:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b8f1a9c2d4e6"
down_revision: Union[str, None] = "7a9d4b1c2e33"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tasks",
        sa.Column(
            "scheduling_type",
            sa.String(length=32),
            server_default="flexible",
            nullable=False,
        ),
    )
    op.add_column("tasks", sa.Column("fixed_start", sa.Time(), nullable=True))
    op.add_column("tasks", sa.Column("fixed_end", sa.Time(), nullable=True))
    op.add_column("tasks", sa.Column("preferred_window", sa.String(length=32), nullable=True))
    op.add_column("tasks", sa.Column("earliest_start", sa.Time(), nullable=True))
    op.add_column("tasks", sa.Column("latest_end", sa.Time(), nullable=True))
    op.add_column(
        "tasks",
        sa.Column("is_locked", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.add_column(
        "plan_items",
        sa.Column("unscheduled_reason", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("plan_items", "unscheduled_reason")
    op.drop_column("tasks", "is_locked")
    op.drop_column("tasks", "latest_end")
    op.drop_column("tasks", "earliest_start")
    op.drop_column("tasks", "preferred_window")
    op.drop_column("tasks", "fixed_end")
    op.drop_column("tasks", "fixed_start")
    op.drop_column("tasks", "scheduling_type")
