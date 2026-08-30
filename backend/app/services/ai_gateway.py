"""Phase 5 AI Gateway: one safe interface for pilot AI reasoning."""
from __future__ import annotations
import os, time
from typing import Any
from app.services.ai_budget import GLOBAL_AI_BUDGET
from app.services.opencode_brain import reason as opencode_reason

async def reason(evidence: dict[str, Any], *, deterministic_decision: str | None = None) -> dict[str, Any]:
    if not GLOBAL_AI_BUDGET.can_call():
        return {"source":"fallback", "decision": deterministic_decision or "DO_NOTHING",
                "confidence":0.0, "reasoning":"AI budget unavailable; deterministic decision retained.",
                "risk_flags":["AI_BUDGET_EXHAUSTED"], "latency_ms":0}
    start=time.monotonic()
    result = await opencode_reason(evidence, deterministic_decision=deterministic_decision,
                                    max_calls=1)
    latency=(time.monotonic()-start)*1000
    GLOBAL_AI_BUDGET.record(success=result.source == "opencode", latency_ms=latency)
    data=result.to_dict(); data["latency_ms"]=latency
    return data

def budget_snapshot() -> dict[str, Any]: return GLOBAL_AI_BUDGET.snapshot()
