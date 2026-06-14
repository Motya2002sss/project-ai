"""add task target date

Revision ID: de5d40004c9d
Revises: 23c4905f352b
Create Date: 2026-06-13 00:41:44.830642

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'de5d40004c9d'
down_revision: Union[str, None] = '23c4905f352b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("tasks", sa.Column("target_date", sa.Date(), nullable=True))
    op.execute("UPDATE tasks SET target_date = CURRENT_DATE WHERE target_date IS NULL")
    op.alter_column("tasks", "target_date", nullable=False)
    op.create_index(op.f("ix_tasks_target_date"), "tasks", ["target_date"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_tasks_target_date"), table_name="tasks")
    op.drop_column("tasks", "target_date")
