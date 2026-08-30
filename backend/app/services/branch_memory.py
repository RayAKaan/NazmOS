"""Branch Memory Service — derives structured branch-level facts.

Phase 2 §10: Branch-level inventory, demand, transfer history.
Multi-branch businesses are modeled as multiple business rows with organization_id.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, asdict
from datetime import date, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.utils.clock import utcnow

logger = logging.getLogger("branch_memory")

ZERO = Decimal("0")


@dataclass
class BranchMemory:
    """Structured branch-level memory. §10 spec."""
    branch_id: str
    business_id: str
    branch_name: str
    location_code: str | None
    is_headquarters: bool

    # Inventory
    total_items: int
    total_stock_value_sar: float
    current_stock: float  # units

    # Demand
    velocity_30d: float
    velocity_7d: float

    # Health
    days_of_supply: float | None
    stockout_frequency: str  # HIGH / MEDIUM / LOW / NONE
    surplus_frequency: str  # HIGH / MEDIUM / LOW / NONE

    # Transfers
    transfers_out_90d: int
    transfers_in_90d: int
    net_transfer_balance: float  # positive = net receiver

    # Priority
    branch_priority: int

    # Confidence
    confidence: str
    evidence_count: int
    memory_updated_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


async def build_branch_memory(
    db: AsyncSession,
    business_id: UUID | str,
    branch_id: UUID | str | None = None,
) -> list[BranchMemory]:
    """Build memory for all branches of a business. §10 spec."""
    b = str(business_id)
    now = utcnow()
    anchor = now.date()

    # Find all branches (businesses in the same organization)
    org_res = await db.execute(text("""
        SELECT b.id, b.name, b.location_code, b.is_headquarters, b.organization_id
        FROM businesses b
        WHERE b.id = :b OR b.organization_id = (
            SELECT organization_id FROM businesses WHERE id = :b
        )
        ORDER BY b.is_headquarters DESC, b.name
    """), {"b": b})
    branches = org_res.fetchall()

    if not branches:
        return []

    # Load branch priorities from constraints
    constraints_res = await db.execute(text("""
        SELECT constraints_json FROM businesses WHERE id = :b
    """), {"b": b})
    constraints_row = constraints_res.fetchone()
    constraints = constraints_row.constraints_json if constraints_row and isinstance(constraints_row.constraints_json, dict) else {}
    branch_priorities = constraints.get("branch_priority", {})

    results = []
    for br in branches:
        br_id = str(br.id)

        # ── Inventory aggregate ────────────────────────────────────────
        inv_res = await db.execute(text("""
            SELECT COUNT(*) AS items, COALESCE(SUM(inv.current_stock), 0) AS total_stock,
                   COALESCE(SUM(inv.current_stock * COALESCE(i.cost_price, 0)), 0) AS stock_value
            FROM inventory inv
            JOIN items i ON i.id = inv.item_id
            WHERE inv.business_id = :br AND i.is_active = true
        """), {"br": br_id})
        inv = inv_res.fetchone()
        total_items = int(inv.items or 0) if inv else 0
        total_stock = float(inv.total_stock or 0) if inv else 0
        stock_value = float(inv.stock_value or 0) if inv else 0

        # ── Velocity ───────────────────────────────────────────────────
        vel_30d = await _branch_velocity(db, br_id, anchor - timedelta(days=30), anchor)
        vel_7d = await _branch_velocity(db, br_id, anchor - timedelta(days=7), anchor)

        # ── Days of supply ─────────────────────────────────────────────
        daily_v = vel_30d / Decimal("30") if vel_30d > 0 else ZERO
        dos = float(total_stock / float(daily_v)) if daily_v > 0 and total_stock > 0 else None

        # ── Stockout frequency ─────────────────────────────────────────
        stockout_res = await db.execute(text("""
            SELECT COUNT(*) AS cnt
            FROM inventory inv
            WHERE inv.business_id = :br
              AND inv.stockout_count_90d > 0
        """), {"br": br_id})
        stockout_row = stockout_res.fetchone()
        so_count = int(stockout_row.cnt or 0) if stockout_row else 0
        so_freq = "HIGH" if so_count >= 5 else ("MEDIUM" if so_count >= 2 else ("LOW" if so_count >= 1 else "NONE"))

        # ── Surplus frequency (overstock items) ────────────────────────
        surplus_res = await db.execute(text("""
            SELECT COUNT(*) AS cnt
            FROM inventory inv
            JOIN items i ON i.id = inv.item_id
            WHERE inv.business_id = :br AND i.is_active = true
              AND inv.current_stock > 0
              AND inv.max_stock > 0
              AND inv.current_stock > inv.max_stock * 1.5
        """), {"br": br_id})
        surplus_row = surplus_res.fetchone()
        surplus_count = int(surplus_row.cnt or 0) if surplus_row else 0
        surplus_freq = "HIGH" if surplus_count >= 5 else ("MEDIUM" if surplus_count >= 2 else ("LOW" if surplus_count >= 1 else "NONE"))

        # ── Transfer history ───────────────────────────────────────────
        transfer_out = await db.execute(text("""
            SELECT COUNT(*) AS cnt FROM transactions
            WHERE business_id = :br AND transaction_type = 'transfer'
              AND transaction_at >= (:anchor)::date - INTERVAL '90 days'
        """), {"br": br_id, "anchor": anchor})
        to_row = transfer_out.fetchone()
        transfers_out = int(to_row.cnt or 0) if to_row else 0

        transfer_in = await db.execute(text("""
            SELECT COUNT(*) AS cnt FROM transactions
            WHERE business_id = :br AND transaction_type = 'transfer'
              AND quantity < 0
              AND transaction_at >= (:anchor)::date - INTERVAL '90 days'
        """), {"br": br_id, "anchor": anchor})
        ti_row = transfer_in.fetchone()
        transfers_in = int(ti_row.cnt or 0) if ti_row else 0

        # ── Priority ───────────────────────────────────────────────────
        priority = int(branch_priorities.get(br_id, 1))

        # ── Confidence ─────────────────────────────────────────────────
        evidence_count = sum([
            1 if total_items > 0 else 0,
            1 if vel_30d > 0 else 0,
            1 if so_count > 0 else 0,
            1 if transfers_out > 0 or transfers_in > 0 else 0,
        ])
        confidence = "HIGH" if evidence_count >= 3 else ("MEDIUM" if evidence_count >= 2 else ("LOW" if evidence_count >= 1 else "INSUFFICIENT_DATA"))

        results.append(BranchMemory(
            branch_id=br_id,
            business_id=b,
            branch_name=br.name or "",
            location_code=br.location_code,
            is_headquarters=bool(br.is_headquarters),
            total_items=total_items,
            total_stock_value_sar=round(stock_value, 2),
            current_stock=round(total_stock, 1),
            velocity_30d=round(float(vel_30d), 1),
            velocity_7d=round(float(vel_7d), 1),
            days_of_supply=round(dos, 1) if dos else None,
            stockout_frequency=so_freq,
            surplus_frequency=surplus_freq,
            transfers_out_90d=transfers_out,
            transfers_in_90d=transfers_in,
            net_transfer_balance=float(transfers_in - transfers_out),
            branch_priority=priority,
            confidence=confidence,
            evidence_count=evidence_count,
            memory_updated_at=now.isoformat(),
        ))

    return results


async def _branch_velocity(db: AsyncSession, branch_id: str, from_date: date, to_date: date) -> Decimal:
    res = await db.execute(text("""
        SELECT COALESCE(SUM(quantity), 0) AS total
        FROM transactions
        WHERE business_id = :b AND transaction_type = 'sale'
          AND transaction_at >= :from_date AND transaction_at < :to_date
    """), {"b": branch_id, "from_date": from_date, "to_date": to_date})
    row = res.fetchone()
    return Decimal(str(row.total or 0)) if row else ZERO
