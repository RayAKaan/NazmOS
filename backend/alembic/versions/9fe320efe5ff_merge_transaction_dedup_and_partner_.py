"""merge transaction dedup and partner program branches

Revision ID: 9fe320efe5ff
Revises: e6f8a0c2b4d6, e8a1b2c3d4e5
Create Date: 2026-08-08 14:29:16.089184

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9fe320efe5ff'
down_revision: Union[str, None] = ('e6f8a0c2b4d6', 'e8a1b2c3d4e5')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
