"""add_dob_lthr_to_profile

Revision ID: a1b2c3d4e5f6
Revises: 3edb7a3d4579
Create Date: 2026-04-27 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '877488417ea9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("user_profiles") as batch_op:
        batch_op.add_column(sa.Column("date_of_birth", sa.Date(), nullable=True))
        batch_op.add_column(sa.Column("lthr", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("user_profiles") as batch_op:
        batch_op.drop_column("lthr")
        batch_op.drop_column("date_of_birth")
