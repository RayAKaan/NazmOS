"""Phase 5 + Phase A: AI Gateway -- the ONE safe policy-checked AI interface.

Entry contract:
    await ai_gateway.reason(payload, *, capability, purpose)

    payload: either a structured dict ({items:[...], business:{...}}) or an
             already-built ReasoningCapsule. A raw dict is immediately passed
             through the privacy firewall; nothing raw ever reaches the AI.

The gateway, in order:
  1. checks the AI policy kill switch for the capability,
  2. budget check,
  3. builds/signs a ReasoningCapsule via the privacy firewall,
  4. dispatches to the OpenCode brain transport,
  5. returns the validated BrainDecision (source: opencode | fallback).

Keep using this one interface instead of calling opencode_brain directly so
policy, budget, capsule construction and audit stay in a single choke point.
"""
from __future__ import annotations

import os
import time
from typing import Any, Mapping

from app.config import get_settings
from app.security.ai_policy import AiPolicy, audit_event
from app.security.capsule import ReasoningCapsule
from app.security.privacy_firewall import build_capsule_for_payload
from app.services.ai_budget import GLOBAL_AI_BUDGET
from app.services.opencode_brain import reason as opencode_reason
from app.services.security_audit_service import (
    record_ai_reasoning_request,
    record_security_event,
)

DEFAULT_CAPABILITY = "opencode_brain"
DEFAULT_PURPOSE = "resolve ambiguity in inventory decisions"

_policy = AiPolicy(get_settings())


def ai_enabled(capability: str = DEFAULT_CAPABILITY) -> bool:
    return _policy.enabled(capability)


async def reason(
    payload: Mapping[str, Any] | ReasoningCapsule,
    *,
    capability: str = DEFAULT_CAPABILITY,
    purpose: str = DEFAULT_PURPOSE,
    deterministic_decision: str | None = None,
) -> dict[str, Any]:
    """Policed entry point for OpenCode brain reasoning."""
    allowed, reason_blocked = _policy.allow_request(capability, purpose)
    if not allowed:
        audit_event("ai_denied", actor=capability, detail={"reason": reason_blocked})
        await record_security_event(
            event_type="ai.policy.denied",
            actor=capability,
            detail={"reason": reason_blocked},
        )
        return {
            "source": "fallback",
            "decision": deterministic_decision or "DO_NOTHING",
            "confidence": 0.0,
            "reasoning": f"AI policy blocked request: {reason_blocked}",
            "risk_flags": ["AI_POLICY_BLOCKED"],
            "latency_ms": 0,
        }

    if not GLOBAL_AI_BUDGET.can_call():
        audit_event("ai_budget_exhausted", actor=capability)
        await record_security_event(
            event_type="ai.budget.exhausted",
            actor=capability,
        )
        return {
            "source": "fallback",
            "decision": deterministic_decision or "DO_NOTHING",
            "confidence": 0.0,
            "reasoning": "AI budget unavailable; deterministic decision retained.",
            "risk_flags": ["AI_BUDGET_EXHAUSTED"],
            "latency_ms": 0,
        }

    # Build the capsule in the trusted zone. A dict never crosses the boundary
    # raw; a supplied capsule must still be a fresh typed ReasoningCapsule.
    if isinstance(payload, ReasoningCapsule):
        capsule = payload
    else:
        capsule = build_capsule_for_payload(
            payload, capability=capability, purpose=purpose
        )

    start = time.monotonic()
    result = await opencode_reason(
        capsule,
        deterministic_decision=deterministic_decision,
        max_calls=1,
    )
    latency = (time.monotonic() - start) * 1000
    GLOBAL_AI_BUDGET.record(success=result.source == "opencode", latency_ms=latency)

    audit_event(
        "ai_request",
        actor=capability,
        detail={
            "source": result.source,
            "decision": result.decision,
            "capsule_id": capsule.capsule_id,
            "latency_ms": latency,
        },
    )

    # Durable audit trail (Phase D): fingerprint only, never prompt/payload.
    # The capsule deliberately carries no business_id (see capsule.py); the
    # tenant column is resolved from the request's RLS tenant context.
    await record_ai_reasoning_request(
        capsule_id=capsule.capsule_id,
        request_id=capsule.request_id,
        nonce=capsule.nonce,
        capsule_hash=capsule.capsule_hash,
        capability=capability,
        purpose=purpose,
        business_id=None,
        issued_at=capsule.issued_at,
        expires_at=capsule.expires_at,
        status="completed",
        decision=result.decision,
    )
    await record_security_event(
        event_type="ai.reason.completed",
        actor=capability,
        capsule_id=capsule.capsule_id,
        request_id=capsule.request_id,
        detail={
            "source": result.source,
            "decision": result.decision,
        },
    )

    data = result.to_dict()
    data["latency_ms"] = latency
    return data


def budget_snapshot() -> dict[str, Any]:
    return GLOBAL_AI_BUDGET.snapshot()