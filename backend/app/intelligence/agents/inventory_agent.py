"""Inventory Agent — proposes restock, discount, and dead-stock actions."""
from __future__ import annotations

from typing import Any

from app.database.models import MemoryType
from app.intelligence.agents.base import BaseAgent


class InventoryAgent(BaseAgent):
    agent_type = "inventory"

    async def propose(self, context: dict[str, Any] | None = None) -> dict[str, Any]:
        memory = await self._get_memory(MemoryType.CURRENT_STATE.value)
        inventory = memory.get("inventory", {})

        proposals = []
        for item_key, item_state in inventory.items():
            stock = float(item_state.get("stock", 0))
            reorder_flag = item_state.get("reorder_flag")
            if reorder_flag or stock < 10:
                proposals.append({
                    "action_type": "restock",
                    "item_key": item_key,
                    "current_stock": stock,
                    "suggested_qty": max(50, int(20 - stock) * 5),
                    "reason": f"Stock level {stock} is below reorder threshold",
                    "confidence": 0.85,
                    "urgency": 0.9 if stock < 5 else 0.6,
                })

        patterns = await self._get_memory(MemoryType.PATTERNS.value)
        pricing = patterns.get("pricing", {})
        for item_key, history_data in pricing.items():
            history = history_data.get("history", [])
            if len(history) >= 5:
                decreases = sum(
                    1 for i in range(1, len(history))
                    if float(history[i].get("price", 0)) < float(history[i - 1].get("price", 0))
                )
                if decreases >= 3:
                    proposals.append({
                        "action_type": "discount",
                        "item_key": item_key,
                        "recommended_discount_pct": 15,
                        "reason": "Repeated price decreases suggest weak demand",
                        "confidence": 0.65,
                        "urgency": 0.5,
                    })

        return {
            "agent_type": self.agent_type,
            "proposal_event_type": "agent.proposal",
            "payload": {"proposals": proposals},
            "confidence": 0.8 if proposals else 0.9,
            "reasons": ["Memory-based inventory signals"],
        }
