"""Business Memory Engine service (Phase 1).

Maintains a living, queryable projection of business state derived from the
universal event stream. Projectors are idempotent and write an audit record for
every mutation.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import BusinessMemory, Event, MemoryUpdate, MemoryType
from app.utils.logger import setup_logger

logger = setup_logger("business_memory")


MEMORY_TYPES = {m.value for m in MemoryType}


def _to_uuid(value: UUID | str) -> UUID:
    """Normalize a UUID or string to UUID."""
    if isinstance(value, UUID):
        return value
    return UUID(value)


def _get_path(data: dict[str, Any], path: str) -> Any:
    """Read a dot-notation path from a nested dict, returning None if missing."""
    parts = path.split(".")
    node: Any = data
    for part in parts:
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def _set_path(data: dict[str, Any], path: str, value: Any) -> Any:
    """Set a dot-notation path in a nested dict, creating intermediate dicts.

    Returns the previous value at the path (or None).
    """
    parts = path.split(".")
    node = data
    for part in parts[:-1]:
        if part not in node or not isinstance(node[part], dict):
            node[part] = {}
        node = node[part]
    old_value = node.get(parts[-1])
    node[parts[-1]] = value
    return old_value


def _deep_delta(old: Any, new: Any) -> bool:
    """Return True if old and new values are meaningfully different."""
    return old != new


async def get_or_create_memory(
    session: AsyncSession,
    business_id: UUID | str,
    memory_type: str,
) -> BusinessMemory:
    """Fetch a memory document or create an empty one."""
    business_id = _to_uuid(business_id)
    result = await session.execute(
        select(BusinessMemory).where(
            BusinessMemory.business_id == business_id,
            BusinessMemory.memory_type == memory_type,
        )
    )
    memory = result.scalar_one_or_none()
    if memory is None:
        memory = BusinessMemory(
            business_id=business_id,
            memory_type=memory_type,
            data={},
            version=0,
        )
        session.add(memory)
        await session.flush()
    return memory


async def set_memory_path(
    session: AsyncSession,
    business_id: UUID | str,
    memory_type: str,
    path: str,
    value: Any,
    event_id: UUID | str | None = None,
    skip_if_unchanged: bool = True,
) -> MemoryUpdate | None:
    """Set a value in a memory document and record the mutation."""
    if memory_type not in MEMORY_TYPES:
        raise ValueError(f"Unsupported memory_type: {memory_type}")

    memory = await get_or_create_memory(session, business_id, memory_type)
    old_value = _get_path(memory.data, path)
    if skip_if_unchanged and not _deep_delta(old_value, value):
        return None

    # Reassign the whole dict so SQLAlchemy detects the mutation for JSON columns
    # that do not use MutableDict tracking.
    new_data = deepcopy(memory.data)
    _set_path(new_data, path, deepcopy(value))
    memory.data = new_data
    memory.version += 1
    memory.updated_at = datetime.now(timezone.utc)
    if event_id is not None:
        memory.updated_by_event_id = _to_uuid(event_id)

    update = MemoryUpdate(
        business_id=memory.business_id,
        memory_type=memory_type,
        event_id=memory.updated_by_event_id,
        path=path,
        old_value=deepcopy(old_value),
        new_value=deepcopy(value),
        occurred_at=datetime.now(timezone.utc),
    )
    session.add(update)
    await session.flush()
    return update


async def set_goals(
    session: AsyncSession,
    business_id: UUID | str,
    goals: dict[str, Any],
    event_id: UUID | str | None = None,
) -> BusinessMemory:
    """Set or replace the goals memory document."""
    memory = await get_or_create_memory(session, business_id, MemoryType.GOALS.value)
    old_goals = memory.data.get("goals")
    if _deep_delta(old_goals, goals):
        new_data = deepcopy(memory.data)
        new_data["goals"] = deepcopy(goals)
        memory.data = new_data
        memory.version += 1
        memory.updated_at = datetime.now(timezone.utc)
        if event_id is not None:
            memory.updated_by_event_id = _to_uuid(event_id)
        session.add(
            MemoryUpdate(
                business_id=memory.business_id,
                memory_type=MemoryType.GOALS.value,
                event_id=memory.updated_by_event_id,
                path="goals",
                old_value=deepcopy(old_goals),
                new_value=deepcopy(goals),
                occurred_at=datetime.now(timezone.utc),
            )
        )
        await session.flush()
    return memory


# ═══════════════════════════════════════════════════════════════════════════
# Projectors
# ═══════════════════════════════════════════════════════════════════════════

async def _project_inventory_changed(session: AsyncSession, event: Event) -> None:
    payload = event.payload or {}
    item_key = payload.get("item_id") or payload.get("sku") or "unknown"
    new_quantity = payload.get("new_quantity")
    quantity_delta = payload.get("quantity_delta")
    reason = payload.get("reason")

    base_path = f"inventory.{item_key}"
    if new_quantity is not None:
        await set_memory_path(
            session,
            event.business_id,
            MemoryType.CURRENT_STATE.value,
            f"{base_path}.stock",
            float(new_quantity),
            event_id=event.id,
        )
    if quantity_delta is not None:
        await set_memory_path(
            session,
            event.business_id,
            MemoryType.CURRENT_STATE.value,
            f"{base_path}.last_delta",
            float(quantity_delta),
            event_id=event.id,
        )
    if reason is not None:
        await set_memory_path(
            session,
            event.business_id,
            MemoryType.CURRENT_STATE.value,
            f"{base_path}.last_reason",
            reason,
            event_id=event.id,
        )

    # Reorder flag: simple heuristic when stock drops below 10 units.
    stock = new_quantity if new_quantity is not None else None
    if stock is not None:
        await set_memory_path(
            session,
            event.business_id,
            MemoryType.CURRENT_STATE.value,
            f"{base_path}.reorder_flag",
            stock < 10,
            event_id=event.id,
        )


async def _project_sale_completed(session: AsyncSession, event: Event) -> None:
    payload = event.payload or {}
    total = payload.get("total_amount", 0.0)
    items = payload.get("items", []) or []
    branch_id = payload.get("branch_id")

    # Current state: rolling sales totals keyed by calendar date (UTC).
    today = event.occurred_at.date().isoformat() if event.occurred_at else datetime.now(timezone.utc).date().isoformat()
    current_total = _get_path((await get_or_create_memory(session, event.business_id, MemoryType.CURRENT_STATE.value)).data, f"sales.daily.{today}.total") or 0.0
    await set_memory_path(
        session,
        event.business_id,
        MemoryType.CURRENT_STATE.value,
        f"sales.daily.{today}.total",
        float(current_total) + float(total),
        event_id=event.id,
    )
    await set_memory_path(
        session,
        event.business_id,
        MemoryType.CURRENT_STATE.value,
        f"sales.daily.{today}.last_order_id",
        payload.get("order_id"),
        event_id=event.id,
    )
    if branch_id:
        branch_total = _get_path(
            (await get_or_create_memory(session, event.business_id, MemoryType.CURRENT_STATE.value)).data,
            f"sales.branches.{branch_id}.total",
        ) or 0.0
        await set_memory_path(
            session,
            event.business_id,
            MemoryType.CURRENT_STATE.value,
            f"sales.branches.{branch_id}.total",
            float(branch_total) + float(total),
            event_id=event.id,
        )

    # Patterns: top products by quantity sold.
    for item in items:
        item_id = item.get("item_id") or item.get("sku")
        qty = item.get("quantity", 0)
        if not item_id:
            continue
        current_qty = _get_path(
            (await get_or_create_memory(session, event.business_id, MemoryType.PATTERNS.value)).data,
            f"top_products.{item_id}.quantity_30d",
        ) or 0.0
        await set_memory_path(
            session,
            event.business_id,
            MemoryType.PATTERNS.value,
            f"top_products.{item_id}.quantity_30d",
            float(current_qty) + float(qty),
            event_id=event.id,
        )


async def _project_supplier_delivered(session: AsyncSession, event: Event) -> None:
    payload = event.payload or {}
    supplier_id = payload.get("supplier_id")
    if not supplier_id:
        return

    delivered_at = payload.get("delivered_at") or event.occurred_at.isoformat() if event.occurred_at else datetime.now(timezone.utc).isoformat()
    await set_memory_path(
        session,
        event.business_id,
        MemoryType.RELATIONSHIPS.value,
        f"suppliers.{supplier_id}.last_delivery_at",
        delivered_at,
        event_id=event.id,
    )

    # Increment delivery count for a simple reliability signal.
    current_count = _get_path(
        (await get_or_create_memory(session, event.business_id, MemoryType.RELATIONSHIPS.value)).data,
        f"suppliers.{supplier_id}.delivery_count_90d",
    ) or 0
    await set_memory_path(
        session,
        event.business_id,
        MemoryType.RELATIONSHIPS.value,
        f"suppliers.{supplier_id}.delivery_count_90d",
        int(current_count) + 1,
        event_id=event.id,
    )


async def _project_price_updated(session: AsyncSession, event: Event) -> None:
    payload = event.payload or {}
    item_id = payload.get("item_id") or payload.get("sku")
    if not item_id:
        return
    new_price = payload.get("new_price")
    old_price = payload.get("old_price")

    history_path = f"pricing.{item_id}.history"
    memory = await get_or_create_memory(session, event.business_id, MemoryType.PATTERNS.value)
    # Deepcopy so appending does not mutate the persisted document in place
    # before set_memory_path can detect the change.
    history = deepcopy(_get_path(memory.data, history_path) or [])
    entry = {
        "price": float(new_price) if new_price is not None else None,
        "old_price": float(old_price) if old_price is not None else None,
        "updated_at": event.occurred_at.isoformat() if event.occurred_at else datetime.now(timezone.utc).isoformat(),
    }
    history.append(entry)
    # Keep last 20 price points to bound document size.
    history = history[-20:]
    await set_memory_path(
        session,
        event.business_id,
        MemoryType.PATTERNS.value,
        history_path,
        history,
        event_id=event.id,
    )


_PROJECTOR_MAP: dict[str, Any] = {
    "inventory.changed": _project_inventory_changed,
    "sale.completed": _project_sale_completed,
    "supplier.delivered": _project_supplier_delivered,
    "price.updated": _project_price_updated,
}


async def route_event_to_projectors(session: AsyncSession, event: Event) -> None:
    """Dispatch an event to all memory projectors that understand its type.

    The caller is responsible for committing the session; this keeps event
    processing and memory projection atomic.
    """
    projector = _PROJECTOR_MAP.get(event.event_type)
    if projector is None:
        return

    await projector(session, event)
    logger.info(
        "Memory projection applied",
        extra={
            "event_id": str(event.id),
            "event_type": event.event_type,
            "business_id": str(event.business_id),
        },
    )


# ═══════════════════════════════════════════════════════════════════════════
# Query helpers
# ═══════════════════════════════════════════════════════════════════════════

async def get_memory(
    session: AsyncSession,
    business_id: UUID | str,
    memory_type: str,
) -> BusinessMemory | None:
    """Return a memory document or None if it has never been written."""
    if memory_type not in MEMORY_TYPES:
        raise ValueError(f"Unsupported memory_type: {memory_type}")
    result = await session.execute(
        select(BusinessMemory).where(
            BusinessMemory.business_id == _to_uuid(business_id),
            BusinessMemory.memory_type == memory_type,
        )
    )
    return result.scalar_one_or_none()


async def list_memory_changes(
    session: AsyncSession,
    business_id: UUID | str,
    memory_type: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[MemoryUpdate], int]:
    """Return recent memory mutations and total count."""
    query = select(MemoryUpdate).where(MemoryUpdate.business_id == _to_uuid(business_id))
    count_query = select(func.count(MemoryUpdate.id)).where(MemoryUpdate.business_id == _to_uuid(business_id))
    if memory_type:
        query = query.where(MemoryUpdate.memory_type == memory_type)
        count_query = count_query.where(MemoryUpdate.memory_type == memory_type)
    query = query.order_by(MemoryUpdate.occurred_at.desc()).offset(offset).limit(limit)

    result = await session.execute(query)
    total_result = await session.execute(count_query)
    return list(result.scalars().all()), int(total_result.scalar_one())


async def replay_events_to_memory(
    session: AsyncSession,
    business_id: UUID | str,
    events: list[Event],
) -> dict[str, BusinessMemory]:
    """Rebuild business memory by replaying a list of events deterministically.

    Events are replayed in the order provided. This is used for property tests
    and disaster recovery, not normal ingestion.
    """
    business_id = _to_uuid(business_id)
    # Clear existing memory and audit for this business.
    await session.execute(
        MemoryUpdate.__table__.delete().where(MemoryUpdate.business_id == business_id)
    )
    await session.execute(
        BusinessMemory.__table__.delete().where(BusinessMemory.business_id == business_id)
    )
    await session.commit()

    for event in events:
        if event.business_id != business_id:
            continue
        await route_event_to_projectors(session, event)

    result = await session.execute(
        select(BusinessMemory).where(BusinessMemory.business_id == business_id)
    )
    return {m.memory_type: m for m in result.scalars().all()}
