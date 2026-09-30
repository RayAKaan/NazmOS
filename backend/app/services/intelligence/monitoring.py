"""The Business Monitor — one Intelligence evaluation, end to end.

    Orbit state
        → BusinessContext
        → Signals
        → RootCauses
        → Impacts
        → Recommendations
        → Jev advisory (bounded, optional)
        → DecisionCandidates → Governance
        → Alerts
        → IntelligenceRun

Guarantees:
- Intelligence never executes and never authorizes.
- A Jev failure never fails the run (explicit deterministic-only fallback).
- A failing detector produces a PARTIAL run with the failure recorded, never a
  silently fabricated "clean" result.
- Missing Orbit state is an explicit failure, never a zero-valued result.
- Re-running against unchanged state converges (deterministic fingerprints).
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.intelligence import advisory as advisory_engine
from app.services.intelligence import impact as impact_engine
from app.services.intelligence import recommendations as rec_engine
from app.services.intelligence import signals as signal_engine
from app.services.intelligence.alerts import build_alerts
from app.services.intelligence.context import OrbitStateUnavailable, build_business_context
from app.services.intelligence.contracts import (
    BusinessContext,
    IntelligenceRun,
    IntelligenceRunStatus,
    Signal,
)
from app.services.intelligence.decisions import generate_decision_candidates
from app.services.intelligence.root_cause import analyze_signals
from app.utils.logger import setup_logger

logger = setup_logger("intelligence_monitor")

MONITOR_VERSION = "monitor-v1"


async def run_intelligence(
    session: AsyncSession,
    business_id: UUID,
    *,
    state_version: Optional[str] = None,
    trigger: Optional[str] = None,
    enable_advisory: bool = False,
    shariah_approved: bool = False,
    max_advisory_consultations: int = 3,
    detectors: Optional[list[str]] = None,
    client: Any | None = None,
) -> IntelligenceRun:
    """Run one bounded Intelligence evaluation for a business.

    Args:
        session: Async session (must already carry RLS tenant context).
        business_id: Tenant-scoped business.
        state_version: Optional specific Orbit ``audit_id``; defaults to latest.
        trigger: Free-form provenance label (e.g. "orbit_ingest", "manual").
        enable_advisory: Opt-in Jev advisory. Off by default so a deterministic
            run never depends on external AI availability.
        shariah_approved: Whether a qualified Shariah review exists. Governance
            requires this; Intelligence never assumes it.
        detectors: Restrict to a subset of detectors (testing/debug).
    """
    started = datetime.utcnow()
    warnings: list[str] = []
    failed_detectors: list[str] = []
    detector_errors: dict[str, str] = {}

    # ── 1. Context (Orbit is authoritative) ─────────────────────────────────
    try:
        context = await build_business_context(
            session, business_id, state_version=state_version
        )
    except OrbitStateUnavailable as exc:
        # No canonical truth: fail explicitly. Never fabricate a business state.
        return IntelligenceRun(
            business_id=business_id,
            state_version=state_version or "",
            started_at=started,
            completed_at=datetime.utcnow(),
            status=IntelligenceRunStatus.FAILED,
            warnings=[f"orbit_state_unavailable:{exc}"],
        )

    # ── 2. Signals (deterministic, failure-isolated) ───────────────────────
    try:
        detected, insufficients = signal_engine.run_detectors(context, only=detectors)
    except signal_engine.DetectorFailure as exc:
        logger.warning("intelligence detector failure", extra={"error": str(exc)})
        failed_detectors.append(exc.detector)
        detector_errors[exc.detector] = exc.message
        detected, insufficients = [], []

    for marker in insufficients:
        warnings.append(
            f"insufficient_data:{marker.detector_name}:{marker.metric}:{marker.reason}"
        )

    # ── 3. Root causes ─────────────────────────────────────────────────────
    try:
        causes = analyze_signals(context, detected)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("intelligence root cause failure", extra={"error": str(exc)})
        causes = []
        warnings.append(f"root_cause_failed:{type(exc).__name__}")

    # ── 4. Impact (POTENTIAL + EXPECTED only) ──────────────────────────────
    try:
        impacts = impact_engine.quantify(context, detected, causes)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("intelligence impact failure", extra={"error": str(exc)})
        impacts = []
        warnings.append(f"impact_failed:{type(exc).__name__}")

    # ── 5. Recommendations (deterministic, canonical vocabulary) ───────────
    try:
        recs = rec_engine.generate_recommendations(context, detected, causes, impacts)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("intelligence recommendation failure", extra={"error": str(exc)})
        recs = []
        warnings.append(f"recommendation_failed:{type(exc).__name__}")

    # ── 6. Bounded Jev advisory (never authoritative, never fatal) ─────────
    try:
        advisories = await advisory_engine.advisory_for_recommendations(
            context,
            recs,
            potentials=impact_engine.potentials_by_signal(impacts),
            enabled=enable_advisory,
            max_consultations=max_advisory_consultations,
            client=client,
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("intelligence advisory failure", extra={"error": str(exc)})
        advisories = {
            rec.recommendation_id: advisory_engine.deterministic_only(
                f"advisory_failed:{type(exc).__name__}"
            )
            for rec in recs
        }
        warnings.append(f"advisory_failed:{type(exc).__name__}")

    for rec_id, adv in advisories.items():
        if not adv.jev_consulted and adv.source.value != "deterministic_only":
            warnings.append(f"advisory_source_not_jev:{rec_id}:{adv.source.value}")

    # ── 7. Decision candidates + Governance handoff ────────────────────────
    try:
        candidates = generate_decision_candidates(
            context, recs, advisories, impacts, shariah_approved=shariah_approved
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("intelligence decision failure", extra={"error": str(exc)})
        candidates = []
        warnings.append(f"decision_candidate_failed:{type(exc).__name__}")

    # ── 8. Alerts (deduplicated) ───────────────────────────────────────────
    try:
        alerts = build_alerts(detected, recs)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("intelligence alert failure", extra={"error": str(exc)})
        alerts = []
        warnings.append(f"alert_failed:{type(exc).__name__}")

    # ── 9. Status ──────────────────────────────────────────────────────────
    if failed_detectors:
        status = IntelligenceRunStatus.PARTIAL
    elif not detected and insufficients:
        # Everything was unjudgeable: partial, not a clean bill of health.
        status = IntelligenceRunStatus.PARTIAL
    else:
        status = IntelligenceRunStatus.COMPLETED

    return IntelligenceRun(
        business_id=business_id,
        state_version=context.state_version,
        started_at=started,
        completed_at=datetime.utcnow(),
        status=status,
        signals=detected,
        root_causes=causes,
        impacts=impacts,
        recommendations=recs,
        decision_candidates=candidates,
        alerts=alerts,
        evidence_ids=list(context.evidence_ids),
        warnings=warnings,
        failed_detectors=failed_detectors,
        detector_errors=detector_errors,
    )


def signals_by_fingerprint(run: IntelligenceRun) -> dict[str, Signal]:
    """Index a run's signals by deterministic fingerprint (idempotency key)."""
    return {s.fingerprint: s for s in run.signals if s.fingerprint}


def _material_signal_key(signal: Signal) -> tuple:
    """The material identity of a signal.

    Deliberately excludes ``signal_id`` and ``detected_at``: two runs against
    unchanged state produce the same business signal with different surrogate
    ids and timestamps. Convergence is about *material* identity, not object
    identity.
    """
    return (
        signal.fingerprint,
        signal.signal_type,
        signal.domain,
        signal.metric,
        round(signal.observed_value, 6),
        round(signal.deviation, 6),
        signal.severity.value,
        signal.status.value,
    )


def _material_alert_key(alert) -> tuple:
    return (
        alert.fingerprint,
        alert.alert_type,
        alert.severity.value,
        alert.title,
    )


def _material_recommendation_key(rec: Recommendation) -> tuple:
    """The material identity of a recommendation.

    Excludes surrogate ids (``recommendation_id``, ``signal_ids``,
    ``root_cause_ids``) and timestamps: a re-run against unchanged state yields
    the same recommendation about the same domain with the same action.
    """
    return (
        rec.state_version,
        rec.action_type,
        rec.recommendation_version,
        tuple(sorted(rec.affected_resources)),
        rec.urgency,
        rec.risk,
    )


def run_is_idempotent(previous: IntelligenceRun, current: IntelligenceRun) -> bool:
    """True when a re-run against unchanged state yields identical artifacts.

    Used by monitoring/acceptance tests to prove repeated evaluation converges
    instead of producing unbounded duplicate signals and alerts. Compares
    *material* identity, so freshly minted surrogate ids do not cause a false
    negative.
    """
    if previous.state_version != current.state_version:
        return False
    prev_signals = sorted(_material_signal_key(s) for s in previous.signals)
    curr_signals = sorted(_material_signal_key(s) for s in current.signals)
    if prev_signals != curr_signals:
        return False
    prev_alerts = sorted(_material_alert_key(a) for a in previous.alerts)
    curr_alerts = sorted(_material_alert_key(a) for a in current.alerts)
    if prev_alerts != curr_alerts:
        return False
    prev_recs = sorted(_material_recommendation_key(r) for r in previous.recommendations)
    curr_recs = sorted(_material_recommendation_key(r) for r in current.recommendations)
    return prev_recs == curr_recs
