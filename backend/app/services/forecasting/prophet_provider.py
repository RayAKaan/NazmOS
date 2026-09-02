"""Prophet forecast provider — the primary forecasting model.

Consumes the canonical daily series from :mod:`data_builder`, gates on
:mod:`quality`, and falls back to the deterministic baseline when data cannot
support Prophet or the model fails.

Divergences from the legacy ``prophet_service.TrainAndForecast`` path (bugs
fixed here):
  - no manual event uplifts stacked on top of Prophet's own holiday handling
    (FORECAST_EVENT_UPLIFT_ENABLED governs that separately in the legacy service);
  - intervals come from Prophet's own ``yhat_lower``/``yhat_upper`` and are
    labelled ``interval_type="prophet_interval"``, not a ±30% heuristic;
  - the fit runs in a thread so the FastAPI event loop is not blocked;
  - the fallback reason is explicit in ``fallback_reason``.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, timedelta
from typing import Optional
from uuid import UUID

import pandas as pd
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.services.forecasting.baseline_provider import baseline_from_series
from app.services.forecasting.data_builder import fetch_daily_demand
from app.services.forecasting.provider import ForecastProvider
from app.services.forecasting.quality import assess_quality
from app.services.forecasting.schemas import FallbackReason, ForecastPrediction, ForecastResult
from app.utils.saudi_holidays import SAUDI_HOLIDAYS_DF
from app.utils.timezone import now_utc

try:
    from prophet import Prophet
    PROPHET_AVAILABLE = True
except ImportError:  # pragma: no cover - install path
    PROPHET_AVAILABLE = False

logger = logging.getLogger("forecasting.prophet")

WEEKDAY_NAMES = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


class ProphetProvider(ForecastProvider):
    provider_name = "prophet"
    model_version = "prophet_v1_ksa"

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
                "Prophet skipped (quality=%s) business=%s item=%s",
                quality.reason, business_id, item_id,
            )
            return baseline_from_series(
                series,
                horizon_days=horizon_days,
                provider=self,
                fallback_reason=quality.reason,
            )

        if not PROPHET_AVAILABLE:
            return baseline_from_series(
                series,
                horizon_days=horizon_days,
                provider=self,
                fallback_reason=FallbackReason.PROPHET_FAILED.value,
            )

        try:
            # Prophet fit is CPU-bound; keep the event loop responsive.
            return await asyncio.to_thread(
                self._fit_and_predict, series, horizon_days
            )
        except Exception:
            logger.exception(
                "Prophet fit failed business=%s item=%s -> baseline fallback",
                business_id, item_id,
            )
            return baseline_from_series(
                series,
                horizon_days=horizon_days,
                provider=self,
                fallback_reason=FallbackReason.PROPHET_FAILED.value,
            )

    def _fit_and_predict(self, series, horizon_days: int) -> ForecastResult:
        settings = get_settings()
        daily = pd.DataFrame(
            [{"ds": p.ds, "y": p.y} for p in series.points],
            columns=["ds", "y"],
        )
        daily["ds"] = pd.to_datetime(daily["ds"])
        daily = daily.sort_values("ds").reset_index(drop=True)

        p97 = daily["y"].quantile(0.97)
        daily["y"] = daily["y"].clip(upper=p97)

        model = Prophet(
            yearly_seasonality=len(daily) > 180,
            weekly_seasonality=True,
            daily_seasonality=False,
            seasonality_mode="multiplicative",
            changepoint_prior_scale=0.05,
            seasonality_prior_scale=10.0,
            holidays=SAUDI_HOLIDAYS_DF,
            interval_width=0.80,
        )
        model.add_seasonality(name="monthly", period=30.5, fourier_order=5)
        model.fit(daily)

        future = model.make_future_dataframe(periods=horizon_days)
        forecast = model.predict(future)
        future_rows = forecast[forecast["ds"] > daily["ds"].max()].head(horizon_days)

        predictions = [
            ForecastPrediction(
                ds=row["ds"].date(),
                predicted_qty=max(0.0, round(float(row["yhat"]), 2)),
                lower_bound=max(0.0, round(float(row["yhat_lower"]), 2)),
                upper_bound=max(0.0, round(float(row["yhat_upper"]), 2)),
            )
            for _, row in future_rows.iterrows()
        ]

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
            interval_type="prophet_interval",
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