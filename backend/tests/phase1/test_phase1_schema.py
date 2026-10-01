"""Schema/migration consistency for the Phase 1 business-reality tables.

The failure this guards against is real and already happened once: the ORM model
for ``orbit_evidence`` omitted ``audit_id`` / ``evidence_type`` / ``source_ref`` /
``calculation`` while the migration created them. Nothing failed at import time;
the divergence only surfaced when the table was compared against the model.

These tests compare the ORM metadata against the *actually migrated* Postgres
schema, so any future drift fails loudly instead of silently.
"""
from __future__ import annotations

import os
import subprocess
import sys
import uuid
from urllib.parse import urlsplit, urlunsplit

import pytest
import sqlalchemy as sa

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

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _postgres_available() -> bool:
    from tests.conftest import _postgres_available as probe

    return probe()


def _sync_url(url: str, dbname: str) -> str:
    """Async URL -> sync psycopg2 URL for the given database."""
    parts = urlsplit(url)
    scheme = "postgresql+psycopg2" if parts.scheme.startswith("postgresql") else parts.scheme
    return urlunsplit((scheme, parts.netloc, f"/{dbname}", parts.query, parts.fragment))


def _async_url(url: str, dbname: str) -> str:
    """Same server/credentials, different database, keeping the async driver.

    ``alembic/env.py`` always builds an *async* engine from ``settings.DATABASE_URL``
    (and importing the app itself creates one), so the migration subprocess must
    receive an async URL even though inspection is synchronous.
    """
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, f"/{dbname}", parts.query, parts.fragment))


@pytest.fixture(scope="module")
def migrated_engine():
    """A *private* database migrated by alembic, isolated from the shared test DB.

    The shared ``nazmos_test`` database cannot be used here: ``tests/conftest.py``
    drops the ``public`` schema in the ``db_session`` teardown, so any test that
    asserts against the real migrated schema fails depending on collection order.

    Migrating a throwaway database in a subprocess (rather than in-process) keeps
    each migration run honest: a fresh interpreter cannot inherit cached settings
    or a warm connection pool from the test session.
    """
    if not _postgres_available():
        pytest.skip("Postgres test database unavailable")

    from tests.conftest import TEST_DATABASE_URL

    db_name = f"nazmos_phase1_drift_{uuid.uuid4().hex[:8]}"
    admin_url = _sync_url(TEST_DATABASE_URL, "postgres")
    admin = sa.create_engine(admin_url, isolation_level="AUTOCOMMIT")

    try:
        with admin.connect() as conn:
            conn.execute(sa.text(f'CREATE DATABASE "{db_name}"'))
    finally:
        admin.dispose()

    env = {
        **os.environ,
        "DATABASE_URL": _async_url(TEST_DATABASE_URL, db_name),
        "USE_TEMPORAL": "false",
    }
    try:
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=_BACKEND_DIR,
            env=env,
            capture_output=True,
            text=True,
            timeout=600,
        )
        if result.returncode != 0:
            pytest.fail(f"alembic upgrade head failed:\n{result.stdout}\n{result.stderr}")

        engine = sa.create_engine(_sync_url(TEST_DATABASE_URL, db_name))
        try:
            yield engine
        finally:
            engine.dispose()
    finally:
        admin = sa.create_engine(admin_url, isolation_level="AUTOCOMMIT")
        try:
            with admin.connect() as conn:
                conn.execute(sa.text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = :n AND pid <> pg_backend_pid()"
                ), {"n": db_name})
                conn.execute(sa.text(f'DROP DATABASE IF EXISTS "{db_name}"'))
        except Exception:
            pass
        finally:
            admin.dispose()


def _migrated_columns(migrated_engine, table: str) -> set[str]:
    inspector = sa.inspect(migrated_engine)
    if table not in inspector.get_table_names():
        return set()
    return {col["name"] for col in inspector.get_columns(table)}


@pytest.mark.usefixtures("migrated_engine")
class TestSchemaMatchesModels:
    @pytest.mark.parametrize("table", sorted(PHASE1_TABLES))
    def test_every_model_column_exists_in_migrated_schema(self, table: str, migrated_engine):
        model = PHASE1_TABLES[table]
        orm_columns = set(model.__table__.columns.keys())
        db_columns = _migrated_columns(migrated_engine, table)
        assert db_columns, f"{table}: not present in the migrated schema at all"
        missing = orm_columns - db_columns
        assert not missing, (
            f"{table}: ORM declares columns absent from the migrated schema: {sorted(missing)}"
        )

    @pytest.mark.parametrize("table", sorted(PHASE1_TABLES))
    def test_every_migrated_column_is_declared_on_the_model(self, table: str, migrated_engine):
        """The reverse direction: the model must not silently ignore real columns.

        A column in the DB that the ORM does not know about means writes through
        the model will not populate it, which is how the ff16 evidence columns
        ended up permanently empty.
        """
        model = PHASE1_TABLES[table]
        orm_columns = set(model.__table__.columns.keys())
        db_columns = _migrated_columns(migrated_engine, table)
        undeclared = db_columns - orm_columns
        assert not undeclared, (
            f"{table}: migrated schema has columns the ORM model does not declare: {sorted(undeclared)}"
        )


@pytest.mark.usefixtures("migrated_engine")
class TestMigratedIntegrity:
    """Constraints that only exist in the migration must actually exist in Postgres."""

    def test_alembic_reached_head(self, migrated_engine):
        with migrated_engine.connect() as conn:
            version = conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar()
        assert version == "ff17_phase1_business_reality"

    def test_artifact_content_hash_is_unique_per_business(self, migrated_engine):
        with migrated_engine.connect() as conn:
            names = {
                row[0]
                for row in conn.execute(sa.text(
                    "SELECT indexname FROM pg_indexes WHERE tablename='universal_artifacts'"
                ))
            }
        assert "uq_universal_artifact_business_content" in names

    def test_state_version_is_unique_per_business(self, migrated_engine):
        with migrated_engine.connect() as conn:
            names = {
                row[0]
                for row in conn.execute(sa.text(
                    "SELECT indexname FROM pg_indexes WHERE tablename='orbit_state_versions'"
                ))
            }
        assert "uq_orbit_state_version_business_version" in names

    def test_row_level_security_is_enabled_on_phase1_tables(self, migrated_engine):
        """Tenant isolation must be enforced by the database, not only by the app."""
        expected = {
            "universal_artifacts", "orbit_entities", "orbit_conflicts",
            "orbit_state_versions", "orbit_business_profiles",
            "orbit_semantic_mappings", "orbit_evidence", "jev_calls",
        }
        with migrated_engine.connect() as conn:
            rows = conn.execute(sa.text(
                "SELECT c.relname FROM pg_class c "
                "JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname='public' AND c.relrowsecurity"
            )).fetchall()
        enabled = {row[0] for row in rows}
        missing = expected - enabled
        assert not missing, f"RLS not enabled on: {sorted(missing)}"


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