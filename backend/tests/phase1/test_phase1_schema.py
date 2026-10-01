"""Schema/migration consistency for the Phase 1 business-reality tables.

The failure this guards against is real and already happened once: the ORM model
for ``orbit_evidence`` omitted ``audit_id`` / ``evidence_type`` / ``source_ref`` /
``calculation`` while the migration created them. Nothing failed at import time;
the divergence only surfaced when the table was compared against the model.

These tests compare the ORM metadata against the *actually migrated* Postgres
schema, so any future drift fails loudly instead of silently.
"""
from __future__ import annotations

import pytest
from sqlalchemy import inspect, text

from app.database.connection import engine
from app.database.models import (
    JevCall,
    OrbitAuditRun,
    OrbitBusinessProfile,
    OrbitConflict,
    OrbitDataQuality,
    OrbitEntity,
    OrbitEntityAlias,
    OrbitEvidence,
    OrbitFileManifest,
    OrbitIngestionRun,
    OrbitSemanticMapping,
    OrbitStateVersion,
    UniversalArtifact,
)

PHASE1_TABLES = {
    "universal_artifacts": UniversalArtifact,
    "orbit_entities": OrbitEntity,
    "orbit_entity_aliases": OrbitEntityAlias,
    "orbit_conflicts": OrbitConflict,
    "orbit_business_profiles": OrbitBusinessProfile,
    "orbit_state_versions": OrbitStateVersion,
    "orbit_semantic_mappings": OrbitSemanticMapping,
    "jev_calls": JevCall,
    "orbit_ingestion_runs": OrbitIngestionRun,
    "orbit_evidence": OrbitEvidence,
    "orbit_audit_runs": OrbitAuditRun,
    "orbit_file_manifest": OrbitFileManifest,
    "orbit_data_quality": OrbitDataQuality,
}


def _postgres_available() -> bool:
    from tests.conftest import _postgres_available as probe

    return probe()


async def _migrated_columns(table: str) -> set[str]:
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema='public' AND table_name = :t"
            ),
            {"t": table},
        )
        rows = result.fetchall()
        return {row[0] for row in rows}


@pytest.mark.skipif(not _postgres_available(), reason="Postgres test database unavailable")
class TestSchemaMatchesModels:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("table", sorted(PHASE1_TABLES))
    async def test_every_model_column_exists_in_migrated_schema(self, table: str):
        model = PHASE1_TABLES[table]
        orm_columns = set(model.__table__.columns.keys())
        db_columns = await _migrated_columns(table)
        missing = orm_columns - db_columns
        assert not missing, (
            f"{table}: ORM declares columns absent from the migrated schema: {sorted(missing)}"
        )

    @pytest.mark.asyncio
    @pytest.mark.parametrize("table", sorted(PHASE1_TABLES))
    async def test_every_migrated_column_is_declared_on_the_model(self, table: str):
        """The reverse direction: the model must not silently ignore real columns.

        A column in the DB that the ORM does not know about means writes through
        the model will not populate it, which is how the ff16 evidence columns
        ended up permanently empty.
        """
        model = PHASE1_TABLES[table]
        orm_columns = set(model.__table__.columns.keys())
        db_columns = await _migrated_columns(table)
        undeclared = db_columns - orm_columns
        assert not undeclared, (
            f"{table}: migrated schema has columns the ORM model does not declare: {sorted(undeclared)}"
        )


class TestIdempotencyConstraints:
    """Content-addressed uniqueness is what makes re-ingestion idempotent."""

    def test_artifact_unique_on_business_and_content_hash(self):
        names = {c.name for c in UniversalArtifact.__table__.constraints}
        assert "uq_universal_artifact_business_content" in names

    def test_evidence_unique_on_artifact_and_hash(self):
        names = {c.name for c in OrbitEvidence.__table__.constraints}
        assert "uq_orbit_evidence_artifact_hash" in names

    def test_state_version_unique_per_business(self):
        names = {c.name for c in OrbitStateVersion.__table__.constraints}
        assert "uq_orbit_state_version_business_version" in names

    def test_entity_unique_on_business_kind_ref(self):
        names = {c.name for c in OrbitEntity.__table__.constraints}
        assert "uq_orbit_entity_business_kind_ref" in names

    def test_conflict_unique_on_business_ref(self):
        names = {c.name for c in OrbitConflict.__table__.constraints}
        assert "uq_orbit_conflict_business_ref" in names


class TestEvidenceLegacyColumnsRetained:
    """ff16 columns are kept so `AuditPersistenceService` keeps working."""

    def test_evidence_keeps_audit_id_and_ff16_columns(self):
        cols = set(OrbitEvidence.__table__.columns.keys())
        for expected in (
            "audit_id", "finding_id", "metric_name",
            "evidence_type", "source_ref", "calculation",
        ):
            assert expected in cols, f"ff16 column {expected} was dropped from OrbitEvidence"

    def test_evidence_has_phase1_provenance_columns(self):
        cols = set(OrbitEvidence.__table__.columns.keys())
        for expected in (
            "artifact_id", "semantic_role", "entity_ref", "source_locator",
            "raw_value", "normalized_value", "extraction_method",
            "is_ocr", "hash", "observed_at", "period_start", "period_end",
        ):
            assert expected in cols, f"Phase 1 column {expected} missing from OrbitEvidence"

    def test_ingestion_run_has_traceability_counters(self):
        cols = set(OrbitIngestionRun.__table__.columns.keys())
        for expected in (
            "records_seen", "records_accepted", "records_rejected",
            "records_ambiguous", "conflicts_detected",
            "state_version_before", "state_version_after",
        ):
            assert expected in cols, f"ingestion counter {expected} missing"