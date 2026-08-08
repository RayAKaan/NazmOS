"""Robust item resolution for POS/e-commerce webhook adapters.

Maps incoming order line items to the merchant's canonical item catalog using
barcode (best), SKU (good), then fuzzy name matching (fallback). All matching
is case-insensitive and trimmed to handle messy POS exports.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def resolve_item(
    db: AsyncSession,
    business_id: UUID | str,
    name: str,
    sku: str | None = None,
    barcode: str | None = None,
) -> dict[str, Any] | None:
    """Return the best-matching item dict for an incoming line item.

    Matching priority:
      1. barcode (exact, trimmed, case-insensitive)
      2. sku (exact, trimmed, case-insensitive)
      3. name starts-with match (case-insensitive)
      4. name contains match on first 10 chars (legacy fallback)
    """
    bid = str(business_id)
    clean_name = (name or "").strip()
    clean_sku = (sku or "").strip()
    clean_barcode = (barcode or "").strip()

    # 1. Barcode match
    if clean_barcode:
        result = await db.execute(
            text("""
                SELECT id, name, sku, barcode, cost_price, sell_price
                FROM items
                WHERE business_id = :b
                  AND LOWER(TRIM(barcode)) = LOWER(:barcode)
                LIMIT 1
            """),
            {"b": bid, "barcode": clean_barcode},
        )
        row = result.mappings().fetchone()
        if row:
            return dict(row)

    # 2. SKU match
    if clean_sku:
        result = await db.execute(
            text("""
                SELECT id, name, sku, barcode, cost_price, sell_price
                FROM items
                WHERE business_id = :b
                  AND LOWER(TRIM(sku)) = LOWER(:sku)
                LIMIT 1
            """),
            {"b": bid, "sku": clean_sku},
        )
        row = result.mappings().fetchone()
        if row:
            return dict(row)

    # 3. Name starts-with (e.g., "Almarai Milk 1L" matches "Almarai Milk")
    if clean_name:
        result = await db.execute(
            text("""
                SELECT id, name, sku, barcode, cost_price, sell_price
                FROM items
                WHERE business_id = :b
                  AND LOWER(name) LIKE LOWER(:prefix)
                ORDER BY LENGTH(name) ASC
                LIMIT 1
            """),
            {"b": bid, "prefix": f"{clean_name[:40]}%"},
        )
        row = result.mappings().fetchone()
        if row:
            return dict(row)

    # 4. Legacy fuzzy contains on first 10 chars
    if clean_name:
        result = await db.execute(
            text("""
                SELECT id, name, sku, barcode, cost_price, sell_price
                FROM items
                WHERE business_id = :b
                  AND LOWER(name) LIKE LOWER(:name)
                ORDER BY LENGTH(name) ASC
                LIMIT 1
            """),
            {"b": bid, "name": f"%{clean_name[:10]}%"},
        )
        row = result.mappings().fetchone()
        if row:
            return dict(row)

    return None
