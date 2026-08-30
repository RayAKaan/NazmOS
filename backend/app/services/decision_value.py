"""Phase 4: measure whether OpenCode changes decision quality.

This module contains no ground-truth loading and no database access.  It is safe
for use by both the runtime experiment and an offline evaluator.  Ground truth
is supplied only to the evaluator/comparison boundary.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable

CATEGORIES = ("GOOD_OVERRIDE", "BAD_OVERRIDE", "NEUTRAL_OVERRIDE", "UNRESOLVED")


def _norm(value: str | None) -> str:
    return str(value or "").strip().upper()


def classify_decision_value(baseline: str, final: str, truth: str | None) -> str:
    """Classify the value of a changed decision.

    Agreement is deliberately neutral: AI agreeing with the deterministic
    engine is not evidence that AI improved the decision.
    """
    b, f, t = _norm(baseline), _norm(final), _norm(truth)
    if b == f:
        return "NEUTRAL_OVERRIDE"
    if not t:
        return "UNRESOLVED"
    if f == t and b != t:
        return "GOOD_OVERRIDE"
    if b == t and f != t:
        return "BAD_OVERRIDE"
    return "NEUTRAL_OVERRIDE"


@dataclass(frozen=True)
class DecisionComparison:
    case_id: str
    baseline: str
    final: str
    truth: str | None = None
    source: str = "deterministic"
    category: str = "UNRESOLVED"
    ai_called: bool = False
    ai_failed: bool = False
    latency_ms: float | None = None
    cost_usd: float | None = None
    financial_hallucination: bool = False
    constraint_violation: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def summarize_decisions(records: Iterable[DecisionComparison]) -> dict[str, Any]:
    records = list(records)
    counts = {key: 0 for key in CATEGORIES}
    for record in records:
        counts[record.category] = counts.get(record.category, 0) + 1

    resolved = sum(counts[k] for k in ("GOOD_OVERRIDE", "BAD_OVERRIDE", "NEUTRAL_OVERRIDE"))
    ai_calls = sum(r.ai_called for r in records)
    ai_failures = sum(r.ai_failed for r in records)
    hallucinations = sum(r.financial_hallucination for r in records)
    constraint_violations = sum(r.constraint_violation for r in records)
    latencies = sorted(r.latency_ms for r in records if r.latency_ms is not None)
    costs = [r.cost_usd for r in records if r.cost_usd is not None]

    return {
        "total": len(records),
        **counts,
        "resolved": resolved,
        "good_rate": counts["GOOD_OVERRIDE"] / resolved if resolved else 0.0,
        "bad_rate": counts["BAD_OVERRIDE"] / resolved if resolved else 0.0,
        "net_good_over_bad": counts["GOOD_OVERRIDE"] - counts["BAD_OVERRIDE"],
        "override_rate": (counts["GOOD_OVERRIDE"] + counts["BAD_OVERRIDE"] + counts["NEUTRAL_OVERRIDE"]) / len(records) if records else 0.0,
        "ai_calls": ai_calls,
        "ai_failures": ai_failures,
        "ai_failure_rate": ai_failures / ai_calls if ai_calls else 0.0,
        "financial_hallucinations": hallucinations,
        "constraint_violations": constraint_violations,
        "latency_ms_avg": sum(latencies) / len(latencies) if latencies else None,
        "latency_ms_p95": latencies[min(len(latencies) - 1, max(0, int(len(latencies) * 0.95) - 1))] if latencies else None,
        "cost_usd_total": sum(costs) if costs else None,
    }


def compare_mode_accuracy(records: Iterable[DecisionComparison]) -> dict[str, float | int]:
    """Return strict/effective baseline and final accuracy.

    ``truth`` can be a single expected decision or a pipe/comma-separated set
    of acceptable labels for evaluator fixtures.
    """
    records = list(records)
    strict_baseline = strict_final = effective_baseline = effective_final = 0
    total = len(records)
    for r in records:
        accepted = {_norm(x) for x in str(r.truth or "").replace("|", ",").split(",") if x.strip()}
        if not accepted:
            continue
        b, f = _norm(r.baseline), _norm(r.final)
        strict_baseline += b == next(iter(accepted)) if len(accepted) == 1 else 0
        strict_final += f == next(iter(accepted)) if len(accepted) == 1 else 0
        effective_baseline += b in accepted
        effective_final += f in accepted
    return {
        "total": total,
        "strict_baseline_accuracy": strict_baseline / total if total else 0.0,
        "strict_final_accuracy": strict_final / total if total else 0.0,
        "effective_baseline_accuracy": effective_baseline / total if total else 0.0,
        "effective_final_accuracy": effective_final / total if total else 0.0,
    }
