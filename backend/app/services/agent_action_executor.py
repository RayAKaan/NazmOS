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
            last_price_change = NOW(),
            price_change_count_30d = COALESCE(price_change_count_30d, 0) + 1,
            updated_at = NOW()
        WHERE id = :item_id AND business_id = :business_id
        RETURNING name, sell_price
    """), {
        "business_id": str(business_id),
        "item_id": str(item_id),
        "new_price": suggested_price,
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
    po_number = f"NAZM-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{str(uuid4())[:8]}"
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
            (gen_random_uuid(), :business_id, :action_id, :po_number, 'approved', :total_sar,
             CAST(:items_json AS JSON), true, NOW(), NOW())
    """), {
        "business_id": str(business_id),
        "action_id": str(action_id),
        "po_number": po_number,
        "total_sar": total_sar,
        "items_json": json.dumps(items_json),
    })

    return {
        "executed": True,
        "action": "purchase_order_created",
        "po_number": po_number,
        "total_sar": float(total_sar),
        "items": items_json,
    }


async def execute_agent_action(db: AsyncSession, business_id: UUID | str, action_id: UUID | str, action_type: str, payload: dict) -> dict:
    if action_type in {"pricing_increase", "pricing_decrease"}:
        return await _execute_pricing_update(db, business_id, payload)
    if action_type == "restock":
        return await _execute_restock_po(db, business_id, action_id, payload)
    return {"executed": False, "reason": f"No deterministic executor for action_type={action_type}"}


async def approve_agent_action(
    db: AsyncSession,
    action_id: UUID | str,
    note: str = "Approved",
    decided_by: Optional[UUID | str] = None,
) -> dict:
    res = await db.execute(text("""
        UPDATE agent_actions
        SET status = 'approved',
            decided_at = NOW(),
            decided_by = COALESCE(CAST(:decided_by AS UUID), decided_by),
            decision_note = :note,
            updated_at = NOW()
        WHERE id = :id AND status = 'pending_approval'
        RETURNING id, business_id, action_type, payload
    """), {
        "id": str(action_id),
        "decided_by": str(decided_by) if decided_by else None,
        "note": note,
    })
    row = res.fetchone()
    if not row:
        return {"ok": False, "reason": "Action not found or not pending approval", "action_id": str(action_id)}

    payload = _payload_to_dict(row.payload)
    outcome = await execute_agent_action(db, row.business_id, row.id, row.action_type, payload)

    await db.execute(text("""
        UPDATE agent_actions
        SET applied_at = CASE WHEN :executed THEN NOW() ELSE applied_at END,
            outcome_json = CAST(:outcome AS JSON),
            updated_at = NOW()
        WHERE id = :id
    """), {
        "id": str(row.id),
        "executed": bool(outcome.get("executed")),
        "outcome": json.dumps(outcome),
    })
    await db.commit()
    return {"ok": True, "action_id": str(row.id), "outcome": outcome}


async def reject_agent_action(db: AsyncSession, action_id: UUID | str, note: str = "Rejected") -> dict:
    res = await db.execute(text("""
        UPDATE agent_actions
        SET status = 'rejected',
            decided_at = NOW(),
            decision_note = :note,
            updated_at = NOW()
        WHERE id = :id AND status = 'pending_approval'
        RETURNING id
    """), {"id": str(action_id), "note": note})
    row = res.fetchone()
    await db.commit()
    return {"ok": bool(row), "action_id": str(action_id)}
