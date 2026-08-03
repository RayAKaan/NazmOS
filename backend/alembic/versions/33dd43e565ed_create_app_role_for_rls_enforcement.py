"""create app role for rls enforcement

Revision ID: 33dd43e565ed
Revises: a25a714a2de8
Create Date: 2026-08-03 17:13:34.831007

"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = '33dd43e565ed'
down_revision: Union[str, None] = 'a25a714a2de8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


APP_ROLE = "nazmos_app"

# Tables that carry a direct business_id column and are scoped to a single
# merchant.  These must match the TENANT_TABLES list in migration
# a25a714a2de8_add_tenant_rls_policies.py.
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

    # Create the restricted application role if it does not already exist.
    # NOLOGIN because the application connects as the owner and uses SET ROLE.
    conn.execute(
        text(
            f"""
            DO $$
            BEGIN
                CREATE ROLE {APP_ROLE} NOLOGIN;
            EXCEPTION WHEN duplicate_object THEN
                RAISE NOTICE 'Role {APP_ROLE} already exists, skipping create.';
            END
            $$;
            """
        )
    )

    # Allow the migration user (and the application owner connection) to
    # assume the restricted role.
    conn.execute(text(f"GRANT {APP_ROLE} TO CURRENT_USER"))

    # Schema access.
    conn.execute(text(f"GRANT USAGE ON SCHEMA public TO {APP_ROLE}"))
    conn.execute(text(f"GRANT USAGE ON SCHEMA app TO {APP_ROLE}"))

    # Table DML access.  RLS policies still restrict rows to the current
    # tenant set by SET LOCAL app.current_tenant_id.
    for table in TENANT_TABLES:
        conn.execute(
            text(
                f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE {table} TO {APP_ROLE}"
            )
        )

    # Sequence access for any integer primary keys / counters.
    conn.execute(
        text(
            f"""
            DO $$
            DECLARE seq_name text;
            BEGIN
                FOR seq_name IN (
                    SELECT sequence_name
                    FROM information_schema.sequences
                    WHERE sequence_schema = 'public'
                ) LOOP
                    EXECUTE format('GRANT USAGE, SELECT ON SEQUENCE %I TO {APP_ROLE}', seq_name);
                END LOOP;
            END
            $$;
            """
        )
    )


def downgrade() -> None:
    conn = op.get_bind()

    for table in TENANT_TABLES:
        conn.execute(
            text(
                f"REVOKE ALL PRIVILEGES ON TABLE {table} FROM {APP_ROLE}"
            )
        )

    conn.execute(text(f"REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public FROM {APP_ROLE}"))
    conn.execute(text(f"REVOKE USAGE ON SCHEMA app FROM {APP_ROLE}"))
    conn.execute(text(f"REVOKE USAGE ON SCHEMA public FROM {APP_ROLE}"))
    conn.execute(text(f"REVOKE {APP_ROLE} FROM CURRENT_USER"))
    conn.execute(text(f"DROP ROLE IF EXISTS {APP_ROLE}"))
