"""Provider-neutral LLM usage field

Revision ID: 007
Revises: 006
Create Date: 2026-07-15

Adds llm_usage_tokens to businesses for OpenRouter/model-router usage tracking.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("businesses", sa.Column("llm_usage_tokens", sa.BigInteger(), server_default="0", nullable=True))


def downgrade() -> None:
    op.drop_column("businesses", "llm_usage_tokens")
