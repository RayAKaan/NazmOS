"""Policy / Permission foundation (Phase 1, brief §8).

Layers a **risk classification** on top of the existing autonomy dial
(`autonomy_service.py`), producing a single disposition:

    low risk    → automatic (subject to autonomy dial + guardrails)
    medium risk → draft / owner approval
    high risk   → mandatory human approval

No LLM may execute a business action directly — every action passes through
`classify_and_disposition`, which reuses the existing guardrail logic rather than
inventing new limits. Risk classification is per-action-type and overridable per
business via the autonomy dial (configurable, brief §8).
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from app.services.autonomy_service import evaluate_action, load_policy
from app.utils.money import sar
from app.config import get_settings

_settings = get_settings()

# Base risk band per action type. Financial *impact* can escalate a band but never
# demote it below this floor. These are conservative SaaS-retail defaults, NOT
# invented financial limits — they mirror the autonomy_service DEFAULTS ceilings.
BASE_RISK: dict[str, str] = {
    "restock": "medium",            # spends money
    "pricing_increase": "medium",   # revenue-facing
    "pricing_decrease": "low",      # recoverable, reversible
    "discount": "low",
    "margin_fix": "medium",         # touches supplier/cost data
    "cash_alert": "low",            # inform-only
    "staff_schedule": "low",
    "expiry_alert": "low",
    "recovery_match": "low",        # read-only in v1
    "review": "low",
    "transfer_inventory": "low",    # internal, reversible, no external spend
}

# Financial thresholds (SAR) that escalate risk band. Configurable (§13) with the
# original 5k/20k as the conservative default. Enforced safety floor: never below
# the default, so config can only raise (never silently lower) the bar.
IMPACT_ESCALATE_MEDIUM = max(Decimal("5000"), Decimal(str(_settings.RISK_ESCALATE_MEDIUM_SAR)))
IMPACT_ESCALATE_HIGH = max(Decimal("20000"), Decimal(str(_settings.RISK_ESCALATE_HIGH_SAR)))


@dataclass
class Disposition:
    risk: str                      # low | medium | high
    decision: str                  # auto | draft | approve
    reason: str
    policy: dict[str, Any]
    autonomy_mode: Any             # AutonomyMode from autonomy_service


def classify_risk(action_type: str, estimated_impact_sar: Any = None) -> str:
    risk = BASE_RISK.get(action_type, "medium")
    if estimated_impact_sar is None:
        return risk
    try:
        impact = sar(estimated_impact_sar)
    except Exception:
        return risk
    if impact >= IMPACT_ESCALATE_HIGH:
        return "high"
    if impact >= IMPACT_ESCALATE_MEDIUM and risk == "low":
        return "medium"
    return risk


async def classify_and_disposition(
    db: AsyncSession,
    business_id: UUID | str,
    action_type: str,
    payload: dict[str, Any],
    confidence: float = 0.0,
    estimated_impact_sar: Any = None,
) -> Disposition:
    """The single gate every agent action must pass before execution."""
    risk = classify_risk(action_type, estimated_impact_sar)
    policy = await load_policy(db, business_id, action_type)
    mode = evaluate_action(action_type, payload, policy, confidence)

    if risk == "high":
        # Mandatory human approval regardless of dial.
        return Disposition("high", "approve", "high-risk action requires mandatory human approval", policy, mode)

    if mode.mode == "auto_execute" and risk == "low":
        return Disposition(risk, "auto", f"low-risk action within autonomy dial ({policy.get('dial')})", policy, mode)

    if mode.mode == "inform":
        return Disposition(risk, "approve", "inform-only dial; human must act", policy, mode)

    # draft = owner one-tap approval (web or WhatsApp).
    return Disposition(risk, "draft", "draft + owner approval required", policy, mode)
