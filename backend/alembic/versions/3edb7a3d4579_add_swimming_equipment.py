"""add_swimming_equipment

Revision ID: 3edb7a3d4579
Revises: ff8a37d02522
Create Date: 2026-04-25 21:40:58.477083

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3edb7a3d4579'
down_revision: Union[str, Sequence[str], None] = 'ff8a37d02522'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('user_profiles') as batch_op:
        batch_op.add_column(sa.Column('swim_equipment', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('swim_strokes', sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('user_profiles') as batch_op:
        batch_op.drop_column('swim_strokes')
        batch_op.drop_column('swim_equipment')
