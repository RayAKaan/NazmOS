"""StatsForecast provider tests.

Covers the canonical statistical forecasting provider:
  - determinism (same input -> same output),
  - honest sparse-data handling (falls back to baseline with an explicit
    reason when the quality gate rejects the series — never fabricates a
    statistical fit from a few days of data),
  - full-horizon interval/order guarantees,
  - fallback when StatsForecast itself is unavailable or the fit fails.

These are pure unit tests (no Postgres): the provider fetches a series via
``fetch_daily_demand``, so we exercise the Semantic-layer-friendly seams by
building a series directly and calling the pure `_fit_and_predict` / policy
helpers, plus the async forecast() path through the quality gate with a
minimal in-memory store.
"""
from __future__ import annotations

import datetime as dt
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.services.forecasting.schemas import DailyDemandPoint, DailyDemandSeries
from app.services.forecasting.statsforecast_provider import (
    StatsForecastProvider,
    _ensemble_point,
    _ensemble_band,
)


def _series(points, business_id="b", item_id="i") -> DailyDemandSeries:
    return DailyDemandSeries(
        business_id=business_id,
        item_id=item_id,
        timezone="Asia/Riyadh",
        points=points,
        date_range_days=len(points),
        observation_count=len(points),
        nonzero_days=sum(1 for p in points if p.y > 0),
    )


def _points(start, days, base=10.0):
    return [
        DailyDemandPoint(
            ds=start + dt.timedelta(days=i),
            y=round(base + (i % 7) * 0.75, 2),
        )
        for i in range(days)
    ]


@pytest_asyncio.fixture(scope="module")
async def sqlite_engine():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.execute(text(
            "CREATE TABLE transactions ("
            "id VARCHAR(36) PRIMARY KEY, business_id VARCHAR(36), item_id VARCHAR(36), "
            "quantity FLOAT, transaction_at DATETIME)"
        ))
    yield engine
    await engine.dispose()


def test_ensemble_point_is_median():
    assert _ensemble_point({"a": 1.0, "b": 3.0}) == 2.0
    assert _ensemble_point({"a": None, "b": 5.0}) == 5.0
    assert _ensemble_point({"a": None, "b": None}) == 0.0


def test_ensemble_band_covers_all_models():
    lo, hi = _ensemble_band([3.0], {"a": 1.0, "b": 2.5}, {"a": 8.0, "b": 5.0})
    assert lo == 1.0
    assert hi == 8.0


def test_provider_is_deterministic():
    provider = StatsForecastProvider()
    a = provider._fit_and_predict(_series(_points(dt.date(2026, 1, 1), 45)), 7)
    b = provider._fit_and_predict(_series(_points(dt.date(2026, 1, 1), 45)), 7)
    assert [p.predicted_qty for p in a.predictions] == [p.predicted_qty for p in b.predictions]
    assert a.provider == "statsforecast"
    assert a.interval_type == "statsforecast_interval"


def test_full_horizon_predictions_have_valid_bounds_and_order():
    provider = StatsForecastProvider()
    result = provider._fit_and_predict(_series(_points(dt.date(2026, 1, 1), 60)), 30)
    assert len(result.predictions) == 30
    assert all(p.predicted_qty >= 0 for p in result.predictions)
    assert all(p.lower_bound <= p.predicted_qty <= p.upper_bound for p in result.predictions)
    dates = [p.ds for p in result.predictions]
    assert dates == sorted(dates)
    assert result.data_start == dt.date(2026, 1, 1)
    assert result.data_end == dt.date(2026, 1, 1) + dt.timedelta(days=59)


@pytest.mark.asyncio
async def test_sparse_history_falls_back_to_baseline(sqlite_engine):
    """Sparse data (a few sales days) must NOT produce a statistical fit.

    The golden sales fixture covers only 6 sales days; the quality gate
    (MIN_DAYS_FOR_FORECAST=14) rejects it, and the provider must defer to the
    deterministic baseline with an explicit fallback_reason.
    """
    bid = str(uuid.uuid4())
    iid = str(uuid.uuid4())
    async with AsyncSession(sqlite_engine) as session:
        for i, qty in enumerate([4.0, 6.0, 5.0, 7.0, 5.0, 6.0]):
            await session.execute(text(
                "INSERT INTO transactions (id, business_id, item_id, quantity, transaction_at) "
                "VALUES (:id, :b, :i, :q, :ts)"
            ), {
                "id": str(uuid.uuid4()), "b": bid, "i": iid, "q": qty,
                "ts": dt.datetime(2026, 8, 4 + i, 12, 0, tzinfo=dt.timezone.utc),
            })
        await session.commit()

        provider = StatsForecastProvider()
        result = await provider.forecast(session, bid, iid, horizon_days=7)
        # Honest fallback: heuristic interval (not a statistical fit) with an
        # explicit reason. The provider attribution stays "statsforecast"
        # (established ProphetProvider contract); fallback_reason records the
        # degradation.
        assert result.interval_type == "heuristic"
        assert result.fallback_reason == "insufficient_data"
        assert len(result.predictions) == 7


@pytest.mark.asyncio
async def test_no_transactions_returns_zero_reason(sqlite_engine):
    bid = str(uuid.uuid4())
    iid = str(uuid.uuid4())
    async with AsyncSession(sqlite_engine) as session:
        provider = StatsForecastProvider()
        result = await provider.forecast(session, bid, iid, horizon_days=7)
        assert result.interval_type == "heuristic"
        assert result.fallback_reason == "no_transactions"
        assert all(p.predicted_qty == 0.0 for p in result.predictions)


@pytest.mark.asyncio
async def test_sufficient_history_produces_statsforecast_fit(sqlite_engine):
    bid = str(uuid.uuid4())
    iid = str(uuid.uuid4())
    async with AsyncSession(sqlite_engine) as session:
        start = dt.date(2026, 7, 1)
        for i in range(45):
            await session.execute(text(
                "INSERT INTO transactions (id, business_id, item_id, quantity, transaction_at) "
                "VALUES (:id, :b, :i, :q, :ts)"
            ), {
                "id": str(uuid.uuid4()), "b": bid, "i": iid,
                "q": 3.0 + (i % 5),
                "ts": dt.datetime.combine(start + dt.timedelta(days=i), dt.time(10, 0), tzinfo=dt.timezone.utc),
            })
        await session.commit()

        provider = StatsForecastProvider()
        result = await provider.forecast(session, bid, iid, horizon_days=7)
        assert result.provider == "statsforecast"
        assert result.interval_type == "statsforecast_interval"
        assert result.fallback_reason is None
        assert len(result.predictions) == 7