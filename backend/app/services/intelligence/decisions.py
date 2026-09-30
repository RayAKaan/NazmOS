"""Decision candidates and the Governance handoff.

Intelligence produces ``DecisionCandidate`` objects. It does not authorize them
and it never executes them. The handoff to Governance reuses the canonical
``evaluate_governance`` so there is exactly one policy authority.

Status discipline: Intelligence may only ever set statuses up to
``APPROVAL_REQUIRED`` / ``GOVERNANCE_PENDING``. ``EXECUTED`` and ``VERIFIED`` do
not exist in the Intelligence status enum at all, so Intelligence structurally
cannot claim them.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from app.services.action_registry import ACTION_REGISTRY
from app.services.business_loop.governance import (
    GovernanceOutcome,
    evaluate_governance,
)
from app.services.intelligence.contracts import (
    AdvisoryResult,
    BusinessContext,
    DecisionCandidate,
    DecisionCandidateStatus,
    ImpactEstimate,
    Recommendation,
    RootCause,
    Signal,
)

DECISION_CONTRACT_VERSION = "decision-v1"

# Registry action key for each canonical contract action. Governance consumes
# the registry key, so the handoff must carry it.
CANONICAL_TO_REGISTRY: dict[str, str] = {
    "DISCOUNT": "discount",
    "REORDER": "reorder",
    "RESTOCK": "restock",
    "TRANSFER": "transfer_inventory",
    "MARGIN_FIX": "margin_fix",
    "PRICING_INCREASE": "pricing_increase",
    "PRICING_DECREASE": "pricing_decrease",
    "RECOVERY_MATCH": "recovery_match",
    "EXPIRY_ALERT": "expiry_alert",
}

# Review-style actions are not registry-backed; Governance would DENY them, so
# Intelligence never forwards them as executable candidates.
REVIEW_ACTIONS: frozenset[str] = frozenset({
    "REVIEW", "INFO_ONLY", "REVIEW_PRICING", "REVIEW_SUPPLIER", "GENERATE_DECISION",
})

GOVERNANCE_OUTCOME_TO_STATUS: dict[GovernanceOutcome, DecisionCandidateStatus] = {
    GovernanceOutcome.PERMITTED: DecisionCandidateStatus.VALIDATED,
    GovernanceOutcome.APPROVAL_REQUIRED: DecisionCandidateStatus.APPROVAL_REQUIRED,
    GovernanceOutcome.REVIEW_REQUIRED: DecisionCandidateStatus.APPROVAL_REQUIRED,
    GovernanceOutcome.DENIED: DecisionCandidateStatus.REJECTED,
    GovernanceOutcome.DEFERRED: DecisionCandidateStatus.GOVERNANCE_PENDING,
}


def registry_key_for(action_type: str) -> Optional[str]:
    """Registry key for a canonical action, or ``None`` for review-only actions."""
    if action_type in REVIEW_ACTIONS:
        return None
    return CANONICAL_TO_REGISTRY.get(action_type)


def build_decision_candidate(
    context: BusinessContext,
    recommendation: Recommendation,
    advisory: Optional[AdvisoryResult],
    expected: Optional[ImpactEstimate],
) -> Optional[DecisionCandidate]:
    """Build the canonical DecisionCandidate for a recommendation.

    Returns ``None`` for review-only actions: those are not executable candidates
    and must not be handed to Governance as if they were.
    """
    registry_key = registry_key_for(recommendation.action_type)
    if registry_key is None or registry_key not in ACTION_REGISTRY:
        return None

    deterministic_basis: dict[str, Any] = {
        "action_type": recommendation.action_type,
        "registry_action": registry_key,
        "score": recommendation.constraints.get("score"),
        "score_terms": recommendation.constraints.get("score_terms"),
        "urgency": recommendation.urgency,
        "risk": recommendation.risk,
        "confidence": recommendation.confidence,
        "state_version": context.state_version,
        "detector_version": recommendation.recommendation_version,
        "data_freshness": context.data_freshness.value,
    }
    if advisory is not None:
        deterministic_basis["advisory_source"] = advisory.source.value
        if advisory.alternative_action and advisory.alternative_action != advisory.suggested_action:
            deterministic_basis["advisory_dissent"] = advisory.alternative_action

    constraints = dict(recommendation.constraints)
    constraints["governance_requirements"] = list(recommendation.governance_requirements)

    return DecisionCandidate(
        business_id=context.business_id,
        tenant_id=context.business_id,
        state_version=context.state_version,
        recommendation_id=recommendation.recommendation_id,
        action_type=recommendation.action_type,
        deterministic_basis=deterministic_basis,
        advisory=advisory,
        expected_impact=expected,
        risk=_risk_token(recommendation.risk),
        urgency=_urgency_token(recommendation.urgency),
        confidence=recommendation.confidence,
        evidence_ids=list(recommendation.evidence_ids),
        constraints=constraints,
        governance_status="pending",
        approval_required=recommendation.approval_required,
        status=DecisionCandidateStatus.VALIDATED,
        created_at=datetime.utcnow(),
        expires_at=recommendation.expires_at,
    )


def _risk_token(value: Any) -> float:
    return {"low": 0.0, "medium": 0.5, "high": 1.0}.get(str(value).lower(), 0.5)


def _urgency_token(value: Any) -> float:
    return {"low": 0.25, "medium": 0.5, "high": 0.75, "critical": 1.0}.get(str(value).lower(), 0.5)


def handoff_to_governance(
    candidate: DecisionCandidate,
    *,
    shariah_approved: bool = False,
    shariah_ambiguous: bool = False,
    required_for_action: tuple[str, ...] = (),
) -> DecisionCandidate:
    """Evaluate a candidate against canonical Governance and return the outcome.

    This is the *only* place Intelligence touches policy. It records Governance's
    verdict; it never overrides it. Intelligence never advances a candidate past
    ``APPROVAL_REQUIRED``.
    """
    registry_key = str(candidate.deterministic_basis.get("registry_action") or "")
    if not registry_key:
        return candidate

    amount = None
    if candidate.expected_impact is not None:
        amount = candidate.expected_impact.amount_sar

    decision = evaluate_governance(
        recommendation_id=str(candidate.recommendation_id),
        action_type=registry_key,
        business_id=str(candidate.business_id),
        amount_sar=amount,
        shariah_approved=shariah_approved,
        shariah_ambiguous=shariah_ambiguous,
        approval_required=candidate.approval_required,
        required_for_action=required_for_action,
    )

    status = GOVERNANCE_OUTCOME_TO_STATUS.get(decision.outcome, DecisionCandidateStatus.GOVERNANCE_PENDING)
    constraints = dict(candidate.constraints)
    constraints["governance"] = {
        "outcome": decision.outcome.value,
        "reasons": list(decision.reasons),
        "policy_version": decision.policy_version,
    }
    return DecisionCandidate(
        decision_id=candidate.decision_id,
        business_id=candidate.business_id,
        tenant_id=candidate.tenant_id,
        state_version=candidate.state_version,
        recommendation_id=candidate.recommendation_id,
        action_type=candidate.action_type,
        deterministic_basis=candidate.deterministic_basis,
        advisory=candidate.advisory,
        expected_impact=candidate.expected_impact,
        risk=candidate.risk,
        urgency=candidate.urgency,
        confidence=candidate.confidence,
        evidence_ids=candidate.evidence_ids,
        constraints=constraints,
        governance_status=decision.outcome.value,
        approval_required=candidate.approval_required,
        status=status,
        created_at=candidate.created_at,
        expires_at=candidate.expires_at,
    )


def generate_decision_candidates(
    context: BusinessContext,
    recommendations: list[Recommendation],
    advisories: dict[Any, AdvisoryResult],
    impacts: list[ImpactEstimate],
    *,
    shariah_approved: bool = False,
) -> list[DecisionCandidate]:
    """Build + govern every recommendation in one bounded pass."""
    from app.services.intelligence import impact as impact_engine

    expected_map = impact_engine.expected_by_signal(impacts)
    out: list[DecisionCandidate] = []
    for rec in recommendations:
        expected = None
        for sid in rec.signal_ids:
            if sid in expected_map:
                expected = expected_map[sid]
                break
        candidate = build_decision_candidate(
            context, rec, advisories.get(rec.recommendation_id), expected
        )
        if candidate is None:
            continue
        out.append(
            handoff_to_governance(candidate, shariah_approved=shariah_approved)
        )
    return out
