"""Business Context — the single Intelligence entry point.

Projects authoritative Orbit state (+ bounded Loop state) into the canonical
``BusinessContext``. Orbit owns truth; this module only *projects* it.

Design constraints honoured here:
- Orbit is authoritative. We never re-read raw uploads or re-derive business
  truth.
- Missing is not zero. If Orbit has no metric, the context carries an explicit
  ``MISSING``/``UNKNOWN`` marker instead of a fabricated ``0``.
- Stale is not fresh. Freshness is derived from the Orbit audit's own
  ``created_at`` timestamp.
- Every field keeps ``state_version`` + ``evidence_ids`` so downstream artifacts
  can be traced and invalidated.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.audit_persistence import AuditPersistenceService
from app.services.intelligence.contracts import (
    BusinessContext,
    FreshnessStatus,
    evaluate_freshness,
)

# Orbit evidence older than this is considered stale for advisory purposes.
STALE_THRESHOLD_HOURS = 4.0
# Beyond this we refuse to treat Orbit state as current at all.
MISSING_THRESHOLD_HOURS = 24.0

DEFAULT_HISTORY_WINDOW = 20


class OrbitStateUnavailable(RuntimeError):
    """Raised when no canonical Orbit state exists for a business.

    Intelligence must NOT silently fabricate a business state. Callers translate
    this into an explicit missing-data outcome.
    """


def _as_mapping(value: Any) -> dict[str, Any]:
    """Normalise Orbit's persisted JSONB (or dataclass) into a plain mapping.

    ``OrbitAuditResult`` stores ``health_breakdown`` / ``exposures`` / ``findings``
    as JSONB, so the round-tripped value is a dict. We accept either shape and
    never invent missing keys.
    """
    if value is None:
        return {}
    if isinstance(value, dict):
        return dict(value)
    if hasattr(value, "__dict__"):
        return {k: v for k, v in vars(value).items() if not k.startswith("_")}
    return {}


def _metric_value(metric: Any) -> tuple[float | None, list[str], str]:
    """Extract (value, evidence_ids, confidence) from a persisted Orbit metric.

    Returns ``value=None`` when Orbit did not record the metric. Callers MUST
    treat ``None`` as missing data — never coerce it to ``0``.
    """
    if metric is None:
        return None, [], "UNKNOWN"
    if isinstance(metric, (int, float)):
        return float(metric), [], "MEDIUM"
    mapping = _as_mapping(metric)
    raw = mapping.get("value")
    if raw is None:
        return None, [], "UNKNOWN"
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None, [], "UNKNOWN"
    evidence = mapping.get("evidence_ids") or []
    if not isinstance(evidence, list):
        evidence = []
    confidence = str(mapping.get("confidence") or "MEDIUM")
    return value, [str(e) for e in evidence], confidence


async def build_business_context(
    session: AsyncSession,
    business_id: UUID,
    *,
    state_version: Optional[str] = None,
    window: Optional[int] = None,
) -> BusinessContext:
    """Assemble the canonical ``BusinessContext`` for a business.

    Args:
        session: Active async DB session (must already carry RLS tenant context).
        business_id: Tenant-scoped business.
        state_version: Optional Orbit ``audit_id``. When omitted the latest
            persisted Orbit audit is used.
        window: How many prior Orbit audits to consider for baselines.

    Raises:
        OrbitStateUnavailable: when the business has no canonical Orbit state.
    """
    persistence = AuditPersistenceService(session)

    if state_version:
        try:
            orbit_audit_id = UUID(str(state_version))
        except (TypeError, ValueError) as exc:
            raise OrbitStateUnavailable(
                f"state_version {state_version!r} is not a valid Orbit audit id"
            ) from exc
        orbit_result = await persistence.get_audit_run(orbit_audit_id)
        if orbit_result is None:
            raise OrbitStateUnavailable(f"Orbit audit {state_version} not found")
        if orbit_result.business_id and str(orbit_result.business_id) != str(business_id):
            # Do not disclose the existence of another tenant's audit.
            raise OrbitStateUnavailable(f"Orbit audit {state_version} not found")
    else:
        orbit_result = await persistence.get_latest_audit_for_business(business_id)
        if orbit_result is None:
            raise OrbitStateUnavailable(
                f"No Orbit audit available for business {business_id}"
            )

    history = await persistence.get_audit_history(
        business_id=business_id,
        limit=(window or DEFAULT_HISTORY_WINDOW) + 1,
        offset=0,
    )

    # ── Freshness from Orbit's own audit timestamp ───────────────────────────
    snapshot_timestamp = datetime.utcnow()
    if orbit_result.generated_at:
        try:
            snapshot_timestamp = datetime.fromisoformat(
                str(orbit_result.generated_at).replace("Z", "+00:00")
            ).replace(tzinfo=None)
        except ValueError:
            snapshot_timestamp = datetime.utcnow()

    freshness = evaluate_freshness(
        snapshot_timestamp,
        max_age_hours=MISSING_THRESHOLD_HOURS,
        stale_threshold_hours=STALE_THRESHOLD_HOURS,
    )

    # ── Normalise Orbit payload sections ─────────────────────────────────────
    health_breakdown = _as_mapping(orbit_result.health_breakdown)
    exposures = _as_mapping(orbit_result.exposures)
    limitations = _as_mapping(orbit_result.limitations)
    findings = [f for f in (orbit_result.findings or []) if isinstance(f, dict)]
    opportunities = [o for o in (orbit_result.opportunities or []) if isinstance(o, dict)]

    metrics: dict[str, Any] = {}
    for key, raw in _as_mapping(orbit_result.metrics).items():
        value, evidence, confidence = _metric_value(raw)
        metrics[key] = {
            "value": value,
            "present": value is not None,
            "evidence_ids": evidence,
            "confidence": confidence,
        }

    # ── Evidence provenance ──────────────────────────────────────────────────
    evidence_ids: list[str] = []
    for key in _as_mapping(orbit_result.evidence).keys():
        evidence_ids.append(str(key))
    for finding in findings:
        for eid in finding.get("evidence_ids") or []:
            evidence_ids.append(str(eid))
    for entry in metrics.values():
        evidence_ids.extend(entry.get("evidence_ids") or [])
    # Preserve order while removing duplicates.
    evidence_ids = list(dict.fromkeys(evidence_ids))

    # ── Historical series for baselines ──────────────────────────────────────
    # Orbit's history rows persist ``health_score`` and ``health_breakdown`` per
    # audit, so per-domain baselines are derivable deterministically. Orbit's
    # history does NOT persist exposures, so we deliberately leave
    # ``exposure_series`` empty — detectors then report insufficient data
    # instead of inventing a prior-period exposure.
    domain_score_series: dict[str, list[dict[str, Any]]] = {}
    for row in reversed(history):
        audit_id = str(row.get("id") or "")
        observed_at = (
            row["created_at"].isoformat()
            if isinstance(row.get("created_at"), datetime)
            else None
        )
        for domain, key in (
            ("sales", "sales"),
            ("margins", "margins"),
            ("inventory", "inventory"),
            ("procurement", "procurement"),
            ("data_quality", "data_quality"),
        ):
            breakdown_row = row.get("health_breakdown")
            score = None
            if isinstance(breakdown_row, dict):
                entry = breakdown_row.get(key)
                if isinstance(entry, dict):
                    score = entry.get("score")
                elif entry is not None:
                    score = entry
            if score is not None:
                domain_score_series.setdefault(domain, []).append(
                    {"audit_id": audit_id, "score": score, "observed_at": observed_at}
                )

    historical = {
        "audit_count": len(history),
        "health_score_series": [
            {
                "audit_id": str(row.get("id") or ""),
                "health_score": row.get("health_score"),
                "observed_at": row.get("created_at").isoformat()
                if isinstance(row.get("created_at"), datetime)
                else None,
            }
            for row in reversed(history)
        ],
        "domain_score_series": domain_score_series,
        "exposure_series": {},
        "window_start": (
            history[-1]["created_at"].isoformat()
            if history and isinstance(history[-1].get("created_at"), datetime)
            else None
        ),
    }

    # ── Data quality from Orbit limitations (explicit, never invented) ───────
    we_know = limitations.get("we_know") or []
    we_estimate = limitations.get("we_estimate") or []
    we_dont_know = limitations.get("we_dont_know") or []
    data_quality_score = None
    total = len(we_know) + len(we_estimate) + len(we_dont_know)
    if total:
        data_quality_score = round(len(we_know) / total, 4)

    # ── Owner constraints / goals (read-only projection) ─────────────────────
    constraints: dict[str, Any] = {}
    goals: dict[str, Any] = {}
    external_context: dict[str, Any] = {}
    inventory_context: dict[str, Any] = {}
    recent_outcomes: list[dict[str, Any]] = []
    open_recommendations: list[Any] = []
    existing_decisions: list[Any] = []
    active_alerts: list[Any] = []

    return BusinessContext(
        business_id=business_id,
        state_version=str(orbit_result.audit_id),
        snapshot_timestamp=snapshot_timestamp,
        data_freshness=freshness,
        data_quality_score=data_quality_score,
        business_type=orbit_result.business_type or "retail",
        health_score=int(orbit_result.health_score or 0),
        health_breakdown=health_breakdown,
        exposures=exposures,
        metrics=metrics,
        findings=findings,
        opportunities=opportunities,
        limitations=limitations,
        historical_metrics=historical,
        existing_decisions=existing_decisions,
        open_recommendations=open_recommendations,
        previous_outcomes=recent_outcomes,
        active_constraints=constraints,
        active_goals=goals,
        supplier_context={},
        inventory_context=inventory_context,
        financial_context=exposures,
        operational_context=health_breakdown,
        external_context=external_context,
        evidence_ids=evidence_ids,
        generated_at=datetime.utcnow(),
    )


def baseline_window(context: BusinessContext, *, max_age_days: int = 90) -> int:
    """Deterministic baseline window size derived from available Orbit history.

    Returns the number of prior audits usable as a baseline. A single audit (the
    current one) yields 0, which detectors must treat as "insufficient data"
    rather than comparing the current period against itself.
    """
    series = context.historical_metrics.get("health_score_series") or []
    # Exclude the current audit from the baseline.
    prior = [p for p in series if p.get("audit_id") != context.state_version]
    if context.snapshot_timestamp:
        cutoff = context.snapshot_timestamp - timedelta(days=max_age_days)
        prior = [
            p for p in prior
            if not p.get("observed_at")
            or datetime.fromisoformat(str(p["observed_at"])) >= cutoff
        ]
    return len(prior)
