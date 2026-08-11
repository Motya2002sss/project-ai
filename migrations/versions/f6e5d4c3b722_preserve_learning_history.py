"""preserve learning sessions and remove redundant budget uniqueness

Revision ID: f6e5d4c3b722
Revises: e5d4c3b2a611
Create Date: 2026-08-11 21:00:00.000000
"""

from typing import Sequence, Union

from alembic import op


revision: str = "f6e5d4c3b722"
down_revision: Union[str, None] = "e5d4c3b2a611"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint(
        "learning_sessions_learning_resource_id_fkey",
        "learning_sessions",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_learning_sessions_learning_resource_id",
        "learning_sessions",
        "learning_resources",
        ["learning_resource_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.drop_constraint(
        "resource_budgets_user_id_key",
        "resource_budgets",
        type_="unique",
    )


def downgrade() -> None:
    op.create_unique_constraint(
        "resource_budgets_user_id_key",
        "resource_budgets",
        ["user_id"],
    )
    op.drop_constraint(
        "fk_learning_sessions_learning_resource_id",
        "learning_sessions",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "learning_sessions_learning_resource_id_fkey",
        "learning_sessions",
        "learning_resources",
        ["learning_resource_id"],
        ["id"],
        ondelete="CASCADE",
    )
