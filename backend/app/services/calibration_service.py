"""V8 Calibration Service — measures prediction error before/after calibration.

Do not claim that the system learned merely because an outcome record exists.

Measure:
  PRE-CALIBRATION prediction error
  ↓
  OBSERVED OUTCOMES
  ↓
  POST-CALIBRATION prediction error

Compare separately for: discount, transfer, reorder, pricing, recovery match.

Only claim learning if prediction error demonstrably improves on unseen subsequent outcomes.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from app.services.outcome_tracker import OutcomeTracker, OutcomeRecord

logger = logging.getLogger(__name__)


@dataclass
class CalibrationMetrics:
    """Prediction error metrics for a specific action type."""
    action_type: str
    pre_calibration_error: float = 0.0
    pre_calibration_error_pct: float = 0.0
    pre_calibration_samples: int = 0
    post_calibration_error: float = 0.0
    post_calibration_error_pct: float = 0.0
    post_calibration_samples: int = 0
    improvement_pct: float = 0.0
    is_improved: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_type": self.action_type,
            "pre_calibration_error": round(self.pre_calibration_error, 2),
            "pre_calibration_error_pct": round(self.pre_calibration_error_pct, 4),
            "pre_calibration_samples": self.pre_calibration_samples,
            "post_calibration_error": round(self.post_calibration_error, 2),
            "post_calibration_error_pct": round(self.post_calibration_error_pct, 4),
            "post_calibration_samples": self.post_calibration_samples,
            "improvement_pct": round(self.improvement_pct, 4),
            "is_improved": self.is_improved,
        }


@dataclass
class CalibrationReport:
    """Full calibration report comparing before/after metrics."""
    business_id: str
    overall_pre_error: float = 0.0
    overall_post_error: float = 0.0
    overall_improvement_pct: float = 0.0
    by_action_type: dict[str, CalibrationMetrics] = field(default_factory=dict)
    claim_learning: bool = False
    learning_evidence: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "business_id": self.business_id,
            "overall_pre_error": round(self.overall_pre_error, 2),
            "overall_post_error": round(self.overall_post_error, 2),
            "overall_improvement_pct": round(self.overall_improvement_pct, 4),
            "by_action_type": {k: v.to_dict() for k, v in self.by_action_type.items()},
            "claim_learning": self.claim_learning,
            "learning_evidence": self.learning_evidence,
        }


class CalibrationService:
    """Measures prediction error before and after calibration."""

    def __init__(self, tracker: OutcomeTracker) -> None:
        self.tracker = tracker

    def compute_calibration_split(
        self,
        records: list[OutcomeRecord],
        split_point: int,
    ) -> tuple[list[OutcomeRecord], list[OutcomeRecord]]:
        """Split records into pre-calibration and post-calibration sets.

        The split_point is an index — records before it are pre-calibration,
        records after it are post-calibration (used for measuring improvement).
        """
        pre = records[:split_point]
        post = records[split_point:]
        return pre, post

    def _compute_error_stats(self, records: list[OutcomeRecord]) -> tuple[float, float, int]:
        """Compute average absolute error and percentage error for a set of records."""
        errors = [r.prediction_error for r in records if r.prediction_error is not None]
        pct_errors = [r.prediction_error_pct for r in records if r.prediction_error_pct is not None]
        avg_error = sum(errors) / len(errors) if errors else 0.0
        avg_pct_error = sum(pct_errors) / len(pct_errors) if pct_errors else 0.0
        return avg_error, avg_pct_error, len(errors)

    def compute_calibration_report(
        self,
        business_id: str,
        split_point: int | None = None,
    ) -> CalibrationReport:
        """Compute calibration report for a business.

        If split_point is None, uses the midpoint of records as the split.
        """
        all_records = self.tracker.get_records(business_id=business_id)
        if not all_records:
            return CalibrationReport(business_id=business_id)

        if split_point is None:
            split_point = len(all_records) // 2

        pre_records, post_records = self.compute_calibration_split(all_records, split_point)

        report = CalibrationReport(business_id=business_id)

        # Overall metrics
        pre_error, pre_pct, pre_count = self._compute_error_stats(pre_records)
        post_error, post_pct, post_count = self._compute_error_stats(post_records)
        report.overall_pre_error = pre_error
        report.overall_post_error = post_error
        report.overall_improvement_pct = (
            (pre_error - post_error) / pre_error if pre_error > 0 else 0.0
        )

        # Per action type
        action_types = set(r.action_type for r in all_records)
        for at in action_types:
            pre_at = [r for r in pre_records if r.action_type == at]
            post_at = [r for r in post_records if r.action_type == at]
            pre_at_error, pre_at_pct, pre_at_count = self._compute_error_stats(pre_at)
            post_at_error, post_at_pct, post_at_count = self._compute_error_stats(post_at)
            improvement = (pre_at_error - post_at_error) / pre_at_error if pre_at_error > 0 else 0.0
            report.by_action_type[at] = CalibrationMetrics(
                action_type=at,
                pre_calibration_error=pre_at_error,
                pre_calibration_error_pct=pre_at_pct,
                pre_calibration_samples=pre_at_count,
                post_calibration_error=post_at_error,
                post_calibration_error_pct=post_at_pct,
                post_calibration_samples=post_at_count,
                improvement_pct=improvement,
                is_improved=improvement > 0.05,  # 5% improvement threshold
            )

        # Determine if learning claim is justified
        min_samples = 5
        improved_types = [m for m in report.by_action_type.values() if m.is_improved and m.post_calibration_samples >= min_samples]
        total_post = sum(m.post_calibration_samples for m in report.by_action_type.values())

        if len(improved_types) >= 1 and total_post >= min_samples and report.overall_improvement_pct > 0.05:
            report.claim_learning = True
            improved_names = [m.action_type for m in improved_types]
            report.learning_evidence = (
                f"Prediction error improved by {report.overall_improvement_pct:.1%} overall. "
                f"Improved action types: {', '.join(improved_names)}. "
                f"Based on {total_post} post-calibration samples."
            )
        else:
            report.claim_learning = False
            report.learning_evidence = (
                f"Insufficient evidence for learning claim. "
                f"Overall improvement: {report.overall_improvement_pct:.1%}. "
                f"Post-calibration samples: {total_post} (need >= {min_samples})."
            )

        return report
