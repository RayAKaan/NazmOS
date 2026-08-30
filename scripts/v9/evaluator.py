"""V9 evaluator — scores decisions against ground truth.

Imports scripts/v9/ground_truth.json ONLY here. Decision engines never read it.
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
    OUTCOME_MODEL = json.load(f)

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
        return "unnecessary_inaction"  # engine produced nothing at all
    if d in spec["bad"]:
        return "bad_action"
    if d in spec["correct"]:
        if d in MANUAL_EQUIV and any(x in MANUAL_EQUIV for x in spec["correct"]):
            return "correct"
        return "correct"
    if d in MANUAL_EQUIV:
        return "acceptable_manual"
    # a valid-but-not-listed action where doing nothing was expected
    if "DO_NOTHING" in spec["correct"] or "HOLD" in spec["correct"]:
        return "unnecessary_action"
    # partially acceptable: not listed as correct nor bad
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
    return {
        "per_sku": per_sku,
        "counts": counts,
        "decisions_evaluated": decided,
        "correct_decision_rate": round(correct / decided, 4) if decided else None,
        "bad_action_rate": round(counts["bad_action"] / decided, 4) if decided else None,
        "unnecessary_action_rate": round(counts["unnecessary_action"] / decided, 4) if decided else None,
    }


def classify_override(biz_key: str, sku: str, det: str, ai_final: str) -> str:
    """GOOD/BAD/NEUTRAL/UNRESOLVED override classification (§16)."""
    if normalize(det) == normalize(ai_final):
        return "NEUTRAL_OVERRIDE"  # no actual disagreement
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
    m = OUTCOME_MODEL["recovery_factors"]
    if verdict in ("correct",):
        return m["on_correct_class_execution"]
    if verdict == "acceptable_manual":
        return m["on_acceptable_manual"]
    if verdict == "bad_action":
        return m["on_bad_class_execution"]
    return 0.5


def consumption_rate(biz_key: str, sku: str) -> float:
    return float(OUTCOME_MODEL["daily_consumption_units_per_day"].get(biz_key, {}).get(sku, 0))
