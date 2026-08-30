"""V10 evaluator — scores decisions against ground truth.

Single business: Al Noor Supermarket & Convenience.
Imports scripts/v10/ground_truth.json ONLY here. Decision engines never read it.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

GT_PATH = Path(__file__).resolve().parent / "ground_truth.json"
_OM_PATH = Path(__file__).resolve().parent / "outcome_model.json"

with GT_PATH.open() as f:
    GT = json.load(f)
with _OM_PATH.open() as f:
    OM = json.load(f)

MANUAL_EQUIV = {"MANUAL_REVIEW", "INSUFFICIENT_EVIDENCE"}


def normalize(decision: str | None) -> str:
    return (decision or "").upper().strip()


def classify_decision(biz_key: str, sku: str, decision: str) -> str:
    """Return one of: correct | bad_action | unnecessary_action | acceptable_manual | unknown_sku."""
    biz = GT["businesses"].get(biz_key, {})
    spec = biz.get("skus", {}).get(sku)
    if not spec:
        return "unknown_sku"
    d = normalize(decision)
    if d in ("", "NONE"):
        return "unnecessary_inaction"
    if d in spec["bad"]:
        return "bad_action"
    if d in spec["correct"]:
        if d in MANUAL_EQUIV and any(x in MANUAL_EQUIV for x in spec["correct"]):
            return "correct"
        return "correct"
    if d in MANUAL_EQUIV:
        return "acceptable_manual"
    if "DO_NOTHING" in spec["correct"] or "HOLD" in spec["correct"]:
        return "unnecessary_action"
    return "neutral"


def score_mode_results(biz_key: str, mode_results: list[dict]) -> dict[str, Any]:
    """mode_results: [{sku, final_decision}, ...] from one mode."""
    per_sku = {}
    counts = {"correct": 0, "bad_action": 0, "unnecessary_action": 0,
              "acceptable_manual": 0, "neutral": 0, "unknown_sku": 0,
              "unnecessary_inaction": 0}
    for r in mode_results:
        sku = r.get("sku") or ""
        verdict = classify_decision(biz_key, sku, r.get("final_decision"))
        counts[verdict] = counts.get(verdict, 0) + 1
        per_sku[sku] = {"decision": r.get("final_decision"), "verdict": verdict}
    decided = sum(v for k, v in counts.items() if k != "unknown_sku")
    correct = counts["correct"]
    acceptable = counts["acceptable_manual"]
    return {
        "per_sku": per_sku,
        "counts": counts,
        "decisions_evaluated": decided,
        "correct_decision_rate": round(correct / decided, 4) if decided else None,
        "effective_accuracy": round((correct + acceptable) / decided, 4) if decided else None,
        "bad_action_rate": round(counts["bad_action"] / decided, 4) if decided else None,
        "unnecessary_action_rate": round(counts["unnecessary_action"] / decided, 4) if decided else None,
    }


def classify_override(biz_key: str, sku: str, det: str, ai_final: str) -> str:
    """GOOD/BAD/NEUTRAL/UNRESOLVED override classification."""
    if normalize(det) == normalize(ai_final):
        return "NEUTRAL_OVERRIDE"
    v_det = classify_decision(biz_key, sku, det)
    v_ai = classify_decision(biz_key, sku, ai_final)
    if v_det == "bad_action" and v_ai in ("correct", "acceptable_manual"):
        return "GOOD_OVERRIDE"
    if v_ai == "bad_action" and v_det in ("correct", "acceptable_manual"):
        return "BAD_OVERRIDE"
    if v_det in ("unknown_sku", "unnecessary_inaction") or v_ai in ("unknown_sku", "unnecessary_inaction"):
        return "UNRESOLVED"
    return "NEUTRAL_OVERRIDE"


def recovery_factor_for(verdict: str) -> float:
    m = OM["recovery_factors"]
    if verdict in ("correct",):
        return m["on_correct_class_execution"]
    if verdict == "acceptable_manual":
        return m["on_acceptable_manual"]
    if verdict == "bad_action":
        return m["on_bad_class_execution"]
    return 0.5


def consumption_rate(biz_key: str, sku: str) -> float:
    return float(OM["daily_consumption_units_per_day"].get(biz_key, {}).get(sku, 0))


def evaluate_all_checkpoints():
    RESULTS = Path(__file__).resolve().parents[2] / "results" / "v10"
    all_results = []
    for cp_file in sorted(RESULTS.glob("checkpoint_d*.json")):
        cp = json.loads(cp_file.read_text())
        all_results.append(cp)

    if not all_results:
        print("No checkpoint files found.")
        return

    total_correct_a = sum(cp.get("eval_mode_a", {}).get("counts", {}).get("correct", 0) for cp in all_results)
    total_correct_b = sum(cp.get("eval_mode_b", {}).get("counts", {}).get("correct", 0) for cp in all_results)
    total_acceptable_a = sum(cp.get("eval_mode_a", {}).get("counts", {}).get("acceptable_manual", 0) for cp in all_results)
    total_acceptable_b = sum(cp.get("eval_mode_b", {}).get("counts", {}).get("acceptable_manual", 0) for cp in all_results)
    total_skus_a = sum(cp.get("eval_mode_a", {}).get("decisions_evaluated", 0) for cp in all_results)
    total_skus_b = sum(cp.get("eval_mode_b", {}).get("decisions_evaluated", 0) for cp in all_results)
    total_good = sum(1 for cp in all_results for o in cp.get("overrides_b_vs_a", [])
                     if o.get("classification") == "GOOD_OVERRIDE")
    total_bad = sum(1 for cp in all_results for o in cp.get("overrides_b_vs_a", [])
                    if o.get("classification") == "BAD_OVERRIDE")
    total_neutral = sum(1 for cp in all_results for o in cp.get("overrides_b_vs_a", [])
                        if o.get("classification") == "NEUTRAL_OVERRIDE")
    total_unresolved = sum(1 for cp in all_results for o in cp.get("overrides_b_vs_a", [])
                           if o.get("classification") == "UNRESOLVED")

    summary = {
        "checkpoints": len(all_results),
        "mode_a": {
            "total_correct": total_correct_a,
            "total_acceptable_manual": total_acceptable_a,
            "total_skus": total_skus_a,
            "accuracy": round(total_correct_a / max(1, total_skus_a), 4),
            "effective_accuracy": round((total_correct_a + total_acceptable_a) / max(1, total_skus_a), 4),
        },
        "mode_b": {
            "total_correct": total_correct_b,
            "total_acceptable_manual": total_acceptable_b,
            "total_skus": total_skus_b,
            "accuracy": round(total_correct_b / max(1, total_skus_b), 4),
            "effective_accuracy": round((total_correct_b + total_acceptable_b) / max(1, total_skus_b), 4),
        },
        "overrides": {
            "good": total_good,
            "bad": total_bad,
            "neutral": total_neutral,
            "unresolved": total_unresolved,
            "net_value": total_good - total_bad,
        },
    }

    (RESULTS / "evaluation_summary.json").write_text(json.dumps(summary, indent=1))
    print(json.dumps(summary, indent=1))
    return summary


if __name__ == "__main__":
    evaluate_all_checkpoints()
