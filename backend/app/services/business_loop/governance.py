"""Governance + Shariah boundary (Phase 3G) — deterministic policy evaluation.

Governance is independent of AI inference (MASTER_PLAN §3.4):
    * No AI output authorizes an action.
    * No recommendation is an authorization.
    * No approved action may bypass current pre-execution checks.
    * Shariah constraints come from qualified review + approved policy, never
      authored by Jev/LLM. Ambiguity is held for review (DEFERRED).

Reuse notes:
    * ``app.services.action_registry`` is the registered-action table; a
      recommendation for an unregistered action is DENIED here.
    * ``app.security.ai_policy`` capability flags gate whether a Jev advisory is
      even eligible; this module consumes a capability-allowed result, it does
      not re-derive AI policy.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.services.action_registry import ACTION_REGISTRY, get_action_spec
from app.services.business_loop.contracts import GovernanceOutcome

SHARIAH_POLICY_VERSION = "shariah-reviewed-v1"


@dataclass
class GovernanceDecision:
    """Deterministic outcome of evaluating one action candidate."""

    outcome: GovernanceOutcome
    policy_version: str
    reasons: list[str]
    recommendation_id: str
    certified_by: str = "deterministic-governance"  # never an AI
    shariah_reviewed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "outcome": self.outcome.value if hasattr(self.outcome, "value") else str(self.outcome),
            "policy_version": self.policy_version,
            "reasons": self.reasons,
            "recommendation_id": self.recommendation_id,
            "certified_by": self.certified_by,
            "shariah_reviewed": self.shariah_reviewed,
        }


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def evaluate_governance(
    *,
    recommendation_id: str,
    action_type: str,
    business_id: str,
    amount_sar: float | None = None,
    policy_version: str = SHARIAH_POLICY_VERSION,
    shariah_approved: bool = False,
    shariah_ambiguous: bool = False,
    approval_required: bool | None = None,
    required_for_action: tuple[str, ...] = (),
) -> GovernanceDecision:
    """Deterministic governance evaluation for one action candidate.

    Rule order (all deterministic):
      1. Unregistered action → DENIED.
      2. Shariah ambiguity or missing qualified review → DEFERRED / REVIEW_REQUIRED.
      3. ``required_for_action`` precondition gaps → REVIEW_REQUIRED.
      4. Action requires approval (registry or explicit) → APPROVAL_REQUIRED.
      5. Otherwise → PERMITTED.
    """
    reasons: list[str] = []

    spec = get_action_spec(action_type)
    if action_type not in ACTION_REGISTRY:
        return GovernanceDecision(
            outcome=GovernanceOutcome.DENIED,
            policy_version=policy_version,
            reasons=["unregistered_action", f"action={action_type}"],
            recommendation_id=recommendation_id,
        )

    if shariah_ambiguous:
        return GovernanceDecision(
            outcome=GovernanceOutcome.DEFERRED,
            policy_version=policy_version,
            reasons=["shariah_ambiguous_held_for_review"],
            recommendation_id=recommendation_id,
        )
    if not shariah_approved:
        return GovernanceDecision(
            outcome=GovernanceOutcome.REVIEW_REQUIRED,
            policy_version=policy_version,
            reasons=["shariah_qualified_review_missing"],
            recommendation_id=recommendation_id,
        )

    if required_for_action and any(rf not in {"tenant_verified", "policy_version_current"} for rf in required_for_action):
        reasons.append(f"precondition_missing:{','.join(required_for_action)}")
        return GovernanceDecision(
            outcome=GovernanceOutcome.REVIEW_REQUIRED,
            policy_version=policy_version,
            reasons=reasons,
            recommendation_id=recommendation_id,
        )

    needs_approval = (
        approval_required if approval_required is not None else spec.approval_required
    )
    if needs_approval:
        reasons.append(f"approval_required_for={action_type}")
        return GovernanceDecision(
            outcome=GovernanceOutcome.APPROVAL_REQUIRED,
            policy_version=policy_version,
            reasons=reasons,
            recommendation_id=recommendation_id,
            shariah_reviewed=True,
        )

    reasons.append(f"permitted_deterministic:{action_type}")
    return GovernanceDecision(
        outcome=GovernanceOutcome.PERMITTED,
        policy_version=policy_version,
        reasons=reasons,
        recommendation_id=recommendation_id,
        shariah_reviewed=True,
    )


def approve_binding(
    *,
    recommendation_id: str,
    recommendation_version: int,
    material_hash: str,
    approved_by: str,
) -> dict[str, Any]:
    """Bind an owner approval to the EXACT recommendation version + material
    parameters. A materially changed recommendation has a different hash and
    thus a different binding key — the approval never carries over."""
    binding_key = f"{recommendation_id}:v{recommendation_version}:{material_hash}"
    return {
        "binding_key": binding_key,
        "approved_by": approved_by,
        "approved_at": _now_iso(),
    }