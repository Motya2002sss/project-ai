"""add single-use auth challenges

Revision ID: a2b1c3d4e5f6
Revises: a1f0c9e2d311
Create Date: 2026-08-11 12:30:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a2b1c3d4e5f6"
down_revision: Union[str, None] = "a1f0c9e2d311"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "auth_challenges",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("state_hash", sa.String(length=64), nullable=False),
        sa.Column("nonce_hash", sa.String(length=64), nullable=False),
        sa.Column("device_id", sa.String(length=128), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_auth_challenges_state_hash",
        "auth_challenges",
        ["state_hash"],
        unique=True,
    )
    op.create_index(
        "ix_auth_challenges_nonce_hash",
        "auth_challenges",
        ["nonce_hash"],
        unique=True,
    )
    op.create_index(
        "ix_auth_challenges_expires_at",
        "auth_challenges",
        ["expires_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_auth_challenges_expires_at", table_name="auth_challenges")
    op.drop_index("ix_auth_challenges_nonce_hash", table_name="auth_challenges")
    op.drop_index("ix_auth_challenges_state_hash", table_name="auth_challenges")
    op.drop_table("auth_challenges")
