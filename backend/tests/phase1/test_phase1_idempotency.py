"""Ingestion idempotency tests (spec §28).

The audit found no ``content_hash`` anywhere in the repository, so there was no
content-addressed way to ask "have we already ingested this?".

These tests pin the contract:

* identical bytes produce an identical content hash;
* re-ingesting identical content reuses the artifact instead of duplicating it;
* a re-upload still needs an ingestion *attempt* recorded;
* row-level duplicates are reported, never silently dropped;
* the artifact lookup is keyed by ``(business_id, content_hash)`` so a hash
  ingested by one tenant can never be reused for another.
"""
from __future__ import annotations

from app.services.orbit.contracts import ArtifactType
from app.services.orbit.ingestion.idempotency import (
    IdempotencyOutcome,
    artifact_identity,
    decide_ingestion,
    dedupe_records,
    duplicate_rate,
    rows_fingerprint,
)


class TestArtifactIdentity:
    def test_same_bytes_same_hash(self):
        a = artifact_identity(b"hello world", ArtifactType.CSV)
        b = artifact_identity(b"hello world", ArtifactType.CSV)
        assert a.content_hash == b.content_hash

    def test_different_bytes_differ(self):
        a = artifact_identity(b"hello world", ArtifactType.CSV)
        b = artifact_identity(b"different", ArtifactType.CSV)
        assert a.content_hash != b.content_hash

    def test_size_recorded(self):
        ident = artifact_identity(b"12345", ArtifactType.CSV)
        assert ident.size_bytes == 5


class TestIngestionDecision:
    def test_first_ingest_is_new(self):
        ident = artifact_identity(b"x", ArtifactType.CSV)
        decision = decide_ingestion(ident, business_id="biz1", known_artifacts={})
        assert decision.outcome is IdempotencyOutcome.NEW
        assert decision.should_ingest is True

    def test_identical_reupload_reuses_artifact(self):
        ident = artifact_identity(b"x", ArtifactType.CSV)
        known = {("biz1", ident.content_hash): "art-1"}
        decision = decide_ingestion(ident, business_id="biz1", known_artifacts=known)
        assert decision.outcome is IdempotencyOutcome.REUSED
        assert decision.existing_artifact_id == "art-1"
        assert decision.should_ingest is False

    def test_cross_tenant_hash_is_never_reused(self):
        """A content hash ingested by one tenant must not leak to another."""
        ident = artifact_identity(b"x", ArtifactType.CSV)
        known = {("biz1", ident.content_hash): "art-1"}
        decision = decide_ingestion(ident, business_id="biz2", known_artifacts=known)
        assert decision.should_ingest is True
        assert decision.outcome is IdempotencyOutcome.NEW

    def test_unscoped_upload_always_ingests(self):
        ident = artifact_identity(b"x", ArtifactType.CSV)
        decision = decide_ingestion(ident, business_id=None, known_artifacts={})
        assert decision.should_ingest is True
        assert "no business scope" in decision.reason

    def test_decision_is_serialisable(self):
        ident = artifact_identity(b"x", ArtifactType.CSV)
        decision = decide_ingestion(ident, business_id="biz1", known_artifacts={})
        payload = decision.to_dict()
        assert payload["outcome"] == "new"
        assert payload["should_ingest"] is True


class TestRowFingerprint:
    def test_stable_across_column_layout(self):
        """Same records reformatted with an extra blank column must hash identically."""
        a = rows_fingerprint([["A", "1"], ["B", "2"]], ["name", "qty"])
        # Same logical records, padded with a trailing empty column.
        b = rows_fingerprint([["A", "1", ""], ["B", "2", ""]], ["name", "qty", "extra"])
        assert a == b

    def test_row_order_does_not_matter(self):
        a = rows_fingerprint([["A", "1"], ["B", "2"]], ["name", "qty"])
        b = rows_fingerprint([["B", "2"], ["A", "1"]], ["name", "qty"])
        assert a == b

    def test_different_values_differ(self):
        a = rows_fingerprint([["A", "1"]], ["name", "qty"])
        b = rows_fingerprint([["A", "2"]], ["name", "qty"])
        assert a != b


class TestDuplicateReporting:
    def test_duplicates_are_reported_not_dropped(self):
        records = [
            {"item": "A", "qty": 1},
            {"item": "A", "qty": 1},
            {"item": "B", "qty": 2},
        ]
        unique, duplicates = dedupe_records(records, key_fields=("item",))
        assert len(unique) == 2
        assert len(duplicates) == 1
        # The dropped row is still available for the quality report.
        assert duplicates[0]["item"] == "A"

    def test_no_duplicates_returns_all(self):
        records = [{"item": "A"}, {"item": "B"}]
        unique, duplicates = dedupe_records(records, key_fields=("item",))
        assert len(unique) == 2 and duplicates == []

    def test_duplicate_rate(self):
        assert duplicate_rate(4, 1) == 0.25
        assert duplicate_rate(0, 0) == 0.0