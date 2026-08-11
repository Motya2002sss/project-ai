"""add resource budgets and onboarding previews

Revision ID: a8e7f6d5c4b3
Revises: a2b1c3d4e5f6
Create Date: 2026-08-11 14:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a8e7f6d5c4b3"
down_revision: Union[str, None] = "a2b1c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "resource_budgets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("weekly_available_minutes", sa.Integer(), nullable=False),
        sa.Column("available_days", sa.JSON(), nullable=False),
        sa.Column("minimum_minutes", sa.Integer(), nullable=False),
        sa.Column("comfortable_minutes", sa.Integer(), nullable=False),
        sa.Column("maximum_minutes", sa.Integer(), nullable=False),
        sa.Column("free_evenings", sa.JSON(), nullable=False),
        sa.Column("preferred_windows", sa.JSON(), nullable=False),
        sa.Column("money_budget", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("conflict_priority", sa.String(length=255), nullable=True),
        sa.Column("reserve_percent", sa.Integer(), nullable=False),
        sa.Column("allocatable_minutes", sa.Integer(), nullable=False),
        sa.Column("allocation", sa.JSON(), nullable=False),
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
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )
    op.create_index(
        "ix_resource_budgets_user_id", "resource_budgets", ["user_id"], unique=True
    )

    op.create_table(
        "onboarding_previews",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("narrative", sa.Text(), nullable=True),
        sa.Column("narrative_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("structured_summary", sa.JSON(), nullable=False),
        sa.Column("goal_candidates", sa.JSON(), nullable=False),
        sa.Column("resource_budget", sa.JSON(), nullable=False),
        sa.Column("allocation", sa.JSON(), nullable=False),
        sa.Column("clarification", sa.JSON(), nullable=True),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_onboarding_previews_user_id",
        "onboarding_previews",
        ["user_id"],
    )
    op.create_index(
        "ix_onboarding_previews_status", "onboarding_previews", ["status"]
    )
    op.create_index(
        "ix_onboarding_previews_narrative_expires_at",
        "onboarding_previews",
        ["narrative_expires_at"],
    )

    op.create_table(
        "onboarding_request_receipts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("preview_id", sa.Uuid(), nullable=False),
        sa.Column("request_id", sa.String(length=128), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["preview_id"], ["onboarding_previews.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "request_id", name="uq_onboarding_request_user_request"
        ),
    )
    op.create_index(
        "ix_onboarding_request_receipts_user_id",
        "onboarding_request_receipts",
        ["user_id"],
    )
    op.create_index(
        "ix_onboarding_request_receipts_preview_id",
        "onboarding_request_receipts",
        ["preview_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_onboarding_request_receipts_preview_id",
        table_name="onboarding_request_receipts",
    )
    op.drop_index(
        "ix_onboarding_request_receipts_user_id",
        table_name="onboarding_request_receipts",
    )
    op.drop_table("onboarding_request_receipts")
    op.drop_index(
        "ix_onboarding_previews_narrative_expires_at",
        table_name="onboarding_previews",
    )
    op.drop_index("ix_onboarding_previews_status", table_name="onboarding_previews")
    op.drop_index("ix_onboarding_previews_user_id", table_name="onboarding_previews")
    op.drop_table("onboarding_previews")
    op.drop_index("ix_resource_budgets_user_id", table_name="resource_budgets")
    op.drop_table("resource_budgets")
