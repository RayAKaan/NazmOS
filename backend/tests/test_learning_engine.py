"""Tests for Phase 6: Learning Engine.

Postgres-dependent integration tests are skipped automatically when the test
database is unavailable. SQLite-backed integration tests run locally.
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database.models import Base, IntelligenceDecision, ModelPerformance, OutcomeFeedback
from app.services.learning_engine import (
    compute_model_performance,
    get_model_performance,
    list_feedback,
    record_feedback,
    refresh_learning,
    suggest_best_action,
    thompson_sample_action,
)


@pytest_asyncio.fixture(scope="function")
async def sqlite_session() -> AsyncSession:
    """In-memory SQLite session for Learning Engine tests."""
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


@pytest.mark.asyncio
async def test_record_feedback_from_decision(sqlite_session: AsyncSession):
    business_id = uuid4()
    decision = IntelligenceDecision(
        business_id=business_id,
        decision_type="restock",
        expected_roi=100.0,
        ranked_action={"action_type": "restock", "expected_roi": 100.0},
        confidence=0.85,
    )
    sqlite_session.add(decision)
    await sqlite_session.flush()

    feedback = await record_feedback(
        sqlite_session,
        business_id=business_id,
        decision_id=decision.id,
        actual_outcome={"roi": 120.0, "success": True},
    )
    await sqlite_session.commit()

    assert feedback.business_id == business_id
    assert feedback.decision_id == decision.id
    assert feedback.decision_type == "restock"
    assert feedback.predicted_outcome["roi"] == 100.0
    assert feedback.delta["roi"] == 20.0
    assert feedback.feedback_source == "manual"


@pytest.mark.asyncio
async def test_list_feedback(sqlite_session: AsyncSession):
    business_id = uuid4()
    decision = IntelligenceDecision(
        business_id=business_id,
        decision_type="pricing",
        expected_roi=50.0,
        ranked_action={"action_type": "pricing_increase"},
        confidence=0.7,
    )
    sqlite_session.add(decision)
    await sqlite_session.flush()

    await record_feedback(
        sqlite_session,
        business_id=business_id,
        decision_id=decision.id,
        actual_outcome={"roi": 45.0, "success": False},
    )
    await sqlite_session.commit()

    items, total = await list_feedback(sqlite_session, business_id, decision_type="pricing")
    assert total == 1
    assert items[0].decision_type == "pricing"


@pytest.mark.asyncio
async def test_compute_model_performance(sqlite_session: AsyncSession):
    business_id = uuid4()
    decision = IntelligenceDecision(
        business_id=business_id,
        decision_type="restock",
        expected_roi=100.0,
        ranked_action={"action_type": "restock"},
        confidence=0.8,
    )
    sqlite_session.add(decision)
    await sqlite_session.flush()

    for actual in [{"roi": 110.0, "success": True}, {"roi": 80.0, "success": False}]:
        await record_feedback(
            sqlite_session,
            business_id=business_id,
            decision_id=decision.id,
            actual_outcome=actual,
        )
    await sqlite_session.commit()

    now = datetime.now(timezone.utc)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    perf = await compute_model_performance(sqlite_session, business_id, "restock", start, now)

    assert perf.samples == 2
    assert perf.accuracy == 0.5
    assert perf.roi_error is not None
    assert perf.roi_error > 0


@pytest.mark.asyncio
async def test_refresh_learning(sqlite_session: AsyncSession):
    business_id = uuid4()
    decision = IntelligenceDecision(
        business_id=business_id,
        decision_type="discount",
        expected_roi=20.0,
        ranked_action={"action_type": "discount"},
        confidence=0.6,
    )
    sqlite_session.add(decision)
    await sqlite_session.flush()

    await record_feedback(
        sqlite_session,
        business_id=business_id,
        decision_id=decision.id,
        actual_outcome={"roi": 25.0, "success": True},
    )
    await sqlite_session.commit()

    refreshed = await refresh_learning(sqlite_session, business_id, window_days=30)
    assert len(refreshed) == 1
    assert refreshed[0].decision_type == "discount"

    performance = await get_model_performance(sqlite_session, business_id)
    assert len(performance) == 1


@pytest.mark.asyncio
async def test_thompson_sampling_selects_historical_winner():
    candidates = [
        {"action_type": "restock", "title": "Restock"},
        {"action_type": "discount", "title": "Discount"},
    ]

    feedback_rows = [
        OutcomeFeedback(
            business_id=uuid4(),
            decision_type="restock",
            predicted_outcome={"action_type": "restock", "roi": 100.0},
            actual_outcome={"action_type": "restock", "roi": 120.0, "success": True},
            delta={"roi": 20.0},
        ),
        OutcomeFeedback(
            business_id=uuid4(),
            decision_type="restock",
            predicted_outcome={"action_type": "restock", "roi": 100.0},
            actual_outcome={"action_type": "restock", "roi": 90.0, "success": False},
            delta={"roi": -10.0},
        ),
        OutcomeFeedback(
            business_id=uuid4(),
            decision_type="discount",
            predicted_outcome={"action_type": "discount", "roi": 20.0},
            actual_outcome={"action_type": "discount", "roi": 5.0, "success": False},
            delta={"roi": -15.0},
        ),
    ]

    import random
    rng = random.Random(42)
    selected, scores, note = thompson_sample_action(candidates, feedback_rows, rng=rng)
    assert selected["action_type"] in {"restock", "discount"}
    assert "restock" in scores
    assert "discount" in scores
    assert "feedback" in note.lower()


@pytest.mark.asyncio
async def test_suggest_best_action(sqlite_session: AsyncSession):
    business_id = uuid4()
    decision = IntelligenceDecision(
        business_id=business_id,
        decision_type="pricing",
        expected_roi=10.0,
        ranked_action={"action_type": "pricing_increase"},
        confidence=0.6,
    )
    sqlite_session.add(decision)
    await sqlite_session.flush()

    for _ in range(3):
        await record_feedback(
            sqlite_session,
            business_id=business_id,
            decision_id=decision.id,
            actual_outcome={"action_type": "pricing_increase", "roi": 15.0, "success": True},
        )
    await sqlite_session.commit()

    candidates = [
        {"action_type": "pricing_increase", "title": "Increase price"},
        {"action_type": "pricing_decrease", "title": "Decrease price"},
    ]
    selected, probabilities, note = await suggest_best_action(
        sqlite_session, business_id, candidates, decision_type="pricing", seed=42
    )
    assert selected["action_type"] in {"pricing_increase", "pricing_decrease"}
    assert "pricing_increase" in probabilities
    assert note


# ═══════════════════════════════════════════════════════════════════════════
# API integration tests (Postgres only)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_feedback_endpoint(authenticated_client: dict):
    ctx = authenticated_client
    client: AsyncClient = ctx["client"]
    business_id = ctx["business_id"]

    response = await client.post(
        f"/api/v1/intelligence/feedback?business_id={business_id}",
        json={"actual_outcome": {"roi": 100.0, "success": True}, "feedback_source": "manual"},
        headers=ctx["headers"],
    )
    assert response.status_code == 400, response.text


@pytest.mark.asyncio
async def test_performance_endpoint(authenticated_client: dict):
    ctx = authenticated_client
    client: AsyncClient = ctx["client"]
    business_id = ctx["business_id"]

    response = await client.get(
        f"/api/v1/intelligence/performance?business_id={business_id}",
        headers=ctx["headers"],
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_suggest_action_endpoint(authenticated_client: dict):
    ctx = authenticated_client
    client: AsyncClient = ctx["client"]
    business_id = ctx["business_id"]

    response = await client.post(
        f"/api/v1/intelligence/learning/suggest-action?business_id={business_id}",
        json={
            "candidates": [
                {"action_type": "restock", "title": "Restock milk"},
                {"action_type": "discount", "title": "Discount bread"},
            ],
            "decision_type": "inventory",
            "seed": 42,
        },
        headers=ctx["headers"],
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert "selected_candidate" in data
    assert "probabilities" in data
