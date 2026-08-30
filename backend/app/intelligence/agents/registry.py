"""Agent registry and dispatcher."""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.intelligence.agents.base import BaseAgent
from app.intelligence.agents.compliance_agent import ComplianceAgent
from app.intelligence.agents.finance_agent import FinanceAgent
from app.intelligence.agents.inventory_agent import InventoryAgent
from app.intelligence.agents.pricing_agent import PricingAgent
from app.intelligence.agents.supplier_agent import SupplierAgent
from app.intelligence.agents.recovery_agent import RecoveryAgent
from app.intelligence.agents.procurement_agent import ProcurementAgent
from app.intelligence.agents.margin_agent import MarginAgent


AGENT_REGISTRY: dict[str, type[BaseAgent]] = {
    "inventory": InventoryAgent,
    "pricing": PricingAgent,
    "supplier": SupplierAgent,
    "finance": FinanceAgent,
    "compliance": ComplianceAgent,
    "recovery": RecoveryAgent,
    "procurement": ProcurementAgent,
    "margin": MarginAgent,
}


async def dispatch_agent(
    session: AsyncSession,
    business_id: UUID | str,
    agent_type: str,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run a specialized agent and return its proposal."""
    agent_cls = AGENT_REGISTRY.get(agent_type)
    if not agent_cls:
        raise ValueError(f"Unknown agent_type: {agent_type}")
    agent = agent_cls(session, business_id)
    return await agent.propose(context)


def list_agent_types() -> list[str]:
    return list(AGENT_REGISTRY.keys())
