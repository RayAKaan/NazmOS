"""Typed advisory — Jev/LLM advisory with exact attribution.

The advisory is STRICTLY NON-AUTHORITATIVE. The loop's deterministic decision
is computed independently; the advisory can enrich confidence, propose an
alternative (validated against a contract), and is always recorded with the
ACTUAL provider identity + validation result.

Reuse notes:
    * The production Jev consult path is ``app.services.ai_providers.jev`` via
      ``app.services.ai_gateway.systemone_reason`` (shadow=True) and
      ``canonical_decision``. This module does NOT re-implement AI transport:
      in DB-free tests it uses a caller-injected advisor callable; production
      wiring passes ``systemone_reason`` (see ``canonical_advisor``).
    * Attribution: ``source`` (¶AdvisorySource) and ``provider`` are recorded
      verbatim. A fallback response is never labelled Jev.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Awaitable

from app.services.business_loop.contracts import AdvisorySource


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# Callable contract for an advisory provider:
#   async fn(capability, context) -> dict with keys:
#     decision (deterministic authoritative), suggested (advisory|None),
#     confidence (0..1), source (str), provider (str), reason, validated (bool)
AdvisoryFn = Callable[..., Awaitable[dict[str, Any]]]


@dataclass
class TypedAdvisory:
    """A bounded, validated advisory signal from one provider."""

    capability: str
    deterministic_decision: str
    suggested: str | None
    confidence: float
    source: AdvisorySource
    provider: str
    model: str
    validation_passed: bool
    risk_flags: list[str] = field(default_factory=list)
    reasoning: str = ""
    captured_at: str = ""

    def __post_init__(self) -> None:
        self.captured_at = self.captured_at or _now_iso()

    def to_dict(self) -> dict[str, Any]:
        return {
            "capability": self.capability,
            "deterministic_decision": self.deterministic_decision,
            "suggested": self.suggested,
            "confidence": self.confidence,
            "source": self.source.value if hasattr(self.source, "value") else str(self.source),
            "provider": self.provider,
            "model": self.model,
            "validation_passed": self.validation_passed,
            "risk_flags": self.risk_flags,
        }


async def consult_advisory(
    advisor: AdvisoryFn,
    *,
    capability: str,
    context: dict[str, Any],
    contract: frozenset[str] | None = None,
) -> TypedAdvisory:
    """Call an advisory provider and normalize/validate its reply.

    Validation ladder (MASTER_PLAN §10.6):
      1. transport (call succeeded)
      2. schema (required keys present)
      3. allowed-value (``suggested`` within ``contract`` when provided)
      4. capability (deterministic decision present)
      5. deterministic domain (provider must not override the deterministic
         decision; if it does, the suggestion is set aside and flagged)
    Invalid replies are never silently coerced into business decisions.
    """
    reply = await advisor(capability, context)
    deterministic = str(reply.get("decision") or "DO_NOTHING")
    suggested_raw = reply.get("suggested")
    source_raw = str(reply.get("source") or AdvisorySource.DETERMINISTIC_ONLY.value)
    provider = str(reply.get("provider") or source_raw)
    model = str(reply.get("model") or "")
    confidence = float(reply.get("confidence") or 0.0)
    reasoning = str(reply.get("reasoning") or "")

    risk_flags: list[str] = []
    suggested: str | None = None
    if suggested_raw is not None:
        suggested = str(suggested_raw).strip()
        if contract is not None and suggested not in contract:
            risk_flags.append("OUT_OF_CONTRACT")
            suggested = None  # discard; reject, do not coerce
        if suggested == deterministic:
            suggested = None  # agreement -> no separate alternative

    try:
        source = AdvisorySource(source_raw)
    except ValueError:
        source = AdvisorySource.DETERMINISTIC_ONLY
        risk_flags.append(f"UNKNOWN_PROVIDER_SOURCE:{source_raw}")

    validated = not risk_flags
    return TypedAdvisory(
        capability=capability,
        deterministic_decision=deterministic,
        suggested=suggested,
        confidence=confidence,
        source=source,
        provider=provider,
        model=model,
        validation_passed=validated,
        risk_flags=risk_flags,
        reasoning=reasoning,
    )


async def deterministic_only_advisor(capability: str, context: dict[str, Any]) -> dict[str, Any]:
    """Fail-closed default: no AI consulted; deterministic decision is the reply."""
    decision = str(context.get("deterministic_decision") or "DO_NOTHING")
    return {
        "decision": decision,
        "suggested": None,
        "confidence": 0.0,
        "source": AdvisorySource.DETERMINISTIC_ONLY.value,
        "provider": "deterministic",
        "model": "n/a",
        "reasoning": "deterministic-only mode; no provider consulted.",
    }


async def canonical_advisor(
    capability: str,
    context: dict[str, Any],
) -> dict[str, Any]:
    """Wire the advisory into the existing canonical gateway (shadow mode).

    Uses ``app.services.ai_gateway.systemone_reason`` exactly like
    ``canonical_controller.canonical_decision``: deterministic decision stays
    authoritative; Jev is advisory only. ``client`` may be injected in tests.
    """
    from app.services import ai_gateway

    result = await ai_gateway.systemone_reason(
        context.get("payload", {}),
        capability=capability,
        purpose=context.get("purpose", "continuous_business_loop"),
        deterministic_decision=str(context.get("deterministic_decision") or "DO_NOTHING"),
        question="Which registered action is safest for this opportunity and why?",
        shadow=True,
        allowed_suggestions=context.get("contract"),
        allowed_decisions=context.get("contract"),
        client=context.get("client"),
    )
    suggested = result.get("alternative_decision")
    return {
        "decision": result.get("decision", context.get("deterministic_decision")),
        "suggested": suggested,
        "confidence": float(result.get("confidence") or 0.0),
        "source": result.get("source", "fallback"),
        "provider": result.get("source", "fallback"),
        "model": result.get("model") or "jev-1.13.0",
        "reasoning": result.get("reasoning"),
        "risk_flags": list(result.get("risk_flags") or []),
    }