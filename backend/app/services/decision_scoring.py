"""Decision Quality + Explainable Recommendations (Phase 9, §8–14).

Deterministic, documented recommendation scoring. Ranking decides what is preferable;
the policy engine decides what is permissible (§13) — the two never merge.

Normalization (§10): every input is mapped to a 0–1 contribution so SAR impact is never
compared raw against percentages. The final score is a weighted sum with explicit,
documented weights; no single factor can overwhelm the rest.

Score =
    0.15 · goal_alignment
  + 0.20 · normalized_impact
  + 0.15 · urgency
  + 0.10 · confidence
  + 0.10 · data_quality
  + 0.20 · strategy (effectiveness + success rate, evidence-tier-weighted)
  − 0.10 · risk
"""
from __future__ import annotations

import math
from typing import Any

from app.config import get_settings
from app.services.strategy_performance import evidence_tier as _evidence_tier

# ── Normalization helpers ──────────────────────────────────────────────────

def normalize_impact_sar(value_sar: float | None, cap_sar: float = 100_000.0) -> float:
    """Log-scale normalization of SAR impact to 0–1 (cap at `cap_sar`)."""
    if value_sar is None or value_sar <= 0:
        return 0.0
    v = min(float(value_sar), cap_sar)
    return round(math.log1p(v) / math.log1p(cap_sar), 4)


def normalize_confidence(confidence: float | None) -> float:
    if confidence is None:
        return 0.5
    return max(0.0, min(1.0, float(confidence)))


def normalize_data_quality(score: float | None) -> float:
    """0–100 data quality → 0–1. Missing data quality defaults to a neutral 0.5."""
    if score is None:
        return 0.5
    return max(0.0, min(1.0, float(score) / 100.0))


_URGENCY_MAP = {"critical": 1.0, "high": 0.75, "medium": 0.5, "low": 0.25}
_RISK_MAP = {"high": 1.0, "medium": 0.5, "low": 0.0}
_GOAL_MAP = {"directly_aligned": 1.0, "indirectly_relevant": 0.5, "unrelated": 0.0}
_EVIDENCE_WEIGHT = {"insufficient": 0.0, "preliminary": 0.5, "strong": 1.0}


def normalize_urgency(urgency: str | None) -> float:
    return _URGENCY_MAP.get(urgency or "medium", 0.5)


def normalize_risk(risk: str | None) -> float:
    return _RISK_MAP.get(risk or "medium", 0.5)


def normalize_goal_alignment(alignment: str | None) -> float:
    return _GOAL_MAP.get(alignment or "unrelated", 0.0)


def normalize_strategy(strategy: dict[str, Any]) -> float:
    """Strategy term: evidence-tier-weighted blend of effectiveness + success rate (§7/§9).
    Insufficient evidence contributes 0 (never masquerades as knowledge, §18)."""
    tier_weight = _EVIDENCE_WEIGHT.get(strategy.get("evidence_tier", "insufficient"), 0.0)
    effectiveness = strategy.get("effectiveness")
    success_rate = strategy.get("success_rate")
    eff = effectiveness if effectiveness is not None else 0.0
    sr = success_rate if success_rate is not None else 0.0
    # clamp to [0,1]; effectiveness can exceed 1 when observed > expected
    eff = max(0.0, min(1.0, float(eff)))
    sr = max(0.0, min(1.0, float(sr)))
    return tier_weight * (0.6 * eff + 0.4 * sr)


# ── Scoring ────────────────────────────────────────────────────────────────

WEIGHTS = {
    "goal_alignment": 0.15,
    "impact": 0.20,
    "urgency": 0.15,
    "confidence": 0.10,
    "data_quality": 0.10,
    "strategy": 0.20,
    "risk": 0.10,  # subtracted
}

# §23: minimum meaningful score difference before a recommendation changes. Below this,
# the previously selected strategy is retained (hysteresis) to avoid thrashing. Deterministic
# and configurable; a meaningful evidence change still flips the recommendation.
MIN_SCORE_DELTA = float(getattr(get_settings(), "RECOMMENDATION_MIN_DELTA", 0.03))


def apply_stability(ranked: list[dict[str, Any]], previous_selection: str | None) -> list[dict[str, Any]]:
    """Hysteresis (§23): if the top two strategies differ by < MIN_SCORE_DELTA and the
    previously-selected strategy is still in the top two, keep it first. Returns the
    (possibly reordered) ranking. A meaningful evidence change (>= delta) still flips.

    §Part 11 CRITICAL: stability NEVER overrides safety. If the previously-selected strategy
    has become unsafe (risk == 'high') or unavailable, it is NOT retained — the system
    switches immediately regardless of the score delta.
    """
    if not ranked or previous_selection is None:
        return ranked
    if len(ranked) < 2:
        return ranked

    # Safety override: if the previous selection is now unsafe/unavailable, never keep it.
    prev_rank = next((r for r in ranked if r.get("action_type") == previous_selection), None)
    if prev_rank is not None and prev_rank.get("risk") == "high":
        return ranked  # do not retain an unsafe strategy

    top = ranked[0]
    second = ranked[1]
    delta = (top.get("score") or 0.0) - (second.get("score") or 0.0)
    if abs(delta) >= MIN_SCORE_DELTA:
        return ranked  # meaningful difference → keep the higher scorer

    # Scores effectively tied: prefer the previous selection if it's in the top two.
    prev_index = next((i for i, r in enumerate(ranked[:2]) if r.get("action_type") == previous_selection), None)
    if prev_index is not None and prev_index != 0:
        ranked = [ranked[1], ranked[0], *ranked[2:]]
    return ranked


def compute_recommendation_score(
    *,
    goal_alignment: str,
    estimated_impact_sar: float | None,
    urgency: str | None,
    confidence: float | None,
    data_quality_score: float | None,
    strategy: dict[str, Any],
    risk: str | None,
) -> dict[str, Any]:
    """Deterministic, documented recommendation score + structured explanation (§14)."""
    terms = {
        "goal_alignment": normalize_goal_alignment(goal_alignment),
        "impact": normalize_impact_sar(estimated_impact_sar),
        "urgency": normalize_urgency(urgency),
        "confidence": normalize_confidence(confidence),
        "data_quality": normalize_data_quality(data_quality_score),
        "strategy": normalize_strategy(strategy),
        "risk": normalize_risk(risk),
    }

    score = sum(WEIGHTS[k] * terms[k] for k in WEIGHTS if k != "risk")
    score -= WEIGHTS["risk"] * terms["risk"]
    score = round(max(0.0, min(1.0, score)), 4)

    return {
        "score": score,
        "terms": {k: round(v, 3) for k, v in terms.items()},
        "weights": WEIGHTS,
        "explanation": build_explanation(
            goal_alignment=goal_alignment, estimated_impact_sar=estimated_impact_sar,
            urgency=urgency, confidence=confidence, data_quality_score=data_quality_score,
            strategy=strategy, risk=risk, score=score,
        ),
    }


def build_explanation(
    *,
    goal_alignment: str,
    estimated_impact_sar: float | None,
    urgency: str | None,
    confidence: float | None,
    data_quality_score: float | None,
    strategy: dict[str, Any],
    risk: str | None,
    score: float,
) -> dict[str, Any]:
    """Structured decision summary (not chain-of-thought). Human-readable, evidence-based."""
    impact_str = f"SAM {estimated_impact_sar:,.0f}" if estimated_impact_sar is not None else "n/a"
    return {
        "goal_alignment": goal_alignment,
        "expected_impact_sar": estimated_impact_sar,
        "urgency": urgency or "medium",
        "confidence": round(normalize_confidence(confidence) * 100, 1),
        "data_quality_pct": round(normalize_data_quality(data_quality_score) * 100, 1) if data_quality_score is not None else None,
        "strategy_effectiveness_pct": round(float(strategy.get("effectiveness") or 0) * 100, 1),
        "strategy_success_rate_pct": round(float(strategy.get("success_rate") or 0) * 100, 1) if strategy.get("success_rate") is not None else None,
        "strategy_attempts": strategy.get("attempts"),
        "evidence_tier": strategy.get("evidence_tier", "insufficient"),
        "risk": risk or "medium",
        "approval": "required" if risk in ("high", "medium") else "subject to policy",
        "score": score,
        "impact_label": impact_str,
    }
