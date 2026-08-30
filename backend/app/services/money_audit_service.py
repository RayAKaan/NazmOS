from __future__ import annotations

import html
import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.recovery_intelligence import classify_inventory, estimate_recovery, stockout_financials, ZERO
from app.utils.clock import utcnow

TARGET_MARGIN_PCT = Decimal("0.22")
MIN_REORDER_DAYS = Decimal("14")
DEAD_STOCK_DAYS = 45
OVERSTOCK_DAYS = Decimal("45")
STOCKOUT_DAYS = Decimal("5")
MAX_ACTIONS = 12


def _money(value: Any) -> Decimal:
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except Exception:
        return Decimal("0")


def _float(value: Any) -> float:
    return float(_money(value))


def _days_since(value: Any) -> int | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return max(0, (utcnow().date() - value.date()).days)
    if isinstance(value, date):
        return max(0, (utcnow().date() - value).days)
    return None


def _safe_text(value: Any) -> str:
    return str(value or "").strip()


@dataclass
class AuditComputation:
    summary: dict[str, Any]
    actions: list[dict[str, Any]]
    missing_data: list[dict[str, str]]


async def _period(db: AsyncSession, business_id: str) -> tuple[date | None, date | None]:
    result = await db.execute(
        text("""
            SELECT MIN(transaction_at)::date AS start_date, MAX(transaction_at)::date AS end_date
            FROM transactions
            WHERE business_id = :business_id
        """),
        {"business_id": business_id},
    )
    row = result.fetchone()
    if not row:
        return None, None
    return row.start_date, row.end_date


async def _quality(db: AsyncSession, business_id: str) -> dict[str, Any]:
    result = await db.execute(
        text("""
            SELECT
                COUNT(i.id) AS item_count,
                COUNT(inv.id) AS inventory_count,
                COALESCE(SUM(CASE WHEN inv.current_stock > 0 THEN 1 ELSE 0 END), 0) AS stocked_item_count,
                COALESCE(SUM(CASE WHEN i.cost_price > 0 THEN 1 ELSE 0 END), 0) AS cost_count,
                COALESCE(SUM(CASE WHEN i.sell_price > 0 THEN 1 ELSE 0 END), 0) AS price_count,
                COALESCE(SUM(CASE WHEN i.barcode IS NOT NULL AND i.barcode <> '' THEN 1 ELSE 0 END), 0) AS barcode_count,
                (SELECT COUNT(*) FROM transactions t WHERE t.business_id = :business_id) AS transaction_count,
                (SELECT COUNT(*) FROM uploaded_files u WHERE u.business_id = :business_id AND u.status = 'completed') AS completed_uploads,
                (SELECT COALESCE(SUM(COALESCE(u.row_count_received, u.row_count_raw, 0)), 0) FROM uploaded_files u WHERE u.business_id = :business_id) AS uploaded_rows,
                (SELECT COALESCE(SUM(COALESCE(u.row_count_rejected, u.row_count_failed, 0)), 0) FROM uploaded_files u WHERE u.business_id = :business_id) AS rejected_rows,
                (SELECT COALESCE(EXTRACT(DAY FROM (MAX(t.transaction_at) - MIN(t.transaction_at))), 0) FROM transactions t WHERE t.business_id = :business_id) AS sales_period_days
            FROM items i
            LEFT JOIN inventory inv ON inv.item_id = i.id AND inv.business_id = i.business_id
            WHERE i.business_id = :business_id AND i.is_active = true
        """),
        {"business_id": business_id},
    )
    row = result.fetchone()
    item_count = int(row.item_count or 0) if row else 0
    transaction_count = int(row.transaction_count or 0) if row else 0
    if item_count <= 0:
        return {
            "item_count": 0,
            "transaction_count": transaction_count,
            "completed_uploads": int(row.completed_uploads or 0) if row else 0,
            "cost_coverage_pct": 0,
            "price_coverage_pct": 0,
            "stock_coverage_pct": 0,
            "barcode_coverage_pct": 0,
            "score": 0,
            "warnings": [{"code": "no_items", "message": "No imported products yet. Upload inventory or sales file first."}],
        }

    def pct(v: Any) -> Decimal:
        return (_money(v) / Decimal(item_count) * Decimal("100")).quantize(Decimal("0.01"))

    cost = pct(row.cost_count)
    price = pct(row.price_count)
    stock = pct(row.stocked_item_count)
    barcode = pct(row.barcode_count)
    has_sales = transaction_count > 0
    completed_uploads = int(row.completed_uploads or 0)
    uploaded_rows = int(row.uploaded_rows or 0)
    rejected_rows = int(row.rejected_rows or 0)
    sales_period_days = int(row.sales_period_days or 0)
    row_integrity = (Decimal("100") - (Decimal(rejected_rows) / Decimal(max(1, uploaded_rows)) * Decimal("100"))) if uploaded_rows else Decimal("100")

    score = (cost * Decimal("0.28")) + (price * Decimal("0.17")) + (stock * Decimal("0.30")) + (barcode * Decimal("0.10")) + (Decimal("15") if has_sales else Decimal("0"))
    period_factor = min(Decimal("100"), Decimal(str(sales_period_days)) / Decimal("90") * Decimal("100")) if has_sales else Decimal("0")
    score = (score * (row_integrity / Decimal("100"))) * (Decimal("0.85") + Decimal("0.15") * (period_factor / Decimal("100")))
    score = min(Decimal("100"), score.quantize(Decimal("0.01")))

    warnings: list[dict[str, str]] = []
    if cost < 60:
        warnings.append({"code": "low_cost_coverage", "message": "Cost price is missing for many products. Money at Risk is conservative."})
    if stock < 60:
        warnings.append({"code": "low_stock_coverage", "message": "Current stock is missing for many products. Dead stock and stockout detection are limited."})
    if not has_sales:
        warnings.append({"code": "no_sales_history", "message": "No sales history imported yet. Stockout risk and margin leakage need a sales file."})
    if barcode < 40:
        warnings.append({"code": "low_barcode_coverage", "message": "Barcode coverage is low. Recovery Match and duplicate cleanup will need manual review."})
    if rejected_rows:
        warnings.append({"code": "rejected_rows", "message": f"{rejected_rows:,} of {uploaded_rows:,} uploaded rows require review. Audit confidence is reduced until they are reconciled."})
    if has_sales and sales_period_days < 30:
        warnings.append({"code": "short_sales_history", "message": f"Only {sales_period_days} days of sales history are available; trend and seasonality confidence is limited."})

    return {
        "item_count": item_count,
        "transaction_count": transaction_count,
        "completed_uploads": completed_uploads,
        "uploaded_rows": uploaded_rows,
        "rejected_rows": rejected_rows,
        "row_integrity_pct": _float(row_integrity),
        "sales_period_days": sales_period_days,
        "cost_coverage_pct": _float(cost),
        "price_coverage_pct": _float(price),
        "stock_coverage_pct": _float(stock),
        "barcode_coverage_pct": _float(barcode),
        "score": _float(score),
        "warnings": warnings,
    }


async def compute_money_audit(db: AsyncSession, business_id: UUID | str) -> AuditComputation:
    """Compute an evidence-first Money Audit.

    The legacy ``money_at_risk_sar`` concept is retained only for API compatibility.
    New consumers should use the distinct financial fields in ``summary``.
    """
    from app.database.connection import enforce_tenant_filter
    enforce_tenant_filter(str(business_id))

    business_id_str = str(business_id)
    period_start, period_end = await _period(db, business_id_str)
    quality = await _quality(db, business_id_str)
    anchor = period_end or utcnow().date()

    item_count = int(quality.get("item_count", 0))
    def pct(v: Any) -> Decimal:
        return (_money(v) / Decimal(max(1, item_count)) * Decimal("100")).quantize(Decimal("0.01"))

    business_res = await db.execute(
        text("SELECT type FROM businesses WHERE id = :business_id"),
        {"business_id": business_id_str},
    )
    business_row = business_res.fetchone()
    business_type = business_row.type if business_row else "retail"

    result = await db.execute(
        text("""
            WITH sales_30 AS (
                SELECT item_id,
                       COALESCE(SUM(CASE WHEN transaction_type = 'sale' THEN quantity WHEN transaction_type IN ('return','refund') THEN -quantity ELSE 0 END), 0) AS qty_30d,
                       COALESCE(SUM(CASE WHEN transaction_type = 'sale' THEN total_amount WHEN transaction_type IN ('return','refund') THEN total_amount ELSE 0 END), 0) AS revenue_30d,
                       COALESCE(SUM(CASE WHEN transaction_type = 'sale' THEN profit WHEN transaction_type IN ('return','refund') THEN profit ELSE 0 END), 0) AS profit_30d,
                       MAX(CASE WHEN transaction_type = 'sale' THEN transaction_at END) AS last_sold_at
                FROM transactions
                WHERE business_id = :business_id
                  AND transaction_at >= (:anchor)::date - INTERVAL '30 days'
                GROUP BY item_id
            ),
            sales_prior AS (
                SELECT item_id,
                       COALESCE(SUM(CASE WHEN transaction_type = 'sale' THEN quantity WHEN transaction_type IN ('return','refund') THEN -quantity ELSE 0 END), 0) AS qty_prior_30d,
                       COALESCE(SUM(CASE WHEN transaction_type = 'sale' THEN quantity WHEN transaction_type IN ('return','refund') THEN -quantity ELSE 0 END), 0) AS demand_prior_30d
                FROM transactions
                WHERE business_id = :business_id
                  AND transaction_at < (:anchor)::date - INTERVAL '30 days'
                  AND transaction_at >= (:anchor)::date - INTERVAL '60 days'
                GROUP BY item_id
            ),
            sales_90 AS (
                SELECT item_id,
                       COUNT(*) AS transaction_count_90d,
                       MAX(transaction_at) AS last_activity_at
                FROM transactions
                WHERE business_id = :business_id
                  AND transaction_at >= (:anchor)::date - INTERVAL '90 days'
                GROUP BY item_id
            ),
            monthly_sales AS (
                SELECT item_id, DATE_TRUNC('month', transaction_at) AS month_bucket,
                       SUM(CASE WHEN transaction_type = 'sale' THEN quantity WHEN transaction_type IN ('return','refund') THEN -quantity ELSE 0 END) AS month_qty
                FROM transactions
                WHERE business_id = :business_id
                  AND transaction_at >= (:anchor)::date - INTERVAL '90 days'
                GROUP BY item_id, DATE_TRUNC('month', transaction_at)
            ),
            month_concentration AS (
                SELECT item_id,
                       CASE WHEN SUM(GREATEST(month_qty, 0)) > 0
                            THEN MAX(GREATEST(month_qty, 0)) / SUM(GREATEST(month_qty, 0))
                            ELSE 0 END AS concentration
                FROM monthly_sales
                GROUP BY item_id
            )
            SELECT i.id AS item_id, i.name AS item_name, i.sku, i.barcode,
                   c.name AS category_name,
                   COALESCE(inv.current_stock, 0) AS current_stock,
                   COALESCE(i.cost_price, 0) AS cost_price,
                   COALESCE(i.sell_price, 0) AS sell_price,
                   COALESCE(s.qty_30d, 0) AS qty_30d,
                   COALESCE(s.revenue_30d, 0) AS revenue_30d,
                   COALESCE(s.profit_30d, 0) AS profit_30d,
                   COALESCE(p.qty_prior_30d, 0) AS qty_prior_30d,
                   COALESCE(s90.transaction_count_90d, 0) AS transaction_count_90d,
                   COALESCE(mc.concentration, 0) AS month_concentration,
                   COALESCE(s.last_sold_at, s90.last_activity_at) AS last_sold_at,
                   inv.reorder_level,
                   inv.safety_stock,
                   inv.last_restocked,
                   inv.lead_time_days,
                   inv.supplier_id,
                   sup.name_en AS supplier_name,
                   sup.lead_time_days AS supplier_lead_time_days,
                   sup.min_order_sar AS supplier_min_order_sar
            FROM items i
            LEFT JOIN inventory inv ON inv.item_id = i.id AND inv.business_id = i.business_id
            LEFT JOIN categories c ON c.id = i.category_id
            LEFT JOIN sales_30 s ON s.item_id = i.id
            LEFT JOIN sales_prior p ON p.item_id = i.id
            LEFT JOIN sales_90 s90 ON s90.item_id = i.id
            LEFT JOIN month_concentration mc ON mc.item_id = i.id
            LEFT JOIN suppliers sup ON sup.id = inv.supplier_id
            WHERE i.business_id = :business_id AND i.is_active = true
        """),
        {"business_id": business_id_str, "anchor": anchor},
    )
    rows = result.fetchall()

    inventory_value = ZERO = Decimal("0")
    capital_at_risk = Decimal("0")
    revenue_at_risk = Decimal("0")
    gross_profit_at_risk = Decimal("0")
    recoverable_low = Decimal("0")
    recoverable_high = Decimal("0")
    # Per-category financial breakdown for the Money Recovery Map.
    dead_stock_value = Decimal("0")
    overstock_value = Decimal("0")
    stockout_risk_value = Decimal("0")
    margin_leakage_value = Decimal("0")
    actions: list[dict[str, Any]] = []
    classifications: dict[str, int] = {}
    evidence_count = 0
    limited_analysis = business_type in {"cafe", "restaurant"}

    # Calibration is based only on observed completed Money Audit actions. No prior
    # observations means expected recovery remains unavailable rather than guessed.
    calibration_res = await db.execute(text("""
        SELECT action_type, completed_value_sar, expected_recovery_sar_v2,
               recoverable_value_low_sar, recoverable_value_high_sar\n        FROM money_audit_actions\n        WHERE business_id = :business_id AND status = 'completed' AND completed_value_sar IS NOT NULL
    """), {"business_id": business_id_str})
    calibration: dict[str, list[Decimal]] = {}
    for cr in calibration_res.fetchall():
        basis = cr.expected_recovery_sar_v2 or cr.recoverable_value_high_sar
        if basis and Decimal(str(basis)) > 0:
            calibration.setdefault(cr.action_type, []).append((Decimal(str(cr.completed_value_sar)) / Decimal(str(basis))))

    from app.services.po_service import (
        get_confirmed_inbound_map,
        usable_confirmed_inbound,
        projected_stockout_date,
    )
    inbound_map = await get_confirmed_inbound_map(db, business_id=business_id_str, as_of=anchor)
    confirmed_inbound: dict[str, Decimal] = {
        k: v.confirmed_inbound_qty for k, v in inbound_map.items()
    }
    confirmed_inbound_ghost: dict[str, bool] = {
        k: v.ghost_po_risk for k, v in inbound_map.items()
    }

    # V7: Query monthly sales concentrations per item for seasonal detection
    monthly_res = await db.execute(text("""
        SELECT item_id,
               DATE_TRUNC('month', transaction_at) AS month_bucket,
               SUM(CASE WHEN transaction_type = 'sale' THEN quantity
                        WHEN transaction_type IN ('return','refund') THEN -quantity
                        ELSE 0 END) AS month_qty
        FROM transactions
        WHERE business_id = :business_id
          AND transaction_at >= (:anchor)::date - INTERVAL '90 days'
        GROUP BY item_id, DATE_TRUNC('month', transaction_at)
        ORDER BY item_id, month_bucket
    """), {"business_id": business_id_str, "anchor": anchor})
    monthly_data: dict[str, list[Decimal]] = {}
    for mr in monthly_res.fetchall():
        iid = str(mr.item_id)
        monthly_data.setdefault(iid, []).append(_money(mr.month_qty))

    for row in rows:
        stock = _money(row.current_stock)
        cost = _money(row.cost_price)
        sell = _money(row.sell_price)
        qty_30d = _money(row.qty_30d)
        qty_prior = _money(row.qty_prior_30d)
        daily_velocity = qty_30d / Decimal("30") if qty_30d > 0 else Decimal("0")
        last_sold_days = None
        if row.last_sold_at:
            value = row.last_sold_at.date() if isinstance(row.last_sold_at, datetime) else row.last_sold_at
            last_sold_days = max(0, (anchor - value).days)
        stock_value = stock * cost
        inventory_value += stock_value
        item_name = _safe_text(row.item_name)

        inventory_age_days = None
        if row.last_restocked:
            restocked = row.last_restocked.date() if isinstance(row.last_restocked, datetime) else row.last_restocked
            inventory_age_days = max(0, (anchor - restocked).days)
        classification = classify_inventory(
            stock=stock,
            recent_qty_30=qty_30d,
            prior_qty_30=qty_prior,
            days_since_last_sale=last_sold_days,
            inventory_age_days=inventory_age_days,
            monthly_concentrations=monthly_data.get(str(row.item_id)),
        )
        classifications[classification] = classifications.get(classification, 0) + 1

        recovery = estimate_recovery(
            classification=classification,
            stock=stock,
            cost=cost,
            sell=sell,
            calibration_rates=calibration.get("discount", []),
        )
        if classification in {"DEAD", "SLOW MOVING"}:
            capital_at_risk += stock_value
            dead_stock_value += stock_value
            recoverable_low += recovery.recoverable_low
            recoverable_high += recovery.recoverable_high
            evidence_count += 1
            days_label = f"{last_sold_days} days" if last_sold_days is not None else "no recorded sale"
            actions.append({
                "item_id": str(row.item_id), "action_type": "discount",
                "priority": 1 if stock_value >= Decimal("5000") else 2,
                "title": f"Review {item_name} inventory",
                "description": f"{stock} units in stock; last sale {days_label}; recent 30-day demand {qty_30d} units vs {qty_prior} units in the preceding 30 days.",
                "expected_recovery_sar": recovery.expected_recovery,
                "recoverable_value_low_sar": recovery.recoverable_low,
                "recoverable_value_high_sar": recovery.recoverable_high,
                "recovery_confidence": recovery.confidence,
                "quantity": stock,
                "recommended_discount_pct": None,
                "reason": "dead_stock" if classification == "DEAD" else "slow_moving",
                "financial_model": {**recovery.json(), "financial_impact_type": "CAPITAL_AT_RISK"},
                "evidence": {
                    "item_id": str(row.item_id), "sku": row.sku, "item_name": item_name, "current_stock": float(stock),
                    "cost_price_sar": float(cost), "sell_price_sar": float(sell),
                    "inventory_value_sar": float(stock_value), "qty_30d": float(qty_30d),
                    "qty_prior_30d": float(qty_prior), "last_sold_days": last_sold_days,
                    "classification": classification,
                },
            })
        elif classification == "SEASONAL":
            evidence_count += 1
            actions.append({
                "item_id": str(row.item_id), "action_type": "reorder",
                "priority": 3,
                "title": f"Seasonal item: {item_name}",
                "description": f"Demand spike detected. {stock} units in stock; recent 30-day demand {qty_30d} units. Monitor for restocking before next season.",
                "expected_recovery_sar": None,
                "recoverable_value_low_sar": Decimal("0"),
                "recoverable_value_high_sar": Decimal("0"),
                "recovery_confidence": "INSUFFICIENT DATA",
                "quantity": stock,
                "recommended_discount_pct": None,
                "reason": "seasonal_pattern",
                "financial_model": {**recovery.json(), "financial_impact_type": "SEASONAL"},
                "evidence": {
                    "item_id": str(row.item_id), "sku": row.sku, "item_name": item_name,
                    "current_stock": float(stock), "cost_price_sar": float(cost),
                    "sell_price_sar": float(sell), "qty_30d": float(qty_30d),
                    "qty_prior_30d": float(qty_prior), "last_sold_days": last_sold_days,
                    "classification": classification,
                },
            })
        elif classification == "FAST":
            evidence_count += 1
            actions.append({
                "item_id": str(row.item_id), "action_type": "reorder",
                "priority": 3,
                "title": f"High velocity: {item_name}",
                "description": f"Selling well. {stock} units in stock; {daily_velocity.quantize(Decimal('0.1'))} units/day; {stock/daily_velocity if daily_velocity > 0 else 0:.0f} days supply.",
                "expected_recovery_sar": None,
                "recoverable_value_low_sar": Decimal("0"),
                "recoverable_value_high_sar": Decimal("0"),
                "recovery_confidence": "HIGH",
                "quantity": stock,
                "recommended_discount_pct": None,
                "reason": "fast_moving",
                "financial_model": {**recovery.json(), "financial_impact_type": "HEALTHY"},
                "evidence": {
                    "item_id": str(row.item_id), "sku": row.sku, "item_name": item_name,
                    "current_stock": float(stock), "daily_velocity": float(daily_velocity),
                    "classification": classification,
                },
            })

        if stock > 0 and cost > 0 and daily_velocity > 0:
            days_supply = stock / daily_velocity
            if days_supply > OVERSTOCK_DAYS:
                surplus_qty = max(Decimal("0"), stock - daily_velocity * Decimal("30"))
                surplus_value = surplus_qty * cost
                if surplus_value >= Decimal("500") and classification not in {"SEASONAL", "SLOW MOVING"}:
                    capital_at_risk += surplus_value
                    overstock_value += surplus_value
                    recoverable_high += min(surplus_value, _money(surplus_qty * sell))
                    evidence_count += 1
                    actions.append({
                        "item_id": str(row.item_id), "action_type": "recovery_match", "priority": 3,
                        "title": f"Review {item_name} for excess inventory",
                        "description": f"Approximately {surplus_qty.quantize(Decimal('0.01'))} units exceed a 30-day demand cover. No recovery percentage is assumed.",
                        "expected_recovery_sar": None,
                        "recoverable_value_low_sar": Decimal("0"),
                        "recoverable_value_high_sar": min(surplus_value, _money(surplus_qty * sell)),
                        "recovery_confidence": "LOW",
                        "quantity": surplus_qty.quantize(Decimal("0.01")), "recommended_discount_pct": None,
                        "reason": "overstock",
                        "financial_impact_type": "CAPITAL_AT_RISK",
                        "financial_model": {"classification": classification, "days_supply": float(days_supply), "surplus_units": float(surplus_qty)},
                        "evidence": {"sku": row.sku, "current_stock": float(stock), "daily_velocity": float(daily_velocity), "days_supply": float(days_supply), "surplus_value_sar": float(surplus_value)},
                    })

        if daily_velocity > 0 and sell > 0:
            lead_time = None
            if row.supplier_id is not None and row.supplier_lead_time_days is not None:
                lead_time = int(row.supplier_lead_time_days)
            elif row.supplier_id is not None and row.lead_time_days is not None:
                lead_time = int(row.lead_time_days)
            inbound_total = confirmed_inbound.get(str(row.item_id), Decimal('0'))
            # Time-aware reasoning (Section 4 / A6 / A7): compute the projected
            # stockout date from on-hand stock, then count as *usable* only the
            # confirmed inbound that arrives STRICTLY BEFORE that date. A PO that
            # arrives at/after the projected stockout (or with unknown arrival)
            # must NOT suppress an immediate reorder — it is surfaced as
            # actionable stockout risk instead.
            stockout_dt = projected_stockout_date(
                as_of=anchor, current_stock=stock, daily_demand=daily_velocity
            )
            timing = usable_confirmed_inbound(
                inbound_map.get(str(row.item_id)),
                stockout_date=stockout_dt,
            )
            usable_inbound = timing.usable_qty if timing is not None else Decimal('0')
            late_inbound = timing.late_qty if timing is not None else Decimal('0')
            projected_stock = stock + usable_inbound
            stockout = stockout_financials(
                stock=projected_stock, daily_velocity=daily_velocity, sell=sell, cost=cost,
                lead_time_days=lead_time,
                safety_stock=_money(row.safety_stock) if row.safety_stock is not None else None,
            )
            if projected_stock / daily_velocity < STOCKOUT_DAYS:
                revenue_at_risk += stockout.revenue_at_risk
                gross_profit_at_risk += stockout.gross_profit_at_risk
                stockout_risk_value += stockout.revenue_at_risk
                evidence_count += 1
                order_qty = max(Decimal("0"), daily_velocity * Decimal(str(lead_time or 7)) + (_money(row.safety_stock) if row.safety_stock is not None else Decimal("0")) - projected_stock)
                actions.append({
                    "item_id": str(row.item_id), "action_type": "reorder",
                    "priority": 1 if stock / daily_velocity < Decimal("2") else 2,
                    "title": f"Prevent stockout on {item_name}",
                    "description": f"Projected stock cover is {(projected_stock / daily_velocity).quantize(Decimal('0.1'))} days (incl. {usable_inbound} confirmed inbound arriving before stockout). Supplier lead time is {'unavailable' if lead_time is None else str(lead_time) + ' days'}." if late_inbound <= 0 else f"Projected stock cover is {(projected_stock / daily_velocity).quantize(Decimal('0.1'))} days. {late_inbound} units of confirmed inbound arrive too late (at/after projected stockout) to prevent the stockout. Supplier lead time is {'unavailable' if lead_time is None else str(lead_time) + ' days'}.",
                    "expected_recovery_sar": None,
                    "recoverable_value_low_sar": Decimal("0"), "recoverable_value_high_sar": Decimal("0"),
                    "recovery_confidence": stockout.confidence,
                    "quantity": order_qty.quantize(Decimal("1")), "recommended_discount_pct": None,
                    "reason": "stockout_risk", "financial_impact_type": "REVENUE_AT_RISK", "financial_model": {**stockout.json(), "financial_impact_type": "REVENUE_AT_RISK"},
                    "evidence": {"sku": row.sku, "item_name": item_name, **stockout.evidence, "confirmed_inbound_qty": float(inbound_total), "usable_inbound_qty": float(usable_inbound), "late_inbound_qty": float(late_inbound), "projected_stockout_date": stockout_dt.isoformat() if stockout_dt else None, "ghost_po_risk": bool(confirmed_inbound_ghost.get(str(row.item_id), False)), "supplier_name": row.supplier_name, "supplier_min_order_sar": float(row.supplier_min_order_sar) if row.supplier_min_order_sar is not None else None},
                })

        if qty_30d > 0 and cost > 0 and sell > 0:
            margin = (sell - cost) / sell
            if margin < TARGET_MARGIN_PCT:
                target_price = (cost / (Decimal("1") - TARGET_MARGIN_PCT)).quantize(Decimal("0.01"))
                leakage = max(Decimal("0"), target_price - sell) * qty_30d
                if leakage > 0:
                    # This is profit opportunity, not recoverable cash.
                    gross_profit_at_risk += leakage
                    margin_leakage_value += leakage
                    evidence_count += 1
                    actions.append({
                        "item_id": str(row.item_id), "action_type": "margin_fix", "priority": 2,
                        "title": f"Review margin on {item_name}",
                        "description": f"Current gross margin {pct(margin)}%; target reference {pct(TARGET_MARGIN_PCT)}%. This is theoretical profit opportunity, not recovered cash.",
                        "expected_recovery_sar": None, "recoverable_value_low_sar": Decimal("0"),
                        "recoverable_value_high_sar": leakage, "recovery_confidence": "LOW",
                        "quantity": qty_30d, "recommended_discount_pct": None, "reason": "margin_leakage",
                        "financial_model": {"current_cost_sar": float(cost), "current_price_sar": float(sell), "target_price_sar": float(target_price), "units_affected": float(qty_30d), "gross_profit_opportunity_sar": float(leakage)},
                        "evidence": {"sku": row.sku, "current_cost_sar": float(cost), "current_price_sar": float(sell), "current_margin_pct": float(pct(margin)), "units_30d": float(qty_30d), "target_price_sar": float(target_price)},
                    })

    actions = sorted(actions, key=lambda a: (a["priority"], -(float(a.get("recoverable_value_high_sar") or 0))))[:MAX_ACTIONS]
    calibrated_expected = sum((Decimal(str(a["expected_recovery_sar"])) for a in actions if a.get("expected_recovery_sar") is not None), Decimal("0"))
    data_confidence = Decimal(str(quality.get("score", 0))).quantize(Decimal("0.01"))
    overall_conf = "HIGH" if data_confidence >= 90 and evidence_count >= 5 else ("MEDIUM" if data_confidence >= 70 and evidence_count >= 2 else ("LOW" if evidence_count else "INSUFFICIENT DATA"))

    summary = {
        "period_start": period_start.isoformat() if period_start else None,
        "period_end": period_end.isoformat() if period_end else None,
        "financial_model_version": "v2",
        # Legacy compatibility only; do not display as the canonical headline.
        "money_at_risk_sar": _float(capital_at_risk),
        "inventory_value_sar": _float(inventory_value),
        "capital_at_risk_sar": _float(capital_at_risk),
        "revenue_at_risk_sar": _float(revenue_at_risk),
        "gross_profit_at_risk_sar": _float(gross_profit_at_risk),
        "dead_stock_value_sar": _float(dead_stock_value),
        "overstock_value_sar": _float(overstock_value),
        "stockout_risk_value_sar": _float(stockout_risk_value),
        "margin_leakage_sar": _float(margin_leakage_value),
        "recoverable_value_low_sar": _float(recoverable_low),
        "recoverable_value_high_sar": _float(recoverable_high),
        "expected_recovery_sar": _float(calibrated_expected) if calibrated_expected > 0 else None,
        "recovery_confidence": "MEDIUM" if calibrated_expected > 0 else overall_conf,
        "money_approved_sar": 0.0,
        "money_recovered_sar": 0.0,
        "confidence_score": _float(data_confidence),
        "data_quality_score": quality.get("score", 0),
        "quality": quality,
        "business_type": business_type,
        "limited_analysis": limited_analysis,
        "classifications": classifications,
        "action_count": len(actions),
        "evidence_count": evidence_count,
        "headline_note": "Financial measures are intentionally separated. Revenue/profit at risk are not cash recovered.",
        "generated_at": utcnow().isoformat(),
    }
    if limited_analysis:
        summary["vertical_note"] = "Limited product-level analysis. Recipe/ingredient profitability and wastage are not asserted without recipe data."
    return AuditComputation(summary=summary, actions=actions, missing_data=quality.get("warnings", []))


def _json_default(value: Any):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)


async def generate_money_audit(db: AsyncSession, business_id: UUID | str, generated_by: UUID | str | None = None) -> dict[str, Any]:
    business_id_str = str(business_id)
    computation = await compute_money_audit(db, business_id_str)
    summary = computation.summary

    # DB expects date objects, but summary JSON uses ISO strings.
    period_start = summary.get("period_start")
    period_end = summary.get("period_end")
    if isinstance(period_start, str):
        period_start = date.fromisoformat(period_start)
    if isinstance(period_end, str):
        period_end = date.fromisoformat(period_end)

    audit_result = await db.execute(
        text("""
            INSERT INTO money_audits
                (id, business_id, generated_by, status, period_start, period_end,
                 money_at_risk_sar, dead_stock_value_sar, stockout_risk_value_sar, margin_leakage_sar,
                 overstock_value_sar, inventory_value_sar, capital_at_risk_sar, revenue_at_risk_sar,
                 gross_profit_at_risk_sar, recoverable_value_low_sar, recoverable_value_high_sar, expected_recovery_sar,
                 financial_model_version, recovery_confidence, evidence_summary,
                 money_approved_sar, money_recovered_sar, confidence_score, data_quality_score, missing_data, summary, created_at, updated_at)
            VALUES
                (gen_random_uuid(), :business_id, :generated_by, 'generated', :period_start, :period_end,
                 :money_at_risk_sar, :dead_stock_value_sar, :stockout_risk_value_sar, :margin_leakage_sar,
                 :overstock_value_sar, :inventory_value_sar, :capital_at_risk_sar, :revenue_at_risk_sar,
                 :gross_profit_at_risk_sar, :recoverable_value_low_sar, :recoverable_value_high_sar, :expected_recovery_sar,
                 'v2', :recovery_confidence, CAST(:evidence_summary AS JSONB),
                 0, 0, :confidence_score, :data_quality_score, CAST(:missing_data AS JSONB), CAST(:summary AS JSONB), NOW(), NOW())
            RETURNING id
        """),
        {
            "business_id": business_id_str,
            "generated_by": str(generated_by) if generated_by else None,
            "period_start": period_start,
            "period_end": period_end,
            "money_at_risk_sar": summary["money_at_risk_sar"],
            "dead_stock_value_sar": summary["dead_stock_value_sar"],
            "stockout_risk_value_sar": summary["stockout_risk_value_sar"],
            "margin_leakage_sar": summary["margin_leakage_sar"],
            "overstock_value_sar": summary["overstock_value_sar"],
            "revenue_at_risk_sar": summary["revenue_at_risk_sar"],
            "gross_profit_at_risk_sar": summary["gross_profit_at_risk_sar"],
            "inventory_value_sar": summary["inventory_value_sar"],
            "capital_at_risk_sar": summary["capital_at_risk_sar"],
            "recoverable_value_low_sar": summary["recoverable_value_low_sar"],
            "recoverable_value_high_sar": summary["recoverable_value_high_sar"],
            "expected_recovery_sar": summary["expected_recovery_sar"],
            "recovery_confidence": summary["recovery_confidence"],
            "evidence_summary": json.dumps({"evidence_count": summary["evidence_count"], "business_type": summary["business_type"]}),
            "confidence_score": summary["confidence_score"],
            "data_quality_score": summary["data_quality_score"],
            "missing_data": json.dumps(computation.missing_data, default=_json_default),
            "summary": json.dumps(summary, default=_json_default),
        },
    )
    audit_id = str(audit_result.fetchone()[0])

    for action in computation.actions:
        await db.execute(
            text("""
                INSERT INTO money_audit_actions
                    (id, audit_id, business_id, item_id, action_type, priority, title, description,
                     expected_recovery_sar, recoverable_value_low_sar, recoverable_value_high_sar, expected_recovery_sar_v2,
                     recovery_confidence, financial_model, quantity, recommended_discount_pct, status, evidence, created_at, updated_at)
                VALUES
                    (gen_random_uuid(), :audit_id, :business_id, :item_id, :action_type, :priority, :title, :description,
                     :legacy_expected, :recoverable_low, :recoverable_high, :expected_recovery,
                     :recovery_confidence, CAST(:financial_model AS JSONB), :quantity, :recommended_discount_pct, 'suggested', CAST(:evidence AS JSONB), NOW(), NOW())
            """),
            {
                "audit_id": audit_id,
                "business_id": business_id_str,
                "item_id": action.get("item_id"),
                "action_type": action["action_type"],
                "priority": action.get("priority", 3),
                "title": action["title"],
                "description": action.get("description"),
                # Legacy amount is deliberately zero when no observed calibration exists.
                "legacy_expected": _float(action.get("expected_recovery_sar")) if action.get("expected_recovery_sar") is not None else 0,
                "recoverable_low": _float(action.get("recoverable_value_low_sar")) if action.get("recoverable_value_low_sar") is not None else 0,
                "recoverable_high": _float(action.get("recoverable_value_high_sar")) if action.get("recoverable_value_high_sar") is not None else 0,
                "expected_recovery": _float(action.get("expected_recovery_sar")) if action.get("expected_recovery_sar") is not None else None,
                "recovery_confidence": action.get("recovery_confidence", "INSUFFICIENT DATA"),
                "financial_model": json.dumps(action.get("financial_model") or {}, default=_json_default),
                "quantity": _float(action.get("quantity")) if action.get("quantity") is not None else None,
                "recommended_discount_pct": _float(action.get("recommended_discount_pct")) if action.get("recommended_discount_pct") is not None else None,
                "evidence": json.dumps({**(action.get("evidence") or {}), "reason": action.get("reason")}, default=_json_default),
            },
        )

    await db.commit()
    return await get_money_audit(db, audit_id)


async def _row_to_audit(row: Any, actions: list[dict[str, Any]]) -> dict[str, Any]:
    summary = row.summary or {}
    if isinstance(summary, str):
        try:
            summary = json.loads(summary)
        except Exception:
            summary = {}
    # The stored summary is a generation-time snapshot; action totals are live
    # columns on the audit row. Always reflect the live values in the API so
    # merchants see recovered/approved money that matches their actions.
    summary["money_approved_sar"] = _float(row.money_approved_sar)
    summary["money_recovered_sar"] = _float(row.money_recovered_sar)
    missing_data = row.missing_data or []
    if isinstance(missing_data, str):
        try:
            missing_data = json.loads(missing_data)
        except Exception:
            missing_data = []
    return {
        "id": str(row.id),
        "business_id": str(row.business_id),
        "status": row.status,
        "period_start": row.period_start.isoformat() if row.period_start else None,
        "period_end": row.period_end.isoformat() if row.period_end else None,
        "money_at_risk_sar": _float(row.money_at_risk_sar),
        "inventory_value_sar": _float(row.inventory_value_sar),
        "capital_at_risk_sar": _float(row.capital_at_risk_sar),
        "revenue_at_risk_sar": _float(row.revenue_at_risk_sar),
        "gross_profit_at_risk_sar": _float(row.gross_profit_at_risk_sar),
        "recoverable_value_low_sar": _float(row.recoverable_value_low_sar),
        "recoverable_value_high_sar": _float(row.recoverable_value_high_sar),
        "expected_recovery_sar": _float(row.expected_recovery_sar) if row.expected_recovery_sar is not None else None,
        "recovery_confidence": row.recovery_confidence,
        "financial_model_version": row.financial_model_version,
        "dead_stock_value_sar": _float(row.dead_stock_value_sar),
        "stockout_risk_value_sar": _float(row.stockout_risk_value_sar),
        "margin_leakage_sar": _float(row.margin_leakage_sar),
        "overstock_value_sar": _float(row.overstock_value_sar),
        "money_approved_sar": _float(row.money_approved_sar),
        "money_recovered_sar": _float(row.money_recovered_sar),
        "confidence_score": _float(row.confidence_score),
        "data_quality_score": _float(row.data_quality_score),
        "missing_data": missing_data,
        "summary": summary,
        "actions": actions,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


async def get_money_audit(db: AsyncSession, audit_id: UUID | str) -> dict[str, Any]:
    audit_res = await db.execute(text("SELECT * FROM money_audits WHERE id = :id"), {"id": str(audit_id)})
    audit = audit_res.fetchone()
    if not audit:
        raise ValueError("Money Audit not found")
    actions = await list_money_audit_actions(db, str(audit.id))
    return await _row_to_audit(audit, actions)


async def get_latest_money_audit(db: AsyncSession, business_id: UUID | str) -> dict[str, Any] | None:
    from app.database.connection import enforce_tenant_filter
    enforce_tenant_filter(str(business_id))

    result = await db.execute(
        text("""
            SELECT * FROM money_audits
            WHERE business_id = :business_id
            ORDER BY created_at DESC
            LIMIT 1
        """),
        {"business_id": str(business_id)},
    )
    row = result.fetchone()
    if not row:
        return None
    actions = await list_money_audit_actions(db, str(row.id))
    return await _row_to_audit(row, actions)


async def list_money_audit_actions(db: AsyncSession, audit_id: UUID | str) -> list[dict[str, Any]]:
    result = await db.execute(
        text("""
            SELECT a.*, i.name AS item_name, i.sku, i.barcode
            FROM money_audit_actions a
            LEFT JOIN items i ON i.id = a.item_id
            WHERE a.audit_id = :audit_id
            ORDER BY a.priority ASC, a.expected_recovery_sar DESC, a.created_at ASC
        """),
        {"audit_id": str(audit_id)},
    )
    actions = []
    for row in result.fetchall():
        evidence = row.evidence or {}
        if isinstance(evidence, str):
            try:
                evidence = json.loads(evidence)
            except Exception:
                evidence = {}
        actions.append({
            "id": str(row.id),
            "audit_id": str(row.audit_id),
            "business_id": str(row.business_id),
            "item_id": str(row.item_id) if row.item_id else None,
            "item_name": row.item_name,
            "sku": row.sku,
            "barcode": row.barcode,
            "action_type": row.action_type,
            "priority": row.priority,
            "title": row.title,
            "description": row.description,
            "expected_recovery_sar": _float(row.expected_recovery_sar_v2) if row.expected_recovery_sar_v2 is not None else None,
            "recoverable_value_low_sar": _float(row.recoverable_value_low_sar) if row.recoverable_value_low_sar is not None else 0,
            "recoverable_value_high_sar": _float(row.recoverable_value_high_sar) if row.recoverable_value_high_sar is not None else 0,
            "recovery_confidence": row.recovery_confidence,
            "financial_model": row.financial_model or {},
            "quantity": _float(row.quantity) if row.quantity is not None else None,
            "recommended_discount_pct": _float(row.recommended_discount_pct) if row.recommended_discount_pct is not None else None,
            "status": row.status,
            "approval_channel": row.approval_channel,
            "completed_value_sar": _float(row.completed_value_sar) if row.completed_value_sar is not None else None,
            "notes": row.notes,
            "evidence": evidence,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        })
    return actions


async def _recalculate_audit_totals(db: AsyncSession, audit_id: str) -> None:
    await db.execute(
        text("""
            WITH totals AS (
                SELECT
                    COALESCE(SUM(expected_recovery_sar) FILTER (WHERE status IN ('approved', 'completed')), 0) AS approved,
                    COALESCE(SUM(COALESCE(completed_value_sar, expected_recovery_sar)) FILTER (WHERE status = 'completed'), 0) AS recovered
                FROM money_audit_actions
                WHERE audit_id = :audit_id
            )
            UPDATE money_audits ma
            SET money_approved_sar = t.approved,
                money_recovered_sar = t.recovered,
                summary = jsonb_set(
                    jsonb_set(
                        COALESCE(ma.summary, '{}')::jsonb,
                        '{money_approved_sar}',
                        to_jsonb(t.approved)
                    ),
                    '{money_recovered_sar}',
                    to_jsonb(t.recovered)
                ),
                updated_at = NOW()
            FROM totals t
            WHERE ma.id = :audit_id
        """),
        {"audit_id": audit_id},
    )


async def update_action_status(
    db: AsyncSession,
    action_id: UUID | str,
    business_id: UUID | str,
    status: str,
    notes: str | None = None,
    completed_value_sar: float | None = None,
    approval_channel: str = "dashboard",
) -> dict[str, Any]:
    if status not in {"approved", "rejected", "completed"}:
        raise ValueError("Invalid action status")
    if status == "completed" and completed_value_sar is None:
        raise ValueError("Measured actual recovery is required before an action can be marked completed")

    result = await db.execute(
        text("SELECT id, audit_id, status AS current_status FROM money_audit_actions WHERE id = :id AND business_id = :business_id"),
        {"id": str(action_id), "business_id": str(business_id)},
    )
    action = result.fetchone()
    if not action:
        raise ValueError("Money Audit action not found")

    # §9 Approval Safety: enforce valid lifecycle transitions.
    # Valid: suggested → approved | rejected; approved → completed | rejected
    # Invalid: approve twice, reject rejected, complete unapproved, etc.
    VALID_TRANSITIONS = {
        "approved": {"suggested"},
        "rejected": {"suggested", "approved"},
        "completed": {"approved"},
    }
    allowed_from = VALID_TRANSITIONS.get(status, set())
    if action.current_status not in allowed_from:
        raise ValueError(
            f"Cannot transition from '{action.current_status}' to '{status}'. "
            f"Allowed transitions from '{action.current_status}': "
            f"{[s for s, froms in VALID_TRANSITIONS.items() if action.current_status in froms] or 'none (terminal state)'}"
        )

    timestamp_col = {
        "approved": "approved_at",
        "rejected": "rejected_at",
        "completed": "completed_at",
    }[status]

    completed_value_sql = "completed_value_sar = :completed_value_sar," if status == "completed" else ""
    prediction_sql = "prediction_error_pct = CASE WHEN expected_recovery_sar_v2 > 0 THEN ((:completed_value_sar - expected_recovery_sar_v2) / expected_recovery_sar_v2) * 100 ELSE NULL END, measurement_window_days = COALESCE(measurement_window_days, 30)," if status == "completed" else ""
    await db.execute(
        text(f"""
            UPDATE money_audit_actions
            SET status = :status,
                approval_channel = :approval_channel,
                {timestamp_col} = NOW(),
                {completed_value_sql}
                {prediction_sql}
                notes = COALESCE(:notes, notes),
                updated_at = NOW()
            WHERE id = :id AND business_id = :business_id
        """),
        {
            "id": str(action_id),
            "business_id": str(business_id),
            "status": status,
            "approval_channel": approval_channel,
            "completed_value_sar": completed_value_sar,
            "notes": notes,
        },
    )
    await _recalculate_audit_totals(db, str(action.audit_id))
    await db.commit()
    return await get_money_audit(db, str(action.audit_id))


def whatsapp_summary(audit: dict[str, Any]) -> str:
    top_actions = audit.get("actions", [])[:3]
    lines = [
        "NazmOS Money Audit",
        f"Inventory value: SAR {audit.get('inventory_value_sar', 0):,.0f}",
        f"Capital at risk: SAR {audit.get('capital_at_risk_sar', 0):,.0f}",
        f"Revenue at risk: SAR {audit.get('revenue_at_risk_sar', 0):,.0f}",
        f"Gross profit at risk: SAR {audit.get('gross_profit_at_risk_sar', 0):,.0f}",
        f"Potentially recoverable: SAR {audit.get('recoverable_value_low_sar', 0):,.0f}–{audit.get('recoverable_value_high_sar', 0):,.0f}",
        f"Recovery confidence: {audit.get('recovery_confidence', 'INSUFFICIENT DATA')}",
        "",
        "Top actions:",
    ]
    for idx, action in enumerate(top_actions, start=1):
        expected = action.get('expected_recovery_sar')
        range_text = f"range SAR {action.get('recoverable_value_low_sar', 0):,.0f}–{action.get('recoverable_value_high_sar', 0):,.0f}"
        lines.append(f"{idx}. {action['title']} — {('expected SAR ' + format(expected, ',.0f')) if expected is not None else range_text}; {action.get('recovery_confidence', 'INSUFFICIENT DATA')}")
    if not top_actions:
        lines.append("Upload sales + inventory files to generate actions.")
    lines.append("")
    lines.append("Reply APPROVE to start with action #1, or ask for the full report.")
    return "\n".join(lines)


def printable_html(audit: dict[str, Any]) -> str:
    actions = "".join(
        f"""
        <tr>
          <td>{html.escape(action.get('title') or '')}</td>
          <td>{html.escape(action.get('action_type') or '')}</td>
          <td>{('SAR ' + format(action.get('expected_recovery_sar'), ',.0f')) if action.get('expected_recovery_sar') is not None else ('SAR ' + format(action.get('recoverable_value_low_sar', 0), ',.0f') + '–' + format(action.get('recoverable_value_high_sar', 0), ',.0f'))}</td>
          <td>{html.escape(action.get('status') or '')}</td>
        </tr>
        """
        for action in audit.get("actions", [])
    )
    warnings = "".join(f"<li>{html.escape(w.get('message', ''))}</li>" for w in audit.get("missing_data", []))
    return f"""
<!doctype html>
<html><head><meta charset='utf-8'><title>NazmOS Money Audit</title>
<style>
body{{font-family:Inter,Arial,sans-serif;background:#F4EFE6;color:#0A0E0C;margin:0;padding:32px}}.page{{max-width:900px;margin:0 auto;background:white;border-radius:24px;padding:32px;box-shadow:0 20px 60px rgba(0,0,0,.12)}}h1{{font-family:Georgia,serif;font-size:44px;margin:0}}.kpis{{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin:24px 0}}.kpi{{border:1px solid #ddd;border-radius:16px;padding:16px}}.kpi b{{display:block;font-size:26px;margin-top:6px}}table{{width:100%;border-collapse:collapse;margin-top:18px}}td,th{{border-bottom:1px solid #ddd;text-align:left;padding:12px}}.red{{color:#C8412A}}.gold{{color:#A87B18}}.green{{color:#13A05A}}@media print{{body{{background:white;padding:0}}.page{{box-shadow:none}}}}
</style></head><body><main class='page'>
<p style='letter-spacing:.22em;text-transform:uppercase;color:#A87B18;font-weight:800'>Nazmak · NazmOS</p>
<h1>Free Money Audit</h1>
<p>Generated {html.escape(audit.get('created_at') or '')}. Period: {html.escape(str(audit.get('period_start') or '—'))} to {html.escape(str(audit.get('period_end') or '—'))}.</p>
<div class='kpis'>
<div class='kpi'><span>Capital at Risk</span><b class='red'>SAR {audit.get('capital_at_risk_sar', 0):,.0f}</b></div>
<div class='kpi'><span>Potentially Recoverable</span><b class='gold'>SAR {audit.get('recoverable_value_low_sar', 0):,.0f}–{audit.get('recoverable_value_high_sar', 0):,.0f}</b></div>
<div class='kpi'><span>Money Approved</span><b class='gold'>SAR {audit.get('money_approved_sar', 0):,.0f}</b></div>
<div class='kpi'><span>Money Recovered</span><b class='green'>SAR {audit.get('money_recovered_sar', 0):,.0f}</b></div>
</div>
<div class='kpis'>
<div class='kpi'><span>Inventory Value</span><b>SAR {audit.get('inventory_value_sar', 0):,.0f}</b></div>
<div class='kpi'><span>Revenue at Risk</span><b>SAR {audit.get('revenue_at_risk_sar', 0):,.0f}</b></div>
<div class='kpi'><span>Gross Profit at Risk</span><b>SAR {audit.get('gross_profit_at_risk_sar', 0):,.0f}</b></div>
</div>
<div class='kpis'>
<div class='kpi'><span>Dead Stock</span><b>SAR {audit.get('dead_stock_value_sar', 0):,.0f}</b></div>
<div class='kpi'><span>Stockout Risk</span><b>SAR {audit.get('stockout_risk_value_sar', 0):,.0f}</b></div>
<div class='kpi'><span>Margin Leakage</span><b>SAR {audit.get('margin_leakage_sar', 0):,.0f}</b></div>
</div>
<h2>Top Recovery Actions</h2>
<table><thead><tr><th>Action</th><th>Type</th><th>Expected</th><th>Status</th></tr></thead><tbody>{actions}</tbody></table>
<h2>Data Quality Notes</h2><ul>{warnings or '<li>No major data quality warnings.</li>'}</ul>
</main></body></html>
"""
