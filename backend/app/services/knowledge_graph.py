"""Knowledge Graph Engine service (Phase 2).

Models the business as a connected graph of entities and relationships in
PostgreSQL (relational tables + recursive CTEs). The abstraction is kept
storage-agnostic so Apache AGE or Neo4j can be swapped in later.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Event, GraphEntity, GraphRelationship
from app.utils.logger import setup_logger

logger = setup_logger("knowledge_graph")


def _to_uuid(value: UUID | str) -> UUID:
    if isinstance(value, UUID):
        return value
    return UUID(value)


async def upsert_entity(
    session: AsyncSession,
    business_id: UUID | str,
    entity_type: str,
    name: str,
    external_id: str | None = None,
    attributes: dict[str, Any] | None = None,
    vector: list[float] | None = None,
) -> GraphEntity:
    """Create or update a graph entity."""
    business_id = _to_uuid(business_id)
    result = await session.execute(
        select(GraphEntity).where(
            GraphEntity.business_id == business_id,
            GraphEntity.entity_type == entity_type,
            GraphEntity.external_id == external_id,
        )
    )
    entity = result.scalar_one_or_none()
    if entity is None:
        entity = GraphEntity(
            business_id=business_id,
            entity_type=entity_type,
            external_id=external_id,
            name=name,
            attributes=attributes or {},
            vector=vector,
        )
        session.add(entity)
    else:
        entity.name = name
        if attributes is not None:
            entity.attributes = attributes
        if vector is not None:
            entity.vector = vector
        entity.updated_at = datetime.now(timezone.utc)
    await session.flush()
    return entity


async def get_entity(
    session: AsyncSession,
    entity_id: UUID | str,
    business_id: UUID | str | None = None,
) -> GraphEntity | None:
    """Fetch a single entity, optionally scoped to a business."""
    query = select(GraphEntity).where(GraphEntity.id == _to_uuid(entity_id))
    if business_id is not None:
        query = query.where(GraphEntity.business_id == _to_uuid(business_id))
    result = await session.execute(query)
    return result.scalar_one_or_none()


async def upsert_relationship(
    session: AsyncSession,
    business_id: UUID | str,
    source_id: UUID | str,
    target_id: UUID | str,
    relation_type: str,
    strength_delta: float = 0.1,
    evidence_event_id: str | None = None,
    valid_from: datetime | None = None,
    valid_until: datetime | None = None,
) -> GraphRelationship:
    """Create or strengthen a relationship and append evidence."""
    business_id = _to_uuid(business_id)
    source_id = _to_uuid(source_id)
    target_id = _to_uuid(target_id)

    result = await session.execute(
        select(GraphRelationship).where(
            GraphRelationship.business_id == business_id,
            GraphRelationship.source_id == source_id,
            GraphRelationship.target_id == target_id,
            GraphRelationship.relation_type == relation_type,
        )
    )
    rel = result.scalar_one_or_none()
    if rel is None:
        rel = GraphRelationship(
            business_id=business_id,
            source_id=source_id,
            target_id=target_id,
            relation_type=relation_type,
            strength=min(1.0, 0.5 + strength_delta),
            evidence_event_ids=[evidence_event_id] if evidence_event_id else [],
            valid_from=valid_from or datetime.now(timezone.utc),
            valid_until=valid_until,
        )
        session.add(rel)
    else:
        rel.strength = min(1.0, float(rel.strength or 0.0) + strength_delta)
        evidence = list(rel.evidence_event_ids or [])
        if evidence_event_id and evidence_event_id not in evidence:
            evidence.append(evidence_event_id)
            rel.evidence_event_ids = evidence
        rel.updated_at = datetime.now(timezone.utc)
        if valid_from:
            rel.valid_from = valid_from
        if valid_until is not None:
            rel.valid_until = valid_until
    await session.flush()
    return rel


async def expand_graph(
    session: AsyncSession,
    root_entity_id: UUID | str,
    business_id: UUID | str,
    depth: int = 2,
    relation_type: str | None = None,
) -> dict[str, Any]:
    """Expand the graph around a root entity using a recursive CTE.

    Returns {root, depth, entities: [...], edges: [...]}.
    """
    business_id = _to_uuid(business_id)
    root_entity_id = _to_uuid(root_entity_id)

    # Fetch root entity first to return a stable root object and validate access.
    root = await get_entity(session, root_entity_id, business_id)
    if not root:
        return {"root": None, "depth": depth, "entities": [], "edges": []}

    relation_filter = ""
    params = {
        "business_id": str(business_id),
        "root_id": str(root_entity_id),
        "depth": depth,
    }
    if relation_type:
        relation_filter = "AND r.relation_type = :relation_type"
        params["relation_type"] = relation_type

    # Recursive CTE: traverse edges in both directions up to max depth.
    cte_sql = f"""
    WITH RECURSIVE traversal AS (
        SELECT
            g.id AS entity_id,
            0 AS hops,
            CAST(g.id AS VARCHAR) AS path
        FROM graph_entities g
        WHERE g.id = :root_id AND g.business_id = :business_id

        UNION

        SELECT
            CASE
                WHEN t.entity_id = r.source_id THEN r.target_id
                ELSE r.source_id
            END AS entity_id,
            t.hops + 1 AS hops,
            t.path || ',' || CAST(CASE
                WHEN t.entity_id = r.source_id THEN r.target_id
                ELSE r.source_id
            END AS VARCHAR)
        FROM traversal t
        JOIN graph_relationships r
            ON (t.entity_id = r.source_id OR t.entity_id = r.target_id)
            AND r.business_id = :business_id
            {relation_filter}
        WHERE t.hops < :depth
            AND t.path NOT LIKE '%' || CAST(CASE
                WHEN t.entity_id = r.source_id THEN r.target_id
                ELSE r.source_id
            END AS VARCHAR) || '%'
    )
    SELECT DISTINCT entity_id, hops FROM traversal ORDER BY hops
    """
    result = await session.execute(text(cte_sql), params)
    rows = result.fetchall()

    entity_ids = {row[0] for row in rows}
    if not entity_ids:
        return {"root": root, "depth": depth, "entities": [root], "edges": []}

    entities_result = await session.execute(
        select(GraphEntity).where(GraphEntity.id.in_(entity_ids))
    )
    entities = {str(e.id): e for e in entities_result.scalars().all()}

    # Fetch edges among the discovered entity set.
    edges_result = await session.execute(
        select(GraphRelationship).where(
            GraphRelationship.business_id == business_id,
            GraphRelationship.source_id.in_(entity_ids),
            GraphRelationship.target_id.in_(entity_ids),
        )
    )
    edges = edges_result.scalars().all()

    return {
        "root": root,
        "depth": depth,
        "entities": list(entities.values()),
        "edges": edges,
    }


async def shortest_path(
    session: AsyncSession,
    from_entity_id: UUID | str,
    to_entity_id: UUID | str,
    business_id: UUID | str,
    max_depth: int = 6,
) -> dict[str, Any]:
    """Find the shortest path between two entities using a BFS recursive CTE."""
    business_id = _to_uuid(business_id)
    from_entity_id = _to_uuid(from_entity_id)
    to_entity_id = _to_uuid(to_entity_id)

    sql = """
    WITH RECURSIVE path_search AS (
        SELECT
            r.source_id AS start_id,
            r.target_id AS end_id,
            r.id AS rel_id,
            1 AS hops,
            CAST(r.source_id AS VARCHAR) || ',' || CAST(r.target_id AS VARCHAR) AS path
        FROM graph_relationships r
        WHERE r.business_id = :business_id
            AND (r.source_id = :from_id OR r.target_id = :from_id)

        UNION ALL

        SELECT
            ps.start_id,
            CASE
                WHEN ps.end_id = r.source_id THEN r.target_id
                ELSE r.source_id
            END AS end_id,
            r.id AS rel_id,
            ps.hops + 1 AS hops,
            ps.path || ',' || CAST(CASE
                WHEN ps.end_id = r.source_id THEN r.target_id
                ELSE r.source_id
            END AS VARCHAR)
        FROM path_search ps
        JOIN graph_relationships r
            ON (ps.end_id = r.source_id OR ps.end_id = r.target_id)
            AND r.business_id = :business_id
        WHERE ps.hops < :max_depth
            AND ps.path NOT LIKE '%' || CAST(CASE
                WHEN ps.end_id = r.source_id THEN r.target_id
                ELSE r.source_id
            END AS VARCHAR) || '%'
    )
    SELECT path, rel_id, hops FROM path_search
    WHERE end_id = :to_id
    ORDER BY hops
    LIMIT 1
    """
    result = await session.execute(
        text(sql),
        {
            "business_id": str(business_id),
            "from_id": str(from_entity_id),
            "to_id": str(to_entity_id),
            "max_depth": max_depth,
        },
    )
    row = result.fetchone()
    if not row:
        return {"found": False, "path": [], "edges": [], "distance": 0}

    path_ids = [UUID(pid) for pid in row[0].split(",")]
    rel_ids = [row[1]]
    # If hops > 1, the CTE only returns the last edge id. Reconstruct full edge
    # list by fetching all edges among the path nodes.
    edges_result = await session.execute(
        select(GraphRelationship).where(
            GraphRelationship.business_id == business_id,
            GraphRelationship.source_id.in_(path_ids),
            GraphRelationship.target_id.in_(path_ids),
        )
    )
    edges = edges_result.scalars().all()

    entities_result = await session.execute(
        select(GraphEntity).where(GraphEntity.id.in_(path_ids))
    )
    entity_map = {str(e.id): e for e in entities_result.scalars().all()}
    path_entities = [entity_map[str(pid)] for pid in path_ids if str(pid) in entity_map]

    return {
        "found": True,
        "path": path_entities,
        "edges": edges,
        "distance": row[2],
    }


# ═══════════════════════════════════════════════════════════════════════════
# Event projectors
# ═══════════════════════════════════════════════════════════════════════════

async def _project_supplier_delivered(session: AsyncSession, event: Event) -> None:
    payload = event.payload or {}
    supplier_id = payload.get("supplier_id")
    items = payload.get("items", []) or []
    if not supplier_id:
        return

    supplier = await upsert_entity(
        session,
        event.business_id,
        "supplier",
        name=str(supplier_id),
        external_id=str(supplier_id),
        attributes={"last_delivery_at": payload.get("delivered_at") or (event.occurred_at.isoformat() if event.occurred_at else None)},
    )

    for item in items:
        item_id = item.get("item_id") or item.get("sku")
        item_name = item.get("name") or item_id
        if not item_id:
            continue
        product = await upsert_entity(
            session,
            event.business_id,
            "product",
            name=str(item_name),
            external_id=str(item_id),
            attributes={"last_supplier_delivery_at": event.occurred_at.isoformat() if event.occurred_at else None},
        )
        await upsert_relationship(
            session,
            event.business_id,
            supplier.id,
            product.id,
            "SUPPLIES",
            strength_delta=0.1,
            evidence_event_id=str(event.id),
        )


async def _project_sale_completed(session: AsyncSession, event: Event) -> None:
    payload = event.payload or {}
    items = payload.get("items", []) or []
    branch_id = payload.get("branch_id")

    branch = None
    if branch_id:
        branch = await upsert_entity(
            session,
            event.business_id,
            "branch",
            name=str(branch_id),
            external_id=str(branch_id),
        )

    for item in items:
        item_id = item.get("item_id") or item.get("sku")
        item_name = item.get("name") or item_id
        if not item_id:
            continue
        product = await upsert_entity(
            session,
            event.business_id,
            "product",
            name=str(item_name),
            external_id=str(item_id),
        )
        if branch:
            await upsert_relationship(
                session,
                event.business_id,
                product.id,
                branch.id,
                "SOLD_MOSTLY_AT",
                strength_delta=0.05,
                evidence_event_id=str(event.id),
            )


async def _project_employee_clock_in(session: AsyncSession, event: Event) -> None:
    payload = event.payload or {}
    employee_id = payload.get("employee_id")
    branch_id = payload.get("branch_id")
    if not employee_id or not branch_id:
        return

    employee = await upsert_entity(
        session,
        event.business_id,
        "employee",
        name=str(employee_id),
        external_id=str(employee_id),
    )
    branch = await upsert_entity(
        session,
        event.business_id,
        "branch",
        name=str(branch_id),
        external_id=str(branch_id),
    )
    await upsert_relationship(
        session,
        event.business_id,
        employee.id,
        branch.id,
        "WORKS_AT",
        strength_delta=0.1,
        evidence_event_id=str(event.id),
    )


_GRAPH_PROJECTOR_MAP: dict[str, Any] = {
    "supplier.delivered": _project_supplier_delivered,
    "sale.completed": _project_sale_completed,
    "employee.clock_in": _project_employee_clock_in,
}


async def route_event_to_graph_projectors(session: AsyncSession, event: Event) -> None:
    """Dispatch an event to all graph projectors that understand its type."""
    projector = _GRAPH_PROJECTOR_MAP.get(event.event_type)
    if projector is None:
        return
    await projector(session, event)
    logger.info(
        "Graph projection applied",
        extra={
            "event_id": str(event.id),
            "event_type": event.event_type,
            "business_id": str(event.business_id),
        },
    )
