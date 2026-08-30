"""First-class business constraints applied before recommendation selection.

V8 enhancements:
  - Minimum margin enforcement
  - Strategic product handling
  - MOQ vs cash budget validation
  - Maximum discount percentage check
  - Transfer route blocking
  - Cash budget enforcement
  - Minimum safety stock enforcement
  - Maximum purchase amount enforcement
  - Supplier preference enforcement
  - Branch priority enforcement

Phase 1 (P0-B): every constraint failure now carries a STABLE machine-readable
reason code (``CONSTRAINT_*``) in addition to the human-readable message. The
``filter_action`` API (returns ``(feasible, reason)``) is preserved for existing
callers; ``filter_action_with_code`` returns ``(feasible, code, reason)`` and is
what the final-execution guard uses.
"""
from __future__ import annotations
from typing import Any
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# Stable reason codes — tests and observability assert on these, never on the
# human message, so wording can change without breaking consumers.
CODE_DISCOUNT_BLOCKED = "CONSTRAINT_DISCOUNT_BLOCKED"
CODE_DISCOUNT_STRATEGIC = "CONSTRAINT_DISCOUNT_STRATEGIC"
CODE_DISCOUNT_MAX_PCT = "CONSTRAINT_DISCOUNT_MAX_PCT"
CODE_DISCOUNT_MIN_MARGIN = "CONSTRAINT_DISCOUNT_MIN_MARGIN"
CODE_REORDER_CASH_BUDGET = "CONSTRAINT_REORDER_CASH_BUDGET"
CODE_REORDER_MAX_PURCHASE = "CONSTRAINT_REORDER_MAX_PURCHASE"
CODE_REORDER_MOQ_BUDGET = "CONSTRAINT_REORDER_MOQ_BUDGET"
CODE_REORDER_MIN_SAFETY = "CONSTRAINT_REORDER_MIN_SAFETY_STOCK"
CODE_REORDER_SUPPLIER_PREFERENCE = "CONSTRAINT_REORDER_SUPPLIER_PREFERENCE"
CODE_TRANSFER_ROUTE = "CONSTRAINT_TRANSFER_ROUTE"
CODE_TRANSFER_PRIORITY = "CONSTRAINT_TRANSFER_PRIORITY"
CODE_OK = "CONSTRAINT_OK"

_FEASIBLE = (True, CODE_OK, "Feasible under current owner constraints.")


async def get_constraints(db: AsyncSession, business_id: str) -> dict[str, Any]:
    r = await db.execute(text("SELECT constraints_json FROM businesses WHERE id=:b"), {"b": str(business_id)})
    row = r.fetchone()
    return row.constraints_json if row and isinstance(row.constraints_json, dict) else {}


def filter_action_with_code(
    action_type: str,
    payload: dict[str, Any],
    constraints: dict[str, Any],
) -> tuple[bool, str, str]:
    """Validate an action against owner constraints.

    Returns (feasible, stable_reason_code, human_reason).
    """
    # Discount / pricing decrease
    if action_type in {"discount", "pricing_decrease"}:
        item_id = str(payload.get("item_id", ""))

        # Blocked products check
        blocked = set(map(str, constraints.get("blocked_discount_products", [])))
        if item_id in blocked:
            return False, CODE_DISCOUNT_BLOCKED, f"Discount is blocked for product {item_id} by owner constraints."

        # Strategic product check — strategic products should not be discounted
        strategic = set(map(str, constraints.get("strategic_products", [])))
        if item_id in strategic:
            return False, CODE_DISCOUNT_STRATEGIC, f"Product {item_id} is marked as strategic by owner constraints and should not be discounted."

        # Maximum discount percentage check
        max_discount = float(constraints.get("max_discount_pct", constraints.get("max_discount", 100)))
        discount_pct = float(payload.get("discount_pct", 0) or payload.get("recommended_discount_pct", 0) or 0)
        if discount_pct > max_discount:
            return False, CODE_DISCOUNT_MAX_PCT, f"Discount {discount_pct}% exceeds owner maximum of {max_discount}%."

        # Minimum margin check (after discount)
        sell_price = float(payload.get("sell_price_sar", 0) or 0)
        cost_price = float(payload.get("cost_price_sar", 0) or 0)
        min_margin = constraints.get("minimum_margin_pct")
        if sell_price > 0 and cost_price > 0 and min_margin is not None:
            discounted_price = sell_price * (1 - discount_pct / 100)
            margin_after_pct = ((discounted_price - cost_price) / discounted_price * 100) if discounted_price > 0 else 0
            if margin_after_pct < float(min_margin):
                return False, CODE_DISCOUNT_MIN_MARGIN, f"After {discount_pct}% discount, margin {margin_after_pct:.1f}% falls below owner minimum {float(min_margin):.1f}%."

    # Reorder / restock
    if action_type in {"reorder", "restock"}:
        budget = constraints.get("cash_budget")
        cost = float(payload.get("estimated_cost_sar", 0) or 0)

        if budget is not None and cost > float(budget):
            return False, CODE_REORDER_CASH_BUDGET, f"Purchase cost SAR {cost:.0f} exceeds owner cash budget SAR {float(budget):.0f}."

        # Maximum purchase amount check
        max_purchase = constraints.get("maximum_purchase_amount")
        if max_purchase is not None and cost > float(max_purchase):
            return False, CODE_REORDER_MAX_PURCHASE, f"Purchase cost SAR {cost:.0f} exceeds maximum purchase amount SAR {float(max_purchase):.0f}."

        # MOQ check
        moq = payload.get("supplier_moq")
        if moq is not None and budget is not None:
            if float(moq) > float(budget):
                return False, CODE_REORDER_MOQ_BUDGET, f"Supplier MOQ SAR {float(moq):.0f} exceeds owner cash budget SAR {float(budget):.0f}."

        # Minimum safety stock check — reorder must not leave stock below minimum
        min_safety = constraints.get("minimum_safety_stock")
        if min_safety is not None:
            reorder_qty = float(payload.get("quantity", 0) or 0)
            current_stock = float(payload.get("current_stock", 0) or 0)
            if current_stock + reorder_qty < float(min_safety):
                return False, CODE_REORDER_MIN_SAFETY, f"Reorder would leave stock {current_stock + reorder_qty:.0f} below minimum safety stock {float(min_safety):.0f}."

        # Supplier preference check
        preferred_suppliers = constraints.get("supplier_preferences", [])
        supplier_id = str(payload.get("supplier_id", ""))
        if preferred_suppliers and supplier_id and supplier_id not in map(str, preferred_suppliers):
            return False, CODE_REORDER_SUPPLIER_PREFERENCE, f"Supplier {supplier_id} is not in the owner's preferred supplier list."

    # Transfer
    if action_type == "transfer_inventory":
        route = f"{payload.get('from_business_id', '')}->{payload.get('to_business_id', '')}"
        blocked_routes = set(constraints.get("blocked_transfer_routes", []))
        if route in blocked_routes:
            return False, CODE_TRANSFER_ROUTE, f"Transfer route {route} is blocked by owner constraints."

        # Branch priority check
        branch_priorities = constraints.get("branch_priority", {})
        from_branch = str(payload.get("from_business_id", ""))
        to_branch = str(payload.get("to_business_id", ""))
        if branch_priorities and isinstance(branch_priorities, dict):
            from_priority = branch_priorities.get(from_branch, 0)
            to_priority = branch_priorities.get(to_branch, 0)
            if to_priority < from_priority:
                return False, CODE_TRANSFER_PRIORITY, f"Transfer to branch {to_branch} (priority {to_priority}) is lower than source branch {from_branch} (priority {from_priority})."

    return _FEASIBLE


def filter_action(action_type: str, payload: dict[str, Any], constraints: dict[str, Any]) -> tuple[bool, str]:
    """Backward-compatible wrapper returning (feasible, reason)."""
    feasible, _code, reason = filter_action_with_code(action_type, payload, constraints)
    return feasible, reason
