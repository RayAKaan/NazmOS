"""Data-quality gating for forecasts.

Before any provider trains on a series, the series must pass :func:`assess_quality`.
Providers that succeed when data is poor silently write unreliable forecasts
(and can clobber a previously valid one); quality gating makes the "eligible or
fallback" decision explicit and transparent to the caller.
"""
from __future__ import annotations

from typing import Optional

from app.config import get_settings
from app.services.forecasting.schemas import DailyDemandSeries, DataQualityResult


def assess_quality(
    series: DailyDemandSeries,
    min_days: Optional[int] = None,
    min_nonzero_ratio: float = 0.05,
) -> DataQualityResult:
    """Assess whether a series is forecastable.

    Eligibility requires:
    - at least ``min_days`` distinct observed days (config MIN_DAYS_FOR_FORECAST);
    - at least ``max(1, min_days * min_nonzero_ratio)`` days with positive demand;
    - no negative quantity (returns should be netted by the caller, not treated
      as negative demand that distorts slope).
    """
    settings = get_settings()
    min_days = min_days or settings.MIN_DAYS_FOR_FORECAST

    if not series.points:
        return DataQualityResult(
            eligible=False,
            reason="no_transactions",
            observation_count=series.observation_count,
            nonzero_days=0,
            date_range_days=0,
            zero_ratio=1.0,
        )

    # Derive the authoritative stats from the points themselves; the series
    # metadata is informational (raw transaction count) and may be 0 when a
    # series was built directly by a provider/test.
    dates = [p.ds for p in series.points]
    date_range_days = (max(dates) - min(dates)).days + 1
    nonzero_days = sum(1 for p in series.points if p.y > 0)
    total_points = len(series.points)
    zero_ratio = round(1.0 - (nonzero_days / total_points), 4)

    if date_range_days < min_days:
        return DataQualityResult(
            eligible=False,
            reason="insufficient_data",
            observation_count=series.observation_count,
            nonzero_days=nonzero_days,
            date_range_days=date_range_days,
            zero_ratio=zero_ratio,
        )

    # Negative demand distorts both Prophet's slope and any baseline average.
    # Checked before zero-day gating so the more specific reason wins.
    neg_days = [p for p in series.points if p.y < 0]
    if neg_days:
        return DataQualityResult(
            eligible=False,
            reason="negative_quantities",
            observation_count=series.observation_count,
            nonzero_days=nonzero_days,
            date_range_days=date_range_days,
            zero_ratio=zero_ratio,
        )

    if nonzero_days < max(1, int(min_days * min_nonzero_ratio)):
        return DataQualityResult(
            eligible=False,
            reason="too_many_zero_days",
            observation_count=series.observation_count,
            nonzero_days=nonzero_days,
            date_range_days=date_range_days,
            zero_ratio=zero_ratio,
        )

    return DataQualityResult(
        eligible=True,
        reason=None,
        observation_count=series.observation_count,
        nonzero_days=nonzero_days,
        date_range_days=date_range_days,
        zero_ratio=zero_ratio,
    )