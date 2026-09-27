"""Phase 4D — scanner-visible RLS coverage for cycle_runs.

The ``cycle_runs`` table created in ``ff14_cycle_runs`` was granted the
standard ``business_id = app.current_tenant_id()`` isolation policy via inline
raw SQL. That policy is correct at rest, but the RLS drift-guard
(``tests/test_rls_coverage_complete.py``) only recognises coverage declared
through the shared ``TENANT_TABLES`` loop pattern, so it reported the table as
uncovered. This migration re-asserts the identical policy using that pattern
(idempotent: ``DROP POLICY IF EXISTS`` + grant-if-role-exists), making the
existing coverage machine-detectable without changing behaviour.

Revision ID: ff15_cycle_runs_rls_coverage
Revises: ff14_cycle_runs
Create Date: 2026-09-25
"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text


revision: str = "ff15_cycle_runs_rls_coverage"
down_revision: Union[str, None] = "ff14_cycle_runs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TENANT_TABLES = [
    "cycle_runs",
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