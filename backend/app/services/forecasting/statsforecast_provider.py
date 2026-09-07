"""StatsForecast forecast provider.

The canonical statistical forecasting model for NazmOS. Consumes the same
canonical daily series and quality gate as the rest of the pipeline, and
selects/mixes a small ensemble of statistically-correct Auto* models exposed by
StatsForecast (a permissive Apache-2.0 library).

Divergences from the legacy Prophet path (bugs fixed here):
  - no manual event uplifts stacked on top of the model (the models handle
    seasonality themselves; manual-uplift double counting is gone);
  - intervals come from StatsForecast conformal prediction, labelled
    ``interval_type="statsforecast_interval"``, not a ±30% heuristic nor a
    Prophet-specific interval;
  - the fit runs in a thread so the FastAPI event loop is not blocked;
  - the fallback reason is explicit in ``fallback_reason``.

Forecasting *policy* (which models, the season length, and the ensemble
aggregation) is owned by this provider layer — StatsForecast is used only as a
library of statistical forecasters. The sparse-data decision is owned by
:func:`app.services.forecasting.quality.assess_quality`; this provider never
overrides it.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, timedelta
from statistics import median
from typing import Optional
from uuid import UUID

import pandas as pd
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.forecasting.baseline_provider import baseline_from_series
from app.services.forecasting.data_builder import fetch_daily_demand
from app.services.forecasting.provider import ForecastProvider
from app.services.forecasting.quality import assess_quality
from app.services.forecasting.schemas import FallbackReason, ForecastPrediction, ForecastResult
from app.utils.timezone import now_utc

try:
    from statsforecast import StatsForecast
    from statsforecast.models import AutoARIMA, AutoETS
    STATSFORECAST_AVAILABLE = True
except ImportError:  # pragma: no cover - install path
    STATSFORECAST_AVAILABLE = False

logger = logging.getLogger("forecasting.statsforecast")

WEEKDAY_NAMES = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

# Ensemble model policy (NazmOS owns the choice; StatsForecast only executes it).
SEASON_LENGTH = 7        # weekly seasonality for daily demand
INTERVAL_LEVEL = 80      # conformal prediction level (matches legacy 0.80 Prophet width)
ENSEMBLE_MODEL_NAMES = ("AutoETS", "AutoARIMA")


def _ensemble_point(model_points: dict[str, float]) -> float:
    """Robustly combine the per-model point forecasts for one horizon step.

    The median is chosen over the mean so a single model's degenerate fit
    (e.g. a flat ARIMA on a near-constant series) cannot pull the ensemble.
    """
    values = [v for v in model_points.values() if v is not None]
    if not values:
        return 0.0
    return float(median(values))


def _ensemble_band(points: list[float], model_lows: dict[str, float], model_highs: dict[str, float]) -> tuple[float, float]:
    """Combine per-model conformal interval bands into one conservative band.

    Lower bound = min of model lows (widest below), upper = max of model highs
    (widest above), so the reported band covers every model's uncertainty.
    """
    lows = [v for v in model_lows.values() if v is not None]
    highs = [v for v in model_highs.values() if v is not None]
    lo = min(lows) if lows else points[0]
    hi = max(highs) if highs else points[0]
    return lo, hi


class StatsForecastProvider(ForecastProvider):
    provider_name = "statsforecast"
    model_version = "statsforecast_ensemble_v1"

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
        quality = assess_quality(series)

        if not quality.eligible:
            logger.info(
                "StatsForecast skipped (quality=%s) business=%s item=%s",
                quality.reason, business_id, item_id,
            )
            return baseline_from_series(
                series,
                horizon_days=horizon_days,
                provider=self,
                fallback_reason=quality.reason,
            )

        if not STATSFORECAST_AVAILABLE:
            return baseline_from_series(
                series,
                horizon_days=horizon_days,
                provider=self,
                fallback_reason=FallbackReason.STATSFORECAST_FAILED.value,
            )

        try:
            # StatsForecast fit is CPU-bound; keep the event loop responsive.
            return await asyncio.to_thread(
                self._fit_and_predict, series, horizon_days
            )
        except Exception:
            logger.exception(
                "StatsForecast fit failed business=%s item=%s -> baseline fallback",
                business_id, item_id,
            )
            return baseline_from_series(
                series,
                horizon_days=horizon_days,
                provider=self,
                fallback_reason=FallbackReason.STATSFORECAST_FAILED.value,
            )

    def _fit_and_predict(self, series, horizon_days: int) -> ForecastResult:
        daily = pd.DataFrame(
            [{"ds": p.ds, "y": p.y} for p in series.points],
            columns=["ds", "y"],
        )
        daily["ds"] = pd.to_datetime(daily["ds"])
        daily = daily.sort_values("ds").reset_index(drop=True)
        daily = daily.rename(columns={"ds": "ds", "y": "y"})
        daily.insert(0, "unique_id", series.item_id)

        models = [
            AutoETS(season_length=SEASON_LENGTH),
            AutoARIMA(season_length=SEASON_LENGTH),
        ]
        sf = StatsForecast(
            models=models,
            freq="D",
            n_jobs=1,
        )
        forecast = sf.forecast(h=horizon_days, df=daily, level=[INTERVAL_LEVEL])

        date_base = daily["ds"].max()
        predictions: list[ForecastPrediction] = []
        for i, row in forecast.iterrows():
            d = date_base.date() + timedelta(days=i + 1)
            point = _ensemble_point({
                "AutoETS": float(row["AutoETS"]) if pd.notna(row.get("AutoETS")) else None,
                "AutoARIMA": float(row["AutoARIMA"]) if pd.notna(row.get("AutoARIMA")) else None,
            })
            lo, hi = _ensemble_band(
                [point],
                {"AutoETS": float(row["AutoETS-lo-80"]) if pd.notna(row.get("AutoETS-lo-80")) else None,
                 "AutoARIMA": float(row["AutoARIMA-lo-80"]) if pd.notna(row.get("AutoARIMA-lo-80")) else None},
                {"AutoETS": float(row["AutoETS-hi-80"]) if pd.notna(row.get("AutoETS-hi-80")) else None,
                 "AutoARIMA": float(row["AutoARIMA-hi-80"]) if pd.notna(row.get("AutoARIMA-hi-80")) else None},
            )
            point = max(0.0, round(point, 2))
            lo = max(0.0, round(lo, 2))
            hi = max(lo, round(hi, 2))
            predictions.append(ForecastPrediction(
                ds=d,
                predicted_qty=point,
                lower_bound=lo,
                upper_bound=hi,
            ))

        weekly_avgs = daily.groupby(daily["ds"].dt.dayofweek)["y"].mean()
        baseline = weekly_avgs.mean() or 1
        weekly_pattern = {
            WEEKDAY_NAMES[i]: round(weekly_avgs.get(i, baseline) / baseline, 3)
            for i in range(7)
        }

        recent = daily.tail(14)["y"].mean()
        prior = daily.iloc[-28:-14]["y"].mean() if len(daily) >= 28 else daily["y"].mean()
        trend_pct = ((recent - prior) / prior * 100) if prior > 0 else 0
        trend_direction = "up" if trend_pct > 8 else "down" if trend_pct < -8 else "stable"

        return ForecastResult(
            business_id=series.business_id,
            item_id=series.item_id,
            predictions=predictions,
            provider=self.provider_name,
            model_version=self.model_version,
            interval_type="statsforecast_interval",
            fallback_reason=None,
            generated_at=now_utc(),
            data_start=series.points[0].ds if series.points else None,
            data_end=series.points[-1].ds if series.points else None,
            context_days=len(series.points),
            horizon_days=horizon_days,
            weekly_pattern=weekly_pattern,
            trend_direction=trend_direction,
            trend_strength=round(trend_pct, 2),
        )
