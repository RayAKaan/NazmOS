"""Failure-mode tests for the orchestration layer (Temporal retry semantics).

These tests run against the real ``app.database.models.Base`` schema on an
in-memory SQLite engine (DB-free: runs in CI without Postgres) and drive the
same canonical workflow code that the local deterministic runner
(``USE_TEMPORAL=False``) and the Temporal server (``USE_TEMPORAL=True``) both
execute.

Each test proves a concrete invariant rather than merely exercising a path:

  * an activity retry re-entering a completed execution is effectively-once
    (stock 50 -> 75 -> 75, never 50 -> 100)
  * a duplicate request derives the same execution_key and replays the prior
    outcome without re-applying
  * a durable completed record short-circuits apply even in a fresh session
  * simulated executions never mutate business data (ADR §7 two-path invariant)
  * tenant A's execution cannot touch tenant B's inventory
  * a stale approval is re-validated against CURRENT state at apply time and
    blocks with zero side effects (P0-B final-execution guard)
"""

from __future__ import annotations

import json
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database.models import Base, ExecutedAction, AgentAction
from app.orchestration.apply import apply_agent_action
from app.orchestration.keys import derive_execution_key
from app.orchestration.record import record_agent_approval
from app.orchestration.runner import run_manual_action, run_simulated


# ── Helpers ──────────────────────────────────────────────────────────


async def _seed_business(db: AsyncSession, business_id, *, owner_id=None, constraints=None):
    await db.execute(
        text(
            "INSERT INTO businesses (id, name, type, currency, constraints_json, owner_id) "
            "VALUES (:id, :name, 'retail', 'SAR', :constraints, :owner_id)"
        ),
        {
            "id": str(business_id),
            "name": "Failure Test Biz",
            "constraints": json.dumps(constraints or {}),
            "owner_id": str(owner_id) if owner_id else None,
        },
    )


async def _seed_item(db: AsyncSession, business_id, item_id, *, stock=20.0, cost=10, sell=20):
    await db.execute(
        text(
            "INSERT INTO items (id, business_id, name, sku, unit, cost_price, sell_price, is_active) "
            "VALUES (:id, :b, 'Widget', 'FLR1', 'piece', :cost, :sell, true)"
        ),
        {"id": str(item_id), "b": str(business_id), "cost": cost, "sell": sell},
    )
    inventory_id = uuid.uuid5(uuid.NAMESPACE_URL, f"inventory|{item_id}")
    await db.execute(
        text(
            "INSERT INTO inventory (id, item_id, business_id, current_stock, safety_stock, lead_time_days, updated_at) "
            "VALUES (:inv, :iid, :b, :stock, 5, 7, CURRENT_TIMESTAMP)"
        ),
        {"inv": str(inventory_id), "iid": str(item_id), "b": str(business_id), "stock": stock},
    )


async def _seed_agent_action(
    db: AsyncSession,
    business_id,
    action_id,
    item_id,
    *,
    action_type="restock",
    payload=None,
    status="pending_approval",
):
    action = AgentAction(
        id=action_id,
        business_id=business_id,
        action_type=action_type,
        status=status,
        confidence=0.9,
        autonomy_dial_at_creation=50,
        title="Restock test action",
        summary="Stale approval test",
        payload=payload or {},
    )
    db.add(action)
    await db.flush()
    return action.id


async def _stock(db: AsyncSession, item_id) -> float:
    res = await db.execute(
        text("SELECT current_stock FROM inventory WHERE item_id = :i"),
        {"i": str(item_id)},
    )
    return float(res.scalar_one())


async def _executed_count(db: AsyncSession, business_id) -> int:
    res = await db.execute(
        text("SELECT count(*) FROM executed_actions WHERE business_id = :b"),
        {"b": str(business_id)},
    )
    return int(res.scalar_one())


@pytest_asyncio.fixture(scope="function")
async def sqlite_session() -> AsyncSession:
    """In-memory SQLite session over the real Base.metadata schema."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with SessionLocal() as session:
        yield session
    await engine.dispose()


def _manual_kwargs(business_id, item_id, qty, *, source="money_audit"):
    payload = {"restock_qty": float(qty)}
    return dict(
        business_id=business_id,
        action_type="RESTOCK",
        entity_type="item",
        entity_id=item_id,
        payload=payload,
        previous_state={"current_stock": 50.0},
        new_state=dict(payload),
        user_id=None,
        source=source,
    )


# ── Retry: effectively-once under Temporal-style activity retry ──────


@pytest.mark.asyncio
async def test_activity_retry_transient_failure(sqlite_session: AsyncSession):
    """A retried activity re-enters the workflow; idempotency prevents a
    second mutation — stock 50 -> 75 -> 75, never 50 -> 100."""
    biz, item = uuid.uuid4(), uuid.uuid4()
    await _seed_business(sqlite_session, biz)
    await _seed_item(sqlite_session, biz, item, stock=50.0)
    await sqlite_session.commit()

    kwargs = _manual_kwargs(biz, item, 25.0)

    first = await run_manual_action(sqlite_session, **kwargs)
    await sqlite_session.commit()
    assert first.success is True, first.message
    assert await _stock(sqlite_session, item) == 75.0

    retry = await run_manual_action(sqlite_session, **kwargs)
    await sqlite_session.commit()
    assert retry.success is True, retry.message
    assert await _stock(sqlite_session, item) == 75.0, "retry must NOT re-apply the mutation"
    assert await _executed_count(sqlite_session, biz) == 1


# ── Duplicate request: same key, replay, single side effect ──────────


@pytest.mark.asyncio
async def test_duplicate_request_same_execution_key(sqlite_session: AsyncSession):
    """Two identical requests derive the same key; the second replays the
    prior outcome with no additional business mutation."""
    biz, item = uuid.uuid4(), uuid.uuid4()
    await _seed_business(sqlite_session, biz)
    await _seed_item(sqlite_session, biz, item, stock=50.0)
    await sqlite_session.commit()

    kwargs = _manual_kwargs(biz, item, 25.0)
    key = derive_execution_key(
        biz, "RESTOCK", "item", item, {"restock_qty": 25.0}, "money_audit"
    )

    first = await run_manual_action(sqlite_session, **kwargs)
    await sqlite_session.commit()
    assert first.success is True, first.message

    second = await run_manual_action(sqlite_session, **kwargs)
    await sqlite_session.commit()
    assert second.success is True, second.message
    assert "already executed" in second.message, "duplicate must return a replay outcome"
    assert await _stock(sqlite_session, item) == 75.0

    stored = (await sqlite_session.execute(
        text("SELECT execution_key FROM executed_actions WHERE business_id = :b"),
        {"b": str(biz)},
    )).scalar_one()
    assert stored == key, "stored execution_key must match the derived key"
    assert await _executed_count(sqlite_session, biz) == 1


# ── Durable terminal record short-circuits a fresh session ───────────


@pytest.mark.asyncio
async def test_already_executed_no_second_mutation(sqlite_session: AsyncSession):
    """A durable completed row for the key (created by a prior worker/session)
    short-circuits apply: the fresh execution replays and mutates nothing."""
    biz, item = uuid.uuid4(), uuid.uuid4()
    await _seed_business(sqlite_session, biz)
    await _seed_item(sqlite_session, biz, item, stock=50.0)
    await sqlite_session.commit()

    key = derive_execution_key(
        biz, "RESTOCK", "item", item, {"restock_qty": 25.0}, "money_audit"
    )
    sqlite_session.add(ExecutedAction(
        business_id=biz,
        source="money_audit",
        action_type="RESTOCK",
        entity_type="item",
        entity_id=item,
        previous_state={"current_stock": 50.0},
        new_state={"restock_qty": 25.0},
        status="completed",
        execution_key=key,
    ))
    await sqlite_session.commit()

    result = await run_manual_action(sqlite_session, **_manual_kwargs(biz, item, 25.0))
    await sqlite_session.commit()
    assert result.success is True, result.message
    assert "already executed" in result.message
    assert await _stock(sqlite_session, item) == 50.0, "no apply when a terminal record exists"
    assert await _executed_count(sqlite_session, biz) == 1


# ── Simulated path: ADR §7 two-path invariant ────────────────────────


@pytest.mark.asyncio
async def test_simulated_no_business_mutation(sqlite_session: AsyncSession):
    """The simulated path records an ExecutionJob but never mutates inventory."""
    biz, item = uuid.uuid4(), uuid.uuid4()
    await _seed_business(sqlite_session, biz)
    await _seed_item(sqlite_session, biz, item, stock=20.0)
    await sqlite_session.commit()

    job = await run_simulated(
        sqlite_session,
        business_id=biz,
        action_type="restock",
        entity_type="item",
        entity_id=item,
        payload={"quantity": 100},
    )
    await sqlite_session.commit()

    status = (await sqlite_session.execute(
        text("SELECT status FROM execution_jobs WHERE id = :jid"),
        {"jid": str(job.id)},
    )).scalar_one()
    assert status == "completed"

    jobs = (await sqlite_session.execute(
        text("SELECT count(*) FROM execution_jobs WHERE business_id = :b"),
        {"b": str(biz)},
    )).scalar_one()
    assert jobs == 1
    assert await _stock(sqlite_session, item) == 20.0, "simulated exec must NOT touch inventory"


# ── Tenant isolation: cross-tenant mutation is impossible ────────────


@pytest.mark.asyncio
async def test_tenant_isolation_no_cross_tenant(sqlite_session: AsyncSession):
    """Each tenant's execution affects only its own inventory and rows."""
    biz_a, biz_b = uuid.uuid4(), uuid.uuid4()
    item_a, item_b = uuid.uuid4(), uuid.uuid4()
    await _seed_business(sqlite_session, biz_a)
    await _seed_item(sqlite_session, biz_a, item_a, stock=50.0)
    await _seed_business(sqlite_session, biz_b)
    await _seed_item(sqlite_session, biz_b, item_b, stock=80.0)
    await sqlite_session.commit()

    r_a = await run_manual_action(sqlite_session, **_manual_kwargs(biz_a, item_a, 25.0))
    await sqlite_session.commit()
    r_b = await run_manual_action(sqlite_session, **_manual_kwargs(biz_b, item_b, 30.0))
    await sqlite_session.commit()
    assert r_a.success and r_b.success

    assert await _stock(sqlite_session, item_a) == 75.0
    assert await _stock(sqlite_session, item_b) == 110.0
    assert await _executed_count(sqlite_session, biz_a) == 1
    assert await _executed_count(sqlite_session, biz_b) == 1

    a_keys = (await sqlite_session.execute(
        text("SELECT execution_key FROM executed_actions WHERE business_id = :b"),
        {"b": str(biz_a)},
    )).scalars().all()
    b_keys = (await sqlite_session.execute(
        text("SELECT execution_key FROM executed_actions WHERE business_id = :b"),
        {"b": str(biz_b)},
    )).scalars().all()
    assert a_keys and b_keys
    assert all(k not in b_keys for k in a_keys), "execution keys must be tenant-scoped"


# ── Stale approval: revalidation against CURRENT state at apply ──────


@pytest.mark.asyncio
async def test_stale_approval_blocks_execution(sqlite_session: AsyncSession):
    """An approval targets an entity that disappears before the apply activity
    runs. The final-execution guard re-reads CURRENT state at apply time and
    blocks with zero side effects (P0-B stale-state defense)."""
    biz, item, aid = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    await _seed_business(sqlite_session, biz)
    await _seed_item(sqlite_session, biz, item, stock=10.0, cost=100, sell=200)
    payload = {"item_id": str(item), "quantity": 5}
    await _seed_agent_action(sqlite_session, biz, aid, item, payload=payload)
    await sqlite_session.commit()

    approval = await record_agent_approval(
        sqlite_session,
        action_id=aid,
        business_id=biz,
        note="Approved",
        decided_by=None,
    )
    assert approval.get("ok") is True, approval
    await sqlite_session.commit()

    await sqlite_session.execute(
        text("DELETE FROM inventory WHERE item_id = :i"),
        {"i": str(item)},
    )
    await sqlite_session.execute(
        text("DELETE FROM items WHERE id = :i"),
        {"i": str(item)},
    )
    await sqlite_session.commit()

    outcome = await apply_agent_action(sqlite_session, biz, aid, "restock", payload)
    await sqlite_session.commit()

    assert outcome.get("executed") is False, outcome
    assert outcome.get("reason_code") == "GUARD_ITEM_NOT_FOUND", outcome

    remaining = (await sqlite_session.execute(
        text("SELECT count(*) FROM items WHERE id = :i"),
        {"i": str(item)},
    )).scalar_one()
    assert remaining == 0, "stale approval must not resurrect or mutate the entity"

    status = (await sqlite_session.execute(
        text("SELECT status FROM agent_actions WHERE id = :aid"),
        {"aid": str(aid)},
    )).scalar_one()
    assert status == "approved", "no terminal status may be recorded for a blocked apply"