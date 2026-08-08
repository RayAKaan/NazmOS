"""Learning Engine service (Phase 6).

Closes the intelligence feedback loop by comparing predicted and actual
outcomes, tracking per-decision-type performance, and refreshing selection
heuristics with weighted averages and Thompson sampling.
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import ExecutionJob, IntelligenceDecision, ModelPerformance, OutcomeFeedback
from app.utils.logger import setup_logger

logger = setup_logger("learning_engine")


def _to_uuid(value: UUID | str) -> UUID:
    if isinstance(value, UUID):
        return value
    return UUID(value)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _compute_delta(predicted: dict[str, Any], actual: dict[str, Any]) -> dict[str, Any]:
    delta: dict[str, Any] = {}
    for key, pred in predicted.items():
        if key in actual:
            actual_val = actual[key]
            pred_f = _safe_float(pred, None)
            actual_f = _safe_float(actual_val, None)
            if pred_f is not None and actual_f is not None:
                delta[key] = round(actual_f - pred_f, 4)
                if pred_f != 0:
                    delta[f"{key}_error_pct"] = round(((actual_f - pred_f) / pred_f) * 100, 4)
    return delta


def _predicted_outcome_from_decision(decision: IntelligenceDecision | None) -> dict[str, Any]:
    if decision is None:
        return {}
    predicted: dict[str, Any] = {
        "decision_type": decision.decision_type,
        "confidence": float(decision.confidence) if decision.confidence is not None else None,
    }
    if decision.expected_roi is not None:
        predicted["roi"] = float(decision.expected_roi)
    ranked = decision.ranked_action or {}
    if ranked.get("action_type"):
        predicted["action_type"] = ranked["action_type"]
    if ranked.get("expected_roi") is not None:
        predicted["expected_roi"] = _safe_float(ranked.get("expected_roi"))
    return predicted


async def record_feedback(
    session: AsyncSession,
    business_id: UUID | str,
    actual_outcome: dict[str, Any],
    decision_id: UUID | str | None = None,
    execution_job_id: UUID | str | None = None,
    feedback_source: str = "manual",
    recorded_at: datetime | None = None,
) -> OutcomeFeedback:
    """Record a single outcome feedback record.

    Predicted outcome is derived from the linked decision when available.
    """
    business_id = _to_uuid(business_id)

    decision: IntelligenceDecision | None = None
    if decision_id is not None:
        decision = await session.get(IntelligenceDecision, _to_uuid(decision_id))
    elif execution_job_id is not None:
        job = await session.get(ExecutionJob, _to_uuid(execution_job_id))
        if job is not None:
            if job.decision_id is not None:
                decision = await session.get(IntelligenceDecision, job.decision_id)

    if decision is None and execution_job_id is None and decision_id is None:
        raise ValueError("Either decision_id or execution_job_id is required")

    predicted_outcome = _predicted_outcome_from_decision(decision)
    if decision is not None and decision_id is None:
        decision_id = decision.id

    delta = _compute_delta(predicted_outcome, actual_outcome)

    feedback = OutcomeFeedback(
        business_id=business_id,
        decision_id=_to_uuid(decision_id) if decision_id else None,
        execution_job_id=_to_uuid(execution_job_id) if execution_job_id else None,
        decision_type=decision.decision_type if decision else predicted_outcome.get("decision_type"),
        predicted_outcome=predicted_outcome,
        actual_outcome=actual_outcome,
        delta=delta,
        feedback_source=feedback_source,
        recorded_at=recorded_at or datetime.now(timezone.utc),
    )
    session.add(feedback)
    await session.flush()
    return feedback


async def list_feedback(
    session: AsyncSession,
    business_id: UUID | str,
    decision_type: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[OutcomeFeedback], int]:
    """List recorded feedback for a business, optionally filtered by decision type."""
    business_id = _to_uuid(business_id)
    query = select(OutcomeFeedback).where(OutcomeFeedback.business_id == business_id)
    count_query = select(func.count(OutcomeFeedback.id)).where(OutcomeFeedback.business_id == business_id)

    if decision_type:
        query = query.where(OutcomeFeedback.decision_type == decision_type)
        count_query = count_query.where(OutcomeFeedback.decision_type == decision_type)

    query = query.order_by(OutcomeFeedback.recorded_at.desc()).offset(offset).limit(limit)

    result = await session.execute(query)
    total_result = await session.execute(count_query)
    return list(result.scalars().all()), int(total_result.scalar_one())


def _feedback_success(feedback: OutcomeFeedback) -> bool | None:
    actual = feedback.actual_outcome or {}
    if "success" in actual:
        return bool(actual["success"])
    predicted_roi = _safe_float(feedback.predicted_outcome.get("roi"), None)
    actual_roi = _safe_float(actual.get("roi"), None)
    if predicted_roi is not None and actual_roi is not None:
        # Consider a decision successful when actual ROI meets or exceeds prediction.
        return actual_roi >= predicted_roi
    return None


async def compute_model_performance(
    session: AsyncSession,
    business_id: UUID | str,
    decision_type: str,
    window_start: datetime,
    window_end: datetime,
) -> ModelPerformance:
    """Compute accuracy and ROI error for a decision type over a time window.

    Inserts or updates the corresponding ``model_performance`` row.
    """
    business_id = _to_uuid(business_id)

    result = await session.execute(
        select(OutcomeFeedback).where(
            OutcomeFeedback.business_id == business_id,
            OutcomeFeedback.decision_type == decision_type,
            OutcomeFeedback.recorded_at >= window_start,
            OutcomeFeedback.recorded_at <= window_end,
        )
    )
    feedback_rows = list(result.scalars().all())
    samples = len(feedback_rows)

    accuracy: float | None = None
    roi_errors: list[float] = []
    latencies: list[float] = []

    if samples:
        successes = 0
        judged = 0
        for fb in feedback_rows:
            success = _feedback_success(fb)
            if success is not None:
                judged += 1
                if success:
                    successes += 1

            predicted_roi = _safe_float(fb.predicted_outcome.get("roi"), None)
            actual_roi = _safe_float(fb.actual_outcome.get("roi"), None)
            if predicted_roi is not None and actual_roi is not None:
                if predicted_roi != 0:
                    roi_errors.append(abs((actual_roi - predicted_roi) / predicted_roi) * 100)
                else:
                    roi_errors.append(abs(actual_roi - predicted_roi))

            latency = _safe_float(fb.actual_outcome.get("latency_ms"), None)
            if latency is not None:
                latencies.append(latency)

        if judged:
            accuracy = round(successes / judged, 4)

    roi_error = round(sum(roi_errors) / len(roi_errors), 4) if roi_errors else None
    mean_latency_ms = round(sum(latencies) / len(latencies), 2) if latencies else None

    existing = await session.scalar(
        select(ModelPerformance).where(
            ModelPerformance.business_id == business_id,
            ModelPerformance.decision_type == decision_type,
            ModelPerformance.window_start == window_start,
        )
    )

    if existing:
        existing.samples = samples
        existing.accuracy = accuracy
        existing.roi_error = roi_error
        existing.mean_latency_ms = mean_latency_ms
        existing.last_updated_at = datetime.now(timezone.utc)
        performance = existing
    else:
        performance = ModelPerformance(
            business_id=business_id,
            decision_type=decision_type,
            window_start=window_start,
            window_end=window_end,
            samples=samples,
            accuracy=accuracy,
            roi_error=roi_error,
            mean_latency_ms=mean_latency_ms,
        )
        session.add(performance)

    await session.flush()
    return performance


async def get_model_performance(
    session: AsyncSession,
    business_id: UUID | str,
    decision_type: str | None = None,
) -> list[ModelPerformance]:
    """Return model performance rows for a business, optionally filtered."""
    business_id = _to_uuid(business_id)
    query = select(ModelPerformance).where(ModelPerformance.business_id == business_id)
    if decision_type:
        query = query.where(ModelPerformance.decision_type == decision_type)
    query = query.order_by(ModelPerformance.window_start.desc())
    result = await session.execute(query)
    return list(result.scalars().all())


async def refresh_learning(
    session: AsyncSession,
    business_id: UUID | str,
    window_days: int = 30,
) -> list[ModelPerformance]:
    """Refresh performance aggregates for all decision types with recent feedback."""
    business_id = _to_uuid(business_id)
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(days=window_days)

    result = await session.execute(
        select(OutcomeFeedback.decision_type)
        .distinct()
        .where(
            OutcomeFeedback.business_id == business_id,
            OutcomeFeedback.recorded_at >= window_start,
        )
    )
    decision_types = [row[0] for row in result.all() if row[0]]

    refreshed: list[ModelPerformance] = []
    for dt in decision_types:
        performance = await compute_model_performance(
            session, business_id, dt, window_start, now
        )
        refreshed.append(performance)

    return refreshed


def thompson_sample_action(
    candidates: list[dict[str, Any]],
    feedback_rows: list[OutcomeFeedback],
    rng: random.Random | None = None,
) -> tuple[dict[str, Any], dict[str, float], str]:
    """Select a candidate action using Thompson sampling over historical feedback.

    Each candidate is treated as a Bernoulli bandit arm. Successes and failures
    are derived from outcome feedback for the matching action type. The function
    returns the selected candidate, arm scores (probabilities), and an
    explanatory note.
    """
    if rng is None:
        rng = random.Random()

    scores: dict[str, float] = {}
    for candidate in candidates:
        action_type = candidate["action_type"]
        successes = 0
        failures = 0
        for fb in feedback_rows:
            fb_action = fb.predicted_outcome.get("action_type") or fb.actual_outcome.get("action_type")
            if fb_action != action_type:
                continue
            success = _feedback_success(fb)
            if success is True:
                successes += 1
            elif success is False:
                failures += 1

        alpha = successes + 1
        beta = failures + 1
        scores[action_type] = rng.betavariate(alpha, beta)

    if not scores:
        selected = candidates[0]
        note = "No historical feedback; selected first candidate"
        return selected, {c["action_type"]: 1.0 / len(candidates) for c in candidates}, note

    selected_action_type = max(scores, key=scores.get)
    selected = next(c for c in candidates if c["action_type"] == selected_action_type)
    note = f"Selected '{selected_action_type}' by Thompson sampling over {len(feedback_rows)} feedback records"
    return selected, scores, note


async def suggest_best_action(
    session: AsyncSession,
    business_id: UUID | str,
    candidates: list[dict[str, Any]],
    decision_type: str | None = None,
    seed: int | None = None,
) -> tuple[dict[str, Any], dict[str, float], str]:
    """Suggest the best candidate action for a business using learned feedback.

    Feedback is filtered by decision_type when provided and limited to the last
    90 days so recent signal dominates.
    """
    business_id = _to_uuid(business_id)
    since = datetime.now(timezone.utc) - timedelta(days=90)

    query = select(OutcomeFeedback).where(
        OutcomeFeedback.business_id == business_id,
        OutcomeFeedback.recorded_at >= since,
    )
    if decision_type:
        query = query.where(OutcomeFeedback.decision_type == decision_type)

    result = await session.execute(query)
    feedback_rows = list(result.scalars().all())

    rng = random.Random(seed) if seed is not None else None
    selected, scores, note = thompson_sample_action(candidates, feedback_rows, rng=rng)
    return selected, scores, note
