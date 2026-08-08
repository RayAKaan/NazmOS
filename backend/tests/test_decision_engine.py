"""Tests for the Decision & Explainability Engine (Phase 4).

Postgres-dependent integration tests are skipped automatically when the test
database is unavailable. SQLite-backed integration tests run the decision
generation and explainability logic locally.
"""
from __future__ import annotations

from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database.models import Base, BusinessMemory, GraphEntity, GraphRelationship, IntelligenceDecision, MemoryType
from app.services.business_memory import set_memory_path
from app.services.decision_engine import explain_decision, generate_decision, get_decision


@pytest_asyncio.fixture(scope="function")
async def sqlite_session() -> AsyncSession:
    """In-memory SQLite session for decision engine tests."""
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
async def test_generate_decision_with_low_stock(sqlite_session: AsyncSession):
    business_id = uuid4()
    await set_memory_path(
        sqlite_session,
        business_id,
        MemoryType.CURRENT_STATE.value,
        "inventory.milk.stock",
        3.0,
    )
    await set_memory_path(
        sqlite_session,
        business_id,
        MemoryType.CURRENT_STATE.value,
        "inventory.milk.reorder_flag",
        True,
    )
    await sqlite_session.commit()

    decision = await generate_decision(sqlite_session, business_id, decision_type="inventory_optimization")
    await sqlite_session.commit()

    assert decision.decision_type == "inventory_optimization"
    assert decision.ranked_action is not None
    assert decision.confidence > 0
    assert decision.explanation is not None
    assert any("Restock" in str(a.get("title", "")) for a in decision.candidate_actions)


@pytest.mark.asyncio
async def test_generate_decision_pricing_signal(sqlite_session: AsyncSession):
    business_id = uuid4()
    await set_memory_path(
        sqlite_session,
        business_id,
        MemoryType.PATTERNS.value,
        "pricing.bread.history",
        [
            {"price": 10.0},
            {"price": 10.0},
            {"price": 11.5},
        ],
    )
    await sqlite_session.commit()

    decision = await generate_decision(sqlite_session, business_id, decision_type="pricing")
    await sqlite_session.commit()

    assert decision.ranked_action is not None
    titles = [a.get("title", "") for a in decision.candidate_actions]
    assert any("decreasing" in t or "increasing" in t for t in titles)


@pytest.mark.asyncio
async def test_generate_decision_with_graph_supplier_signal(sqlite_session: AsyncSession):
    business_id = uuid4()
    supplier = GraphEntity(
        business_id=business_id,
        entity_type="supplier",
        name="Supplier A",
        external_id="sup-a",
        attributes={},
    )
    product = GraphEntity(
        business_id=business_id,
        entity_type="product",
        name="Milk",
        external_id="sku-milk",
        attributes={},
    )
    sqlite_session.add(supplier)
    sqlite_session.add(product)
    await sqlite_session.flush()

    rel = GraphRelationship(
        business_id=business_id,
        source_id=supplier.id,
        target_id=product.id,
        relation_type="SUPPLIES",
        strength=0.2,
        evidence_event_ids=[],
    )
    sqlite_session.add(rel)
    await sqlite_session.commit()

    decision = await generate_decision(sqlite_session, business_id, decision_type="supplier")
    await sqlite_session.commit()

    titles = [a.get("title", "") for a in decision.candidate_actions]
    assert any("supplier" in t.lower() for t in titles)


@pytest.mark.asyncio
async def test_explain_decision(sqlite_session: AsyncSession):
    business_id = uuid4()
    decision = await generate_decision(sqlite_session, business_id, decision_type="general")
    await sqlite_session.commit()

    explanation = await explain_decision(sqlite_session, decision.id, business_id)
    assert explanation["decision_id"] == decision.id
    assert explanation["why"] != ""
    assert "evidence" in explanation


@pytest.mark.asyncio
async def test_get_decision(sqlite_session: AsyncSession):
    business_id = uuid4()
    decision = await generate_decision(sqlite_session, business_id)
    await sqlite_session.commit()

    fetched = await get_decision(sqlite_session, decision.id, business_id)
    assert fetched is not None
    assert fetched.id == decision.id


# ═══════════════════════════════════════════════════════════════════════════
# API integration tests (Postgres only)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_decision_generate_endpoint(authenticated_client: dict):
    ctx = authenticated_client
    client: AsyncClient = ctx["client"]
    business_id = ctx["business_id"]

    response = await client.post(
        f"/api/v1/intelligence/decisions/generate?business_id={business_id}",
        json={"decision_type": "inventory_optimization"},
        headers=ctx["headers"],
    )
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["decision_type"] == "inventory_optimization"
    assert "ranked_action" in data


@pytest.mark.asyncio
async def test_decision_explain_endpoint(authenticated_client: dict):
    ctx = authenticated_client
    client: AsyncClient = ctx["client"]
    business_id = ctx["business_id"]

    gen_resp = await client.post(
        f"/api/v1/intelligence/decisions/generate?business_id={business_id}",
        json={"decision_type": "general"},
        headers=ctx["headers"],
    )
    decision_id = gen_resp.json()["id"]

    response = await client.get(
        f"/api/v1/intelligence/decisions/{decision_id}/explain?business_id={business_id}",
        headers=ctx["headers"],
    )
    assert response.status_code == 200
    data = response.json()
    assert data["decision_id"] == decision_id
    assert "evidence" in data
