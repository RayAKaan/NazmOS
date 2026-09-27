"""Recommendation lifecycle (Phase 3E) — versioned, evidence-backed, governed.

A Recommendation binds:
    * opportunity (id) + business-state version + evidence references
    * deterministic impact (POTENTIAL/EXPECTED) + impact formula version
    * registered action type + action contract version
    * Jev advisory reference + actual provider identity + validation result
    * policy version + approval requirements + expiry/revalidation
    * lifecycle status (state machine with valid transitions only)

Reuse notes:
    * Jev advisory is obtained through the existing canonical gateway path
      (``app.services.ai_gateway.systemone_reason`` / ``canonical_decision``)
      — this module records the reference + provider attribution; it does not
      re-implement AI.
    * The lifecycle mirrors the findings convention in ``finding_service.py``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from app.services.business_loop.contracts import (
    RecommendationStatus,
    RECOMMENDATION_TRANSITIONS,
)


def _now_iso() -> str | None:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Recommendation:
    """Versioned recommendation object (immutable after promote)."""

    recommendation_id: str
    version: int
    opportunity_id: str
    business_id: str
    tenant_id: str
    state_version: str
    evidence_ids: tuple[str, ...]
    action_type: str
    potential_impact_sar: float
    expected_impact_sar: float | None
    impact_formula_version: str
    action_contract_version: str
    provider: str                  # actual provider identity (advisory attribution)
    advisory_validated: bool
    status: RecommendationStatus = RecommendationStatus.DETECTED
    policy_version: str = "pending"
    approval_requirements: list[str] = field(default_factory=list)
    expires_at: str | None = None
    material_hash: str = ""

    def __post_init__(self) -> None:
        if not self.material_hash:
            self.material_hash = self.compute_material_hash()

    def compute_material_hash(self) -> str:
        """Hash over the exact recommendation version + material parameters."""
        import hashlib

        composite = (
            f"{self.recommendation_id}:{self.version}:{self.opportunity_id}:"
            f"{self.action_type}:{self.potential_impact_sar}:{self.expected_impact_sar}"
        )
        return hashlib.sha256(composite.encode()).hexdigest()[:24]

    def is_stale(self, now: str | None = None) -> bool:
        """Stale when expired or superseded."""
        if self.status in (RecommendationStatus.EXPIRED, RecommendationStatus.SUPERSEDED):
            return True
        if not self.expires_at:
            return False
        try:
            expires = datetime.fromisoformat(self.expires_at)
        except (TypeError, ValueError):
            return False
        return _utcnow() > expires

    def describe(self) -> dict[str, Any]:
        return {
            "recommendation_id": self.recommendation_id,
            "version": self.version,
            "opportunity_id": self.opportunity_id,
            "state_version": self.state_version,
            "evidence_ids": list(self.evidence_ids),
            "action_type": self.action_type,
            "provider": self.provider,
            "advisory_validated": self.advisory_validated,
            "status": self.status.value if hasattr(self.status, "value") else str(self.status),
            "policy_version": self.policy_version,
            "material_hash": self.material_hash,
            "expires_at": self.expires_at,
            "potential_impact_sar": self.potential_impact_sar,
            "expected_impact_sar": self.expected_impact_sar,
        }


class RecommendationLifecycle:
    """State machine over a recommendation with version-safe transitions."""

    @staticmethod
    def transition(recommendation: Recommendation, to: RecommendationStatus) -> Recommendation:
        """Promote to ``to`` only if the transition is in the allowed map.

        Returns a NEW recommendation (version bumped on reroute) so a materially
        changed recommendation can never silently reuse a prior approval.
        """
        current = recommendation.status
        allowed = RECOMMENDATION_TRANSITIONS.get(current)
        if allowed is None or to not in allowed:
            raise ValueError(f"invalid_transition:{current}->{to}")

        new = Recommendation(
            recommendation_id=recommendation.recommendation_id,
            version=recommendation.version,
            opportunity_id=recommendation.opportunity_id,
            business_id=recommendation.business_id,
            tenant_id=recommendation.tenant_id,
            state_version=recommendation.state_version,
            evidence_ids=recommendation.evidence_ids,
            action_type=recommendation.action_type,
            potential_impact_sar=recommendation.potential_impact_sar,
            expected_impact_sar=recommendation.expected_impact_sar,
            impact_formula_version=recommendation.impact_formula_version,
            action_contract_version=recommendation.action_contract_version,
            provider=recommendation.provider,
            advisory_validated=recommendation.advisory_validated,
            status=to,
            policy_version=recommendation.policy_version,
            approval_requirements=list(recommendation.approval_requirements),
            expires_at=recommendation.expires_at,
            material_hash=recommendation.material_hash,
        )
        return new

    @staticmethod
    def supersede(recommendation: Recommendation) -> Recommendation:
        """Mark superseded: prior versions must never inherit auto-approval."""
        return RecommendationLifecycle.transition(recommendation, RecommendationStatus.SUPERSEDED)

    @staticmethod
    def bump_version(recommendation: Recommendation) -> Recommendation:
        """Create the next version with a fresh material hash (requires revalidating)."""
        return Recommendation(
            recommendation_id=recommendation.recommendation_id,
            version=recommendation.version + 1,
            opportunity_id=recommendation.opportunity_id,
            business_id=recommendation.business_id,
            tenant_id=recommendation.tenant_id,
            state_version=recommendation.state_version,
            evidence_ids=recommendation.evidence_ids,
            action_type=recommendation.action_type,
            potential_impact_sar=recommendation.potential_impact_sar,
            expected_impact_sar=recommendation.expected_impact_sar,
            impact_formula_version=recommendation.impact_formula_version,
            action_contract_version=recommendation.action_contract_version,
            provider=recommendation.provider,
            advisory_validated=False,  # a changed recommendation must be revalidated
            status=RecommendationStatus.DETECTED,
            policy_version="pending",
            approval_requirements=list(recommendation.approval_requirements),
            expires_at=recommendation.expires_at,
            material_hash="",  # recomputed
        )


def make_recommendation(
    *,
    recommendation_id: str,
    opportunity: Any,
    business_id: str,
    tenant_id: str,
    state_version: str,
    action_type: str,
    provider: str,
    advisory_validated: bool,
    expected_impact_sar: float | None = None,
    impact_formula_version: str = "audit-core-v1",
    action_contract_version: str = "1.0.0",
    validity_hours: int = 24,
) -> Recommendation:
    """Construct the first version (DETECTED) of a recommendation."""
    expires_at = (_utcnow() + timedelta(hours=validity_hours)).isoformat(timespec="seconds")
    return Recommendation(
        recommendation_id=recommendation_id,
        version=1,
        opportunity_id=opportunity.opportunity_id,
        business_id=business_id,
        tenant_id=tenant_id,
        state_version=state_version,
        evidence_ids=opportunity.evidence_ids,
        action_type=action_type,
        potential_impact_sar=float(opportunity.potential_impact_sar),
        expected_impact_sar=expected_impact_sar,
        impact_formula_version=impact_formula_version,
        action_contract_version=action_contract_version,
        provider=provider,
        advisory_validated=advisory_validated,
        status=RecommendationStatus.DETECTED,
        expires_at=expires_at,
    )