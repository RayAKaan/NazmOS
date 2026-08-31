"""Shared inventory-audit math — the single source of truth for Money Audit.

Both the authenticated Money Audit (``money_audit_service``) and the free guest
audit (``guest_audit_service``) drive this one pure function so that identical
product metrics always produce identical classifications and financial deltas.

The module is pure Python + ``recovery_intelligence`` primitives. No AI, no
no external services — every number is a deterministic calculation from the
evidence supplied.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Iterable

from app.services.recovery_intelligence import (
    classify_inventory,
    estimate_recovery,
    stockout_financials,
    FinancialEstimate,
)

D = Decimal
ZERO = D("0")

TARGET_MARGIN_PCT = D("0.22")
DEAD_STOCK_DAYS = 45
OVERSTOCK_DAYS = D("45")
STOCKOUT_DAYS = D("5")
STOCKOUT_HORIZON_DAYS = 7  # fallback horizon when supplier lead time is unavailable
OVERSTOCK_MIN_SURPLUS_SAR = D("500")


def money(value: Any) -> Decimal:
    if value is None:
        return ZERO
    try:
        return D(str(value)).quantize(D("0.01"), rounding=ROUND_HALF_UP)
    except Exception:
        return ZERO


@dataclass
class ProductMetrics:
    """Every signal the audit math needs about one product.

    Guests (no supplier data) leave the optional fields unset; the money audit
    supplies seasonal concentrations, calibration rates, confirmed inbound and
    supplier lead time. The math itself is identical for both.
    """

    name: str
    stock: D
    cost: D
    sell: D
    recent_qty_30: D
    prior_qty_30: D = ZERO
    last_sold_days: int | None = None
    inventory_age_days: int | None = None
    monthly_concentrations: list[D] | None = None
    calibration_discount_rates: Iterable[D] | None = None
    projected_stock: D | None = None
    lead_time_days: int | None = None
    safety_stock: D | None = None


@dataclass
class ProductAudit:
    """Deterministic classification + financial decomposition for one product."""

    name: str
    classification: str
    stock: D
    cost: D
    sell: D
    daily_velocity: D
    stock_value: D
    days_supply: D | None
    capital_at_risk: D
    dead_stock_value: D
    slow_moving_value: D
    overstock_value: D
    surplus_qty: D
    revenue_at_risk: D
    gross_profit_at_risk: D
    margin_leakage: D
    recoverable_low: D
    recoverable_high: D
    dead_recoverable_low: D
    dead_recoverable_high: D
    overstock_recoverable_high: D
    order_qty: D
    has_dead_or_slow_risk: bool
    has_overstock_risk: bool
    has_stockout_risk: bool
    has_margin_leakage: bool
    recovery: FinancialEstimate | None = None
    stockout: FinancialEstimate | None = None

    @property
    def needs_attention(self) -> bool:
        return (
            self.has_dead_or_slow_risk
            or self.has_overstock_risk
            or self.has_stockout_risk
            or self.has_margin_leakage
        )


def analyze_product(metrics: ProductMetrics) -> ProductAudit:
    """Classify one product and decompose its financial exposure.

    Mirrors the historical money-audit row logic exactly:
    - Dead/slow-moving capital at risk
    - Overstock surplus value (30-day-demand excess)
    - Stockout revenue/profit at risk (projected stock incl. usable inbound)
    - Margin leakage below the target reference margin
    Recovery is bounded by realizable proceeds; nothing is fabricated.
    """
    stock = money(metrics.stock)
    cost = money(metrics.cost)
    sell = money(metrics.sell)
    recent_qty_30 = money(metrics.recent_qty_30)
    prior_qty_30 = money(metrics.prior_qty_30)
    daily_velocity = recent_qty_30 / D("30") if recent_qty_30 > 0 else ZERO
    projected_stock = money(metrics.projected_stock if metrics.projected_stock is not None else stock)

    stock_value = stock * cost
    classification = classify_inventory(
        stock=stock,
        recent_qty_30=recent_qty_30,
        prior_qty_30=prior_qty_30,
        days_since_last_sale=metrics.last_sold_days,
        inventory_age_days=metrics.inventory_age_days,
        monthly_concentrations=metrics.monthly_concentrations,
    )

    recovery = estimate_recovery(
        classification=classification,
        stock=stock,
        cost=cost,
        sell=sell,
        calibration_rates=metrics.calibration_discount_rates,
    )

    capital_at_risk = ZERO
    dead_stock_value = ZERO
    slow_moving_value = ZERO
    recoverable_low = ZERO
    recoverable_high = ZERO
    dead_recoverable_low = ZERO
    dead_recoverable_high = ZERO
    has_dead_or_slow = False

    if classification in {"DEAD", "SLOW MOVING"}:
        has_dead_or_slow = True
        capital_at_risk += stock_value
        if classification == "DEAD":
            dead_stock_value += stock_value
        else:
            slow_moving_value += stock_value
        recoverable_low += recovery.recoverable_low
        recoverable_high += recovery.recoverable_high
        dead_recoverable_low += recovery.recoverable_low
        dead_recoverable_high += recovery.recoverable_high

    days_supply = None
    overstock_value = ZERO
    surplus_qty = ZERO
    overstock_recoverable_high = ZERO
    has_overstock = False
    if stock > 0 and cost > 0 and daily_velocity > 0:
        days_supply = stock / daily_velocity
        if days_supply > OVERSTOCK_DAYS:
            surplus_qty = max(ZERO, stock - daily_velocity * D("30"))
            surplus_value = surplus_qty * cost
            if surplus_value >= OVERSTOCK_MIN_SURPLUS_SAR and classification not in {"SEASONAL", "SLOW MOVING"}:
                has_overstock = True
                capital_at_risk += surplus_value
                overstock_value += surplus_value
                overstock_recoverable_high = min(surplus_value, money(surplus_qty * sell))
                recoverable_high += overstock_recoverable_high

    revenue_at_risk = ZERO
    gross_profit_at_risk = ZERO
    order_qty = ZERO
    has_stockout = False
    stockout: FinancialEstimate | None = None
    if daily_velocity > 0 and sell > 0:
        stockout = stockout_financials(
            stock=projected_stock,
            daily_velocity=daily_velocity,
            sell=sell,
            cost=cost,
            lead_time_days=metrics.lead_time_days,
            safety_stock=metrics.safety_stock,
        )
        if projected_stock / daily_velocity < STOCKOUT_DAYS:
            has_stockout = True
            revenue_at_risk += stockout.revenue_at_risk
            gross_profit_at_risk += stockout.gross_profit_at_risk
            lead_horizon = metrics.lead_time_days if metrics.lead_time_days is not None else STOCKOUT_HORIZON_DAYS
            order_qty = max(
                ZERO,
                daily_velocity * D(str(lead_horizon))
                + (money(metrics.safety_stock) if metrics.safety_stock is not None else ZERO)
                - projected_stock,
            )

    margin_leakage = ZERO
    has_margin_leakage = False
    if recent_qty_30 > 0 and cost > 0 and sell > 0:
        margin = (sell - cost) / sell
        if margin < TARGET_MARGIN_PCT:
            target_price = (cost / (D("1") - TARGET_MARGIN_PCT)).quantize(D("0.01"))
            leakage = max(ZERO, target_price - sell) * recent_qty_30
            if leakage > 0:
                has_margin_leakage = True
                margin_leakage = leakage
                gross_profit_at_risk += leakage

    return ProductAudit(
        name=metrics.name,
        classification=classification,
        stock=stock,
        cost=cost,
        sell=sell,
        daily_velocity=daily_velocity,
        stock_value=stock_value,
        days_supply=days_supply,
        capital_at_risk=capital_at_risk,
        dead_stock_value=dead_stock_value,
        slow_moving_value=slow_moving_value,
        overstock_value=overstock_value,
        surplus_qty=surplus_qty,
        revenue_at_risk=revenue_at_risk,
        gross_profit_at_risk=gross_profit_at_risk,
        margin_leakage=margin_leakage,
        recoverable_low=recoverable_low,
        recoverable_high=recoverable_high,
        dead_recoverable_low=dead_recoverable_low,
        dead_recoverable_high=dead_recoverable_high,
        overstock_recoverable_high=overstock_recoverable_high,
        order_qty=order_qty,
        has_dead_or_slow_risk=has_dead_or_slow,
        has_overstock_risk=has_overstock,
        has_stockout_risk=has_stockout,
        has_margin_leakage=has_margin_leakage,
        recovery=recovery,
        stockout=stockout,
    )