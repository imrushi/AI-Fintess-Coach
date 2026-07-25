"""add_fitness_level_history

Revision ID: f6a7b8c9d0e1
Revises: 0cee53f2cc34
Create Date: 2026-07-25 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f6a7b8c9d0e1'
down_revision: Union[str, Sequence[str], None] = '0cee53f2cc34'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('user_profiles', schema=None) as batch_op:
        batch_op.add_column(sa.Column('fitness_level_locked', sa.Boolean(), nullable=False, server_default='0'))

    # Existing users who already have a fitness_level set are treated as manually locked.
    op.execute(
        "UPDATE user_profiles SET fitness_level_locked = 1 WHERE fitness_level IS NOT NULL"
    )

    op.create_table(
        'fitness_level_history',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('old_level', sa.String(), nullable=True),
        sa.Column('new_level', sa.String(), nullable=False),
        sa.Column('reason', sa.String(), nullable=True),
        sa.Column('source', sa.String(), nullable=False, server_default='auto'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    op.drop_table('fitness_level_history')
    with op.batch_alter_table('user_profiles', schema=None) as batch_op:
        batch_op.drop_column('fitness_level_locked')
