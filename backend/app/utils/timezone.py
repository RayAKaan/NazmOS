"""Shared timezone helpers (KSA-first).

Body of truth for converting persisted UTC timestamps into the business's
local calendar date before daily-demand aggregation. The old code duplicated
``timezone(timedelta(hours=3))`` inline in ``forecast.py``, ``seed.py`` and
``nazm_planner.py``; every consumer should use these helpers instead.
"""
from datetime import date, datetime, time, timedelta
from typing import Optional, Union
from zoneinfo import ZoneInfo

from app.config import get_settings

KSA_TZ = ZoneInfo("Asia/Riyadh")

_TZ_CACHE: dict[str, ZoneInfo] = {"Asia/Riyadh": KSA_TZ}


def resolve_timezone(tz_name: Optional[str]) -> ZoneInfo:
    """Return a ``ZoneInfo`` for an IANA name, falling back to Riyadh/KSA.

    The  ``Business.timezone`` column is stored as an IANA string but is not
    guaranteed populated; unknown/blank values should never crash forecasting.
    """
    name = (tz_name or "").strip() or get_settings().DEFAULT_TIMEZONE
    cached = _TZ_CACHE.get(name)
    if cached is not None:
        return cached
    try:
        tz = ZoneInfo(name)
    except Exception:
        tz = KSA_TZ
    _TZ_CACHE[name] = tz
    return tz


def _coerce_to_datetime(ts: Union[datetime, date, str]) -> datetime:
    """Normalize SQLAlchemy row values (SQLite returns ISO strings)."""
    if isinstance(ts, datetime):
        return ts
    if isinstance(ts, date):
        return datetime(ts.year, ts.month, ts.day, tzinfo=ZoneInfo("UTC"))
    if isinstance(ts, str):
        value = ts.strip()
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        return datetime.fromisoformat(value)
    raise TypeError(f"Cannot coerce {type(ts).__name__} to datetime")


def to_business_local(ts: Union[datetime, date, str], tz_name: Optional[str] = None) -> datetime:
    """Convert a timestamp into business-local wall time.

    Naive datetimes and strings are assumed to be UTC (that is how the API
    persists them). Aware datetimes are converted directly.
    """
    tz = resolve_timezone(tz_name)
    dt = _coerce_to_datetime(ts)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo("UTC"))
    return dt.astimezone(tz)


def business_date(ts: Union[datetime, date, str], tz_name: Optional[str] = None) -> date:
    """The calendar date of ``ts`` in the business's local timezone."""
    return to_business_local(ts, tz_name).date()


def today_business(tz_name: Optional[str] = None) -> date:
    """Today's calendar date in the business's local timezone."""
    tz = resolve_timezone(tz_name)
    return datetime.now(tz).date()


def now_utc() -> datetime:
    """Current time as a timezone-aware UTC datetime (the storage format)."""
    return datetime.now(ZoneInfo("UTC"))


def utc_now_naive() -> datetime:
    """Current UTC time as a naive datetime — for cache TTL comparisons.

    ``ForecastCache.expires_at`` is ``DateTime(timezone=True)``; callers that
    compute expiry should pass aware UTC datetimes via :func:`now_utc` so the
    value written to the column matches its ``timestamptz`` type on Postgres.
    """
    return datetime.now(ZoneInfo("UTC")).replace(tzinfo=None)


def floor_to_utc_hour(dt: datetime) -> datetime:
    """Round an aware datetime down to the top of its UTC hour."""
    return dt.astimezone(ZoneInfo("UTC")).replace(minute=0, second=0, microsecond=0)