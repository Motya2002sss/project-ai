"""add user external id

Revision ID: 7a9d4b1c2e33
Revises: de5d40004c9d
Create Date: 2026-06-18 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "7a9d4b1c2e33"
down_revision: Union[str, None] = "de5d40004c9d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("external_id", sa.String(length=255), nullable=True))
    op.create_index(op.f("ix_users_external_id"), "users", ["external_id"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_users_external_id"), table_name="users")
    op.drop_column("users", "external_id")
