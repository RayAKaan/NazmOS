"""Canonical daily-demand data builder.

Single source of truth for turning raw transactions into a daily demand
series. Every forecasting path (router, Celery task, providers, evaluation)
consumes this so the whole system aggregates by the SAME local calendar date.

Historical bug this fixes: `forecast.py` grouped by the raw ``transaction_at``
timestamp, so multiple transactions during one day became separate rows and
Prophet never saw a true daily series. Here rows are bucketed by the business's
local calendar date in Python, which works identically on PostgreSQL and SQLite.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.utils.timezone import business_date, now_utc, resolve_timezone
from app.services.forecasting.schemas import DailyDemandPoint, DailyDemandSeries


async def fetch_daily_demand(
    db: AsyncSession,
    business_id: str,
    item_id: str,
    tz_name: Optional[str] = None,
    lookback_days: int = 365,
) -> DailyDemandSeries:
    """Build a continuous daily demand series for one item.

    - Fetches raw ``transaction_at`` / ``quantity`` rows scoped to the item;
    - Buckets each row into the business's local calendar date;
    - Sums quantities per day (returns/refunds may contribute negative values);
    - Fills missing dates between first and last observed day with ``0``.
    """
    settings = get_settings()
    tz = resolve_timezone(tz_name or settings.DEFAULT_TIMEZONE)
    since = now_utc() - timedelta(days=lookback_days)

    result = await db.execute(
        text(
            "SELECT transaction_at, quantity FROM transactions "
            "WHERE business_id = :business_id AND item_id = :item_id "
            "AND transaction_at >= :since ORDER BY transaction_at"
        ),
        {
            "business_id": str(business_id),
            "item_id": str(item_id),
            "since": since,
        },
    )
    rows = result.fetchall()

    if not rows:
        return DailyDemandSeries(
            business_id=str(business_id),
            item_id=str(item_id),
            points=[],
            timezone=tz.key,
        )

    daily: dict = {}
    for row in rows:
        local_day = business_date(row.transaction_at, tz.key)
        qty = float(row.quantity) if row.quantity is not None else 0.0
        daily[local_day] = daily.get(local_day, 0.0) + qty

    min_date = min(daily)
    max_date = max(daily)
    points: list[DailyDemandPoint] = []
    for offset in range((max_date - min_date).days + 1):
        day = min_date + timedelta(days=offset)
        points.append(DailyDemandPoint(ds=day, y=round(daily.get(day, 0.0), 4)))

    nonzero_days = sum(1 for p in points if p.y > 0)
    return DailyDemandSeries(
        business_id=str(business_id),
        item_id=str(item_id),
        points=points,
        timezone=tz.key,
        date_range_days=len(points),
        observation_count=len(rows),
        nonzero_days=nonzero_days,
        total_demand=round(sum(p.y for p in points), 4),
    )


async def fetch_many_daily_demand(
    db: AsyncSession,
    business_id: str,
    item_ids: list[str],
    tz_name: Optional[str] = None,
    lookback_days: int = 365,
) -> dict[str, DailyDemandSeries]:
    """Build daily series for several items of one business in a single query.

    Returns a map keyed by item id. Items without transactions yield an empty
    series rather than being omitted, so callers can fail fast on bad items.
    """
    from sqlalchemy import bindparam

    settings = get_settings()
    tz = resolve_timezone(tz_name or settings.DEFAULT_TIMEZONE)
    since = now_utc() - timedelta(days=lookback_days)

    result = await db.execute(
        text(
            "SELECT item_id, transaction_at, quantity FROM transactions "
            "WHERE business_id = :business_id AND item_id IN :item_ids "
            "AND transaction_at >= :since ORDER BY transaction_at"
        ).bindparams(bindparam("item_ids", expanding=True)),
        {
            "business_id": str(business_id),
            "item_ids": [str(i) for i in item_ids],
            "since": since,
        },
    )

    buckets: dict[str, dict] = {}
    tx_counts: dict[str, int] = {}
    for row in result.fetchall():
        item_key = str(row.item_id)
        item_bucket = buckets.setdefault(item_key, {})
        tx_counts[item_key] = tx_counts.get(item_key, 0) + 1
        local_day = business_date(row.transaction_at, tz.key)
        qty = float(row.quantity) if row.quantity is not None else 0.0
        item_bucket[local_day] = item_bucket.get(local_day, 0.0) + qty

    series_map: dict[str, DailyDemandSeries] = {}
    for item_id in item_ids:
        item_id = str(item_id)
        bucket = buckets.get(item_id, {})
        if not bucket:
            series_map[item_id] = DailyDemandSeries(
                business_id=str(business_id),
                item_id=item_id,
                points=[],
                timezone=tz.key,
            )
            continue
        min_date = min(bucket)
        max_date = max(bucket)
        points = [
            DailyDemandPoint(
                ds=min_date + timedelta(days=offset),
                y=round(bucket.get(min_date + timedelta(days=offset), 0.0), 4),
            )
            for offset in range((max_date - min_date).days + 1)
        ]
        series_map[item_id] = DailyDemandSeries(
            business_id=str(business_id),
            item_id=item_id,
            points=points,
            timezone=tz.key,
            date_range_days=len(points),
            observation_count=tx_counts.get(item_id, 0),
            nonzero_days=sum(1 for p in points if p.y > 0),
            total_demand=round(sum(p.y for p in points), 4),
        )
    return series_map