"""add platform operator flag to users

Revision ID: 9f8e7d6c5b4a
Revises: 5f0a1b2c3d4e
Create Date: 2026-08-09

Adds an explicit ``is_platform_operator`` boolean to ``users`` so the
NazmOS founder/operator identity is a real, auditable DB flag instead of a
role string that every registered merchant also holds. Capabilities such as
``can_view_ops_console`` are computed from this flag OR the FOUNDER_EMAILS
environment allowlist (see app/services/capabilities_service.py).
"""
from alembic import op

revision = "9f8e7d6c5b4a"
down_revision = "5f0a1b2c3d4e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE users ADD COLUMN is_platform_operator BOOLEAN NOT NULL DEFAULT false"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE users DROP COLUMN is_platform_operator")
