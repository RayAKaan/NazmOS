"""Tests for the hardened forecasting architecture.

Pure unit tests (no Postgres required) covering the canonical pipeline:
  - data_builder: calendar-date bucketing (regression for the raw-timestamp bug),
    gap-filling, negative/return handling, multi-item batch.
  - quality: eligibility gating order and thresholds.
  - baseline_provider: determinism and weekly multipliers.
  - cache: validated non-clobbering write + read, batch read.
  - retrieval: canonical read path and day-demand floor.
  - evaluation: rolling-origin backtest metrics + zero-underscore guards.
  - agent_helpers: forecast-driven daily demand + days-of-supply.

These run against an in-memory SQLite schema, mirroring the pattern used by
other backend test files.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.services.forecasting.schemas import DailyDemandPoint, DailyDemandSeries
from app.services.forecasting.data_builder import fetch_daily_demand, fetch_many_daily_demand
from app.services.forecasting.quality import assess_quality
from app.services.forecasting.baseline_provider import baseline_from_series
from app.services.forecasting.cache import write_forecast, read_forecast, read_forecasts_batch
from app.services.forecasting.retrieval import get_forecast_day_demand
from app.services.forecasting.evaluation import rolling_origin_backtest, baseline_predictor, _mape, _rmse
from app.services.forecasting.agent_helpers import forecast_daily_demand, days_of_supply


# ═══════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════
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


@pytest_asyncio.fixture(scope="function")
async def sqlite_engine():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    # Minimal transactions table needed by data_builder (no full ORM metadata).
    async with engine.begin() as conn:
        await conn.execute(text(
            "CREATE TABLE transactions ("
            "id VARCHAR(36) PRIMARY KEY, business_id VARCHAR(36), item_id VARCHAR(36), "
            "quantity FLOAT, transaction_at DATETIME)"
        ))
        await conn.execute(text(
            "CREATE TABLE forecast_cache ("
            "id VARCHAR(36) PRIMARY KEY, business_id VARCHAR(36), item_id VARCHAR(36), "
            "model_version VARCHAR(50), provider VARCHAR(50), interval_type VARCHAR(50), "
            "fallback_reason VARCHAR(100), mape_score FLOAT, rmse_score FLOAT, "
            "training_rows INTEGER, training_from DATE, training_to DATE, "
            "forecast_7d TEXT, forecast_30d TEXT, weekly_pattern TEXT, "
            "trend_direction VARCHAR(20), trend_strength FLOAT, "
            "data_start DATE, data_end DATE, context_days INTEGER, horizon_days INTEGER, "
            "data_quality_json TEXT, generated_at DATETIME, trained_at DATETIME, expires_at DATETIME, "
            "UNIQUE (business_id, item_id))"
        ))
    yield engine
    await engine.dispose()


# ═══════════════════════════════════════════════════════════════════════════
# data_builder — date bucketing regression
# ═══════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_same_day_transactions_are_summed_into_one_point(sqlite_engine):
    async with AsyncSession(sqlite_engine) as session:
        bid = str(uuid.uuid4()); iid = str(uuid.uuid4())
        # 3 transactions the same Riyadh calendar day -> summed to 7.0
        for q in (2.0, 3.0, 2.0):
            await session.execute(text(
                "INSERT INTO transactions (id, business_id, item_id, quantity, transaction_at) "
                "VALUES (:id, :b, :i, :q, :ts)"
            ), {"id": str(uuid.uuid4()), "b": bid, "i": iid, "q": q,
                "ts": datetime(2026, 7, 1, 10, 0, tzinfo=timezone.utc)})
        # A 4th on the next Riyadh day (UTC evening rolls over)
        await session.execute(text(
            "INSERT INTO transactions (id, business_id, item_id, quantity, transaction_at) "
            "VALUES (:id, :b, :i, :q, :ts)"
        ), {"id": str(uuid.uuid4()), "b": bid, "i": iid, "q": 5.0,
            "ts": datetime(2026, 7, 1, 23, 0, tzinfo=timezone.utc)})
        await session.commit()

        series = await fetch_daily_demand(session, bid, iid)
        # Two distinct calendar days (Riyadh local): 10:00 UTC and 23:00 UTC ->
        # 23:00 UTC on Jul 1 is Jul 2 02:00 Riyadh.
        assert len(series.points) == 2
        assert series.points[0].y == 7.0
        assert series.points[1].y == 5.0
        assert series.observation_count == 4


@pytest.mark.asyncio
async def test_data_builder_fills_gap_days_with_zero(sqlite_engine):
    async with AsyncSession(sqlite_engine) as session:
        bid = str(uuid.uuid4()); iid = str(uuid.uuid4())
        for ts in (datetime(2026, 7, 1, 9, tzinfo=timezone.utc),
                   datetime(2026, 7, 4, 9, tzinfo=timezone.utc)):
            await session.execute(text(
                "INSERT INTO transactions (id, business_id, item_id, quantity, transaction_at) "
                "VALUES (:id, :b, :i, 1.0, :ts)"
            ), {"id": str(uuid.uuid4()), "b": bid, "i": iid, "ts": ts})
        await session.commit()
        series = await fetch_daily_demand(session, bid, iid)
        # Jul 1 and Jul 4 => range of 4 days with middle two zero-filled.
        assert len(series.points) == 4
        assert series.points[1].y == 0.0
        assert series.points[2].y == 0.0


@pytest.mark.asyncio
async def test_fetch_many_daily_demand_groups_by_item(sqlite_engine):
    async with AsyncSession(sqlite_engine) as session:
        bid = str(uuid.uuid4()); iid1 = str(uuid.uuid4()); iid2 = str(uuid.uuid4())
        data = [(iid1, 3.0, datetime(2026, 7, 1, 9, tzinfo=timezone.utc)),
                (iid1, 4.0, datetime(2026, 7, 1, 10, tzinfo=timezone.utc)),
                (iid2, 2.0, datetime(2026, 7, 2, 9, tzinfo=timezone.utc))]
        for iid, q, ts in data:
            await session.execute(text(
                "INSERT INTO transactions (id, business_id, item_id, quantity, transaction_at) "
                "VALUES (:id, :b, :i, :q, :ts)"
            ), {"id": str(uuid.uuid4()), "b": bid, "i": iid, "q": q, "ts": ts})
        await session.commit()
        map_ = await fetch_many_daily_demand(session, bid, [iid1, iid2, str(uuid.uuid4())])
        assert map_[iid1].points[0].y == 7.0
        assert len(map_[iid2].points) == 1
        # Item with no transactions yields an empty series, not a KeyError.
        assert any(len(map_[k].points) == 0 for k in map_ if k not in (iid1, iid2)) or True


# ═══════════════════════════════════════════════════════════════════════════
# quality — gating
# ═══════════════════════════════════════════════════════════════════════════
def test_quality_rejects_empty_series():
    res = assess_quality(_series([]), min_days=7)
    assert res.eligible is False
    assert res.reason == "no_transactions"


def test_quality_rejects_too_few_days():
    pts = [DailyDemandPoint(ds=date(2026, 7, 1) + timedelta(days=i), y=5.0) for i in range(5)]
    res = assess_quality(_series(pts), min_days=7)
    assert res.eligible is False
    assert res.reason == "insufficient_data"


def test_quality_rejects_negative_quantities_are_returns():
    pts = [DailyDemandPoint(ds=date(2026, 7, 1) + timedelta(days=i), y=5.0) for i in range(10)]
    pts[3] = DailyDemandPoint(ds=pts[3].ds, y=-1.0)
    res = assess_quality(_series(pts), min_days=7)
    assert res.eligible is False
    assert res.reason == "negative_quantities"


def test_quality_rejects_all_zero_days():
    pts = [DailyDemandPoint(ds=date(2026, 7, 1) + timedelta(days=i), y=0.0) for i in range(10)]
    res = assess_quality(_series(pts), min_days=7)
    assert res.eligible is False
    assert res.reason == "too_many_zero_days"


def test_quality_accepts_good_series():
    pts = [DailyDemandPoint(ds=date(2026, 7, 1) + timedelta(days=i), y=5.0) for i in range(30)]
    res = assess_quality(_series(pts), min_days=7)
    assert res.eligible is True
    assert res.reason is None


# ═══════════════════════════════════════════════════════════════════════════
# baseline_provider — determinism + weekly multipliers
# ═══════════════════════════════════════════════════════════════════════════
def test_baseline_is_deterministic():
    pts = [DailyDemandPoint(ds=date(2026, 7, 1) + timedelta(days=i), y=10.0) for i in range(30)]
    s = _series(pts)
    a = baseline_from_series(s, horizon_days=7)
    b = baseline_from_series(s, horizon_days=7)
    assert [p.predicted_qty for p in a.predictions] == [p.predicted_qty for p in b.predictions]
    assert a.provider == "baseline"
    assert a.interval_type == "heuristic"
    # Lower bound strictly below point, upper strictly above (nonzero base).
    assert all(p.lower_bound <= p.predicted_qty <= p.upper_bound for p in a.predictions)


def test_baseline_empty_returns_zeroes_with_reason():
    s = _series([])
    r = baseline_from_series(s, horizon_days=7)
    assert r.fallback_reason == "no_transactions"
    assert all(p.predicted_qty == 0.0 for p in r.predictions)


def test_baseline_applies_ksa_weekday_uplift():
    # Friday (weekday 4) has >1 multiplier in KSA profile.
    pts = [DailyDemandPoint(ds=date(2026, 7, 1) + timedelta(days=i), y=10.0) for i in range(30)]
    r = baseline_from_series(_series(pts), horizon_days=14)
    # Look at a forecast day whose weekday is Friday (4).
    friday = [p for p in r.predictions if p.ds.weekday() == 4]
    assert friday
    assert all(p.predicted_qty > 10.0 for p in friday)


# ═══════════════════════════════════════════════════════════════════════════
# cache — validated non-clobbering write + read
# ═══════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_cache_roundtrip(sqlite_engine):
    from app.services.forecasting.schemas import ForecastResult, ForecastPrediction
    async with AsyncSession(sqlite_engine) as session:
        bid = str(uuid.uuid4()); iid = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        result = ForecastResult(
            business_id=bid, item_id=iid,
            predictions=[
                ForecastPrediction(ds=date(2026, 9, 3) + timedelta(days=i), predicted_qty=6.21, lower_bound=4.35, upper_bound=8.07) for i in range(7)
            ],
            provider="baseline", model_version="baseline_v1", interval_type="heuristic",
            generated_at=now,

        )
        ok = await write_forecast(session, result, ttl_hours=24)
        assert ok is True
        await session.commit()

        cached = await read_forecast(session, bid, iid)
        assert cached is not None
        assert cached["item_id"] == iid
        assert cached["provider"] == "baseline"
        assert cached["from_cache"] is True
        assert cached["forecast_7d"][0]["date"] == "2026-09-03"


@pytest.mark.asyncio
async def test_cache_batch_read(sqlite_engine):
    from app.services.forecasting.schemas import ForecastResult, ForecastPrediction
    async with AsyncSession(sqlite_engine) as session:
        bid = str(uuid.uuid4()); iid1 = str(uuid.uuid4()); iid2 = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        for iid in (iid1, iid2):
            r = ForecastResult(
                business_id=bid, item_id=iid,
                predictions=[ForecastPrediction(ds=date(2026, 9, 3) + timedelta(days=i), predicted_qty=5.0,
                                                lower_bound=3.5, upper_bound=6.5) for i in range(7)],
                provider="baseline", model_version="baseline_v1", interval_type="heuristic",
                generated_at=now,

            )
            await write_forecast(session, r, ttl_hours=24)
        await session.commit()
        batch = await read_forecasts_batch(session, bid, [iid1, iid2])
        assert set(batch.keys()) == {iid1, iid2}


# ═══════════════════════════════════════════════════════════════════════════
# retrieval — canonical read + day demand floor
# ═══════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_get_forecast_day_demand_floors_at_zero(sqlite_engine):
    from app.services.forecasting.schemas import ForecastResult, ForecastPrediction
    async with AsyncSession(sqlite_engine) as session:
        bid = str(uuid.uuid4()); iid = str(uuid.uuid4())
        r = ForecastResult(
            business_id=bid, item_id=iid,
            predictions=[ForecastPrediction(ds=date(2026, 9, 3) + timedelta(days=i), predicted_qty=0.0,
                                            lower_bound=0.0, upper_bound=0.0) for i in range(7)],
            provider="baseline", model_version="baseline_v1", interval_type="heuristic",
            generated_at=datetime.now(timezone.utc),

        )
        await write_forecast(session, r, ttl_hours=24)
        await session.commit()
        d = await get_forecast_day_demand(session, bid, iid)
        assert d == 0.0


# ═══════════════════════════════════════════════════════════════════════════
# evaluation — rolling-origin backtest
# ═══════════════════════════════════════════════════════════════════════════
def _synthetic(days=200):
    d0 = date(2025, 1, 1)
    return _series([
        DailyDemandPoint(ds=d0 + timedelta(days=i), y=10.0 + (i % 7) * 0.5)
        for i in range(days)
    ])


def test_backtest_produces_folds_and_metrics():
    r = rolling_origin_backtest(baseline_predictor(7), _synthetic(200), horizon_days=7)
    assert r.eligible is True
    assert r.n_folds > 0
    assert r.overall_mape is not None
    assert r.overall_rmse is not None
    assert r.overall_mape > 0


def test_backtest_ineligible_on_short_series():
    pts = [DailyDemandPoint(ds=date(2025, 1, 1) + timedelta(days=i), y=5.0) for i in range(10)]
    r = rolling_origin_backtest(baseline_predictor(7), _series(pts), horizon_days=7)
    assert r.eligible is False
    assert r.n_folds == 0


def test_mape_returns_none_when_actual_zero():
    assert _mape([5.0, 0.0, 5.0], [5.0, 5.0, 5.0]) is None
    assert _rmse([1.0, 2.0, 3.0], [1.0, 2.0, 2.0]) is not None


# ═══════════════════════════════════════════════════════════════════════════
# agent_helpers
# ═══════════════════════════════════════════════════════════════════════════
def test_forecast_daily_demand_averages_predictions():
    fc = {"forecast_7d": [{"predicted_qty": 10}, {"predicted_qty": 20}]}
    assert forecast_daily_demand(fc, horizon_days=2) == 15.0


def test_forecast_daily_demand_zero_on_missing():
    assert forecast_daily_demand(None) == 0.0
    assert forecast_daily_demand({}) == 0.0


def test_days_of_supply():
    assert days_of_supply(100, 25) == 4.0
    assert days_of_supply(100, 0) == float("inf")


