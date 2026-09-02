"""Approval and execution helpers for Nazm agent actions.

This gives WhatsApp and web approvals one shared path:
1. mark pending action approved/rejected;
2. execute safe first-party actions where we have deterministic handlers;
3. write applied_at/outcome_json for auditability.
"""
import json
from decimal import Decimal
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import UUID, uuid4
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.utils.money import sar, decimal_value
from app.utils.clock import utcnow
from app.services.action_registry import can_execute, get_action_spec


def _payload_to_dict(payload: Any) -> Dict[str, Any]:
    if isinstance(payload, dict):
        return payload
    if isinstance(payload, str):
        try:
            return json.loads(payload)
        except Exception:
            return {}
    return {}


async def _execute_pricing_update(db: AsyncSession, business_id: UUID | str, payload: dict) -> dict:
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

    res = await db.execute(text("""
        UPDATE items
        SET sell_price = :new_price,
            last_price_change = :now,
            price_change_count_30d = COALESCE(price_change_count_30d, 0) + 1,
            updated_at = :now
        WHERE id = :item_id AND business_id = :business_id
        RETURNING name, sell_price
    """), {
        "business_id": str(business_id),
        "item_id": str(item_id),
        "new_price": suggested_price,
        "now": utcnow(),
    })
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


async def _execute_restock_po(db: AsyncSession, business_id: UUID | str, action_id: UUID | str, payload: dict) -> dict:
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

    item_res = await db.execute(text("""
        SELECT id, name, cost_price
        FROM items
        WHERE id = :item_id AND business_id = :business_id
    """), {"business_id": str(business_id), "item_id": str(item_id)})
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

    await db.execute(text("""
        INSERT INTO purchase_orders
            (id, business_id, agent_action_id, po_number, status, total_sar,
             items_json, created_by_agent, created_at, updated_at)
        VALUES
            (:po_id, :business_id, :action_id, :po_number, 'approved', :total_sar,
             CAST(:items_json AS JSON), true, :now, :now)
    """), {
        "po_id": str(uuid4()),
        "business_id": str(business_id),
        "action_id": str(action_id),
        "po_number": po_number,
        "total_sar": total_sar,
        "items_json": json.dumps(items_json),
        "now": utcnow(),
    })

    return {
        "executed": True,
        "action": "purchase_order_created",
        "po_number": po_number,
        "total_sar": float(total_sar),
        "items": items_json,
    }


async def _execute_transfer(db: AsyncSession, business_id: UUID | str, payload: dict) -> dict:
    """Execute an inter-branch inventory transfer (Phase 2 §6).

    Decrements the source inventory and increments the destination for the same
    item. Validates quantities > 0 and that the source has sufficient stock.
    """
    item_id = payload.get("item_id")
    from_business = payload.get("from_business_id")
    to_business = payload.get("to_business_id")
    qty = payload.get("recommended_transfer_qty") or payload.get("quantity")

    if not (item_id and from_business and to_business):
        return {"executed": False, "reason": "transfer requires item_id, from_business_id, to_business_id"}
    if not from_business or not to_business or str(from_business) == str(to_business):
        return {"executed": False, "reason": "transfer requires distinct source and destination branches"}

    try:
        qty = decimal_value(qty)
    except Exception:
        return {"executed": False, "reason": "Invalid transfer quantity"}
    if qty <= 0:
        return {"executed": False, "reason": "transfer quantity must be positive"}

    # Source must have enough stock (fail-closed, §26 failure recovery).
    src = await db.execute(text("""
        SELECT current_stock FROM inventory
        WHERE item_id = :item AND business_id = :from
        FOR UPDATE
    """), {"item": str(item_id), "from": str(from_business)})
    src_row = src.fetchone()
    if not src_row:
        return {"executed": False, "reason": "Source inventory not found"}
    if float(src_row.current_stock or 0) < float(qty):
        return {"executed": False, "reason": f"Insufficient stock at source ({src_row.current_stock})"}

    now = utcnow()
    await db.execute(text("""
        UPDATE inventory SET current_stock = current_stock - :qty, updated_at = :now
        WHERE item_id = :item AND business_id = :from
    """), {"item": str(item_id), "from": str(from_business), "qty": qty, "now": now})

    dest = await db.execute(text("""
        SELECT id FROM inventory WHERE item_id = :item AND business_id = :to
    """), {"item": str(item_id), "to": str(to_business)})
    if not dest.fetchone():
        return {"executed": False, "reason": "Destination inventory not found; transfer rolled back"}

    await db.execute(text("""
        UPDATE inventory SET current_stock = current_stock + :qty, updated_at = :now
        WHERE item_id = :item AND business_id = :to
    """), {"item": str(item_id), "to": str(to_business), "qty": qty, "now": now})

    return {
        "executed": True,
        "action": "inventory_transfer",
        "item_id": str(item_id),
        "from_business_id": str(from_business),
        "to_business_id": str(to_business),
        "quantity": float(qty),
    }


async def execute_agent_action(db: AsyncSession, business_id: UUID | str, action_id: UUID | str, action_type: str, payload: dict) -> dict:
    from app.services.execution_guard import validate_action_for_execution, record_constraint_block
    verdict = await validate_action_for_execution(
        db,
        business_id=business_id,
        action_type=action_type,
        payload=payload,
        actor_business_id=business_id,
    )
    if verdict.blocked:
        await record_constraint_block(
            db,
            business_id=business_id,
            action_type=action_type,
            reason_code=verdict.reason_code,
            reason=verdict.reason,
            action_id=action_id,
            payload=payload,
        )
        return {
            "executed": False,
            "reason": verdict.reason,
            "reason_code": verdict.reason_code,
            "execution_mode": "BLOCKED_BY_CONSTRAINT",
        }
    if action_type in {"discount", "margin_fix", "pricing_increase", "pricing_decrease"}:
        if not can_execute(action_type, payload):
            return {"executed": False, "reason": "Manual action: connected POS price/discount executor is unavailable for this payload.", "execution_mode": "MANUAL"}
        return await _execute_pricing_update(db, business_id, payload)
    if action_type in {"reorder", "restock"}:
        return await _execute_restock_po(db, business_id, action_id, payload)
    if action_type in {"recovery_match", "transfer_inventory"}:
        if not can_execute(action_type, payload):
            return {"executed": False, "reason": "Manual action: transfer source/destination and quantity are required.", "execution_mode": "MANUAL"}
        return await _execute_transfer(db, business_id, payload)
    if action_type == "expiry_alert":
        return {"executed": False, "reason": "expiry_alert is informational", "action": "expiry_alert", "execution_mode": "MANUAL"}
    spec = get_action_spec(action_type)
    return {"executed": False, "reason": f"No deterministic executor for action_type={action_type}", "execution_mode": spec.execution_mode}


async def approve_agent_action(
    db: AsyncSession,
    action_id: UUID | str,
    note: str = "Approved",
    decided_by: Optional[UUID | str] = None,
    business_id: Optional[UUID | str] = None,
) -> dict:
    now = utcnow()
    # §10 Tenant Safety: when business_id is provided, enforce it in the WHERE clause
    # for defense-in-depth (caller should already verify ownership).
    tenant_clause = "AND business_id = :business_id" if business_id else ""
    params: dict = {
        "id": str(action_id),
        "decided_by": str(decided_by) if decided_by else None,
        "note": note,
        "now": now,
    }
    if business_id:
        params["business_id"] = str(business_id)
    res = await db.execute(text(f"""
        UPDATE agent_actions
        SET status = 'approved',
            decided_at = :now,
            decided_by = COALESCE(CAST(:decided_by AS UUID), decided_by),
            decision_note = :note,
            updated_at = :now
        WHERE id = :id AND status = 'pending_approval' {tenant_clause}
        RETURNING id, business_id, action_type, payload
    """), params)  # nosec B608
    row = res.fetchone()
    if not row:
        return {"ok": False, "reason": "Action not found or not pending approval", "action_id": str(action_id)}

    payload = _payload_to_dict(row.payload)
    await db.execute(text("UPDATE agent_actions SET status='executing', updated_at=:now WHERE id=:id AND status='approved'"), {"id":str(row.id), "now":utcnow()})
    outcome = await execute_agent_action(db, row.business_id, row.id, row.action_type, payload)
    terminal_status = 'executed' if outcome.get("executed") else ('failed' if outcome.get("execution_mode") != 'MANUAL' else 'approved')

    await db.execute(text("""
        UPDATE agent_actions
        SET status = :terminal_status,
            applied_at = CASE WHEN :executed THEN :now ELSE applied_at END,
            outcome_json = CAST(:outcome AS JSON),
            updated_at = :now
        WHERE id = :id
    """), {
        "id": str(row.id),
        "terminal_status": terminal_status,
        "executed": bool(outcome.get("executed")),
        "outcome": json.dumps(outcome),
        "now": utcnow(),
    })
    await db.commit()
    await _record_terminal_outcome(db, row.business_id, row.id)
    return {"ok": True, "action_id": str(row.id), "outcome": outcome}


async def reject_agent_action(db: AsyncSession, action_id: UUID | str, note: str = "Rejected",
                               business_id: Optional[UUID | str] = None) -> dict:
    # §10 Tenant Safety: when business_id is provided, enforce it in the WHERE clause.
    tenant_clause = "AND business_id = :business_id" if business_id else ""
    params: dict = {"id": str(action_id), "note": note, "now": utcnow()}
    if business_id:
        params["business_id"] = str(business_id)
    res = await db.execute(text(f"""
        UPDATE agent_actions
        SET status = 'rejected',
            decided_at = :now,
            decision_note = :note,
            updated_at = :now
        WHERE id = :id AND status = 'pending_approval' {tenant_clause}
        RETURNING id, business_id
    """), params)  # nosec B608
    row = res.fetchone()
    await db.commit()
    if row:
        await _record_terminal_outcome(db, row.business_id, row.id)
    return {"ok": bool(row), "action_id": str(action_id)}


async def _record_terminal_outcome(db: AsyncSession, business_id: UUID | str, action_id: UUID | str) -> None:
    """Phase 5 §2: the runtime is the canonical integration point for learning. Whenever an
    AgentAction reaches a terminal state (approved/executed/rejected), distill it into a
    LearnedOutcome — agents never need to remember to call the learning system themselves.
    Also projects the action→outcome edge into the KG (§15). Best-effort: neither write may
    ever fail the action transition it observes."""
    import logging
    logger = logging.getLogger("agent_action_executor")
    from sqlalchemy import text as _text

    # Fetch the action's finding_id (explicit lineage, §5) + fields in one read.
    meta = await db.execute(_text(
        "SELECT action_type, status, outcome_json, payload, finding_id FROM agent_actions WHERE id = :id"
    ), {"id": str(action_id)})
    row = meta.fetchone()
    finding_id = row.finding_id if row else None

    try:
        from app.services.outcome_learning import record_unified_outcome
        await record_unified_outcome(db, business_id, action_id, finding_id=finding_id, commit=True)
    except Exception as exc:  # learning must never break the action flow
        logger.warning("learned-outcome write skipped for action %s: %s", action_id, exc)

    try:
        from app.services.knowledge_graph import project_action_to_graph
        if row:
            payload = row.payload if isinstance(row.payload, dict) else (json.loads(row.payload) if row.payload else {})
            outcome = row.outcome_json if isinstance(row.outcome_json, dict) else (json.loads(row.outcome_json) if row.outcome_json else {})
            targets = []
            if payload.get("item_id"):
                targets.append({"type": "product", "id": str(payload["item_id"])})
            await project_action_to_graph(
                db, business_id, action_id, action_type=row.action_type, status=row.status,
                executed=bool(outcome.get("executed")) if isinstance(outcome, dict) else None,
                outcome=outcome, targets=targets, finding_id=str(finding_id) if finding_id else None,
            )
            await db.commit()
    except Exception as exc:
        logger.warning("action graph projection skipped: %s", exc)
