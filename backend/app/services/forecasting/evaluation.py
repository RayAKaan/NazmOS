"""Rolling-origin backtesting and metrics for forecast evaluation.

The forecasting pipeline makes no claims it cannot measure.  This module
implements a standard rolling-origin (expanding-window) evaluation:

1. Split the available demand history into successive train/test windows.
2. Fit the provider on each training window.
3. Forecast the next ``horizon_days`` and compare with actuals.
4. Aggregate per-fold errors into MAPE / RMSE.

Evaluation drives a *predictor callable* so it stays provider-agnostic.  In
practice backtests run against ``BaselineProvider`` (deterministic, no DB
dependency, explicit ``baseline_from_series``).  A caller that wants to
benchmark Prophet in-process can supply its own predictor that fits and
returns the next ``horizon_days`` quantities from a training series.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Callable, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.forecasting.data_builder import DailyDemandPoint, DailyDemandSeries

logger = logging.getLogger("forecasting.evaluation")

MIN_FOLDS = 5           # below this, aggregate metrics are too volatile to be useful
DEFAULT_HORIZON = 7     # compare next 7 days against actuals
DEFAULT_MIN_TRAIN = 30  # minimum days required before the first fold

# (train_points) -> list[float] of horizon_days predicted quantities
Predictor = Callable[[list[DailyDemandPoint]], list[float]]


@dataclass(frozen=True)
class FoldResult:
    train_end: str
    test_start: str
    actual_qty: list[float]
    predicted_qty: list[float]
    mape: float | None  # None when any actual == 0
    rmse: float | None


@dataclass(frozen=True)
class BacktestResult:
    folds: list[FoldResult]
    overall_mape: float | None
    overall_rmse: float | None
    n_folds: int
    data_points: int
    eligible: bool
    reason: str


def _mape(actual: list[float], predicted: list[float]) -> float | None:
    """Mean Absolute Percentage Error; ``None`` when any actual is 0 (undefined)."""
    if not actual or not predicted or len(actual) != len(predicted):
        return None
    if any(a == 0 for a in actual):
        return None
    return sum(abs(a - p) / a for a, p in zip(actual, predicted)) / len(actual) * 100


def _rmse(actual: list[float], predicted: list[float]) -> float | None:
    if not actual or not predicted or len(actual) != len(predicted):
        return None
    n = len(actual)
    return math.sqrt(sum((a - p) ** 2 for a, p in zip(actual, predicted)) / n)


def rolling_origin_backtest(
    predictor: Predictor,
    series: DailyDemandSeries,
    min_train_days: int = DEFAULT_MIN_TRAIN,
    horizon_days: int = DEFAULT_HORIZON,
    step_days: int = 1,
) -> BacktestResult:
    """Evaluate ``predictor`` on ``series`` using expanding-window backtesting.

    Each fold:
      - trains on ``points[:train_end]`` inclusive
      - forecasts ``horizon_days`` steps
      - computes error against the next ``horizon_days`` actuals

    Returns a ``BacktestResult`` with aggregate metrics and per-fold detail.
    """
    points = list(series.points)
    if not points:
        return BacktestResult([], None, None, 0, 0, False, "no_data")

    n = len(points)
    if n < min_train_days + horizon_days:
        return BacktestResult(
            [], None, None, 0, n, False,
            f"insufficient_data: {n} points < {min_train_days + horizon_days} required",
        )

    folds: list[FoldResult] = []
    train_end_idx = min_train_days - 1  # inclusive index into points
    while train_end_idx + horizon_days < n:
        train_points = points[: train_end_idx + 1]
        test_points = points[train_end_idx + 1 : train_end_idx + 1 + horizon_days]
        if len(test_points) < horizon_days:
            break
        try:
            pred_qty = predictor(train_points)
        except Exception:
            logger.debug(
                "Backtest fold train_end=%s failed", train_points[-1].ds, exc_info=True
            )
            train_end_idx += step_days
            continue
        if not pred_qty or len(pred_qty) < horizon_days:
            train_end_idx += step_days
            continue

        actual_vals = [p.y for p in test_points[: len(pred_qty)]]
        pred_vals = [float(v) for v in pred_qty[: len(actual_vals)]]
        folds.append(FoldResult(
            train_end=str(train_points[-1].ds),
            test_start=str(test_points[0].ds),
            actual_qty=actual_vals,
            predicted_qty=pred_vals,
            mape=_mape(actual_vals, pred_vals),
            rmse=_rmse(actual_vals, pred_vals),
        ))
        train_end_idx += step_days

    if not folds:
        return BacktestResult([], None, None, 0, n, False, "all_folds_failed")

    mapes = [f.mape for f in folds if f.mape is not None]
    rmses = [f.rmse for f in folds if f.rmse is not None]
    overall_mape = round(sum(mapes) / len(mapes), 2) if mapes else None
    overall_rmse = round(sum(rmses) / len(rmses), 2) if rmses else None
    eligible = len(folds) >= MIN_FOLDS and overall_mape is not None
    reason = None if eligible else "insufficient_folds" if len(folds) < MIN_FOLDS else "mapes_contain_zeros"

    return BacktestResult(
        folds=folds,
        overall_mape=overall_mape,
        overall_rmse=overall_rmse,
        n_folds=len(folds),
        data_points=n,
        eligible=eligible,
        reason=reason,
    )


def baseline_predictor(horizon_days: int = DEFAULT_HORIZON) -> Predictor:
    """Return a ``BaselineProvider``-driven predictor for backtesting.

    Because ``baseline_from_series`` is pure (no DB), it is the natural,
    fully deterministic backtest baseline.
    """
    from app.services.forecasting.baseline_provider import baseline_from_series
    from app.services.forecasting.schemas import DailyDemandSeries as Series

    def _predict(train_points: list[DailyDemandPoint]) -> list[float]:
        mini = Series(
            business_id="eval",
            item_id="eval",
            timezone="Asia/Riyadh",
            points=train_points,
        )
        result = baseline_from_series(mini, horizon_days=horizon_days)
        return [p.predicted_qty for p in result.predictions]

    return _predict


async def populate_metrics(
    db: AsyncSession,
    business_id: str | UUID,
    item_id: str | UUID,
    horizon_days: int = DEFAULT_HORIZON,
    predictor: Optional[Predictor] = None,
) -> dict:
    """Backtest one item and persist metrics into ``forecast_cache``.

    Defaults to the ``BaselineProvider`` predictor.  The caller owns the
    transaction (commit / rollback).  Metrics land in the existing
    ``mape_score`` / ``rmse_score`` columns (Phase 9 moves them to a dedicated
    evaluation table when the schema is finalised).
    """
    from sqlalchemy import text

    from app.services.forecasting.data_builder import fetch_daily_demand

    points = await fetch_daily_demand(db, str(business_id), str(item_id))
    if not points:
        return {"status": "no_data", "mape_score": None, "rmse_score": None}

    series = DailyDemandSeries(
        business_id=str(business_id),
        item_id=str(item_id),
        timezone="Asia/Riyadh",
        points=points,
    )
    predictor = predictor or baseline_predictor(horizon_days=horizon_days)
    result = rolling_origin_backtest(predictor, series, horizon_days=horizon_days)

    if not result.eligible:
        return {
            "status": "ineligible",
            "reason": result.reason,
            "mape_score": result.overall_mape,
            "rmse_score": result.overall_rmse,
        }

    await db.execute(
        text(
            "UPDATE forecast_cache SET mape_score = :mape, rmse_score = :rmse "
            "WHERE business_id = :business_id AND item_id = :item_id"
        ),
        {
            "business_id": str(business_id),
            "item_id": str(item_id),
            "mape": result.overall_mape,
            "rmse": result.overall_rmse,
        },
    )
    return {
        "status": "ok",
        "mape_score": result.overall_mape,
        "rmse_score": result.overall_rmse,
        "n_folds": result.n_folds,
    }