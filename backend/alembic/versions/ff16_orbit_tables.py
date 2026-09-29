"""Phase 1A — Orbit audit infrastructure tables.

Creates tables for:
- orbit_ingestion_runs: one per upload session (guest or auth)
- orbit_file_manifest: per-file metadata in an ingestion run
- orbit_data_quality: data quality snapshot per run
- orbit_audit_runs: full Orbit audit result snapshots
- orbit_evidence: finding -> metric -> source row linkage

Revision ID: ff16_orbit_tables
Revises: ff15_cycle_runs_rls_coverage
Create Date: 2026-09-27
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "ff16_orbit_tables"
down_revision: Union[str, None] = "ff15_cycle_runs_rls_coverage"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

APP_ROLE = "nazmos_app"

TENANT_TABLES = [
    "orbit_ingestion_runs",
    "orbit_file_manifest",
    "orbit_data_quality",
    "orbit_audit_runs",
    "orbit_evidence",
]

# Tables that carry business_id directly and use the standard tenant policy.
OWNER_TABLES = [
    "orbit_ingestion_runs",
    "orbit_audit_runs",
]

# Child tables carry no business_id; they resolve their tenant through the
# parent row's run_id, mirroring the ff12 chat_messages / pos_sync_logs
# pattern (no denormalized second tenant column).
JOIN_POLICIES = {
    "orbit_file_manifest": ("run_id", "orbit_ingestion_runs"),
    "orbit_data_quality": ("run_id", "orbit_ingestion_runs"),
    "orbit_evidence": ("audit_id", "orbit_audit_runs"),
}


def upgrade() -> None:
    # orbit_ingestion_runs: one per upload session (guest or auth)
    op.create_table(
        "orbit_ingestion_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("business_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("businesses.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="processing"),
        sa.Column("business_type", sa.String(32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("guest_session_id", sa.String(64), nullable=True),
    )
    op.create_index("ix_orbit_ingestion_runs_business_id", "orbit_ingestion_runs", ["business_id"])
    op.create_index("ix_orbit_ingestion_runs_status", "orbit_ingestion_runs", ["status"])

    # orbit_file_manifest: per-file metadata in an ingestion run
    op.create_table(
        "orbit_file_manifest",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("orbit_ingestion_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("file_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("classification", sa.String(32), nullable=False),
        sa.Column("confidence", sa.Numeric(4, 3), nullable=False),
        sa.Column("row_count", sa.Integer, nullable=False),
        sa.Column("column_count", sa.Integer, nullable=False),
        sa.Column("mapped_fields", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("missing_fields", postgresql.ARRAY(sa.Text), nullable=False, server_default=sa.text("'{}'::text[]")),
        sa.Column("ambiguous_fields", postgresql.ARRAY(sa.Text), nullable=False, server_default=sa.text("'{}'::text[]")),
        sa.Column("quality", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("metadata", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_orbit_file_manifest_run_id", "orbit_file_manifest", ["run_id"])

    # orbit_data_quality: data quality snapshot per run
    op.create_table(
        "orbit_data_quality",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("orbit_ingestion_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("overall_score", sa.Integer, nullable=False),
        sa.Column("domain_scores", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("missing_required_fields", postgresql.ARRAY(sa.Text), nullable=False, server_default=sa.text("'{}'::text[]")),
        sa.Column("ambiguous_fields", postgresql.ARRAY(sa.Text), nullable=False, server_default=sa.text("'{}'::text[]")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_orbit_data_quality_run_id", "orbit_data_quality", ["run_id"])

    # orbit_audit_runs: full Orbit audit result snapshots
    op.create_table(
        "orbit_audit_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("orbit_ingestion_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("business_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("businesses.id", ondelete="SET NULL"), nullable=True),
        sa.Column("business_type", sa.String(32), nullable=True),
        sa.Column("period_start", sa.Date, nullable=True),
        sa.Column("period_end", sa.Date, nullable=True),
        sa.Column("health_score", sa.Integer, nullable=False),
        sa.Column("health_breakdown", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("exposures", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("findings", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("opportunities", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("evidence", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("limitations", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("sources", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_orbit_audit_runs_run_id", "orbit_audit_runs", ["run_id"])
    op.create_index("ix_orbit_audit_runs_business_id", "orbit_audit_runs", ["business_id"])

    # orbit_evidence: finding -> metric -> source row linkage
    op.create_table(
        "orbit_evidence",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("audit_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("orbit_audit_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("finding_id", sa.String(64), nullable=False),
        sa.Column("metric_name", sa.String(64), nullable=False),
        sa.Column("evidence_type", sa.String(32), nullable=False),  # source_row, calculation, cross_column
        sa.Column("source_ref", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("calculation", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_orbit_evidence_audit_id", "orbit_evidence", ["audit_id"])
    op.create_index("ix_orbit_evidence_finding_id", "orbit_evidence", ["finding_id"])

    # RLS + grants for new tables
    conn = op.get_bind()
    if conn.dialect.name != "postgresql":
        return

    for table in TENANT_TABLES:
        conn.execute(sa.text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
        conn.execute(sa.text(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}"))

    for table in OWNER_TABLES:
        conn.execute(
            sa.text(
                f"""
                CREATE POLICY {table}_tenant_isolation ON {table}
                    FOR ALL
                    USING (business_id = app.current_tenant_id())
                    WITH CHECK (business_id = app.current_tenant_id())
                """
            )
        )

    for table, (child_col, parent_table) in JOIN_POLICIES.items():
        conn.execute(
            sa.text(
                f"""
                CREATE POLICY {table}_tenant_isolation ON {table}
                    FOR ALL
                    USING ({child_col} IN (
                        SELECT id FROM {parent_table}
                        WHERE business_id = app.current_tenant_id()
                    ))
                    WITH CHECK ({child_col} IN (
                        SELECT id FROM {parent_table}
                        WHERE business_id = app.current_tenant_id()
                    ))
                """
            )
        )

    grants = ", ".join(TENANT_TABLES)
    conn.execute(
        sa.text(
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
    if conn.dialect.name != "postgresql":
        return

    revokes = ", ".join(TENANT_TABLES)
    conn.execute(
        sa.text(
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
        conn.execute(sa.text(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}"))
        conn.execute(sa.text(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY"))

    op.drop_table("orbit_evidence")
    op.drop_table("orbit_audit_runs")
    op.drop_table("orbit_data_quality")
    op.drop_table("orbit_file_manifest")
    op.drop_table("orbit_ingestion_runs")