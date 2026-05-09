"""add_current_volume_to_profile

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-05-08 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("user_profiles") as batch_op:
        batch_op.add_column(sa.Column("current_swim_km_week", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("current_bike_km_week", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("current_run_km_week", sa.Float(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("user_profiles") as batch_op:
        batch_op.drop_column("current_run_km_week")
        batch_op.drop_column("current_bike_km_week")
        batch_op.drop_column("current_swim_km_week")
