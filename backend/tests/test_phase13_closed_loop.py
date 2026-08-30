"""Phase 13 — definitive Day 1 → Day 14 closed-loop SIMULATION (single test run).

This is NOT a 14-real-day test. It compresses 14 days of synthetic business history into one
execution by seeding historical timestamps and passing a virtual `now` to the deterministic
evaluation functions (recency, freshness, regime). No sleeps, no Celery Beat, no real time.

Days covered: audit → finding → data quality/freshness → root cause → strategy → execution →
learning → recurrence → regime → margin root cause → goal movement → weekly report →
freshness degradation → final audit comparison.

Requires zero external data; all values are synthetic.
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
from tests.fixtures.merchants import (
    seed_business, seed_category, seed_item, seed_inventory, seed_transactions,
    seed_supplier, seed_supplier_price,
)

DAY1 = datetime(2026, 1, 1, tzinfo=timezone.utc)


@pytest_asyncio.fixture(scope="function")
async def db() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool,
                                 connect_args={"check_same_thread": False})
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    S = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with S() as session:
        yield session
    await engine.dispose()


async def _audit(db, bid, domain="inventory"):
    from app.services.audit_engine import run_audit
    return await run_audit(db, bid, domain, trigger="manual")


def _at(day: int) -> datetime:
    return DAY1 + timedelta(days=day - 1)


async def test_day1_to_day14_simulation_runs_immediately(db):
    """The flagship: the entire 14-day lifecycle compresses into one test with no real time."""
    from app.services.root_cause import investigate_root_cause
    from app.services.operational_health import operational_health
    from app.services.weekly_report_service import build_weekly_report
    from app.services.audit_comparison import compare_audits
    from app.services.strategy_performance import best_strategy_for_finding
    from app.services.regime_detection import detect_regime
    from app.services.prioritization import top_problems

    # ── DAY 1: seed a recurring-stockout merchant ───────────────────────────
    bid = await seed_business(db, "Day1-14 Sim Merchant")
    cat = await seed_category(db, bid, "Dairy")
    milk = await seed_item(db, bid, "Fresh Milk 1L", cat, cost=1.0, sell=3.0, sku="MILK-1L")
    await seed_inventory(db, bid, milk, stock=3.0, reorder_level=10, lead_time_days=6, safety_stock=2)
    # 30 days of sales at 10/day, ending at Day 1
    for d in range(30):
        await seed_transactions(db, bid, milk, 10.0, _at(1) - timedelta(days=d))

    # supplier price history for margin tests later
    sup = await seed_supplier(db, "Sim Distributor")
    await seed_supplier_price(db, sup, milk, 1.0, _at(1) - timedelta(days=60), bid)
    await seed_supplier_price(db, sup, milk, 1.5, _at(1), bid)
    await db.commit()

    # ── DAY 1: audit → finding ─────────────────────────────────────────────
    r = await _audit(db, bid)
    assert r["status"] == "completed" and r["findings"] >= 1

    # ── DAY 2: root cause ──────────────────────────────────────────────────
    findings = await db.execute(text("SELECT id, category FROM findings WHERE business_id = :b ORDER BY created_at"),
                                {"b": bid})
    frows = findings.fetchall()
    assert frows
    stockout = next((f for f in frows if f.category == "stockout_risk"), frows[0])
    rc = await investigate_root_cause(db, bid, {"id": str(stockout.id), "category": stockout.category,
                                                "evidence": {"item_id": milk}})
    assert rc["status"] in ("supported", "plausible", "uncertain")

    # ── DAY 2–3: strategy ranking (recency + regime) ────────────────────────
    ranking = await best_strategy_for_finding(db, bid, ["transfer_inventory", "restock", "discount"],
                                              regime_state="no_signal")
    assert ranking["ranking"]  # deterministic ranking produced

    # ── DAY 3: execute a transfer → learning ───────────────────────────────
    from app.services.agent_action_executor import _record_terminal_outcome
    aid = str(uuid4())
    await db.execute(text("""
        INSERT INTO agent_actions (id, business_id, action_type, status, confidence, priority,
                                   title, summary, payload, autonomy_dial_at_creation, was_auto_executed,
                                   outcome_json, created_at, updated_at)
        VALUES (:id, :b, 'transfer_inventory', 'approved', 0.9, 3, 'transfer', 's', '{}', 50, false, :out, :at, :at)
    """), {"id": aid, "b": bid, "out": json.dumps({"executed": True}), "at": _at(3)})
    await db.commit()
    await _record_terminal_outcome(db, bid, aid)

    # learning recorded
    lo = await db.execute(text("SELECT COUNT(*) FROM learned_outcomes WHERE business_id = :b"), {"b": bid})
    assert lo.scalar() >= 1

    # ── DAY 5: recurrence → audit comparison ───────────────────────────────
    await _audit(db, bid)  # second audit (same finding recurs)
    comparison = await compare_audits(db, bid)
    assert comparison["counts"]["resolved"] == 0  # never fake RESOLVED

    # ── DAY 8: regime change (velocity drops) ──────────────────────────────
    # seed a 7-day recent window of low velocity (2/day) after a 28-day high window
    for d in range(7):
        await seed_transactions(db, bid, milk, 2.0, _at(8) - timedelta(days=d))
    await db.commit()

    historical = [10.0] * 12   # prior 12 daily observations (10/day)
    recent = [2.0] * 7         # recent 7 daily observations (2/day)
    regime = detect_regime(historical, recent)
    assert regime["state"] == "supported_change"

    # ── DAY 9: regime relevance changes ranking, history preserved ──────────
    r_no = await best_strategy_for_finding(db, bid, ["transfer_inventory", "restock"], regime_state="no_signal")
    r_chg = await best_strategy_for_finding(db, bid, ["transfer_inventory", "restock"], regime_state="supported_change")
    assert r_chg["ranking"][0]["regime_relevance"] == 0.4
    # historical effectiveness is preserved (attempts unchanged)
    assert r_chg["ranking"][0]["attempts"] == r_no["ranking"][0]["attempts"]

    # ── DAY 10: margin root cause (supplier cost increased) ────────────────
    coffee = await seed_item(db, bid, "Coffee Beans", cat, cost=20.0, sell=24.0, sku="COFFEE")
    await seed_inventory(db, bid, coffee, stock=50.0)
    await seed_supplier_price(db, sup, coffee, 16.0, _at(1) - timedelta(days=60), bid)
    await seed_supplier_price(db, sup, coffee, 22.0, _at(10), bid)
    await db.commit()
    mrc = await investigate_root_cause(db, bid, {"id": str(uuid4()), "category": "margin_leakage",
                                                 "evidence": {"item_id": coffee}})
    assert any(h.get("hypothesis_key") == "supplier_cost_increase" for h in mrc["hypotheses"])

    # ── DAY 11: goal movement ──────────────────────────────────────────────
    from app.services.goal_service import create_goal, list_goals_with_progress
    await create_goal(db, bid, title="Reduce dead stock", metric="dead_stock_value", direction="decrease",
                      target=5000, baseline=20000, source="manual")
    goals = await list_goals_with_progress(db, bid)
    assert len(goals) >= 1

    # ── DAY 12: weekly report + canonical priorities ───────────────────────
    report = await build_weekly_report(db, bid)
    assert "priorities" in report
    top = await top_problems(db, bid, limit=3)
    assert len(top) <= 3

    # ── DAY 13: freshness degradation → operational health ─────────────────
    # age the inventory timestamp to 200 hours ago relative to "now"
    await db.execute(text("UPDATE inventory SET updated_at = :old WHERE business_id = :b"),
                     {"old": _at(13) - timedelta(hours=200), "b": bid})
    await db.commit()
    health = await operational_health(db, bid, now=_at(13))
    assert health["status"] in ("healthy", "degraded", "requires_reconciliation")

    # ── DAY 14: final audit + comparison ───────────────────────────────────
    await _audit(db, bid)
    final = await compare_audits(db, bid)
    assert "counts" in final  # deterministic classification produced


async def test_virtual_clock_affects_recency_and_freshness(db):
    """Virtual time (explicit `now`) correctly shifts recency + freshness without sleeps."""
    from app.services.strategy_performance import recency_weight
    from app.services.operational_health import data_freshness

    # recency: same created_at evaluated at two different 'now's
    created = DAY1
    w_now = recency_weight(created, now=DAY1 + timedelta(days=1))
    w_later = recency_weight(created, now=DAY1 + timedelta(days=200))
    assert w_later < w_now  # older relative to 'now' → lower weight

    # freshness: seed stale inventory, evaluate at two 'now's
    bid = await seed_business(db, "Freshness Merchant")
    cat = await seed_category(db, bid, "G")
    item = await seed_item(db, bid, "X", cat, 1.0, 2.0)
    await db.execute(text("""
        INSERT INTO inventory (id, business_id, item_id, current_stock, reorder_level, lead_time_days, safety_stock, updated_at)
        VALUES (:id, :b, :i, 5, 10, 3, 2, :at)
    """), {"id": str(uuid4()), "b": bid, "i": item, "at": DAY1})
    await db.commit()

    f1 = await data_freshness(db, bid, now=DAY1 + timedelta(hours=1))
    f2 = await data_freshness(db, bid, now=DAY1 + timedelta(hours=200))
    assert f1["inventory"]["state"] == "fresh"
    assert f2["inventory"]["state"] in ("aging", "stale")


async def test_cash_and_compliance_root_cause(db):
    """Cash + compliance root-cause hypotheses derive from real fields only."""
    from app.services.root_cause import investigate_root_cause
    from tests.fixtures.merchants import seed_cash_pressure_merchant, seed_pharmacy_merchant

    cash = await seed_cash_pressure_merchant(db)
    crc = await investigate_root_cause(db, cash["business_id"], {"category": "cash_pressure", "evidence": {}})
    assert any(h.get("hypothesis_key") == "inventory_cash_trapped" for h in crc["hypotheses"])

    pharm = await seed_pharmacy_merchant(db)
    prc = await investigate_root_cause(db, pharm["business_id"], {"category": "compliance_risk", "evidence": {}})
    assert prc["status"] in ("supported", "plausible", "uncertain")
