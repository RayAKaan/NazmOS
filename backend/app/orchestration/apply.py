"""Apply activities — business-mutation primitives (idempotent by caller).

Each function performs ONE atomic business-state mutation using the same
SQL as the legacy executors. They are pure side-effect functions: the
precheck layer has already verified authz and constraint guards.

Idempotency is enforced by the workflow calling record.py's
``check_idempotency`` BEFORE invoking an apply function.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ── Manual path (ActionExecutor legacy) ──────────────────────────────


async def apply_restock(
    db: AsyncSession,
    business_id: UUID,
    item_id: UUID,
    new_state: dict[str, Any],
) -> dict[str, Any]:
    """Increment inventory for a received restock. Single atomic UPDATE."""
    from app.utils.money import decimal_value

    received_qty = new_state.get("restock_qty")
    if received_qty is None:
        received_qty = new_state.get("quantity")
    if received_qty is None:
        return {"executed": False, "reason": "Restock requires a received quantity (restock_qty)."}
    try:
        received_qty = decimal_value(received_qty)
    except Exception:
        return {"executed": False, "reason": "Restock quantity must be numeric."}
    if received_qty < 0:
        return {"executed": False, "reason": "Restock quantity cannot be negative."}

    now = _now()
    result = await db.execute(
        text("""
            UPDATE inventory
            SET current_stock = current_stock + :qty,
                last_restocked = :now,
                updated_at = :now
            WHERE business_id = :business_id
              AND item_id = :item_id
            RETURNING id, current_stock
        """),
        {"qty": float(received_qty), "now": now, "business_id": str(business_id), "item_id": str(item_id)},
    )
    row = result.fetchone()
    if row is None:
        return {"executed": False, "reason": f"Inventory position not found for item {item_id}"}

    logger.info(
        "orchestration_restock_applied",
        business_id=str(business_id),
        item_id=str(item_id),
        received_qty=float(received_qty),
        new_stock=float(row.current_stock),
    )
    return {
        "executed": True,
        "action": "restock",
        "message": f"Restocked item {item_id}: +{float(received_qty)} units received",
    }


async def apply_price_change(
    db: AsyncSession,
    business_id: UUID,
    item_id: UUID,
    new_state: dict[str, Any],
) -> dict[str, Any]:
    """Update item sell_price and mark pricing recommendation applied."""
    from app.database.models import Item, PricingRecommendation

    item = await db.get(Item, item_id)
    if not item:
        return {"executed": False, "reason": f"Item {item_id} not found"}

    old_price = item.sell_price
    item.sell_price = new_state.get("sell_price", item.sell_price)
    item.last_price_change = _now()
    item.price_change_count_30d = (item.price_change_count_30d or 0) + 1

    rec_result = await db.execute(
        text("""
            SELECT id FROM pricing_recommendations
            WHERE item_id = :item_id AND status = 'pending'
            LIMIT 1
        """),
        {"item_id": str(item_id)},
    )
    rec_row = rec_result.fetchone()
    if rec_row:
        await db.execute(
            text("UPDATE pricing_recommendations SET status='applied', applied_at=:now WHERE id=:id"),
            {"id": str(rec_row.id), "now": _now()},
        )

    logger.info(
        "orchestration_price_change_applied",
        business_id=str(business_id),
        item_id=str(item_id),
        old_price=float(old_price) if old_price else None,
        new_price=item.sell_price,
    )
    return {
        "executed": True,
        "action": "price_change",
        "message": f"Price updated for item {item_id}",
    }


async def apply_discount(
    db: AsyncSession,
    business_id: UUID,
    item_id: UUID,
    new_state: dict[str, Any],
) -> dict[str, Any]:
    """Apply discount (currently a semantic no-op, logged for audit)."""
    logger.info("orchestration_discount_applied", business_id=str(business_id), item_id=str(item_id))
    return {"executed": True, "action": "discount", "message": f"Discount applied for item {item_id}"}


async def apply_alert_dismiss(
    db: AsyncSession,
    decision_id: UUID,
) -> dict[str, Any]:
    """Dismiss an alert (decision-level, no inventory mutation)."""
    return {"executed": True, "action": "alert_dismiss", "message": "Alert dismissed"}


# ── Agent path (agent_action_executor legacy) ────────────────────────


async def apply_agent_pricing_update(
    db: AsyncSession,
    business_id: UUID,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Update item sell_price from agent recommendation."""
    from app.utils.money import sar
    from app.services.action_registry import can_execute

    item_id = payload.get("item_id")
    suggested_price = payload.get("suggested_price") or payload.get("recommended_sell_price_sar")
    if not item_id or suggested_price is None:
        return {"executed": False, "reason": "Missing item_id or suggested_price"}

    try:
        suggested_price = sar(suggested_price)
    except Exception:
        return {"executed": False, "reason": "Invalid suggested_price"}

    if suggested_price <= 0:
        return {"executed": False, "reason": "suggested_price must be positive"}

    res = await db.execute(
        text("""
            UPDATE items
            SET sell_price = :new_price,
                last_price_change = :now,
                price_change_count_30d = COALESCE(price_change_count_30d, 0) + 1,
                updated_at = :now
            WHERE id = :item_id AND business_id = :business_id
            RETURNING name, sell_price
        """),
        {"business_id": str(business_id), "item_id": str(item_id), "new_price": suggested_price, "now": _now()},
    )
    row = res.fetchone()
    if not row:
        return {"executed": False, "reason": "Item not found for business"}

    return {
        "executed": True,
        "action": "price_update",
        "item_id": str(item_id),
        "item_name": row.name,
        "new_sell_price_sar": float(sar(row.sell_price)),
    }


async def apply_agent_restock_po(
    db: AsyncSession,
    business_id: UUID,
    action_id: UUID,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Create a purchase order for agent-initiated restock."""
    from app.utils.money import sar, decimal_value
    from app.utils.clock import utcnow

    item_id = payload.get("item_id")
    qty = payload.get("recommended_qty") or payload.get("quantity")
    if not item_id or qty is None:
        return {"executed": False, "reason": "Missing item_id or recommended_qty"}

    try:
        qty = decimal_value(qty)
    except Exception:
        return {"executed": False, "reason": "Invalid recommended_qty"}

    if qty <= 0:
        return {"executed": False, "reason": "recommended_qty must be positive"}

    item_res = await db.execute(
        text("SELECT id, name, cost_price FROM items WHERE id = :item_id AND business_id = :business_id"),
        {"business_id": str(business_id), "item_id": str(item_id)},
    )
    item = item_res.fetchone()
    if not item:
        return {"executed": False, "reason": "Item not found for business"}

    unit_cost = sar(item.cost_price or 0)
    total_sar = sar(unit_cost * qty)
    po_number = f"NAZM-{utcnow().strftime('%Y%m%d%H%M%S')}-{str(uuid4())[:8]}"
    items_json = [{
        "item_id": str(item.id),
        "item_name": item.name,
        "qty": float(qty),
        "unit_cost_sar": float(unit_cost),
    }]

    await db.execute(
        text("""
            INSERT INTO purchase_orders
                (id, business_id, agent_action_id, po_number, status, total_sar,
                 items_json, created_by_agent, created_at, updated_at)
            VALUES
                (:po_id, :business_id, :action_id, :po_number, 'approved', :total_sar,
                 CAST(:items_json AS JSON), true, :now, :now)
        """),
        {
            "po_id": str(uuid4()),
            "business_id": str(business_id),
            "action_id": str(action_id),
            "po_number": po_number,
            "total_sar": total_sar,
            "items_json": json.dumps(items_json),
            "now": utcnow(),
        },
    )

    return {
        "executed": True,
        "action": "purchase_order_created",
        "po_number": po_number,
        "total_sar": float(total_sar),
        "items": items_json,
    }


async def apply_agent_transfer(
    db: AsyncSession,
    business_id: UUID,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Execute inter-branch inventory transfer."""
    from app.utils.money import decimal_value

    item_id = payload.get("item_id")
    from_business = payload.get("from_business_id")
    to_business = payload.get("to_business_id")
    qty = payload.get("recommended_transfer_qty") or payload.get("quantity")

    if not (item_id and from_business and to_business):
        return {"executed": False, "reason": "transfer requires item_id, from_business_id, to_business_id"}
    if str(from_business) == str(to_business):
        return {"executed": False, "reason": "transfer requires distinct source and destination branches"}

    try:
        qty = decimal_value(qty)
    except Exception:
        return {"executed": False, "reason": "Invalid transfer quantity"}
    if qty <= 0:
        return {"executed": False, "reason": "transfer quantity must be positive"}

    src = await db.execute(
        text("SELECT current_stock FROM inventory WHERE item_id = :item AND business_id = :from_b FOR UPDATE"),
        {"item": str(item_id), "from_b": str(from_business)},
    )
    src_row = src.fetchone()
    if not src_row:
        return {"executed": False, "reason": "Source inventory not found"}
    if float(src_row.current_stock or 0) < float(qty):
        return {"executed": False, "reason": f"Insufficient stock at source ({src_row.current_stock})"}

    from app.utils.clock import utcnow
    now = utcnow()
    await db.execute(
        text("UPDATE inventory SET current_stock = current_stock - :qty, updated_at = :now WHERE item_id = :item AND business_id = :from_b"),
        {"item": str(item_id), "from_b": str(from_business), "qty": float(qty), "now": now},
    )

    dest = await db.execute(
        text("SELECT id FROM inventory WHERE item_id = :item AND business_id = :to_b"),
        {"item": str(item_id), "to_b": str(to_business)},
    )
    if not dest.fetchone():
        return {"executed": False, "reason": "Destination inventory not found; transfer rolled back"}

    await db.execute(
        text("UPDATE inventory SET current_stock = current_stock + :qty, updated_at = :now WHERE item_id = :item AND business_id = :to_b"),
        {"item": str(item_id), "to_b": str(to_business), "qty": float(qty), "now": now},
    )

    return {
        "executed": True,
        "action": "inventory_transfer",
        "item_id": str(item_id),
        "from_business_id": str(from_business),
        "to_business_id": str(to_business),
        "quantity": float(qty),
    }


async def apply_agent_action(
    db: AsyncSession,
    business_id: UUID | str,
    action_id: UUID | str,
    action_type: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Dispatch agent action to the correct mutation by type.

    This is the combined entrypoint for agent-side mutations (replaces
    execute_agent_action from the legacy agent_action_executor).
    """
    from app.services.execution_guard import validate_action_for_execution, record_constraint_block

    verdict = await validate_action_for_execution(
        db, business_id=business_id, action_type=action_type, payload=payload,
        actor_business_id=business_id,
    )
    if verdict.blocked:
        await record_constraint_block(
            db, business_id=business_id, action_type=action_type,
            reason_code=verdict.reason_code, reason=verdict.reason,
            action_id=action_id, payload=payload,
        )
        return {"executed": False, "reason": verdict.reason, "reason_code": verdict.reason_code,
                "execution_mode": "BLOCKED_BY_CONSTRAINT"}

    if action_type in {"discount", "margin_fix", "pricing_increase", "pricing_decrease"}:
        from app.services.action_registry import can_execute
        if not can_execute(action_type, payload):
            return {"executed": False, "reason": "Manual action: connected POS price/discount executor is unavailable for this payload.",
                    "execution_mode": "MANUAL"}
        return await apply_agent_pricing_update(db, business_id, payload)

    if action_type in {"reorder", "restock"}:
        return await apply_agent_restock_po(db, business_id, action_id, payload)

    if action_type in {"recovery_match", "transfer_inventory"}:
        from app.services.action_registry import can_execute
        if not can_execute(action_type, payload):
            return {"executed": False, "reason": "Manual action: transfer source/destination and quantity are required.",
                    "execution_mode": "MANUAL"}
        return await apply_agent_transfer(db, business_id, payload)

    if action_type == "expiry_alert":
        return {"executed": False, "reason": "expiry_alert is informational", "action": "expiry_alert",
                "execution_mode": "MANUAL"}

    from app.services.action_registry import get_action_spec
    spec = get_action_spec(action_type)
    return {"executed": False, "reason": f"No deterministic executor for action_type={action_type}",
            "execution_mode": spec.execution_mode}


# ── Simulated path (execution_engine legacy) ─────────────────────────


async def apply_simulated_execution(
    db: AsyncSession,
    business_id: UUID,
    action_type: str,
    entity_type: str,
    entity_id: UUID,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Simulated external execution (intelligence path).

    Creates an ExecutionJob row and emits an execution.completed event.
    Does NOT mutate business data (items, inventory). This preserves
    the ADR §7 simulated-vs-real invariant.
    """
    import hashlib
    from app.database.models import ExecutionJob, Event

    now = _now()

    # Select-before-insert idempotency (preserves original behavior)
    from sqlalchemy import select
    existing = await db.execute(
        select(ExecutionJob).where(
            ExecutionJob.business_id == business_id,
            ExecutionJob.action_type == action_type,
            ExecutionJob.entity_type == entity_type,
            ExecutionJob.entity_id == entity_id,
            ExecutionJob.status.in_(["pending", "completed"]),
        )
    )
    existing_job = existing.scalar_one_or_none()
    if existing_job:
        return {
            "executed": True,
            "simulated": True,
            "job_id": str(existing_job.id),
            "status": existing_job.status,
            "result": existing_job.result,
        }

    job = ExecutionJob(
        business_id=business_id,
        action_type=action_type,
        entity_type=entity_type,
        entity_id=entity_id,
        payload=payload,
        status="pending",
    )
    db.add(job)
    await db.flush()

    job.status = "executing"
    await db.flush()

    external_reference = f"EXT-{action_type.upper()}-{job.id.hex[:8]}"
    result = {
        "simulated": True,
        "external_reference": external_reference,
        "action_type": action_type,
        "entity_type": entity_type,
        "entity_id": str(entity_id),
        "payload": payload,
    }

    event_payload = {
        "job_id": str(job.id),
        "action_type": action_type,
        "external_reference": external_reference,
    }
    checksum = hashlib.sha256(
        json.dumps(event_payload, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()
    event = Event(
        business_id=business_id,
        event_type="execution.completed",
        source="orchestration",
        source_id=str(job.id),
        payload=event_payload,
        checksum=checksum,
        occurred_at=now,
        processed=True,
        processed_at=now,
    )
    db.add(event)

    job.status = "completed"
    job.result = result
    job.external_reference = external_reference
    job.executed_at = now

    logger.info(
        "orchestration_simulated_completed",
        business_id=str(business_id),
        action_type=action_type,
        job_id=str(job.id),
    )

    return {
        "executed": True,
        "simulated": True,
        "job_id": str(job.id),
        "status": "completed",
        "result": result,
    }
