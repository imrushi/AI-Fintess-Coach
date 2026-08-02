"""add_hr_zones_to_workouts

Revision ID: a2b3c4d5e6f7
Revises: f6a7b8c9d0e1
Create Date: 2026-08-02

"""
from alembic import op
import sqlalchemy as sa

revision: str = 'a2b3c4d5e6f7'
down_revision: str = 'f6a7b8c9d0e1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("workouts") as batch_op:
        batch_op.add_column(sa.Column("hr_zone_secs_json", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("hr_zone_thresholds_json", sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("workouts") as batch_op:
        batch_op.drop_column("hr_zone_thresholds_json")
        batch_op.drop_column("hr_zone_secs_json")
