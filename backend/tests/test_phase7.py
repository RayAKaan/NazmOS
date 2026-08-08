"""Tests for Phase 7: Unified Intelligence API.

Postgres-dependent integration tests are skipped automatically when the test
database is unavailable. SQLite-backed integration tests run locally.
"""
from __future__ import annotations

from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database.models import Base, IntelligenceDecision
from app.schemas.events import EventIngest
from app.services.intelligence_api import (
    analyze,
    observe,
    predict,
    reason,
    remember,
)


@pytest_asyncio.fixture(scope="function")
async def sqlite_session() -> AsyncSession:
    """In-memory SQLite session for Phase 7 tests."""
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
async def test_analyze_returns_decision(sqlite_session: AsyncSession):
    business_id = uuid4()
    result = await analyze(sqlite_session, business_id, query="What should I do today?")
    assert "memory_snapshot" in result
    assert "graph_evidence" in result
    assert "context_evidence" in result
    assert result["recent_event_count"] == 0
    assert result["decision"] is not None


@pytest.mark.asyncio
async def test_predict_sales_with_no_data(sqlite_session: AsyncSession):
    business_id = uuid4()
    result = await predict(sqlite_session, business_id, target="sales", horizon_days=7)
    assert result["target"] == "sales"
    assert result["horizon_days"] == 7
    assert result["predicted_value"] == 0.0
    assert result["basis"] == ["no_recent_data"]


@pytest.mark.asyncio
async def test_observe_ingests_event(sqlite_session: AsyncSession):
    business_id = uuid4()
    event = EventIngest(
        event_type="inventory.changed",
        source="test",
        source_id="inv-1",
        payload={"item_id": "milk", "new_quantity": 5.0},
    )
    record = await observe(sqlite_session, business_id, event)
    await sqlite_session.commit()
    assert record.event_type == "inventory.changed"
    assert record.processed is True


@pytest.mark.asyncio
async def test_remember_sets_memory(sqlite_session: AsyncSession):
    business_id = uuid4()
    memory = await remember(
        sqlite_session,
        business_id,
        "goals",
        operation="goal",
        goals={"target": "increase profit"},
    )
    await sqlite_session.commit()
    assert memory.memory_type == "goals"
    assert memory.data["goals"]["target"] == "increase profit"


@pytest.mark.asyncio
async def test_reason_returns_answer(sqlite_session: AsyncSession):
    business_id = uuid4()
    result = await reason(sqlite_session, business_id, "What should I order?")
    await sqlite_session.commit()
    assert result["answer"]
    assert result["decision"] is not None
    assert "sources" in result


@pytest.mark.asyncio
async def test_explain_decision(sqlite_session: AsyncSession):
    from app.services.intelligence_api import explain

    business_id = uuid4()
    decision = IntelligenceDecision(
        business_id=business_id,
        decision_type="restock",
        expected_roi=100.0,
        ranked_action={"action_type": "restock", "title": "Restock milk", "reasons": ["Low stock"]},
        confidence=0.85,
        explanation={"summary": "Test explanation", "primary_drivers": ["Low stock"]},
    )
    sqlite_session.add(decision)
    await sqlite_session.flush()

    result = await explain(sqlite_session, business_id, decision.id)
    assert result["decision_id"] == decision.id
    assert result["why"]
    assert result["ranked_action"] is not None


# ═══════════════════════════════════════════════════════════════════════════
# API integration tests (Postgres only)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_analyze_endpoint(authenticated_client: dict):
    ctx = authenticated_client
    client: AsyncClient = ctx["client"]
    business_id = ctx["business_id"]

    response = await client.post(
        f"/api/v1/intelligence/analyze?business_id={business_id}",
        json={"query": "What should I do today?", "decision_type": "inventory"},
        headers=ctx["headers"],
    )
    assert response.status_code == 201, response.text
    data = response.json()
    assert "summary" in data
    assert "decision" in data


@pytest.mark.asyncio
async def test_predict_endpoint(authenticated_client: dict):
    ctx = authenticated_client
    client: AsyncClient = ctx["client"]
    business_id = ctx["business_id"]

    response = await client.post(
        f"/api/v1/intelligence/predict?business_id={business_id}",
        json={"target": "sales", "horizon_days": 7},
        headers=ctx["headers"],
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["target"] == "sales"
    assert "predicted_value" in data


@pytest.mark.asyncio
async def test_reason_endpoint(authenticated_client: dict):
    ctx = authenticated_client
    client: AsyncClient = ctx["client"]
    business_id = ctx["business_id"]

    response = await client.post(
        f"/api/v1/intelligence/reason?business_id={business_id}",
        json={"question": "What should I order today?"},
        headers=ctx["headers"],
    )
    assert response.status_code == 201, response.text
    data = response.json()
    assert "answer" in data
    assert "decision" in data


@pytest.mark.asyncio
async def test_dashboard_intelligence_summary_endpoint(authenticated_client: dict):
    ctx = authenticated_client
    client: AsyncClient = ctx["client"]
    business_id = ctx["business_id"]

    response = await client.get(
        f"/api/v1/dashboard/intelligence-summary?business_id={business_id}",
        headers=ctx["headers"],
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert "summary" in data
    assert "sources" in data


@pytest.mark.asyncio
async def test_chat_reason_endpoint(authenticated_client: dict):
    ctx = authenticated_client
    client: AsyncClient = ctx["client"]
    business_id = ctx["business_id"]

    response = await client.post(
        f"/api/v1/chat/reason?business_id={business_id}",
        json={"message": "What should I order today?"},
        headers=ctx["headers"],
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert "answer" in data
    assert "decision" in data


@pytest.mark.asyncio
async def test_agent_reason_endpoint(authenticated_client: dict):
    ctx = authenticated_client
    client: AsyncClient = ctx["client"]
    business_id = ctx["business_id"]

    response = await client.post(
        f"/api/v1/agent/reason?business_id={business_id}",
        json={"question": "What should I focus on today?"},
        headers=ctx["headers"],
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert "answer" in data
    assert "sources" in data


@pytest.mark.asyncio
async def test_recovery_match_preview_intelligence(authenticated_client: dict):
    ctx = authenticated_client
    client: AsyncClient = ctx["client"]
    business_id = ctx["business_id"]

    response = await client.get(
        f"/api/v1/recovery-match/preview?business_id={business_id}",
        headers=ctx["headers"],
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert "opportunities" in data
    assert "intelligence_recommendations" in data
