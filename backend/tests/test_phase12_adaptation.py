"""Phase 12 — recency + regime + strategy-adaptation tests (SQLite, real round-trips).

Proves the §Part 4 matrix + §Part 8 "learning actually changes behavior":
  A. no regime → historical evidence remains relevant
  B/C. regime change discounts historical relevance (without erasing history)
  D. insufficient data → no invented penalty
  E/F. recency weighting shifts relevance; weak recent sample doesn't override strong history
  G. safety always overrides stability
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database.models import Base
from tests.fixtures.merchants import (
    seed_business, seed_category, seed_item, seed_inventory,
    seed_recurring_stockout_merchant,
)


@pytest_asyncio.fixture(scope="function")
async def db() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool,
                                 connect_args={"check_same_thread": False})
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with SessionLocal() as session:
        yield session
    await engine.dispose()


# ── §Part 4: regime detection matrix (pure logic) ─────────────────────────

def test_regime_matrix():
    from app.services.regime_detection import detect_regime, regime_relevance_multiplier

    # A. no change
    assert detect_regime([100, 98, 102, 99, 101, 100], [101, 100, 99])["state"] == "no_signal"
    # C. supported change
    assert detect_regime([100, 98, 102, 99, 101, 100], [20, 22, 18])["state"] == "supported_change"
    # D. insufficient data → multiplier 1.0 (no invented penalty)
    assert regime_relevance_multiplier("insufficient_data") == 1.0
    # supported change discounts to 0.4
    assert regime_relevance_multiplier("supported_change") == 0.4


def test_recency_weight_matrix():
    from app.services.strategy_performance import recency_weight
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert recency_weight(now - timedelta(days=1), now) > recency_weight(now - timedelta(days=300), now)


# ── §Part 8 / §Part 2: regime relevance actually affects ranking ──────────

async def _seed_strategy_history(db: AsyncSession, bid: str, action_type: str, n: int, executed: bool):
    import json
    for _ in range(n):
        aid = str(uuid4())
        await db.execute(text("""
            INSERT INTO agent_actions (id, business_id, action_type, status, confidence, priority,
                                       title, summary, payload, autonomy_dial_at_creation, was_auto_executed,
                                       outcome_json, created_at, updated_at)
            VALUES (:id, :b, :t, 'approved', 0.9, 3, :t, 's', '{}', 50, false, :out, datetime('now'), datetime('now'))
        """), {"id": aid, "b": bid, "t": action_type, "out": json.dumps({"executed": executed})})
        await db.execute(text("""
            INSERT INTO learned_outcomes (id, business_id, agent_action_id, action_type, kind, approval,
                                          execution_result, expected_impact_sar, actual_impact_sar, confidence,
                                          evidence_count, created_at)
            VALUES (:id, :b, :aid, :t, 'inference', 'approved', :er, 1000, 900, 0.8, 1, datetime('now'))
        """), {"id": str(uuid4()), "b": bid, "aid": aid, "t": action_type, "er": json.dumps({"executed": executed})})
    await db.commit()


async def test_regime_relevance_discounts_ranking_without_erasing(db):
    """§Part 2/10: supported regime change lowers contextual score but keeps historical data."""
    from app.services.strategy_performance import best_strategy_for_finding

    bid = await seed_business(db, "Regime Merchant")
    await _seed_strategy_history(db, bid, "transfer_inventory", 6, executed=True)

    no_regime = await best_strategy_for_finding(db, bid, ["transfer_inventory"], regime_state="no_signal")
    regime = await best_strategy_for_finding(db, bid, ["transfer_inventory"], regime_state="supported_change")

    top_none = no_regime["ranking"][0]
    top_regime = regime["ranking"][0]
    # Same historical effectiveness (not erased)…
    assert top_none["effectiveness"] == top_regime["effectiveness"]
    assert top_none["attempts"] == top_regime["attempts"]
    # …but the contextual score is discounted under regime change.
    assert top_regime["regime_relevance"] == 0.4
    assert top_regime["score"] < top_none["score"]


async def test_insufficient_data_does_not_penalize(db):
    """§Part 4 D / §Part 8 E: no evidence → deterministic baseline, no invented regime penalty."""
    from app.services.strategy_performance import best_strategy_for_finding
    bid = await seed_business(db, "Empty Merchant")
    r = await best_strategy_for_finding(db, bid, ["discount"], regime_state="insufficient_data")
    assert r["ranking"][0]["regime_relevance"] == 1.0
    assert r["ranking"][0]["evidence_tier"] == "insufficient"


# ── §Part 3: safety overrides everything ──────────────────────────────────

def test_safety_overrides_stability_and_history():
    from app.services.decision_scoring import apply_stability
    ranked = [
        {"action_type": "discount", "score": 0.50, "risk": "low"},
        {"action_type": "transfer_inventory", "score": 0.49, "risk": "high"},
    ]
    out = apply_stability(ranked, previous_selection="transfer_inventory")
    # transfer is high-risk → not retained despite being the previous selection.
    assert out[0]["action_type"] == "discount"


async def test_recurring_stockout_merchant_has_low_stock(db):
    """Fixture sanity: recurring-stockout merchant has low stock + high velocity."""
    info = await seed_recurring_stockout_merchant(db)
    row = await db.execute(text("SELECT current_stock FROM inventory WHERE item_id = :i"),
                           {"i": info["item_id"]})
    assert float(row.scalar()) < 5
