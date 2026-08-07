"""add day work availability

Revision ID: e7a31c4d8f20
Revises: d6f4a82c1b09
Create Date: 2026-08-04 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e7a31c4d8f20"
down_revision: Union[str, None] = "d6f4a82c1b09"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("day_plans", sa.Column("work_override_mode", sa.String(length=16), nullable=True))
    op.add_column("day_plans", sa.Column("work_start_time", sa.Time(), nullable=True))
    op.add_column("day_plans", sa.Column("work_end_time", sa.Time(), nullable=True))


def downgrade() -> None:
    op.drop_column("day_plans", "work_end_time")
    op.drop_column("day_plans", "work_start_time")
    op.drop_column("day_plans", "work_override_mode")
