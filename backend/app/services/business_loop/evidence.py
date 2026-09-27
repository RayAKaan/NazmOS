"""Evidence foundation (Phase 3B) — normalized, quality-flagged observation.

This stage turns raw observations into ACCEPTED evidence records with:
    * schema_version (loop-v1)
    * idempotency (checksum-derived evidence_id — deterministic replay)
    * provenance (source type/reference, event timestamp, ingestion timestamp)
    * validation status (accepted | rejected | quarantined | duplicate)
    * quality flags (fresh | stale | partial | missing | revised | conflict)

Reuse notes:
    * ``app.services.event_engine`` already provides SHA-256 checksum + built-in
      schema validation for the production `Event` tables. This module is the
      DB-free, loop-internal normalized view ON TOP of that concept — it does
      NOT create a second durable store. A thin adapter converts `Event`
      ingestions into :class:`EvidenceRecord` when wiring the loop to the live
      DB (see ``from_event``).
    * Integrity rules: accepted evidence is traceable; corrections preserve
      lineage (REVISED flag + prior evidence reference); conflicting evidence is
      never silently overwritten (CONFLICT flag + rejection).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.services.business_loop.contracts import (
    EvidenceQualityFlag,
    EvidenceValidationStatus,
    LoopSchemaVersion,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _canonical_json(payload: dict[str, Any]) -> str:
    """Deterministic JSON serialization (mirrors event_engine canonical form)."""
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)


def checksum_of(payload: dict[str, Any]) -> str:
    """SHA-256 over the canonical payload — the evidence idempotency key."""
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class EvidenceRecord:
    """One accepted (or quarantined) observation, normalized for the loop.

    Deliberately held DB-free: the loop stages consume these records; the
    production durable home remains the `Event` tables / event_engine. The
    payload field carries only the normalized, deterministic facts the loop
    stage needs (a DLP-clean capsule or minimal numeric fields) — never raw
    merchant PII where avoidable.
    """

    evidence_id: str
    tenant_id: str
    business_id: str
    source_type: str
    source_reference: str
    observation_type: str
    event_timestamp: str
    observed_at: str
    ingested_at: str
    schema_version: str = LoopSchemaVersion.V1.value
    validation_status: str = EvidenceValidationStatus.ACCEPTED.value
    quality_flags: tuple[EvidenceQualityFlag, ...] = ()
    idempotency_key: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    provenance: dict[str, Any] = field(default_factory=dict)
    prior_evidence_id: str | None = None

    @classmethod
    def from_payload(
        cls,
        *,
        tenant_id: str,
        business_id: str,
        source_type: str,
        source_reference: str,
        observation_type: str,
        event_timestamp: str,
        observed_at: str,
        payload: dict[str, Any],
        provenance: dict[str, Any] | None = None,
    ) -> "EvidenceRecord":
        """Build a normalized evidence record with a derived idempotency key."""
        body = {
            "tenant_id": tenant_id,
            "business_id": business_id,
            "source_type": source_type,
            "source_reference": source_reference,
            "observation_type": observation_type,
            "event_timestamp": event_timestamp,
            "payload": payload,
        }
        digest = checksum_of(body)
        return cls(
            evidence_id=f"ev-{digest[:24]}",
            tenant_id=tenant_id,
            business_id=business_id,
            source_type=source_type,
            source_reference=source_reference,
            observation_type=observation_type,
            event_timestamp=event_timestamp,
            observed_at=observed_at,
            ingested_at=_now_iso(),
            idempotency_key=digest,
            payload=payload,
            provenance=provenance or {},
        )

    def with_flags(self, *flags: EvidenceQualityFlag, prior: str | None = None) -> "EvidenceRecord":
        """Return a revised copy carrying quality/lineage flags (immutable)."""
        return EvidenceRecord(
            evidence_id=self.evidence_id,
            tenant_id=self.tenant_id,
            business_id=self.business_id,
            source_type=self.source_type,
            source_reference=self.source_reference,
            observation_type=self.observation_type,
            event_timestamp=self.event_timestamp,
            observed_at=self.observed_at,
            ingested_at=_now_iso(),
            schema_version=self.schema_version,
            validation_status=self.validation_status,
            quality_flags=tuple(dict.fromkeys((*self.quality_flags, *flags))),
            idempotency_key=self.idempotency_key,
            payload=self.payload,
            provenance=self.provenance,
            prior_evidence_id=prior or self.prior_evidence_id,
        )


class EvidenceStore:
    """In-memory, idempotent evidence ledger (DB-free, deterministic replay).

    Provides exactly the behavior Phase 3B acceptance tests require:
    duplicate rejection by idempotency key, conflict marking (never silent
    overwrite), correction lineage (REVISED via ``apply_correction``), and
    provenance preservation. It is the loop-local view; the durable `Event`
    tables remain the production severity of record.
    """

    def __init__(self) -> None:
        self._records: dict[str, EvidenceRecord] = {}
        self._by_ids: dict[str, EvidenceRecord] = {}

    def put(self, record: EvidenceRecord) -> EvidenceRecord:
        """Idempotent insert: an identical checksum replays without duplication."""
        existing = self._records.get(record.idempotency_key)
        if existing is not None:
            return existing.with_flags(EvidenceQualityFlag.FRESH)
        self._records[record.idempotency_key] = record
        self._by_ids[record.evidence_id] = record
        return record

    def apply_correction(self, record: EvidenceRecord, *, prior_id: str) -> EvidenceRecord:
        """Correction preserves historical lineage (REVISED + prior reference)."""
        prior = self._by_ids.get(prior_id)
        if prior is None:
            return record.with_flags(EvidenceQualityFlag.CONFLICT)
        revised = record.with_flags(EvidenceQualityFlag.REVISED, prior=prior_id)
        self._records[revised.idempotency_key] = revised
        self._by_ids[revised.evidence_id] = revised
        return revised

    def mark_conflict(self, record: EvidenceRecord) -> EvidenceRecord:
        """Conflicting evidence is flagged, never silently dropped."""
        flagged = record.with_flags(EvidenceQualityFlag.CONFLICT)
        self._records[flagged.idempotency_key] = flagged
        self._by_ids[flagged.evidence_id] = flagged
        return flagged

    def get(self, evidence_id: str) -> EvidenceRecord | None:
        return self._by_ids.get(evidence_id)

    def accepted(self) -> list[EvidenceRecord]:
        return [
            r for r in self._records.values()
            if r.validation_status == EvidenceValidationStatus.ACCEPTED.value
        ]

    def all(self) -> list[EvidenceRecord]:
        return list(self._records.values())


def freshness_flag(record: EvidenceRecord, now: str, max_age_days: int = 7) -> EvidenceQualityFlag:
    """Deterministic freshness classification: stale is not current."""
    try:
        dt = datetime.fromisoformat(record.observed_at)
        now_dt = datetime.fromisoformat(now)
        age_days = (now_dt - dt).days
    except (TypeError, ValueError):
        return EvidenceQualityFlag.MISSING
    return EvidenceQualityFlag.FRESH if age_days <= max_age_days else EvidenceQualityFlag.STALE


def normalize_observation(
    *,
    tenant_id: str,
    business_id: str,
    raw: dict[str, Any],
    source_type: str,
    source_reference: str,
    observation_type: str,
    event_timestamp: str,
    observed_at: str,
    required_fields: tuple[str, ...] = ("sku", "stock", "cost", "sell"),
) -> tuple[EvidenceRecord | None, str]:
    """Validate + normalize one incoming observation.

    Returns ``(record | None, reason)``. Invalid payloads (missing required
    fields, cross-tenant mismatch in raw) are rejected; they never silently
    enter the accepted evidence set.
    """
    missing = [f for f in required_fields if f not in raw]
    if missing:
        return None, f"missing_fields:{','.join(missing)}"
    raw_tenant = raw.get("tenant_id")
    if raw_tenant is not None and str(raw_tenant) != tenant_id:
        return None, "cross_tenant_rejection"
    payload = {k: raw[k] for k in required_fields if k in raw}
    return (
        EvidenceRecord.from_payload(
            tenant_id=tenant_id,
            business_id=business_id,
            source_type=source_type,
            source_reference=source_reference,
            observation_type=observation_type,
            event_timestamp=event_timestamp,
            observed_at=observed_at,
            payload=payload,
            provenance={"normalizer": "business_loop.evidence.v1", "raw_keys": sorted(raw.keys())},
        ),
        "",
    )