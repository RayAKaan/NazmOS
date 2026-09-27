"""Outcome verification + verified learning (Phase 3I).

Distinguishes execution success from business success (MASTER_PLAN §14.1):
    * an execution receipt is not proof of improvement;
    * outcomes are promoted VERIFIED only when criteria are satisfied.
A verified outcome is written through the EXISTING
``app.services.outcome_ledger.OutcomeLedger`` (V1, opt-in, idempotent, DLP-clean)
— this module consumes and gates; it does NOT create a parallel ledger.

Learning eligibility (MASTER_PLAN §15.2): only traceable, VERIFIED, authorized,
quality-satisfying outcomes enter learning. Raw Jev output is never a truth
source, and unverified outcomes are never eligible.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.services.business_loop.contracts import VerificationStatus


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _iso_dt(value: Any, default: str = "") -> str:
    if value is None:
        return default
    if isinstance(value, str):
        return value
    try:
        return value.isoformat(timespec="seconds")
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class OutcomeRecord:
    """One outcome measurement for a recommendation/execution."""

    outcome_id: str
    recommendation_id: str
    recommendation_version: int
    execution_key: str
    baseline_state_version: str
    post_action_state_version: str
    verification_status: VerificationStatus
    expected_impact_sar: float | None
    observed_impact_sar: float | None
    verification_method: str
    measurement_window: str
    evidence: tuple[str, ...]
    recorded_at: str = ""

    def __post_init__(self) -> None:
        if not self.recorded_at:
            object.__setattr__(self, "recorded_at", _now_iso())

    @property
    def is_verified(self) -> bool:
        return self.verification_status == VerificationStatus.VERIFIED

    def to_dict(self) -> dict[str, Any]:
        return {
            "outcome_id": self.outcome_id,
            "recommendation_id": self.recommendation_id,
            "recommendation_version": self.recommendation_version,
            "execution_key": self.execution_key,
            "baseline_state_version": self.baseline_state_version,
            "post_action_state_version": self.post_action_state_version,
            "verification_status": self.verification_status.value if hasattr(self.verification_status, "value") else str(self.verification_status),
            "expected_impact_sar": self.expected_impact_sar,
            "observed_impact_sar": self.observed_impact_sar,
            "verification_method": self.verification_method,
        }


VERIFICATION_CRITERIA = {
    "verified": ("observed_impact_sar", "baseline_state_version", "post_action_state_version"),
    "partially_verified": ("observed_impact_sar",),
    "observed": ("observed_impact_sar",),
    "reported": (),
}


def verify_outcome(
    *,
    outcome_id: str,
    recommendation_id: str,
    recommendation_version: int,
    execution_key: str,
    baseline_state_version: str,
    post_action_state_version: str,
    expected_impact_sar: float | None,
    observed_impact_sar: float | None,
    verification_method: str,
    measurement_window: str,
    evidence: tuple[str, ...] = (),
) -> OutcomeRecord:
    """Create an outcome record promoted according to its measurable criteria.

    A VERIFIED outcome requires a measured observed impact AND distinct
    baseline/post state versions AND a concrete verification method — a raw
    reported receipt (no measurement) can never reach VERIFIED.
    """
    status = VerificationStatus.REPORTED
    if observed_impact_sar is not None:
        status = VerificationStatus.OBSERVED
        required = set(VERIFICATION_CRITERIA["verified"])
        base_ok = all(
            v is not None and v != ""
            for v in (observed_impact_sar, baseline_state_version, post_action_state_version)
        )
        distinct_versions = bool(baseline_state_version) and bool(post_action_state_version) and baseline_state_version != post_action_state_version
        if base_ok and verification_method and distinct_versions:
            # VERIFIED requires DISTINCT baseline/post snapshots (Phase 4F): an
            # identical reused snapshot cannot attribute any change to the action.
            status = VerificationStatus.VERIFIED
        elif observed_impact_sar is not None and verification_method:
            # Measured but not attributable to a changed state (missing or
            # identical baseline/post snapshot): never VERIFIED (Phase 4F).
            status = VerificationStatus.PARTIALLY_VERIFIED if (baseline_state_version or post_action_state_version) else VerificationStatus.OBSERVED
    return OutcomeRecord(
        outcome_id=outcome_id,
        recommendation_id=recommendation_id,
        recommendation_version=recommendation_version,
        execution_key=execution_key,
        baseline_state_version=baseline_state_version,
        post_action_state_version=post_action_state_version,
        verification_status=status,
        expected_impact_sar=expected_impact_sar,
        observed_impact_sar=observed_impact_sar,
        verification_method=verification_method,
        measurement_window=measurement_window,
        evidence=evidence,
    )


def disputed_outcome(*, outcome_id: str, recommendation_id: str, recommendation_version: int, execution_key: str) -> OutcomeRecord:
    return OutcomeRecord(
        outcome_id=outcome_id,
        recommendation_id=recommendation_id,
        recommendation_version=recommendation_version,
        execution_key=execution_key,
        baseline_state_version="",
        post_action_state_version="",
        verification_status=VerificationStatus.DISPUTED,
        expected_impact_sar=None,
        observed_impact_sar=None,
        verification_method="dispute",
        measurement_window="",
        evidence=(),
    )


def unverified_outcome(*, outcome_id: str, recommendation_id: str, recommendation_version: int, execution_key: str) -> OutcomeRecord:
    return OutcomeRecord(
        outcome_id=outcome_id,
        recommendation_id=recommendation_id,
        recommendation_version=recommendation_version,
        execution_key=execution_key,
        baseline_state_version="",
        post_action_state_version="",
        verification_status=VerificationStatus.UNVERIFIED,
        expected_impact_sar=None,
        observed_impact_sar=None,
        verification_method="no_measurement",
        measurement_window="",
        evidence=(),
    )


@dataclass(frozen=True)
class LearningEligibility:
    eligible: bool
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {"eligible": self.eligible, "reasons": list(self.reasons)}


def learning_eligibility(
    outcome: OutcomeRecord,
    *,
    tenant_authorized: bool = True,
    source_traceable: bool = True,
    quality_satisfied: bool = True,
    attribution_sufficient: bool = True,
) -> LearningEligibility:
    """The ONLY gate for the verified learning pipeline (MASTER_PLAN §15.2).

    Learning requires:
      * traceable source (recom reference + execution key present)
      * verification status VERIFIED
      * DISTINCT baseline/post state versions (Phase 4F — a reused identical
        snapshot can never attribute improvement to the action)
      * tenant + purpose authorized
      * quality satisfied
      * attribution sufficient (Phase 4F — an outcome that is only Jev-advisory
        attributed is never eligible; the measured deterministic path is)
    An unverified outcome is rejected regardless of other conditions.
    """
    reasons: list[str] = []
    if not outcome.recommendation_id or not outcome.execution_key:
        reasons.append("source_not_traceable")
    if not outcome.is_verified:
        reasons.append("outcome_not_verified")
    if (
        outcome.baseline_state_version
        and outcome.post_action_state_version
        and outcome.baseline_state_version == outcome.post_action_state_version
    ):
        reasons.append("state_versions_not_distinct")
    if not tenant_authorized:
        reasons.append("tenant_not_authorized")
    if not quality_satisfied:
        reasons.append("quality_failed")
    if not attribution_sufficient:
        reasons.append("attribution_insufficient")
    return LearningEligibility(eligible=not reasons, reasons=tuple(reasons))


class VerifiedOutcomeLedger:
    """Verified-outcome capture through the EXISTING V1 outcome ledger.

    Wires the loop's verification status/impact into
    ``app.services.outcome_ledger.OutcomeLedger`` using the sha-derived
    decision key so learning consumers read it through the same
    ``verified_outcomes()`` path — no parallel ledger is created.
    """

    def __init__(self, ledger_path: str) -> None:
        from app.services.outcome_ledger import OutcomeLedger

        self._ledger = OutcomeLedger(ledger_path)

    def attach(self, outcome: OutcomeRecord) -> bool:
        """Capture one outcome row through the EXISTING V1 ledger path.

        The row is first recorded (idempotent on decision_key) then the
        verified/measured result is attached. ``verified_outcomes()`` on the
        same ledger exposes only rows promoted to verified.
        """
        import hashlib

        composite = f"{outcome.execution_key}:{outcome.recommendation_id}:{outcome.recommendation_version}"
        key = hashlib.sha256(composite.encode()).hexdigest()[:24]
        status_mapping = {
            VerificationStatus.VERIFIED: "confirmed",
            VerificationStatus.PARTIALLY_VERIFIED: "partial",
            VerificationStatus.DISPUTED: "failed",
            VerificationStatus.UNVERIFIED: "rejected",
            VerificationStatus.OBSERVED: "confirmed",
            VerificationStatus.REPORTED: "unknown",
        }
        recorded = self._ledger.record(
            decision_key=key,
            capability="business_loop.verified",
            deterministic_decision=outcome.recommendation_id or "unknown",
            source="business_loop",
            capsule_hash=outcome.execution_key,
        )
        if not recorded:
            return False
        return self._ledger.record_verified_result(
            decision_key=key,
            outcome_status=status_mapping.get(outcome.verification_status, "unknown"),
            verified=outcome.is_verified,
            actual_impact_sar=outcome.observed_impact_sar,
            expected_impact_sar=outcome.expected_impact_sar,
        )

    def verified_outcomes(self) -> list[dict[str, Any]]:
        return self._ledger.verified_outcomes()


def latest_verified_impact(
    *,
    ledger_path: str,
    capability_filter: str | None = None,
) -> dict[str, Any]:
    """Aggregate the verified learning signal for loop feedback (read-only)."""
    from app.services.outcome_ledger import OutcomeLedger

    ledger = OutcomeLedger(ledger_path)
    rows = ledger.verified_outcomes()
    if capability_filter:
        rows = [r for r in rows if r.get("capability") == capability_filter]
    total_actual = sum(float(r.get("actual_impact_sar") or 0) for r in rows)
    return {
        "verified_rows": len(rows),
        "total_verified_impact_sar": round(total_actual, 2),
        "rows": rows,
    }