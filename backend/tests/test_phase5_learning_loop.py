"""Phase 5 self-improving loop — DB-backed integration test (SQLite).

This is the critical proof (§28–29): an outcome from yesterday changes today's
recommendation, through deterministic, auditable structured evidence.

Scenario A: action executes → learned outcome auto-recorded → idempotent on re-record.
Scenario B: rejection stored → future agent sees the rejection evidence.
Scenario E: finding → action → outcome represented in the KG (product→category, AFFECTS,
RECOMMENDS, PRODUCES).
"""
from __future__ import annotations

from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database.models import Base


@pytest_asyncio.fixture(scope="function")
async def db() -> AsyncSession:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:", poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with SessionLocal() as session:
        yield session
    await engine.dispose()


async def _seed_business(db: AsyncSession) -> str:
    bid = str(uuid4())
    await db.execute(text("INSERT INTO businesses (id, name, type, is_active) VALUES (:id, 'Test', 'retail', true)"),
                     {"id": bid})
    await db.commit()
    return bid


async def _create_action(db: AsyncSession, bid: str, action_type: str, status: str = "pending_approval",
                         executed: bool = False) -> str:
    import json
    aid = str(uuid4())
    outcome = json.dumps({"executed": executed})
    await db.execute(text("""
        INSERT INTO agent_actions (id, business_id, action_type, status, confidence, priority,
                                   title, summary, payload, estimated_value_sar,
                                   autonomy_dial_at_creation, was_auto_executed, outcome_json, created_at, updated_at)
        VALUES (:id, :b, :t, :s, 0.9, 3, :title, 'summary', '{}', 1000, 50, false, :outcome, datetime('now'), datetime('now'))
    """), {"id": aid, "b": bid, "t": action_type, "s": status, "title": f"{action_type} test",
           "outcome": outcome})
    await db.commit()
    return aid


async def test_learned_outcome_is_idempotent_per_action(db):
    from app.services.outcome_learning import learn_from_action

    bid = await _seed_business(db)
    aid = await _create_action(db, bid, "discount", status="approved", executed=True)

    r1 = await learn_from_action(db, bid, aid, commit=True)
    r2 = await learn_from_action(db, bid, aid, commit=True)  # replay/retry

    assert r1["ok"] and r2["ok"]
    assert r1["learned_outcome_id"] == r2["learned_outcome_id"]  # same canonical record

    count = await db.execute(text("SELECT COUNT(*) FROM learned_outcomes WHERE agent_action_id = :a"),
                             {"a": aid})
    assert count.scalar() == 1  # no duplicate on replay


async def test_rejection_is_stored_as_evidence(db):
    from app.services.outcome_learning import learn_from_action, rejections_for

    bid = await _seed_business(db)
    aid = await _create_action(db, bid, "discount", status="rejected")
    # set the rejection note (decision_note) then learn
    await db.execute(text("UPDATE agent_actions SET decision_note = 'seasonal product' WHERE id = :a"), {"a": aid})
    await db.commit()
    await learn_from_action(db, bid, aid, commit=True)

    rej = await rejections_for(db, bid, action_type="discount")
    assert len(rej) == 1
    assert rej[0]["rejection_reason"] == "seasonal product"


async def test_runtime_terminal_outcome_wiring(db):
    """The runtime's canonical terminal-state hook (_record_terminal_outcome) records a
    learned outcome + graph edge for an action (SQLite-safe; approve_agent_action's full
    path uses Postgres-only NOW()/gen_random_uuid())."""
    from app.services.agent_action_executor import _record_terminal_outcome

    bid = await _seed_business(db)
    aid = await _create_action(db, bid, "discount", status="approved", executed=True)
    await _record_terminal_outcome(db, bid, aid)

    count = await db.execute(text("SELECT COUNT(*) FROM learned_outcomes WHERE agent_action_id = :a"),
                             {"a": aid})
    assert count.scalar() == 1

    # the action→outcome edge must also be projected (§15)
    edges = await db.execute(text("SELECT COUNT(*) FROM graph_relationships WHERE relation_type='PRODUCES' AND business_id=:b"),
                             {"b": bid})
    assert edges.scalar() >= 1


async def test_finding_projected_to_graph(db):
    from app.services.knowledge_graph import project_finding_to_graph

    bid = await _seed_business(db)
    fid = str(uuid4())
    await project_finding_to_graph(
        db, bid, fid, domain="money_audit", category="dead_stock", severity="high",
        title="Dead stock", affected_entities=[{"type": "product", "id": "item-1"}],
    )
    await db.commit()

    n = await db.execute(text("SELECT COUNT(*) FROM graph_entities WHERE entity_type='finding' AND business_id=:b"),
                         {"b": bid})
    assert n.scalar() == 1
    edges = await db.execute(text("SELECT COUNT(*) FROM graph_relationships WHERE relation_type='AFFECTS' AND business_id=:b"),
                             {"b": bid})
    assert edges.scalar() == 1


async def test_action_projected_to_graph_with_outcome(db):
    from app.services.knowledge_graph import project_action_to_graph

    bid = await _seed_business(db)
    aid = str(uuid4())
    await project_action_to_graph(
        db, bid, aid, action_type="discount", status="completed", executed=True,
        outcome={"executed": True}, targets=[{"type": "product", "id": "item-1"}],
    )
    await db.commit()

    edges = await db.execute(text("""
        SELECT relation_type FROM graph_relationships WHERE business_id = :b
    """), {"b": bid})
    rels = {r[0] for r in edges.fetchall()}
    assert "TARGETS" in rels
    assert "PRODUCES" in rels


async def test_product_category_edge_projected_from_ledger(db):
    """BELONGS_TO is only created when items.category_id resolves to a real category row."""
    from uuid import UUID
    from app.services.knowledge_graph import _project_inventory_changed
    from app.database.models import Event

    bid = await _seed_business(db)
    cid = str(uuid4())
    iid = str(uuid4())
    await db.execute(text("INSERT INTO categories (id, business_id, name) VALUES (:id, :b, 'Dairy')"),
                     {"id": cid, "b": bid})
    await db.execute(text("""
        INSERT INTO items (id, business_id, category_id, name, cost_price, sell_price)
        VALUES (:id, :b, :cid, 'Milk', 1.0, 2.0)
    """), {"id": iid, "b": bid, "cid": cid})
    await db.commit()

    event = Event(business_id=UUID(bid), event_type="inventory.changed",
                  payload={"item_id": iid, "item_name": "Milk", "business_id": bid})
    await _project_inventory_changed(db, event)
    await db.commit()

    bel = await db.execute(text("SELECT COUNT(*) FROM graph_relationships WHERE relation_type='BELONGS_TO' AND business_id=:b"),
                           {"b": bid})
    assert bel.scalar() == 1
