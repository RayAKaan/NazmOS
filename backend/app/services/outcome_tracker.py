"""V8 Outcome Tracker — records predicted vs actual outcomes for every action.

Every completed action records:
  - predicted impact
  - recoverable range
  - expected recovery (if calibrated)
  - action type
  - decision rationale
  - actual outcome
  - actual recovery
  - actual savings
  - execution success
  - time to outcome

Then compares PREDICTION vs ACTUAL.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class OutcomeRecord:
    """A single completed action's predicted vs actual outcome."""
    action_id: str
    sku: str
    business_id: str
    action_type: str
    decision_source: str  # DETERMINISTIC, AI_REASONING, AI_AGREES, etc.
    ai_confidence: float = 0.0
    ai_reasoning: str = ""
    # Predicted values (at decision time)
    predicted_impact_sar: float = 0.0
    recoverable_low_sar: float = 0.0
    recoverable_high_sar: float = 0.0
    expected_recovery_sar: float | None = None
    recovery_confidence: str = "INSUFFICIENT DATA"
    # Actual values (after execution)
    actual_recovery_sar: float = 0.0
    actual_savings_sar: float = 0.0
    execution_success: bool = False
    owner_accepted: bool = False
    time_to_outcome_days: int = 0
    # Metadata
    executed_at: str = ""
    completed_at: str = ""
    mode: str = ""  # MODE_A, MODE_B, MODE_C, SIMULATED
    is_simulated: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items()}

    @property
    def prediction_error(self) -> float | None:
        """Absolute error between expected and actual recovery."""
        if self.expected_recovery_sar is None:
            return None
        return abs(self.expected_recovery_sar - self.actual_recovery_sar)

    @property
    def prediction_error_pct(self) -> float | None:
        """Percentage error relative to actual recovery."""
        if self.expected_recovery_sar is None or self.actual_recovery_sar == 0:
            return None
        return abs(self.expected_recovery_sar - self.actual_recovery_sar) / abs(self.actual_recovery_sar)

    @property
    def within_recoverable_range(self) -> bool | None:
        """Whether actual recovery fell within the predicted range."""
        if self.recoverable_low_sar == 0 and self.recoverable_high_sar == 0:
            return None
        return self.recoverable_low_sar <= self.actual_recovery_sar <= self.recoverable_high_sar


@dataclass
class OutcomeSummary:
    """Aggregated outcome metrics for a set of actions."""
    total_actions: int = 0
    completed_actions: int = 0
    successful_executions: int = 0
    owner_acceptances: int = 0
    total_predicted_sar: float = 0.0
    total_actual_recovery_sar: float = 0.0
    total_actual_savings_sar: float = 0.0
    avg_prediction_error: float = 0.0
    avg_prediction_error_pct: float = 0.0
    within_range_count: int = 0
    within_range_pct: float = 0.0
    # Per action type
    by_action_type: dict[str, dict[str, Any]] = field(default_factory=dict)
    # Per decision source
    by_decision_source: dict[str, dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_actions": self.total_actions,
            "completed_actions": self.completed_actions,
            "successful_executions": self.successful_executions,
            "owner_acceptances": self.owner_acceptances,
            "total_predicted_sar": round(self.total_predicted_sar, 2),
            "total_actual_recovery_sar": round(self.total_actual_recovery_sar, 2),
            "total_actual_savings_sar": round(self.total_actual_savings_sar, 2),
            "avg_prediction_error": round(self.avg_prediction_error, 2),
            "avg_prediction_error_pct": round(self.avg_prediction_error_pct, 4),
            "within_range_count": self.within_range_count,
            "within_range_pct": round(self.within_range_pct, 4),
            "by_action_type": self.by_action_type,
            "by_decision_source": self.by_decision_source,
        }


class OutcomeTracker:
    """Tracks all outcome records and computes summary metrics.

    Supports both in-memory tracking (for experiments) and database persistence
    (for production). Database persistence uses the outcome_feedback table.
    """

    def __init__(self) -> None:
        self._records: list[OutcomeRecord] = []

    def record(self, outcome: OutcomeRecord) -> None:
        """Record a completed action's outcome (in-memory)."""
        self._records.append(outcome)

    async def record_and_persist(self, outcome: OutcomeRecord, db: "AsyncSession") -> None:
        """Record outcome in-memory and persist to database."""
        self._records.append(outcome)
        await self._persist_to_db(outcome, db)

    async def _persist_to_db(self, outcome: OutcomeRecord, db: "AsyncSession") -> None:
        """Persist a single outcome record to the outcome_feedback table.

        Uses the REAL outcome_feedback schema:
          decision_type        -> action type
          predicted_outcome    -> JSON snapshot at decision time
          actual_outcome       -> JSON measured result
          delta                -> prediction error metrics
          feedback_source      -> provenance label
        """
        from sqlalchemy import text
        await db.execute(
            text("""
                INSERT INTO outcome_feedback
                    (id, business_id, decision_type, predicted_outcome,
                     actual_outcome, delta, feedback_source, created_at)
                VALUES
                    (gen_random_uuid(), :business_id, :decision_type,
                     CAST(:predicted AS JSONB), CAST(:actual AS JSONB),
                     CAST(:delta AS JSONB), :feedback_source, NOW())
            """),
            {
                "business_id": outcome.business_id,
                "decision_type": outcome.action_type,
                "predicted": json.dumps({
                    "sku": outcome.sku,
                    "expected_recovery_sar": outcome.expected_recovery_sar,
                    "recoverable_low_sar": outcome.recoverable_low_sar,
                    "recoverable_high_sar": outcome.recoverable_high_sar,
                    "recovery_confidence": outcome.recovery_confidence,
                    "ai_confidence": outcome.ai_confidence,
                    "ai_reasoning": outcome.ai_reasoning[:500] if outcome.ai_reasoning else "",
                }, default=str),
                "actual": json.dumps({
                    "actual_recovery_sar": outcome.actual_recovery_sar,
                    "actual_savings_sar": outcome.actual_savings_sar,
                    "execution_success": outcome.execution_success,
                    "owner_accepted": outcome.owner_accepted,
                    "time_to_outcome_days": outcome.time_to_outcome_days,
                }, default=str),
                "delta": json.dumps({
                    "prediction_error": outcome.prediction_error,
                    "prediction_error_pct": outcome.prediction_error_pct,
                    "within_recoverable_range": outcome.within_recoverable_range,
                    "decision_source": outcome.decision_source,
                    "mode": outcome.mode,
                    "is_simulated": outcome.is_simulated,
                    "executed_at": outcome.executed_at,
                    "completed_at": outcome.completed_at,
                }, default=str),
                "feedback_source": "SIMULATION" if outcome.is_simulated else "money_audit",
            },
        )
        await db.commit()

    async def load_from_db(self, business_id: str, db: "AsyncSession") -> None:
        """Load outcome records from database into memory."""
        from sqlalchemy import text
        result = await db.execute(
            text("""
                SELECT business_id, decision_type, predicted_outcome,
                       actual_outcome, delta, created_at
                FROM outcome_feedback
                WHERE business_id = :business_id
                  AND decision_type IS NOT NULL
                ORDER BY created_at DESC
            """),
            {"business_id": business_id},
        )
        for row in result.fetchall():
            predicted = row.predicted_outcome if isinstance(row.predicted_outcome, dict) else {}
            actual = row.actual_outcome if isinstance(row.actual_outcome, dict) else {}
            delta = row.delta if isinstance(row.delta, dict) else {}
            expected = predicted.get("expected_recovery_sar")
            actual_recovery = float(actual.get("actual_recovery_sar") or 0)
            record = OutcomeRecord(
                action_id=str(row.created_at.timestamp()) if row.created_at else "",
                sku=str(predicted.get("sku", "")),
                business_id=str(row.business_id),
                action_type=row.decision_type or "",
                decision_source=delta.get("decision_source", "UNKNOWN"),
                ai_confidence=float(predicted.get("ai_confidence") or 0.0),
                predicted_impact_sar=float(expected) if expected is not None else 0.0,
                recoverable_low_sar=float(predicted.get("recoverable_low_sar") or 0.0),
                recoverable_high_sar=float(predicted.get("recoverable_high_sar") or 0.0),
                expected_recovery_sar=float(expected) if expected is not None else None,
                recovery_confidence=predicted.get("recovery_confidence", "INSUFFICIENT DATA"),
                actual_recovery_sar=actual_recovery,
                actual_savings_sar=float(actual.get("actual_savings_sar") or 0),
                execution_success=bool(actual.get("execution_success", False)),
                owner_accepted=bool(actual.get("owner_accepted", False)),
                time_to_outcome_days=int(actual.get("time_to_outcome_days") or 0),
                executed_at=str(delta.get("executed_at", "")),
                completed_at=str(delta.get("completed_at", "")),
                mode=delta.get("mode", ""),
                is_simulated=bool(delta.get("is_simulated", False)),
            )
            self._records.append(record)

    def get_records(self, business_id: str | None = None, mode: str | None = None) -> list[OutcomeRecord]:
        """Get filtered outcome records."""
        records = self._records
        if business_id:
            records = [r for r in records if r.business_id == business_id]
        if mode:
            records = [r for r in records if r.mode == mode]
        return records

    def compute_summary(self, business_id: str | None = None, mode: str | None = None) -> OutcomeSummary:
        """Compute aggregated outcome metrics."""
        records = self.get_records(business_id, mode)
        if not records:
            return OutcomeSummary()

        completed = [r for r in records if r.execution_success]
        accepted = [r for r in records if r.owner_accepted]
        errors = [r.prediction_error for r in records if r.prediction_error is not None]
        pct_errors = [r.prediction_error_pct for r in records if r.prediction_error_pct is not None]
        in_range = [r for r in records if r.within_recoverable_range is True]

        summary = OutcomeSummary(
            total_actions=len(records),
            completed_actions=len(completed),
            successful_executions=sum(1 for r in records if r.execution_success),
            owner_acceptances=len(accepted),
            total_predicted_sar=sum(r.expected_recovery_sar or 0 for r in records),
            total_actual_recovery_sar=sum(r.actual_recovery_sar for r in records),
            total_actual_savings_sar=sum(r.actual_savings_sar for r in records),
            avg_prediction_error=sum(errors) / len(errors) if errors else 0.0,
            avg_prediction_error_pct=sum(pct_errors) / len(pct_errors) if pct_errors else 0.0,
            within_range_count=len(in_range),
            within_range_pct=len(in_range) / len([r for r in records if r.within_recoverable_range is not None]) if any(r.within_recoverable_range is not None for r in records) else 0.0,
        )

        # By action type
        action_types = set(r.action_type for r in records)
        for at in action_types:
            at_records = [r for r in records if r.action_type == at]
            at_completed = [r for r in at_records if r.execution_success]
            summary.by_action_type[at] = {
                "total": len(at_records),
                "completed": len(at_completed),
                "total_predicted_sar": round(sum(r.expected_recovery_sar or 0 for r in at_records), 2),
                "total_actual_sar": round(sum(r.actual_recovery_sar for r in at_records), 2),
                "avg_prediction_error": round(
                    sum(r.prediction_error for r in at_records if r.prediction_error is not None) /
                    max(1, len([r for r in at_records if r.prediction_error is not None])), 2
                ),
            }

        # By decision source
        sources = set(r.decision_source for r in records)
        for src in sources:
            src_records = [r for r in records if r.decision_source == src]
            src_completed = [r for r in src_records if r.execution_success]
            summary.by_decision_source[src] = {
                "total": len(src_records),
                "completed": len(src_completed),
                "total_predicted_sar": round(sum(r.expected_recovery_sar or 0 for r in src_records), 2),
                "total_actual_sar": round(sum(r.actual_recovery_sar for r in src_records), 2),
                "avg_prediction_error": round(
                    sum(r.prediction_error for r in src_records if r.prediction_error is not None) /
                    max(1, len([r for r in src_records if r.prediction_error is not None])), 2
                ),
            }

        return summary
