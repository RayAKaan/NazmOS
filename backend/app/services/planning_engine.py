"""Planning Engine service (Phase 5).

Builds goal-driven plans by backward chaining from a goal to concrete execution
steps, reading memory and graph to fill constraints.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import BusinessMemory, GraphEntity, MemoryType, Plan
from app.services.business_memory import get_or_create_memory
from app.utils.logger import setup_logger

logger = setup_logger("planning_engine")


def _to_uuid(value: UUID | str) -> UUID:
    if isinstance(value, UUID):
        return value
    return UUID(value)


async def create_plan(
    session: AsyncSession,
    business_id: UUID | str,
    goal: str,
    context: dict[str, Any] | None = None,
    simulation_id: UUID | str | None = None,
) -> Plan:
    """Generate a plan from a natural-language goal.

    The initial planner uses deterministic heuristics. It inspects business
    memory and the knowledge graph to produce ordered steps.
    """
    business_id = _to_uuid(business_id)
    context = context or {}

    memory = await get_or_create_memory(session, business_id, MemoryType.CURRENT_STATE.value)
    patterns = await get_or_create_memory(session, business_id, MemoryType.PATTERNS.value)
    goals_memory = await get_or_create_memory(session, business_id, MemoryType.GOALS.value)

    steps: list[dict[str, Any]] = []
    estimated_cost = 0.0
    estimated_duration_hours = 0.0

    goal_lower = goal.lower()

    if any(word in goal_lower for word in ["stock", "restock", "inventory", "out of stock", "نفاذ", "مخزون"]):
        inventory = memory.data.get("inventory", {})
        for idx, (item_key, item_state) in enumerate(inventory.items(), start=1):
            stock = float(item_state.get("stock", 0))
            if stock < 10:
                qty = max(50, int(20 - stock) * 5)
                steps.append({
                    "step_number": idx,
                    "action_type": "restock",
                    "description": f"Order {qty} units of {item_key}",
                    "payload": {"item_key": item_key, "quantity": qty},
                })
                estimated_cost += qty * 10.0
                estimated_duration_hours += 4.0

    if any(word in goal_lower for word in ["price", "pricing", "margin", "سعر", "هامش"]):
        pricing = patterns.data.get("pricing", {})
        for idx, item_key in enumerate(pricing.keys(), start=len(steps) + 1):
            steps.append({
                "step_number": idx,
                "action_type": "review_pricing",
                "description": f"Review and adjust pricing for {item_key}",
                "payload": {"item_key": item_key},
            })
            estimated_duration_hours += 2.0

    if any(word in goal_lower for word in ["supplier", "vendor", "مورد"]):
        result = await session.execute(
            select(GraphEntity)
            .where(GraphEntity.business_id == business_id, GraphEntity.entity_type == "supplier")
            .limit(5)
        )
        suppliers = result.scalars().all()
        for idx, supplier in enumerate(suppliers, start=len(steps) + 1):
            steps.append({
                "step_number": idx,
                "action_type": "review_supplier",
                "description": f"Review supplier {supplier.name}",
                "payload": {"supplier_id": str(supplier.id)},
            })
            estimated_duration_hours += 1.0

    if not steps:
        # Generic plan: gather data, decide, execute, review.
        steps = [
            {"step_number": 1, "action_type": "gather_data", "description": "Collect latest business signals", "payload": {}},
            {"step_number": 2, "action_type": "generate_decision", "description": "Run Decision Engine", "payload": {}},
            {"step_number": 3, "action_type": "seek_approval", "description": "Request human approval", "payload": {}},
            {"step_number": 4, "action_type": "execute", "description": "Execute approved action", "payload": {}},
            {"step_number": 5, "action_type": "review", "description": "Review outcome", "payload": {}},
        ]
        estimated_duration_hours = 24.0

    # Store goal in memory for downstream tracking.
    current_goals = goals_memory.data.get("goals", {})
    current_goals[goal] = {"created_at": datetime.now(timezone.utc).isoformat()}
    from app.services.business_memory import set_goals
    await set_goals(session, business_id, current_goals)

    plan = Plan(
        business_id=business_id,
        goal=goal,
        steps=steps,
        estimated_roi=estimated_cost * 0.3 if estimated_cost else 100.0,
        estimated_cost=estimated_cost if estimated_cost else None,
        estimated_duration_hours=estimated_duration_hours if estimated_duration_hours else None,
        simulation_id=_to_uuid(simulation_id) if simulation_id else None,
        status="draft",
    )
    session.add(plan)
    await session.flush()
    return plan


async def get_plan(
    session: AsyncSession,
    plan_id: UUID | str,
    business_id: UUID | str | None = None,
) -> Plan | None:
    query = select(Plan).where(Plan.id == _to_uuid(plan_id))
    if business_id is not None:
        query = query.where(Plan.business_id == _to_uuid(business_id))
    result = await session.execute(query)
    return result.scalar_one_or_none()
