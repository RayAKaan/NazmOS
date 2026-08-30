"""Phase 8 integration tests (SQLite, real DB round-trips).

Proves the adaptive loop (§30–31): per-finding impact attribution, strategy performance,
and that a previous outcome changes a future recommendation ranking.

Scenarios:
  A/B — strategy selection + insufficient evidence.
  E — impact attribution (finding → action → ImpactLedger with attribution).
  F — no double counting (per-finding attribution doesn't inflate business totals).
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


async def _make_finding(db: AsyncSession, bid: str, category: str) -> str:
    fid = str(uuid4())
    await db.execute(text("""
        INSERT INTO findings (id, business_id, domain, category, severity, title, status, source, created_at, updated_at)
        VALUES (:id, :b, 'money_audit', :cat, 'high', :cat, 'detected', 'audit_engine', datetime('now'), datetime('now'))
    """), {"id": fid, "b": bid, "cat": category})
    await db.commit()
    return fid


async def _make_action(db: AsyncSession, bid: str, action_type: str, finding_id: str, executed: bool = True) -> str:
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


async def _record_impact(db: AsyncSession, bid: str, finding_id: str, action_id: str, amount: float,
                         attribution: str, verified: bool = True):
    from app.services.impact_ledger_service import record_impact
    await record_impact(
        db, bid, "money_recovered", amount, finding_id=finding_id, agent_action_id=action_id,
        actual_sar=amount, verified=verified, verification="observed", attribution=attribution,
        source="test", commit=True,
    )


async def test_per_finding_impact_attribution(db):
    """Scenario E: finding → action → ImpactLedger with attribution; direct vs business separated."""
    from app.services.impact_ledger_service import finding_observed_impact

    bid = await _seed_business(db)
    fid = await _make_finding(db, bid, "dead_stock")
    aid = await _make_action(db, bid, "transfer_inventory", fid)
    await _record_impact(db, bid, fid, aid, 2400.0, "direct")

    impact = await finding_observed_impact(db, bid, fid)
    assert impact["direct_sar"] == 2400.0
    assert impact["total_verified_sar"] == 2400.0
    assert impact["business_level_sar"] == 0.0  # not conflated


async def test_no_double_count_business_vs_direct(db):
    """Scenario F: business-level and direct attributions are kept distinct in aggregation."""
    from app.services.impact_ledger_service import finding_observed_impact, total_impact

    bid = await _seed_business(db)
    fid = await _make_finding(db, bid, "dead_stock")
    aid = await _make_action(db, bid, "transfer_inventory", fid)
    await _record_impact(db, bid, fid, aid, 2400.0, "direct")

    # A coarse business-level entry (a different source) must not be summed as "direct".
    fid2 = await _make_finding(db, bid, "margin_leakage")
    aid2 = await _make_action(db, bid, "margin_fix", fid2)
    await _record_impact(db, bid, fid2, aid2, 12000.0, "business_level")

    f1 = await finding_observed_impact(db, bid, fid)
    assert f1["direct_sar"] == 2400.0
    assert f1["business_level_sar"] == 0.0  # finding 1 has no business-level entries

    # total_impact aggregates all verified (both attributions), but per-finding stays precise.
    total = await total_impact(db, bid, observed_only=True)
    assert total["observed_sar"] == 14400.0


async def _learn(db: AsyncSession, bid: str, aid: str):
    from app.services.agent_action_executor import _record_terminal_outcome
    await _record_terminal_outcome(db, bid, aid)


async def test_strategy_performance_ranks_higher_effectiveness_first(db):
    """Scenario A: a strategy with more verified successes/effectiveness ranks first."""
    from app.services.strategy_performance import best_strategy_for_finding

    bid = await _seed_business(db)
    fid = await _make_finding(db, bid, "dead_stock")

    # transfer_inventory: 3 successful, high actual impact.
    for i in range(3):
        aid = await _make_action(db, bid, "transfer_inventory", fid)
        await _record_impact(db, bid, fid, aid, 2000.0 + i, "direct")
        await _learn(db, bid, aid)
    # discount: 3 attempts, low impact.
    for i in range(3):
        aid = await _make_action(db, bid, "discount", fid)
        await _record_impact(db, bid, fid, aid, 100.0, "direct")
        await _learn(db, bid, aid)

    ranking = await best_strategy_for_finding(db, bid, ["transfer_inventory", "discount"], "dead_stock")
    top = ranking["ranking"][0]
    assert top["action_type"] == "transfer_inventory"
    assert top["evidence_tier"] in ("preliminary", "strong")


async def test_insufficient_evidence_not_strongly_ranked(db):
    """Scenario B: a single attempt is insufficient evidence (low tier weight)."""
    from app.services.strategy_performance import strategy_summary

    bid = await _seed_business(db)
    fid = await _make_finding(db, bid, "dead_stock")
    aid = await _make_action(db, bid, "discount", fid)
    await _record_impact(db, bid, fid, aid, 5000.0, "direct")  # one big success
    await _learn(db, bid, aid)

    s = await strategy_summary(db, bid, "discount")
    assert s["attempts"] == 1
    assert s["evidence_tier"] == "insufficient"  # §9: 1 attempt is never "strong"
