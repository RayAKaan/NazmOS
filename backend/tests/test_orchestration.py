"""Orchestration contract tests (Phase 1 Temporal replacement).

These tests pin the NEW canonical execution layer (`app.orchestration`):

  * execution-key derivation is deterministic and intent-sensitive
  * the manual action workflow is idempotent — a replayed key never
    double-applies a business mutation
  * capability revalidation runs BEFORE any side effect
  * the owner-constraint guard re-runs at execution time and blocks
  * simulated executions never mutate business data (ADR §7 two-path
    invariant), while the real path does

SQLite-based tests are DB-free and run in CI; the Postgres-backed test
uses the standard `db_session` fixture and is skipped when Postgres is
unavailable.
"""
from __future__ import annotations

import json
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database.models import Base
from app.orchestration.keys import derive_execution_key
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
            "name": "Orchestration Test Biz",
            "constraints": json.dumps(constraints or {}),
            "owner_id": str(owner_id) if owner_id else None,
        },
    )


async def _seed_item(db: AsyncSession, business_id, item_id, *, stock=20.0, cost=10, sell=20):
    await db.execute(
        text(
            "INSERT INTO items (id, business_id, name, sku, unit, cost_price, sell_price, is_active) "
            "VALUES (:id, :b, 'Widget', 'ORC1', 'piece', :cost, :sell, true)"
        ),
        {"id": str(item_id), "b": str(business_id), "cost": cost, "sell": sell},
    )
    await db.execute(
        text(
            "INSERT INTO inventory (id, item_id, business_id, current_stock, safety_stock, lead_time_days, updated_at) "
            "VALUES (X'A1B2C3D4A1B2C3D4A1B2C3D4A1B2C3D4', :iid, :b, :stock, 5, 7, CURRENT_TIMESTAMP)"
        ),
        {"iid": str(item_id), "b": str(business_id), "stock": stock},
    )


async def _seed_user(db: AsyncSession, user_id, email_suffix):
    await db.execute(
        text(
            "INSERT INTO users (id, email, password_hash, full_name, role, is_active) "
            "VALUES (:id, :email, 'hash', 'User', 'staff', true)"
        ),
        {"id": str(user_id), "email": f"orchestration_{email_suffix}@example.com"},
    )


async def _stock(db: AsyncSession, item_id) -> float:
    res = await db.execute(
        text("SELECT current_stock FROM inventory WHERE item_id = :i"),
        {"i": str(item_id)},
    )
    return float(res.scalar_one())


@pytest_asyncio.fixture(scope="function")
async def sqlite_session() -> AsyncSession:
    """In-memory SQLite session (DB-free: runs without Postgres)."""
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


# ── Execution-key derivation (pure, deterministic) ───────────────────


@pytest.mark.asyncio
async def test_execution_key_is_deterministic_and_intent_sensitive():
    bid, eid = uuid.uuid4(), uuid.uuid4()
    base = dict(
        business_id=bid,
        action_type="RESTOCK",
        entity_type="item",
        entity_id=eid,
        payload={"restock_qty": 50.0},
    )
    k1 = derive_execution_key(**base, source="money_audit")
    k2 = derive_execution_key(**base, source="money_audit")
    assert k1 == k2, "identical intent must derive an identical execution key"
    assert len(k1) == 64

    k3 = derive_execution_key(**base, source="simulated")
    assert k3 != k1, "source must be part of the key (simulated vs real diverge)"

    k4 = derive_execution_key(
        business_id=bid, action_type="RESTOCK", entity_type="item", entity_id=eid,
        payload={"restock_qty": 30.0}, source="money_audit",
    )
    assert k4 != k1, "different payload must derive a different key"

    k5 = derive_execution_key(business_id=eid, action_type="RESTOCK", entity_type="item",
                              entity_id=bid, payload={"restock_qty": 50.0}, source="money_audit")
    assert k5 != k1, "different business/entity ids must derive a different key"


# ── Manual path: determinism = idempotent replay, never double-apply ─

@pytest.mark.asyncio
async def test_manual_restock_replay_never_double_applies(sqlite_session: AsyncSession):
    biz, item = uuid.uuid4(), uuid.uuid4()
    await _seed_business(sqlite_session, biz)
    await _seed_item(sqlite_session, biz, item, stock=20.0)
    await sqlite_session.commit()

    kwargs = dict(
        business_id=biz,
        action_type="RESTOCK",
        entity_type="item",
        entity_id=item,
        previous_state={"current_stock": 20.0},
        new_state={"restock_qty": 50.0},
        user_id=None,
        source="money_audit",
    )

    first = await run_manual_action(sqlite_session, **kwargs)
    assert first.success is True, first.message
    await sqlite_session.commit()

    # Deterministic double-run: same inputs → same result (No-op replay).
    second = await run_manual_action(sqlite_session, **kwargs)
    await sqlite_session.commit()

    assert await _stock(sqlite_session, item) == 70.0, "stock must increment exactly once"
    assert second.success is True

    count = (await sqlite_session.execute(
        text("SELECT count(*) FROM executed_actions WHERE business_id = :b"),
        {"b": str(biz)},
    )).scalar_one()
    assert count == 1, "one execution_key must map to exactly one executed_actions row"


@pytest.mark.asyncio
async def test_manual_workflow_records_execution_key(sqlite_session: AsyncSession):
    biz, item = uuid.uuid4(), uuid.uuid4()
    await _seed_business(sqlite_session, biz)
    await _seed_item(sqlite_session, biz, item, stock=20.0)
    await sqlite_session.commit()

    prev, new = {"current_stock": 20.0}, {"restock_qty": 25.0}
    result = await run_manual_action(
        sqlite_session,
        business_id=biz,
        action_type="RESTOCK",
        entity_type="item",
        entity_id=item,
        previous_state=prev,
        new_state=new,
        user_id=None,
        source="money_audit",
    )
    await sqlite_session.commit()
    assert result.success is True

    key = derive_execution_key(biz, "RESTOCK", "item", item, new, "money_audit")
    row = (await sqlite_session.execute(
        text("SELECT execution_key, status FROM executed_actions WHERE business_id = :b"),
        {"b": str(biz)},
    )).fetchone()
    assert row.status == "completed"
    assert row.execution_key == key


@pytest.mark.asyncio
async def test_distinct_intents_derive_distinct_keys_and_both_apply(sqlite_session: AsyncSession):
    """Different payloads are distinct executions, not replays."""
    biz, item = uuid.uuid4(), uuid.uuid4()
    await _seed_business(sqlite_session, biz)
    await _seed_item(sqlite_session, biz, item, stock=20.0)
    await sqlite_session.commit()

    for qty in (50.0, 30.0):
        r = await run_manual_action(
            sqlite_session,
            business_id=biz,
            action_type="RESTOCK",
            entity_type="item",
            entity_id=item,
            previous_state={"current_stock": 20.0},
            new_state={"restock_qty": qty},
            user_id=None,
            source="money_audit",
        )
        assert r.success is True, r.message
        await sqlite_session.commit()

    assert await _stock(sqlite_session, item) == 100.0, "20 + 50 + 30 = 100"


# ── Revalidation before side effect ──────────────────────────────────


@pytest.mark.asyncio
async def test_capability_revalidation_blocks_without_mutation(sqlite_session: AsyncSession):
    """A user with no ownership/membership must be refused BEFORE any apply."""
    biz, item, user = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    await _seed_business(sqlite_session, biz, owner_id=uuid.uuid4())
    await _seed_item(sqlite_session, biz, item, stock=20.0)
    await _seed_user(sqlite_session, user, "outsider")
    await sqlite_session.commit()

    result = await run_manual_action(
        sqlite_session,
        business_id=biz,
        action_type="RESTOCK",
        entity_type="item",
        entity_id=item,
        previous_state={"current_stock": 20.0},
        new_state={"restock_qty": 50.0},
        user_id=user,
        source="money_audit",
    )
    await sqlite_session.commit()

    assert result.success is False
    assert result.error == "INSUFFICIENT_CAPABILITY"
    assert await _stock(sqlite_session, item) == 20.0, "no mutation when revalidation fails"


@pytest.mark.asyncio
async def test_owner_capability_allows_execution(sqlite_session: AsyncSession):
    biz, item, owner = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    await _seed_business(sqlite_session, biz, owner_id=owner)
    await _seed_item(sqlite_session, biz, item, stock=20.0)
    await _seed_user(sqlite_session, owner, "owner")
    await sqlite_session.commit()

    result = await run_manual_action(
        sqlite_session,
        business_id=biz,
        action_type="RESTOCK",
        entity_type="item",
        entity_id=item,
        previous_state={"current_stock": 20.0},
        new_state={"restock_qty": 50.0},
        user_id=owner,
        source="money_audit",
    )
    await sqlite_session.commit()

    assert result.success is True, result.message
    assert await _stock(sqlite_session, item) == 70.0


@pytest.mark.asyncio
async def test_constraint_guard_blocks_excess_restock(sqlite_session: AsyncSession):
    """Owner cash-budget constraint must re-block at execution time."""
    biz, item = uuid.uuid4(), uuid.uuid4()
    await _seed_business(sqlite_session, biz, constraints={"cash_budget": 1000})
    await _seed_item(sqlite_session, biz, item, stock=10.0, cost=100, sell=200)
    await sqlite_session.commit()

    result = await run_manual_action(
        sqlite_session,
        business_id=biz,
        action_type="RESTOCK",
        entity_type="item",
        entity_id=item,
        previous_state={"current_stock": 10.0},
        new_state={"current_stock": 110.0},  # qty 100 × cost 100 = 10000 > 1000
        user_id=None,
        source="money_audit",
    )
    await sqlite_session.commit()

    assert result.success is False, "blocked restock must not succeed"
    assert await _stock(sqlite_session, item) == 10.0, "inventory must not mutate when the guard blocks"


# ── ADR §7: simulated vs real mutation boundary ──────────────────────


@pytest.mark.asyncio
async def test_simulated_path_never_mutates_business_data(sqlite_session: AsyncSession):
    biz, item = uuid.uuid4(), uuid.uuid4()
    await _seed_business(sqlite_session, biz)
    await _seed_item(sqlite_session, biz, item, stock=20.0)
    await sqlite_session.commit()

    result = await run_simulated(
        sqlite_session,
        business_id=biz,
        action_type="restock",
        entity_type="item",
        entity_id=item,
        payload={"quantity": 100},
    )
    await sqlite_session.commit()

    assert result is not None
    job_id = result.id

    status = (await sqlite_session.execute(
        text("SELECT status FROM execution_jobs WHERE id = :jid"),
        {"jid": str(job_id)},
    )).scalar_one()
    assert status == "completed"

    assert await _stock(sqlite_session, item) == 20.0, "simulated exec must NOT touch inventory"


@pytest.mark.asyncio
async def test_simulated_versus_real_boundary(sqlite_session: AsyncSession):
    """The same intent executed simulated leaves data untouched; real mutates."""
    biz, item = uuid.uuid4(), uuid.uuid4()
    await _seed_business(sqlite_session, biz)
    await _seed_item(sqlite_session, biz, item, stock=20.0)
    await sqlite_session.commit()

    await run_simulated(
        sqlite_session,
        business_id=biz,
        action_type="restock",
        entity_type="item",
        entity_id=item,
        payload={"quantity": 100},
    )
    await sqlite_session.commit()

    jobs = (await sqlite_session.execute(
        text("SELECT count(*) FROM execution_jobs WHERE business_id = :b"),
        {"b": str(biz)},
    )).scalar_one()
    assert jobs == 1

    result = await run_manual_action(
        sqlite_session,
        business_id=biz,
        action_type="RESTOCK",
        entity_type="item",
        entity_id=item,
        previous_state={"current_stock": 20.0},
        new_state={"restock_qty": 50.0},
        user_id=None,
        source="money_audit",
    )
    await sqlite_session.commit()

    assert result.success is True, result.message
    assert await _stock(sqlite_session, item) == 70.0, "real path must apply the mutation"

    jobs_after = (await sqlite_session.execute(
        text("SELECT count(*) FROM execution_jobs WHERE business_id = :b"),
        {"b": str(biz)},
    )).scalar_one()
    assert jobs_after == 1, "simulated and real paths must not cross-contaminate tracking rows"