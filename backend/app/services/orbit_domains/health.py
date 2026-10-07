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
        data_quality_score: int | None = None,
    ) -> tuple[int | None, Any]:
        """Compute health score and breakdown.

        Every domain score may be ``None`` when that domain could not be assessed.
        An unavailable domain is **excluded and its weight renormalised**, never
        treated as zero. Scoring an unknown domain as 0 would report a healthy
        business as badly unhealthy, and the previous implementation avoided the
        opposite problem by hardcoding 91 for data quality, which is worse because
        it looks like a measurement.

        Returns ``(None, breakdown)`` when no domain at all could be assessed.
        """
        from app.services.orbit_contracts import HealthBreakdown, DomainScore

        c = self.config
        weighted = (
            (sales_score, c.sales_weight),
            (inventory_score, c.inventory_weight),
            (margin_score, c.margins_weight),
            (procurement_score, c.procurement_weight),
            (data_quality_score, c.data_quality_weight),
        )
        usable = [
            (score, weight) for score, weight in weighted
            if score is not None and weight > 0
        ]
        total_weight = sum(weight for _score, weight in usable)

        def clamp(value: int | None) -> int | None:
            return None if value is None else max(0, min(100, value))

        sales_c, inventory_c = clamp(sales_score), clamp(inventory_score)
        margin_c, procurement_c = clamp(margin_score), clamp(procurement_score)
        dq_c = clamp(data_quality_score)

        if not usable or total_weight <= 0:
            return None, HealthBreakdown(
                sales=DomainScore(score=sales_c, confidence="UNKNOWN", evidence_ids=[]),
                inventory=DomainScore(score=inventory_c, confidence="UNKNOWN", evidence_ids=[]),
                margins=DomainScore(score=margin_c, confidence="UNKNOWN", evidence_ids=[]),
                procurement=DomainScore(score=procurement_c, confidence="UNKNOWN", evidence_ids=[]),
                data_quality=DomainScore(score=dq_c, confidence="UNKNOWN", evidence_ids=[]),
            )

        total = sum(score * weight for score, weight in usable) / total_weight
        total_c = max(0, min(100, int(total)))

        # Confidence reflects how much of the composite weight was actually measured.
        coverage = total_weight / (
            c.sales_weight + c.inventory_weight + c.margins_weight
            + c.procurement_weight + c.data_quality_weight
        )
        confidence = "HIGH" if coverage >= 0.99 else "MEDIUM" if coverage >= 0.6 else "LOW"

        breakdown = HealthBreakdown(
            sales=DomainScore(score=sales_c, confidence=confidence if sales_c is not None else "UNKNOWN", evidence_ids=[]),
            inventory=DomainScore(score=inventory_c, confidence=confidence if inventory_c is not None else "UNKNOWN", evidence_ids=[]),
            margins=DomainScore(score=margin_c, confidence=confidence if margin_c is not None else "UNKNOWN", evidence_ids=[]),
            procurement=DomainScore(score=procurement_c, confidence=confidence if procurement_c is not None else "UNKNOWN", evidence_ids=[]),
            data_quality=DomainScore(score=dq_c, confidence=confidence if dq_c is not None else "UNKNOWN", evidence_ids=[]),
        )
        return total_c, breakdown