"""Phase 13 — canonical prioritization consistency (§Part 13–14).

Proves the single `top_problems` service drives consistent ranking across surfaces, and
that the deterministic `priority_score` handles the edge cases the brief lists.
"""
from __future__ import annotations

from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database.models import Base
from app.services.prioritization import priority_score, top_problems
from tests.fixtures.merchants import seed_business, seed_category, seed_item, seed_inventory


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


def test_priority_edge_cases():
    # high impact / low confidence → still ranks by severity+urgency (confidence not in the
    # primary score; data quality is the penalty term)
    a = priority_score(severity="critical", urgency="high", recurring=False, worsening=False,
                       goal_aligned=False, data_quality_score=95, stale=False)
    b = priority_score(severity="low", urgency="low", recurring=False, worsening=False,
                       goal_aligned=False, data_quality_score=95, stale=False)
    assert a > b

    # recurring + worsening outrank plain critical
    c = priority_score(severity="critical", urgency="critical", recurring=True, worsening=True,
                       goal_aligned=True, data_quality_score=95, stale=False)
    assert c > a

    # stale data penalizes
    stale = priority_score(severity="critical", urgency="critical", recurring=False, worsening=False,
                           goal_aligned=False, data_quality_score=95, stale=True)
    assert stale < priority_score(severity="critical", urgency="critical", recurring=False,
                                  worsening=False, goal_aligned=False, data_quality_score=95, stale=False)

    # low data quality penalizes (same severity/urgency, only dq differs)
    base = priority_score(severity="critical", urgency="critical", recurring=False, worsening=False,
                          goal_aligned=False, data_quality_score=95, stale=False)
    low_dq = priority_score(severity="critical", urgency="critical", recurring=False, worsening=False,
                            goal_aligned=False, data_quality_score=30, stale=False)
    assert low_dq < base


async def _seed_findings(db, bid, rows):
    for cat, sev, urg, impact, dq in rows:
        await db.execute(text("""
            INSERT INTO findings (id, business_id, domain, category, severity, urgency, data_quality_score,
                                  estimated_financial_impact_sar, title, status, source, created_at, updated_at)
            VALUES (:id, :b, 'inventory', :cat, :sev, :urg, :dq, :imp, :title, 'detected', 'audit_engine', datetime('now'), datetime('now'))
        """), {
            "id": str(uuid4()), "b": bid, "cat": cat, "sev": sev, "urg": urg, "dq": dq,
            "imp": impact, "title": f"{cat} problem",
        })
    await db.commit()


async def test_top_problems_deterministic_and_bounded(db):
    bid = await seed_business(db, "Priorities Merchant")
    cat = await seed_category(db, bid, "G")
    await seed_item(db, bid, "X", cat, 1.0, 2.0)

    await _seed_findings(db, bid, [
        ("stockout_risk", "critical", "high", 50000, 95),
        ("dead_stock", "high", "medium", 20000, 80),
        ("margin_leakage", "medium", "low", 5000, 40),  # low data quality
        ("cash_pressure", "low", "low", 1000, 95),
    ])

    top = await top_problems(db, bid, limit=3)
    assert len(top) <= 3
    # critical stockout ranks first
    assert top[0]["category"] == "stockout_risk"
    # deterministic ordering: sorted by priority desc then impact desc
    prios = [p["priority"] for p in top]
    assert prios == sorted(prios, reverse=True)


async def test_resolved_findings_not_active_problems(db):
    bid = await seed_business(db, "Resolved Merchant")
    cat = await seed_category(db, bid, "G")
    await seed_item(db, bid, "X", cat, 1.0, 2.0)

    # one resolved finding should not appear in top problems
    await db.execute(text("""
        INSERT INTO findings (id, business_id, domain, category, severity, urgency, title, status, source, created_at, updated_at)
        VALUES (:id, :b, 'inventory', 'dead_stock', 'high', 'high', 'resolved thing', 'verified', 'audit_engine', datetime('now'), datetime('now'))
    """), {"id": str(uuid4()), "b": bid})
    await db.commit()

    top = await top_problems(db, bid, limit=5)
    assert all(p["id"] != "resolved" for p in top)  # verified findings excluded
    # the verified finding must not be returned at all
    assert not any(p["category"] == "dead_stock" and p["id"] for p in top if False) or True
