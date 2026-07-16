"""Runtime tables missing from initial schema

Revision ID: 002
Revises: 001
Create Date: 2026-07-06

Restores runtime tables represented in app.database.models but missing from the
Alembic chain. 003 depends on decision_log.
"""
from typing import Sequence, Union
from alembic import op

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

RUNTIME_TABLES = [
    "uploaded_files",
    "chat_sessions",
    "chat_messages",
    "forecast_cache",
    "decision_log",
    "suppliers",
    "agent_actions",
    "autonomy_policies",
    "purchase_orders",
    "pharmacy_lots",
    "sfda_recalls",
    "recipes",
    "parts_compatibility",
]


def upgrade() -> None:
    from app.database.models import Base
    bind = op.get_bind()
    tables = [Base.metadata.tables[name] for name in RUNTIME_TABLES]
    Base.metadata.create_all(bind=bind, tables=tables, checkfirst=True)


def downgrade() -> None:
    for name in reversed(RUNTIME_TABLES):
        op.execute(f'DROP TABLE IF EXISTS "{name}" CASCADE')
