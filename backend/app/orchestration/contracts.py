"""Execution contracts — request/result types for the orchestration layer.

These are the single source of truth for execution inputs and outputs.
Routers produce requests; workflows consume them; runners return results.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional
from uuid import UUID


@dataclass(frozen=True)
class ExecutionRequest:
    """Unified request for any execution path (manual, agent, simulated)."""

    business_id: Optional[UUID] = None
    action_type: str = ""
    entity_type: str = ""
    entity_id: Optional[UUID] = None
    payload: dict[str, Any] = field(default_factory=dict)
    previous_state: dict[str, Any] = field(default_factory=dict)
    new_state: dict[str, Any] = field(default_factory=dict)
    source: str = "manual"
    execution_key: str = ""
    decision_id: Optional[UUID] = None
    user_id: Optional[UUID] = None
    plan_id: Optional[UUID] = None
    # Agent-action specific (for approval workflow)
    action_id: Optional[UUID] = None
    note: str = "Approved"
    decided_by: Optional[UUID] = None


@dataclass
class ActionResult:
    """Outcome of a manual execution (actions.py / money_audit.py)."""

    success: bool
    action_id: Optional[UUID]
    message: str
    external_reference: Optional[str] = None
    error: Optional[str] = None


@dataclass
class ExecutionOutcome:
    """Structured outcome returned by workflows to runners."""

    ok: bool
    result: Any = None
    error: Optional[str] = None
    execution_key: str = ""
