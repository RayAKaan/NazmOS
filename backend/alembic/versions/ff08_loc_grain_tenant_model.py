"""Phase 1 (canonical model): first-class Location dimension and tenant grain.

The canonical data model now treats ``(business, location, item)`` as the
inventory dimension and ``(business, location, item, transaction)`` as the sales
dimension.  Before this migration, locations were modelled as separate
``businesses`` rows (sharing an ``organization_id``) or dropped at ETL time,
which collapsed a multi-location inventory snapshot (45 rows / 15 SKUs x 3
locations) into a single per-SKU row and destroyed per-branch provenance.

This migration:
  * creates the ``locations`` tenant table,
  * adds ``location_id`` to ``inventory`` and ``transactions``,
  * makes inventory uniqueness ``(business, item, location)``-aware with a
    backward-compatible legacy partial unique index for NULL-location rows,
  * stores the merchant/POS ``source_transaction_id`` on ``transactions``
    (participates in the content-hash dedup identity, never a hard unique key —
    one invoice may legitimately span multiple SKU rows),
  * rekeys the content-hash dedup index to ``(business, location, item, hash)``
    so identical content sold at different branches no longer collapses,
  * enables tenant RLS on ``locations``.

Revision ID: ff08_loc_grain_tenant_model
Revises: ff07_rls_audit_isolation
Create Date: 2026-09-06
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

from app.database.types import UUID

# revision identifiers, used by Alembic.
revision: str = "ff08_loc_grain_tenant_model"
down_revision: Union[str, None] = "ff07_rls_audit_isolation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

APP_ROLE = "nazmos_app"

# Scan-compatible RLS coverage list (test_rls_coverage_complete recognises the
# TENANT_TABLES assignment + *_tenant_isolation CREATE POLICY).
TENANT_TABLES = ["locations"]


def upgrade() -> None:
    op.create_table(
        "locations",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("business_id", UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("code", sa.String(length=30), nullable=True),
        sa.Column("is_headquarters", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("business_id", "name", name="uq_location_business_name"),
    )
    op.create_index("idx_location_business", "locations", ["business_id"], unique=False)

    # ── inventory: location grain ─────────────────────────────────────────
    op.add_column("inventory", sa.Column("location_id", UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_inventory_location_locations", "inventory", "locations",
        ["location_id"], ["id"], ondelete="CASCADE",
    )
    op.drop_constraint("uq_inventory_business_item", "inventory", type_="unique")
    op.create_unique_constraint(
        "uq_inventory_business_item_location",
        "inventory",
        ["business_id", "item_id", "location_id"],
    )
    op.create_index(
        "uq_inventory_business_item_legacy",
        "inventory",
        ["business_id", "item_id"],
        unique=True,
        postgresql_where=sa.text("location_id IS NULL"),
    )
    op.create_index("idx_inventory_location", "inventory", ["location_id"], unique=False)

    # ── transactions: location + source provenance ────────────────────────
    op.add_column("transactions", sa.Column("location_id", UUID(as_uuid=True), nullable=True))
    op.add_column("transactions", sa.Column("source_transaction_id", sa.String(length=120), nullable=True))
    op.create_foreign_key(
        "fk_transactions_location_locations", "transactions", "locations",
        ["location_id"], ["id"], ondelete="SET NULL",
    )
    op.create_index("idx_transaction_location", "transactions", ["location_id"], unique=False)
    op.drop_index("uq_transactions_row_hash", table_name="transactions")
    op.create_index(
        "uq_transactions_row_hash",
        "transactions",
        ["business_id", "location_id", "item_id", "row_hash"],
        unique=True,
        postgresql_where=sa.text("row_hash IS NOT NULL"),
    )

    conn = op.get_bind()
    if conn.dialect.name != "postgresql":
        # RLS is PostgreSQL-only; the AST drift-guard still recognises coverage.
        return

    for table in TENANT_TABLES:
        conn.execute(text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
        conn.execute(text(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}"))
        conn.execute(
            text(
                f"""
                CREATE POLICY {table}_tenant_isolation ON {table}
                    FOR ALL
                    USING (business_id = app.current_tenant_id())
                    WITH CHECK (business_id = app.current_tenant_id())
                """
            )
        )

    conn.execute(
        text(
            f"""
            DO $$
            BEGIN
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
                    EXECUTE 'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE {", ".join(TENANT_TABLES)} TO {APP_ROLE}';
                END IF;
            END
            $$;
            """
        )
    )


def downgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name == "postgresql":
        conn.execute(
            text(
                f"""
                DO $$
                BEGIN
                    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
                        EXECUTE 'REVOKE ALL PRIVILEGES ON TABLE {", ".join(TENANT_TABLES)} FROM {APP_ROLE}';
                    END IF;
                END
                $$;
                """
            )
        )
        for table in TENANT_TABLES:
            conn.execute(text(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}"))
            conn.execute(text(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY"))

    op.drop_index("uq_transactions_row_hash", table_name="transactions")
    op.create_index(
        "uq_transactions_row_hash",
        "transactions",
        ["business_id", "row_hash"],
        unique=True,
        postgresql_where=sa.text("row_hash IS NOT NULL"),
    )
    op.drop_index("idx_transaction_location", table_name="transactions")
    op.drop_constraint("fk_transactions_location_locations", "transactions", type_="foreignkey")
    op.drop_column("transactions", "source_transaction_id")
    op.drop_column("transactions", "location_id")

    op.drop_index("idx_inventory_location", table_name="inventory")
    op.drop_index("uq_inventory_business_item_legacy", table_name="inventory")
    op.drop_constraint("uq_inventory_business_item_location", "inventory", type_="unique")
    op.create_unique_constraint(
        "uq_inventory_business_item", "inventory", ["business_id", "item_id"]
    )
    op.drop_constraint("fk_inventory_location_locations", "inventory", type_="foreignkey")
    op.drop_column("inventory", "location_id")

    op.drop_index("idx_location_business", table_name="locations")
    op.drop_table("locations")