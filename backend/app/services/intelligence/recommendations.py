"""Deterministic recommendation generation.

Pipeline:  Signal → RootCauses → Impact → Available Actions → Constraints
           → Candidate Recommendations

Reuses the repository's authoritative machinery rather than adding a third
scoring formula:

- ``app.services.action_registry.ACTION_REGISTRY`` — the action vocabulary and
  approval/execution semantics. Governance consumes these keys verbatim.
- ``app.orchestration.contracts.CANONICAL_ACTION_TYPES`` — the canonical
  upper-case action vocabulary used in contracts and Jev's advisory contract.
- ``app.services.decision_scoring.compute_recommendation_score`` — the single
  documented, centralized scoring function.

Intelligence produces *candidates*. It never authorizes and never executes.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Optional

from app.orchestration.contracts import CANONICAL_ACTION_TYPES
from app.services.action_registry import ACTION_REGISTRY, get_action_spec
from app.services.decision_scoring import compute_recommendation_score
from app.services.intelligence.contracts import (
    AdvisoryResult,
    BusinessContext,
    ImpactEstimate,
    Recommendation,
    RecommendationStatus,
    RootCause,
    RootCauseSupportLevel,
    Signal,
    SignalSeverity,
)

RECOMMENDATION_VERSION = "recommend-v1"

# A candidate is only meaningful for this long; it is invalidated by state change.
RECOMMENDATION_TTL_HOURS = 72

# Registry action key -> the canonical (upper-case) contract vocabulary.
REGISTRY_TO_CANONICAL: dict[str, str] = {
    "discount": "DISCOUNT",
    "reorder": "REORDER",
    "restock": "RESTOCK",
    "recovery_match": "RECOVERY_MATCH",
    "margin_fix": "MARGIN_FIX",
    "transfer_inventory": "TRANSFER",
    "pricing_increase": "PRICING_INCREASE",
    "pricing_decrease": "PRICING_DECREASE",
    "expiry_alert": "EXPIRY_ALERT",
}

# Registry action key -> the canonical contract vocabulary to use when the
# registry has no direct canonical counterpart.
CANONICAL_FALLBACK = {
    "reorder": "REORDER",
    "restock": "RESTOCK",
    "transfer_inventory": "TRANSFER",
    "discount": "DISCOUNT",
    "margin_fix": "MARGIN_FIX",
}

# Deterministic signal-type -> candidate registry actions, most preferred first.
SIGNAL_ACTIONS: dict[str, tuple[str, ...]] = {
    "excess_inventory": ("transfer_inventory", "discount", "review"),
    "stockout_risk": ("reorder", "restock", "review"),
    "margin_health_erosion": ("margin_fix", "pricing_increase", "review"),
    "margin_health_low": ("margin_fix", "review"),
    "procurement_health_low": ("review_supplier", "review"),
    "sales_health_decline": ("discount", "review"),
    "health_deterioration": ("review",),
    "gross_profit_at_risk": ("margin_fix", "review"),
    "revenue_at_risk_observed": ("review",),
    "data_quality_gap": ("review",),
}

# Actions that are informational only: they never mutate business state.
REVIEW_ONLY_ACTIONS = frozenset({"review", "info_only"})

URGENCY_BY_SEVERITY: dict[SignalSeverity, str] = {
    SignalSeverity.CRITICAL: "critical",
    SignalSeverity.WARNING: "medium",
    SignalSeverity.INFO: "low",
}

RISK_BY_ACTION: dict[str, str] = {
    "transfer_inventory": "medium",
    "discount": "high",
    "pricing_increase": "medium",
    "margin_fix": "medium",
    "reorder": "medium",
    "restock": "medium",
    "review": "low",
    "review_supplier": "low",
    "info_only": "low",
}

# Data-quality gate: below this, we emit only a review action.
MIN_ACTIONABLE_DATA_QUALITY = 0.4


def canonical_action_for(registry_key: str) -> str:
    """Map a registry action key to the canonical contract vocabulary."""
    if registry_key in REGISTRY_TO_CANONICAL:
        candidate = REGISTRY_TO_CANONICAL[registry_key]
        if candidate in CANONICAL_ACTION_TYPES:
            return candidate
    fallback = CANONICAL_FALLBACK.get(registry_key)
    if fallback and fallback in CANONICAL_ACTION_TYPES:
        return fallback
    # Review-style actions are canonical but not registry-backed.
    if registry_key == "review":
        return "REVIEW"
    if registry_key == "review_supplier":
        return "REVIEW_SUPPLIER"
    if registry_key == "info_only":
        return "INFO_ONLY"
    return registry_key.upper()


def _is_supported(registry_key: str) -> bool:
    """Only registry-backed or review-style actions may be recommended."""
    if registry_key in ACTION_REGISTRY:
        return True
    return registry_key in REVIEW_ONLY_ACTIONS


def _spec_or_none(registry_key: str):
    if registry_key in ACTION_REGISTRY:
        return get_action_spec(registry_key)
    return None


def _dominant_cause(causes: list[RootCause]) -> Optional[RootCause]:
    """Pick the best-supported cause for a signal (None when only UNKNOWN)."""
    if not causes:
        return None
    ranked = sorted(causes, key=lambda c: (-c.confidence, c.cause_type))
    best = ranked[0]
    if best.support_level is RootCauseSupportLevel.UNKNOWN:
        return None
    return best


def build_recommendation(
    context: BusinessContext,
    signal: Signal,
    causes: list[RootCause],
    potential: Optional[ImpactEstimate],
    expected: Optional[ImpactEstimate],
    *,
    registry_action: str,
) -> Optional[Recommendation]:
    """Build one candidate recommendation, or ``None`` if not supportable.

    Returns ``None`` when the action is not in the canonical vocabulary/registry
    so an invalid action can never become a recommendation.
    """
    if not _is_supported(registry_action):
        return None

    canonical_action = canonical_action_for(registry_action)
    if canonical_action not in CANONICAL_ACTION_TYPES and registry_action not in REVIEW_ONLY_ACTIONS:
        return None

    cause = _dominant_cause([c for c in causes if c.signal_id == signal.signal_id])

    # Data-quality gate: weak data never yields an action that changes state.
    dq = context.data_quality_score
    if dq is not None and dq < MIN_ACTIONABLE_DATA_QUALITY and registry_key_actionable(registry_action):
        registry_action = "review"
        canonical_action = "REVIEW"

    spec = _spec_or_none(registry_action)
    approval_required = True if spec is None else bool(spec.approval_required)
    if registry_action in REVIEW_ONLY_ACTIONS:
        approval_required = False

    urgency = URGENCY_BY_SEVERITY.get(signal.severity, "medium")
    risk = RISK_BY_ACTION.get(registry_action, "medium")

    # Confidence blends the signal's evidence confidence with cause support.
    cause_confidence = cause.confidence if cause else 0.0
    confidence = round(
        min(1.0, (signal.confidence * 0.5) + (cause_confidence * 0.5)), 4
    ) if cause else round(signal.confidence * 0.5, 4)

    estimated_impact = expected.amount_sar if expected is not None else None
    if estimated_impact is not None and estimated_impact <= 0:
        estimated_impact = None

    # The single authoritative scoring function.
    scored = compute_recommendation_score(
        goal_alignment=goal_alignment_for(signal, cause),
        estimated_impact_sar=estimated_impact,
        urgency=urgency,
        confidence=confidence,
        data_quality_score=(dq * 100.0) if dq is not None else None,
        strategy=strategy_context(context),
        risk=risk,
    )

    rationale_parts = [
        f"{signal.signal_type} in {signal.domain} detected by {signal.detector_name} "
        f"({signal.detector_version}).",
        f"Orbit {signal.metric}={signal.observed_value:g}; {signal.baseline_formula}.",
    ]
    if cause is not None:
        rationale_parts.append(
            f"Root cause {cause.cause_type} is {cause.support_level.value} "
            f"(confidence {cause.confidence:.2f})."
        )
    else:
        rationale_parts.append("No defensible root cause established; manual review required.")
    if potential is not None:
        rationale_parts.append(
            f"Potential impact SAR {potential.amount_sar:,.0f} (not approved, executed or verified)."
        )

    constraints = {
        "data_freshness": context.data_freshness.value,
        "data_quality_score": dq,
        "state_version": context.state_version,
        "score": scored["score"],
        "score_terms": scored["terms"],
        "requires_revalidation_on_state_change": True,
    }
    if context.active_constraints:
        constraints["owner_constraints"] = dict(context.active_constraints)

    governance_requirements: list[str] = []
    if approval_required:
        governance_requirements.append("owner_approval_required")
    if registry_key_actionable(registry_action):
        governance_requirements.append("governance_policy_evaluation")
        governance_requirements.append("loop_execution_path")
    if risk in ("high", "medium"):
        governance_requirements.append("risk_review")
    if signal.freshness.value not in ("fresh",):
        governance_requirements.append(f"data_freshness_{signal.freshness.value}_revalidation")

    evidence = sorted(set(
        list(signal.evidence_ids)
        + (list(cause.evidence_ids) if cause else [])
        + (list(potential.evidence_ids) if potential else [])
    ))

    return Recommendation(
        business_id=context.business_id,
        tenant_id=context.business_id,
        state_version=context.state_version,
        signal_ids=[signal.signal_id],
        root_cause_ids=[cause.root_cause_id] if cause else [],
        evidence_ids=evidence,
        action_type=canonical_action,
        rationale=" ".join(rationale_parts),
        potential_impact=potential,
        expected_impact=expected,
        confidence=confidence,
        urgency=urgency,
        risk=risk,
        reversibility=reversibility_for(registry_action),
        affected_resources=[signal.domain],
        constraints=constraints,
        approval_required=approval_required,
        governance_requirements=governance_requirements,
        expires_at=datetime.utcnow() + timedelta(hours=RECOMMENDATION_TTL_HOURS),
        recommendation_version=RECOMMENDATION_VERSION,
        status=RecommendationStatus.QUANTIFIED,
    )


def registry_key_actionable(registry_key: str) -> bool:
    """True when the action can change business state (needs governance)."""
    if registry_key in REVIEW_ONLY_ACTIONS:
        return False
    return registry_key in ACTION_REGISTRY


def reversibility_for(registry_key: str) -> str:
    if registry_key in REVIEW_ONLY_ACTIONS:
        return "reversible"
    spec = _spec_or_none(registry_key)
    if spec is None:
        return "reversible"
    return "reversible" if spec.can_execute else "reversible_with_review"


def goal_alignment_for(signal: Signal, cause: Optional[RootCause]) -> str:
    """Map a supported root cause to the scoring contract's goal-alignment token."""
    if cause is None:
        return "unrelated"
    profitable = {
        "SUPPLIER_COST_INCREASE",
        "SELLING_PRICE_MISMATCH",
        "EXCESSIVE_DISCOUNTING",
        "INVENTORY_CASH_TRAPPED",
        "LOW_DEMAND",
        "SLOW_STOCK_CONVERSION",
    }
    return "directly_aligned" if cause.cause_type in profitable else "indirectly_relevant"


def strategy_context(context: BusinessContext) -> dict[str, Any]:
    """Verified-outcome strategy context for scoring.

    Intelligence may *consume* verified outcomes but never creates learning
    authority, so this only reports what the Loop already verified. With no
    verified evidence the tier is ``insufficient`` and contributes 0.
    """
    verified = [
        o for o in (context.previous_outcomes or [])
        if str(o.get("status", "")).lower() == "verified"
    ]
    if not verified:
        return {
            "evidence_tier": "insufficient",
            "effectiveness": None,
            "success_rate": None,
            "attempts": 0,
        }
    successes = sum(1 for o in verified if o.get("success") is True)
    return {
        "evidence_tier": "strong" if len(verified) >= 5 else "preliminary",
        "effectiveness": round(successes / len(verified), 4),
        "success_rate": round(successes / len(verified), 4),
        "attempts": len(verified),
    }


def generate_recommendations(
    context: BusinessContext,
    signals: list[Signal],
    causes: list[RootCause],
    impacts: list[ImpactEstimate],
) -> list[Recommendation]:
    """Generate ranked candidate recommendations for a whole run."""
    from app.services.intelligence import impact as impact_engine

    potentials = impact_engine.potentials_by_signal(impacts)
    expected_map = impact_engine.expected_by_signal(impacts)

    out: list[Recommendation] = []
    for signal in signals:
        actions = SIGNAL_ACTIONS.get(signal.signal_type)
        if not actions:
            continue
        signal_causes = [c for c in causes if c.signal_id == signal.signal_id]
        for registry_action in actions:
            rec = build_recommendation(
                context,
                signal,
                signal_causes,
                potentials.get(signal.signal_id),
                expected_map.get(signal.signal_id),
                registry_action=registry_action,
            )
            if rec is not None:
                out.append(rec)

    # Deterministic ranking: authoritative score, then urgency, then action name.
    urgency_rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    out.sort(
        key=lambda r: (
            -float(r.constraints.get("score") or 0.0),
            urgency_rank.get(r.urgency, 4),
            r.action_type,
        )
    )
    return out


def is_stale(recommendation: Recommendation, context: BusinessContext) -> bool:
    """Material-state invalidation.

    A recommendation is stale when the underlying Orbit state version changed
    (i.e. a newer canonical audit exists) or it has expired. The Loop must
    refuse to execute a stale recommendation.
    """
    if recommendation.state_version != context.state_version:
        return True
    if recommendation.expires_at is not None and recommendation.expires_at < datetime.utcnow():
        return True
    return False
