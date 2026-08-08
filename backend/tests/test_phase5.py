"""Tests for Phase 5: Agents, Planning, Simulation, Execution.

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

from app.database.models import Base, BusinessMemory, GraphEntity, MemoryType
from app.intelligence.agents.registry import dispatch_agent
from app.services.business_memory import set_memory_path
from app.services.execution_engine import execute_from_request, get_execution_job
from app.services.planning_engine import create_plan, get_plan
from app.services.simulation_engine import create_simulation, get_simulation


@pytest_asyncio.fixture(scope="function")
async def sqlite_session() -> AsyncSession:
    """In-memory SQLite session for Phase 5 tests."""
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
async def test_inventory_agent_proposes_restock(sqlite_session: AsyncSession):
    business_id = uuid4()
    await set_memory_path(sqlite_session, business_id, MemoryType.CURRENT_STATE.value, "inventory.milk.stock", 3.0)
    await set_memory_path(sqlite_session, business_id, MemoryType.CURRENT_STATE.value, "inventory.milk.reorder_flag", True)
    await sqlite_session.commit()

    result = await dispatch_agent(sqlite_session, business_id, "inventory")
    assert result["agent_type"] == "inventory"
    assert any(p["action_type"] == "restock" for p in result["payload"]["proposals"])


@pytest.mark.asyncio
async def test_pricing_agent_proposes_price_change(sqlite_session: AsyncSession):
    business_id = uuid4()
    await set_memory_path(
        sqlite_session,
        business_id,
        MemoryType.PATTERNS.value,
        "pricing.bread.history",
        [{"price": 10.0}, {"price": 10.0}, {"price": 11.5}],
    )
    await sqlite_session.commit()

    result = await dispatch_agent(sqlite_session, business_id, "pricing")
    assert result["agent_type"] == "pricing"
    assert len(result["payload"]["proposals"]) > 0


@pytest.mark.asyncio
async def test_create_plan_from_goal(sqlite_session: AsyncSession):
    business_id = uuid4()
    plan = await create_plan(sqlite_session, business_id, "Restock inventory")
    await sqlite_session.commit()

    assert plan.goal == "Restock inventory"
    assert len(plan.steps) > 0
    assert plan.status == "draft"


@pytest.mark.asyncio
async def test_create_price_simulation(sqlite_session: AsyncSession):
    business_id = uuid4()
    simulation = await create_simulation(
        sqlite_session,
        business_id,
        "10% price increase on bread",
        {"type": "price_change", "item_key": "bread", "price_delta_pct": 10.0},
    )
    await sqlite_session.commit()

    assert simulation.status == "completed"
    assert simulation.results is not None
    assert simulation.results["scenario_type"] == "price_change"


@pytest.mark.asyncio
async def test_execution_job_idempotency(sqlite_session: AsyncSession):
    business_id = uuid4()
    entity_id = uuid4()

    job1 = await execute_from_request(
        sqlite_session,
        business_id,
        "restock",
        "item",
        entity_id,
        {"quantity": 100},
    )
    await sqlite_session.commit()

    job2 = await execute_from_request(
        sqlite_session,
        business_id,
        "restock",
        "item",
        entity_id,
        {"quantity": 100},
    )
    await sqlite_session.commit()

    assert job1.id == job2.id
    assert job1.status == "completed"


@pytest.mark.asyncio
async def test_get_plan_and_simulation(sqlite_session: AsyncSession):
    business_id = uuid4()
    plan = await create_plan(sqlite_session, business_id, "Improve margins")
    simulation = await create_simulation(sqlite_session, business_id, "Test", {"type": "generic"})
    await sqlite_session.commit()

    fetched_plan = await get_plan(sqlite_session, plan.id, business_id)
    assert fetched_plan is not None

    fetched_sim = await get_simulation(sqlite_session, simulation.id, business_id)
    assert fetched_sim is not None


# ═══════════════════════════════════════════════════════════════════════════
# API integration tests (Postgres only)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_agent_propose_endpoint(authenticated_client: dict):
    ctx = authenticated_client
    client: AsyncClient = ctx["client"]
    business_id = ctx["business_id"]

    response = await client.post(
        f"/api/v1/intelligence/agents/propose?business_id={business_id}",
        json={"agent_type": "finance", "context": {}},
        headers=ctx["headers"],
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["agent_type"] == "finance"


@pytest.mark.asyncio
async def test_plan_endpoint(authenticated_client: dict):
    ctx = authenticated_client
    client: AsyncClient = ctx["client"]
    business_id = ctx["business_id"]

    response = await client.post(
        f"/api/v1/intelligence/plans?business_id={business_id}",
        json={"goal": "Restock inventory"},
        headers=ctx["headers"],
    )
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["goal"] == "Restock inventory"
    assert len(data["steps"]) > 0


@pytest.mark.asyncio
async def test_simulate_endpoint(authenticated_client: dict):
    ctx = authenticated_client
    client: AsyncClient = ctx["client"]
    business_id = ctx["business_id"]

    response = await client.post(
        f"/api/v1/intelligence/simulate?business_id={business_id}",
        json={
            "name": "Test discount",
            "scenario": {"type": "discount", "item_key": "milk", "discount_pct": 15},
        },
        headers=ctx["headers"],
    )
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["status"] == "completed"
    assert data["results"] is not None
