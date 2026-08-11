"""add bounded path read indexes

Revision ID: c3d2e1f4a5b6
Revises: b2a1d0f3e422
Create Date: 2026-08-11 18:00:00.000000
"""

from typing import Sequence, Union

from alembic import op


revision: str = "c3d2e1f4a5b6"
down_revision: Union[str, None] = "b2a1d0f3e422"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_evidence_user_goal_occurred_id",
        "evidence",
        ["user_id", "goal_id", "occurred_at", "id"],
    )
    op.create_index(
        "ix_goal_progress_user_goal_as_of_created_id",
        "goal_progress_snapshots",
        ["user_id", "goal_id", "as_of", "created_at", "id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_goal_progress_user_goal_as_of_created_id",
        table_name="goal_progress_snapshots",
    )
    op.drop_index(
        "ix_evidence_user_goal_occurred_id",
        table_name="evidence",
    )
