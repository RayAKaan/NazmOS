"""Deterministic baseline forecast provider.

A transparent moving-average forecast used for:
  - fallback when data cannot support Prophet,
  - a backtesting/evaluation baseline to compare Prophet against,
  - any consumer that wants a fast, deterministic, explainable number.

Interval type is ``heuristic`` (fixed ±30% band) — never presented as a
statistical Prophet interval.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.forecasting.data_builder import fetch_daily_demand
from app.services.forecasting.provider import ForecastProvider
from app.services.forecasting.quality import assess_quality
from app.services.forecasting.schemas import FallbackReason, ForecastPrediction, ForecastResult
from app.utils.timezone import now_utc

# KSA weekend rush / mid-week lull multipliers (Thu/Fri/Sat peak, Tue lull).
WEEKDAY_MULTIPLIERS = {3: 1.38, 4: 1.45, 5: 1.30, 6: 0.85, 1: 0.70}
WEEKDAY_NAMES = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

# Heuristic interval band used by the baseline (NOT a statistical interval).
LOWER_FACTOR = 0.7
UPPER_FACTOR = 1.3


class BaselineProvider(ForecastProvider):
    provider_name = "baseline"
    model_version = "baseline_v1"

    async def forecast(
        self,
        db: AsyncSession,
        business_id: str | UUID,
        item_id: str | UUID,
        horizon_days: int = 30,
        context_days: int = 365,
        tz_name: Optional[str] = None,
    ) -> ForecastResult:
        series = await fetch_daily_demand(
            db, str(business_id), str(item_id), tz_name=tz_name, lookback_days=context_days
        )
        return baseline_from_series(
            series, horizon_days=horizon_days, provider=self, fallback_reason=None
        )


def baseline_from_series(
    series,
    horizon_days: int = 30,
    provider: ForecastProvider | None = None,
    fallback_reason: Optional[str] = None,
) -> ForecastResult:
    """Build a deterministic baseline forecast from a daily demand series."""
    provider = provider or BaselineProvider()
    quality = assess_quality(series)

    if not series.points:
        reason = fallback_reason or FallbackReason.NO_TRANSACTIONS.value
        return _empty_result(series, provider, horizon_days, reason)

    # Base level: mean of the most recent 30 observed days (or all if fewer).
    tail = series.points[-30:]
    base = sum(p.y for p in tail) / len(tail)
    base = max(base, 0.0)

    today = date.today()
    preds: list[ForecastPrediction] = []
    start = max(series.points[-1].ds, today)
    for i in range(1, horizon_days + 1):
        d = start + timedelta(days=i)
        mult = WEEKDAY_MULTIPLIERS.get(d.weekday(), 1.0)
        point = max(0.0, round(base * mult, 2))
        preds.append(
            ForecastPrediction(
                ds=d,
                predicted_qty=point,
                lower_bound=round(point * LOWER_FACTOR, 2),
                upper_bound=round(point * UPPER_FACTOR, 2),
            )
        )

    pattern_values = [WEEKDAY_MULTIPLIERS.get(i, 1.0) for i in range(7)]
    mean_mult = sum(pattern_values) / 7
    weekly_pattern = {
        WEEKDAY_NAMES[i]: round(pattern_values[i] / mean_mult, 3) for i in range(7)
    }

    return ForecastResult(
        business_id=series.business_id,
        item_id=series.item_id,
        predictions=preds,
        provider=provider.provider_name,
        model_version=provider.model_version,
        interval_type="heuristic",
        fallback_reason=fallback_reason,
        generated_at=now_utc(),
        data_start=series.points[0].ds if series.points else None,
        data_end=series.points[-1].ds if series.points else None,
        context_days=len(series.points),
        horizon_days=horizon_days,
        weekly_pattern=weekly_pattern,
        trend_direction="stable",
        trend_strength=0.0,
    )


def _empty_result(series, provider: ForecastProvider, horizon_days: int, reason: str) -> ForecastResult:
    """Zero-demand deterministic forecast used when there is no history at all.

    Returns a horizon of zeroes so consumers always receive a forecast-shaped
    answer, with ``fallback_reason`` telling them it is not real demand.
    """
    today = date.today()
    preds = [
        ForecastPrediction(
            ds=today + timedelta(days=i),
            predicted_qty=0.0,
            lower_bound=0.0,
            upper_bound=0.0,
        )
        for i in range(1, horizon_days + 1)
    ]
    return ForecastResult(
        business_id=series.business_id,
        item_id=series.item_id,
        predictions=preds,
        provider=provider.provider_name,
        model_version=provider.model_version,
        interval_type="heuristic",
        fallback_reason=reason,
        generated_at=now_utc(),
        data_start=None,
        data_end=None,
        context_days=0,
        horizon_days=horizon_days,
        weekly_pattern={
            "monday": 0.88, "tuesday": 0.85, "wednesday": 0.90,
            "thursday": 1.15, "friday": 1.42, "saturday": 1.35, "sunday": 0.95,
        },
        trend_direction="stable",
        trend_strength=0.0,
    )