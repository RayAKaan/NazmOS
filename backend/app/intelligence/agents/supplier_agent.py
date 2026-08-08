"""Supplier Agent — proposes supplier switches and reviews from graph signals."""
from __future__ import annotations

from typing import Any

from sqlalchemy import select

from app.database.models import GraphRelationship
from app.intelligence.agents.base import BaseAgent


class SupplierAgent(BaseAgent):
    agent_type = "supplier"

    async def propose(self, context: dict[str, Any] | None = None) -> dict[str, Any]:
        result = await self.session.execute(
            select(GraphRelationship)
            .where(
                GraphRelationship.business_id == self.business_id,
                GraphRelationship.relation_type == "SUPPLIES",
            )
            .order_by(GraphRelationship.strength.asc())
            .limit(10)
        )
        rels = result.scalars().all()

        proposals = []
        for rel in rels:
            strength = float(rel.strength) if rel.strength else 0.0
            if strength < 0.4:
                proposals.append({
                    "action_type": "supplier_switch",
                    "source_id": str(rel.source_id),
                    "target_id": str(rel.target_id),
                    "strength": strength,
                    "reason": "Supplier relationship strength is low",
                    "confidence": 0.6,
                    "urgency": 0.45,
                })

        return {
            "agent_type": self.agent_type,
            "proposal_event_type": "agent.proposal",
            "payload": {"proposals": proposals},
            "confidence": 0.7 if proposals else 0.9,
            "reasons": ["Knowledge graph supplier relationship signals"],
        }
