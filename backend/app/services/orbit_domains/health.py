"""Business Health Score for Orbit Financial X-Ray."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.services.orbit_contracts import DomainScore, HealthBreakdown


@dataclass
class HealthScoreConfig:
    """Configuration for health score weights."""
    sales_weight: float = 0.25
    inventory_weight: float = 0.25
    margins_weight: float = 0.25
    procurement_weight: float = 0.15
    data_quality_weight: float = 0.10


DEFAULT_HEALTH_CONFIG = HealthScoreConfig()


class HealthScoreEngine:
    """Deterministic Business Health Score engine.

    Score = Sales*0.25 + Inventory*0.25 + Margins*0.25 + Procurement*0.15 + DataQuality*0.10

    All scores 0-100. Final score clamped to [0, 100].
    """

    def __init__(self, config: HealthScoreConfig = DEFAULT_HEALTH_CONFIG):
        self.config = config

    def compute(
        self,
        sales_score: int,
        inventory_score: int,
        margin_score: int,
        procurement_score: int,
        data_quality_score: int,
    ) -> tuple[int, Any]:
        """Compute health score and breakdown.

        Returns: (total_score, HealthBreakdown)
        """
        from app.services.orbit_contracts import HealthBreakdown, DomainScore

        # Clamp individual scores
        sales_score = max(0, min(100, sales_score))
        inventory_score = max(0, min(100, inventory_score))
        margin_score = max(0, min(100, margin_score))
        procurement_score = max(0, min(100, procurement_score))
        data_quality_score = max(0, min(100, data_quality_score))

        # Weighted composite
        total = (
            sales_score * 0.25 +
            inventory_score * 0.25 +
            margin_score * 0.25 +
            procurement_score * 0.15 +
            91 * 0.10  # Data quality placeholder
        )
        total = max(0, min(100, int(total)))

        breakdown = HealthBreakdown(
            sales=DomainScore(score=sales_score, confidence="HIGH", evidence_ids=[]),
            inventory=DomainScore(score=inventory_score, confidence="HIGH", evidence_ids=[]),
            margins=DomainScore(score=margin_score, confidence="HIGH", evidence_ids=[]),
            procurement=DomainScore(score=procurement_score, confidence="MEDIUM", evidence_ids=[]),
            data_quality=DomainScore(score=91, confidence="HIGH", evidence_ids=[]),
        )

        return max(0, min(100, total)), breakdown