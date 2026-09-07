"""NazmOS-owned analytical semantics over DuckDB raw facts (Phase 1).

DuckDB only computes raw aggregates (``app.analytics.duckdb_engine``); every
business meaning — coverage-aware velocity, valuation basis, trend, status,
dead-stock scan — is implemented here on top of ``ItemFact`` and reuses the
canonical `audit_core` math so Money Audit, guests, agents and analytics all
agree by construction.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

from app.analytics.contracts import AnalyticalFeed, ItemFact, ItemKPI, ValueBasis
from app.services.audit_core import (
    ZERO,
    money,
)

TREND_UP_THRESHOLD = Decimal("0.10")
DEAD_MAX_DAILY_AVG = Decimal("0.1")
CRITICAL_STOCKOUT_DAYS = 2
LOW_STOCKOUT_DAYS = 5
OVERSTOCK_DAYS = 20


def daily_velocity(fact: ItemFact) -> Decimal:
    """Coverage-aware daily demand; the canonical ``audit_core`` convention."""
    from app.services.audit_core import coverage_aware_daily_velocity

    return coverage_aware_daily_velocity(fact.qty_30d, fact.coverage_days_30d)


def stock_value(current_stock: float, unit_price: float, basis: ValueBasis) -> Decimal:
    """Value of stock at an explicit basis (cost or sell).

    The engine keeps the raw floats; every monetary surface re-quantizes here
    so NazmOS money is always ``Decimal`` at 0.01.
    """
    del basis  # basis selects the price column the caller already passed
    return money(money(current_stock) * money(unit_price))


def days_until_stockout(current_stock: float, velocity: Decimal) -> Decimal | None:
    if velocity > 0:
        return money(Decimal(str(current_stock)) / velocity)
    return None


def trend_7d(qty_7d: float, qty_prev7d: float) -> str:
    if qty_prev7d > 0:
        change = (qty_7d - qty_prev7d) / qty_prev7d
        if change > TREND_UP_THRESHOLD:
            return "up"
        if change < -TREND_UP_THRESHOLD:
            return "down"
    return "stable"


def classify_status(
    current_stock: float,
    velocity: Decimal,
    *,
    include_overstock: bool = True,
    dead_max_daily_avg: Decimal = DEAD_MAX_DAILY_AVG,
) -> str:
    """Full listing/alert classification shared by list, detail and alerts.

    ``include_overstock=False`` reproduces the health-score buckets (healthy
    for anything >= ``LOW_STOCKOUT_DAYS`` days, no overstock bucket).
    """
    if velocity < dead_max_daily_avg:
        return "dead"
    remaining = days_until_stockout(current_stock, velocity)
    if remaining is None:
        return "dead"
    if remaining < CRITICAL_STOCKOUT_DAYS:
        return "critical"
    if remaining < LOW_STOCKOUT_DAYS:
        return "low"
    if include_overstock and remaining > OVERSTOCK_DAYS:
        return "overstock"
    return "healthy"


def kpi(fact: ItemFact) -> ItemKPI:
    """Derive the semantic KPI bundle for one raw fact."""
    velocity = daily_velocity(fact)
    return ItemKPI(
        fact=fact,
        daily_avg=velocity,
        stock_value_cost=stock_value(fact.current_stock, fact.cost_price, ValueBasis.COST),
        stock_value_sell=stock_value(fact.current_stock, fact.sell_price, ValueBasis.SELL),
        days_until_stockout=days_until_stockout(fact.current_stock, velocity),
        trend_7d=trend_7d(fact.qty_7d, fact.qty_prev7d),
    )


def dead_stock_total(feed: AnalyticalFeed, value_basis: ValueBasis) -> Decimal:
    """Sum of stuck value across dead items (WS5 canonical rule)."""
    total = ZERO
    for fact in feed.facts:
        if not fact.dead_by_scan:
            continue
        if value_basis is ValueBasis.COST:
            total += stock_value(fact.current_stock, fact.cost_price, value_basis)
        else:
            total += stock_value(fact.current_stock, fact.sell_price, value_basis)
    return total


def dead_stock_rows(
    feed: AnalyticalFeed,
    anchor_date: date,
) -> tuple[list[dict], Decimal]:
    """Router dead-stock scan (all-time rule), returning display rows + total.

    Mirrors the pre-DuckDB behavior field for field:
      - ``total_qty < 1`` -> synthetic 60-day-old sale, days_since = 60.
      - otherwise ``days_since`` from the latest sale date.
      - dead when ``days_since >= 30`` and ``current_stock > 0``.
      - recommendation: remove (>60d), discount (>45d), bundle (otherwise).
    """
    thirty = anchor_date - timedelta(days=60)
    rows: list[dict] = []
    total = ZERO
    for fact in feed.facts:
        if fact.current_stock <= 0:
            continue
        if fact.qty_30d < 1:
            last_sold = datetime.combine(thirty, datetime.min.time())
        elif fact.last_sold_at is not None:
            last_sold = fact.last_sold_at
        else:
            last_sold = datetime.combine(thirty, datetime.min.time())
        days_since = (anchor_date - last_sold.date()).days
        if days_since < 30:
            continue
        value = stock_value(fact.current_stock, fact.cost_price, ValueBasis.COST)
        total += value
        if days_since > 60:
            recommendation = "remove"
        elif days_since > 45:
            recommendation = "discount"
        else:
            recommendation = "bundle"
        rows.append(
            {
                "item_id": fact.item_id,
                "name": fact.name,
                "category": fact.category_name or "Uncategorized",
                "current_stock": float(fact.current_stock),
                "stock_value": float(value),
                "last_sold_at": (
                    last_sold.strftime("%Y-%m-%d") if last_sold else None
                ),
                "days_since_last_sale": days_since,
                "recommendation": recommendation,
            }
        )
    return rows, total