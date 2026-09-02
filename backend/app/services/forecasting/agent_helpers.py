"""Shared helpers so agents stop re-inventing demand forecasts.

Agents identify candidate items with their own fast SQL scans, but the demand
signal that drives ``days_of_supply`` / recommended quantities comes from the
canonical forecast cache (written by the forecasting pipeline). ``0.0`` is
never treated as a real daily demand — it maps to a zero/unknown signal.
"""
from __future__ import annotations

INF = float("inf")


def forecast_daily_demand(forecast: dict | None, horizon_days: int = 7) -> float:
    """Average predicted daily demand from the canonical forecast dict.

    Returns ``0.0`` when no usable forecast exists so callers can decide
    whether to fall back to their own velocity surrogate.
    """
    if not forecast:
        return 0.0
    series = forecast.get("forecast_7d") or forecast.get("forecast_30d") or []
    if not series:
        return 0.0
    values = [float(p.get("predicted_qty") or 0.0) for p in series[:horizon_days]]
    if not values:
        return 0.0
    return sum(values) / len(values)


def days_of_supply(stock: float, daily_demand: float) -> float:
    if daily_demand <= 0:
        return INF
    return stock / daily_demand