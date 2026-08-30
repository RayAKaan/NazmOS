"""Phase 7 integration tests (SQLite, real DB round-trips).

Proves: recovery is Finding-driven (§2), learning reconciliation repairs missing
OutcomeFeedback (§8–9), and the finding timeline reconstructs the decision chain (§7).
"""
from __future__ import annotations

import json
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


async def _make_finding(db: AsyncSession, bid: str, category: str, impact: float) -> str:
    fid = str(uuid4())
    await db.execute(text("""
        INSERT INTO findings (id, business_id, domain, category, severity, title, explanation, evidence,
                              affected_entities, estimated_financial_impact_sar, recommended_action, status, source, created_at, updated_at)
        VALUES (:id, :b, 'money_audit', :cat, 'high', :title, 'trapped capital', '{}', '[]',
                :impact, :rec, 'detected', 'audit_engine', datetime('now'), datetime('now'))
    """), {
        "id": fid, "b": bid, "cat": category, "title": f"{category} finding", "impact": impact,
        "rec": json.dumps({"type": "discount", "why": "recover capital", "item_id": "item-1"}),
    })
    await db.commit()
    return fid


async def _make_action(db: AsyncSession, bid: str, action_type: str, finding_id: str | None, executed: bool):
    aid = str(uuid4())
    await db.execute(text("""
        INSERT INTO agent_actions (id, business_id, finding_id, action_type, status, confidence, priority,
                                   title, summary, payload, estimated_value_sar, autonomy_dial_at_creation,
                                   was_auto_executed, outcome_json, created_at, updated_at)
        VALUES (:id, :b, :fid, :t, 'approved', 0.9, 3, :title, 'summary', :payload, 4000, 50, false, :outcome,
                datetime('now'), datetime('now'))
    """), {
        "id": aid, "b": bid, "fid": finding_id, "t": action_type, "title": f"{action_type} test",
        "payload": json.dumps({"title": f"{action_type} test"}),
        "outcome": json.dumps({"executed": executed}),
    })
    await db.commit()
    return aid


async def test_recovery_is_finding_driven(db):
    """§2: Recovery Agent proposes from canonical Findings (carries finding_id)."""
    from app.intelligence.agents.recovery_agent import RecoveryAgent

    bid = await _seed_business(db)
    fid = await _make_finding(db, bid, "dead_stock", 5000)

    agent = RecoveryAgent(db, bid)
    result = await agent.propose()

    proposals = result["payload"]["proposals"]
    assert len(proposals) >= 1
    assert proposals[0]["finding_id"] == fid  # deterministic lineage, not inferred


async def test_learning_reconciliation_repairs_missing_feedback(db):
    """§8–9: a terminal action with a LearnedOutcome but no OutcomeFeedback is repaired."""
    from app.services.outcome_learning import learn_from_action
    from app.services.learning_reconciliation import reconcile_all

    bid = await _seed_business(db)
    aid = await _make_action(db, bid, "discount", None, executed=True)

    # Write only the LearnedOutcome (simulate the OutcomeFeedback bridge having failed).
    await learn_from_action(db, bid, aid, commit=True)
    # Manually delete any outcome_feedback that learn_from_action may have written via record_unified_outcome
    await db.execute(text("DELETE FROM outcome_feedback WHERE agent_action_id = :a"), {"a": aid})
    await db.commit()

    # Before reconcile: feedback missing.
    before = await db.execute(text("SELECT COUNT(*) FROM outcome_feedback WHERE agent_action_id = :a"), {"a": aid})
    assert before.scalar() == 0

    result = await reconcile_all(db, bid)
    assert result["repaired"] >= 1

    after = await db.execute(text("SELECT COUNT(*) FROM outcome_feedback WHERE agent_action_id = :a"), {"a": aid})
    assert after.scalar() == 1  # idempotent: exactly one


async def test_finding_timeline_reconstructs_chain(db):
    """§7: timeline includes found → approved/executed → learned events."""
    from app.services.finding_timeline import build_finding_timeline
    from app.services.agent_action_executor import _record_terminal_outcome

    bid = await _seed_business(db)
    fid = await _make_finding(db, bid, "dead_stock", 5000)
    aid = await _make_action(db, bid, "discount", fid, executed=True)
    await _record_terminal_outcome(db, bid, aid)

    timeline = await build_finding_timeline(db, fid, bid)
    steps = [e["step"] for e in timeline]
    assert "found" in steps
    assert "executed" in steps or "approved" in steps
    assert "learned" in steps


async def test_outcome_feedback_unique_per_action(db):
    """§8: one OutcomeFeedback per action (unique constraint enforces idempotency)."""
    from app.services.outcome_learning import record_unified_outcome

    bid = await _seed_business(db)
    aid = await _make_action(db, bid, "discount", None, executed=True)
    await record_unified_outcome(db, bid, aid, commit=True)
    await record_unified_outcome(db, bid, aid, commit=True)  # replay

    count = await db.execute(text("SELECT COUNT(*) FROM outcome_feedback WHERE agent_action_id = :a"), {"a": aid})
    assert count.scalar() == 1
