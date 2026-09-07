"""Analytical repository — the single entry point for the money-critical KPIs.

Consumers call ``inventory_feed`` (never the engine directly) so every request
that needs per-item velocity, valuation or dead-stock facts goes through one
tenant-scoped DuckDB engine and one provenance record.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.contracts import AnalyticalFeed, ItemFact
from app.analytics.duckdb_engine import ScopedAnalyticalEngine
from app.utils.clock import utcnow


def _fact(row: dict[str, Any]) -> ItemFact:
    return ItemFact(
        item_id=str(row["item_id"]),
        name=str(row["name"] or ""),
        sku=row.get("sku"),
        category_name=row.get("category_name"),
        unit=row.get("unit"),
        current_stock=float(row.get("current_stock") or 0),
        cost_price=float(row.get("cost_price") or 0),
        sell_price=float(row.get("sell_price") or 0),
        reorder_level=float(row.get("reorder_level") or 0),
        last_restocked=row.get("last_restocked"),
        is_active=bool(row.get("is_active", True)),
        qty_30d=float(row.get("qty_30d") or 0),
        qty_7d=float(row.get("qty_7d") or 0),
        qty_prev7d=float(row.get("qty_prev7d") or 0),
        coverage_days_30d=int(row.get("coverage_days_30d") or 0),
        last_sold_at=row.get("last_sold_at"),
    )


async def inventory_feed(
    db: AsyncSession,
    business_id: Any,
    *,
    window_days: int | None = 30,
    anchor: datetime | None = None,
    series_item_ids: tuple[str, ...] = (),
) -> AnalyticalFeed:
    """Build the canonical per-item analytical feed for a business.

    ``window_days=None`` streams the business's full sales history (used by
    the all-time dead-stock scan); the default 30-day window covers every
    velocity/valuation KPI that shares this feed. ``series_item_ids`` requests
    per-item daily sales series from the same engine instance (no double load).
    """
    anchor = anchor or utcnow()
    async with ScopedAnalyticalEngine(
        db, business_id, window_days=window_days, anchor=anchor
    ) as engine:
        rows = engine.inventory_facts_rows()
        provenance = engine.provenance
        series = {
            item_id: engine.item_sales_series(item_id) for item_id in series_item_ids
        }
    return AnalyticalFeed(
        provenance=provenance,
        facts=[_fact(row) for row in rows],
        sales_series=series,
    )


async def item_sales_series(
    db: AsyncSession,
    business_id: Any,
    item_id: Any,
    *,
    window_days: int = 30,
    anchor: datetime | None = None,
) -> list[dict[str, Any]]:
    """Daily per-item sales series from the engine (for item-detail history)."""
    anchor = anchor or utcnow()
    async with ScopedAnalyticalEngine(
        db, business_id, window_days=window_days, anchor=anchor
    ) as engine:
        return engine.item_sales_series(item_id)