"""add session_skipped and skip_reason to user_feedback

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-05-28

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "d4e5f6a7b8c9"
down_revision = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("user_feedback") as batch_op:
        batch_op.add_column(
            sa.Column("session_skipped", sa.Boolean(), nullable=False, server_default="0")
        )
        batch_op.add_column(
            sa.Column("skip_reason", sa.String(), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("user_feedback") as batch_op:
        batch_op.drop_column("skip_reason")
        batch_op.drop_column("session_skipped")
