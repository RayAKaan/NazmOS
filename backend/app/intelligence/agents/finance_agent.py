"""Finance Agent — proposes cash alerts from sales trend signals."""
from __future__ import annotations

from typing import Any

from app.database.models import MemoryType
from app.intelligence.agents.base import BaseAgent


class FinanceAgent(BaseAgent):
    agent_type = "finance"

    async def propose(self, context: dict[str, Any] | None = None) -> dict[str, Any]:
        memory = await self._get_memory(MemoryType.CURRENT_STATE.value)
        sales = memory.get("sales", {})
        daily = sales.get("daily", {})

        total_today = 0.0
        for day_data in daily.values():
            total_today += float(day_data.get("total", 0))

        proposals = []
        if total_today < 1000:
            proposals.append({
                "action_type": "cash_alert",
                "daily_total": total_today,
                "reason": "Daily sales are below expected threshold",
                "confidence": 0.7,
                "urgency": 0.6,
            })

        return {
            "agent_type": self.agent_type,
            "proposal_event_type": "agent.proposal",
            "payload": {"proposals": proposals},
            "confidence": 0.75 if proposals else 0.9,
            "reasons": ["Daily sales trend signals"],
        }
