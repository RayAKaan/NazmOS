"""Execution contracts — request/result types for the orchestration layer.

These are the single source of truth for execution inputs and outputs.
Routers produce requests; workflows consume them; runners return results.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional
from uuid import UUID


SCHEMA_VERSION = "1.0.0"

CANONICAL_ACTION_TYPES = frozenset({
    "DISCOUNT", "REORDER", "RECOVERY_MATCH", "TRANSFER", "RESTOCK",
    "PRICING_INCREASE", "PRICING_DECREASE", "MARGIN_FIX", "CASH_ALERT",
    "EXPIRY_ALERT", "DEAD_STOCK", "STOCK_CHECK", "SEEK_APPROVAL",
    "DATA_EXPORT", "DATA_DELETION_SCHEDULED", "DATA_DELETION_IMMEDIATE",
    "DATA_DELETION_CANCELLED", "REVIEW", "REVIEW_PRICING", "REVIEW_SUPPLIER",
    "GENERATE_DECISION", "INFO_ONLY", "STAFF_SCHEDULE", "SUPPLIER_SWITCH",
})


def serialize_decision_action(
    *,
    business_id: Optional[UUID] = None,
    action_type: str = "",
    entity_type: str = "",
    entity_id: Optional[UUID] = None,
    payload: dict[str, Any] | None = None,
    previous_state: dict[str, Any] | None = None,
    new_state: dict[str, Any] | None = None,
    source: str = "manual",
    decision_id: Optional[UUID] = None,
    user_id: Optional[UUID] = None,
    plan_id: Optional[UUID] = None,
    action_id: Optional[UUID] = None,
    note: str = "Approved",
    decided_by: Optional[UUID] = None,
    schema_version: str = SCHEMA_VERSION,
    decision_type: str = "",
) -> dict[str, Any]:
    """Canonical serializer for decision/action payloads.

    Ensures stable, deterministic serialization with explicit versioning.
    All production callers should use this function rather than building
    payloads inline, to guarantee field coherence and provenance.
    """
    if payload is None:
        payload = {}
    if previous_state is None:
        previous_state = {}
    if new_state is None:
        new_state = {}

    # Validate action_type against known set (informational only; runtime
    # permissive so existing payloads remain valid).
    _ = schema_version  # reserved for future validation

    return {
        "schema_version": schema_version,
        "decision_type": decision_type,
        "business_id": str(business_id) if business_id else None,
        "action_type": action_type,
        "entity_type": entity_type,
        "entity_id": str(entity_id) if entity_id else None,
        "payload": payload,
        "previous_state": previous_state,
        "new_state": new_state,
        "source": source,
        "decision_id": str(decision_id) if decision_id else None,
        "user_id": str(user_id) if user_id else None,
        "plan_id": str(plan_id) if plan_id else None,
        "action_id": str(action_id) if action_id else None,
        "note": note,
        "decided_by": str(decided_by) if decided_by else None,
    }


def deserialize_decision_action(data: dict[str, Any]) -> dict[str, Any]:
    """Canonical deserializer for decision/action payloads.

    Returns a plain dict with normalized keys. Missing fields default to
    safe emptiness. Does not perform validation of business rules — that
    is the caller's responsibility.
    """
    schema_version = data.get("schema_version", SCHEMA_VERSION)
    decision_type = data.get("decision_type", "")

    return {
        "schema_version": schema_version,
        "decision_type": decision_type,
        "business_id": UUID(data["business_id"]) if data.get("business_id") else None,
        "action_type": data.get("action_type", ""),
        "entity_type": data.get("entity_type", ""),
        "entity_id": UUID(data["entity_id"]) if data.get("entity_id") else None,
        "payload": data.get("payload", {}),
        "previous_state": data.get("previous_state", {}),
        "new_state": data.get("new_state", {}),
        "source": data.get("source", "manual"),
        "decision_id": UUID(data["decision_id"]) if data.get("decision_id") else None,
        "user_id": UUID(data["user_id"]) if data.get("user_id") else None,
        "plan_id": UUID(data["plan_id"]) if data.get("plan_id") else None,
        "action_id": UUID(data["action_id"]) if data.get("action_id") else None,
        "note": data.get("note", "Approved"),
        "decided_by": UUID(data["decided_by"]) if data.get("decided_by") else None,
    }


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
    schema_version: str = SCHEMA_VERSION
    decision_type: str = ""


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
