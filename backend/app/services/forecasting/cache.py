"""Safe forecast-cache read/write.

The cache is the single persistence point for forecasts. Two guarantees:

1. **Everything written is validated.** ``write_forecast`` rejects NaN/inf,
   inverted bounds, wrong horizons and non-ascending dates BEFORE touching the DB.
2. **A bad forecast never clobbers a good one.** If validation fails, the
   previous row is left untouched and the failure is logged.

Serialization is always ``json.dumps`` (the Celery task previously used
``str()``, producing different representations than the router).
"""
from __future__ import annotations

import json
import logging
import math
from datetime import timedelta
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.services.forecasting.schemas import ForecastResult
from app.utils.timezone import now_utc

logger = logging.getLogger("forecasting.cache")


def _to_iso_or_none(value) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    try:
        return value.isoformat()
    except AttributeError:
        return str(value)


def _is_finite(value: float) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def validate_result(result: ForecastResult) -> Optional[str]:
    """Return an error reason if the forecast is unsafe to persist, else None."""
    predictions = result.predictions
    if not predictions:
        return "no_predictions"
    if len(predictions) != result.horizon_days:
        return f"horizon_mismatch_expect_{result.horizon_days}_got_{len(predictions)}"

    prev_date = None
    for p in predictions:
        if not _is_finite(p.predicted_qty) or not _is_finite(p.lower_bound) or not _is_finite(p.upper_bound):
            return "non_finite_values"
        if p.lower_bound > p.predicted_qty or p.predicted_qty > p.upper_bound:
            return "inverted_bounds"
        if prev_date is not None and p.ds <= prev_date:
            return "non_ascending_dates"
        prev_date = p.ds

    if not isinstance(result.weekly_pattern, dict):
        return "invalid_weekly_pattern"
    if not isinstance(result.trend_direction, str) or not result.trend_direction:
        return "invalid_trend_direction"
    return None


def _to_json_variants(result: ForecastResult) -> tuple[str, str, str]:
    """Render forecast_7d / forecast_30d / weekly_pattern as consistent JSON."""
    legacy_7d = result.forecast_7d
    legacy_30d = result.forecast_30d
    weekly = result.weekly_pattern
    return (
        json.dumps(legacy_7d),
        json.dumps(legacy_30d),
        json.dumps(weekly),
    )


async def write_forecast(
    db: AsyncSession,
    result: ForecastResult,
    ttl_hours: Optional[int] = None,
) -> bool:
    """Persist ``result`` to ``forecast_cache``, never overwriting a good row
    with an invalid one. Returns True if the row was (re)written."""
    error = validate_result(result)
    if error:
        logger.error(
            "Rejected invalid forecast business=%s item=%s reason=%s (previous row preserved)",
            result.business_id, result.item_id, error,
        )
        return False

    settings = get_settings()
    ttl_hours = ttl_hours or settings.FORECAST_CACHE_TTL_HOURS
    expires_at = now_utc() + timedelta(hours=ttl_hours)

    f7, f30, wp = _to_json_variants(result)

    await db.execute(
        text(
            """
            INSERT INTO forecast_cache
                (id, business_id, item_id, model_version, training_rows,
                 training_from, training_to, forecast_7d, forecast_30d,
                 weekly_pattern, trend_direction, trend_strength,
                 trained_at, expires_at,
                 provider, data_start, data_end, context_days, horizon_days,
                 interval_type, fallback_reason, data_quality_json, generated_at)
            VALUES
                (:id, :business_id, :item_id, :model_version, :training_rows,
                 :training_from, :training_to, :forecast_7d, :forecast_30d,
                 :weekly_pattern, :trend_direction, :trend_strength,
                 :trained_at, :expires_at,
                 :provider, :data_start, :data_end, :context_days, :horizon_days,
                 :interval_type, :fallback_reason, :data_quality_json, :generated_at)
            ON CONFLICT (business_id, item_id) DO UPDATE SET
                 model_version = EXCLUDED.model_version,
                 training_rows = EXCLUDED.training_rows,
                 training_from = EXCLUDED.training_from,
                 training_to = EXCLUDED.training_to,
                 forecast_7d = EXCLUDED.forecast_7d,
                 forecast_30d = EXCLUDED.forecast_30d,
                 weekly_pattern = EXCLUDED.weekly_pattern,
                 trend_direction = EXCLUDED.trend_direction,
                 trend_strength = EXCLUDED.trend_strength,
                 trained_at = EXCLUDED.trained_at,
                 expires_at = EXCLUDED.expires_at,
                 provider = EXCLUDED.provider,
                 data_start = EXCLUDED.data_start,
                 data_end = EXCLUDED.data_end,
                 context_days = EXCLUDED.context_days,
                 horizon_days = EXCLUDED.horizon_days,
                 interval_type = EXCLUDED.interval_type,
                 fallback_reason = EXCLUDED.fallback_reason,
                 data_quality_json = EXCLUDED.data_quality_json,
                 generated_at = EXCLUDED.generated_at
            """
        ),
        {
            "id": str(uuid4()),
            "business_id": str(result.business_id),
            "item_id": str(result.item_id),
            "model_version": result.model_version,
            "training_rows": result.context_days,
            "training_from": result.data_start,
            "training_to": result.data_end,
            "forecast_7d": f7,
            "forecast_30d": f30,
            "weekly_pattern": wp,
            "trend_direction": result.trend_direction,
            "trend_strength": result.trend_strength,
            "trained_at": now_utc(),
            "expires_at": expires_at,
            "provider": result.provider,
            "data_start": result.data_start,
            "data_end": result.data_end,
            "context_days": result.context_days,
            "horizon_days": result.horizon_days,
            "interval_type": result.interval_type,
            "fallback_reason": result.fallback_reason,
            "data_quality_json": json.dumps({
                "observation_count": result.context_days,
                "fallback_reason": result.fallback_reason,
                "interval_type": result.interval_type,
            }),
            "generated_at": result.generated_at,
        },
    )
    await db.commit()
    return True


def _decode_json(value) -> object:
    if value is None:
        return None
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (ValueError, TypeError):
            return None
    return value


def parse_forecast_row(row) -> Optional[dict]:
    """Turn a raw ``forecast_cache`` row into the canonical forecast dict.

    Returns None when the stored JSON is unreadable/invalid so callers never
    act on corrupt rows.
    """
    if row is None:
        return None
    item_id = getattr(row, "item_id", None)

    try:
        forecast_7d = _decode_json(row.forecast_7d) or []
        forecast_30d = _decode_json(row.forecast_30d) or []
        weekly_pattern = _decode_json(row.weekly_pattern) or {}
    except Exception:
        logger.warning("Corrupt forecast row item=%s", item_id)
        return None

    if not forecast_7d or not isinstance(forecast_7d, list):
        return None

    return {
        "item_id": str(item_id) if item_id is not None else None,
        "business_id": str(getattr(row, "business_id", "")) if getattr(row, "business_id", None) else None,
        "model_version": getattr(row, "model_version", None),
        "provider": getattr(row, "provider", None),
        "interval_type": getattr(row, "interval_type", None),
        "fallback_reason": getattr(row, "fallback_reason", None),
        "forecast_7d": forecast_7d,
        "forecast_30d": forecast_30d,
        "weekly_pattern": weekly_pattern,
        "trend_direction": getattr(row, "trend_direction", None),
        "trend_strength": float(row.trend_strength) if getattr(row, "trend_strength", None) else 0.0,
        "trained_at": _to_iso_or_none(getattr(row, "trained_at", None)),
        "expires_at": _to_iso_or_none(getattr(row, "expires_at", None)),
        "generated_at": _to_iso_or_none(getattr(row, "generated_at", None)),
        "data_quality_json": getattr(row, "data_quality_json", None),
        "mape_score": float(row.mape_score) if getattr(row, "mape_score", None) else None,
        "rmse_score": float(row.rmse_score) if getattr(row, "rmse_score", None) else None,
        "from_cache": True,
    }


async def read_forecast(
    db: AsyncSession,
    business_id: str | UUID,
    item_id: str | UUID,
) -> Optional[dict]:
    """Read the freshest valid forecast for an item from the cache.

    Returns the legacy-shaped dict (``forecast_7d`` / ``forecast_30d`` /
    ``weekly_pattern`` / trend / provenance) or None when there is none.
    Callers should use :func:`app.services.forecasting.retrieval.get_forecast`
    instead of querying ``forecast_cache`` directly.
    """
    settings = get_settings()
    result = await db.execute(
        text(
            "SELECT * FROM forecast_cache "
            "WHERE item_id = :item_id AND business_id = :business_id "
            "AND expires_at > :now ORDER BY trained_at DESC LIMIT 1"
        ),
        {
            "item_id": str(item_id),
            "business_id": str(business_id),
            "now": now_utc(),
        },
    )
    row = result.fetchone()
    if not row:
        return None

    return parse_forecast_row(row)


async def read_forecasts_batch(
    db: AsyncSession,
    business_id: str | UUID,
    item_ids: list[str | UUID],
) -> dict[str, dict]:
    """Read the freshest valid cached forecast for each of several items.

    Cache-only: never triggers generation. Consumers running bulk scans (agents,
    planner) use this instead of querying ``forecast_cache`` directly.
    """
    if not item_ids:
        return {}
    settings = get_settings()
    from sqlalchemy import bindparam

    result = await db.execute(
        text(
            "SELECT * FROM forecast_cache "
            "WHERE business_id = :business_id AND item_id IN :item_ids "
            "AND expires_at > :now ORDER BY trained_at DESC"
        ).bindparams(bindparam("item_ids", expanding=True)),
        {
            "business_id": str(business_id),
            "item_ids": [str(i) for i in item_ids],
            "now": now_utc(),
        },
    )
    forecasts: dict[str, dict] = {}
    for row in result.fetchall():
        key = str(row.item_id)
        if key in forecasts:
            continue  # first row is the most recently trained; keep it
        parsed = parse_forecast_row(row)
        if parsed:
            forecasts[key] = parsed
    return forecasts