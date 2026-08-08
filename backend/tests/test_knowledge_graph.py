"""Tests for the Knowledge Graph Engine (Phase 2).

Postgres-dependent integration tests are skipped automatically when the test
database is unavailable. SQLite-backed integration tests run the projector,
expand, and shortest-path logic locally.
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database.models import Base, Event, GraphEntity, GraphRelationship
from app.services.knowledge_graph import (
    expand_graph,
    get_entity,
    route_event_to_graph_projectors,
    shortest_path,
    upsert_entity,
    upsert_relationship,
)


@pytest_asyncio.fixture(scope="function")
async def sqlite_session() -> AsyncSession:
    """In-memory SQLite session for graph projector/query tests."""
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
async def test_upsert_entity_creates_and_updates(sqlite_session: AsyncSession):
    business_id = uuid4()
    entity = await upsert_entity(sqlite_session, business_id, "product", "Milk", external_id="sku-1")
    await sqlite_session.commit()
    assert entity.entity_type == "product"
    assert entity.name == "Milk"

    updated = await upsert_entity(sqlite_session, business_id, "product", "Almarai Milk", external_id="sku-1")
    await sqlite_session.commit()
    assert updated.id == entity.id
    assert updated.name == "Almarai Milk"


@pytest.mark.asyncio
async def test_upsert_relationship_strengthens(sqlite_session: AsyncSession):
    business_id = uuid4()
    a = await upsert_entity(sqlite_session, business_id, "product", "A", external_id="a")
    b = await upsert_entity(sqlite_session, business_id, "product", "B", external_id="b")
    rel1 = await upsert_relationship(sqlite_session, business_id, a.id, b.id, "RELATED", strength_delta=0.1)
    rel2 = await upsert_relationship(sqlite_session, business_id, a.id, b.id, "RELATED", strength_delta=0.1)
    await sqlite_session.commit()
    assert rel1.id == rel2.id
    assert float(rel2.strength) == pytest.approx(0.7)


@pytest.mark.asyncio
async def test_sale_completed_projector(sqlite_session: AsyncSession):
    business_id = uuid4()
    event = Event(
        id=uuid4(),
        business_id=business_id,
        event_type="sale.completed",
        source="pos",
        source_id="order-1",
        payload={
            "items": [
                {"item_id": "sku-1", "name": "Milk"},
                {"item_id": "sku-2", "name": "Bread"},
            ],
            "branch_id": "branch-1",
        },
        checksum="x",
        occurred_at=datetime.now(timezone.utc),
    )
    sqlite_session.add(event)
    await sqlite_session.flush()

    await route_event_to_graph_projectors(sqlite_session, event)
    await sqlite_session.commit()

    entities = (await sqlite_session.execute(select(GraphEntity).where(GraphEntity.business_id == business_id))).scalars().all()
    types = {e.entity_type for e in entities}
    assert "product" in types
    assert "branch" in types

    rels = (await sqlite_session.execute(select(GraphRelationship).where(GraphRelationship.business_id == business_id))).scalars().all()
    assert any(r.relation_type == "SOLD_MOSTLY_AT" for r in rels)


@pytest.mark.asyncio
async def test_expand_graph(sqlite_session: AsyncSession):
    business_id = uuid4()
    a = await upsert_entity(sqlite_session, business_id, "product", "A", external_id="a")
    b = await upsert_entity(sqlite_session, business_id, "product", "B", external_id="b")
    c = await upsert_entity(sqlite_session, business_id, "product", "C", external_id="c")
    await upsert_relationship(sqlite_session, business_id, a.id, b.id, "RELATED")
    await upsert_relationship(sqlite_session, business_id, b.id, c.id, "RELATED")
    await sqlite_session.commit()

    result = await expand_graph(sqlite_session, a.id, business_id, depth=2)
    assert result["root"].id == a.id
    assert len(result["entities"]) == 3
    assert len(result["edges"]) == 2


@pytest.mark.asyncio
async def test_shortest_path(sqlite_session: AsyncSession):
    business_id = uuid4()
    a = await upsert_entity(sqlite_session, business_id, "product", "A", external_id="a")
    b = await upsert_entity(sqlite_session, business_id, "product", "B", external_id="b")
    c = await upsert_entity(sqlite_session, business_id, "product", "C", external_id="c")
    await upsert_relationship(sqlite_session, business_id, a.id, b.id, "RELATED")
    await upsert_relationship(sqlite_session, business_id, b.id, c.id, "RELATED")
    await sqlite_session.commit()

    result = await shortest_path(sqlite_session, a.id, c.id, business_id, max_depth=5)
    assert result["found"] is True
    assert len(result["path"]) == 3
    assert result["distance"] == 2


@pytest.mark.asyncio
async def test_shortest_path_not_found(sqlite_session: AsyncSession):
    business_id = uuid4()
    a = await upsert_entity(sqlite_session, business_id, "product", "A", external_id="a")
    b = await upsert_entity(sqlite_session, business_id, "product", "B", external_id="b")
    await sqlite_session.commit()

    result = await shortest_path(sqlite_session, a.id, b.id, business_id, max_depth=3)
    assert result["found"] is False


# ═══════════════════════════════════════════════════════════════════════════
# API integration tests (Postgres only)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_graph_entity_endpoint(authenticated_client: dict):
    ctx = authenticated_client
    client: AsyncClient = ctx["client"]
    business_id = ctx["business_id"]

    response = await client.post(
        f"/api/v1/intelligence/graph/entities?business_id={business_id}",
        json={"entity_type": "product", "name": "Milk", "external_id": "sku-milk"},
        headers=ctx["headers"],
    )
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["entity_type"] == "product"
    assert data["external_id"] == "sku-milk"


@pytest.mark.asyncio
async def test_graph_expand_endpoint(authenticated_client: dict):
    ctx = authenticated_client
    client: AsyncClient = ctx["client"]
    business_id = ctx["business_id"]

    a_resp = await client.post(
        f"/api/v1/intelligence/graph/entities?business_id={business_id}",
        json={"entity_type": "product", "name": "A", "external_id": "a"},
        headers=ctx["headers"],
    )
    a_id = a_resp.json()["id"]

    b_resp = await client.post(
        f"/api/v1/intelligence/graph/entities?business_id={business_id}",
        json={"entity_type": "product", "name": "B", "external_id": "b"},
        headers=ctx["headers"],
    )
    b_id = b_resp.json()["id"]

    rel_resp = await client.post(
        f"/api/v1/intelligence/graph/relationships?business_id={business_id}",
        json={"source_id": a_id, "target_id": b_id, "relation_type": "RELATED"},
        headers=ctx["headers"],
    )
    assert rel_resp.status_code == 201

    expand_resp = await client.get(
        f"/api/v1/intelligence/graph/expand?business_id={business_id}&entity_id={a_id}&depth=2",
        headers=ctx["headers"],
    )
    assert expand_resp.status_code == 200
    data = expand_resp.json()
    assert data["root"]["id"] == a_id
    assert len(data["entities"]) == 2
