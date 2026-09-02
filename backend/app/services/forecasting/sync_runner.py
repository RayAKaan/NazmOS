"""Sync facade for the async forecasting pipeline.

Celery forecast tasks execute inside sync worker processes (`get_sync_session`).
This module runs the async ``ForecastProvider`` + safe cache writer in a
dedicated event loop so the Celery path produces exactly the same forecasts as
the HTTP path.
"""
from __future__ import annotations

import asyncio
from typing import Optional
from uuid import UUID

from app.database.connection import async_session_scope
from app.services.forecasting.cache import write_forecast
from app.services.forecasting.provider import ForecastProvider
from app.services.forecasting.schemas import ForecastResult


def run_provider_forecast_sync(
    provider: ForecastProvider,
    business_id: str | UUID,
    item_id: str | UUID,
    horizon_days: int = 30,
    tz_name: Optional[str] = None,
    ttl_hours: Optional[int] = None,
) -> dict:
    """Run one provider forecast + cache persist synchronously.

    Returns the legacy-shaped forecast dict (via ``as_legacy_dict``), or an
    empty dict on failure (callers keep Celery batches isolated).
    """

    async def _run() -> Optional[ForecastResult]:
        async with async_session_scope() as session:
            result = await provider.forecast(
                session,
                business_id,
                item_id,
                horizon_days=horizon_days,
                tz_name=tz_name,
            )
            await write_forecast(session, result, ttl_hours=ttl_hours)
            return result

    try:
        result = asyncio.run(_run())
    except Exception:
        import logging

        logging.getLogger("forecasting.sync_runner").exception(
            "Sync provider forecast failed business=%s item=%s", business_id, item_id
        )
        return {}

    if result is None:
        return {}
    legacy = result.as_legacy_dict()
    legacy["item_id"] = str(item_id)
    return legacy


def forecast_batch_sync(
    provider: ForecastProvider,
    pairs: list[tuple[str, str]],
    horizon_days: int = 30,
) -> tuple[int, int, int]:
    """Run a batch of (item_id, business_id) forecasts synchronously.

    Returns ``(completed, failed, no_data)``. Per-item isolation means one bad
    item never aborts the batch.
    """
    completed = failed = no_data = 0
    for item_id, business_id in pairs:
        try:
            legacy = run_provider_forecast_sync(
                provider, business_id, item_id, horizon_days=horizon_days
            )
        except Exception:
            completed, failed = completed, failed + 1
            continue
        if not legacy:
            failed += 1
        elif legacy.get("fallback_reason") == "no_transactions":
            no_data += 1
        else:
            completed += 1
    return completed, failed, no_data