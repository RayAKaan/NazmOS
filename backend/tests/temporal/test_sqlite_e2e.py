"""End-to-end Temporal execution over the app engine.

This file proves REAL end-to-end execution — runner → Temporal server → the
production worker → the canonical apply/record services → the database. It runs
against any engine: a file-based sqlite DB on a developer machine WITHOUT
Postgres or Docker, or the real Postgres engine in CI where the whole
``tests/temporal`` suite runs with zero skips. (Agent/intelligence paths need
Postgres-only SQL and are covered by test_full_integration.py.)

Run it like this:
    cd backend
    $env:DATABASE_URL="sqlite+aiosqlite:///./nazmos_temporal_test.db"
    $env:USE_TEMPORAL="true"
    python -m pytest tests/temporal/test_sqlite_e2e.py -q
"""
from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import text

from app.orchestration.runner import run_manual_action, run_simulated

pytestmark = [
    pytest.mark.skipif(
        not (os.environ.get("DATABASE_URL") or "").startswith(("sqlite", "postgresql")),
        reason=(
            "engine-backed Temporal E2E: set DATABASE_URL to a sqlite+aiosqlite "
            "file (local) or the Postgres test database (CI)."
        ),
    ),
    pytest.mark.asyncio(loop_scope="session"),
]


async def _seed_owner(db, business_id: str) -> str:
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


async def _business_and_item(db) -> tuple[str, str]:
    from tests.fixtures.merchants import seed_business, seed_category, seed_item, seed_inventory

    bid = await seed_business(db, "Temporal E2E Baqala")
    cat = await seed_category(db, bid, "Dairy")
    iid = await seed_item(db, bid, "Milk 1L", cat, cost=1.0, sell=3.0, sku="E2E-MILK")
    await seed_inventory(db, bid, iid, stock=50.0)
    await db.commit()
    return bid, iid


async def _stock(db, business_id: str, item_id: str) -> float:
    row = (
        await db.execute(
            text("SELECT current_stock FROM inventory WHERE business_id=:b AND item_id=:i"),
            {"b": business_id, "i": item_id},
        )
    ).fetchone()
    assert row is not None
    return float(row.current_stock)


async def _executed_count(db, business_id: str) -> int:
    return (
        await db.execute(
            text("SELECT COUNT(*) FROM executed_actions WHERE business_id=:b"),
            {"b": business_id},
        )
    ).scalar()


async def test_manual_restock_end_to_end(db):
    bid, iid = await _business_and_item(db)
    uid = await _seed_owner(db, bid)
    await db.commit()

    res = await run_manual_action(
        db,
        business_id=uuid.UUID(bid),
        action_type="RESTOCK",
        entity_type="item",
        entity_id=uuid.UUID(iid),
        payload={"restock_qty": 25},
        new_state={"restock_qty": 25},
        user_id=uuid.UUID(uid),
    )

    assert res.success is True
    assert res.action_id is not None
    assert await _stock(db, bid, iid) == 75.0
    assert await _executed_count(db, bid) == 1


async def test_manual_restock_capability_denied_never_mutates(db):
    bid, iid = await _business_and_item(db)
    await db.commit()

    res = await run_manual_action(
        db,
        business_id=uuid.UUID(bid),
        action_type="RESTOCK",
        entity_type="item",
        entity_id=uuid.UUID(iid),
        payload={"restock_qty": 25},
        new_state={"restock_qty": 25},
        user_id=uuid.UUID(str(uuid.uuid4())),
    )

    assert res.success is False
    assert res.error == "INSUFFICIENT_CAPABILITY"
    assert await _stock(db, bid, iid) == 50.0
    assert await _executed_count(db, bid) == 0


async def test_manual_restock_replay_is_exactly_once(db):
    bid, iid = await _business_and_item(db)
    uid = await _seed_owner(db, bid)
    await db.commit()

    kwargs = dict(
        business_id=uuid.UUID(bid),
        action_type="RESTOCK",
        entity_type="item",
        entity_id=uuid.UUID(iid),
        payload={"restock_qty": 25},
        new_state={"restock_qty": 25},
        user_id=uuid.UUID(uid),
    )
    first = await run_manual_action(db, **kwargs)
    second = await run_manual_action(db, **kwargs)

    assert first.success is True
    assert second.success is True
    assert "replayed" in (second.message or "").lower()
    assert await _stock(db, bid, iid) == 75.0  # +25 once, never +50
    assert await _executed_count(db, bid) == 1


async def test_alert_dismiss_records_without_mutation(db):
    bid, _ = await _business_and_item(db)
    uid = await _seed_owner(db, bid)
    await db.commit()

    res = await run_manual_action(
        db,
        business_id=uuid.UUID(bid),
        action_type="ALERT_DISMISS",
        entity_type="decision",
        entity_id=uuid.UUID(str(uuid.uuid4())),
        payload={},
        user_id=uuid.UUID(uid),
    )

    assert res.success is True
    assert res.action_id is not None
    assert await _executed_count(db, bid) == 1
    key = (
        await db.execute(
            text("SELECT execution_key FROM executed_actions WHERE business_id=:b"),
            {"b": bid},
        )
    ).scalar()
    assert key and len(key) == 64


async def test_simulated_execution_never_touches_business_data(db):
    bid, iid = await _business_and_item(db)
    await db.commit()

    res = await run_simulated(
        db,
        business_id=uuid.UUID(bid),
        action_type="FORECAST",
        entity_type="inventory",
        entity_id=uuid.UUID(iid),
        payload={"horizon_days": 7},
    )

    assert getattr(res, "status", None) in ("completed", "pending")
    assert await _executed_count(db, bid) == 0  # no manual execution recorded
    assert await _stock(db, bid, iid) == 50.0   # inventory untouched (ADR §7)
    jobs = (
        await db.execute(text("SELECT COUNT(*) FROM execution_jobs WHERE business_id=:b"), {"b": bid})
    ).scalar()
    assert jobs == 1