"""add_training_plans_feedback

Revision ID: ff8a37d02522
Revises: 2782f156b3f1
Create Date: 2026-04-25 16:19:40.100312

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ff8a37d02522'
down_revision: Union[str, Sequence[str], None] = '2782f156b3f1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'training_plans',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('generated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('valid_from', sa.Date(), nullable=False),
        sa.Column('valid_to', sa.Date(), nullable=False),
        sa.Column('plan_json', sa.String(), nullable=False),
        sa.Column('readiness_report_id', sa.String(), nullable=True),
        sa.Column('readiness_score', sa.Integer(), nullable=True),
        sa.Column('training_gate', sa.String(), nullable=True),
        sa.Column('override_applied', sa.String(), nullable=True),
        sa.Column('model_used', sa.String(), nullable=True),
        sa.Column('tokens_in', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('tokens_out', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('is_current', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.ForeignKeyConstraint(['readiness_report_id'], ['readiness_reports.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'valid_from', name='uq_training_plan_user_from'),
    )


def downgrade() -> None:
    op.drop_table('training_plans')
