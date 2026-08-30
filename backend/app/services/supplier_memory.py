"""Supplier Memory Service — derives structured supplier-level facts from existing data.

Phase 2 §8: Track supplier reliability, lead times, fulfillment behavior.
Only make claims when underlying evidence exists.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, asdict
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.utils.clock import utcnow

logger = logging.getLogger("supplier_memory")

ZERO = Decimal("0")


@dataclass
class SupplierMemory:
    """Structured supplier-level memory. §8 spec."""
    supplier_id: str
    business_id: str
    supplier_name: str
    category: str | None
    city: str | None

    # Lead time
    configured_lead_time_days: int | None
    average_actual_lead_time_days: float | None
    lead_time_variance: float | None

    # Reliability
    total_orders: int
    received_orders: int
    cancelled_orders: int
    overdue_orders: int
    reliability_rate: float | None  # 0-1
    late_order_rate: float | None
    cancellation_rate: float | None
    on_time_rate: float | None

    # Order patterns
    average_order_quantity: float | None
    known_moq_sar: float | None
    last_order_at: str | None
    last_order_status: str | None
    purchase_frequency_days: float | None  # avg days between orders

    # Open purchasing
    open_po_count: int
    confirmed_inbound_qty: float
    overdue_inbound_qty: float
    average_delivery_delay_days: float | None

    # Price intelligence
    items_supplied: int
    last_price_update: str | None
    price_trend: str | None  # INCREASING / STABLE / DECLINING / INSUFFICIENT_DATA

    # Confidence
    confidence: str
    evidence_count: int
    memory_updated_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


async def build_supplier_memory(
    db: AsyncSession,
    business_id: UUID | str,
    supplier_id: UUID | str,
) -> SupplierMemory:
    """Build structured memory for one supplier from existing data. §8 spec."""
    b = str(business_id)
    s = str(supplier_id)
    now = utcnow()

    # ── Supplier profile ────────────────────────────────────────────────
    sup_res = await db.execute(text("""
        SELECT id, name_en, name_ar, category, city, lead_time_days, min_order_sar
        FROM suppliers WHERE id = :s
    """), {"s": s})
    sup = sup_res.fetchone()
    if not sup:
        raise ValueError(f"Supplier {supplier_id} not found")

    # ── PO history ──────────────────────────────────────────────────────
    po_res = await db.execute(text("""
        SELECT
            COUNT(*) AS total,
            COUNT(CASE WHEN status = 'received' THEN 1 END) AS received,
            COUNT(CASE WHEN status = 'cancelled' THEN 1 END) AS cancelled,
            COUNT(CASE WHEN status IN ('sent','confirmed')
                       AND expected_delivery < CURRENT_DATE THEN 1 END) AS overdue,
            AVG(CASE WHEN status = 'received' AND received_at IS NOT NULL
                     THEN EXTRACT(EPOCH FROM (received_at - sent_at)) / 86400.0
                END) AS avg_lead_time,
            AVG(CASE WHEN status = 'received' AND received_at IS NOT NULL AND sent_at IS NOT NULL
                     THEN ABS(EXTRACT(EPOCH FROM (received_at - sent_at)) / 86400.0
                              - COALESCE((SELECT lead_time_days FROM suppliers WHERE id = :s), 7))
                END) AS lead_time_variance,
            AVG(total_sar) AS avg_order_sar,
            MAX(CASE WHEN status IN ('sent','confirmed','received') THEN created_at END) AS last_order_at,
            (SELECT status FROM purchase_orders WHERE supplier_id = :s
             AND status IN ('sent','confirmed','received')
             ORDER BY created_at DESC LIMIT 1) AS last_order_status
        FROM purchase_orders
        WHERE business_id = :b AND supplier_id = :s
    """), {"b": b, "s": s})
    po = po_res.fetchone()

    total = int(po.total or 0) if po else 0
    received = int(po.received or 0) if po else 0
    cancelled = int(po.cancelled or 0) if po else 0
    overdue = int(po.overdue or 0) if po else 0

    # ── Open POs ────────────────────────────────────────────────────────
    open_res = await db.execute(text("""
        SELECT COUNT(*) AS open_count,
               COALESCE(SUM(CAST(elem->>'qty' AS NUMERIC)), 0) AS inbound_qty
        FROM purchase_orders po
        CROSS JOIN LATERAL jsonb_array_elements(CAST(po.items_json AS jsonb)) elem
        WHERE po.business_id = :b AND po.supplier_id = :s
          AND po.status IN ('approved','sent','confirmed','pending_approval')
    """), {"b": b, "s": s})
    open_row = open_res.fetchone()
    open_po_count = int(open_row.open_count or 0) if open_row else 0
    confirmed_inbound = float(open_row.inbound_qty or 0) if open_row else 0

    # ── Overdue inbound ─────────────────────────────────────────────────
    overdue_res = await db.execute(text("""
        SELECT COALESCE(SUM(CAST(elem->>'qty' AS NUMERIC)), 0) AS overdue_qty
        FROM purchase_orders po
        CROSS JOIN LATERAL jsonb_array_elements(CAST(po.items_json AS jsonb)) elem
        WHERE po.business_id = :b AND po.supplier_id = :s
          AND po.status IN ('sent','confirmed')
          AND po.expected_delivery < CURRENT_DATE
    """), {"b": b, "s": s})
    overdue_row = overdue_res.fetchone()
    overdue_inbound = float(overdue_row.overdue_qty or 0) if overdue_row else 0

    # ── Purchase frequency ──────────────────────────────────────────────
    freq_res = await db.execute(text("""
        SELECT AVG(gap_days) AS avg_gap FROM (
            SELECT EXTRACT(EPOCH FROM (
                created_at - LAG(created_at) OVER (ORDER BY created_at)
            )) / 86400.0 AS gap_days
            FROM purchase_orders
            WHERE business_id = :b AND supplier_id = :s
              AND status != 'cancelled'
        ) gaps WHERE gap_days > 0
    """), {"b": b, "s": s})
    freq_row = freq_res.fetchone()
    purchase_frequency = float(freq_row.avg_gap or 0) if freq_row and freq_row.avg_gap else None

    # ── Items supplied ──────────────────────────────────────────────────
    items_res = await db.execute(text("""
        SELECT COUNT(DISTINCT CAST(elem->>'item_id' AS UUID)) AS item_count
        FROM purchase_orders po
        CROSS JOIN LATERAL jsonb_array_elements(CAST(po.items_json AS jsonb)) elem
        WHERE po.business_id = :b AND po.supplier_id = :s
    """), {"b": b, "s": s})
    items_row = items_res.fetchone()
    items_supplied = int(items_row.item_count or 0) if items_row else 0

    # ── Price trend ─────────────────────────────────────────────────────
    price_res = await db.execute(text("""
        SELECT unit_price_sar, effective_from
        FROM supplier_prices
        WHERE supplier_id = :s AND is_active = true
        ORDER BY effective_from DESC
        LIMIT 10
    """), {"s": s})
    price_rows = price_res.fetchall()
    price_trend = None
    last_price_update = None
    if len(price_rows) >= 2:
        prices = [float(r.unit_price_sar or 0) for r in price_rows if r.unit_price_sar]
        if len(prices) >= 2:
            recent = sum(prices[:3]) / min(3, len(prices))
            older = sum(prices[3:]) / max(1, len(prices[3:]))
            if older > 0:
                change = (recent - older) / older
                if change > 0.05:
                    price_trend = "INCREASING"
                elif change < -0.05:
                    price_trend = "DECLINING"
                else:
                    price_trend = "STABLE"
    if price_rows:
        last_price_update = price_rows[0].effective_from.isoformat() if price_rows[0].effective_from else None

    # ── Compute rates ───────────────────────────────────────────────────
    reliability_rate = (received / total) if total > 0 else None
    late_rate = (overdue / total) if total > 0 else None
    cancel_rate = (cancelled / total) if total > 0 else None
    on_time_rate = ((received - overdue) / received) if received > 0 else None

    # Avg delivery delay
    avg_delay = float(po.avg_lead_time or 0) if po and po.avg_lead_time else None

    # ── Confidence ──────────────────────────────────────────────────────
    evidence_count = sum([
        1 if total >= 3 else 0,
        1 if received >= 3 else 0,
        1 if purchase_frequency else 0,
        1 if items_supplied > 0 else 0,
        1 if price_trend else 0,
    ])

    if total >= 10:
        confidence = "HIGH"
    elif total >= 3:
        confidence = "MEDIUM"
    elif total >= 1:
        confidence = "LOW"
    else:
        confidence = "INSUFFICIENT_DATA"

    return SupplierMemory(
        supplier_id=s,
        business_id=b,
        supplier_name=sup.name_en or sup.name_ar or "",
        category=sup.category,
        city=sup.city,
        configured_lead_time_days=sup.lead_time_days,
        average_actual_lead_time_days=round(avg_delay, 1) if avg_delay else None,
        lead_time_variance=round(float(po.lead_time_variance or 0), 2) if po and po.lead_time_variance else None,
        total_orders=total,
        received_orders=received,
        cancelled_orders=cancelled,
        overdue_orders=overdue,
        reliability_rate=round(reliability_rate, 3) if reliability_rate is not None else None,
        late_order_rate=round(late_rate, 3) if late_rate is not None else None,
        cancellation_rate=round(cancel_rate, 3) if cancel_rate is not None else None,
        on_time_rate=round(on_time_rate, 3) if on_time_rate is not None else None,
        average_order_quantity=round(confirmed_inbound / open_po_count, 1) if open_po_count > 0 else None,
        known_moq_sar=float(sup.min_order_sar or 0) if sup.min_order_sar else None,
        last_order_at=po.last_order_at.isoformat() if po and po.last_order_at else None,
        last_order_status=po.last_order_status if po else None,
        purchase_frequency_days=round(purchase_frequency, 1) if purchase_frequency else None,
        open_po_count=open_po_count,
        confirmed_inbound_qty=round(confirmed_inbound, 1),
        overdue_inbound_qty=round(overdue_inbound, 1),
        average_delivery_delay_days=round(avg_delay, 1) if avg_delay else None,
        items_supplied=items_supplied,
        last_price_update=last_price_update,
        price_trend=price_trend,
        confidence=confidence,
        evidence_count=evidence_count,
        memory_updated_at=now.isoformat(),
    )
