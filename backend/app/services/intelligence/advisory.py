"""Bounded Jev advisory for the Intelligence layer.

Jev is advisory. This module is the *only* place the Intelligence layer talks to
the AI gateway, and it routes through the existing canonical controller so the
invariants already enforced there apply unchanged:

- the deterministic recommendation is always authoritative;
- the capsule is built by the privacy firewall (opaque refs + banded signals);
- out-of-contract suggestions are discarded, never coerced;
- any failure (policy, budget, transport, parse) yields an explicit
  ``deterministic_only`` / ``fallback`` source — never mislabelled as Jev.

Jev may contribute confidence, an alternative, a challenge and rationale. It may
never authorize, execute, mutate state, bypass governance or invent evidence.
"""
from __future__ import annotations

import time
from typing import Any, Optional

from app.services.canonical_controller import (
    CanonicalControllerError,
    canonical_decision,
)
from app.orchestration.contracts import CANONICAL_ACTION_TYPES
from app.services.intelligence.contracts import (
    AdvisoryResult,
    AdvisorySource,
    BusinessContext,
    ImpactEstimate,
    Recommendation,
)

ADVISORY_CONTRACT_VERSION = "advisory-v1"

ADVISORY_CAPABILITY = "intelligence.recommendation_advisory"

# Deterministic labels → the advisory decision vocabulary Jev may suggest.
# Reusing the privacy firewall's mapping keeps the capsule and the deterministic
# decision on one vocabulary instead of two.
DETERMINISTIC_LABEL_TO_DECISION: dict[str, str] = {
    "DISCOUNT": "DISCOUNT",
    "REORDER": "REORDER",
    "RESTOCK": "REORDER",
    "TRANSFER": "TRANSFER",
    "MARGIN_FIX": "PRICE_CHANGE",
    "PRICING_INCREASE": "PRICE_CHANGE",
    "PRICING_DECREASE": "PRICE_CHANGE",
    "RECOVERY_MATCH": "RECOVERY_MATCH",
    "REVIEW": "MANUAL_REVIEW",
    "INFO_ONLY": "DO_NOTHING",
    "REVIEW_SUPPLIER": "MANUAL_REVIEW",
}

ADVISORY_DECISION_CONTRACT: frozenset[str] = frozenset(
    {"DO_NOTHING", "REORDER", "TRANSFER", "DISCOUNT", "PRICE_CHANGE", "RECOVERY_MATCH", "MANUAL_REVIEW"}
)


def deterministic_only(
    reason: str,
    *,
    risk_flags: Optional[list[str]] = None,
) -> AdvisoryResult:
    """The explicit no-advisory result. Never labelled as Jev."""
    flags = list(risk_flags or [])
    if reason and reason not in flags:
        flags.append(reason)
    return AdvisoryResult(
        source=AdvisorySource.DETERMINISTIC_ONLY,
        confidence=0.0,
        reasoning="Deterministic recommendation retained; no advisory was consulted.",
        suggested_action=None,
        alternative_action=None,
        challenge=False,
        risk_flags=flags,
        evidence_ids=[],
        latency_ms=0.0,
        jev_consulted=False,
    )


def _capsule_payload(
    context: BusinessContext,
    recommendation: Recommendation,
    potential: Optional[ImpactEstimate],
) -> dict[str, Any]:
    """Build the *banded* payload the privacy firewall turns into a capsule.

    Only derived, non-identifying signals are supplied. No business id, tenant
    id, product/SKU names or exact SAR values are included here — the firewall
    bands whatever arrives, and we keep the payload minimal to begin with.
    """
    return {
        "items": [
            {
                "classification": recommendation.affected_resources[0]
                if recommendation.affected_resources
                else "business",
                "current_stock": None,
                "days_of_supply": None,
                "trend": recommendation.urgency,
                "margin_pct": None,
                "candidate_actions": [recommendation.action_type],
            }
        ],
        "business": {
            "business_type": context.business_type,
            "branch_count": None,
            # Capital is supplied only as a band, never an exact figure.
            "total_capital_at_risk_sar": _band(potential.amount_sar if potential else None),
        },
        "forecast_signals": {
            "deterministic": {
                "decision": recommendation.action_type,
                "confidence": recommendation.confidence,
            }
        },
    }


def _band(value: Optional[float]) -> Optional[float]:
    """Return a coarse band representative for a SAR amount.

    The privacy firewall performs the authoritative banding of the capsule; this
    pre-banding simply avoids handing it an exact figure to begin with.
    """
    if value is None:
        return None
    if value < 1_000:
        return 500.0
    if value < 10_000:
        return 5_000.0
    if value < 50_000:
        return 25_000.0
    if value < 100_000:
        return 75_000.0
    return 150_000.0


async def advisory_for_recommendation(
    context: BusinessContext,
    recommendation: Recommendation,
    *,
    potential: Optional[ImpactEstimate] = None,
    enabled: bool = True,
    client: Any | None = None,
) -> AdvisoryResult:
    """Obtain a bounded advisory for one deterministic recommendation.

    Failure isolation: any exception is contained and reported as an explicit
    deterministic-only advisory. Intelligence continues to operate.
    """
    if not enabled:
        return deterministic_only("advisory_disabled")

    deterministic_label = recommendation.action_type
    deterministic_decision = DETERMINISTIC_LABEL_TO_DECISION.get(
        deterministic_label, "MANUAL_REVIEW"
    )
    if deterministic_decision not in ADVISORY_DECISION_CONTRACT:
        deterministic_decision = "MANUAL_REVIEW"

    payload = _capsule_payload(context, recommendation, potential)
    question = (
        "Which advisory interpretation of this deterministic business signal is "
        "safest, and what alternative should the owner consider?"
    )

    start = time.monotonic()
    try:
        result = await canonical_decision(
            payload=payload,
            deterministic_decision=deterministic_decision,
            capability=ADVISORY_CAPABILITY,
            purpose="advisory interpretation of a deterministic intelligence recommendation",
            question=question,
            contract=ADVISORY_DECISION_CONTRACT,
            client=client,
        )
    except CanonicalControllerError as exc:
        return deterministic_only(f"advisory_contract_violation:{exc}")
    except Exception as exc:  # defensive: advisory must never break the run
        return deterministic_only(f"advisory_failed:{type(exc).__name__}")
    latency = (time.monotonic() - start) * 1000.0

    source = str(result.get("source") or "fallback")
    jev_consulted = bool(result.get("jev_consulted"))
    alternative = result.get("alternative_decision")
    # The controller already validated the alternative against the contract and
    # discarded out-of-contract values (risk flag JEV_OUT_OF_CONTRACT). We only
    # surface what survived validation.
    if alternative and alternative not in ADVISORY_DECISION_CONTRACT:
        alternative = None

    risk_flags = list(result.get("risk_flags") or [])
    dissent = bool(
        alternative and alternative != deterministic_decision
    )
    if dissent and "JEV_DISSENT" not in risk_flags:
        risk_flags.append("JEV_DISSENT")

    if source == "jev":
        advisory_source = AdvisorySource.JEV
    else:
        # Explicitly NOT jev.
        advisory_source = AdvisorySource.DETERMINISTIC_ONLY

    confidence = result.get("confidence") or 0.0
    try:
        confidence = float(confidence)
    except (TypeError, ValueError):
        confidence = 0.0
    # Jev confidence must never inflate deterministic evidence quality, so it is
    # reported as advisory confidence and not merged into the recommendation's.
    if not jev_consulted:
        confidence = 0.0

    return AdvisoryResult(
        source=advisory_source,
        confidence=round(confidence, 4),
        reasoning=str(result.get("reasoning") or ""),
        # The deterministic decision always wins; the advisory never suggests
        # something that replaces it.
        suggested_action=deterministic_decision,
        alternative_action=alternative,
        challenge=bool(result.get("challenge")),
        risk_flags=risk_flags,
        evidence_ids=list(result.get("evidence_ids") or []),
        latency_ms=round(latency, 2),
        jev_consulted=jev_consulted,
    )


async def advisory_for_recommendations(
    context: BusinessContext,
    recommendations: list[Recommendation],
    *,
    potentials: Optional[dict[Any, ImpactEstimate]] = None,
    enabled: bool = True,
    max_consultations: int = 3,
    client: Any | None = None,
) -> dict[Any, AdvisoryResult]:
    """Advisory for the top-N recommendations only (bounded AI budget)."""
    out: dict[Any, AdvisoryResult] = {}
    for rec in recommendations[:max_consultations]:
        potential = None
        if potentials:
            for sid in rec.signal_ids:
                if sid in potentials:
                    potential = potentials[sid]
                    break
        out[rec.recommendation_id] = await advisory_for_recommendation(
            context,
            rec,
            potential=potential,
            enabled=enabled,
            client=client,
        )
    for rec in recommendations[max_consultations:]:
        out[rec.recommendation_id] = deterministic_only("advisory_budget_bounded")
    return out
