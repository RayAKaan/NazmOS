"""Canonical forecast retrieval for consumers.

No consumer (nazm_planner, agents, tools, routers) should query
``forecast_cache`` directly. This is the single entry point: it serves the
freshest valid cached forecast, or generates (and caches) a fresh one via a
:class:`ForecastProvider` when needed.
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.forecasting.cache import read_forecast, write_forecast
from app.services.forecasting.provider import ForecastProvider
from app.services.forecasting.prophet_provider import ProphetProvider


async def get_forecast(
    db: AsyncSession,
    business_id: str | UUID,
    item_id: str | UUID,
    horizon_days: int = 7,
    provider: Optional[ForecastProvider] = None,
    tz_name: Optional[str] = None,
    ttl_hours: Optional[int] = None,
) -> dict:
    """Return a forecast dict for one item (cache-first, generate-on-miss).

    Shape (legacy-compatible so existing consumers keep working):
      forecast_7d, forecast_30d, weekly_pattern, trend_direction,
      trend_strength, model_version, provider, interval_type,
      fallback_reason, generated_at, from_cache
    """
    cached = await read_forecast(db, business_id, item_id)
    if cached:
        return cached

    provider = provider or ProphetProvider()
    result = await provider.forecast(
        db,
        business_id,
        item_id,
        horizon_days=max(7, horizon_days),
        tz_name=tz_name,
    )
    await write_forecast(db, result, ttl_hours=ttl_hours)

    legacy = result.as_legacy_dict()
    legacy.update(
        {
            "from_cache": False,
            "item_id": str(item_id),
            "expires_at": None,
        }
    )
    return legacy


async def get_forecast_day_demand(
    db: AsyncSession,
    business_id: str | UUID,
    item_id: str | UUID,
    provider: Optional[ForecastProvider] = None,
    tz_name: Optional[str] = None,
) -> float:
    """Daily demand for the next day (used by restock/procurement planning).

    Returns the first day of the 7-day forecast if available, else ``1.0``.
    The ``1.0`` floor mirrors the legacy NazmPlanner behaviour so decisions
    never divide by zero.
    """
    forecast = await get_forecast(
        db, business_id, item_id, horizon_days=7, provider=provider, tz_name=tz_name
    )
    try:
        return max(float(forecast["forecast_7d"][0]["predicted_qty"]), 0.0)
    except (KeyError, IndexError, TypeError, ValueError):
        return 1.0