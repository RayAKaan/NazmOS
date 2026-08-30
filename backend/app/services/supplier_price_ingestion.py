"""Supplier-price ingestion (Phase 3, §4).

Writes real SupplierPrice records from actual data the merchant already uploads
(purchase-order / invoice CSV/XLSX with a supplier + cost/price column) and from
received purchase orders. No prices are fabricated — every record carries its source
and effective date.

Supports two paths:
  1. `ingest_from_etl_rows` — called from the ETL pipeline when a `supplier` column is present.
  2. `ingest_from_purchase_order` — from a received PurchaseOrder's items_json.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("supplier_price_ingestion")


async def _get_or_create_supplier(db: AsyncSession, name: str) -> UUID | None:
    """Resolve a supplier name to a suppliers.id (get-or-create, network-level)."""
    name = (name or "").strip()
    if not name:
        return None
    res = await db.execute(text("SELECT id FROM suppliers WHERE name_en ILIKE :n OR name_ar = :n LIMIT 1"),
                           {"n": f"%{name}%"})
    row = res.fetchone()
    if row:
        return row.id
    import uuid
    sid = uuid.uuid4()
    await db.execute(text("""
        INSERT INTO suppliers (id, name_ar, name_en, is_active, is_verified, created_at)
        VALUES (:id, :n, :n, true, false, :now)
    """), {"id": str(sid), "n": name, "now": datetime.now(timezone.utc)})
    return sid


async def ingest_supplier_price(
    db: AsyncSession,
    business_id: UUID | str,
    *,
    supplier_name: str,
    sku: str | None = None,
    barcode: str | None = None,
    item_id: UUID | str | None = None,
    unit_price_sar: float,
    currency: str = "SAR",
    min_quantity: float | None = None,
    effective_from: date | None = None,
    source: str = "upload",
) -> dict[str, Any]:
    """Insert one SupplierPrice observation. Returns {ok, price_id} or {ok:False, reason}."""
    if unit_price_sar is None or unit_price_sar <= 0:
        return {"ok": False, "reason": "unit_price_sar must be positive"}

    supplier_id = await _get_or_create_supplier(db, supplier_name)
    if supplier_id is None:
        return {"ok": False, "reason": "supplier name required"}

    # Resolve item_id from SKU/barcode if not given.
    if item_id is None:
        if sku:
            res = await db.execute(text("SELECT id FROM items WHERE business_id = :b AND sku = :sku LIMIT 1"),
                                   {"b": str(business_id), "sku": sku})
            row = res.fetchone()
            if row:
                item_id = row.id
        elif barcode:
            res = await db.execute(text("SELECT id FROM items WHERE business_id = :b AND barcode = :barcode LIMIT 1"),
                                   {"b": str(business_id), "barcode": barcode})
            row = res.fetchone()
            if row:
                item_id = row.id

    import uuid
    await db.execute(text("""
        INSERT INTO supplier_prices
            (id, supplier_id, item_id, sku, barcode, unit_price_sar, currency, min_quantity,
             effective_from, source, is_active, business_id, created_at)
        VALUES
            (:id, :sid, :iid, :sku, :barcode, :price, :currency, :moq, :eff, :source, true, :b, :now)
    """), {
        "id": str(uuid.uuid4()),
        "sid": str(supplier_id),
        "iid": str(item_id) if item_id else None,
        "sku": sku,
        "barcode": barcode,
        "price": unit_price_sar,
        "currency": currency,
        "moq": min_quantity,
        "eff": effective_from or datetime.now(timezone.utc).date(),
        "source": source,
        "b": str(business_id),
        "now": datetime.now(timezone.utc),
    })
    return {"ok": True, "supplier_id": str(supplier_id), "item_id": str(item_id) if item_id else None}


async def ingest_from_etl_rows(
    db: AsyncSession,
    business_id: UUID | str,
    rows: list[dict[str, Any]],
    *,
    supplier_col: str = "supplier",
    price_col: str = "cost_price",
    sku_col: str = "sku",
    source: str = "upload",
    commit: bool = False,
) -> dict[str, Any]:
    """Bulk-ingest supplier prices from normalized ETL rows. Only rows with a supplier
    name AND a positive cost/price are used; everything else is skipped."""
    imported = 0
    skipped = 0
    for row in rows:
        supplier = (row.get(supplier_col) or "").strip()
        price = row.get(price_col) or row.get("unit_price") or row.get("purchase_price")
        try:
            price_f = float(price) if price is not None else 0.0
        except (TypeError, ValueError):
            price_f = 0.0
        if not supplier or price_f <= 0:
            skipped += 1
            continue
        result = await ingest_supplier_price(
            db,
            business_id,
            supplier_name=supplier,
            sku=row.get(sku_col),
            item_id=row.get("item_id"),
            unit_price_sar=price_f,
            source=source,
        )
        if result.get("ok"):
            imported += 1
        else:
            skipped += 1
    if commit:
        await db.commit()
    return {"imported": imported, "skipped": skipped}


async def ingest_from_purchase_order(
    db: AsyncSession,
    business_id: UUID | str,
    po_id: UUID | str,
    commit: bool = False,
) -> dict[str, Any]:
    """Ingest supplier prices from a PurchaseOrder (supplier_id + items_json with unit_cost)."""
    import json
    res = await db.execute(text("""
        SELECT supplier_id, items_json FROM purchase_orders WHERE id = :id AND business_id = :b
    """), {"id": str(po_id), "b": str(business_id)})
    row = res.fetchone()
    if not row:
        return {"ok": False, "reason": "purchase order not found"}
    if not row.supplier_id:
        return {"ok": False, "reason": "purchase order has no supplier"}

    supplier = await db.execute(text("SELECT name_en FROM suppliers WHERE id = :id"), {"id": str(row.supplier_id)})
    srow = supplier.fetchone()
    supplier_name = srow.name_en if srow else str(row.supplier_id)

    items = row.items_json if isinstance(row.items_json, list) else json.loads(row.items_json or "[]")
    imported = 0
    for it in items:
        unit_cost = it.get("unit_cost_sar") or it.get("unit_cost")
        try:
            cost = float(unit_cost) if unit_cost is not None else 0.0
        except (TypeError, ValueError):
            cost = 0.0
        if cost <= 0:
            continue
        result = await ingest_supplier_price(
            db, business_id, supplier_name=supplier_name, item_id=it.get("item_id"),
            unit_price_sar=cost, source="purchase_order",
        )
        if result.get("ok"):
            imported += 1
    if commit:
        await db.commit()
    return {"ok": True, "imported": imported}
