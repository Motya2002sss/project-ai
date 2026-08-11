"""enforce one task placement per day plan

Revision ID: a7f6e5d4c833
Revises: f6e5d4c3b722
Create Date: 2026-08-11 22:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a7f6e5d4c833"
down_revision: Union[str, None] = "f6e5d4c3b722"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


CONSTRAINT_NAME = "uq_plan_items_day_plan_task"


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        bind.execute(
            sa.text("LOCK TABLE plan_items IN SHARE ROW EXCLUSIVE MODE")
        )

    duplicates = bind.execute(
        sa.text(
            """
            SELECT day_plan_id, task_id, COUNT(*) AS duplicate_count
            FROM plan_items
            WHERE task_id IS NOT NULL
            GROUP BY day_plan_id, task_id
            HAVING COUNT(*) > 1
            ORDER BY day_plan_id ASC, task_id ASC
            LIMIT 20
            """
        )
    ).mappings().all()
    if duplicates:
        groups = "; ".join(
            "day_plan_id={day_plan_id}, task_id={task_id}, count={duplicate_count}".format(
                **row
            )
            for row in duplicates
        )
        raise RuntimeError(
            "Refusing migration a7f6e5d4c833: duplicate non-null task "
            "placements exist. No rows were changed. Explicitly resolve each "
            "duplicate group using authoritative product evidence, then rerun "
            f"the migration. Duplicate groups (first 20): {groups}"
        )

    with op.batch_alter_table("plan_items") as batch_op:
        batch_op.create_unique_constraint(
            CONSTRAINT_NAME,
            ["day_plan_id", "task_id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("plan_items") as batch_op:
        batch_op.drop_constraint(CONSTRAINT_NAME, type_="unique")
