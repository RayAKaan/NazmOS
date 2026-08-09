"""enforce one active business per owner

Revision ID: 5f0a1b2c3d4e
Revises: 748e4f2a4e7b
Create Date: 2026-08-09

Adds a partial unique index on businesses(owner_id) WHERE is_active = true
so concurrent /businesses/bootstrap calls cannot create duplicate stores.
Existing duplicates (from the pre-index race) are deactivated, keeping the
earliest-created business active.
"""
from alembic import op

revision = "5f0a1b2c3d4e"
down_revision = "a5b6c7d8e901"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # Deactivate duplicate active businesses per owner, keeping the oldest.
    conn.exec_driver_sql(
        """
        WITH ranked AS (
            SELECT id,
                   ROW_NUMBER() OVER (
                       PARTITION BY owner_id
                       ORDER BY created_at ASC, id ASC
                   ) AS rn
            FROM businesses
            WHERE is_active = true AND owner_id IS NOT NULL
        )
        UPDATE businesses b
        SET is_active = false
        FROM ranked r
        WHERE b.id = r.id AND r.rn > 1
        """
    )

    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_businesses_active_owner "
        "ON businesses (owner_id) WHERE is_active = true"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_businesses_active_owner")
