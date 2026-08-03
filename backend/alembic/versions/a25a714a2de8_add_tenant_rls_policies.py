"""add_tenant_rls_policies

Revision ID: a25a714a2de8
Revises: fbcd840f72b7
Create Date: 2026-08-03 16:26:49.045228

"""
from typing import Sequence, Union
from alembic import op
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = 'a25a714a2de8'
down_revision: Union[str, None] = 'fbcd840f72b7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Tables that carry a direct business_id column and are scoped to a single
# merchant.  Organization-only tables (e.g. team_members with a nullable
# business_id) are intentionally excluded from business_id RLS here.
TENANT_TABLES = [
    "agent_actions",
    "analytics_cache",
    "audit_log",
    "autonomy_policies",
    "billing_events",
    "categories",
    "chat_sessions",
    "daily_summaries",
    "decision_log",
    "enabled_modules",
    "executed_actions",
    "forecast_cache",
    "inventory",
    "items",
    "money_audit_actions",
    "money_audits",
    "notification_preferences",
    "notifications",
    "pharmacy_lots",
    "pos_connections",
    "pricing_recommendations",
    "pricing_rules",
    "purchase_orders",
    "recipes",
    "recovery_match_settings",
    "reports",
    "subscriptions",
    "transactions",
    "uploaded_files",
]


def upgrade() -> None:
    conn = op.get_bind()

    conn.execute(text("CREATE SCHEMA IF NOT EXISTS app"))

    conn.execute(
        text("""
            CREATE OR REPLACE FUNCTION app.current_tenant_id() RETURNS uuid AS $$
            DECLARE
                tenant_id text;
            BEGIN
                tenant_id := current_setting('app.current_tenant_id', true);
                IF tenant_id IS NULL OR tenant_id = '' THEN
                    RETURN NULL;
                END IF;
                RETURN tenant_id::uuid;
            EXCEPTION WHEN OTHERS THEN
                RETURN NULL;
            END;
            $$ LANGUAGE plpgsql STABLE SECURITY DEFINER
        """)
    )

    for table in TENANT_TABLES:
        conn.execute(text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
        conn.execute(
            text(
                f"""
                DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}
                """
            )
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


def downgrade() -> None:
    conn = op.get_bind()

    for table in TENANT_TABLES:
        conn.execute(
            text(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}")
        )
        conn.execute(text(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY"))

    conn.execute(text("DROP FUNCTION IF EXISTS app.current_tenant_id()"))
    conn.execute(text("DROP SCHEMA IF EXISTS app"))
