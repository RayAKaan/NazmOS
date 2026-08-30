"""Base class and shared utilities for NazmOS specialized agents (Phase 1 runtime contract).

An agent now declares an explicit surface (brief §5):

    Agent
    ├── Identity      (agent_type, name)
    ├── Objective     (objective)
    ├── Context       (business memory / context passed in)
    ├── Tools         (names the agent may call via the tool registry)
    ├── Memory        (existing business-memory engine)
    ├── Policies      (per-action-type autonomy policies via policy_engine)
    ├── Permissions   (read-only vs mutating tools)
    ├── Model provider (LLMOrchestrator — already abstracted)
    ├── Execution budget (max_tool_calls)
    ├── Triggers      (event types that wake this agent)
    └── Verification  (verify_outcome hook)

Existing agents (inventory/pricing/supplier/finance/compliance) remain valid: they
only implement `propose()`. New agents may override `verify_outcome()`.
"""
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

    # ── Identity / objective (Phase 1 runtime contract) ──────────────────
    agent_type: str = "base"
    name: str = "Base Agent"
    objective: str = ""

    # ── Capability surface ────────────────────────────────────────────────
    tools: list[str] = []            # tool names this agent may call (tool_registry)
    read_only: bool = True           # True = may only call read-only tools
    max_tool_calls: int = 8          # execution budget
    triggers: list[str] = []         # event types that wake this agent (brief §11)

    def __init__(self, session: AsyncSession, business_id: UUID | str):
        self.session = session
        self.business_id = business_id

    async def propose(self, context: dict[str, Any] | None = None) -> dict[str, Any]:
        """Return a proposal payload for this agent's domain.

        Must be implemented by subclasses.
        """
        raise NotImplementedError

    async def verify_outcome(self, context: dict[str, Any] | None = None) -> dict[str, Any]:
        """Post-execution verification hook (brief §5 / §12 step 8).

        Default: a no-op pass-through so existing agents keep working. Subclasses
        that execute actions should override this to measure actual impact.
        """
        return {"verified": False, "note": f"{self.agent_type} has no verification hook"}

    async def _get_memory(self, memory_type: str) -> dict[str, Any]:
        memory = await get_or_create_memory(self.session, self.business_id, memory_type)
        return memory.data
