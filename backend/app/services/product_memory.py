"""Product Memory Service — derives structured product-level facts from existing data.

Phase 2 §4: Memory stores useful interpretation, not raw data.
Every field is computed from existing transactions, inventory, POs, actions, and outcomes.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.utils.clock import utcnow

logger = logging.getLogger("product_memory")

ZERO = Decimal("0")
MONEY_Q = Decimal("0.01")


def _money(v: Any) -> Decimal:
    try:
        return Decimal(str(v or 0)).quantize(MONEY_Q)
    except Exception:
        return ZERO


def _float(v: Any) -> float:
    return float(_money(v))


# ── Confidence Tiers ────────────────────────────────────────────────────────

def _confidence(evidence_count: int) -> str:
    if evidence_count >= 20:
        return "HIGH"
    if evidence_count >= 5:
        return "MEDIUM"
    if evidence_count >= 1:
        return "LOW"
    return "INSUFFICIENT_DATA"


# ── Trend Detection ─────────────────────────────────────────────────────────

def _detect_trend(
    velocity_7d: Decimal,
    velocity_30d: Decimal,
    velocity_90d: Decimal,
) -> str:
    """Simple multi-window trend detection. §5 spec."""
    if velocity_90d <= 0 and velocity_30d <= 0 and velocity_7d <= 0:
        return "INSUFFICIENT_DATA"
    if velocity_90d <= 0:
        # No long-term data; use short windows
        if velocity_30d > 0 and velocity_7d > velocity_30d * Decimal("1.2"):
            return "INCREASING"
        if velocity_30d > 0 and velocity_7d < velocity_30d * Decimal("0.8"):
            return "DECLINING"
        return "STABLE"
    # Compare 7d vs 30d, 30d vs 90d
    r7_30 = velocity_7d / velocity_30d if velocity_30d > 0 else Decimal("1")
    r30_90 = velocity_30d / velocity_90d if velocity_90d > 0 else Decimal("1")
    # Both increasing
    if r7_30 > Decimal("1.15") and r30_90 > Decimal("1.05"):
        return "INCREASING"
    # Both declining
    if r7_30 < Decimal("0.85") and r30_90 < Decimal("0.95"):
        return "DECLINING"
    return "STABLE"


# ── Seasonal Detection ──────────────────────────────────────────────────────

def _detect_seasonality(
    monthly_concentrations: list[Decimal] | None,
    monthly_sales: dict[str, Decimal] | None,
) -> dict[str, Any]:
    """Simple seasonal signal from monthly concentration data. §6 spec."""
    if not monthly_concentrations or len(monthly_concentrations) < 3:
        return {
            "seasonal_type": "UNKNOWN",
            "seasonal_strength": 0.0,
            "active_season": None,
            "next_expected_season": None,
            "days_until_expected_season": None,
        }
    # Calculate concentration ratio: max month / total
    total = sum(monthly_concentrations)
    if total <= 0:
        return {
            "seasonal_type": "UNKNOWN",
            "seasonal_strength": 0.0,
            "active_season": None,
            "next_expected_season": None,
            "days_until_expected_season": None,
        }
    peak = max(monthly_concentrations)
    strength = float(peak / total) if total > 0 else 0.0

    if strength >= 0.35:
        # Find peak month (approximate from concentration order)
        # monthly_concentrations is ordered oldest→newest
        peak_idx = monthly_concentrations.index(peak)
        months_back = len(monthly_concentrations) - 1 - peak_idx
        now = utcnow()
        peak_month = (now.month - months_back - 1) % 12 + 1
        month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                       "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        return {
            "seasonal_type": "SEASONAL",
            "seasonal_strength": round(strength, 2),
            "active_season": month_names[peak_month - 1],
            "next_expected_season": month_names[peak_month - 1],
            "days_until_expected_season": max(0, (12 - now.month + peak_month) % 12 * 30),
        }
    return {
        "seasonal_type": "NOT_SEASONAL",
        "seasonal_strength": round(strength, 2),
        "active_season": None,
        "next_expected_season": None,
        "days_until_expected_season": None,
    }


# ── Product Memory Dataclass ────────────────────────────────────────────────

@dataclass
class ProductMemory:
    """Structured, derived product-level memory. §4 spec."""
    product_id: str
    business_id: str
    product_name: str
    sku: str
    category: str | None

    # Current inventory
    current_stock: float
    inventory_value_sar: float
    cost_price: float
    sell_price: float
    gross_margin_pct: float

    # Velocity
    velocity_7d: float
    velocity_30d: float
    velocity_90d: float

    # Trend
    trend: str  # INCREASING / STABLE / DECLINING / INSUFFICIENT_DATA
    demand_stability: str  # STABLE / VOLATILE / INSUFFICIENT_DATA

    # Days of supply
    days_of_supply: float | None

    # Sales recency
    last_sale_at: str | None
    days_since_last_sale: int | None

    # Stockout history
    stockout_count: int
    stockout_frequency: str  # HIGH / MEDIUM / LOW / NONE / INSUFFICIENT_DATA

    # Dead/slow stock history
    dead_stock_events: int
    slow_stock_events: int

    # Seasonal
    seasonal_type: str
    seasonal_strength: float
    active_season: str | None
    next_expected_season: str | None
    days_until_expected_season: int | None

    # Promotion
    promotion_count: int
    last_promotion: str | None
    current_promotion: bool
    pre_promotion_velocity: float | None
    promotion_velocity: float | None
    post_promotion_velocity: float | None

    # Supplier
    primary_supplier_id: str | None
    primary_supplier_name: str | None
    supplier_reliability: str | None  # HIGH / MEDIUM / LOW / INSUFFICIENT_DATA

    # Action history
    last_action: str | None
    last_action_at: str | None
    last_action_result: str | None
    last_outcome_sar: float | None
    prediction_error_pct: float | None

    # Confidence & freshness
    confidence: str
    evidence_count: int
    memory_updated_at: str
    source_period_start: str | None
    source_period_end: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ── Core Memory Builder ─────────────────────────────────────────────────────

async def build_product_memory(
    db: AsyncSession,
    business_id: UUID | str,
    item_id: UUID | str,
) -> ProductMemory:
    """Build structured memory for one product from existing data. §4 spec."""
    b = str(business_id)
    i = str(item_id)
    now = utcnow()
    anchor = now.date()

    # ── Item + Inventory ─────────────────────────────────────────────────
    item_res = await db.execute(text("""
        SELECT i.id, i.name, i.sku, i.cost_price, i.sell_price,
               i.category_id, c.name AS category_name,
               inv.current_stock, inv.reorder_level, inv.safety_stock,
               inv.supplier_id, inv.last_stockout_date, inv.stockout_count_90d,
               inv.last_restocked
        FROM items i
        LEFT JOIN inventory inv ON inv.item_id = i.id AND inv.business_id = i.business_id
        LEFT JOIN categories c ON c.id = i.category_id
        WHERE i.id = :item_id AND i.business_id = :business_id
    """), {"item_id": i, "business_id": b})
    row = item_res.fetchone()
    if not row:
        raise ValueError(f"Item {item_id} not found for business {business_id}")

    stock = _money(row.current_stock)
    cost = _money(row.cost_price)
    sell = _money(row.sell_price)
    margin = ((sell - cost) / sell * 100) if sell > 0 else ZERO

    # ── Velocity (3 windows) ────────────────────────────────────────────
    velocity_7d = await _velocity(db, b, i, anchor - timedelta(days=7), anchor)
    velocity_30d = await _velocity(db, b, i, anchor - timedelta(days=30), anchor)
    velocity_90d = await _velocity(db, b, i, anchor - timedelta(days=90), anchor)

    # ── Trend ───────────────────────────────────────────────────────────
    trend = _detect_trend(velocity_7d, velocity_30d, velocity_90d)

    # ── Demand stability (coefficient of variation of daily sales, 30d) ─
    demand_stability = await _demand_stability(db, b, i, anchor - timedelta(days=30), anchor)

    # ── Days of supply ──────────────────────────────────────────────────
    daily_v = velocity_30d / Decimal("30") if velocity_30d > 0 else ZERO
    dos = float(stock / daily_v) if daily_v > 0 else None

    # ── Last sale ───────────────────────────────────────────────────────
    last_sale_res = await db.execute(text("""
        SELECT MAX(transaction_at) AS last_sale
        FROM transactions
        WHERE business_id = :b AND item_id = :i AND transaction_type = 'sale'
    """), {"b": b, "i": i})
    last_sale_row = last_sale_res.fetchone()
    last_sale_at = None
    days_since_last_sale = None
    if last_sale_row and last_sale_row.last_sale:
        last_sale_dt = last_sale_row.last_sale
        if isinstance(last_sale_dt, datetime):
            last_sale_at = last_sale_dt.isoformat()
            days_since_last_sale = max(0, (now - last_sale_dt).days)
        elif isinstance(last_sale_dt, date):
            last_sale_at = last_sale_dt.isoformat()
            days_since_last_sale = max(0, (anchor - last_sale_dt).days)

    # ── Stockout count ──────────────────────────────────────────────────
    stockout_count = int(row.stockout_count_90d or 0)
    # Supplement with transaction gap detection
    gap_count = await _count_stockout_gaps(db, b, i, anchor - timedelta(days=90), anchor)
    stockout_count = max(stockout_count, gap_count)
    if stockout_count >= 5:
        stockout_freq = "HIGH"
    elif stockout_count >= 2:
        stockout_freq = "MEDIUM"
    elif stockout_count >= 1:
        stockout_freq = "LOW"
    else:
        stockout_freq = "NONE" if velocity_30d > 0 else "INSUFFICIENT_DATA"

    # ── Dead/slow stock events from money_audit_actions ─────────────────
    dead_events_res = await db.execute(text("""
        SELECT COUNT(*) AS cnt FROM money_audit_actions
        WHERE business_id = :b AND item_id = :i
          AND action_type = 'discount'
          AND (evidence->>'classification' = 'DEAD'
               OR evidence->>'reason' = 'dead_stock')
    """), {"b": b, "i": i})
    dead_stock_events = 0
    dead_row = dead_events_res.fetchone()
    if dead_row and dead_row.cnt:
        dead_stock_events = int(dead_row.cnt)

    slow_events_res = await db.execute(text("""
        SELECT COUNT(*) AS cnt FROM money_audit_actions
        WHERE business_id = :b AND item_id = :i
          AND action_type = 'discount'
          AND (evidence->>'classification' = 'SLOW MOVING'
               OR evidence->>'reason' = 'slow_moving')
    """), {"b": b, "i": i})
    slow_stock_events = 0
    slow_row = slow_events_res.fetchone()
    if slow_row and slow_row.cnt:
        slow_stock_events = int(slow_row.cnt)

    # ── Seasonal detection ──────────────────────────────────────────────
    monthly_res = await db.execute(text("""
        SELECT DATE_TRUNC('month', transaction_at) AS month_bucket,
               SUM(CASE WHEN transaction_type = 'sale' THEN quantity
                        WHEN transaction_type IN ('return','refund') THEN -quantity
                        ELSE 0 END) AS month_qty
        FROM transactions
        WHERE business_id = :b AND item_id = :i
          AND transaction_at >= (:anchor)::date - INTERVAL '180 days'
        GROUP BY DATE_TRUNC('month', transaction_at)
        ORDER BY month_bucket
    """), {"b": b, "i": i, "anchor": anchor})
    monthly_data = [Decimal(str(r.month_qty or 0)) for r in monthly_res.fetchall()]
    seasonal = _detect_seasonality(monthly_data, None)

    # ── Promotion detection (price drops > 10% with volume spike) ──────
    promotion = await _detect_promotion(db, b, i, anchor)

    # ── Primary supplier ────────────────────────────────────────────────
    supplier_res = await db.execute(text("""
        SELECT s.id, s.name_en, s.lead_time_days,
               inv.supplier_id AS inv_supplier
        FROM inventory inv
        LEFT JOIN suppliers s ON s.id = inv.supplier_id
        WHERE inv.item_id = :i AND inv.business_id = :b
    """), {"i": i, "b": b})
    sup_row = supplier_res.fetchone()
    primary_supplier_id = str(sup_row.id) if sup_row and sup_row.id else None
    primary_supplier_name = sup_row.name_en if sup_row and sup_row.name_en else None

    # Supplier reliability from PO history
    supplier_reliability = None
    if primary_supplier_id:
        supplier_reliability = await _supplier_reliability(db, b, primary_supplier_id)

    # ── Last action + outcome ───────────────────────────────────────────
    action_res = await db.execute(text("""
        SELECT aa.action_type, aa.created_at, aa.status, aa.outcome_json,
               aa.estimated_value_sar
        FROM agent_actions aa
        WHERE aa.business_id = :b
          AND aa.payload->>'item_id' = :i
        ORDER BY aa.created_at DESC LIMIT 1
    """), {"b": b, "i": i})
    act_row = action_res.fetchone()
    last_action = act_row.action_type if act_row else None
    last_action_at = act_row.created_at.isoformat() if act_row and act_row.created_at else None
    last_action_result = act_row.status if act_row else None
    last_outcome_sar = None
    prediction_error_pct = None

    # Check outcome feedback for this action
    if act_row:
        outcome_res = await db.execute(text("""
            SELECT actual_outcome, delta, predicted_outcome
            FROM outcome_feedback
            WHERE agent_action_id = :aid
            ORDER BY created_at DESC LIMIT 1
        """), {"aid": str(act_row.id) if hasattr(act_row, 'id') else None})
        out_row = outcome_res.fetchone()
        if out_row:
            actual = out_row.actual_outcome if isinstance(out_row.actual_outcome, dict) else {}
            delta = out_row.delta if isinstance(out_row.delta, dict) else {}
            last_outcome_sar = float(actual.get("actual_recovery_sar", 0) or 0)
            prediction_error_pct = delta.get("prediction_error_pct")

    # ── Confidence ──────────────────────────────────────────────────────
    evidence_count = sum([
        1 if velocity_30d > 0 else 0,
        1 if last_sale_at else 0,
        1 if stockout_count > 0 else 0,
        1 if dead_stock_events > 0 or slow_stock_events > 0 else 0,
        1 if primary_supplier_id else 0,
        1 if monthly_data and len(monthly_data) >= 3 else 0,
        1 if last_action else 0,
    ])

    # Source period
    source_start = (anchor - timedelta(days=90)).isoformat()
    source_end = anchor.isoformat()

    return ProductMemory(
        product_id=i,
        business_id=b,
        product_name=row.name or "",
        sku=row.sku or "",
        category=row.category_name,
        current_stock=_float(stock),
        inventory_value_sar=_float(stock * cost),
        cost_price=_float(cost),
        sell_price=_float(sell),
        gross_margin_pct=round(float(margin), 1),
        velocity_7d=_float(velocity_7d),
        velocity_30d=_float(velocity_30d),
        velocity_90d=_float(velocity_90d),
        trend=trend,
        demand_stability=demand_stability,
        days_of_supply=round(dos, 1) if dos is not None else None,
        last_sale_at=last_sale_at,
        days_since_last_sale=days_since_last_sale,
        stockout_count=stockout_count,
        stockout_frequency=stockout_freq,
        dead_stock_events=dead_stock_events,
        slow_stock_events=slow_stock_events,
        seasonal_type=seasonal["seasonal_type"],
        seasonal_strength=seasonal["seasonal_strength"],
        active_season=seasonal["active_season"],
        next_expected_season=seasonal["next_expected_season"],
        days_until_expected_season=seasonal["days_until_expected_season"],
        promotion_count=promotion["promotion_count"],
        last_promotion=promotion["last_promotion"],
        current_promotion=promotion["current_promotion"],
        pre_promotion_velocity=promotion["pre_promotion_velocity"],
        promotion_velocity=promotion["promotion_velocity"],
        post_promotion_velocity=promotion["post_promotion_velocity"],
        primary_supplier_id=primary_supplier_id,
        primary_supplier_name=primary_supplier_name,
        supplier_reliability=supplier_reliability,
        last_action=last_action,
        last_action_at=last_action_at,
        last_action_result=last_action_result,
        last_outcome_sar=last_outcome_sar,
        prediction_error_pct=prediction_error_pct,
        confidence=_confidence(evidence_count),
        evidence_count=evidence_count,
        memory_updated_at=now.isoformat(),
        source_period_start=source_start,
        source_period_end=source_end,
    )


# ── Helper Functions ────────────────────────────────────────────────────────

async def _velocity(
    db: AsyncSession, business_id: str, item_id: str,
    from_date: date, to_date: date,
) -> Decimal:
    """Sum of sale quantities in the window."""
    res = await db.execute(text("""
        SELECT COALESCE(SUM(quantity), 0) AS total
        FROM transactions
        WHERE business_id = :b AND item_id = :i
          AND transaction_type = 'sale'
          AND transaction_at >= :from_date AND transaction_at < :to_date
    """), {"b": business_id, "i": item_id, "from_date": from_date, "to_date": to_date})
    row = res.fetchone()
    return _money(row.total if row else 0)


async def _demand_stability(
    db: AsyncSession, business_id: str, item_id: str,
    from_date: date, to_date: date,
) -> str:
    """Coefficient of variation of daily sales. §5 spec."""
    res = await db.execute(text("""
        SELECT DATE(transaction_at) AS day, SUM(quantity) AS qty
        FROM transactions
        WHERE business_id = :b AND item_id = :i
          AND transaction_type = 'sale'
          AND transaction_at >= :from_date AND transaction_at < :to_date
        GROUP BY DATE(transaction_at)
    """), {"b": business_id, "i": item_id, "from_date": from_date, "to_date": to_date})
    rows = res.fetchall()
    if len(rows) < 5:
        return "INSUFFICIENT_DATA"
    quantities = [float(r.qty or 0) for r in rows]
    mean = sum(quantities) / len(quantities)
    if mean <= 0:
        return "INSUFFICIENT_DATA"
    variance = sum((q - mean) ** 2 for q in quantities) / len(quantities)
    cv = (variance ** 0.5) / mean
    if cv < 0.3:
        return "STABLE"
    return "VOLATILE"


async def _count_stockout_gaps(
    db: AsyncSession, business_id: str, item_id: str,
    from_date: date, to_date: date,
) -> int:
    """Count days with zero sales when the item should have demand."""
    res = await db.execute(text("""
        SELECT COUNT(*) AS gap_days
        FROM (
            SELECT DATE(transaction_at) AS day
            FROM transactions
            WHERE business_id = :b AND item_id = :i
              AND transaction_type = 'sale'
              AND transaction_at >= :from_date AND transaction_at < :to_date
            GROUP BY DATE(transaction_at)
            HAVING SUM(quantity) <= 0
        ) gaps
    """), {"b": business_id, "i": item_id, "from_date": from_date, "to_date": to_date})
    row = res.fetchone()
    return int((row.gap_days if row else 0) or 0)


async def _detect_promotion(
    db: AsyncSession, business_id: str, item_id: str, anchor: date,
) -> dict[str, Any]:
    """Detect promotion activity from pricing rules and transaction patterns. §7 spec."""
    # Check pricing rules for active promotions
    promo_res = await db.execute(text("""
        SELECT COUNT(*) AS cnt, MAX(active_from) AS last_promo
        FROM pricing_rules
        WHERE business_id = :b AND item_id = :i AND is_active = true
          AND rule_type IN ('time_based', 'demand_based', 'bundle')
    """), {"b": business_id, "i": item_id})
    promo_row = promo_res.fetchone()
    promo_count = int((promo_row.cnt if promo_row else 0) or 0)
    last_promo = promo_row.last_promo.isoformat() if promo_row and promo_row.last_promo else None

    # Check for current promotion (price drop > 10% with volume increase)
    current_promo = False
    pre_vel = None
    promo_vel = None
    post_vel = None

    if promo_count > 0:
        # Simple heuristic: if recent velocity is > 150% of 30-day average, likely promotion
        vel_7d = await _velocity(db, business_id, item_id, anchor - timedelta(days=7), anchor)
        vel_30d = await _velocity(db, business_id, item_id, anchor - timedelta(days=30), anchor)
        avg_daily_30 = vel_30d / Decimal("30") if vel_30d > 0 else ZERO
        avg_daily_7 = vel_7d / Decimal("7") if vel_7d > 0 else ZERO
        if avg_daily_30 > 0 and avg_daily_7 > avg_daily_30 * Decimal("1.5"):
            current_promo = True
            pre_vel = float(avg_daily_30)
            promo_vel = float(avg_daily_7)

    return {
        "promotion_count": promo_count,
        "last_promotion": last_promo,
        "current_promotion": current_promo,
        "pre_promotion_velocity": pre_vel,
        "promotion_velocity": promo_vel,
        "post_promotion_velocity": post_vel,
    }


async def _supplier_reliability(
    db: AsyncSession, business_id: str, supplier_id: str,
) -> str:
    """Supplier reliability from PO fulfillment history. §8 spec."""
    res = await db.execute(text("""
        SELECT
            COUNT(*) AS total_pos,
            COUNT(CASE WHEN status = 'received' THEN 1 END) AS received,
            COUNT(CASE WHEN status = 'cancelled' THEN 1 END) AS cancelled,
            COUNT(CASE WHEN status IN ('sent','confirmed')
                       AND expected_delivery < CURRENT_DATE THEN 1 END) AS overdue
        FROM purchase_orders
        WHERE business_id = :b AND supplier_id = :s
    """), {"b": business_id, "s": supplier_id})
    row = res.fetchone()
    total = int(row.total_pos or 0) if row else 0
    received = int(row.received or 0) if row else 0
    overdue = int(row.overdue or 0) if row else 0

    if total < 3:
        return "INSUFFICIENT_DATA"
    on_time_rate = (received - overdue) / total if total > 0 else 0
    if on_time_rate >= 0.85:
        return "HIGH"
    if on_time_rate >= 0.65:
        return "MEDIUM"
    return "LOW"
