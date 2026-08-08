"""Pricing Agent — proposes price increases/decreases based on demand and history."""
from __future__ import annotations

from typing import Any

from app.database.models import MemoryType
from app.intelligence.agents.base import BaseAgent


class PricingAgent(BaseAgent):
    agent_type = "pricing"

    async def propose(self, context: dict[str, Any] | None = None) -> dict[str, Any]:
        patterns = await self._get_memory(MemoryType.PATTERNS.value)
        pricing = patterns.get("pricing", {})
        top_products = patterns.get("top_products", {})

        proposals = []
        for item_key, history_data in pricing.items():
            history = history_data.get("history", [])
            if len(history) >= 2:
                latest = history[-1]
                previous = history[-2]
                latest_price = float(latest.get("price", 0))
                previous_price = float(previous.get("price", 0))
                if latest_price > previous_price * 1.05:
                    proposals.append({
                        "action_type": "pricing_decrease",
                        "item_key": item_key,
                        "current_price": latest_price,
                        "previous_price": previous_price,
                        "reason": "Recent price increase may reduce demand",
                        "confidence": 0.6,
                        "urgency": 0.5,
                    })
                elif latest_price < previous_price * 0.95:
                    proposals.append({
                        "action_type": "pricing_increase",
                        "item_key": item_key,
                        "current_price": latest_price,
                        "previous_price": previous_price,
                        "reason": "Recent price decrease leaves margin on the table",
                        "confidence": 0.6,
                        "urgency": 0.4,
                    })

        for item_key, data in top_products.items():
            qty = float(data.get("quantity_30d", 0))
            if qty > 50:
                proposals.append({
                    "action_type": "pricing_increase",
                    "item_key": item_key,
                    "quantity_30d": qty,
                    "reason": "High sales velocity in the last 30 days",
                    "confidence": 0.7,
                    "urgency": 0.5,
                })

        return {
            "agent_type": self.agent_type,
            "proposal_event_type": "agent.proposal",
            "payload": {"proposals": proposals},
            "confidence": 0.75 if proposals else 0.9,
            "reasons": ["Price history and demand velocity signals"],
        }
