"""Synthetic merchant fixtures (Phase 12, §Part 5).

Deterministic, clearly-SYNTHETIC test/demo datasets. NOT real Saudi merchant data. Each
fixture seeds a business with items, categories, inventory, transactions, suppliers, and
supplier prices so audits/root-cause/strategy tests have realistic internal relationships.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def seed_category(db: AsyncSession, business_id: str, name: str) -> str:
    cid = str(uuid.uuid4())
    await db.execute(text("INSERT INTO categories (id, business_id, name) VALUES (:id, :b, :n)"),
                     {"id": cid, "b": business_id, "n": name})
    return cid


async def seed_item(db: AsyncSession, business_id: str, name: str, category_id: str | None,
                    cost: float, sell: float, sku: str | None = None) -> str:
    iid = str(uuid.uuid4())
    await db.execute(text("""
        INSERT INTO items (id, business_id, category_id, name, cost_price, sell_price, sku, is_active)
        VALUES (:id, :b, :cid, :n, :cost, :sell, :sku, true)
    """), {"id": iid, "b": business_id, "cid": category_id, "n": name, "cost": cost, "sell": sell, "sku": sku})
    return iid


async def seed_inventory(db: AsyncSession, business_id: str, item_id: str, stock: float,
                         reorder_level: float = 10, lead_time_days: int = 3, safety_stock: float = 2) -> str:
    inv_id = str(uuid.uuid4())
    await db.execute(text("""
        INSERT INTO inventory (id, business_id, item_id, current_stock, reorder_level, lead_time_days, safety_stock, updated_at)
        VALUES (:id, :b, :i, :stock, :ro, :lt, :ss, :now)
    """), {"id": inv_id, "b": business_id, "i": item_id, "stock": stock, "ro": reorder_level,
           "lt": lead_time_days, "ss": safety_stock, "now": _now()})
    return inv_id


async def seed_transactions(db: AsyncSession, business_id: str, item_id: str, qty: float,
                            at: datetime) -> None:
    await db.execute(text("""
        INSERT INTO transactions (id, business_id, item_id, quantity, unit_price, cost_price,
                                  total_amount, profit, transaction_type, transaction_at)
        VALUES (:id, :b, :i, :q, 10, 2, :total, :profit, 'sale', :at)
    """), {"id": str(uuid.uuid4()), "b": business_id, "i": item_id, "q": qty,
           "total": qty * 10.0, "profit": qty * 8.0, "at": at})


async def seed_supplier(db: AsyncSession, name: str) -> str:
    sid = str(uuid.uuid4())
    await db.execute(text("INSERT INTO suppliers (id, name_ar, name_en, is_active, is_verified) VALUES (:id, :n, :n, true, true)"),
                     {"id": sid, "n": name})
    return sid


async def seed_supplier_price(db: AsyncSession, supplier_id: str, item_id: str, price: float,
                              at: datetime, business_id: str | None = None) -> None:
    await db.execute(text("""
        INSERT INTO supplier_prices (id, supplier_id, item_id, unit_price_sar, currency, effective_from, source, is_active, business_id, created_at)
        VALUES (:id, :sid, :iid, :p, 'SAR', :eff, 'fixture', true, :b, :at)
    """), {"id": str(uuid.uuid4()), "sid": supplier_id, "iid": item_id, "p": price,
           "eff": at.date(), "b": business_id, "at": at})


async def seed_business(db: AsyncSession, name: str) -> str:
    bid = str(uuid.uuid4())
    await db.execute(text("INSERT INTO businesses (id, name, type, is_active) VALUES (:id, :n, 'retail', true)"),
                     {"id": bid, "n": name})
    return bid


# ── Scenario fixtures ──────────────────────────────────────────────────────

async def seed_recurring_stockout_merchant(db: AsyncSession) -> dict[str, Any]:
    """A merchant whose 'Milk' item has recurring stockouts: velocity high, reorder level
    too low, long lead time."""
    bid = await seed_business(db, "Recurring Stockout Baqala")
    dairy = await seed_category(db, bid, "Dairy")
    milk = await seed_item(db, bid, "Fresh Milk 1L", dairy, cost=1.0, sell=3.0, sku="MILK-1L")
    # velocity ~10/day, reorder level 10, lead time 6d → reorder threshold too low (supported)
    await seed_inventory(db, bid, milk, stock=3.0, reorder_level=10, lead_time_days=6, safety_stock=2)
    # seed ~30 days of sales at 10/day so velocity ≈ 10
    for d in range(30):
        await seed_transactions(db, bid, milk, 10.0, _now() - timedelta(days=d))
    await db.commit()
    return {"business_id": bid, "item_id": milk, "category_id": dairy}


async def seed_margin_leakage_merchant(db: AsyncSession) -> dict[str, Any]:
    """A merchant whose margin is compressed by a supplier cost increase."""
    bid = await seed_business(db, "Margin Leakage Café")
    cat = await seed_category(db, bid, "Coffee")
    item = await seed_item(db, bid, "Coffee Beans 250g", cat, cost=20.0, sell=24.0, sku="COFFEE-250")
    await seed_inventory(db, bid, item, stock=50.0)
    sup = await seed_supplier(db, "Demo Coffee Distributor")
    # two price observations: cost went from 16 → 22 (+37.5%)
    await seed_supplier_price(db, sup, item, 16.0, _now() - timedelta(days=60), bid)
    await seed_supplier_price(db, sup, item, 22.0, _now() - timedelta(days=2), bid)
    await db.commit()
    return {"business_id": bid, "item_id": item, "category_id": cat, "supplier_id": sup}


async def seed_successful_transfer_merchant(db: AsyncSession) -> dict[str, Any]:
    """A merchant with many historically-successful transfer outcomes (for strategy tests)."""
    bid = await seed_business(db, "Transfer-Success Supermarket")
    cat = await seed_category(db, bid, "Groceries")
    item = await seed_item(db, bid, "Rice 5kg", cat, cost=10.0, sell=18.0, sku="RICE-5")
    await seed_inventory(db, bid, item, stock=100.0)
    await db.commit()
    return {"business_id": bid, "item_id": item, "category_id": cat}


async def seed_cash_pressure_merchant(db: AsyncSession) -> dict[str, Any]:
    """A merchant with cash trapped in slow-moving inventory (for cash root-cause tests)."""
    bid = await seed_business(db, "Cash-Pressure Store")
    cat = await seed_category(db, bid, "Home")
    items = []
    for i in range(6):
        item = await seed_item(db, bid, f"Slow Item {i}", cat, cost=2000.0, sell=2800.0, sku=f"SLOW-{i}")
        await seed_inventory(db, bid, item, stock=10.0)  # no recent sales → slow conversion
        items.append(item)
    await db.commit()
    return {"business_id": bid, "category_id": cat, "items": items}


async def seed_pharmacy_merchant(db: AsyncSession) -> dict[str, Any]:
    """A pharmacy with a near-expiry lot (for compliance root-cause reminder tests)."""
    from datetime import timedelta
    bid = await seed_business(db, "Demo Pharmacy")
    cat = await seed_category(db, bid, "Medication")
    item = await seed_item(db, bid, "Paracetamol", cat, cost=2.0, sell=6.0, sku="PARA-500")
    await seed_inventory(db, bid, item, stock=40.0)
    # near-expiry lot (20 days out)
    lot_id = str(uuid.uuid4())
    await db.execute(text("""
        INSERT INTO pharmacy_lots (id, business_id, item_id, batch_number, expiry_date, quantity)
        VALUES (:id, :b, :i, 'LOT-001', :exp, 40)
    """), {"id": lot_id, "b": bid, "i": item, "exp": (_now() + timedelta(days=20)).date()})
    await db.commit()
    return {"business_id": bid, "item_id": item, "category_id": cat, "lot_id": lot_id}


async def seed_stale_merchant(db: AsyncSession) -> dict[str, Any]:
    """A merchant whose inventory/sales timestamps are old (for freshness tests)."""
    from datetime import timedelta
    bid = await seed_business(db, "Stale-Data Merchant")
    cat = await seed_category(db, bid, "Groceries")
    item = await seed_item(db, bid, "Tea", cat, cost=5.0, sell=12.0, sku="TEA-1")
    # inventory updated 200 hours ago (> 96h fresh threshold)
    old = _now() - timedelta(hours=200)
    await db.execute(text("""
        INSERT INTO inventory (id, business_id, item_id, current_stock, reorder_level, lead_time_days, safety_stock, updated_at)
        VALUES (:id, :b, :i, 50, 10, 3, 2, :at)
    """), {"id": str(uuid.uuid4()), "b": bid, "i": item, "at": old})
    await db.commit()
    return {"business_id": bid, "item_id": item, "category_id": cat}
