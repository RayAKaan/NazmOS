"""Base class and shared utilities for NazmOS specialized agents."""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.business_memory import get_or_create_memory


class BaseAgent:
    """Abstract base for all specialized business agents.

    Agents read business memory and emit structured proposal events. They do not
    call each other directly; all coordination happens through the event bus.
    """

    agent_type: str = "base"

    def __init__(self, session: AsyncSession, business_id: UUID | str):
        self.session = session
        self.business_id = business_id

    async def propose(self, context: dict[str, Any] | None = None) -> dict[str, Any]:
        """Return a proposal payload for this agent's domain.

        Must be implemented by subclasses.
        """
        raise NotImplementedError

    async def _get_memory(self, memory_type: str) -> dict[str, Any]:
        memory = await get_or_create_memory(self.session, self.business_id, memory_type)
        return memory.data
