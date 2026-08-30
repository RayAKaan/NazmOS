"""V11 Metrics Aggregation — Aggregate all results into metrics.json.

Collects results from:
- Checkpoint evaluations
- Override classifications
- Financial metrics
- AI economics
- Challenge quality
- Latency measurements
- Security tests
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results" / "v11"
RESULTS.mkdir(parents=True, exist_ok=True)


def aggregate_checkpoint_metrics() -> dict[str, Any]:
    """Aggregate metrics from all checkpoints."""
    all_checkpoints = []
    for cp_file in sorted(RESULTS.glob("checkpoint_d*.json")):
        cp = json.loads(cp_file.read_text())
        all_checkpoints.append(cp)

    if not all_checkpoints:
        return {"error": "No checkpoint files found"}

    # Aggregate across checkpoints
    total_correct_a = sum(cp.get("eval_mode_a", {}).get("counts", {}).get("correct", 0) for cp in all_checkpoints)
    total_correct_b = sum(cp.get("eval_mode_b", {}).get("counts", {}).get("correct", 0) for cp in all_checkpoints)
    total_acceptable_a = sum(cp.get("eval_mode_a", {}).get("counts", {}).get("acceptable_manual", 0) for cp in all_checkpoints)
    total_acceptable_b = sum(cp.get("eval_mode_b", {}).get("counts", {}).get("acceptable_manual", 0) for cp in all_checkpoints)
    total_bad_a = sum(cp.get("eval_mode_a", {}).get("counts", {}).get("bad_action", 0) for cp in all_checkpoints)
    total_bad_b = sum(cp.get("eval_mode_b", {}).get("counts", {}).get("bad_action", 0) for cp in all_checkpoints)
    total_skus_a = sum(cp.get("eval_mode_a", {}).get("decisions_evaluated", 0) for cp in all_checkpoints)
    total_skus_b = sum(cp.get("eval_mode_b", {}).get("decisions_evaluated", 0) for cp in all_checkpoints)

    # Override metrics
    total_good = sum(1 for cp in all_checkpoints for o in cp.get("overrides_b_vs_a", [])
                     if o.get("classification") == "GOOD_OVERRIDE")
    total_bad = sum(1 for cp in all_checkpoints for o in cp.get("overrides_b_vs_a", [])
                    if o.get("classification") == "BAD_OVERRIDE")
    total_neutral = sum(1 for cp in all_checkpoints for o in cp.get("overrides_b_vs_a", [])
                        if o.get("classification") == "NEUTRAL_OVERRIDE")

    # Challenge metrics
    total_challenges = sum(cp.get("v11_metrics", {}).get("ai_total_calls", 0) for cp in all_checkpoints)

    return {
        "checkpoints": len(all_checkpoints),
        "mode_a": {
            "total_correct": total_correct_a,
            "total_acceptable_manual": total_acceptable_a,
            "total_bad_action": total_bad_a,
            "total_skus": total_skus_a,
            "strict_accuracy": round(total_correct_a / max(1, total_skus_a), 4),
            "effective_accuracy": round((total_correct_a + total_acceptable_a) / max(1, total_skus_a), 4),
            "bad_action_rate": round(total_bad_a / max(1, total_skus_a), 4),
        },
        "mode_b": {
            "total_correct": total_correct_b,
            "total_acceptable_manual": total_acceptable_b,
            "total_bad_action": total_bad_b,
            "total_skus": total_skus_b,
            "strict_accuracy": round(total_correct_b / max(1, total_skus_b), 4),
            "effective_accuracy": round((total_correct_b + total_acceptable_b) / max(1, total_skus_b), 4),
            "bad_action_rate": round(total_bad_b / max(1, total_skus_b), 4),
        },
        "overrides": {
            "good": total_good,
            "bad": total_bad,
            "neutral": total_neutral,
            "net_value": total_good - total_bad,
            "good_rate": round(total_good / max(total_good + total_bad + total_neutral, 1), 4),
        },
        "challenges": {
            "total": total_challenges,
        },
    }


def aggregate_financial_metrics() -> dict[str, Any]:
    """Aggregate MODELLED financial metrics from all checkpoints.

    NOTE: These are MODELLED values, not actual recovery.
    """
    all_checkpoints = []
    for cp_file in sorted(RESULTS.glob("checkpoint_d*.json")):
        cp = json.loads(cp_file.read_text())
        all_checkpoints.append(cp)

    if not all_checkpoints:
        return {"error": "No checkpoint files found"}

    total_det_sar = sum(
        cp.get("v11_metrics", {}).get("financial", {}).get("deterministic_modelled_recovery_sar", 0)
        for cp in all_checkpoints
    )
    total_ai_sar = sum(
        cp.get("v11_metrics", {}).get("financial", {}).get("ai_modelled_recovery_sar", 0)
        for cp in all_checkpoints
    )
    total_incremental = sum(
        cp.get("v11_metrics", {}).get("financial", {}).get("incremental_modelled_recovery_sar", 0)
        for cp in all_checkpoints
    )
    total_inventory = sum(
        cp.get("v11_metrics", {}).get("financial", {}).get("total_inventory_value_sar", 0)
        for cp in all_checkpoints
    )

    return {
        "total_inventory_value_sar": round(total_inventory, 2),
        "deterministic_modelled_recovery_sar": round(total_det_sar, 2),
        "ai_modelled_recovery_sar": round(total_ai_sar, 2),
        "incremental_modelled_recovery_sar": round(total_incremental, 2),
        "incremental_pct": round(total_incremental / max(total_det_sar, 0.01) * 100, 2),
        "note": "MODELLED values — not actual recovery.",
    }


def aggregate_challenge_quality() -> dict[str, Any]:
    """Aggregate challenge quality metrics."""
    all_checkpoints = []
    for cp_file in sorted(RESULTS.glob("checkpoint_d*.json")):
        cp = json.loads(cp_file.read_text())
        all_checkpoints.append(cp)

    if not all_checkpoints:
        return {"error": "No checkpoint files found"}

    total_challenges = 0
    total_accepted = 0
    total_rejected = 0
    total_no_challenge = 0
    total_insufficient = 0
    total_failed = 0

    for cp in all_checkpoints:
        challenge_log = cp.get("challenge_log", [])
        for c in challenge_log:
            status = c.get("status", "")
            source = c.get("source", "")

            if status == "CHALLENGE":
                total_challenges += 1
                if source == "AI_CHALLENGE_ACCEPTED":
                    total_accepted += 1
                else:
                    total_rejected += 1
            elif status == "NO_CHALLENGE":
                total_no_challenge += 1
            elif status == "INSUFFICIENT_EVIDENCE":
                total_insufficient += 1
            elif status.startswith("AI_FAILED"):
                total_failed += 1

    # Get AI economics from checkpoints
    total_ai_calls = 0
    total_latency_ms = 0
    for cp in all_checkpoints:
        economics = cp.get("v11_metrics", {}).get("ai_calls", {})
        total_ai_calls += economics.get("actual_calls", 0)
        total_latency_ms += economics.get("total_latency_ms", 0)

    return {
        "total_challenges": total_challenges,
        "accepted": total_accepted,
        "rejected": total_rejected,
        "no_challenge": total_no_challenge,
        "insufficient_evidence": total_insufficient,
        "failed": total_failed,
        "challenge_accuracy": round(total_accepted / max(total_challenges, 1), 4),
        "ai_calls": total_ai_calls,
        "total_latency_ms": round(total_latency_ms, 1),
        "avg_latency_ms": round(total_latency_ms / max(total_ai_calls, 1), 1),
    }


def load_latency_metrics() -> dict[str, Any]:
    """Load latency measurement results."""
    latency_file = RESULTS / "latency_results.json"
    if latency_file.exists():
        return json.loads(latency_file.read_text())
    return {"error": "Latency results not found"}


def aggregate_all_metrics() -> dict[str, Any]:
    """Aggregate all V11 metrics."""
    metrics = {
        "version": "V11",
        "description": "V11 Contextual AI Challenge & Incremental Value Reality Test",
        "checkpoint_metrics": aggregate_checkpoint_metrics(),
        "financial_metrics": aggregate_financial_metrics(),
        "challenge_quality": aggregate_challenge_quality(),
        "latency": load_latency_metrics(),
    }

    # Save aggregated metrics
    output_file = RESULTS / "metrics.json"
    output_file.write_text(json.dumps(metrics, indent=1))
    print(f"Metrics aggregated to: {output_file}")

    return metrics


if __name__ == "__main__":
    metrics = aggregate_all_metrics()
    print(json.dumps(metrics, indent=1))
