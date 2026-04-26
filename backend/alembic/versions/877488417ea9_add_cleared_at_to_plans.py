"""add_cleared_at_to_plans

Revision ID: 877488417ea9
Revises: 3edb7a3d4579
Create Date: 2026-04-26 14:34:42.078922

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '877488417ea9'
down_revision: Union[str, Sequence[str], None] = '3edb7a3d4579'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('training_plans', sa.Column('cleared_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('training_plans', 'cleared_at')
