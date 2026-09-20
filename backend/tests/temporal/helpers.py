"""Seeding/assertion helpers for the Temporal integration suites."""
from __future__ import annotations

import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.orchestration.runner import run_manual_action
from tests.fixtures.merchants import (
    seed_business,
    seed_category,
    seed_inventory,
    seed_item,
)


async def seed_owner(db: AsyncSession, business_id: str) -> str:
    uid = str(uuid.uuid4())
    await db.execute(
        text("INSERT INTO users (id, email, password_hash, full_name) VALUES (:id, :e, :p, :f)"),
        {"id": uid, "e": f"owner-{uuid.uuid4().hex[:8]}@test.local", "p": "x", "f": "Owner"},
    )
    await db.execute(
        text("UPDATE businesses SET owner_id = :o WHERE id = :b"),
        {"o": uid, "b": business_id},
    )
    return uid


async def seed_business_and_item(
    db: AsyncSession, name: str = "Temporal E2E Baqala", stock: float = 50.0
) -> tuple[str, str]:
    bid = await seed_business(db, name)
    cat = await seed_category(db, bid, "Dairy")
    iid = await seed_item(db, bid, "Milk 1L", cat, cost=1.0, sell=3.0, sku="E2E-MILK")
    await seed_inventory(db, bid, iid, stock=stock)
    await db.commit()
    return bid, iid


async def stock_of(db: AsyncSession, business_id: str, item_id: str) -> float:
    row = (
        await db.execute(
            text("SELECT current_stock FROM inventory WHERE business_id=:b AND item_id=:i"),
            {"b": business_id, "i": item_id},
        )
    ).fetchone()
    assert row is not None
    return float(row.current_stock)


async def executed_count(db: AsyncSession, business_id: str) -> int:
    return (
        await db.execute(
            text("SELECT COUNT(*) FROM executed_actions WHERE business_id=:b"),
            {"b": business_id},
        )
    ).scalar()


async def manual_restock_args(business_id: str, item_id: str, user_id: str | None) -> dict:
    return dict(
        business_id=uuid.UUID(business_id),
        action_type="RESTOCK",
        entity_type="item",
        entity_id=uuid.UUID(item_id),
        payload={"restock_qty": 25},
        new_state={"restock_qty": 25},
        user_id=uuid.UUID(user_id) if user_id else None,
    )


async def run_restock(db: AsyncSession, business_id: str, item_id: str, user_id: str | None):
    args = await manual_restock_args(business_id, item_id, user_id)
    return await run_manual_action(db, **args)