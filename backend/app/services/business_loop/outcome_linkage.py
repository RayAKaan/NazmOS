"""Phase 4F — canonical execution→outcome linkage + verified capture.

This module is the SMALL canonical association between a durable cycle run
(tenant/business/cycle) and its outcome record, and it persists the verified
result through the EXISTING ``app.services.outcome_ledger.OutcomeLedger`` V1
(idempotent, opt-in, DLP-clean). It creates NO second ledger, NO learning
store and NO new business-truth authority — ``VerifiedOutcomeLedger.attach``
in ``outcomes.py`` is superseded by the readback-confirmed path here.

Guarantees (all deterministic, DB-free testable, JSON-safe):
    * ``derive_outcome_key`` is stable per (tenant, execution_key,
      recommendation) so replays coalesce onto ONE ledger row.
    * Linkage is rebuilt deterministically from the run + outcome each time
      (restart/replay-safe): identical inputs produce identical linkage.
    * Every execution that ran produces an OutcomeRecord; an execution with
      no measurable result is REPORTED/OBSERVED, never VERIFIED.
    * VERIFIED requires DISTINCT baseline/post state versions (see
      ``outcomes.verify_outcome``).
    * Attribution is captured EXACTLY (provider/model verbatim) and never
      upgraded: a Jev advisory alone can neither verify nor authorize learning.
    * ``attach_outcome`` confirms the row by readback — a bare ``True`` from
      the best-effort V1 write is never treated as proof of capture.
    * Tenant isolation is enforced at the attach layer: an outcome without a
      tenant-scoped run binding is refused (``tenant_unscoped``).
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.services.business_loop.contracts import AdvisorySource, VerificationStatus
from app.services.business_loop.outcomes import (
    OutcomeRecord,
    unverified_outcome,
    verify_outcome,
)

_OUTCOME_CAPABILITY = "business_loop.verified"
_LEDGER_NAME = "outcome_ledger_v1"
_ATTRIBUTION_NOISE = {"", "none", "n/a", "unknown"}
_ATTRIBUTION_SUFFICIENT = {"deterministic_measurement", "deterministic_advisory", "provider_advisory"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def derive_outcome_key(
    *,
    tenant_id: str,
    execution_key: str,
    recommendation_id: str,
    recommendation_version: int,
) -> str:
    """Idempotent outcome identity (tenant-scoped).

    The same execution+recommendation for the same tenant ALWAYS maps to the
    same key, so replayed executions coalesce to one row. Tenant is part of
    the composite so identical execution keys never collide across tenants.
    """
    composite = f"{tenant_id}:{execution_key}:{recommendation_id}:{recommendation_version}"
    return hashlib.sha256(composite.encode()).hexdigest()[:24]


def outcome_from_run(run: Any) -> OutcomeRecord:
    """Rehydrate the canonical OutcomeRecord from a CycleRun's state_output.

    Lossless for the fields the loop produces; a run with no outcome dict
    (e.g. execution skipped) maps to an explicit UNVERIFIED record.
    """
    run_cycle_id = str(getattr(run, "cycle_id", "") or "")
    state = getattr(run, "state_output", {}) or {}
    d = state.get("outcome") or {}
    if not isinstance(d, dict) or not d:
        return unverified_outcome(
            outcome_id=f"out-{run_cycle_id}",
            recommendation_id="",
            recommendation_version=1,
            execution_key="",
        )
    raw_status = str(d.get("verification_status", ""))
    try:
        status = VerificationStatus(raw_status)
    except ValueError:
        status = VerificationStatus.UNVERIFIED
    return OutcomeRecord(
        outcome_id=str(d.get("outcome_id") or f"out-{run_cycle_id}"),
        recommendation_id=str(d.get("recommendation_id") or ""),
        recommendation_version=int(d.get("recommendation_version") or 1),
        execution_key=str(d.get("execution_key") or ""),
        baseline_state_version=str(d.get("baseline_state_version") or getattr(run, "starting_state_version", "") or ""),
        post_action_state_version=str(d.get("post_action_state_version") or ""),
        verification_status=status,
        expected_impact_sar=d.get("expected_impact_sar"),
        observed_impact_sar=d.get("observed_impact_sar"),
        verification_method=str(d.get("verification_method") or ""),
        measurement_window=str(d.get("measurement_window") or ""),
        evidence=tuple(d.get("evidence") or ()),
    )


def attribution_quality(
    *,
    verification_status: VerificationStatus | str,
    verification_method: str,
    observed_impact_sar: float | None,
    advisory_source: str = "",
    advisory_provider: str = "",
    advisory_validated: bool = True,
) -> str:
    """Deterministic attribution classifier (never upgraded by a provider).

    A deterministic measurement (external authority announcing a measured
    impact for the executed action) dominates ANY advisory: neither a Jev nor
    a provider fallback can upgrade or downgrade it. With no measurement, only
    the exact advisory provenance is recorded:
        deterministic_advisory / provider_advisory   -> candidate-sufficient
        jev_advisory_only                           -> NEVER sufficient
        none                                         -> nothing attributable
    """
    if not isinstance(verification_status, VerificationStatus):
        try:
            verification_status = VerificationStatus(str(verification_status))
        except ValueError:
            verification_status = VerificationStatus.UNVERIFIED
    if (
        verification_status in (VerificationStatus.VERIFIED, VerificationStatus.PARTIALLY_VERIFIED)
        and observed_impact_sar is not None
        and verification_method
    ):
        return "deterministic_measurement"
    source = (advisory_source or "").strip().lower()
    provider = (advisory_provider or "").strip().lower()
    if source == AdvisorySource.JEV.value or "jev" in provider:
        return "jev_advisory_only"
    if source in (AdvisorySource.MOCKED.value, AdvisorySource.DETERMINISTIC_ONLY.value, "deterministic"):
        return "deterministic_advisory"
    if advisory_validated and provider not in _ATTRIBUTION_NOISE:
        return "provider_advisory"
    return "none"


def attribution_sufficient(quality: str) -> bool:
    """Deterministic gate: which attribution signatures may feed learning."""
    return quality in _ATTRIBUTION_SUFFICIENT


@dataclass(frozen=True)
class OutcomeLinkage:
    """The durable association between one cycle run and its outcome record.

    References only immutable identifiers and measured numbers already in the
    run/outcome — it never invents values, never duplicating large payloads.
    """

    outcome_id: str
    cycle_id: str
    tenant_id: str
    business_id: str
    baseline_state_version: str
    post_action_state_version: str
    opportunity_id: str
    recommendation_id: str
    recommendation_version: int
    action_type: str
    execution_key: str
    action_attempt: int = 1
    executed_at: str = ""
    verification_status: str = "unverified"
    expected_impact_sar: float | None = None
    observed_impact_sar: float | None = None
    impact_delta_sar: float | None = None
    verification_method: str = ""
    measurement_window: str = ""
    measurement_evidence_count: int = 0
    attribution_source: str = ""
    attribution_provider: str = ""
    attribution_model: str = ""
    attribution_quality: str = "none"
    risk_flags: tuple[str, ...] = ()
    evidence_watermark: str = ""
    outcome_key: str = ""
    recorded_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = {
            "outcome_id": self.outcome_id,
            "cycle_id": self.cycle_id,
            "tenant_id": self.tenant_id,
            "business_id": self.business_id,
            "baseline_state_version": self.baseline_state_version,
            "post_action_state_version": self.post_action_state_version,
            "opportunity_id": self.opportunity_id,
            "recommendation_id": self.recommendation_id,
            "recommendation_version": self.recommendation_version,
            "action_type": self.action_type,
            "execution_key": self.execution_key,
            "action_attempt": self.action_attempt,
            "executed_at": self.executed_at,
            "verification_status": self.verification_status,
            "expected_impact_sar": self.expected_impact_sar,
            "observed_impact_sar": self.observed_impact_sar,
            "impact_delta_sar": self.impact_delta_sar,
            "verification_method": self.verification_method,
            "measurement_window": self.measurement_window,
            "measurement_evidence_count": self.measurement_evidence_count,
            "attribution_source": self.attribution_source,
            "attribution_provider": self.attribution_provider,
            "attribution_model": self.attribution_model,
            "attribution_quality": self.attribution_quality,
            "evidence_watermark": self.evidence_watermark,
            "outcome_key": self.outcome_key,
            "recorded_at": self.recorded_at,
        }
        if self.risk_flags:
            d["risk_flags"] = list(self.risk_flags)
        return d


def build_linkage(run: Any, outcome: OutcomeRecord | None = None) -> OutcomeLinkage:
    """Deterministically associate a CycleRun with its canonical outcome.

    Pure: identical run/outcome inputs always yield identical linkage, so the
    state_output copy made by the orchestrator and the one made by the
    attach path can never drift.
    """
    state = getattr(run, "state_output", {}) or {}
    out = outcome or outcome_from_run(run)
    cycle_id = str(getattr(run, "cycle_id", "") or "")
    tenant_id = str(getattr(run, "tenant_id", "") or "")
    business_id = str(getattr(run, "business_id", "") or "")
    starting_version = str(getattr(run, "starting_state_version", "") or "")
    watermark = str(getattr(run, "evidence_watermark", "") or "")
    created_at = str(getattr(run, "created_at", "") or "")

    recos = state.get("recommendations") or []
    reco = recos[0] if isinstance(recos, list) and recos and isinstance(recos[0], dict) else {}
    opps = state.get("opportunities") or []
    opp = opps[0] if isinstance(opps, list) and opps and isinstance(opps[0], dict) else {}
    execution = state.get("execution") or {}
    if not isinstance(execution, dict):
        execution = {}
    advisory = state.get("advisory") or {}
    if not isinstance(advisory, dict):
        advisory = {}

    quality = attribution_quality(
        verification_status=out.verification_status,
        verification_method=out.verification_method,
        observed_impact_sar=out.observed_impact_sar,
        advisory_source=str(advisory.get("source") or ""),
        advisory_provider=str(advisory.get("provider") or ""),
        advisory_validated=bool(advisory.get("validation_passed", True)),
    )
    expected = out.expected_impact_sar
    observed = out.observed_impact_sar
    delta = round(observed - expected, 2) if observed is not None and expected is not None else None
    recorded_at = out.recorded_at or _now_iso()

    return OutcomeLinkage(
        outcome_id=out.outcome_id,
        cycle_id=cycle_id,
        tenant_id=tenant_id,
        business_id=business_id,
        baseline_state_version=out.baseline_state_version or starting_version,
        post_action_state_version=out.post_action_state_version or str(state.get("post_state_version", "") or ""),
        opportunity_id=str(opp.get("opportunity_id", "") or ""),
        recommendation_id=out.recommendation_id,
        recommendation_version=out.recommendation_version,
        action_type=str(execution.get("action_type", "") or "") or str(reco.get("action_type", "") or ""),
        execution_key=out.execution_key,
        action_attempt=int(execution.get("attempt", 1) or 1),
        executed_at=created_at or recorded_at,
        verification_status=out.verification_status.value if hasattr(out.verification_status, "value") else str(out.verification_status),
        expected_impact_sar=expected,
        observed_impact_sar=observed,
        impact_delta_sar=delta,
        verification_method=out.verification_method or "",
        measurement_window=out.measurement_window or "",
        measurement_evidence_count=len(out.evidence),
        attribution_source=str(advisory.get("source") or ""),
        attribution_provider=str(advisory.get("provider") or ""),
        attribution_model=str(advisory.get("model") or ""),
        attribution_quality=quality,
        risk_flags=tuple(str(f) for f in (advisory.get("risk_flags") or ())),
        evidence_watermark=watermark,
        outcome_key=derive_outcome_key(
            tenant_id=tenant_id,
            execution_key=out.execution_key,
            recommendation_id=out.recommendation_id,
            recommendation_version=out.recommendation_version,
        ),
        recorded_at=recorded_at,
    )


def _outcome_status(outcome: OutcomeRecord) -> str:
    mapping = {
        VerificationStatus.VERIFIED: "confirmed",
        VerificationStatus.PARTIALLY_VERIFIED: "partial",
        VerificationStatus.DISPUTED: "failed",
        VerificationStatus.UNVERIFIED: "rejected",
        VerificationStatus.OBSERVED: "confirmed",
        VerificationStatus.REPORTED: "unknown",
    }
    return mapping.get(outcome.verification_status, "unknown")


@dataclass(frozen=True)
class OutcomeAttachment:
    """Readback-confirmed result of attaching an outcome to OutcomeLedger V1."""

    outcome_key: str
    outcome_id: str
    capability: str
    ledger: str
    recorded: bool
    attached_verified: bool
    row_present: bool
    row_verified: bool
    outcome_status: str
    reason: str
    recorded_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return {
            "outcome_key": self.outcome_key,
            "outcome_id": self.outcome_id,
            "capability": self.capability,
            "ledger": self.ledger,
            "recorded": self.recorded,
            "attached_verified": self.attached_verified,
            "row_present": self.row_present,
            "row_verified": self.row_verified,
            "outcome_status": self.outcome_status,
            "reason": self.reason,
            "recorded_at": self.recorded_at,
        }


def _resolved_ledger() -> tuple[OutcomeLedger | None, str]:
    """Resolve the V1 ledger from settings; ``(None, "ledger_disabled")`` off."""
    from app.config import get_settings

    path = str(getattr(get_settings(), "AI_OUTCOME_LEDGER_PATH", "") or "")
    if not path:
        return None, "ledger_disabled"
    from app.services.outcome_ledger import OutcomeLedger

    return OutcomeLedger(path), ""


def attach_outcome(
    outcome: OutcomeRecord,
    *,
    run: Any = None,
    ledger: Any = None,
) -> OutcomeAttachment:
    """Attach one outcome to OutcomeLedger V1 (idempotent, readback-confirmed).

    The ledger write is best-effort and never blocks the cycle. Unlike the
    legacy ``VerifiedOutcomeLedger.attach``, this path CONFIRMS the row landed
    via readback — a bare ``True`` from the V1 write is never treated as proof.
    """
    linkage = build_linkage(run, outcome) if run is not None else None
    tenant_id = linkage.tenant_id if linkage is not None else ""
    if not tenant_id:
        return OutcomeAttachment(
            outcome_key="",
            outcome_id=outcome.outcome_id,
            capability=_OUTCOME_CAPABILITY,
            ledger=_LEDGER_NAME,
            recorded=False,
            attached_verified=False,
            row_present=False,
            row_verified=False,
            outcome_status="rejected",
            reason="tenant_unscoped",
        )
    key = derive_outcome_key(
        tenant_id=tenant_id,
        execution_key=outcome.execution_key,
        recommendation_id=outcome.recommendation_id,
        recommendation_version=outcome.recommendation_version,
    )
    if ledger is None:
        ledger, disabled_reason = _resolved_ledger()
        if ledger is None:
            return OutcomeAttachment(
                outcome_key=key,
                outcome_id=outcome.outcome_id,
                capability=_OUTCOME_CAPABILITY,
                ledger=f"{_LEDGER_NAME}(disabled)",
                recorded=False,
                attached_verified=False,
                row_present=False,
                row_verified=False,
                outcome_status=_outcome_status(outcome),
                reason=disabled_reason,
            )

    status = _outcome_status(outcome)
    recorded = ledger.record(
        decision_key=key,
        capability=_OUTCOME_CAPABILITY,
        deterministic_decision=outcome.recommendation_id or "unknown",
        source=(linkage.attribution_source if linkage is not None else "") or "business_loop",
        capsule_hash=outcome.execution_key,
        provider=(linkage.attribution_provider if linkage is not None else "") or None,
        model=(linkage.attribution_model if linkage is not None else "") or None,
        risk_flags=list(linkage.risk_flags) if linkage is not None else [],
        latency_ms=0.0,
    )
    attached = False
    if recorded:
        attached = ledger.record_verified_result(
            decision_key=key,
            outcome_status=status,
            verified=outcome.is_verified,
            actual_impact_sar=outcome.observed_impact_sar,
            expected_impact_sar=outcome.expected_impact_sar,
        )
    row = ledger.row(key)
    row_present = row is not None
    row_verified = bool(row.get("verified", False)) if row else False

    reason = ""
    if not recorded:
        reason = "record_skipped"
    elif not row_present:
        reason = "row_missing"
    elif outcome.is_verified and not row_verified:
        reason = "verified_mismatch"
    return OutcomeAttachment(
        outcome_key=key,
        outcome_id=outcome.outcome_id,
        capability=_OUTCOME_CAPABILITY,
        ledger=_LEDGER_NAME,
        recorded=recorded,
        attached_verified=bool(attached),
        row_present=row_present,
        row_verified=row_verified,
        outcome_status=status,
        reason=reason,
    )


def attach_cycle_outcome(run: Any, *, ledger: Any = None) -> OutcomeAttachment | None:
    """Attach the run's outcome once per run (idempotent replay-safe marker).

    Returns ``None`` when there is no realized execution to record (skipped /
    failed / unknown outcome) or when the run already recorded an attempt —
    the ``outcome_recorded`` marker is persisted with the run so a replayed
    advance never double-attaches (the ledger key remains the backstop).
    """
    if run is None:
        return None
    state = getattr(run, "state_output", {}) or {}
    # Only attach once the verification stage produced an actual outcome
    # record: advancing past EXECUTION (where the outcome is not yet written)
    # must not fabricate a placeholder capture with an empty execution key.
    if not state.get("outcome"):
        return None
    execution = state.get("execution") or {}
    if not isinstance(execution, dict):
        execution = {}
    if execution.get("skipped") or not execution.get("receipt", {}).get("ok"):
        return None
    if state.get("outcome_recorded"):
        return None
    outcome = outcome_from_run(run)
    return attach_outcome(outcome, run=run, ledger=ledger)


__all__ = [
    "OutcomeAttachment",
    "OutcomeLinkage",
    "attach_cycle_outcome",
    "attach_outcome",
    "attribution_quality",
    "attribution_sufficient",
    "build_linkage",
    "derive_outcome_key",
    "outcome_from_run",
]