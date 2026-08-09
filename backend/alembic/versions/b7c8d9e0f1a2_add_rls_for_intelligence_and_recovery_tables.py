"""add rls for intelligence and recovery tables

Revision ID: b7c8d9e0f1a2
Revises: 9f8e7d6c5b4a
Create Date: 2026-08-09 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = 'b7c8d9e0f1a2'
down_revision: Union[str, None] = '9f8e7d6c5b4a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Business-scoped tables introduced after the earlier RLS migrations that were
# not yet covered.  All of these carry a NOT NULL business_id and are written
# and read through the same tenant-scoped session helpers, so they get the same
# ``app.current_tenant_id()`` isolation policy as the rest of the platform.
TENANT_TABLES = [
    "business_context",
    "business_memory",
    "event_derivations",
    "events",
    "execution_jobs",
    "feature_flag_overrides",
    "graph_entities",
    "graph_relationships",
    "intelligence_decisions",
    "memory_updates",
    "model_performance",
    "outcome_feedback",
    "plans",
    "simulations",
]

# Tables whose tenant column is not literally named ``business_id``.
CUSTOM_COLUMN_TABLES = {
    "stock_recovery_listings": "seller_business_id",
    "stock_recovery_matches": "buyer_business_id",
    "stock_recovery_events": "actor_business_id",
}

APP_ROLE = "nazmos_app"


def upgrade() -> None:
    conn = op.get_bind()

    for table in TENANT_TABLES:
        conn.execute(text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
        conn.execute(
            text(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}")
        )
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

    for table, column in CUSTOM_COLUMN_TABLES.items():
        conn.execute(text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
        conn.execute(
            text(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}")
        )
        conn.execute(
            text(
                f"""
                CREATE POLICY {table}_tenant_isolation ON {table}
                    FOR ALL
                    USING ({column} = app.current_tenant_id())
                    WITH CHECK ({column} = app.current_tenant_id())
                """
            )
        )

    # Grant DML on the newly covered tables to the restricted app role so the
    # tenant-scoped session role can continue to operate on them.
    all_tables = list(TENANT_TABLES) + list(CUSTOM_COLUMN_TABLES.keys())
    grant = ", ".join(all_tables)
    conn.execute(
        text(
            f"""
            DO $$
            BEGIN
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
                    EXECUTE 'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE {grant} TO {APP_ROLE}';
                END IF;
            END
            $$;
            """
        )
    )


def downgrade() -> None:
    conn = op.get_bind()

    all_tables = list(TENANT_TABLES) + list(CUSTOM_COLUMN_TABLES.keys())
    revoke = ", ".join(all_tables)
    conn.execute(
        text(
            f"""
            DO $$
            BEGIN
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
                    EXECUTE 'REVOKE ALL PRIVILEGES ON TABLE {revoke} FROM {APP_ROLE}';
                END IF;
            END
            $$;
            """
        )
    )

    for table in TENANT_TABLES + list(CUSTOM_COLUMN_TABLES.keys()):
        conn.execute(
            text(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}")
        )
        conn.execute(text(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY"))
