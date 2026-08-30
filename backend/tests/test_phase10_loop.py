"""Phase 10 integration tests (SQLite).

Proves: recency-weighted strategy summary keeps raw history, root-cause investigation
returns evidence-backed hypotheses (and 'uncertain' when data is absent), and operational
health reports reconciliation gaps.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
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


async def _learned(db: AsyncSession, bid: str, action_type: str, executed: bool, impact: float,
                   created_at: datetime) -> str:
    aid = str(uuid4())
    await db.execute(text("""
        INSERT INTO agent_actions (id, business_id, action_type, status, confidence, priority,
                                   title, summary, payload, autonomy_dial_at_creation, was_auto_executed,
                                   outcome_json, created_at, updated_at)
        VALUES (:id, :b, :t, 'approved', 0.9, 3, :title, 's', :payload, 50, false, :outcome, :at, :at)
    """), {
        "id": aid, "b": bid, "t": action_type, "title": action_type,
        "payload": json.dumps({"title": action_type}), "outcome": json.dumps({"executed": executed}),
        "at": created_at,
    })
    await db.execute(text("""
        INSERT INTO learned_outcomes (id, business_id, agent_action_id, action_type, kind, approval,
                                      execution_result, expected_impact_sar, actual_impact_sar, confidence,
                                      evidence_count, created_at)
        VALUES (:id, :b, :aid, :t, 'inference', 'approved', :er, 1000, :imp, 0.8, 1, :at)
    """), {
        "id": str(uuid4()), "b": bid, "aid": aid, "t": action_type,
        "er": json.dumps({"executed": executed}), "imp": impact, "at": created_at,
    })
    await db.commit()
    return aid


async def test_recency_weighted_summary_preserves_raw_history(db):
    """§12: recency weighting shifts relevance but never rewrites raw attempt counts."""
    from app.services.strategy_performance import strategy_summary, strategy_summary_recency

    bid = await _seed_business(db)
    old = datetime.now(timezone.utc) - timedelta(days=400)
    recent = datetime.now(timezone.utc) - timedelta(days=1)
    for _ in range(5):
        await _learned(db, bid, "discount", executed=True, impact=1000.0, created_at=old)
    await _learned(db, bid, "discount", executed=True, impact=1000.0, created_at=recent)

    raw = await strategy_summary(db, bid, "discount")
    rw = await strategy_summary_recency(db, bid, "discount")

    # Raw history unchanged: 6 attempts, all succeeded.
    assert raw["attempts"] == 6
    assert raw["success_rate"] == 1.0
    assert rw["attempts"] == 6  # recency does not erase history
    # Recency-weighted success stays high (all succeeded), but the sum of weights < attempts.
    assert rw["recency_weight_sum"] < 6.0


async def test_root_cause_uncertain_without_data(db):
    """§17/§36: no root-cause model or no data → 'uncertain', never a fabricated cause."""
    from app.services.root_cause import investigate_root_cause

    bid = await _seed_business(db)
    r = await investigate_root_cause(db, bid, {"category": "no_such_category", "evidence": {}})
    assert r["status"] == "uncertain"
    assert r["hypotheses"] == []


async def test_root_cause_stockout_uses_real_fields(db):
    """§16: stockout root-cause uses reorder/lead-time data when present."""
    from app.services.root_cause import investigate_root_cause

    bid = await _seed_business(db)
    item_id = str(uuid4())
    await db.execute(text("""
        INSERT INTO items (id, business_id, name, cost_price, sell_price) VALUES (:i, :b, 'Milk', 1.0, 2.0)
    """), {"i": item_id, "b": bid})
    await db.execute(text("""
        INSERT INTO inventory (id, business_id, item_id, current_stock, reorder_level, lead_time_days, safety_stock)
        VALUES (:id, :b, :i, 5, 10, 6, 2)
    """), {"id": str(uuid4()), "b": bid, "i": item_id})
    await db.commit()

    r = await investigate_root_cause(db, bid, {
        "category": "stockout_risk",
        "evidence": {"item_id": item_id},
    })
    assert r["status"] in ("supported", "plausible")
    assert any("lead time" in h["hypothesis"] or "reorder" in h["hypothesis"] for h in r["hypotheses"])


async def test_operational_health_detects_reconciliation_gap(db):
    """§25: a terminal action missing its LearnedOutcome → requires_reconciliation."""
    from app.services.operational_health import operational_health

    bid = await _seed_business(db)
    # A terminal action with NO learned outcome (gap).
    await db.execute(text("""
        INSERT INTO agent_actions (id, business_id, action_type, status, confidence, priority,
                                   title, summary, payload, autonomy_dial_at_creation, was_auto_executed,
                                   created_at, updated_at)
        VALUES (:id, :b, 'discount', 'approved', 0.9, 3, 'x', 'y', '{}', 50, false, datetime('now'), datetime('now'))
    """), {"id": str(uuid4()), "b": bid})
    await db.commit()

    health = await operational_health(db, bid)
    assert health["status"] == "requires_reconciliation"
    assert health["reconciliation"]["missing_learned_outcomes"] >= 1
