from pydantic import BaseModel, Field

from datetime import date, datetime
from enum import Enum
from typing import Optional


class DailyDemandPoint(BaseModel):
    ds: date
    y: float


class DailyDemandSeries(BaseModel):
    business_id: str
    item_id: str
    points: list[DailyDemandPoint]
    timezone: str
    date_range_days: int = 0
    observation_count: int = 0
    nonzero_days: int = 0
    total_demand: float = 0.0


class DataQualityResult(BaseModel):
    eligible: bool
    reason: Optional[str] = None
    observation_count: int = 0
    nonzero_days: int = 0
    date_range_days: int = 0
    zero_ratio: float = 1.0


class ForecastPrediction(BaseModel):
    ds: date
    predicted_qty: float
    lower_bound: float
    upper_bound: float


class ForecastResult(BaseModel):
    business_id: str
    item_id: str
    predictions: list[ForecastPrediction]
    provider: str
    model_version: str
    interval_type: str = "heuristic"  # "prophet_interval" | "heuristic"
    fallback_reason: Optional[str] = None
    generated_at: datetime
    data_start: Optional[date] = None
    data_end: Optional[date] = None
    context_days: int = 0
    horizon_days: int = 7
    weekly_pattern: dict = {}
    trend_direction: str = "stable"
    trend_strength: float = 0.0

    @property
    def forecast_7d(self) -> list[dict]:
        return self._to_legacy(self.predictions[:7])

    @property
    def forecast_30d(self) -> list[dict]:
        return self._to_legacy(self.predictions[:30])

    def _to_legacy(self, preds: list[ForecastPrediction]) -> list[dict]:
        return [
            {
                "date": p.ds.isoformat(),
                "predicted_qty": round(p.predicted_qty, 2),
                "lower": round(p.lower_bound, 2),
                "upper": round(p.upper_bound, 2),
            }
            for p in preds
        ]

    def as_legacy_dict(self) -> dict:
        """Shape consumed by routers/agents that still read ``forecast_7d``."""
        return {
            "forecast_7d": self.forecast_7d,
            "forecast_30d": self.forecast_30d,
            "weekly_pattern": self.weekly_pattern,
            "trend_direction": self.trend_direction,
            "trend_strength": self.trend_strength,
            "training_rows": self.context_days,
            "mape_score": None,
            "model_version": self.model_version,
            "provider": self.provider,
            "interval_type": self.interval_type,
            "fallback_reason": self.fallback_reason,
            "generated_at": self.generated_at.isoformat(),
        }


class FallbackReason(str, Enum):
    INSUFFICIENT_DATA = "insufficient_data"
    PROPHET_FAILED = "prophet_failed"
    NO_TRANSACTIONS = "no_transactions"