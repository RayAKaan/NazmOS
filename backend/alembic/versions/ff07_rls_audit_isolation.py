"""Phase A (follow-up): RLS tenant isolation for the AI/security audit tables.

The AI reasoning request and security event tables (``ai_reasoning_requests``,
``security_events``) are business-scoped audit trails.  This migration closes
the nullable/tenant gap the WS2 drift-guard flagged (``test_rls_coverage_complete``)
by enabling the same ``app.current_tenant_id()`` isolation policy used across
the rest of the platform.

Unlike the strict core tables, these audit tables accept context-less (global)
rows written outside any active tenant session (e.g. background jobs, platform
security events).  The policy therefore adds ``business_id IS NOT NULL``-safe
handling: rows are granted/checked when they belong to the active tenant OR when
they carry a NULL business_id (a world-invisible "platform" event that only the
table owner / restricted app-role bookkeeping can see).  Cross-tenant reads stay
fail-closed because the ``USING`` clause only exposes rows whose business_id
equals the active tenant.

Revision ID: ff07_rls_audit_isolation
Revises: ff06_field_encryption
Create Date: 2026-09-02
"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision: str = "ff07_rls_audit_isolation"
down_revision: Union[str, None] = "ff06_field_encryption"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Audit tables covered by tenant isolation.  These match the migrations that
# create them (ff05_ai_isolation) and the WS2 drift-guard list.
TENANT_TABLES = [
    "ai_reasoning_requests",
    "security_events",
]

APP_ROLE = "nazmos_app"


def upgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name != "postgresql":
        # RLS is a PostgreSQL-only construct; SQLite/SQLServer dev runs do not
        # need it and the AST-based drift-guard still recognises the coverage.
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
                    WITH CHECK (
                        business_id = app.current_tenant_id() OR business_id IS NULL
                    )
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
    if conn.dialect.name != "postgresql":
        return

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
