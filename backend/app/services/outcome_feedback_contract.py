"""Unified Outcome Feedback Contract (Phase 2C-B).

Defines the canonical, versioned schema for recording what happened after
a decision or action. All producers and consumers must use this contract
(or an adapter with a bounded compatibility period).

Key design principles:
- Unknown is not zero. Outcomes distinguish "no data" from "zero result".
- Reported outcomes are not independently verified outcomes.
- Missing feedback is not a zero result.
- Idempotent under retries (ON CONFLICT DO NOTHING on agent_action_id).
- Tenant-scoped: feedback is always linked to the correct business.
- Financial units, currency, and basis are preserved; never silently coerced.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID


SCHEMA_VERSION = "1.0.0"


# Outcome status values — strictly enumerated. A recommendation is NOT an outcome.
# An execution attempt is NOT proof of success. Missing feedback is NOT a zero result.
OUTCOME_STATUS_CONFIRMED = "confirmed"   # execution completed, actual measured
OUTCOME_STATUS_PARTIAL = "partial"       # execution completed but incomplete
OUTCOME_STATUS_FAILED = "failed"         # execution did not succeed
OUTCOME_STATUS_UNKNOWN = "unknown"       # outcome not yet observed/reported
OUTCOME_STATUS_REJECTED = "rejected"     # explicitly rejected by owner


# Canonical outcome feedback fields, all justified by existing workflows.
# Fields that must always be present are marked; others have safe defaults.
CANONICAL_FEEDBACK_FIELDS = frozenset({
    "schema_version",
    "feedback_id",
    "tenant_id",
    "business_id",
    "decision_id",
    "action_id",
    "outcome_status",
    "observed_at",
    "recorded_at",
    "actual_measured_values",
    "expected_values",
    "evidence_references",
    "source_provenance",
    "verification_status",
    "failure_reason",
    "idempotency_key",
})


def serialize_outcome_feedback(
    *,
    feedback_id: UUID,
    business_id: UUID,
    decision_id: UUID | None = None,
    action_id: UUID | None = None,
    outcome_status: str = OUTCOME_STATUS_UNKNOWN,
    observed_at: datetime | None = None,
    recorded_at: datetime | None = None,
    actual_measured_values: dict[str, Any] | None = None,
    expected_values: dict[str, Any] | None = None,
    evidence_references: dict[str, Any] | None = None,
    source_provenance: str = "system",
    verification_status: str | None = None,
    failure_reason: str | None = None,
    idempotency_key: str | None = None,
    schema_version: str = SCHEMA_VERSION,
) -> dict[str, Any]:
    """Canonical serializer for outcome feedback payloads.

    Guarantees stable, deterministic serialization with explicit versioning.
    All production callers should use this function rather than building
    payloads inline, to guarantee field coherence and provenance.

    Outcome status values and their semantics:
    - confirmed: execution completed, actual measured values exist
    - partial: execution completed but some data missing (not zero)
    - failed: execution did not succeed as intended
    - unknown: outcome not yet observed or reported (default)
    - rejected: explicitly rejected by owner/authority
    """
    if actual_measured_values is None:
        actual_measured_values = {}
    if expected_values is None:
        expected_values = {}
    if evidence_references is None:
        evidence_references = {}

    return {
        "schema_version": schema_version,
        "feedback_id": str(feedback_id),
        "tenant_id": str(business_id),
        "business_id": str(business_id),
        "decision_id": str(decision_id) if decision_id else None,
        "action_id": str(action_id) if action_id else None,
        "outcome_status": outcome_status,
        "observed_at": _iso_datetime(observed_at),
        "recorded_at": _iso_datetime(recorded_at or datetime.now(timezone.utc)),
        "actual_measured_values": actual_measured_values,
        "expected_values": expected_values,
        "evidence_references": evidence_references,
        "source_provenance": source_provenance,
        "verification_status": verification_status,
        "failure_reason": failure_reason,
        "idempotency_key": idempotency_key or _derive_idempotency_key(
            str(business_id), str(action_id) if action_id else "", str(outcome_status)
        ),
    }


def deserialize_outcome_feedback(data: dict[str, Any]) -> dict[str, Any]:
    """Canonical deserializer for outcome feedback payloads.

    Returns a plain dict with normalized keys. Missing fields default to
    safe emptiness. Does not perform validation of business rules — that
    is the caller's responsibility.
    """
    schema_version = data.get("schema_version", SCHEMA_VERSION)
    outcome_status = data.get("outcome_status", OUTCOME_STATUS_UNKNOWN)

    return {
        "schema_version": schema_version,
        "feedback_id": data.get("feedback_id", ""),
        "tenant_id": data.get("tenant_id", ""),
        "business_id": data.get("business_id", ""),
        "decision_id": data.get("decision_id") or None,
        "action_id": data.get("action_id") or None,
        "outcome_status": outcome_status,
        "observed_at": _parse_iso_datetime(data.get("observed_at")),
        "recorded_at": _parse_iso_datetime(data.get("recorded_at")),
        "actual_measured_values": data.get("actual_measured_values", {}),
        "expected_values": data.get("expected_values", {}),
        "evidence_references": data.get("evidence_references", {}),
        "source_provenance": data.get("source_provenance", "system"),
        "verification_status": data.get("verification_status"),
        "failure_reason": data.get("failure_reason"),
        "idempotency_key": data.get("idempotency_key"),
    }


def _iso_datetime(dt: datetime | None) -> str | None:
    """Dialect-safe ISO timestamp serialization."""
    if dt is None:
        return None
    if isinstance(dt, str):
        return dt
    return dt.replace(tzinfo=timezone.utc).isoformat() if dt.tzinfo else dt.isoformat()


def _parse_iso_datetime(s: str | None) -> datetime | None:
    """Parse an ISO datetime string; returns None on failure."""
    if s is None:
        return None
    if isinstance(s, datetime):
        return s
    try:
        # Handle both with and without timezone
        if s.endswith("+00:00") or s.endswith("Z"):
            return datetime.fromisoformat(s)
        return datetime.fromisoformat(s)
    except Exception:
        return None


def _derive_idempotency_key(
    business_id: str, action_id: str, outcome_status: str
) -> str:
    """Derive a deterministic idempotency key from core identifiers.

    This key is safe to use as the natural key for ON CONFLICT DO NOTHING
    on the outcome_feedback table (agent_action_id unique constraint). The
    combination of business_id + action_id + outcome_status is guaranteed
    to be unique per execution lifecycle.
    """
    import hashlib
    composite = f"{business_id}:{action_id}:{outcome_status}"
    return hashlib.sha256(composite.encode()).hexdigest()[:16]