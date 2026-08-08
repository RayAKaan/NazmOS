"""Advanced Learning Engine helpers.

Bayesian updates for pricing/restock conversion confidence, graph-based supplier/
branch similarity, and A/B holdback group assignment per business tier.
"""
from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from typing import Any


@dataclass
class BetaDistribution:
    alpha: float
    beta: float

    def mean(self) -> float:
        total = self.alpha + self.beta
        return self.alpha / total if total > 0 else 0.0

    def confidence_interval_95(self) -> tuple[float, float]:
        # Normal approximation (Wilson) when samples are large enough.
        total = self.alpha + self.beta
        if total < 30:
            # Fallback rough interval.
            return (max(0.0, self.mean() - 0.2), min(1.0, self.mean() + 0.2))
        z = 1.96
        p = self.mean()
        denom = 1 + z * z / total
        centre = (p + z * z / (2 * total)) / denom
        width = z * math.sqrt((p * (1 - p) + z * z / (4 * total)) / total) / denom
        return (max(0.0, centre - width), min(1.0, centre + width))


def update_pricing_confidence(
    prior: BetaDistribution,
    accepted: bool,
    revenue_impact_sar: float | None = None,
) -> BetaDistribution:
    """Update Beta(alpha, beta) after observing a pricing recommendation outcome.

    accepted=True increments alpha; accepted=False increments beta. A positive
    revenue impact gives alpha a small boost to reflect value, not just count.
    """
    alpha = prior.alpha
    beta = prior.beta
    if accepted:
        alpha += 1
        if revenue_impact_sar is not None and revenue_impact_sar > 0:
            alpha += min(0.5, revenue_impact_sar / 10000)
    else:
        beta += 1
    return BetaDistribution(alpha, beta)


def update_restock_confidence(
    prior: BetaDistribution,
    stockout_avoided: bool,
    waste_reduction_sar: float | None = None,
) -> BetaDistribution:
    """Update restock recommendation confidence based on observed outcome."""
    alpha = prior.alpha
    beta = prior.beta
    if stockout_avoided:
        alpha += 1
        if waste_reduction_sar is not None and waste_reduction_sar > 0:
            alpha += min(0.5, waste_reduction_sar / 5000)
    else:
        beta += 1
    return BetaDistribution(alpha, beta)


def graph_similarity(
    neighbors_a: set[str],
    neighbors_b: set[str],
) -> float:
    """Jaccard similarity of two neighbor sets (suppliers, branches, etc.)."""
    if not neighbors_a and not neighbors_b:
        return 1.0
    union = neighbors_a | neighbors_b
    if not union:
        return 0.0
    return len(neighbors_a & neighbors_b) / len(union)


def recommend_suppliers_by_similarity(
    target_neighbors: set[str],
    candidate_supplier_neighbors: dict[str, set[str]],
    min_similarity: float = 0.2,
) -> list[dict[str, Any]]:
    """Return suppliers whose customer graph overlaps with the target business."""
    scored = []
    for supplier_id, neighbors in candidate_supplier_neighbors.items():
        score = graph_similarity(target_neighbors, neighbors)
        if score >= min_similarity:
            scored.append({"supplier_id": supplier_id, "similarity": round(score, 3)})
    return sorted(scored, key=lambda x: x["similarity"], reverse=True)


def assign_holdback_group(
    business_id: str,
    tier: str,
    holdback_pct: float = 10.0,
) -> str:
    """Deterministically assign a business to control or treatment.

    The same business_id+tier always maps to the same group, so re-running the
    assignment does not flip groups. holdback_pct is the share kept in control.
    """
    digest = hashlib.sha256(f"{business_id}:{tier}:nazm_holdback".encode()).hexdigest()
    bucket = int(digest[:8], 16) % 100
    return "control" if bucket < holdback_pct else "treatment"


def compare_groups(
    control_outcomes: list[float],
    treatment_outcomes: list[float],
) -> dict[str, Any]:
    """Simple A/B comparison: means and a basic t-statistic approximation."""
    n_c = len(control_outcomes)
    n_t = len(treatment_outcomes)
    if n_c == 0 or n_t == 0:
        return {"control_mean": 0.0, "treatment_mean": 0.0, "lift_pct": 0.0, "significant": False}

    mean_c = sum(control_outcomes) / n_c
    mean_t = sum(treatment_outcomes) / n_t
    lift_pct = ((mean_t - mean_c) / mean_c * 100) if mean_c != 0 else 0.0

    var_c = sum((x - mean_c) ** 2 for x in control_outcomes) / max(1, n_c - 1)
    var_t = sum((x - mean_t) ** 2 for x in treatment_outcomes) / max(1, n_t - 1)
    se = math.sqrt(var_c / n_c + var_t / n_t) if (var_c + var_t) > 0 else 1.0
    t_stat = (mean_t - mean_c) / se if se > 0 else 0.0
    significant = abs(t_stat) > 1.96 and n_c >= 30 and n_t >= 30

    return {
        "control_mean": round(mean_c, 4),
        "treatment_mean": round(mean_t, 4),
        "lift_pct": round(lift_pct, 2),
        "t_stat": round(t_stat, 3),
        "significant": significant,
    }
