"""Phase B (WS2) — Extend RLS to the core business-services tenant tables.

These merchant-scoped tables were created before or alongside the RLS
migrations but never received policies or app-role grants:

    agent_runs, audit_runs, business_goals, constraint_blocks, findings,
    goal_progress_history, impact_ledger, learned_outcomes, pilot_baselines

All nine carry a NOT NULL business_id and are written/read exclusively through
tenant-scoped services, so the standard ``business_id = app.current_tenant_id()``
isolation policy matches their data model exactly.

Why NOT these five (nullable/cross-tenant reads are documented debt in
``tests/test_rls_coverage_complete.py``, WS2): team_members, team_invitations,
supplier_prices, partner_referrals, idempotency_keys.  team_members backs the
cross-tenant "which businesses does this user belong to" lookup, and the rest
have a nullable business_id, so they require tenant-column normalization before
RLS can be enabled safely.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


revision: str = "phase_b_rls_core_services"
down_revision: Union[str, None] = "phase6_pilot_baseline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TENANT_TABLES = [
    "agent_runs",
    "audit_runs",
    "business_goals",
    "constraint_blocks",
    "findings",
    "goal_progress_history",
    "impact_ledger",
    "learned_outcomes",
    "pilot_baselines",
]

APP_ROLE = "nazmos_app"


def upgrade() -> None:
    conn = op.get_bind()

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

    # Grant DML on the newly covered tables to the restricted app role if it exists.
    grants = ", ".join(TENANT_TABLES)
    conn.execute(
        text(
            f"""
            DO $$
            BEGIN
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
                    EXECUTE 'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE {grants} TO {APP_ROLE}';
                END IF;
            END
            $$;
            """
        )
    )


def downgrade() -> None:
    conn = op.get_bind()

    revokes = ", ".join(TENANT_TABLES)
    conn.execute(
        text(
            f"""
            DO $$
            BEGIN
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
                    EXECUTE 'REVOKE ALL PRIVILEGES ON TABLE {revokes} FROM {APP_ROLE}';
                END IF;
            END
            $$;
            """
        )
    )

    for table in TENANT_TABLES:
        conn.execute(
            text(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}")
        )
        conn.execute(text(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY"))