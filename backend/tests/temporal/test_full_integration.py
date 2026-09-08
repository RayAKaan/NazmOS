"""End-to-end Temporal execution over the real Postgres-backed app engine.

This is the CI-grade suite: it exercises the agent path (pending approval →
executed → learning) whose persistence needs Postgres-only SQL
(``CAST(... AS JSON)``, ``CAST(... AS UUID)``), plus tenant isolation and the
at-execution constraint block with its durable ``constraint_blocks`` record.
Every execution flows through the REAL pipeline: runner → Temporal server →
the production worker → the canonical services → Postgres.

Each test starts from a clean table state (see conftest truncate).
"""
from __future__ import annotations

import json
import os
import uuid

import pytest
from sqlalchemy import text

from app.orchestration.runner import run_agent_approval, run_manual_action, run_simulated
from tests.temporal.helpers import (
    executed_count,
    run_restock,
    seed_business_and_item,
    seed_owner,
    stock_of,
)

pytestmark = [
    pytest.mark.skipif(
        not (os.environ.get("DATABASE_URL") or "postgresql+asyncpg://nazmos:nazmos_dev@localhost:5432/nazmos").startswith(
            "postgresql"
        ),
        reason=(
            "Postgres-backed Temporal integration: point DATABASE_URL at a real "
            "Postgres test database (set TEST_DATABASE_URL / DATABASE_URL)."
        ),
    ),
    pytest.mark.asyncio(loop_scope="session"),
]


async def _seed_agent_action(db, business_id: str, item_id: str, status: str = "pending_approval") -> str:
    action_id = str(uuid.uuid4())
    await db.execute(
        text(
            """
            INSERT INTO agent_actions
                (id, business_id, action_type, status, confidence, priority, title, summary,
                 payload, autonomy_dial_at_creation, was_auto_executed)
            VALUES
                (:id, :b, 'restock', :status, 0.9, 3, 'Restock Milk 1L', 'Agent-proposed restock',
                 :payload, 100, false)
            """
        ),
        {
            "id": action_id,
            "b": business_id,
            "status": status,
            "payload": json.dumps({"item_id": item_id, "quantity": 15}),
        },
    )
    return action_id


async def _purchase_orders(db, business_id: str) -> int:
    return (
        await db.execute(text("SELECT COUNT(*) FROM purchase_orders WHERE business_id=:b"), {"b": business_id})
    ).scalar()


async def _agent_status(db, action_id: str) -> str:
    return (
        await db.execute(text("SELECT status FROM agent_actions WHERE id=:id"), {"id": action_id})
    ).scalar()


# ── Manual path ───────────────────────────────────────────────────────


async def test_manual_restock_end_to_end_postgres(db):
    bid, iid = await seed_business_and_item(db)
    uid = await seed_owner(db, bid)
    await db.commit()

    res = await run_restock(db, bid, iid, uid)

    assert res.success is True and res.action_id is not None
    assert await stock_of(db, bid, iid) == 75.0
    assert await executed_count(db, bid) == 1


async def test_manual_restock_replay_short_circuits(db):
    bid, iid = await seed_business_and_item(db)
    uid = await seed_owner(db, bid)
    await db.commit()

    first = await run_restock(db, bid, iid, uid)
    second = await run_restock(db, bid, iid, uid)

    assert first.success is True
    assert second.success is True
    assert "replayed" in (second.message or "").lower()
    assert await stock_of(db, bid, iid) == 75.0
    assert await executed_count(db, bid) == 1


async def test_manual_capability_denied_blocks_before_any_mutation(db):
    bid, iid = await seed_business_and_item(db)
    await db.commit()

    res = await run_restock(db, bid, iid, str(uuid.uuid4()))
    assert res.success is False
    assert res.error == "INSUFFICIENT_CAPABILITY"
    assert await stock_of(db, bid, iid) == 50.0
    assert await executed_count(db, bid) == 0


async def test_tenant_isolation_two_businesses(db):
    bid_a, iid_a = await seed_business_and_item(db, "Tenant A")
    bid_b, iid_b = await seed_business_and_item(db, "Tenant B")
    uid_a = await seed_owner(db, bid_a)
    uid_b = await seed_owner(db, bid_b)
    await db.commit()

    await run_restock(db, bid_a, iid_a, uid_a)

    assert await stock_of(db, bid_a, iid_a) == 75.0
    assert await stock_of(db, bid_b, iid_b) == 50.0
    assert await executed_count(db, bid_a) == 1
    assert await executed_count(db, bid_b) == 0


async def test_at_execution_constraint_block_is_durable_and_recorded(db):
    """A reorder whose item is not found in this business is blocked at the
    final guard; the block is durably recorded to constraint_blocks."""
    bid, _ = await seed_business_and_item(db)
    uid = await seed_owner(db, bid)
    foreign_item = str(uuid.uuid4())
    await db.commit()

    res = await run_manual_action(
        db,
        business_id=uuid.UUID(bid),
        action_type="RESTOCK",
        entity_type="item",
        entity_id=uuid.UUID(foreign_item),
        payload={"restock_qty": 10},
        new_state={"restock_qty": 10},
        user_id=uuid.UUID(uid),
    )

    assert res.success is False
    assert res.error == "GUARD_ITEM_NOT_FOUND"
    assert await executed_count(db, bid) == 0
    blocks = (
        await db.execute(
            text("SELECT reason_code FROM constraint_blocks WHERE business_id=:b"),
            {"b": bid},
        )
    ).scalars().all()
    assert "GUARD_ITEM_NOT_FOUND" in blocks


# ── Agent path ────────────────────────────────────────────────────────


async def test_agent_approval_restock_end_to_end(db):
    bid, iid = await seed_business_and_item(db)
    uid = await seed_owner(db, bid)
    action_id = await _seed_agent_action(db, bid, iid)
    await db.commit()

    res = await run_agent_approval(db, action_id=action_id, business_id=bid, decided_by=uid)

    assert res["ok"] is True
    assert await _agent_status(db, action_id) == "executed"
    assert await _purchase_orders(db, bid) == 1


async def test_agent_approval_stale_never_executes_p0b(db):
    """A stale/raced approval (action already transitioned) is refused and no
    apply ever runs — P0-B race defense through the durable substrate."""
    bid, iid = await seed_business_and_item(db)
    uid = await seed_owner(db, bid)
    action_id = await _seed_agent_action(db, bid, iid, status="executing")
    await db.commit()

    res = await run_agent_approval(db, action_id=action_id, business_id=bid, decided_by=uid)

    assert res["ok"] is False
    assert "not pending approval" in res["reason"]
    assert await _agent_status(db, action_id) == "executing"
    assert await _purchase_orders(db, bid) == 0


async def test_agent_approval_requires_capability(db):
    bid, iid = await seed_business_and_item(db)
    action_id = await _seed_agent_action(db, bid, iid)
    await db.commit()

    res = await run_agent_approval(
        db, action_id=action_id, business_id=bid, decided_by=str(uuid.uuid4())
    )

    assert res["ok"] is False
    assert "capability" in res["reason"]
    assert await _agent_status(db, action_id) == "pending_approval"
    assert await _purchase_orders(db, bid) == 0


# ── Simulated path ────────────────────────────────────────────────────


async def test_simulated_execution_postgres_is_non_mutating(db):
    bid, iid = await seed_business_and_item(db)
    await db.commit()

    res = await run_simulated(
        db,
        business_id=uuid.UUID(bid),
        action_type="FORECAST",
        entity_type="inventory",
        entity_id=uuid.UUID(iid),
        payload={"horizon_days": 7},
    )

    assert (getattr(res, "status", None) or "") in ("completed", "pending")
    assert await executed_count(db, bid) == 0
    assert await stock_of(db, bid, iid) == 50.0
    jobs = (
        await db.execute(text("SELECT COUNT(*) FROM execution_jobs WHERE business_id=:b"), {"b": bid})
    ).scalar()
    assert jobs == 1