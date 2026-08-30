"""Final execution boundary guard (Phase 1, P0-B).

Every mutation that lands in the database must pass OWNER-constraint enforcement
AT the point of execution — not only at recommendation time. This module is the
single choke point that:
  1. verifies tenant / identity consistency,
  2. verifies the actor holds the required permission (when the caller requires it),
  3. re-validates the action against owner constraints using STABLE reason codes,
  4. records every block to the `constraint_blocks` observability table
     (best-effort, never fails the caller).

Reason codes are machine-readable marketing-free IDs. Every blocking outcome
carries exactly one code so tests and dashboards can assert stable behaviour.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.constraint_service import get_constraints, filter_action_with_code
from app.utils.clock import utcnow

# Guard-level (non-constraint) stable codes
CODE_OK = "GUARD_OK"
CODE_TENANT_MISMATCH = "GUARD_TENANT_MISMATCH"
CODE_INSUFFICIENT_PERMISSION = "GUARD_INSUFFICIENT_PERMISSION"
CODE_UNKNOWN_ACTION = "GUARD_UNKNOWN_ACTION"
CODE_STATE_INVALID = "GUARD_STATE_INVALID"
# P0-B at-execution re-verification codes (Section 8/9 race + stale defense)
CODE_STALE_REORDER = "GUARD_STALE_REORDER"
CODE_ITEM_NOT_FOUND = "GUARD_ITEM_NOT_FOUND"

# Legacy ActionExecutor action types → canonical constraint groups
_ACTION_TO_CONSTRAINT = {
    "RESTOCK": "reorder",
    "restock": "reorder",
    "reorder": "reorder",
    "PRICE_CHANGE": "pricing_increase",
    "pricing_increase": "pricing_increase",
    "pricing_decrease": "pricing_decrease",
    "DISCOUNT": "discount",
    "discount": "discount",
    "margin_fix": "discount",
    "TRANSFER": "transfer_inventory",
    "transfer_inventory": "transfer_inventory",
}


@dataclass
class ExecutionVerdict:
    feasible: bool
    reason_code: str = CODE_OK
    reason: str = "Allowed under current owner constraints."
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def blocked(self) -> bool:
        return not self.feasible


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value) if value is not None else default
    except (TypeError, ValueError):
        return default


def _build_constraint_payload(
    action_type: str,
    payload: dict[str, Any],
    previous_state: Optional[dict[str, Any]] = None,
    new_state: Optional[dict[str, Any]] = None,
    cost: Optional[float] = None,
) -> dict[str, Any]:
    """Extract the constraint-checkable fields for a given action type.

    For legacy RESTOCK the stock delta is derived from previous/new state so the
    guard can enforce cash budget / minimum-safety-stock on that path too.
    """
    cp = {
        "item_id": payload.get("item_id") or payload.get("sku"),
        "supplier_id": payload.get("supplier_id"),
        "supplier_moq": payload.get("supplier_moq") or payload.get("supplier_min_order_sar"),
        "quantity": payload.get("quantity"),
        "current_stock": payload.get("current_stock"),
        "sell_price_sar": payload.get("sell_price_sar") or payload.get("sell_price"),
        "cost_price_sar": payload.get("cost_price_sar") or payload.get("cost_price"),
        "estimated_cost_sar": payload.get("estimated_cost_sar"),
        "discount_pct": payload.get("discount_pct") or payload.get("recommended_discount_pct"),
        "from_business_id": payload.get("from_business_id"),
        "to_business_id": payload.get("to_business_id"),
    }

    if action_type in {"RESTOCK", "restock", "reorder"}:
        if cp["quantity"] is None and previous_state is not None and new_state is not None:
            cp["quantity"] = _to_float(new_state.get("current_stock")) - _to_float(previous_state.get("current_stock"))
        if cp["current_stock"] is None and previous_state is not None:
            cp["current_stock"] = previous_state.get("current_stock")
        if cp["estimated_cost_sar"] is None:
            cp["estimated_cost_sar"] = _to_float(cp["quantity"]) * _to_float(cost)
    elif action_type in {"DISCOUNT", "discount", "margin_fix"}:
        cp["discount_pct"] = cp["discount_pct"] if cp["discount_pct"] is not None else payload.get("discount_pct")
    return cp


async def validate_action_for_execution(
    db: AsyncSession,
    *,
    business_id: str | UUID,
    action_type: str,
    payload: dict[str, Any],
    actor_business_id: Optional[str | UUID] = None,
    required_permission: Optional[str] = None,
    has_permission: Optional[bool] = None,
    previous_state: Optional[dict[str, Any]] = None,
    new_state: Optional[dict[str, Any]] = None,
    cost: Optional[float] = None,
) -> ExecutionVerdict:
    """Return an ExecutionVerdict; if ``feasible`` is False the action MUST NOT execute.

    Order of precedence (first failing check wins):
      1. tenant identity, 2. permission, 3. owner constraints.
    """
    constraint_key = _ACTION_TO_CONSTRAINT.get(action_type, action_type)
    if constraint_key not in {"discount", "reorder", "transfer_inventory", "pricing_increase", "pricing_decrease"}:
        return ExecutionVerdict(
            feasible=True,
            reason_code=CODE_OK,
            reason="Action type has no owner-constraint rules; permitted.",
        )

    # 1) Tenant / identity consistency
    if actor_business_id is not None and str(actor_business_id) != str(business_id):
        return ExecutionVerdict(
            feasible=False,
            reason_code=CODE_TENANT_MISMATCH,
            reason=f"Action targets business {business_id} but actor operates business {actor_business_id}.",
            metadata={"target_business_id": str(business_id), "actor_business_id": str(actor_business_id)},
        )

    # 2) Permission (when the caller requires it)
    if required_permission is not None and (has_permission is None or not has_permission):
        return ExecutionVerdict(
            feasible=False,
            reason_code=CODE_INSUFFICIENT_PERMISSION,
            reason=f"Missing required permission: {required_permission}.",
            metadata={"required_permission": required_permission},
        )

    # 3) Owner constraints (stable reason codes from constraint_service)
    constraints = await get_constraints(db, str(business_id))
    cp = _build_constraint_payload(action_type, payload, previous_state, new_state, cost)
    # Resolve unit cost so the cash-budget / max-purchase checks can be enforced
    # on legacy executor paths that do not carry cost themselves.
    if (
        constraint_key == "reorder"
        and cp.get("item_id")
        and _to_float(cp.get("estimated_cost_sar")) <= 0
    ):
        _cost_row = await db.execute(
            text("SELECT cost_price FROM items WHERE id = :id"),
            {"id": str(cp["item_id"])},
        )
        _cr = _cost_row.fetchone()
        if _cr and _cr.cost_price is not None:
            cp["estimated_cost_sar"] = _to_float(cp.get("quantity", 0)) * _to_float(_cr.cost_price)
    feasible, reason_code, reason = filter_action_with_code(constraint_key, cp, constraints)

    metadata: dict[str, Any] = {
        "constraint_key": constraint_key,
        "constraint_payload": {k: v for k, v in cp.items() if v is not None},
    }

    # 4) P0-B at-execution re-verification: re-read CURRENT state at the moment
    #    of execution (not the stale recommendation snapshot). Guards against the
    #    race where a PO was already created / stock changed between
    #    recommendation and execution (Sections 8/9).
    if feasible and constraint_key == "reorder" and cp.get("item_id"):
        stag = await _reverify_reorder_state(db, str(business_id), str(cp["item_id"]), _to_float(cp.get("quantity")))
        if stag is not None:
            return ExecutionVerdict(
                feasible=False,
                reason_code=stag["code"],
                reason=stag["reason"],
                metadata={**metadata, "reverified_at_execution": True, **_drop_none(stag.get("meta", {}))},
            )

    return ExecutionVerdict(
        feasible=feasible,
        reason_code=reason_code,
        reason=reason,
        metadata=metadata,
    )


def _drop_none(d: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in d.items() if v is not None}


async def _reverify_reorder_state(
    db: AsyncSession,
    business_id: str,
    item_id: str,
    requested_qty: float,
) -> Optional[dict[str, Any]]:
    """Re-read the item's current inventory + confirmed inbound at execution time.

    Returns a blocking verdict dict (with ``code`` / ``reason`` / ``meta``) or
    ``None`` when the reorder is still warranted. This is the race defense: if a
    PO was already placed (or stock refilled) since the recommendation, executing
    the reorder would over-order.
    """
    try:
        from app.services.po_service import get_confirmed_inbound_map, usable_confirmed_inbound, projected_stockout_date
        from app.utils.clock import utcnow
        from decimal import Decimal as _D

        _row = await db.execute(
            text("SELECT current_stock, item_id FROM inventory WHERE item_id = :item_id AND business_id = :business_id"),
            {"item_id": item_id, "business_id": business_id},
        )
        _inv = _row.fetchone()

        _itm = await db.execute(text("SELECT id FROM items WHERE id = :id AND business_id = :business_id"), {"id": item_id, "business_id": business_id})
        if _itm.fetchone() is None:
            return {
                "code": CODE_ITEM_NOT_FOUND,
                "reason": "Item does not exist in this business; refusing execution.",
                "meta": {"item_id": item_id, "business_id": business_id},
            }

        current_stock = _D(str(float(_inv.current_stock))) if _inv and _inv.current_stock is not None else _D("0")
        as_of = utcnow().date()
        inbound_map = await get_confirmed_inbound_map(db, business_id=business_id, as_of=as_of)
        so = projected_stockout_date(as_of=as_of, current_stock=current_stock, daily_demand=_D("1"))
        # Use a nominal daily demand so that only a real, imminent stockout keeps
        # the reorder feasible; any confirmed inbound (usable before stockout)
        # that already meets the requested quantity makes the reorder stale.
        timing = usable_confirmed_inbound(inbound_map.get(str(item_id)), stockout_date=so)
        usable_inbound = _to_float(timing.usable_qty) if timing else 0.0
        total_inbound = _to_float(timing.total_qty) if timing else 0.0

        if usable_inbound >= requested_qty > 0:
            return {
                "code": CODE_STALE_REORDER,
                "reason": (
                    f"Reorder is stale: {usable_inbound:.0f} units of confirmed inbound "
                    f"already covers the requested {requested_qty:.0f} before projected stockout."
                ),
                "meta": {"item_id": item_id, "usable_inbound_qty": usable_inbound, "requested_qty": requested_qty, "total_inbound_qty": total_inbound},
            }
        return None
    except Exception:
        # If re-verification cannot run (e.g. table missing), fail OPEN to avoid
        # blocking legitimate executions on infra errors.
        return None


async def record_constraint_block(
    db: AsyncSession,
    *,
    business_id: str | UUID,
    action_type: str,
    reason_code: str,
    reason: str,
    action_id: Optional[str | UUID] = None,
    payload: Optional[dict[str, Any]] = None,
    attempted_by: Optional[str | UUID] = None,
) -> None:
    """Persist a blocked execution for observability. Best-effort: must never
    raise, because a failed observability write must not prevent the block from
    being enforced (or crash a caller that is correctly refusing mutation)."""
    try:
        import json as _json
        await db.execute(
            text(
                "INSERT INTO constraint_blocks "
                "(id, business_id, action_id, action_type, reason_code, reason, payload, attempted_by, created_at) "
                "VALUES (gen_random_uuid(), :business_id, :action_id, :action_type, :reason_code, :reason, "
                "CAST(:payload AS JSON), :attempted_by, :created_at)"
            ),
            {
                "business_id": str(business_id),
                "action_id": str(action_id) if action_id else None,
                "action_type": action_type,
                "reason_code": reason_code,
                "reason": reason[:1000],
                "payload": _json.dumps(payload) if payload else "{}",
                "attempted_by": str(attempted_by) if attempted_by else None,
                "created_at": utcnow(),
            },
        )
        await db.commit()
    except Exception:
        await db.rollback()
