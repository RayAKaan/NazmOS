"""Forecasting architecture.

Consolidated, hardening-oriented forecasting package:

  data_builder     → canonical local-calendar-day demand series
  quality          → gating before any provider trains
  provider         → ForecastProvider abstraction
  prophet_provider → Prophet implementation (primary model)
  baseline_provider→ deterministic fallback / evaluation baseline
  cache            → validated, non-clobbering forecast cache read/write
  retrieval        → canonical read path for consumers
  evaluation       → rolling-origin backtesting and metrics
"""
from app.services.forecasting.schemas import (
    DailyDemandPoint,
    DailyDemandSeries,
    DataQualityResult,
    FallbackReason,
    ForecastPrediction,
    ForecastResult,
)
from app.services.forecasting.quality import assess_quality
from app.services.forecasting.data_builder import fetch_daily_demand, fetch_many_daily_demand
from app.services.forecasting.provider import ForecastProvider
from app.services.forecasting.baseline_provider import BaselineProvider
from app.services.forecasting.prophet_provider import ProphetProvider
from app.services.forecasting.cache import validate_result, write_forecast, read_forecast
from app.services.forecasting.retrieval import get_forecast, get_forecast_day_demand
from app.services.forecasting.evaluation import (
    BacktestResult,
    FoldResult,
    baseline_predictor,
    populate_metrics,
    rolling_origin_backtest,
)

__all__ = [
    "DailyDemandPoint",
    "DailyDemandSeries",
    "DataQualityResult",
    "FallbackReason",
    "ForecastPrediction",
    "ForecastResult",
    "ForecastProvider",
    "BaselineProvider",
    "ProphetProvider",
    "assess_quality",
    "fetch_daily_demand",
    "fetch_many_daily_demand",
    "validate_result",
    "write_forecast",
    "read_forecast",
    "get_forecast",
    "get_forecast_day_demand",
    "BacktestResult",
    "FoldResult",
    "baseline_predictor",
    "populate_metrics",
    "rolling_origin_backtest",
]