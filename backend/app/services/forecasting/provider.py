"""ForecastProvider abstraction.

Every forecasting path (router, Celery task, intelligence API, tools) goes
through :class:`ForecastProvider` so the whole product agrees on:
  - the canonical daily series (data_builder),
  - the quality gate (quality),
  - the interval semantics and provenance.

Producers that only need a deterministic forecast use :class:`BaselineProvider`;
producers that can pay Prophets cost use :class:`ProphetProvider`, which falls
back to the baseline when data is poor.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.forecasting.schemas import ForecastResult


class ForecastProvider(ABC):
    provider_name: str = "base"
    model_version: str = "base_v1"

    @abstractmethod
    async def forecast(
        self,
        db: AsyncSession,
        business_id: str | UUID,
        item_id: str | UUID,
        horizon_days: int = 30,
        context_days: int = 365,
        tz_name: Optional[str] = None,
    ) -> ForecastResult:
        """Produce a forecast for one item of one business.

        ``horizon_days`` is the number of future daily steps; ``context_days``
        is how much transaction history (in days) to load. ``tz_name`` is the
        business's IANA timezone (falls back to KSA).
        """
        raise NotImplementedError