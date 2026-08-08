"""Simulation Engine service (Phase 5).

Runs deterministic what-if scenarios on a copy of business memory.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import BusinessMemory, MemoryType, Simulation
from app.services.business_memory import get_or_create_memory
from app.utils.logger import setup_logger

logger = setup_logger("simulation_engine")


def _to_uuid(value: UUID | str) -> UUID:
    if isinstance(value, UUID):
        return value
    return UUID(value)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


async def create_simulation(
    session: AsyncSession,
    business_id: UUID | str,
    name: str,
    scenario: dict[str, Any],
    assumptions: dict[str, Any] | None = None,
) -> Simulation:
    """Create a simulation record and run it."""
    business_id = _to_uuid(business_id)
    simulation = Simulation(
        business_id=business_id,
        name=name,
        scenario=scenario,
        assumptions=assumptions or {},
        status="running",
        started_at=datetime.now(timezone.utc),
    )
    session.add(simulation)
    await session.flush()

    results = await run_simulation(session, business_id, scenario, assumptions)
    simulation.results = results
    simulation.status = "completed"
    simulation.completed_at = datetime.now(timezone.utc)
    await session.flush()
    return simulation


async def run_simulation(
    session: AsyncSession,
    business_id: UUID | str,
    scenario: dict[str, Any],
    assumptions: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run a deterministic what-if on a copy of business memory."""
    business_id = _to_uuid(business_id)
    assumptions = assumptions or {}

    memory_result = await session.execute(
        select(BusinessMemory).where(BusinessMemory.business_id == business_id)
    )
    memory_copy = {m.memory_type: deepcopy(m.data) for m in memory_result.scalars().all()}

    scenario_type = scenario.get("type", "generic")
    results: dict[str, Any] = {
        "scenario_type": scenario_type,
        "memory_snapshot_before": memory_copy,
    }

    if scenario_type == "price_change":
        item_key = scenario.get("item_key")
        price_delta_pct = _safe_float(scenario.get("price_delta_pct"), 0.0)
        inventory = memory_copy.get(MemoryType.CURRENT_STATE.value, {}).get("inventory", {})
        item = inventory.get(item_key, {})
        current_price = _safe_float(item.get("avg_price"), 10.0)
        new_price = current_price * (1 + price_delta_pct / 100.0)
        # Assume price elasticity of -1.5 for simplicity.
        demand_change_pct = -1.5 * price_delta_pct
        revenue_change_pct = price_delta_pct + demand_change_pct
        results["projected"] = {
            "item_key": item_key,
            "current_price": round(current_price, 2),
            "new_price": round(new_price, 2),
            "demand_change_pct": round(demand_change_pct, 2),
            "revenue_change_pct": round(revenue_change_pct, 2),
        }

    elif scenario_type == "restock":
        item_key = scenario.get("item_key")
        qty = _safe_float(scenario.get("quantity"), 0.0)
        unit_cost = _safe_float(scenario.get("unit_cost"), 10.0)
        results["projected"] = {
            "item_key": item_key,
            "quantity": qty,
            "total_cost": round(qty * unit_cost, 2),
            "stockout_risk": "reduced" if qty > 50 else "moderate",
        }

    elif scenario_type == "discount":
        item_key = scenario.get("item_key")
        discount_pct = _safe_float(scenario.get("discount_pct"), 0.0)
        inventory = memory_copy.get(MemoryType.CURRENT_STATE.value, {}).get("inventory", {})
        stock = _safe_float(inventory.get(item_key, {}).get("stock"), 0.0)
        # Assume discount clears 30% of slow stock at reduced margin.
        cleared_qty = stock * 0.3
        recovery_value = cleared_qty * discount_pct / 100.0 * 10.0
        results["projected"] = {
            "item_key": item_key,
            "discount_pct": discount_pct,
            "cleared_quantity": round(cleared_qty, 2),
            "recovery_value": round(recovery_value, 2),
        }

    else:
        results["projected"] = {
            "note": "Generic simulation; no specific model applied",
            "assumptions": assumptions,
        }

    results["confidence"] = 0.7
    return results


async def get_simulation(
    session: AsyncSession,
    simulation_id: UUID | str,
    business_id: UUID | str | None = None,
) -> Simulation | None:
    query = select(Simulation).where(Simulation.id == _to_uuid(simulation_id))
    if business_id is not None:
        query = query.where(Simulation.business_id == _to_uuid(business_id))
    result = await session.execute(query)
    return result.scalar_one_or_none()
