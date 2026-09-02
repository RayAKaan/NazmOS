"""Privacy firewall: builds signed ReasoningCapsules from trusted evidence.

This is the enforcement point of the data-classification policy. Exact
identifiers (SKU, product/supplier names, business/tenant ids) and exact
financial values (SAR amounts, stock counts, percentages, budgets) never enter
a capsule. Only banded, derived signals and the deterministic engine's candidate
decisions do. The mapping from trusted object -> opaque ref is a per-request
object in the trusted zone; it is never persisted or sent to the AI.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Mapping

from app.security.capsule import (
    CapsuleBusiness,
    CapsuleConstraints,
    CapsuleItem,
    CapsuleSigner,
    ReasoningCapsule,
)
from app.services.evidence_package import BusinessContext, ItemEvidence

if TYPE_CHECKING:
    from app.services.business_context import StructuredContext

# Deterministic action label -> decision enum used across the AI contracts.
ACTION_TO_DECISION: dict[str, str] = {
    "restock": "REORDER",
    "reorder": "REORDER",
    "purchase": "REORDER",
    "discount": "DISCOUNT",
    "transfer": "TRANSFER",
    "do_nothing": "DO_NOTHING",
    "none": "DO_NOTHING",
    "price_change": "PRICE_CHANGE",
    "price_increase": "PRICE_CHANGE",
    "price_decrease": "PRICE_CHANGE",
    "raise_price": "PRICE_CHANGE",
    "lower_price": "PRICE_CHANGE",
    "recovery_match": "RECOVERY_MATCH",
    "return_to_supplier": "RECOVERY_MATCH",
    "manual_review": "MANUAL_REVIEW",
    "manual_intervention": "MANUAL_REVIEW",
    "write_off": "MANUAL_REVIEW",
}

DECISION_HINTS = ("DO_NOTHING", "REORDER", "TRANSFER", "DISCOUNT", "PRICE_CHANGE",
                  "RECOVERY_MATCH", "MANUAL_REVIEW")


def _as_decision(action: str) -> str:
    action = action.strip().lower().replace("-", "_")
    if action in ACTION_TO_DECISION:
        return ACTION_TO_DECISION[action]
    candidate = action.upper().replace("_", "-")
    if candidate in DECISION_HINTS or candidate.replace("-", "_") in DECISION_HINTS:
        return candidate.replace("-", "_")
    return "MANUAL_REVIEW"


def _band_stock(qty: float | None) -> str | None:
    if qty is None:
        return None
    if qty <= 0:
        return "0"
    if qty <= 9:
        return "1-9"
    if qty <= 49:
        return "10-49"
    if qty <= 199:
        return "50-199"
    if qty <= 499:
        return "200-499"
    return "500+"


def _band_velocity(v: float | None) -> str | None:
    if v is None:
        return None
    if v <= 0:
        return "NONE"
    if v < 0.5:
        return "LOW"
    if v < 5:
        return "MEDIUM"
    return "HIGH"


def _band_days_of_supply(dos: float | None) -> str | None:
    if dos is None:
        return None
    if dos < 7:
        return "CRITICAL"
    if dos <= 30:
        return "LOW"
    if dos <= 60:
        return "ADEQUATE"
    return "OVER"


def _band_inventory_age(days: int | None) -> str | None:
    if days is None:
        return None
    if days < 90:
        return "FRESH"
    if days <= 180:
        return "AGING"
    return "OLD"


def _band_last_sale(days: int | None, velocity: str | None) -> str | None:
    if velocity == "NONE":
        return "NONE"
    if days is None:
        return None
    if days <= 1:
        return "RECENT"
    if days <= 7:
        return "WEEK"
    if days <= 31:
        return "MONTH"
    return "NONE"


def _band_margin(pct: float | None) -> str | None:
    if pct is None:
        return None
    if pct < 0.15:
        return "LOW"
    if pct <= 0.40:
        return "MEDIUM"
    return "HIGH"


def _band_concentration(peak: float | None) -> str | None:
    if peak is None:
        return None
    if peak >= 0.5:
        return "HIGH"
    if peak >= 0.3:
        return "MEDIUM"
    return "LOW"


def _band_reliability(reliability: str | None) -> str | None:
    if reliability is None:
        return None
    r = reliability.strip().lower()
    if r in ("reliable", "high", "good", "strong"):
        return "HIGH"
    if r in ("unreliable", "low", "poor", "weak", "risky"):
        return "LOW"
    return "MEDIUM"


def _band_lead_time(days: int | None) -> str | None:
    if days is None:
        return None
    if days <= 7:
        return "SHORT"
    if days <= 21:
        return "MEDIUM"
    return "LONG"


def _band_inbound(qty: float | None) -> str:
    if not qty or qty <= 0:
        return "NONE"
    if qty <= 50:
        return "LOW"
    if qty <= 200:
        return "MEDIUM"
    return "HIGH"


def _band_volatility(v: float | None) -> str | None:
    if v is None:
        return None
    if v < 0.2:
        return "LOW"
    if v <= 0.5:
        return "MEDIUM"
    return "HIGH"


def _band_capital(sar: float | None) -> str | None:
    if sar is None:
        return None
    if sar < 10_000:
        return "LOW"
    if sar < 100_000:
        return "MEDIUM"
    return "HIGH"


def _band_cash(sar: float | None) -> str | None:
    if sar is None:
        return None
    if sar < 10_000:
        return "LOW"
    if sar < 50_000:
        return "MEDIUM"
    return "HIGH"


def _band_max_discount(pct: float | None) -> str | None:
    if pct is None:
        return None
    if pct <= 15:
        return "conservative"
    if pct <= 35:
        return "moderate"
    return "aggressive"


def _candidate_decisions_from_actions(candidate_actions: list[str] | None) -> list[str]:
    decisions: list[str] = []
    for action in candidate_actions or []:
        d = _as_decision(action)
        if d not in decisions:
            decisions.append(d)
    return decisions


def item_evidence_to_capsule_item(item: ItemEvidence, ref: str) -> CapsuleItem:
    velocity = _band_velocity(max(item.recent_velocity_per_day or 0, item.daily_velocity or 0))
    dos_band = _band_days_of_supply(item.days_of_supply)
    is_overstock = bool(item.overstock_days and item.overstock_days > 0) or (dos_band == "OVER")
    is_stockout = bool(item.stockout_days and item.stockout_days > 0) or (dos_band == "CRITICAL")

    evidence_fields = [
        "classification", "stock_band", "velocity_band", "days_of_supply_band",
        "is_overstock", "is_stockout_risk", "inventory_age_band", "last_sale_band",
        "is_seasonal", "seasonal_type", "days_until_season", "trend",
        "sales_frequency_band", "demand_volatility_band", "margin_band",
        "supplier_reliability_band", "supplier_lead_time_band", "inbound_band",
        "is_strategic", "is_promotional", "promotion_type",
        "monthly_concentration_band", "candidate_decisions",
    ]

    return CapsuleItem(
        ref=ref,
        classification=item.classification,
        stock_band=_band_stock(item.current_stock),
        velocity_band=velocity,
        days_of_supply_band=dos_band,
        is_overstock=is_overstock,
        is_stockout_risk=is_stockout,
        inventory_age_band=_band_inventory_age(item.inventory_age_days),
        last_sale_band=_band_last_sale(item.days_since_last_sale, velocity),
        is_seasonal=bool(item.is_promotional is False and item.seasonal_type),
        seasonal_type=item.seasonal_type,
        days_until_season=item.days_until_season,
        trend=item.trend,
        sales_frequency_band={"NONE": "never", "LOW": "monthly", "MEDIUM": "weekly", "HIGH": "daily"}.get(velocity or "never"),
        demand_volatility_band=_band_volatility(item.demand_volatility),
        margin_band=_band_margin(item.margin_pct),
        supplier_reliability_band=_band_reliability(item.supplier_reliability),
        supplier_lead_time_band=_band_lead_time(item.supplier_lead_time_days),
        inbound_band=_band_inbound(item.confirmed_inbound_qty),
        is_strategic=item.is_strategic,
        is_promotional=item.is_promotional,
        promotion_type=None,
        monthly_concentration_band=_band_concentration(item.monthly_concentration_peak),
        candidate_decisions=_candidate_decisions_from_actions(item.candidate_actions),
        evidence_fields=evidence_fields,
    )


def _business_to_capsule_business(business: BusinessContext) -> CapsuleBusiness:
    return CapsuleBusiness(
        business_type=business.business_type,
        branch_count=None,
        capital_at_risk_band=_band_capital(business.total_capital_at_risk_sar),
        cash_available=_band_cash(business.cash_budget),
    )


def _business_constraints(business: BusinessContext) -> CapsuleConstraints:
    return CapsuleConstraints(
        max_discount_band=_band_max_discount(business.max_discount_pct),
        min_margin_band=_band_margin(business.minimum_margin_pct),
        blocked_refs=[],
        transfer_allowed=True,
    )


def build_reasoning_capsule(
    item: ItemEvidence,
    business: BusinessContext,
    *,
    capability: str,
    purpose: str,
    forecast_signals: Mapping[str, dict[str, Any]] | None = None,
    ttl_seconds: int = 90,
) -> ReasoningCapsule:
    """Build a single-item capsule for the reasoning (V8) path."""
    capsule = ReasoningCapsule.new(
        capability=capability,
        purpose=purpose,
        items=[item_evidence_to_capsule_item(item, "item_A")],
        business=_business_to_capsule_business(business),
        constraints=_business_constraints(business),
        forecast_signals=dict(forecast_signals or {}),
        ttl_seconds=ttl_seconds,
    )
    return CapsuleSigner().sign(capsule)


def build_challenge_capsule(
    context: StructuredContext,
    *,
    capability: str,
    purpose: str,
    ttl_seconds: int = 90,
) -> ReasoningCapsule:
    """Build a capsule from a StructuredContext for the challenge (V11) path."""
    product = context.product
    supplier = context.supplier
    owner = context.owner
    agg = context.business

    velocity = _band_velocity(max(product.recent_velocity, product.long_term_velocity, product.prior_velocity))
    dos_band = _band_days_of_supply(product.days_of_supply)
    is_overstock = dos_band == "OVER"
    is_stockout = dos_band == "CRITICAL"
    is_strategic = bool(product.sku and product.sku in owner.strategic_skus)
    is_blocked_discount = bool(product.sku and product.sku in owner.blocked_discount_skus)

    item = CapsuleItem(
        ref="item_A",
        classification=product.category or "unknown",
        stock_band=_band_stock(product.current_stock),
        velocity_band=velocity,
        days_of_supply_band=dos_band,
        is_overstock=is_overstock,
        is_stockout_risk=is_stockout,
        inventory_age_band=_band_inventory_age(product.inventory_age_days),
        last_sale_band=_band_last_sale(product.last_sale_days_ago, velocity),
        is_seasonal=context.seasonal.is_seasonal,
        seasonal_type=context.seasonal.seasonal_type,
        days_until_season=context.seasonal.days_until_season,
        trend=product.trend,
        sales_frequency_band=product.sales_frequency or None,
        demand_volatility_band=_band_volatility(product.demand_volatility),
        margin_band=_band_margin(product.gross_margin_pct),
        supplier_reliability_band=_band_reliability(supplier.supplier_reliability),
        supplier_lead_time_band=_band_lead_time(supplier.lead_time_days),
        inbound_band=_band_inbound(supplier.confirmed_inbound_qty),
        is_strategic=is_strategic,
        is_promotional=context.promotion.is_promotional,
        promotion_type=context.promotion.promotion_type,
        monthly_concentration_band=None,
        candidate_decisions=[context.deterministic_decision],
        evidence_fields=[
            "classification", "stock_band", "velocity_band", "days_of_supply_band",
            "is_overstock", "is_stockout_risk", "inventory_age_band", "last_sale_band",
            "is_seasonal", "seasonal_type", "days_until_season", "trend",
            "sales_frequency_band", "demand_volatility_band", "margin_band",
            "supplier_reliability_band", "supplier_lead_time_band", "inbound_band",
            "is_strategic", "is_promotional", "promotion_type",
            "monthly_concentration_band", "candidate_decisions",
        ],
    )

    constraints = CapsuleConstraints(
        max_discount_band=_band_max_discount(owner.max_discount_pct),
        min_margin_band=_band_margin(owner.min_margin_pct),
        blocked_refs=["item_A"] if is_blocked_discount else [],
        transfer_allowed=not bool(context.deterministic_decision == "TRANSFER"),
    )

    forecast_signals = {
        "deterministic": {
            "decision": context.deterministic_decision,
            "confidence": context.deterministic_confidence,
        }
    }

    capsule = ReasoningCapsule.new(
        capability=capability,
        purpose=purpose,
        items=[item],
        business=CapsuleBusiness(
            business_type=agg.business_type,
            branch_count=agg.branch_count,
            capital_at_risk_band=_band_capital(agg.total_capital_at_risk_sar),
            cash_available=_band_cash(owner.cash_budget),
        ),
        constraints=constraints,
        forecast_signals=forecast_signals,
        ttl_seconds=ttl_seconds,
    )
    return CapsuleSigner().sign(capsule)


def build_capsule_for_payload(
    payload: Mapping[str, Any],
    *,
    capability: str,
    purpose: str,
    ttl_seconds: int = 90,
) -> ReasoningCapsule:
    """Build a multi-item capsule from a plain evidence dict (gateway path).

    Used by the OpenCode brain gateway when a caller hands the trusted zone an
    already-structured package (``items`` + ``business`` keyed like
    ItemEvidence/BusinessContext). Absent keys are safely skipped.
    """
    items_raw = payload.get("items", []) if isinstance(payload, dict) else []
    business_raw = payload.get("business", {})

    blocked_skus = set(business_raw.get("blocked_discount_products") or [])
    strategic_skus = set(business_raw.get("strategic_products") or [])

    ref_by_sku: dict[str, str] = {}
    capsule_items: list[CapsuleItem] = []
    for idx, raw in enumerate(items_raw):
        if not isinstance(raw, dict):
            continue
        ref = f"item_{chr(ord('A') + idx)}"
        sku = raw.get("sku")
        if sku:
            ref_by_sku[str(sku)] = ref

        candidate_decisions = _candidate_decisions_from_actions(raw.get("candidate_actions") or [])
        dos_band = _band_days_of_supply(raw.get("days_of_supply"))
        velocity = _band_velocity(max(raw.get("recent_velocity_per_day") or 0, raw.get("daily_velocity") or 0))
        is_overstock = dos_band == "OVER"
        is_stockout = dos_band == "CRITICAL"

        capsule_items.append(
            CapsuleItem(
                ref=ref,
                classification=raw.get("classification"),
                stock_band=_band_stock(raw.get("current_stock")),
                velocity_band=velocity,
                days_of_supply_band=dos_band,
                is_overstock=is_overstock,
                is_stockout_risk=is_stockout,
                inventory_age_band=_band_inventory_age(raw.get("inventory_age_days")),
                last_sale_band=_band_last_sale(raw.get("days_since_last_sale"), velocity),
                is_seasonal=bool(raw.get("is_promotional") is False and raw.get("seasonal_type")),
                seasonal_type=raw.get("seasonal_type"),
                days_until_season=raw.get("days_until_season"),
                trend=raw.get("trend"),
                sales_frequency_band={"NONE": "never", "LOW": "monthly", "MEDIUM": "weekly", "HIGH": "daily"}.get(velocity or "never"),
                demand_volatility_band=_band_volatility(raw.get("demand_volatility")),
                margin_band=_band_margin(raw.get("margin_pct")),
                supplier_reliability_band=_band_reliability(raw.get("supplier_reliability")),
                supplier_lead_time_band=_band_lead_time(raw.get("supplier_lead_time_days")),
                inbound_band=_band_inbound(raw.get("confirmed_inbound_qty")),
                is_strategic=bool(raw.get("is_strategic") or (sku and sku in strategic_skus)),
                is_promotional=bool(raw.get("is_promotional")),
                promotion_type=None,
                monthly_concentration_band=_band_concentration(raw.get("monthly_concentration_peak")),
                candidate_decisions=candidate_decisions,
                evidence_fields=[
                    "classification", "stock_band", "velocity_band", "days_of_supply_band",
                    "is_overstock", "is_stockout_risk", "inventory_age_band", "last_sale_band",
                    "is_seasonal", "seasonal_type", "days_until_season", "trend",
                    "sales_frequency_band", "demand_volatility_band", "margin_band",
                    "supplier_reliability_band", "supplier_lead_time_band", "inbound_band",
                    "is_strategic", "is_promotional", "promotion_type",
                    "monthly_concentration_band", "candidate_decisions",
                ],
            )
        )

    blocked_refs = [ref_by_sku[str(s)] for s in blocked_skus if str(s) in ref_by_sku]

    constraints = CapsuleConstraints(
        max_discount_band=_band_max_discount(business_raw.get("max_discount_pct")),
        min_margin_band=_band_margin(business_raw.get("minimum_margin_pct")),
        blocked_refs=blocked_refs,
        transfer_allowed=True,
    )

    business = CapsuleBusiness(
        business_type=business_raw.get("business_type"),
        branch_count=business_raw.get("branch_count"),
        capital_at_risk_band=_band_capital(business_raw.get("total_capital_at_risk_sar")),
        cash_available=_band_cash(business_raw.get("cash_budget")),
    )

    capsule = ReasoningCapsule.new(
        capability=capability,
        purpose=purpose,
        items=capsule_items,
        business=business,
        constraints=constraints,
        ttl_seconds=ttl_seconds,
    )
    return CapsuleSigner().sign(capsule)