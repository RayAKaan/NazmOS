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
    """  # nosec B608
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


async def _project_price_updated(session: AsyncSession, event: Event) -> None:
    """Project a supplier price change: supplier → product (SUPPLIES) + product → supplier
    (SUPPLIED_BY), so margin/price changes are traceable in the graph."""
    payload = event.payload or {}
    supplier_id = payload.get("supplier_id")
    item_id = payload.get("item_id") or payload.get("sku")
    item_name = payload.get("item_name") or item_id
    if not item_id:
        return
    product = await upsert_entity(session, event.business_id, "product", name=str(item_name),
                                  external_id=str(item_id))
    if supplier_id:
        supplier = await upsert_entity(session, event.business_id, "supplier", name=str(supplier_id),
                                       external_id=str(supplier_id))
        await upsert_relationship(session, event.business_id, supplier.id, product.id, "SUPPLIES",
                                  strength_delta=0.1, evidence_event_id=str(event.id))


async def _project_inventory_changed(session: AsyncSession, event: Event) -> None:
    """Project a stock change: branch → product (STOCKS) + product → category (BELONGS_TO,
    §15 — only when the ledger has a real category for the item)."""
    payload = event.payload or {}
    item_id = payload.get("item_id") or payload.get("sku")
    item_name = payload.get("item_name") or item_id
    branch_id = payload.get("branch_id") or payload.get("business_id")
    if not item_id:
        return
    product = await upsert_entity(session, event.business_id, "product", name=str(item_name),
                                  external_id=str(item_id))
    if branch_id:
        branch = await upsert_entity(session, event.business_id, "branch", name=str(branch_id),
                                     external_id=str(branch_id))
        await upsert_relationship(session, event.business_id, branch.id, product.id, "STOCKS",
                                  strength_delta=0.05, evidence_event_id=str(event.id))

    # product → category (real evidence from the items/categories ledger).
    from sqlalchemy import text
    cat = await session.execute(text("""
        SELECT c.id, c.name FROM categories c
        JOIN items i ON i.category_id = c.id
        WHERE i.id = :item AND i.business_id = :b
        LIMIT 1
    """), {"item": str(item_id), "b": str(event.business_id)})
    crow = cat.fetchone()
    if crow:
        category = await upsert_entity(session, event.business_id, "category", name=crow.name,
                                       external_id=str(crow.id))
        await upsert_relationship(session, event.business_id, product.id, category.id, "BELONGS_TO",
                                  strength_delta=0.1, evidence_event_id=str(event.id))


async def _project_transfer_completed(session: AsyncSession, event: Event) -> None:
    """Project an inter-branch transfer: from-branch → to-branch (NEAR) + both stock product."""
    payload = event.payload or {}
    from_branch = payload.get("from_business_id")
    to_branch = payload.get("to_business_id")
    item_id = payload.get("item_id")
    item_name = payload.get("item_name") or item_id
    if from_branch and to_branch:
        f = await upsert_entity(session, event.business_id, "branch", name=str(from_branch),
                                external_id=str(from_branch))
        t = await upsert_entity(session, event.business_id, "branch", name=str(to_branch),
                                external_id=str(to_branch))
        # A completed transfer is concrete evidence the two branches trade stock.
        await upsert_relationship(session, event.business_id, f.id, t.id, "TRADES_STOCK_WITH",
                                  strength_delta=0.1, evidence_event_id=str(event.id))
    if item_id:
        product = await upsert_entity(session, event.business_id, "product", name=str(item_name),
                                      external_id=str(item_id))
        for branch_id in (from_branch, to_branch):
            if branch_id:
                branch = await upsert_entity(session, event.business_id, "branch", name=str(branch_id),
                                             external_id=str(branch_id))
                await upsert_relationship(session, event.business_id, branch.id, product.id, "STOCKS",
                                          strength_delta=0.05, evidence_event_id=str(event.id))


async def _project_finding_created(session: AsyncSession, event: Event) -> None:
    """Project a finding: finding → product/branch (AFFECTS), from the finding's
    affected_entities + category/domain."""
    payload = event.payload or {}
    finding_id = payload.get("finding_id")
    if not finding_id:
        return
    finding = await upsert_entity(session, event.business_id, "finding", name=str(finding_id),
                                  external_id=str(finding_id),
                                  attributes={"title": payload.get("title"), "domain": payload.get("domain"),
                                              "category": payload.get("category"),
                                              "severity": payload.get("severity")})
    for ent in payload.get("affected_entities") or []:
        etype = ent.get("type")
        eid = ent.get("id") or ent.get("name")
        if not eid:
            continue
        target = await upsert_entity(session, event.business_id, etype if etype else "entity",
                                     name=str(eid), external_id=str(eid))
        await upsert_relationship(session, event.business_id, finding.id, target.id, "AFFECTS",
                                  strength_delta=0.1, evidence_event_id=str(event.id))


async def _project_action_completed(session: AsyncSession, event: Event) -> None:
    """Project an executed action: finding → action (RECOMMENDS) and action → product
    (TARGETS), forming the finding→action→outcome chain (§9)."""
    payload = event.payload or {}
    action_id = payload.get("action_id")
    finding_id = payload.get("finding_id")
    if not action_id:
        return
    action = await upsert_entity(session, event.business_id, "action", name=str(action_id),
                                 external_id=str(action_id),
                                 attributes={"action_type": payload.get("action_type"),
                                             "status": payload.get("status", "completed")})
    if finding_id:
        finding = await upsert_entity(session, event.business_id, "finding", name=str(finding_id),
                                      external_id=str(finding_id))
        await upsert_relationship(session, event.business_id, finding.id, action.id, "RECOMMENDS",
                                  strength_delta=0.1, evidence_event_id=str(event.id))
    for ent in payload.get("targets") or []:
        target = await upsert_entity(session, event.business_id, ent.get("type", "entity"),
                                     name=str(ent.get("id") or ent.get("name")),
                                     external_id=str(ent.get("id")))
        await upsert_relationship(session, event.business_id, action.id, target.id, "TARGETS",
                                  strength_delta=0.1, evidence_event_id=str(event.id))

    # action → outcome (PRODUCES, §15): the outcome is a structured, evidence-backed result.
    if payload.get("executed") is not None or payload.get("outcome"):
        outcome = await upsert_entity(
            session, event.business_id, "outcome",
            name=f"outcome-{payload.get('action_id')}",
            external_id=str(payload.get("action_id")),
            attributes={"executed": payload.get("executed"), "outcome": payload.get("outcome")},
        )
        await upsert_relationship(session, event.business_id, action.id, outcome.id, "PRODUCES",
                                  strength_delta=0.1, evidence_event_id=str(event.id))


async def _project_supplier_price_changed(session: AsyncSession, event: Event) -> None:
    """Project a supplier-price observation: supplier → price entity (HAS_PRICE)."""
    payload = event.payload or {}
    price_id = payload.get("price_id")
    supplier_id = payload.get("supplier_id")
    if not price_id or not supplier_id:
        return
    price = await upsert_entity(session, event.business_id, "price", name=str(price_id),
                                external_id=str(price_id),
                                attributes={"unit_price_sar": payload.get("unit_price_sar")})
    supplier = await upsert_entity(session, event.business_id, "supplier", name=str(supplier_id),
                                   external_id=str(supplier_id))
    await upsert_relationship(session, event.business_id, supplier.id, price.id, "HAS_PRICE",
                              strength_delta=0.1, evidence_event_id=str(event.id))


async def project_finding_to_graph(
    session: AsyncSession,
    business_id: UUID | str,
    finding_id: UUID | str,
    *,
    domain: str,
    category: str,
    severity: str,
    title: str,
    affected_entities: list[dict[str, Any]] | None = None,
) -> None:
    """Directly project a finding into the KG at creation time (§15). The finding is born
    in the audit engine (not from an external event), so it is projected here rather than
    through the event bus — the graph edges are identical to the `finding.created` projector."""
    finding = await upsert_entity(
        session, business_id, "finding", name=str(finding_id), external_id=str(finding_id),
        attributes={"title": title, "domain": domain, "category": category, "severity": severity},
    )
    for ent in affected_entities or []:
        etype = ent.get("type")
        eid = ent.get("id") or ent.get("name")
        if not eid:
            continue
        target = await upsert_entity(session, business_id, etype if etype else "entity",
                                     name=str(eid), external_id=str(eid))
        await upsert_relationship(session, business_id, finding.id, target.id, "AFFECTS",
                                  strength_delta=0.1, evidence_event_id=f"finding:{finding_id}")


async def project_action_to_graph(
    session: AsyncSession,
    business_id: UUID | str,
    action_id: UUID | str,
    *,
    action_type: str,
    status: str,
    executed: bool | None = None,
    outcome: dict[str, Any] | None = None,
    finding_id: UUID | str | None = None,
    targets: list[dict[str, Any]] | None = None,
) -> None:
    """Directly project an executed action into the KG (finding → action RECOMMENDS, action →
    product TARGETS, action → outcome PRODUCES). Idempotent via upsert."""
    action = await upsert_entity(session, business_id, "action", name=str(action_id),
                                 external_id=str(action_id),
                                 attributes={"action_type": action_type, "status": status})
    if finding_id:
        finding = await upsert_entity(session, business_id, "finding", name=str(finding_id),
                                      external_id=str(finding_id))
        await upsert_relationship(session, business_id, finding.id, action.id, "RECOMMENDS",
                                  strength_delta=0.1, evidence_event_id=f"action:{action_id}")
    for ent in targets or []:
        target = await upsert_entity(session, business_id, ent.get("type", "entity"),
                                     name=str(ent.get("id") or ent.get("name")),
                                     external_id=str(ent.get("id")))
        await upsert_relationship(session, business_id, action.id, target.id, "TARGETS",
                                  strength_delta=0.1, evidence_event_id=f"action:{action_id}")
    if executed is not None:
        outcome_ent = await upsert_entity(
            session, business_id, "outcome", name=f"outcome-{action_id}",
            external_id=str(action_id), attributes={"executed": executed, "outcome": outcome},
        )
        await upsert_relationship(session, business_id, action.id, outcome_ent.id, "PRODUCES",
                                  strength_delta=0.1, evidence_event_id=f"action:{action_id}")


_GRAPH_PROJECTOR_MAP: dict[str, Any] = {
    "supplier.delivered": _project_supplier_delivered,
    "sale.completed": _project_sale_completed,
    "employee.clock_in": _project_employee_clock_in,
    "price.updated": _project_price_updated,
    "inventory.changed": _project_inventory_changed,
    "transfer.completed": _project_transfer_completed,
    "finding.created": _project_finding_created,
    "action.completed": _project_action_completed,
    "supplier_price.changed": _project_supplier_price_changed,
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
