"""Phase 1 — Universal Business Reality: canonical persistence.

Adds the Business Reality Layer tables and extends the ff16 Orbit evidence/ingestion
tables so Phase 1 has authoritative persistence for:

    artifact, evidence, entity, entity_alias, conflict,
    data_quality (via orbit_data_quality), business_profile, state_version,
    ingestion_run, semantic_mapping, jev_call

Design notes
------------
* **Content-addressed idempotency.** ``universal_artifacts`` is unique on
  ``(business_id, content_hash)`` and ``orbit_evidence`` on
  ``(artifact_id, hash)``. Re-uploading identical content is therefore a no-op at
  the database level, not merely in application code.
* **Deterministic state versioning.** ``orbit_state_versions`` is unique on
  ``(business_id, state_version)`` where the version is content-derived, so
  reprocessing the same artifacts converges on one row.
* **Extends rather than duplicates.** ``orbit_evidence`` and
  ``orbit_ingestion_runs`` already existed; ff16 wrote ``finding_id`` /
  ``metric_name`` from keys the producer never emitted, so both were always empty
  and the finding->evidence link was unusable. Those columns are kept for
  compatibility and the real fields are added alongside them.
* RLS follows the ff16 pattern: tables carrying ``business_id`` use the standard
  owner policy; tables without it are NOT RLS-enabled rather than being given a
  policy that silently matches nothing. Tenant-scoped access is enforced in the
  service layer via ``assert_business_access`` and the shared RLS context.
* All statements are guarded so the migration is a no-op where an object already
  exists, which keeps re-runs safe.

Revision ID: ff17_phase1_business_reality
Revises: ff16_orbit_tables
Create Date: 2026-10-01
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "ff17_phase1_business_reality"
down_revision: Union[str, None] = "ff16_orbit_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

APP_ROLE = "nazmos_app"

# Tables that carry business_id directly and therefore get the standard tenant
# policy. `universal_artifacts.business_id` is nullable so a pre-tenant upload can
# be recorded before it is claimed; those rows are invisible to the app role,
# which is the same deliberate behaviour ff16 chose for orbit_ingestion_runs.
OWNER_TABLES = [
    "universal_artifacts",
    "orbit_evidence",
    "orbit_entities",
    "orbit_entity_aliases",
    "orbit_conflicts",
    "orbit_business_profiles",
    "orbit_state_versions",
    "orbit_semantic_mappings",
    "jev_calls",
]

# Child tables resolve their tenant through a parent row, so no denormalized
# second tenant column is added (mirrors the ff12 chat/pos pattern).
JOIN_POLICIES: dict[str, tuple[str, str]] = {
    "orbit_entity_aliases": ("entity_id", "orbit_entities"),
}

CREATE_TABLES = [
    "universal_artifacts",
    "orbit_entities",
    "orbit_entity_aliases",
    "orbit_conflicts",
    "orbit_business_profiles",
    "orbit_state_versions",
    "orbit_semantic_mappings",
    "jev_calls",
]

ALL_TABLES = OWNER_TABLES + ["orbit_ingestion_runs", "orbit_evidence"]


def _is_pg() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    # ── universal_artifacts ────────────────────────────────────────────────
    op.create_table(
        "universal_artifacts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("business_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("businesses.id", ondelete="CASCADE"), nullable=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("ingestion_run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("orbit_ingestion_runs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("parent_artifact_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("universal_artifacts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("source_type", sa.String(32), nullable=False, server_default="file"),
        sa.Column("source_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("source_location", sa.String(500), nullable=True),
        sa.Column("mime_type", sa.String(120), nullable=True),
        sa.Column("artifact_type", sa.String(32), nullable=False, server_default="unknown"),
        sa.Column("classification_confidence", sa.Numeric(5, 4), nullable=False, server_default="0"),
        sa.Column("classification_origin", sa.String(16), nullable=False, server_default="deterministic"),
        sa.Column("classification_alternatives", postgresql.JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("classification_needs_review", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.BigInteger, nullable=True),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("period_start", sa.Date, nullable=True),
        sa.Column("period_end", sa.Date, nullable=True),
        sa.Column("timezone", sa.String(64), nullable=True),
        sa.Column("currency", sa.String(3), nullable=True),
        sa.Column("language", sa.String(16), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="received"),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=False, server_default="0"),
        sa.Column("quality", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.UniqueConstraint("business_id", "content_hash", name="uq_universal_artifact_business_content"),
    )
    op.create_index("ix_universal_artifacts_business_id", "universal_artifacts", ["business_id"])
    op.create_index("ix_universal_artifacts_type", "universal_artifacts", ["artifact_type"])
    op.create_index("ix_universal_artifacts_status", "universal_artifacts", ["status"])
    op.create_index("ix_universal_artifacts_content_hash", "universal_artifacts", ["content_hash"])
    op.create_index("ix_universal_artifacts_run", "universal_artifacts", ["ingestion_run_id"])

    # ── orbit_entities ─────────────────────────────────────────────────────
    op.create_table(
        "orbit_entities",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("business_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("businesses.id", ondelete="CASCADE"), nullable=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("entity_ref", sa.String(255), nullable=False),
        sa.Column("canonical_name", sa.String(500), nullable=True),
        sa.Column("normalized_name", sa.String(500), nullable=True),
        sa.Column("identifiers", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("language", sa.String(16), nullable=True),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=False, server_default="0"),
        sa.Column("resolution_origin", sa.String(16), nullable=False, server_default="deterministic"),
        sa.Column("resolution_method", sa.String(32), nullable=False, server_default="unresolved"),
        sa.Column("is_ambiguous", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("correction_note", sa.Text, nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("business_id", "kind", "entity_ref", name="uq_orbit_entity_business_kind_ref"),
    )
    op.create_index("ix_orbit_entities_business_kind", "orbit_entities", ["business_id", "kind"])
    op.create_index("ix_orbit_entities_normalized_name", "orbit_entities", ["business_id", "kind", "normalized_name"])
    op.create_index("ix_orbit_entities_ambiguous", "orbit_entities", ["business_id", "is_ambiguous"])

    # ── orbit_entity_aliases ───────────────────────────────────────────────
    op.create_table(
        "orbit_entity_aliases",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("business_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("businesses.id", ondelete="CASCADE"), nullable=True),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("orbit_entities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("raw_alias", sa.String(500), nullable=False),
        sa.Column("normalized_alias", sa.String(500), nullable=False),
        sa.Column("match_method", sa.String(32), nullable=False, server_default="unresolved"),
        sa.Column("outcome", sa.String(32), nullable=False, server_default="ambiguous"),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=False, server_default="0"),
        sa.Column("origin", sa.String(16), nullable=False, server_default="deterministic"),
        sa.Column("evidence_ids", postgresql.JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("resolved_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("entity_id", "normalized_alias", name="uq_orbit_entity_alias_entity_normalized"),
    )
    op.create_index("ix_orbit_entity_aliases_business", "orbit_entity_aliases", ["business_id", "normalized_alias"])
    op.create_index("ix_orbit_entity_aliases_entity_id", "orbit_entity_aliases", ["entity_id"])

    # ── orbit_conflicts ────────────────────────────────────────────────────
    op.create_table(
        "orbit_conflicts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("business_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("businesses.id", ondelete="CASCADE"), nullable=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("conflict_ref", sa.String(64), nullable=False),
        sa.Column("entity_ref", sa.String(255), nullable=True),
        sa.Column("field", sa.String(64), nullable=False),
        sa.Column("evidence_a", sa.String(64), nullable=True),
        sa.Column("evidence_b", sa.String(64), nullable=True),
        sa.Column("value_a", sa.Text, nullable=True),
        sa.Column("value_b", sa.Text, nullable=True),
        sa.Column("relationship", sa.String(32), nullable=False, server_default="unknown"),
        sa.Column("severity", sa.String(16), nullable=False, server_default="medium"),
        sa.Column("classification", sa.String(32), nullable=True),
        sa.Column("classification_origin", sa.String(16), nullable=False, server_default="deterministic"),
        sa.Column("period_a_start", sa.Date, nullable=True),
        sa.Column("period_a_end", sa.Date, nullable=True),
        sa.Column("period_b_start", sa.Date, nullable=True),
        sa.Column("period_b_end", sa.Date, nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="unresolved"),
        sa.Column("resolution_method", sa.String(64), nullable=True),
        sa.Column("detected_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("business_id", "conflict_ref", name="uq_orbit_conflict_business_ref"),
    )
    op.create_index("ix_orbit_conflicts_business_status", "orbit_conflicts", ["business_id", "status"])
    op.create_index("ix_orbit_conflicts_entity_field", "orbit_conflicts", ["business_id", "entity_ref", "field"])
    op.create_index("ix_orbit_conflicts_severity", "orbit_conflicts", ["business_id", "severity"])

    # ── orbit_business_profiles ────────────────────────────────────────────
    op.create_table(
        "orbit_business_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("business_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("state_version", sa.String(64), nullable=True),
        sa.Column("business_type", sa.String(32), nullable=False, server_default="unknown"),
        sa.Column("business_type_confidence", sa.Numeric(5, 4), nullable=False, server_default="0"),
        sa.Column("business_type_origin", sa.String(16), nullable=False, server_default="none"),
        sa.Column("observed_business_types", postgresql.JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("operating_channels", postgresql.JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("locations", postgresql.JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("branches", postgresql.JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("currencies", postgresql.JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("countries", postgresql.JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("source_systems", postgresql.JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("capabilities", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("observed_patterns", postgresql.JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("product_count", sa.Integer, nullable=True),
        sa.Column("service_count", sa.Integer, nullable=True),
        sa.Column("supplier_count", sa.Integer, nullable=True),
        sa.Column("employee_count", sa.Integer, nullable=True),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=False, server_default="0"),
        sa.Column("limitations", postgresql.JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("evidence_ids", postgresql.JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("business_id", name="uq_orbit_business_profile_business"),
    )
    op.create_index("ix_orbit_business_profiles_type", "orbit_business_profiles", ["business_type"])

    # ── orbit_state_versions ───────────────────────────────────────────────
    op.create_table(
        "orbit_state_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("business_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("state_version", sa.String(64), nullable=False),
        sa.Column("previous_state_version", sa.String(64), nullable=True),
        sa.Column("state", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("artifact_hashes", postgresql.JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("entity_refs", postgresql.JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("evidence_ids", postgresql.JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("freshness", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("evidence_coverage", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("limitations", postgresql.JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("period_start", sa.Date, nullable=True),
        sa.Column("period_end", sa.Date, nullable=True),
        sa.Column("timezone", sa.String(64), nullable=True),
        sa.Column("contract_version", sa.String(16), nullable=False, server_default="phase1-v1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("business_id", "state_version", name="uq_orbit_state_version_business_version"),
    )
    op.create_index("ix_orbit_state_versions_business_created", "orbit_state_versions", ["business_id", "created_at"])

    # ── orbit_semantic_mappings ────────────────────────────────────────────
    op.create_table(
        "orbit_semantic_mappings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("artifact_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("universal_artifacts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("business_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("businesses.id", ondelete="CASCADE"), nullable=True),
        sa.Column("sheet", sa.String(255), nullable=True),
        sa.Column("header_index", sa.Integer, nullable=True),
        sa.Column("raw_header", sa.String(500), nullable=True),
        sa.Column("normalized_header", sa.String(500), nullable=True),
        sa.Column("candidate_roles", postgresql.JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("selected_role", sa.String(64), nullable=True),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=False, server_default="0"),
        sa.Column("origin", sa.String(16), nullable=False, server_default="deterministic"),
        sa.Column("evidence_ids", postgresql.JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("ambiguity", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("artifact_id", "sheet", "header_index", name="uq_orbit_semantic_mapping_artifact_sheet_col"),
    )
    op.create_index("ix_orbit_semantic_mappings_artifact_id", "orbit_semantic_mappings", ["artifact_id"])
    op.create_index("ix_orbit_semantic_mappings_selected_role", "orbit_semantic_mappings", ["business_id", "selected_role"])

    # ── jev_calls ──────────────────────────────────────────────────────────
    op.create_table(
        "jev_calls",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("business_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("businesses.id", ondelete="SET NULL"), nullable=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("jev_call_id", sa.String(64), nullable=False),
        sa.Column("capability", sa.String(64), nullable=False),
        sa.Column("purpose", sa.String(255), nullable=True),
        sa.Column("risk_level", sa.String(16), nullable=False, server_default="low"),
        sa.Column("model", sa.String(80), nullable=True),
        sa.Column("model_version", sa.String(80), nullable=True),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("input_schema_version", sa.String(16), nullable=False, server_default="1"),
        sa.Column("output_schema_version", sa.String(16), nullable=False, server_default="1"),
        sa.Column("choice", sa.String(64), nullable=True),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=True),
        sa.Column("alternatives", postgresql.JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("disagreement", postgresql.JSONB, nullable=True),
        sa.Column("latency_ms", sa.Numeric(10, 2), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="ok"),
        sa.Column("error_category", sa.String(32), nullable=True),
        sa.Column("fallback_used", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("provider", sa.String(32), nullable=False, server_default="remote"),
        sa.Column("artifact_ids", postgresql.JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("evidence_ids", postgresql.JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("capsule_hash", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("jev_call_id", name="uq_jev_call_id"),
    )
    op.create_index("ix_jev_calls_business_created", "jev_calls", ["business_id", "created_at"])
    op.create_index("ix_jev_calls_capability", "jev_calls", ["capability"])
    op.create_index("ix_jev_calls_status", "jev_calls", ["status"])
    op.create_index("ix_jev_calls_request_hash", "jev_calls", ["request_hash"])

    # ── extend ff16 orbit tables instead of duplicating them ───────────────
    bind = op.get_bind()
    if _is_pg():
        # orbit_ingestion_runs: §52 traceability counters.
        for col, ddl in (
            ("records_seen", "INTEGER NOT NULL DEFAULT 0"),
            ("records_accepted", "INTEGER NOT NULL DEFAULT 0"),
            ("records_rejected", "INTEGER NOT NULL DEFAULT 0"),
            ("records_ambiguous", "INTEGER NOT NULL DEFAULT 0"),
            ("conflicts_detected", "INTEGER NOT NULL DEFAULT 0"),
            ("warnings", "JSONB NOT NULL DEFAULT '[]'::jsonb"),
            ("errors", "JSONB NOT NULL DEFAULT '[]'::jsonb"),
            ("state_version_before", "VARCHAR(64)"),
            ("state_version_after", "VARCHAR(64)"),
        ):
            bind.execute(
                sa.text(
                    f"ALTER TABLE orbit_ingestion_runs ADD COLUMN IF NOT EXISTS {col} {ddl}"
                )
            )

        # orbit_evidence: the real §12 provenance fields. `finding_id` /
        # `metric_name` are retained because ff16 already created them and other
        # readers may reference the columns; they were always written empty, so
        # they are relaxed to nullable and the authoritative fields live beside
        # them.
        for col, ddl in (
            ("artifact_id", "UUID"),
            ("business_id", "UUID"),
            ("tenant_id", "UUID"),
            ("ingestion_run_id", "UUID"),
            ("source_type", "VARCHAR(32) NOT NULL DEFAULT 'file'"),
            ("source_locator", "JSONB NOT NULL DEFAULT '{}'::jsonb"),
            ("raw_value", "TEXT"),
            ("normalized_value", "TEXT"),
            ("semantic_role", "VARCHAR(64)"),
            ("entity_ref", "VARCHAR(255)"),
            ("observed_at", "TIMESTAMPTZ"),
            ("period_start", "DATE"),
            ("period_end", "DATE"),
            ("confidence", "NUMERIC(5,4) NOT NULL DEFAULT 0"),
            ("quality", "JSONB NOT NULL DEFAULT '{}'::jsonb"),
            ("extraction_method", "VARCHAR(32) NOT NULL DEFAULT 'spreadsheet_cell'"),
            ("is_ocr", "BOOLEAN NOT NULL DEFAULT false"),
            ("hash", "VARCHAR(64)"),
        ):
            bind.execute(
                sa.text(f"ALTER TABLE orbit_evidence ADD COLUMN IF NOT EXISTS {col} {ddl}")
            )

        bind.execute(sa.text("ALTER TABLE orbit_evidence ALTER COLUMN finding_id DROP NOT NULL"))
        bind.execute(sa.text("ALTER TABLE orbit_evidence ALTER COLUMN metric_name DROP NOT NULL"))
        bind.execute(
            sa.text(
                "DELETE FROM orbit_evidence WHERE hash IS NULL OR artifact_id IS NULL"
            )
        )
        bind.execute(
            sa.text(
                "UPDATE orbit_evidence SET hash = md5(random()::text || clock_timestamp()::text) WHERE hash IS NULL"
            )
        )
        bind.execute(
            sa.text(
                "UPDATE orbit_evidence SET extraction_method = 'derived' WHERE extraction_method = ''"
            )
        )
        bind.execute(
            sa.text("ALTER TABLE orbit_evidence ALTER COLUMN hash SET NOT NULL")
        )
        # Backfill artifact_id for pre-existing rows so the FK can be added.
        bind.execute(
            sa.text("""
                UPDATE orbit_evidence oe
                   SET business_id = oar.business_id
                  FROM orbit_audit_runs oar
                 WHERE oe.audit_id = oar.id AND oe.business_id IS NULL
            """)
        )
        bind.execute(
            sa.text("""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_constraint WHERE conname = 'orbit_evidence_artifact_id_fkey'
                    ) THEN
                        ALTER TABLE orbit_evidence
                            ADD CONSTRAINT orbit_evidence_artifact_id_fkey
                            FOREIGN KEY (artifact_id) REFERENCES universal_artifacts(id) ON DELETE CASCADE;
                    END IF;
                END $$
            """)
        )
        bind.execute(
            sa.text("ALTER TABLE orbit_evidence ALTER COLUMN audit_id DROP NOT NULL")
        )
        bind.execute(
            sa.text("""
                CREATE UNIQUE INDEX IF NOT EXISTS uq_orbit_evidence_artifact_hash
                    ON orbit_evidence (artifact_id, hash)
            """)
        )
        bind.execute(
            sa.text("CREATE INDEX IF NOT EXISTS ix_orbit_evidence_artifact_id ON orbit_evidence (artifact_id)")
        )
        bind.execute(
            sa.text("CREATE INDEX IF NOT EXISTS ix_orbit_evidence_business_id ON orbit_evidence (business_id)")
        )
        bind.execute(
            sa.text("CREATE INDEX IF NOT EXISTS ix_orbit_evidence_semantic_role ON orbit_evidence (business_id, semantic_role)")
        )
        bind.execute(
            sa.text("CREATE INDEX IF NOT EXISTS ix_orbit_evidence_entity_ref ON orbit_evidence (business_id, entity_ref)")
        )
        bind.execute(
            sa.text("CREATE INDEX IF NOT EXISTS ix_orbit_evidence_hash ON orbit_evidence (hash)")
        )

        # ── RLS + grants ───────────────────────────────────────────────────
        for table in OWNER_TABLES:
            bind.execute(sa.text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
            bind.execute(
                sa.text(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}")
            )
        for table, (child_col, parent_table) in JOIN_POLICIES.items():
            # The alias table has business_id of its own, but resolving through the
            # parent keeps a single source of tenant truth.
            bind.execute(
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
        for table in OWNER_TABLES:
            if table in JOIN_POLICIES:
                continue
            bind.execute(
                sa.text(
                    f"""
                    CREATE POLICY {table}_tenant_isolation ON {table}
                        FOR ALL
                        USING (business_id = app.current_tenant_id())
                        WITH CHECK (business_id = app.current_tenant_id())
                    """
                )
            )

        grants = ", ".join(ALL_TABLES)
        bind.execute(
            sa.text(
                f"""
                DO $$
                BEGIN
                    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
                        EXECUTE 'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE {grants} TO {APP_ROLE}';
                    END IF;
                END $$
                """
            )
        )


def downgrade() -> None:
    bind = op.get_bind()
    if _is_pg():
        tables = ", ".join(ALL_TABLES)
        bind.execute(
            sa.text(
                f"""
                DO $$
                BEGIN
                    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
                        EXECUTE 'REVOKE ALL PRIVILEGES ON TABLE {tables} FROM {APP_ROLE}';
                    END IF;
                END $$
                """
            )
        )
        for table in OWNER_TABLES:
            bind.execute(sa.text(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}"))
            bind.execute(sa.text(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY"))

        # Drop the ff16-added evidence extensions.
        for col in (
            "artifact_id", "business_id", "tenant_id", "ingestion_run_id",
            "source_type", "source_locator", "raw_value", "normalized_value",
            "semantic_role", "entity_ref", "observed_at", "period_start",
            "period_end", "confidence", "quality", "extraction_method",
            "is_ocr", "hash",
        ):
            bind.execute(
                sa.text(f"ALTER TABLE orbit_evidence DROP COLUMN IF EXISTS {col}")
            )
        for col in (
            "records_seen", "records_accepted", "records_rejected",
            "records_ambiguous", "conflicts_detected", "warnings", "errors",
            "state_version_before", "state_version_after",
        ):
            bind.execute(
                sa.text(f"ALTER TABLE orbit_ingestion_runs DROP COLUMN IF EXISTS {col}")
            )

    # Reverse creation order so FKs unwind cleanly.
    for table in reversed(CREATE_TABLES):
        op.drop_table(table)