"""Unified Intelligence API service (Phase 7).

This module consolidates all intelligence engines behind a single typed surface
so that NazmOS applications (Dashboard, Money Audit, Recovery Match, Chat,
WhatsApp, etc.) can consume intelligence without directly importing individual
engine modules.
"""
from __future__ import annotations
from app.utils.clock import utcnow

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import (
    BusinessMemory,
    Event,
    GraphEntity,
    GraphRelationship,
    MemoryType,
)
from app.schemas.events import EventIngest
from app.services import business_memory
from app.services import context_engine
from app.services import decision_engine
from app.services import event_engine
from app.services import execution_engine
from app.services import planning_engine
from app.services import simulation_engine
from app.utils.logger import setup_logger

logger = setup_logger("intelligence_api")


def _to_uuid(value: UUID | str) -> UUID:
    if isinstance(value, UUID):
        return value
    return UUID(value)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _memory_types() -> list[str]:
    return [m.value for m in MemoryType]


async def _load_memory_snapshot(session: AsyncSession, business_id: UUID) -> dict[str, Any]:
    snapshot: dict[str, Any] = {}
    for memory_type in _memory_types():
        memory = await business_memory.get_memory(session, business_id, memory_type)
        snapshot[memory_type] = memory.data if memory else {}
    return snapshot


async def _load_graph_evidence(session: AsyncSession, business_id: UUID, limit: int = 20) -> list[dict[str, Any]]:
    result = await session.execute(
        select(GraphRelationship)
        .where(GraphRelationship.business_id == business_id)
        .order_by(GraphRelationship.strength.desc())
        .limit(limit)
    )
    rels = result.scalars().all()
    if not rels:
        return []

    entity_ids = {str(r.source_id) for r in rels} | {str(r.target_id) for r in rels}
    entity_map: dict[str, str] = {}
    if entity_ids:
        entities = await session.execute(
            select(GraphEntity).where(GraphEntity.id.in_(entity_ids))
        )
        entity_map = {str(e.id): f"{e.entity_type}:{e.name}" for e in entities.scalars().all()}

    return [
        {
            "source": entity_map.get(str(r.source_id), str(r.source_id)),
            "target": entity_map.get(str(r.target_id), str(r.target_id)),
            "relation_type": r.relation_type,
            "strength": float(r.strength) if r.strength else 0.0,
        }
        for r in rels
    ]


async def _load_context_evidence(session: AsyncSession, business_id: UUID) -> dict[str, Any]:
    contexts = await context_engine.get_active_context(session, business_id)
    return {ctx.context_type: ctx.payload for ctx in contexts}


async def _load_recent_events(
    session: AsyncSession,
    business_id: UUID,
    hours: int = 24,
) -> list[Event]:
    since = utcnow() - timedelta(hours=hours)
    result = await session.execute(
        select(Event)
        .where(Event.business_id == business_id, Event.occurred_at >= since)
        .order_by(Event.occurred_at.desc())
        .limit(1000)
    )
    return list(result.scalars().all())


async def analyze(
    session: AsyncSession,
    business_id: UUID | str,
    query: str | None = None,
    decision_type: str | None = None,
    extra_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Analyze a business across memory, graph, context, and recent events.

    Returns a structured snapshot plus a generated decision so callers can act.
    """
    business_id = _to_uuid(business_id)
    memory_snapshot = await _load_memory_snapshot(session, business_id)
    graph_evidence = await _load_graph_evidence(session, business_id)
    context_evidence = await _load_context_evidence(session, business_id)
    recent_events = await _load_recent_events(session, business_id)

    decision = await decision_engine.generate_decision(
        session,
        business_id,
        decision_type=decision_type,
        extra_context=extra_context,
    )

    summary = (
        f"Analyzed {len(recent_events)} recent events across {len(memory_snapshot)} memory documents, "
        f"{len(graph_evidence)} graph relationships, and {len(context_evidence)} active context types."
    )

    sources = ["memory", "graph", "context", "events", "decision_engine"]
    return {
        "query": query,
        "summary": summary,
        "memory_snapshot": memory_snapshot,
        "graph_evidence": graph_evidence,
        "context_evidence": context_evidence,
        "recent_event_count": len(recent_events),
        "decision": decision,
        "sources": sources,
    }


async def predict(
    session: AsyncSession,
    business_id: UUID | str,
    target: str,
    horizon_days: int = 7,
    item_id: str | None = None,
) -> dict[str, Any]:
    """Predict sales, demand, or stock level over a horizon.

    Uses simple weighted averages from business memory. More sophisticated
    forecasters can be plugged in behind this interface without changing
    consumers.
    """
    business_id = _to_uuid(business_id)
    memory = await _load_memory_snapshot(session, business_id)
    current_state = memory.get(MemoryType.CURRENT_STATE.value, {})

    if target == "stock":
        stock = _safe_float(
            current_state.get("inventory", {}).get(item_id or "unknown", {}).get("stock"),
            None,
        )
        if stock is None:
            stock = 0.0
        return {
            "target": target,
            "horizon_days": horizon_days,
            "item_id": item_id,
            "predicted_value": round(stock, 2),
            "unit": "units",
            "confidence": 0.95,
            "basis": ["current_state.inventory"],
        }

    daily_sales = current_state.get("sales", {}).get("daily", {})
    values: list[float] = []
    if daily_sales:
        # Use the most recent 30 days of recorded daily sales.
        sorted_days = sorted(daily_sales.keys())[-30:]
        for day in sorted_days:
            total = daily_sales[day].get("total") if isinstance(daily_sales[day], dict) else daily_sales[day]
            values.append(_safe_float(total, 0.0))

    if target == "demand" and item_id:
        qty_30d = _safe_float(
            memory.get(MemoryType.PATTERNS.value, {}).get("top_products", {}).get(item_id, {}).get("quantity_30d"),
            0.0,
        )
        daily_avg = qty_30d / 30.0 if qty_30d else 0.0
        predicted = round(daily_avg * horizon_days, 2)
        return {
            "target": target,
            "horizon_days": horizon_days,
            "item_id": item_id,
            "predicted_value": predicted,
            "unit": "units",
            "confidence": 0.7 if qty_30d else 0.3,
            "basis": ["patterns.top_products"],
        }

    if not values:
        return {
            "target": target,
            "horizon_days": horizon_days,
            "item_id": item_id,
            "predicted_value": 0.0,
            "unit": "SAR" if target == "sales" else "units",
            "confidence": 0.3,
            "basis": ["no_recent_data"],
        }

    avg_daily = sum(values) / len(values)
    predicted = round(avg_daily * horizon_days, 2)
    confidence = min(0.95, 0.4 + 0.02 * len(values))
    return {
        "target": target,
        "horizon_days": horizon_days,
        "item_id": item_id,
        "predicted_value": predicted,
        "unit": "SAR" if target == "sales" else "units",
        "confidence": round(confidence, 2),
        "basis": [f"{len(values)} days of recent sales"],
    }


async def explain(
    session: AsyncSession,
    business_id: UUID | str,
    decision_id: UUID | str,
) -> dict[str, Any]:
    """Explain a previously generated decision."""
    return await decision_engine.explain_decision(session, decision_id, business_id)


async def plan(
    session: AsyncSession,
    business_id: UUID | str,
    goal: str,
    context: dict[str, Any] | None = None,
) -> planning_engine.Plan:
    """Generate a goal-driven plan."""
    return await planning_engine.create_plan(session, business_id, goal, context=context)


async def simulate(
    session: AsyncSession,
    business_id: UUID | str,
    name: str,
    scenario: dict[str, Any],
    assumptions: dict[str, Any] | None = None,
) -> simulation_engine.Simulation:
    """Run a what-if simulation."""
    return await simulation_engine.create_simulation(
        session, business_id, name, scenario, assumptions=assumptions
    )


async def execute(
    session: AsyncSession,
    business_id: UUID | str,
    action_type: str,
    entity_type: str,
    entity_id: UUID | str,
    payload: dict[str, Any],
    decision_id: UUID | str | None = None,
    plan_id: UUID | str | None = None,
) -> execution_engine.ExecutionJob:
    """Execute an approved action."""
    return await execution_engine.execute_from_request(
        session,
        business_id,
        action_type,
        entity_type,
        entity_id,
        payload,
        decision_id=decision_id,
        plan_id=plan_id,
    )


async def observe(
    session: AsyncSession,
    business_id: UUID | str,
    event: EventIngest,
) -> Event:
    """Observe a business event through the Universal Event Engine."""
    return await event_engine.ingest_event(session, _to_uuid(business_id), event)


async def remember(
    session: AsyncSession,
    business_id: UUID | str,
    memory_type: str,
    operation: str = "set",
    path: str | None = None,
    value: Any = None,
    goals: dict[str, Any] | None = None,
) -> BusinessMemory:
    """Write to business memory (single path or goals document)."""
    business_id = _to_uuid(business_id)
    if operation == "goal":
        return await business_memory.set_goals(session, business_id, goals or {})

    if path is None:
        raise ValueError("path is required for memory set operation")
    await business_memory.set_memory_path(session, business_id, memory_type, path, value)
    return await business_memory.get_or_create_memory(session, business_id, memory_type)


async def reason(
    session: AsyncSession,
    business_id: UUID | str,
    question: str,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Answer a business question by reasoning over memory, graph, and decisions.

    Produces a natural-language answer, a decision, and an optional plan.
    """
    business_id = _to_uuid(business_id)
    analysis = await analyze(session, business_id, query=question, extra_context=context)
    decision = analysis["decision"]

    plan_obj = None
    if decision and decision.ranked_action:
        goal = decision.ranked_action.get("title") or question
        plan_obj = await planning_engine.create_plan(session, business_id, goal, context=context)

    ranked = decision.ranked_action if decision else {}
    answer = (
        f"Based on the latest signals, the top recommendation is: "
        f"{ranked.get('title', 'No urgent action detected')}. "
        f"Confidence: {round(float(decision.confidence), 2) if decision else 0}. "
        f"Reasoning: {', '.join(ranked.get('reasons', []) or ['Business signals are within normal ranges'])}."
    )

    return {
        "answer": answer,
        "decision": decision,
        "plan": plan_obj,
        "sources": analysis["sources"],
    }
