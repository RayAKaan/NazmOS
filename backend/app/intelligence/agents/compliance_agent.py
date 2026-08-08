"""Compliance Agent — proposes expiry and regulation alerts."""
from __future__ import annotations

from typing import Any

from app.database.models import MemoryType
from app.intelligence.agents.base import BaseAgent


class ComplianceAgent(BaseAgent):
    agent_type = "compliance"

    async def propose(self, context: dict[str, Any] | None = None) -> dict[str, Any]:
        memory = await self._get_memory(MemoryType.CURRENT_STATE.value)
        inventory = memory.get("inventory", {})

        proposals = []
        for item_key, item_state in inventory.items():
            expiry_days = item_state.get("expiry_days")
            if expiry_days is not None and int(expiry_days) <= 30:
                proposals.append({
                    "action_type": "expiry_alert",
                    "item_key": item_key,
                    "expiry_days": int(expiry_days),
                    "reason": f"Item expires in {expiry_days} days",
                    "confidence": 0.9,
                    "urgency": 0.8 if int(expiry_days) <= 7 else 0.5,
                })

        return {
            "agent_type": self.agent_type,
            "proposal_event_type": "agent.proposal",
            "payload": {"proposals": proposals},
            "confidence": 0.85 if proposals else 0.9,
            "reasons": ["Inventory expiry and regulation context"],
        }
