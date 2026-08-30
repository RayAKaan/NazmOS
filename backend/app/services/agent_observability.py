"""Agent Run observability + inference cost tracking (Phase 3, §24–25).

Records every agent execution (agent, business, trigger, tools, decisions, latency,
provider/model, token usage, estimated cost) so the platform can answer
"why did NazmOS do this?" — and so paid inference is visible. Only aggregates are
stored; never sensitive model context or PII.

Cost model: per-1M-token USD rates for the providers NazmOS actually uses. These are
conservative, documented estimates — NOT billed amounts (no billing integration).
"""
from __future__ import annotations
from app.utils.clock import utcnow

import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.llm_rate_limiter import estimate_tokens

# Conservative USD per 1M tokens (input, output). Estimates only.
PROVIDER_RATES: dict[str, tuple[float, float]] = {
    "groq": (0.59, 0.79),      # ~ llama-3.3-70b tier (input, output)
    "google": (0.10, 0.40),    # ~ gemini flash tier
    "mock": (0.0, 0.0),
    "deterministic": (0.0, 0.0),
}

DEFAULT_RATES = (1.0, 3.0)


def estimate_cost_usd(provider: str, prompt_tokens: int | None, completion_tokens: int | None) -> float:
    """Estimate inference cost. Deterministic/mock runs are free."""
    if provider in ("mock", "deterministic"):
        return 0.0
    inp, out = PROVIDER_RATES.get(provider, DEFAULT_RATES)
    p = prompt_tokens or 0
    c = completion_tokens or 0
    return round((p * inp + c * out) / 1_000_000, 6)


def _json(v: Any) -> str:
    return json.dumps(v, default=str)


async def record_agent_run(
    db: AsyncSession,
    *,
    business_id: UUID | str,
    agent_type: str,
    trigger: str = "manual",
    trigger_event_type: str | None = None,
    model_provider: str | None = "deterministic",
    model_name: str | None = None,
    proposals: int = 0,
    auto_executed: int = 0,
    queued_for_approval: int = 0,
    decisions: list[dict[str, Any]] | None = None,
    tools_requested: list[str] | None = None,
    verification: dict[str, Any] | None = None,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
    latency_ms: int | None = None,
    status: str = "completed",
    error: str | None = None,
    commit: bool = False,
) -> UUID:
    import uuid
    run_id = uuid.uuid4()
    cost = estimate_cost_usd(model_provider or "deterministic", prompt_tokens, completion_tokens)
    await db.execute(text("""
        INSERT INTO agent_runs
            (id, business_id, agent_type, trigger, trigger_event_type, model_provider,
             model_name, proposals, auto_executed, queued_for_approval, decisions,
             tools_requested, verification, prompt_tokens, completion_tokens,
             estimated_cost_usd, latency_ms, status, error, created_at)
        VALUES
            (:id, :b, :agent, :trigger, :event, :provider, :model, :proposals, :auto,
             :queued, CAST(:decisions AS JSON), CAST(:tools AS JSON),
             CAST(:verification AS JSON), :pt, :ct, :cost, :latency, :status, :error, :now)
    """), {
        "id": str(run_id),
        "b": str(business_id),
        "agent": agent_type,
        "trigger": trigger,
        "event": trigger_event_type,
        "provider": model_provider,
        "model": model_name,
        "proposals": proposals,
        "auto": auto_executed,
        "queued": queued_for_approval,
        "decisions": _json(decisions or []),
        "tools": _json(tools_requested or []),
        "verification": _json(verification or {}),
        "pt": prompt_tokens,
        "ct": completion_tokens,
        "cost": cost,
        "latency": latency_ms,
        "status": status,
        "error": error,
        "now": utcnow(),
    })
    if commit:
        await db.commit()
    return run_id


def estimate_prompt_tokens(agent_type: str, context: dict[str, Any] | None) -> int:
    """Estimate the prompt tokens an agent run would consume (for cost tracking before
    a run, or when a deterministic agent is used)."""
    payload = json.dumps({"agent": agent_type, "context": context or {}}, default=str)
    return estimate_tokens(payload)
