"""Shadow parity capture + benchmark harness for the Jev adapter.

MASTER_PLAN §5/§8 + TEST_AND_ACCEPTANCE_GATES §6 (determinism / shadow parity /
availability gates):

  * Determinism gate: with Jev disabled/unavailable, output is byte-identical to
    the deterministic decision.
  * Shadow parity audit: on N observed cases, where Jev and deterministic
    disagree, deterministic wins and the divergence is logged.
  * Availability gate: Jev outage/budget-exhaust returns deterministic result
    with the correct ``source`` label.

This module provides ``ShadowParityRecorder`` (writes JSONL to
``AI_CALL_LEDGER_PATH`` when configured, following the llm_orchestrator ledger
pattern) and ``run_shadow_parity`` (a deterministic benchmark that consults Jev
in shadow mode and records divergence without ever letting Jev change the
outcome).

Invariants enforced here:
  * Jev is consulted ONLY in shadow mode; the deterministic answer is always the
    recorded ``decision``.
  * Divergence (Jev suggestion != deterministic) is logged, never applied.
  * Ledger writes are best-effort and never block the decision.
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from app.config import get_settings

logger = logging.getLogger("shadow_parity")

DEFAULT_SHADOW_LEDGER = "results/jev_shadow_parity.jsonl"


def _ledger_path() -> str:
    settings = get_settings()
    return getattr(settings, "AI_CALL_LEDGER_PATH", "") or DEFAULT_SHADOW_LEDGER


class ShadowParityRecorder:
    """Best-effort JSONL capture of deterministic ⊥ Jev shadow comparisons."""

    def __init__(self, path: str | None = None) -> None:
        self.path = path or _ledger_path()

    def record(self, fields: dict[str, Any]) -> None:
        if not self.path:
            return
        try:
            p = Path(self.path)
            p.parent.mkdir(parents=True, exist_ok=True)
            rec = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), **fields}
            with p.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec, default=str) + "\n")
        except Exception:  # best-effort never blocks a decision
            logger.warning("shadow_ledger_write_failed", exc_info=True)


async def run_shadow_parity(
    *,
    cases: list[tuple[dict[str, Any], str]],  # (payload, deterministic_decision)
    question: str = "Which canonical decision is safest and why?",
    capability: str = "opencode_brain",
    purpose: str = "_internal",
    recorder: ShadowParityRecorder | None = None,
    consult: Any | None = None,  # async callable matching jev.consult
) -> dict[str, Any]:
    """Run N deterministic cases through the Jev channel, capture parity.

    Each case consults Jev (shadow), the deterministic decision remains the
    authoritative outcome, and every divergence is logged. Returns a summary:
    total / agree / diverge / jev_down / deterministic_total.
    """
    from app.security.privacy_firewall import build_capsule_for_payload
    from app.services.ai_providers.jev import consult as default_consult

    query = consult or default_consult
    recorder = recorder or ShadowParityRecorder()

    agree = 0
    diverge = 0
    jev_down = 0
    total = 0
    divergences: list[dict[str, Any]] = []

    for payload, deterministic in cases:
        total += 1
        try:
            capsule = build_capsule_for_payload(payload, capability=capability, purpose=purpose)
            reply = await query(
                question=question,
                capsule=capsule,
                deterministic_decision=deterministic,
            )
        except Exception as exc:  # never let a Jev fault break the benchmark
            jev_down += 1
            recorder.record(
                {
                    "capability": capability,
                    "deterministic": deterministic,
                    "jev_source": "error",
                    "jev_error": str(exc),
                    "agree": False,
                    "decision": deterministic,
                }
            )
            continue

        suggested = reply.suggested_decision if reply.source == "jev" else None
        outcome = deterministic  # deterministic always wins
        matched = suggested == outcome or suggested is None
        if matched:
            agree += 1
        else:
            diverge += 1
            divergences.append(
                {
                    "deterministic": deterministic,
                    "jev": suggested,
                    "jev_source": reply.source,
                    "jev_confidence": reply.confidence,
                    "jev_reasoning": reply.reasoning[:200],
                }
            )

        recorder.record(
            {
                "capability": capability,
                "deterministic": deterministic,
                "jev_source": reply.source,
                "jev_suggested": suggested,
                "agree": matched,
                "decision": outcome,
            }
        )

    return {
        "total": total,
        "agree": agree,
        "diverge": diverge,
        "jev_down": jev_down,
        "deterministic_total": total,  # deterministic is ALWAYS the outcome
        "divergences": divergences,
    }