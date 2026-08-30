"""Canonical action capabilities and execution semantics."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any

@dataclass(frozen=True)
class ActionSpec:
    action_type: str
    description: str
    approval_required: bool
    can_execute: bool
    execution_mode: str
    simulator: bool
    measurement: str
    fallback: str | None = None

ACTION_REGISTRY: dict[str, ActionSpec] = {
    "discount": ActionSpec("discount", "Reduce selling price for controlled recovery.", True, False, "MANUAL", True, "sales_margin", "review"),
    "reorder": ActionSpec("reorder", "Create a purchase order when supplier data and execution are available.", True, True, "AUTONOMOUS", True, "inventory_revenue", "manual"),
    "recovery_match": ActionSpec("recovery_match", "Recover surplus through an approved transfer/match.", True, False, "MANUAL", True, "inventory_value", "manual"),
    "margin_fix": ActionSpec("margin_fix", "Change price to protect minimum margin.", True, False, "MANUAL", True, "sales_margin", "review"),
    "transfer_inventory": ActionSpec("transfer_inventory", "Transfer stock between permitted branches.", True, True, "AUTONOMOUS", True, "inventory_value", "manual"),
    "restock": ActionSpec("restock", "Create a purchase order.", True, True, "AUTONOMOUS", True, "inventory_revenue", "manual"),
    "pricing_increase": ActionSpec("pricing_increase", "Increase selling price.", True, True, "AUTONOMOUS", True, "sales_margin", "manual"),
    "pricing_decrease": ActionSpec("pricing_decrease", "Decrease selling price.", True, True, "AUTONOMOUS", True, "sales_margin", "manual"),
    "expiry_alert": ActionSpec("expiry_alert", "Informational expiry warning.", False, False, "MANUAL", False, "none", None),
}

def get_action_spec(action_type: str) -> ActionSpec:
    return ACTION_REGISTRY.get(action_type, ActionSpec(action_type, "Unregistered action.", True, False, "MANUAL", False, "none", "review"))

def can_execute(action_type: str, payload: dict[str, Any] | None = None) -> bool:
    payload = payload or {}
    spec = get_action_spec(action_type)
    if action_type in {"discount", "margin_fix"}:
        return bool(payload.get("suggested_price") or payload.get("recommended_sell_price_sar"))
    if action_type == "recovery_match":
        return bool(payload.get("from_business_id") and payload.get("to_business_id") and payload.get("quantity"))
    return spec.can_execute
