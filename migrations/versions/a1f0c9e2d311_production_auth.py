"""add production auth identities and sessions

Revision ID: a1f0c9e2d311
Revises: e7a31c4d8f20
Create Date: 2026-08-11 12:00:00.000000
"""

from typing import Sequence, Union
from uuid import uuid4

from alembic import op
import sqlalchemy as sa


revision: str = "a1f0c9e2d311"
down_revision: Union[str, None] = "e7a31c4d8f20"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("public_id", sa.Uuid(), nullable=True))
    op.add_column("users", sa.Column("email", sa.String(length=320), nullable=True))
    op.add_column(
        "users",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    connection = op.get_bind()
    user_ids = connection.execute(sa.text("SELECT id FROM users")).scalars()
    for user_id in user_ids:
        connection.execute(
            sa.text("UPDATE users SET public_id = :public_id WHERE id = :user_id"),
            {"public_id": uuid4(), "user_id": user_id},
        )

    op.alter_column("users", "public_id", nullable=False)
    op.create_index("ix_users_public_id", "users", ["public_id"], unique=True)

    op.create_table(
        "auth_identities",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "last_authenticated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "provider", "subject", name="uq_auth_identities_provider_subject"
        ),
    )
    op.create_index(
        "ix_auth_identities_user_id", "auth_identities", ["user_id"], unique=False
    )

    op.create_table(
        "app_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("family_id", sa.Uuid(), nullable=False),
        sa.Column("parent_session_id", sa.Uuid(), nullable=True),
        sa.Column("access_token_hash", sa.String(length=64), nullable=False),
        sa.Column("refresh_token_hash", sa.String(length=64), nullable=False),
        sa.Column("access_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("refresh_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("device_id", sa.String(length=128), nullable=True),
        sa.Column("device_name", sa.String(length=128), nullable=True),
        sa.Column("platform", sa.String(length=32), nullable=True),
        sa.Column("os_version", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("rotated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reuse_detected_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["parent_session_id"], ["app_sessions.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_app_sessions_user_id", "app_sessions", ["user_id"])
    op.create_index("ix_app_sessions_family_id", "app_sessions", ["family_id"])
    op.create_index(
        "ix_app_sessions_access_token_hash",
        "app_sessions",
        ["access_token_hash"],
        unique=True,
    )
    op.create_index(
        "ix_app_sessions_refresh_token_hash",
        "app_sessions",
        ["refresh_token_hash"],
        unique=True,
    )
    op.create_index(
        "ix_app_sessions_access_expires_at", "app_sessions", ["access_expires_at"]
    )
    op.create_index(
        "ix_app_sessions_refresh_expires_at", "app_sessions", ["refresh_expires_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_app_sessions_refresh_expires_at", table_name="app_sessions")
    op.drop_index("ix_app_sessions_access_expires_at", table_name="app_sessions")
    op.drop_index("ix_app_sessions_refresh_token_hash", table_name="app_sessions")
    op.drop_index("ix_app_sessions_access_token_hash", table_name="app_sessions")
    op.drop_index("ix_app_sessions_family_id", table_name="app_sessions")
    op.drop_index("ix_app_sessions_user_id", table_name="app_sessions")
    op.drop_table("app_sessions")
    op.drop_index("ix_auth_identities_user_id", table_name="auth_identities")
    op.drop_table("auth_identities")
    op.drop_index("ix_users_public_id", table_name="users")
    op.drop_column("users", "updated_at")
    op.drop_column("users", "email")
    op.drop_column("users", "public_id")
