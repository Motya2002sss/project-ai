"""add calendar intervals temporary modes and plan changes

Revision ID: e5d4c3b2a611
Revises: d4c3f2b5a644
Create Date: 2026-08-11 20:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e5d4c3b2a611"
down_revision: Union[str, None] = "d4c3f2b5a644"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "calendar_busy_blocks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("device_id", sa.String(length=128), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("calendar_external_id", sa.String(length=255), nullable=False),
        sa.Column("external_id", sa.String(length=255), nullable=False),
        sa.Column(
            "occurrence_external_id", sa.String(length=255), nullable=False
        ),
        sa.Column(
            "occurrence_start", sa.DateTime(timezone=True), nullable=False
        ),
        sa.Column("occurrence_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("device_timezone", sa.String(length=64), nullable=False),
        sa.Column("source_revision", sa.String(length=128), nullable=False),
        sa.Column("last_seen_client_revision", sa.Integer(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint(
            "occurrence_end > occurrence_start",
            name="ck_calendar_busy_positive_interval",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "device_id",
            "provider",
            "calendar_external_id",
            "occurrence_external_id",
            name="uq_calendar_busy_stable_occurrence",
        ),
    )
    op.create_index(
        "ix_calendar_busy_blocks_user_id",
        "calendar_busy_blocks",
        ["user_id"],
    )
    op.create_index(
        "ix_calendar_busy_user_interval_deleted",
        "calendar_busy_blocks",
        ["user_id", "occurrence_start", "occurrence_end", "deleted_at"],
    )
    op.create_index(
        "ix_calendar_busy_sync_scope_interval",
        "calendar_busy_blocks",
        [
            "user_id",
            "device_id",
            "provider",
            "calendar_external_id",
            "occurrence_start",
            "occurrence_end",
            "deleted_at",
        ],
    )

    op.create_table(
        "calendar_sync_states",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("device_id", sa.String(length=128), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("client_revision", sa.Integer(), nullable=False),
        sa.Column("range_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("range_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("device_timezone", sa.String(length=64), nullable=False),
        sa.Column("covered_calendar_ids", sa.JSON(), nullable=False),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=False),
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
        sa.CheckConstraint(
            "version >= 1 AND client_revision >= 1",
            name="ck_calendar_sync_state_versions",
        ),
        sa.CheckConstraint(
            "range_end > range_start",
            name="ck_calendar_sync_state_positive_range",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "device_id",
            "provider",
            name="uq_calendar_sync_state_scope",
        ),
    )
    op.create_index(
        "ix_calendar_sync_states_user_id",
        "calendar_sync_states",
        ["user_id"],
    )
    op.create_index(
        "ix_calendar_sync_states_user_device_provider",
        "calendar_sync_states",
        ["user_id", "device_id", "provider"],
    )

    op.create_table(
        "temporary_life_modes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("request_id", sa.String(length=128), nullable=False),
        sa.Column("mode", sa.String(length=32), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("constraints", sa.JSON(), nullable=False),
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
        sa.CheckConstraint(
            "ends_at > starts_at",
            name="ck_temporary_mode_positive_interval",
        ),
        sa.CheckConstraint(
            "mode IN ('normal', 'workload', 'recovery', 'sick', 'travel', "
            "'vacation', 'low_sleep', 'focus_sprint')",
            name="ck_temporary_mode_kind",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'cancelled', 'completed')",
            name="ck_temporary_mode_status",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "request_id", name="uq_temporary_mode_user_request"
        ),
    )
    op.create_index(
        "ix_temporary_life_modes_user_id",
        "temporary_life_modes",
        ["user_id"],
    )
    op.create_index(
        "ix_temporary_modes_user_interval",
        "temporary_life_modes",
        ["user_id", "starts_at", "ends_at"],
    )

    op.create_table(
        "plan_changes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("request_id", sa.String(length=128), nullable=False),
        sa.Column("reason", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("base_versions", sa.JSON(), nullable=False),
        sa.Column("result_versions", sa.JSON(), nullable=False),
        sa.Column("affected_dates", sa.JSON(), nullable=False),
        sa.Column("forward_payload", sa.JSON(), nullable=False),
        sa.Column("inverse_payload", sa.JSON(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("undone_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('applied', 'undone')",
            name="ck_plan_change_status",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "request_id", name="uq_plan_change_user_request"
        ),
    )
    op.create_index("ix_plan_changes_user_id", "plan_changes", ["user_id"])
    op.create_index(
        "ix_plan_changes_expires_at", "plan_changes", ["expires_at"]
    )
    op.create_index(
        "ix_plan_changes_user_created_id",
        "plan_changes",
        ["user_id", "created_at", "id"],
    )
    op.create_index(
        "ix_plan_changes_user_status_expires",
        "plan_changes",
        ["user_id", "status", "expires_at"],
    )


def downgrade() -> None:
    op.drop_table("calendar_sync_states")
    op.drop_table("plan_changes")
    op.drop_table("temporary_life_modes")
    op.drop_table("calendar_busy_blocks")
