from dataclasses import dataclass
from datetime import date, timedelta
from typing import List, Optional
from enum import Enum
import uuid
import json


class ActionType(str, Enum):
    RESTOCK = "RESTOCK"
    REDUCE_ORDER = "REDUCE_ORDER"
    DISCOUNT = "DISCOUNT"
    PROMOTE = "PROMOTE"
    REMOVE = "REMOVE"
    INVESTIGATE = "INVESTIGATE"
    STAFF_UP = "STAFF_UP"
    PRICE_INCREASE = "PRICE_INCREASE"


@dataclass
class Decision:
    action: ActionType
    item_name: str
    reason: str
    confidence: float
    priority: int
    item_id: Optional[str] = None
    quantity: Optional[float] = None
    unit: Optional[str] = "units"
    by_when: Optional[date] = None
    estimated_value: Optional[float] = None
    metadata: Optional[dict] = None

    def to_dict(self) -> dict:
        return {
            "id": str(uuid.uuid4()),
            "action": self.action.value,
            "item_id": self.item_id,
            "item_name": self.item_name,
            "quantity": self.quantity,
            "unit": self.unit,
            "by_when": self.by_when.isoformat() if self.by_when else "ASAP",
            "reason": self.reason,
            "estimated_value": self.estimated_value,
            "confidence": self.confidence,
            "priority": self.priority,
            "metadata": self.metadata or {},
        }


class DecisionEngine:

    def normalize_decisions(self, raw_decisions: list[dict]) -> list[dict]:
        """Normalize raw action dicts for legacy callers/tests."""
        normalized = []
        for raw in raw_decisions or []:
            action_type = str(raw.get("type") or raw.get("action") or "investigate").lower()
            normalized.append({
                "type": action_type,
                "title": raw.get("title") or action_type.replace("_", " " ).title(),
                "items": raw.get("items", []),
                "priority": raw.get("priority") or self.assign_priority(action_type, raw),
                "confidence": raw.get("confidence", 0.5),
            })
        return normalized

    def assign_priority(self, action_type: str, context: dict) -> str:
        stock = float(context.get("current_stock", 999) or 0)
        days_left = float(context.get("days_left", 999) or 999)
        if action_type in {"restock", "reorder"} and (stock <= 0 or days_left < 2):
            return "high"
        if action_type in {"discount", "margin_fix", "recovery_match"}:
            return "medium"
        return "low"

    def calculate_confidence(self, decision: dict, context: dict) -> float:
        confidence = 0.5
        if decision.get("items"):
            confidence += 0.2
        if context.get("historical_accuracy") is not None:
            confidence = (confidence + float(context.get("historical_accuracy"))) / 2
        return max(0.0, min(1.0, confidence))

    def generate_from_inventory(self, inventory_items: list) -> List[Decision]:
        decisions = []
        today = date.today()

        for item in inventory_items:
            stock = item.get("current_stock", 0)
            daily_avg = item.get("daily_avg_sale", 0)
            days_left = stock / daily_avg if daily_avg > 0.1 else 999
            reorder_level = item.get("reorder_level", 10)
            cost_price = item.get("cost_price", 0)
            sell_price = item.get("sell_price", 0)
            stock_value = stock * cost_price
            trend = item.get("trend_7d", "stable")

            if days_left < 2:
                reorder_qty = max(daily_avg * 7, reorder_level * 2)
                decisions.append(Decision(
                    action=ActionType.RESTOCK,
                    item_id=item.get("item_id"),
                    item_name=item.get("name", "Unknown Item"),
                    quantity=round(reorder_qty),
                    unit=item.get("unit", "units"),
                    by_when=today,
                    reason=f"Only {days_left:.1f} days of stock remaining. Will stock out today or tomorrow.",
                    estimated_value=round(reorder_qty * cost_price),
                    confidence=0.95,
                    priority=1,
                ))

            elif days_left < 5:
                reorder_qty = max(daily_avg * 10, reorder_level)
                decisions.append(Decision(
                    action=ActionType.RESTOCK,
                    item_id=item.get("item_id"),
                    item_name=item.get("name", "Unknown Item"),
                    quantity=round(reorder_qty),
                    unit=item.get("unit", "units"),
                    by_when=today + timedelta(days=2),
                    reason=f"{days_left:.1f} days of stock remaining.",
                    estimated_value=round(reorder_qty * cost_price),
                    confidence=0.90,
                    priority=2,
                ))

            elif days_left > 25 and daily_avg < 0.1:
                decisions.append(Decision(
                    action=ActionType.DISCOUNT,
                    item_id=item.get("item_id"),
                    item_name=item.get("name", "Unknown Item"),
                    quantity=stock,
                    reason=f"No meaningful sales. ﷼ {stock_value:,.0f} tied up. Discount to recover capital.",
                    estimated_value=stock_value,
                    confidence=0.85,
                    priority=3,
                ))

            elif days_left > 20 and trend == "down":
                decisions.append(Decision(
                    action=ActionType.REDUCE_ORDER,
                    item_id=item.get("item_id"),
                    item_name=item.get("name", "Unknown Item"),
                    reason=f"{days_left:.0f} days of stock with declining sales trend. Reduce next order.",
                    confidence=0.75,
                    priority=4,
                ))

        decisions.sort(key=lambda d: (d.priority, -d.confidence))
        return decisions

    def parse_llm_decisions(self, raw_json: list) -> List[Decision]:
        decisions = []
        for raw in raw_json:
            try:
                action = ActionType(raw["action"])
                decisions.append(Decision(
                    action=action,
                    item_id=raw.get("item_id"),
                    item_name=raw["item_name"],
                    quantity=raw.get("quantity"),
                    unit=raw.get("unit", "units"),
                    by_when=date.fromisoformat(raw["by_when"]) if raw.get("by_when") and raw["by_when"] != "ASAP" else None,
                    reason=raw.get("reason", ""),
                    estimated_value=raw.get("estimated_value"),
                    confidence=float(raw.get("confidence", 0.5)),
                    priority=int(raw.get("priority", 3)),
                ))
            except (KeyError, ValueError):
                continue
        return decisions
