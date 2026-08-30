"""V8 Structured Evidence Package Builder.

Builds the deterministic evidence package that the AI reasoning layer receives.
The AI may reason ONLY from this evidence. No inventing numbers, no inventing data.

Evidence package contains ONLY facts available at decision time.
No future information leakage. No hidden ground truth. No test labels.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any


def _float(v: Any) -> float | None:
    if v is None:
        return None
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (int, float)):
        return float(v)
    return None


@dataclass
class ItemEvidence:
    """Structured evidence for a single SKU. AI receives ONLY this."""
    sku: str
    product_name: str
    classification: str
    current_stock: float
    cost_price_sar: float
    sell_price_sar: float
    inventory_value_sar: float
    recent_velocity_per_day: float
    prior_velocity_per_day: float
    daily_velocity: float
    days_of_supply: float | None
    days_since_last_sale: int | None
    inventory_age_days: int | None
    monthly_concentrations: list[float] | None = None
    monthly_concentration_peak: float | None = None
    confirmed_inbound_qty: float = 0
    supplier_lead_time_days: int | None = None
    supplier_moq: float | None = None
    supplier_name: str | None = None
    capital_at_risk_sar: float = 0
    revenue_at_risk_sar: float = 0
    gross_profit_at_risk_sar: float = 0
    recoverable_low_sar: float = 0
    recoverable_high_sar: float = 0
    expected_recovery_sar: float | None = None
    recovery_confidence: str = "INSUFFICIENT DATA"
    candidate_actions: list[str] = field(default_factory=list)
    overstock_days: float | None = None
    stockout_days: float | None = None
    margin_pct: float | None = None
    target_margin_pct: float = 0.30
    is_strategic: bool = False
    historical_outcomes: list[dict[str, Any]] = field(default_factory=list)
    # V11 additions
    seasonal_type: str | None = None
    days_until_season: int | None = None
    days_since_season_ended: int | None = None
    historical_seasonal_multiplier: float | None = None
    supplier_reliability: str | None = None
    ghost_po_risk: bool = False
    is_promotional: bool = False
    promotion_uplift_pct: float | None = None
    normal_velocity: float | None = None
    trend: str | None = None
    demand_volatility: float | None = None
    branch_a_stock: float | None = None
    branch_b_stock: float | None = None
    branch_a_demand: float | None = None
    branch_b_demand: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}

    @property
    def stock(self) -> float:
        """Backwards-compatibility alias for current_stock."""
        return self.current_stock

    @stock.setter
    def stock(self, value: float) -> None:
        self.current_stock = value

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), default=str)


@dataclass
class BusinessContext:
    """Business-level context for AI reasoning."""
    business_id: str
    business_type: str
    total_inventory_value_sar: float
    total_capital_at_risk_sar: float
    total_recoverable_high_sar: float
    cash_budget: float | None = None
    max_discount_pct: float | None = None
    blocked_discount_products: list[str] = field(default_factory=list)
    strategic_products: list[str] = field(default_factory=list)
    blocked_transfer_routes: list[str] = field(default_factory=list)
    minimum_margin_pct: float | None = None
    previous_actions: list[dict[str, Any]] = field(default_factory=list)
    previous_outcomes: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class AuditEvidencePackage:
    """Complete evidence package for one audit. Contains only deterministic facts."""
    business: BusinessContext
    items: list[ItemEvidence]
    classification_summary: dict[str, int]
    ai_budget_remaining: int = 10
    generated_at: str = ""
    period_start: str = ""
    period_end: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "business": self.business.to_dict(),
            "items": [i.to_dict() for i in self.items],
            "classification_summary": self.classification_summary,
            "ai_budget_remaining": self.ai_budget_remaining,
            "generated_at": self.generated_at,
            "period_start": self.period_start,
            "period_end": self.period_end,
        }


def build_item_evidence(
    *,
    sku: str,
    product_name: str,
    classification: str,
    stock: Decimal,
    cost: Decimal,
    sell: Decimal,
    qty_30d: Decimal,
    qty_prior: Decimal,
    days_since_last_sale: int | None,
    inventory_age_days: int | None,
    monthly_concentrations: list[Decimal] | None = None,
    confirmed_inbound: Decimal = Decimal("0"),
    supplier_lead_time: int | None = None,
    supplier_moq: Decimal | None = None,
    supplier_name: str | None = None,
    candidate_actions: list[str] | None = None,
    is_strategic: bool = False,
    historical_outcomes: list[dict[str, Any]] | None = None,
    # V11 additions
    seasonal_type: str | None = None,
    days_until_season: int | None = None,
    days_since_season_ended: int | None = None,
    historical_seasonal_multiplier: float | None = None,
    supplier_reliability: str | None = None,
    ghost_po_risk: bool = False,
    is_promotional: bool = False,
    promotion_uplift_pct: float | None = None,
    normal_velocity: float | None = None,
    trend: str | None = None,
    demand_volatility: float | None = None,
    branch_a_stock: float | None = None,
    branch_b_stock: float | None = None,
    branch_a_demand: float | None = None,
    branch_b_demand: float | None = None,
) -> ItemEvidence:
    """Build evidence for one item from deterministic financial data."""
    inventory_value = float(stock * cost)
    daily_velocity = float(qty_30d / Decimal("30")) if qty_30d > 0 else 0.0
    days_supply = float(stock / Decimal(str(daily_velocity))) if daily_velocity > 0 and stock > 0 else None

    # Monthly concentration peak
    mc_peak = None
    mc_floats = None
    if monthly_concentrations and len(monthly_concentrations) >= 2:
        mc_floats = [float(m) for m in monthly_concentrations]
        total = sum(max(m, 0) for m in mc_floats)
        if total > 0:
            mc_peak = max(mc_floats) / total

    # Financial exposure (deterministic)
    capital_at_risk = inventory_value
    revenue_at_risk = float(stock * sell) if daily_velocity > 0 else 0.0
    gross_profit_at_risk = revenue_at_risk - inventory_value

    # Overstock / stockout
    overstock_days = days_supply if days_supply and days_supply > 60 else None
    stockout_days = days_supply if days_supply and days_supply < 7 and stock > 0 else None

    # Margin
    margin_pct = float((sell - cost) / sell) if sell > 0 else None

    return ItemEvidence(
        sku=sku,
        product_name=product_name,
        classification=classification,
        current_stock=float(stock),
        cost_price_sar=float(cost),
        sell_price_sar=float(sell),
        inventory_value_sar=round(inventory_value, 2),
        recent_velocity_per_day=round(daily_velocity, 4),
        prior_velocity_per_day=round(float(qty_prior / Decimal("30")) if qty_prior > 0 else 0.0, 4),
        daily_velocity=round(daily_velocity, 4),
        days_of_supply=round(days_supply, 1) if days_supply else None,
        days_since_last_sale=days_since_last_sale,
        inventory_age_days=inventory_age_days,
        monthly_concentrations=mc_floats,
        monthly_concentration_peak=round(mc_peak, 4) if mc_peak is not None else None,
        confirmed_inbound_qty=float(confirmed_inbound),
        supplier_lead_time_days=supplier_lead_time,
        supplier_moq=float(supplier_moq) if supplier_moq else None,
        supplier_name=supplier_name,
        capital_at_risk_sar=round(capital_at_risk, 2),
        revenue_at_risk_sar=round(revenue_at_risk, 2),
        gross_profit_at_risk_sar=round(gross_profit_at_risk, 2),
        recoverable_low_sar=0.0,
        recoverable_high_sar=round(min(inventory_value, float(stock * sell)) if stock > 0 else 0, 2),
        expected_recovery_sar=None,
        recovery_confidence="LOW",
        candidate_actions=candidate_actions or [],
        overstock_days=round(overstock_days, 1) if overstock_days else None,
        stockout_days=round(stockout_days, 1) if stockout_days else None,
        margin_pct=round(margin_pct, 4) if margin_pct is not None else None,
        target_margin_pct=0.30,
        is_strategic=is_strategic,
        historical_outcomes=historical_outcomes or [],
        # V11 additions
        seasonal_type=seasonal_type,
        days_until_season=days_until_season,
        days_since_season_ended=days_since_season_ended,
        historical_seasonal_multiplier=historical_seasonal_multiplier,
        supplier_reliability=supplier_reliability,
        ghost_po_risk=ghost_po_risk,
        is_promotional=is_promotional,
        promotion_uplift_pct=promotion_uplift_pct,
        normal_velocity=normal_velocity,
        trend=trend,
        demand_volatility=demand_volatility,
        branch_a_stock=branch_a_stock,
        branch_b_stock=branch_b_stock,
        branch_a_demand=branch_a_demand,
        branch_b_demand=branch_b_demand,
    )


def triage_items_for_ai(items: list[ItemEvidence], max_calls: int = 10) -> list[ItemEvidence]:
    """Deterministic triage: select which items benefit from AI reasoning.

    NOT every item needs AI. Only ambiguous/high-value cases.

    Triage score = ambiguity_score * financial_exposure * action_impact

    Returns top-N items sorted by triage score, descending.

    V11 additions: AI_CALL_REASONS for audit trail.
    """
    scored: list[tuple[float, ItemEvidence, str]] = []

    for item in items:
        # Ambiguity score (0-1)
        ambiguity = 0.0
        triage_reason = "default"

        # V11: Seasonal conflict — AI should challenge deterministic
        if item.classification == "SEASONAL":
            ambiguity += 0.8
            triage_reason = "SEASONAL_CONFLICT"

        # V11: Promotion distortion — sales spike from promotion, not organic
        if item.is_promotional and item.promotion_uplift_pct and item.promotion_uplift_pct > 30:
            ambiguity += 0.7
            triage_reason = "PROMOTION_DISTORTION"

        # V11: Supplier risk — unreliable supplier affects decision
        if item.supplier_reliability == "unreliable":
            ambiguity += 0.6
            triage_reason = "SUPPLIER_RISK"

        # V11: Branch transfer opportunity
        if (item.branch_a_stock is not None and item.branch_b_stock is not None and
            item.branch_a_demand is not None and item.branch_b_demand is not None):
            if item.branch_a_stock > 10 and item.branch_b_demand > 0 and item.branch_b_stock == 0:
                ambiguity += 0.7
                triage_reason = "BRANCH_TRANSFER"

        # V11: Margin erosion
        if item.margin_pct is not None and item.margin_pct < 0.15 and item.current_stock > 0:
            ambiguity += 0.5
            triage_reason = "MARGIN_EROSION"

        # V11: Growth vs overstock ambiguity
        if item.trend == "accelerating" and item.overstock_days:
            ambiguity += 0.6
            triage_reason = "GROWTH_VS_OVERSTOCK"

        # V11: Ghost PO risk
        if item.ghost_po_risk:
            ambiguity += 0.8
            triage_reason = "GHOST_PO_RISK"

        # V11: High-value ambiguity
        if item.inventory_value_sar > 5000 and item.classification in ("UNKNOWN", "HEALTHY"):
            ambiguity += 0.5
            triage_reason = "HIGH_VALUE_AMBIGUITY"

        # V11: Zero stock + demand (was MANUAL_REVIEW, now REORDER)
        if item.current_stock == 0 and item.daily_velocity > 0:
            ambiguity += 0.4
            triage_reason = "ZERO_STOCK_DEMAND"

        # V11: Strategic product with special constraints
        if item.is_strategic:
            ambiguity += 0.3
            triage_reason = "STRATEGIC_CONTEXT"

        # Items with low but non-zero velocity are ambiguous (slow vs seasonal vs dead)
        if item.classification in ("UNKNOWN", "HEALTHY") and 0 < item.daily_velocity < 0.5:
            ambiguity += 0.5
            if triage_reason == "default":
                triage_reason = "HIGH_VALUE_AMBIGUITY"

        # Items with declining velocity are ambiguous
        if item.prior_velocity_per_day > 0 and item.recent_velocity_per_day > 0:
            decline = 1.0 - (item.recent_velocity_per_day / max(item.prior_velocity_per_day, 0.01))
            if 0.3 < decline < 0.8:
                ambiguity += 0.4
                if triage_reason == "default":
                    triage_reason = "GROWTH_VS_OVERSTOCK"

        # Monthly concentration without clear seasonal label
        if item.monthly_concentration_peak and item.monthly_concentration_peak > 0.5 and item.classification != "SEASONAL":
            ambiguity += 0.6
            if triage_reason == "default":
                triage_reason = "SEASONAL_CONFLICT"

        # Overstock is ambiguous (discount vs transfer vs recovery match)
        if item.overstock_days:
            ambiguity += 0.5
            if triage_reason == "default":
                triage_reason = "GROWTH_VS_OVERSTOCK"

        # Clear deterministic cases get low ambiguity
        if item.classification == "DEAD":
            ambiguity = max(ambiguity, 0.1)
            triage_reason = "default"
        if item.classification == "FAST" and item.days_of_supply and item.days_of_supply < 30:
            ambiguity = max(ambiguity, 0.05)
            triage_reason = "default"

        # Financial exposure score (0-1, normalized)
        exposure = min(1.0, item.inventory_value_sar / 10000.0)

        # Action impact score (0-1)
        impact = 0.0
        if item.overstock_days and item.overstock_days > 90:
            impact += 0.8
        if item.stockout_days:
            impact += 0.7
        if item.margin_pct is not None and item.margin_pct < 0.15:
            impact += 0.6
        if item.recoverable_high_sar > 500:
            impact += 0.5
        if item.candidate_actions and len(item.candidate_actions) > 1:
            impact += 0.3

        # Combined triage score
        triage_score = ambiguity * exposure * max(impact, 0.1)

        scored.append((triage_score, item, triage_reason))

    # Sort by score descending, return top-N
    scored.sort(key=lambda x: x[0], reverse=True)
    return [item for _, item, _ in scored[:max_calls]]
