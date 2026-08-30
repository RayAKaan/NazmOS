"""Graph-aware agent context (Phase 4, §10).

Builds a *targeted* connected context for an agent investigating a finding — never a
dump of the whole graph. For a finding, it returns the affected entities, their
relationships (supplier, price, category, previous actions, outcomes) so the agent can
reason from connected business context instead of isolated API calls.

Correlation is never presented as causality (§11): edges carry evidence, not conclusions.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def finding_graph_context(db: AsyncSession, business_id: UUID | str, finding_id: UUID | str) -> dict[str, Any]:
    """Return the connected context for a finding (bounded, tenant-scoped)."""
    res = await db.execute(text("""
        SELECT e.id, e.entity_type, e.name, e.attributes
        FROM graph_entities e
        WHERE e.business_id = :b AND e.entity_type = 'finding' AND e.external_id = :fid
        LIMIT 1
    """), {"b": str(business_id), "fid": str(finding_id)})
    row = res.fetchone()
    if not row:
        return {"finding": None, "context": []}

    entity_id = str(row.id)

    # One-hop neighborhood (both directions) — bounded, never the full graph.
    rels = await db.execute(text("""
        SELECT r.relation_type,
               src.entity_type AS source_type, src.name AS source_name, src.attributes AS source_attrs,
               tgt.entity_type AS target_type, tgt.name AS target_name, tgt.attributes AS target_attrs,
               r.strength, r.evidence_event_ids
        FROM graph_relationships r
        JOIN graph_entities src ON src.id = r.source_id
        JOIN graph_entities tgt ON tgt.id = r.target_id
        WHERE r.business_id = :b AND (r.source_id = :eid OR r.target_id = :eid)
        LIMIT 40
    """), {"b": str(business_id), "eid": entity_id})

    context = []
    for r in rels.fetchall():
        context.append({
            "relation": r.relation_type,
            "from": {"type": r.source_type, "name": r.source_name, "attributes": r.source_attrs},
            "to": {"type": r.target_type, "name": r.target_name, "attributes": r.target_attrs},
            "strength": float(r.strength or 0),
            "evidence_event_ids": r.evidence_event_ids if isinstance(r.evidence_event_ids, list) else [],
        })

    return {
        "finding": {"id": finding_id, "name": row.name, "type": row.entity_type, "attributes": row.attributes},
        "context": context,
        "note": "Edges are observed relationships with evidence, not causal conclusions.",
    }


async def product_graph_context(db: AsyncSession, business_id: UUID | str, item_id: UUID | str) -> dict[str, Any]:
    """Connected context for a product (supplier, prices, category, findings, actions)."""
    res = await db.execute(text("""
        SELECT id FROM graph_entities
        WHERE business_id = :b AND entity_type = 'product' AND external_id = :iid LIMIT 1
    """), {"b": str(business_id), "iid": str(item_id)})
    row = res.fetchone()
    if not row:
        return {"product": None, "context": []}

    entity_id = str(row.id)
    rels = await db.execute(text("""
        SELECT r.relation_type,
               src.entity_type AS source_type, src.name AS source_name,
               tgt.entity_type AS target_type, tgt.name AS target_name,
               r.strength
        FROM graph_relationships r
        JOIN graph_entities src ON src.id = r.source_id
        JOIN graph_entities tgt ON tgt.id = r.target_id
        WHERE r.business_id = :b AND (r.source_id = :eid OR r.target_id = :eid)
        LIMIT 40
    """), {"b": str(business_id), "eid": entity_id})

    context = [
        {
            "relation": r.relation_type,
            "from": r.source_type, "to": r.target_type,
            "name": r.source_name if r.source_type != "product" else r.target_name,
            "strength": float(r.strength or 0),
        }
        for r in rels.fetchall()
    ]
    return {"product": str(item_id), "context": context}
