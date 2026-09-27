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

# The deterministic-decision vocabulary the canonical route preserves by
# default. Surfaces that migrate onto the route pass their own contract via
# ``allowed_decisions`` so owner-specific keys (e.g. rank buckets, root-cause
# taxonomy) are never clobbered to DO_NOTHING.
DEFAULT_ALLOWED_DECISIONS = frozenset({
    "DO_NOTHING", "REORDER", "TRANSFER", "DISCOUNT",
    "PRICE_CHANGE", "RECOVERY_MATCH", "MANUAL_REVIEW",
})

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


async def systemone_reason(
    payload: Mapping[str, Any],
    *,
    capability: str = DEFAULT_CAPABILITY,
    purpose: str = DEFAULT_PURPOSE,
    deterministic_decision: str | None = None,
    question: str = "Which canonical decision is safest and why?",
    client: Any | None = None,
    shadow: bool = True,
    allowed_suggestions: frozenset[str] | None = None,
    allowed_decisions: frozenset[str] | None = None,
) -> dict[str, Any]:
    """Canonical gateway route: Jev-first, STRICTLY NON-AUTHORITATIVE.

    Route contract:
      1. AI policy kill-switch + budget are enforced exactly as the OpenCode
         brain route (same choke point, same fail-closed semantics).
      2. A signed ReasoningCapsule is built from the raw payload; Jev only
         ever sees ``capsule.for_prompt()`` (opaque refs + banded signals).
      3. ``deterministic_decision`` is ALWAYS authoritative. Jev's reply can
         enrich ``confidence``/``reasoning`` or set ``challenge``/a suggested
         alternative, but it can never override the deterministic result.
      4. On ANY failure (policy, budget, transport, parse, out-of-contract)
         the reply is ``source=="fallback"`` with the deterministic decision
         preserved untouched.
      5. Shadow mode (default): the Jev reply is captured to the AI call
         ledger and audit trail but the decision outcome is the deterministic
         decision regardless -- this is how Jev is validated before it ever
         influences exposition text.
    """
    allowed, reason_blocked = _policy.allow_request(capability, purpose)
    if not allowed:
        audit_event("ai_denied", actor=f"{capability}:jev", detail={"reason": reason_blocked})
        await record_security_event(
            event_type="ai.policy.denied",
            actor=f"{capability}:jev",
            detail={"reason": reason_blocked},
        )
        return {
            "source": "fallback",
            "decision": deterministic_decision or "DO_NOTHING",
            "confidence": 0.0,
            "reasoning": f"AI policy blocked request: {reason_blocked}",
            "risk_flags": ["AI_POLICY_BLOCKED"],
            "latency_ms": 0,
            "jev_consulted": False,
        }

    if not GLOBAL_AI_BUDGET.can_call():
        audit_event("ai_budget_exhausted", actor=f"{capability}:jev")
        await record_security_event(
            event_type="ai.budget.exhausted",
            actor=f"{capability}:jev",
        )
        return {
            "source": "fallback",
            "decision": deterministic_decision or "DO_NOTHING",
            "confidence": 0.0,
            "reasoning": "AI budget unavailable; deterministic decision retained.",
            "risk_flags": ["AI_BUDGET_EXHAUSTED"],
            "latency_ms": 0,
            "jev_consulted": False,
        }

    capsule = build_capsule_for_payload(payload, capability=capability, purpose=purpose)

    start = time.monotonic()
    from app.services.ai_providers.jev import JevClient, consult as jev_consult

    reply = await jev_consult(
        question=question,
        capsule=capsule,
        deterministic_decision=deterministic_decision or "DO_NOTHING",
        client=client or JevClient(),
        allowed_suggestions=allowed_suggestions,
    )
    latency = (time.monotonic() - start) * 1000
    GLOBAL_AI_BUDGET.record(success=reply.source == "jev", latency_ms=latency)

    # Jev is non-authoritative: the deterministic decision is the decision.
    # A surface may declare its own deterministic vocabulary so contract keys
    # (rank buckets, root-cause taxonomy) are preserved, not coerced.
    decision = deterministic_decision or reply.decision_basis or "DO_NOTHING"
    if decision.upper() not in (allowed_decisions or DEFAULT_ALLOWED_DECISIONS):
        decision = "DO_NOTHING"

    # The raw Jev suggestion is always surfaced for validation/audit; only its
    # use as exposition prose is shadow-gated below.
    surface_jev_suggestion = reply.source == "jev" and reply.suggested_decision is not None and not shadow
    confidence = reply.confidence if reply.source == "jev" else 0.0
    reasoning = reply.reasoning
    challenge = bool(reply.challenge)
    risk_flags: list[str] = []
    if reply.source == "jev":
        if reply.suggested_decision and reply.suggested_decision != decision:
            risk_flags.append("JEV_DISSENT")
        if not reply.reasoning:
            risk_flags.append("JEV_NO_REASONING")

    audit_event(
        "ai_request",
        actor=f"{capability}:jev",
        detail={
            "source": reply.source,
            "decision": decision,
            "jev_suggested": reply.suggested_decision,
            "capsule_id": capsule.capsule_id,
            "latency_ms": latency,
            "shadow": shadow,
        },
    )

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
        decision=decision,
    )
    await record_security_event(
        event_type="ai.reason.completed",
        actor=f"{capability}:jev",
        capsule_id=capsule.capsule_id,
        request_id=capsule.request_id,
        detail={
            "source": reply.source,
            "decision": decision,
            "jev_suggested": reply.suggested_decision,
        },
    )

    return {
        "source": reply.source,
        "decision": decision,
        "confidence": confidence,
        "reasoning": reasoning,
        "evidence_ids": [i.ref for i in capsule.items if i.ref],
        "risk_flags": risk_flags,
        "alternative_decision": reply.suggested_decision if reply.source == "jev" else None,
        "challenge": challenge,
        "latency_ms": latency,
        "jev_consulted": reply.source == "jev",
        "use_jev_exposition": surface_jev_suggestion,
    }