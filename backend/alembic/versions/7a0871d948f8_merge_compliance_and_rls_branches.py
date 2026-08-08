"""merge compliance and rls branches

Revision ID: 7a0871d948f8
Revises: 7599266ca47c, 33dd43e565ed
Create Date: 2026-08-05 14:00:27.252567

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7a0871d948f8'
down_revision: Union[str, None] = ('7599266ca47c', '33dd43e565ed')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
