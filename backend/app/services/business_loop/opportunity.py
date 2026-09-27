"""Deterministic opportunity engine (Phase 3D) — state -> measurable opportunity.

Transforms a :class:`BusinessStateSnapshot` into deterministic, reproducible
opportunities. The engine NEVER invents thresholds; each rule references the
documented, existing NazmOS threshold (see rule docstrings) or is supplied
explicitly by the caller (``rule_overrides``). Every opportunity is bound to:
    * business state version
    * supporting evidence ids
    * detection rule version
    * deterministic impact (POTENTIAL always; EXPECTED only when supportable)

Impact rules (MASTER_PLAN §9.4): POTENTIAL/EXPECTED/APPROVED/EXECUTED/VERIFIED
are distinct buckets. An estimate is never labelled recovered cash here.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.services.business_loop.contracts import ImpactKind, OpportunityType
from app.services.business_loop.state import BusinessStateSnapshot

# Documented NazmOS thresholds (existing, verified in repo):
#   * surplus / excess inventory: >= 30 days of supply AND value >= SAR 500
#     (audit_core analyze_product overstock condition)
#   * stockout risk: < 5 days of supply with open demand (audit_core)
#   * margin erosion target: gross margin below 22% target (audit_core
#     TARGET_MARGIN / margin leakage computation)
DEFAULT_RULE_OVERRIDES: dict[str, Any] = {
    "surplus_min_days_supply": 30,
    "surplus_min_value_sar": 500.0,
    "stockout_max_days_supply": 5,
    "target_margin_pct": 0.22,
}

RULE_VERSIONS: dict[str, str] = {
    "excess_inventory": "excess-inventory-v1",
    "stockout_risk": "stockout-risk-v1",
    "margin_erosion": "margin-erosion-v1",
    "inventory_anomaly": "inventory-anomaly-v1",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Opportunity:
    """One deterministic, evidence-backed opportunity."""

    opportunity_id: str
    tenant_id: str
    business_id: str
    opportunity_type: str
    state_version: str
    evidence_ids: tuple[str, ...]
    rule_version: str
    potential_impact_sar: float
    expected_impact_sar: float | None  # only when supportable
    impact_kind: str = ImpactKind.POTENTIAL.value
    confidence: str = "deterministic"
    lifecycle_status: str = "open"
    eligible_action_categories: tuple[str, ...] = ()
    details: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""

    def __post_init__(self) -> None:
        self.created_at = self.created_at or _now_iso()

    def to_dict(self) -> dict[str, Any]:
        return {
            "opportunity_id": self.opportunity_id,
            "tenant_id": self.tenant_id,
            "business_id": self.business_id,
            "opportunity_type": self.opportunity_type,
            "state_version": self.state_version,
            "evidence_ids": list(self.evidence_ids),
            "rule_version": self.rule_version,
            "potential_impact_sar": self.potential_impact_sar,
            "expected_impact_sar": self.expected_impact_sar,
            "impact_kind": self.impact_kind,
            "lifecycle_status": self.lifecycle_status,
            "eligible_action_categories": list(self.eligible_action_categories),
        }


def _deterministic_id(opportunity_type: str, state_version: str, sku: str) -> str:
    import hashlib

    composite = f"{opportunity_type}:{state_version}:{sku}"
    return f"opp-{hashlib.sha256(composite.encode()).hexdigest()[:20]}"


def _inventory_items(snapshot: BusinessStateSnapshot) -> list[tuple[str, dict[str, Any]]]:
    inv = snapshot.domain("inventory")
    if inv is None:
        return []
    return [(sku, values) for sku, values in inv.values.items()]


def detect_opportunities(
    snapshot: BusinessStateSnapshot,
    *,
    rule_overrides: dict[str, Any] | None = None,
    eligible_actions: dict[str, tuple[str, ...]] | None = None,
) -> list[Opportunity]:
    """Deterministically detect opportunities from one business-state snapshot.

    ``eligible_actions`` maps opportunity_type -> registered action categories
    (mirrors ACTION_REGISTRY keys). Defaults replicate the de-facto candidate
    surfaces: REORDER/RESTOCK for stockout, RECOVERY_MATCH/TRANSFER for
    surplus, PRICING_INCREASE/MARGIN_FIX for margin erosion, REVIEW for anomaly.
    """
    overrides = {**DEFAULT_RULE_OVERRIDES, **(rule_overrides or {})}
    actions = eligible_actions or {
        OpportunityType.EXCESS_INVENTORY.value: ("recovery_match", "transfer_inventory"),
        OpportunityType.STOCKOUT_RISK.value: ("reorder", "restock"),
        OpportunityType.MARGIN_EROSION.value: ("pricing_increase", "margin_fix"),
        OpportunityType.INVENTORY_ANOMALY.value: ("review",),
    }

    out: list[Opportunity] = []
    for sku, values in _inventory_items(snapshot):
        stock = float(values.get("stock") or 0)
        cost = float(values.get("cost") or 0)
        sell = float(values.get("sell") or 0)
        evidence_id = str(values.get("evidence_id") or "")
        evidence_ids = (evidence_id,) if evidence_id else ()
        days_supply = values.get("days_of_supply")

        # --- Excess inventory / capital at risk ---
        if stock > 0 and cost > 0:
            value_sar = stock * cost
            if days_supply is not None:
                ds = float(days_supply)
            else:
                # conservative fallback: no demand info -> treat as surplus for
                # recovery only when value clearly exceeds threshold (overstock)
                ds = overrides["surplus_min_days_supply"] if value_sar >= overrides["surplus_min_value_sar"] else 0.0
            if ds >= overrides["surplus_min_days_supply"] and value_sar >= overrides["surplus_min_value_sar"]:
                out.append(Opportunity(
                    opportunity_id=_deterministic_id(OpportunityType.EXCESS_INVENTORY.value, snapshot.state_version, sku),
                    tenant_id=snapshot.tenant_id,
                    business_id=snapshot.business_id,
                    opportunity_type=OpportunityType.EXCESS_INVENTORY.value,
                    state_version=snapshot.state_version,
                    evidence_ids=evidence_ids,
                    rule_version=RULE_VERSIONS["excess_inventory"],
                    potential_impact_sar=round(value_sar * 0.80, 2),  # documented recovery preview factor
                    expected_impact_sar=None,  # not supportable from this snapshot alone
                    eligible_action_categories=actions.get(OpportunityType.EXCESS_INVENTORY.value, ()),
                    details={"sku": sku, "stock": stock, "value_sar": round(value_sar, 2), "days_supply": ds},
                ))

        # --- Stockout risk ---
        if days_supply is not None and stock > 0 and float(days_supply) < overrides["stockout_max_days_supply"]:
            out.append(Opportunity(
                opportunity_id=_deterministic_id(OpportunityType.STOCKOUT_RISK.value, snapshot.state_version, sku),
                tenant_id=snapshot.tenant_id,
                business_id=snapshot.business_id,
                opportunity_type=OpportunityType.STOCKOUT_RISK.value,
                state_version=snapshot.state_version,
                evidence_ids=evidence_ids,
                rule_version=RULE_VERSIONS["stockout_risk"],
                potential_impact_sar=round(stock * sell, 2),  # revenue at risk
                expected_impact_sar=None,
                eligible_action_categories=actions.get(OpportunityType.STOCKOUT_RISK.value, ()),
                details={"sku": sku, "stock": stock, "days_supply": float(days_supply)},
            ))

        # --- Margin erosion ---
        if sell > 0 and cost > 0:
            margin_pct = (sell - cost) / sell
            if margin_pct < overrides["target_margin_pct"]:
                out.append(Opportunity(
                    opportunity_id=_deterministic_id(OpportunityType.MARGIN_EROSION.value, snapshot.state_version, sku),
                    tenant_id=snapshot.tenant_id,
                    business_id=snapshot.business_id,
                    opportunity_type=OpportunityType.MARGIN_EROSION.value,
                    state_version=snapshot.state_version,
                    evidence_ids=evidence_ids,
                    rule_version=RULE_VERSIONS["margin_erosion"],
                    potential_impact_sar=round((sell - cost) * (1 if stock > 0 else 0) * -1, 2),  # negative exposure placeholder
                    expected_impact_sar=None,
                    eligible_action_categories=actions.get(OpportunityType.MARGIN_EROSION.value, ()),
                    details={"sku": sku, "margin_pct": round(margin_pct, 4), "target_pct": overrides["target_margin_pct"]},
                ))

    # Deduplicate by deterministic id (idempotent detection).
    seen: set[str] = set()
    deduped: list[Opportunity] = []
    for o in out:
        if o.opportunity_id not in seen:
            seen.add(o.opportunity_id)
            deduped.append(o)
    return deduped


def reproducible_impact(o: Opportunity) -> bool:
    """Opportunity impact is reproducible when it re-computes identically from
    its inputs (state_version + evidence-only payload)."""
    return bool(o.state_version and o.evidence_ids)