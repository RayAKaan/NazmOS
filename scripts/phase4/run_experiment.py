#!/usr/bin/env python3
"""Phase 4 local decision-value experiment.

Input is an evidence JSON list.  Ground truth is loaded only after the AI/baseline
responses have been produced, so it cannot enter the OpenCode prompt.

This script intentionally never executes financial actions.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from app.services.decision_value import DecisionComparison, classify_decision_value, summarize_decisions  # noqa: E402
from app.services.opencode_brain import BrainStats, reason  # noqa: E402


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


async def run(args):
    evidence_rows = load_json(Path(args.evidence))
    if not isinstance(evidence_rows, list):
        raise SystemExit("Evidence file must contain a JSON list")

    # Ground truth is deliberately not loaded until all AI calls have completed.
    stats = BrainStats()
    comparisons: list[DecisionComparison] = []
    for row in evidence_rows:
        case_id = str(row.get("case_id") or row.get("id") or row.get("sku"))
        baseline = str(row.get("deterministic_decision") or "DO_NOTHING").upper()
        result = await reason(
            row,
            deterministic_decision=baseline,
            stats=stats,
            max_calls=args.max_calls,
            timeout_seconds=args.timeout,
            model=args.model,
        )
        comparisons.append(DecisionComparison(
            case_id=case_id,
            baseline=baseline,
            final=result.decision,
            source=result.source,
            ai_called=result.source == "opencode",
            ai_failed=result.source == "fallback",
            latency_ms=result.latency_ms,
            financial_hallucination=bool(result.validation and result.validation.financial_hallucination_detected),
        ))

    truth = load_json(Path(args.ground_truth))
    truth_map = truth if isinstance(truth, dict) else {str(x.get("case_id")): x for x in truth}
    enriched = []
    for row in comparisons:
        expected = truth_map.get(row.case_id, {})
        label = expected.get("truth") or expected.get("correct_decision")
        category = classify_decision_value(row.baseline, row.final, label)
        enriched.append(DecisionComparison(**{**row.to_dict(), "truth": label, "category": category}))

    result = {
        "experiment": "NAZMOS_PHASE_4_AI_DECISION_VALUE",
        "real_ai_required": True,
        "stats": stats.__dict__,
        "metrics": summarize_decisions(enriched),
        "records": [r.to_dict() for r in enriched],
    }
    print(json.dumps(result, indent=2, default=str))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", required=True)
    parser.add_argument("--ground-truth", required=True)
    parser.add_argument("--max-calls", type=int, default=int(os.getenv("NAZMOS_OPENCODE_MAX_CALLS_PER_AUDIT", "10")))
    parser.add_argument("--timeout", type=int, default=int(os.getenv("NAZMOS_OPENCODE_TIMEOUT_SECONDS", "30")))
    parser.add_argument("--model", default=os.getenv("NAZMOS_OPENCODE_MODEL", ""))
    args = parser.parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
