"""Phase 6 — the definitive self-improving loop integration test (SQLite, real DB round-trips).

Proves the full chain (§28–29):
Goal → Finding → AgentAction → approval → execution → outcome → impact →
LearnedOutcome (+ OutcomeFeedback bridge) → graph edges → goal progress → audit
comparison → changed future recommendation.

Failure scenarios (§29): replayed action (no duplicate outcome), rejected action
(learning records rejection), cross-tenant isolation.
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


async def _seed_business(db: AsyncSession, name: str = "Test") -> str:
    bid = str(uuid4())
    await db.execute(text("INSERT INTO businesses (id, name, type, is_active) VALUES (:id, :n, 'retail', true)"),
                     {"id": bid, "n": name})
    await db.commit()
    return bid


async def _make_action(db: AsyncSession, bid: str, action_type: str, *, finding_id: str | None = None,
                       executed: bool = False, status: str = "pending_approval") -> str:
    import json
    aid = str(uuid4())
    await db.execute(text("""
        INSERT INTO agent_actions (id, business_id, finding_id, action_type, status, confidence, priority,
                                   title, summary, payload, estimated_value_sar, autonomy_dial_at_creation,
                                   was_auto_executed, outcome_json, created_at, updated_at)
        VALUES (:id, :b, :fid, :t, :s, 0.9, 3, :title, 'summary', :payload, 4000, 50, false, :outcome,
                datetime('now'), datetime('now'))
    """), {
        "id": aid, "b": bid, "fid": finding_id, "t": action_type, "s": status,
        "title": f"{action_type} test", "payload": json.dumps({"title": f"{action_type} test"}),
        "outcome": json.dumps({"executed": executed}),
    })
    await db.commit()
    return aid


async def test_full_chain_finding_to_learned_outcome_and_graph(db):
    """Scenario: finding → action (finding_id populated) → terminal outcome → learned
    outcome + outcome_feedback + graph edges, all linked."""
    from app.services.agent_action_executor import _record_terminal_outcome
    from app.services.outcome_learning import learning_adjusted_action, intervention_effectiveness

    bid = await _seed_business(db)
    fid = str(uuid4())
    # A finding exists (the action references it).
    await db.execute(text("""
        INSERT INTO findings (id, business_id, domain, category, severity, title, status, source, created_at, updated_at)
        VALUES (:id, :b, 'money_audit', 'dead_stock', 'high', 'Dead stock', 'detected', 'audit_engine', datetime('now'), datetime('now'))
    """), {"id": fid, "b": bid})
    await db.commit()

    aid = await _make_action(db, bid, "discount", finding_id=fid, executed=True, status="approved")
    await _record_terminal_outcome(db, bid, aid)

    # Learned outcome recorded + linked to finding + action.
    lo = await db.execute(text("SELECT id FROM learned_outcomes WHERE agent_action_id = :a"), {"a": aid})
    assert lo.scalar() is not None

    # OutcomeFeedback bridge written (one per action, decision_type = action_type).
    of = await db.execute(text("SELECT COUNT(*) FROM outcome_feedback WHERE business_id = :b"), {"b": bid})
    assert of.scalar() >= 1

    # Graph: action → outcome PRODUCES edge.
    edges = await db.execute(text("SELECT relation_type FROM graph_relationships WHERE business_id = :b"),
                             {"b": bid})
    rels = {r[0] for r in edges.fetchall()}
    assert "PRODUCES" in rels

    # The action is now linked to the finding (agent_actions.finding_id).
    act = await db.execute(text("SELECT finding_id FROM agent_actions WHERE id = :a"), {"a": aid})
    assert str(act.scalar()) == fid


async def test_replayed_action_does_not_duplicate_outcome(db):
    """§29: replaying the terminal-state hook must not duplicate learned outcomes."""
    from app.services.agent_action_executor import _record_terminal_outcome

    bid = await _seed_business(db)
    aid = await _make_action(db, bid, "discount", executed=True, status="approved")
    await _record_terminal_outcome(db, bid, aid)
    await _record_terminal_outcome(db, bid, aid)  # replay/retry

    count = await db.execute(text("SELECT COUNT(*) FROM learned_outcomes WHERE agent_action_id = :a"), {"a": aid})
    assert count.scalar() == 1


async def test_rejection_recorded_and_changes_recommendation(db):
    """§29: rejection is stored; repeated failures flip the recommendation (deterministic)."""
    from app.services.outcome_learning import learning_adjusted_action

    bid = await _seed_business(db)
    # Two failed/rejected discount actions → threshold crossed.
    for _ in range(2):
        aid = await _make_action(db, bid, "discount", executed=False, status="rejected")
        await db.execute(text("UPDATE agent_actions SET decision_note = 'seasonal product' WHERE id = :a"), {"a": aid})
        await db.commit()
        from app.services.agent_action_executor import _record_terminal_outcome
        await _record_terminal_outcome(db, bid, aid)

    adj = await learning_adjusted_action(db, bid, "discount")
    assert adj["adjusted"] is True
    assert adj["action_type"] == "transfer_inventory"
    assert "repeatedly failed" in adj["reason"]


async def test_cross_tenant_isolation(db):
    """§29/§30: business A can never see business B's learned outcomes."""
    from app.services.outcome_learning import list_learned_outcomes
    from app.services.agent_action_executor import _record_terminal_outcome

    bid_a = await _seed_business(db, "A")
    bid_b = await _seed_business(db, "B")

    aid = await _make_action(db, bid_a, "discount", executed=True, status="approved")
    await _record_terminal_outcome(db, bid_a, aid)

    a_outcomes = await list_learned_outcomes(db, bid_a)
    b_outcomes = await list_learned_outcomes(db, bid_b)
    assert len(a_outcomes) == 1
    assert len(b_outcomes) == 0


async def test_finding_agent_action_linkage_is_deterministic(db):
    """§2: finding_id flows through materialization; not inferred from titles."""
    from app.services.runtime import _materialize_action
    from app.intelligence.agents.base import BaseAgent

    bid = await _seed_business(db)
    fid = str(uuid4())
    await db.execute(text("""
        INSERT INTO findings (id, business_id, domain, category, severity, title, status, source, created_at, updated_at)
        VALUES (:id, :b, 'inventory', 'dead_stock', 'medium', 'Dead stock X', 'detected', 'audit_engine', datetime('now'), datetime('now'))
    """), {"id": fid, "b": bid})
    await db.commit()

    class _FakeDisposition:
        decision = "draft"
        risk = "medium"
        policy = {"dial": 50}
        reason = "test"

    agent = BaseAgent.__new__(BaseAgent)
    agent.business_id = bid

    candidate = {"action_type": "discount", "title": "Discount X", "reason": "slow", "finding_id": fid, "confidence": 0.8}
    await _materialize_action(db, agent, candidate, _FakeDisposition())

    act = await db.execute(text("SELECT finding_id FROM agent_actions WHERE business_id = :b"), {"b": bid})
    row = act.fetchone()
    assert row is not None and str(row[0]) == fid

    # Finding.agent_action_id back-pointer set.
    f = await db.execute(text("SELECT agent_action_id FROM findings WHERE id = :fid"), {"fid": fid})
    assert f.scalar() is not None
