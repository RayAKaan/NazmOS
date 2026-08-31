"""Phase C1 — the shared audit core is the single source of truth.

The free guest audit and the authenticated Money Audit must produce identical
classifications and financial deltas for identical product metrics. This test
replays the *historical money-audit row math* (the deterministic formula the
two engines previously duplicated) against ``audit_core.analyze_product`` and
proves numeric equivalence across targeted and randomized scenarios.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

import pytest

from app.services.audit_core import ProductMetrics, analyze_product, money
from app.services.guest_audit_service import run_guest_audit
from app.services.recovery_intelligence import classify_inventory, estimate_recovery, stockout_financials

D = Decimal
ZERO = D("0")
TARGET_MARGIN_PCT = D("0.22")
OVERSTOCK_DAYS = D("45")
STOCKOUT_DAYS = D("5")


def _q(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


@dataclass
class RefMetrics:
    stock: D
    cost: D
    sell: D
    qty_30d: D
    prior: D = ZERO
    last_sold_days: int | None = None
    projected_stock: D | None = None
    lead_time: int | None = None
    safety: D | None = None


def legacy_money_semantics(m: RefMetrics) -> dict[str, Decimal | str | None]:
    """The historical money-audit per-row math, kept verbatim as the oracle."""
    stock, cost, sell, qty_30d, prior = m.stock, m.cost, m.sell, m.qty_30d, m.prior
    daily = qty_30d / D("30") if qty_30d > 0 else ZERO
    stock_value = stock * cost
    projected = m.projected_stock if m.projected_stock is not None else stock

    classification = classify_inventory(
        stock=stock, recent_qty_30=qty_30d, prior_qty_30=prior,
        days_since_last_sale=m.last_sold_days, inventory_age_days=None,
    )
    recovery = estimate_recovery(classification=classification, stock=stock, cost=cost, sell=sell)
    if classification in {"DEAD", "SLOW MOVING"}:
        recovery = estimate_recovery(classification=classification, stock=stock, cost=cost, sell=sell)

    capital = ZERO
    dead_all = ZERO
    rec_low = ZERO
    rec_high = ZERO
    if classification in {"DEAD", "SLOW MOVING"}:
        capital += stock_value
        dead_all += stock_value
        rec_low += recovery.recoverable_low
        rec_high += recovery.recoverable_high

    overstock = ZERO
    overstock_rec_high = ZERO
    days_supply = None
    if stock > 0 and cost > 0 and daily > 0:
        days_supply = stock / daily
        if days_supply > OVERSTOCK_DAYS:
            surplus = max(ZERO, stock - daily * D("30"))
            surplus_value = surplus * cost
            if surplus_value >= D("500") and classification not in {"SEASONAL", "SLOW MOVING"}:
                overstock = surplus_value
                capital += surplus_value
                overstock_rec_high = min(surplus_value, _q(surplus * sell))
                rec_high += overstock_rec_high

    rev = ZERO
    gross = ZERO
    order_qty = ZERO
    has_stockout = False
    if daily > 0 and sell > 0:
        stockout = stockout_financials(
            stock=projected, daily_velocity=daily, sell=sell, cost=cost,
            lead_time_days=m.lead_time, safety_stock=m.safety,
        )
        if projected / daily < STOCKOUT_DAYS:
            has_stockout = True
            rev += stockout.revenue_at_risk
            gross += stockout.gross_profit_at_risk
            order_qty = max(ZERO, daily * D(str(m.lead_time or 7)) + (m.safety or ZERO) - projected)

    leakage = ZERO
    has_leakage = False
    if qty_30d > 0 and cost > 0 and sell > 0:
        margin = (sell - cost) / sell
        if margin < TARGET_MARGIN_PCT:
            target = (cost / (D("1") - TARGET_MARGIN_PCT)).quantize(D("0.01"))
            leakage = max(ZERO, target - sell) * qty_30d
            if leakage > 0:
                has_leakage = True
                gross += leakage

    return {
        "classification": classification,
        "days_supply": days_supply,
        "capital_at_risk": capital,
        "dead_all": dead_all,
        "overstock": overstock,
        "overstock_rec_high": overstock_rec_high,
        "revenue": rev,
        "gross": gross,
        "leakage": leakage,
        "rec_low": rec_low,
        "rec_high": rec_high,
        "order_qty": order_qty,
        "has_stockout": has_stockout,
        "has_leakage": has_leakage,
    }


def audit_to_ref_keys(audit) -> dict[str, Decimal | str | None]:
    return {
        "classification": audit.classification,
        "days_supply": audit.days_supply,
        "capital_at_risk": audit.capital_at_risk,
        "dead_all": audit.dead_stock_value + audit.slow_moving_value,
        "overstock": audit.overstock_value,
        "overstock_rec_high": audit.overstock_recoverable_high,
        "revenue": audit.revenue_at_risk,
        "gross": audit.gross_profit_at_risk,
        "leakage": audit.margin_leakage,
        "rec_low": audit.recoverable_low - ZERO,
        "rec_high": (
            audit.dead_recoverable_high + audit.overstock_recoverable_high
        ),
        "order_qty": audit.order_qty,
        "has_stockout": audit.has_stockout_risk,
        "has_leakage": audit.has_margin_leakage,
    }


REF_CASES: list[RefMetrics] = [
    # Dead stock (no sales)
    RefMetrics(stock=D("100"), cost=D("5"), sell=D("8"), qty_30d=ZERO),
    # Slow-moving out of stock
    RefMetrics(stock=ZERO, cost=D("5"), sell=D("8"), qty_30d=D("15")),
    # Overstock with high surplus value
    RefMetrics(stock=D("4000"), cost=D("10"), sell=D("14"), qty_30d=D("30")),
    # Stockout with projected inbound covering demand
    RefMetrics(stock=D("3"), cost=D("6"), sell=D("12"), qty_30d=D("60"),
               projected_stock=D("33"), lead_time=5, safety=D("10")),
    # Stockout with NO inbound
    RefMetrics(stock=D("2"), cost=D("6"), sell=D("12"), qty_30d=D("60")),
    # Margin leakage
    RefMetrics(stock=D("50"), cost=D("9"), sell=D("10"), qty_30d=D("300")),
    # Fast mover
    RefMetrics(stock=D("120"), cost=D("4"), sell=D("7"), qty_30d=D("120")),
    # Healthy with zero stock
    RefMetrics(stock=ZERO, cost=D("2"), sell=D("5"), qty_30d=D("300")),
]


def test_analyze_product_matches_legacy_money_math_on_targeted_cases():
    for m in REF_CASES:
        audit = analyze_product(ProductMetrics(
            name="x", stock=m.stock, cost=m.cost, sell=m.sell,
            recent_qty_30=m.qty_30d, prior_qty_30=m.prior,
            last_sold_days=m.last_sold_days,
            projected_stock=m.projected_stock,
            lead_time_days=m.lead_time,
            safety_stock=m.safety,
        ))
        ref = legacy_money_semantics(m)
        for key in ("classification", "capital_at_risk", "dead_all", "overstock",
                    "overstock_rec_high", "revenue", "gross", "leakage",
                    "rec_low", "rec_high", "order_qty"):
            got = audit_to_ref_keys(audit)[key]
            expect = ref[key]
            if isinstance(expect, Decimal):
                assert _q(Decimal(got)) == _q(expect), f"case={m} key={key} got={got} expected={expect}"
            else:
                assert got == expect, f"case={m} key={key} got={got} expected={expect}"
        assert audit.days_supply == ref["days_supply"]
        assert audit.has_stockout_risk == ref["has_stockout"]
        assert audit.has_margin_leakage == ref["has_leakage"]


def test_analyze_product_matches_legacy_money_math_randomized():
    rng = random.Random(20260831)
    for _ in range(600):
        stock = D(str(rng.choice([0, 0, 1, 3, 10, 50, 120, 800, 4000, 20000])))
        cost = D(str(rng.choice([2, 4, 5, 6, 9, 11, 30, 80])))
        sell = D(str(rng.choice([3, 5, 6, 7, 10, 12, 14, 20, 35, 100])))
        qty = D(str(rng.choice([0, 1, 5, 15, 30, 60, 120, 300, 900])))
        prior = D(str(rng.choice([0, 0, 10, 45, 200])))
        projected = _npick(rng, stock)
        lead = rng.choice([None, 3, 7, 14])
        safety = D(str(rng.choice([0, 5, 10, 25])))
        m = RefMetrics(stock=stock, cost=cost, sell=sell, qty_30d=qty, prior=prior,
                       last_sold_days=rng.choice([None, 5, 30, 90]),
                       projected_stock=projected, lead_time=lead, safety=safety)
        audit = analyze_product(ProductMetrics(
            name="p", stock=stock, cost=cost, sell=sell, recent_qty_30=qty,
            prior_qty_30=prior, last_sold_days=m.last_sold_days,
            projected_stock=projected, lead_time_days=lead, safety_stock=safety,
        ))
        ref = legacy_money_semantics(m)
        for key in ("classification", "capital_at_risk", "dead_all", "overstock",
                    "overstock_rec_high", "revenue", "gross", "leakage",
                    "rec_low", "rec_high", "order_qty"):
            got = audit_to_ref_keys(audit)[key]
            expect = ref[key]
            if isinstance(expect, Decimal):
                assert _q(Decimal(got)) == _q(expect), f"key={key} got={got} expected={expect} metrics={m}"
            else:
                assert got == expect, f"key={key} got={got} expected={expect} metrics={m}"


def _npick(rng, stock: D) -> D:
    """Random projected stock in the plausible range around on-hand stock."""
    return stock + D(str(rng.choice([0, 0, 20, 60, 120])))


@pytest.mark.asyncio
async def test_guest_and_money_paths_agree_on_two_file_audit():
    """Two-file guest audit uses the same core; categories all surface."""
    from datetime import timedelta

    import pandas as pd

    from app.services.file_ingestion import resolve_columns
    from app.services.guest_audit_service import run_two_file_audit

    recent = (__import__("datetime").datetime.utcnow() - timedelta(days=5)).date().isoformat()
    sales_df = pd.DataFrame([
        {"name": "Hot SKU", "quantity": "75", "price": "12", "date": recent},
        {"name": "Thin SKU", "quantity": "40", "price": "15", "date": recent},
        {"name": "Margin SKU", "quantity": "40", "price": "10", "date": recent},
    ])
    inventory_df = pd.DataFrame([
        {"name": "Dead SKU", "current_stock": "80", "cost": "5", "price": "8"},
        {"name": "Hot SKU", "current_stock": "2", "cost": "6", "price": "12"},
        {"name": "Thin SKU", "current_stock": "3000", "cost": "12", "price": "15"},
        {"name": "Margin SKU", "current_stock": "20", "cost": "9", "price": "10"},
    ])

    result = run_two_file_audit(sales_df, inventory_df, resolve_columns(sales_df), resolve_columns(inventory_df))
    s = result["summary"]
    assert s["dead_stock_value_sar"] == 400.0
    assert s["overstock_value_sar"] > 0
    assert s["stockout_risk_value_sar"] > 0
    assert s["margin_leakage_sar"] > 0
    assert s["is_two_file"] is True
    assert s["products_needing_attention"] == 4
    assert s["pairing"]["paired"] == 3
    assert s["pairing"]["success_rate"] == 100.0