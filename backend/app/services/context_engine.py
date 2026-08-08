"""Context Engine service (Phase 3).

Fetches and caches external context (holidays, weather, regulation, inflation)
that can be attached to business events at ingestion time.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database.models import Business, BusinessContext
from app.utils.logger import setup_logger

settings = get_settings()
logger = setup_logger("context_engine")

CONTEXT_TYPES = {"holiday", "weather", "prayer_time", "inflation", "regulation", "competitor"}


def _to_uuid(value: UUID | str) -> UUID:
    if isinstance(value, UUID):
        return value
    return UUID(value)


async def get_active_context(
    session: AsyncSession,
    business_id: UUID | str,
    context_type: str | None = None,
    at: datetime | None = None,
) -> list[BusinessContext]:
    """Return context records active at a given time (default now)."""
    business_id = _to_uuid(business_id)
    at = at or datetime.now(timezone.utc)
    query = select(BusinessContext).where(
        BusinessContext.business_id == business_id,
        BusinessContext.effective_from <= at,
    )
    if context_type:
        query = query.where(BusinessContext.context_type == context_type)
    query = query.where(
        (BusinessContext.effective_until.is_(None)) | (BusinessContext.effective_until >= at)
    )
    result = await session.execute(query)
    return list(result.scalars().all())


async def create_context(
    session: AsyncSession,
    business_id: UUID | str,
    data: dict[str, Any],
) -> BusinessContext:
    """Persist a context record."""
    if data.get("context_type") not in CONTEXT_TYPES:
        raise ValueError(f"Unsupported context_type: {data.get('context_type')}")
    ctx = BusinessContext(
        business_id=_to_uuid(business_id),
        context_type=data["context_type"],
        source=data.get("source"),
        source_url=data.get("source_url"),
        effective_from=data["effective_from"],
        effective_until=data.get("effective_until"),
        payload=data.get("payload", {}),
        confidence=data.get("confidence", 1.0),
    )
    session.add(ctx)
    await session.flush()
    return ctx


async def build_context_snapshot(
    session: AsyncSession,
    business_id: UUID | str,
    at: datetime | None = None,
) -> dict[str, Any]:
    """Build a snapshot of active context keyed by context_type."""
    contexts = await get_active_context(session, business_id, at=at)
    snapshot: dict[str, Any] = {}
    for ctx in contexts:
        snapshot.setdefault(ctx.context_type, []).append({
            "source": ctx.source,
            "source_url": ctx.source_url,
            "effective_from": ctx.effective_from.isoformat() if ctx.effective_from else None,
            "effective_until": ctx.effective_until.isoformat() if ctx.effective_until else None,
            "payload": ctx.payload,
            "confidence": float(ctx.confidence) if ctx.confidence is not None else 1.0,
        })
    return snapshot


# ═══════════════════════════════════════════════════════════════════════════
# Adapters
# ═══════════════════════════════════════════════════════════════════════════

async def _fetch_json(url: str, timeout: float = 10.0) -> dict[str, Any] | None:
    try:
        import httpx
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.json()
    except Exception as exc:
        logger.warning("External context adapter request failed", extra={"url": url, "error": str(exc)})
        return None


def _ksa_holidays_fallback(year: int) -> list[dict[str, Any]]:
    """Known Saudi public holidays for the current cycle."""
    # Sources: Umm al-Qura calendar and announced public holidays.
    fixed = [
        (f"{year}-01-01", f"{year}-01-01", "New Year's Day"),
        (f"{year}-02-22", f"{year}-02-22", "Saudi Founding Day"),
        (f"{year}-09-23", f"{year}-09-23", "Saudi National Day"),
    ]
    # Approximate Hijri dates for 2026 (subject to moon sighting).
    hijri_2026 = [
        ("2026-02-16", "2026-02-20", "Eid al-Fitr"),
        ("2026-05-25", "2026-05-29", "Eid al-Adha / Hajj"),
    ]
    holidays = []
    for start, end, name in fixed + hijri_2026:
        holidays.append({
            "name": name,
            "start": start,
            "end": end,
        })
    return holidays


async def fetch_holiday_context(year: int | None = None) -> dict[str, Any]:
    """Fetch Saudi holiday context; fallback to known dates if API fails."""
    year = year or datetime.now(timezone.utc).year
    data = await _fetch_json(f"https://date.nager.at/api/v3/publicholidays/{year}/SA")
    if data:
        return {
            "year": year,
            "holidays": [
                {"name": h.get("name"), "date": h.get("date"), "local_name": h.get("localName")}
                for h in data
            ],
            "source": "nager.date",
        }
    return {
        "year": year,
        "holidays": _ksa_holidays_fallback(year),
        "source": "fallback",
    }


async def fetch_weather_context(lat: float, lon: float) -> dict[str, Any]:
    """Fetch current weather from Open-Meteo; graceful fallback on failure."""
    url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}&current=temperature_2m,relative_humidity_2m,weather_code"
    )
    data = await _fetch_json(url)
    if data and "current" in data:
        return {
            "latitude": lat,
            "longitude": lon,
            "temperature_c": data["current"].get("temperature_2m"),
            "humidity_percent": data["current"].get("relative_humidity_2m"),
            "weather_code": data["current"].get("weather_code"),
            "source": "open-meteo.com",
        }
    return {
        "latitude": lat,
        "longitude": lon,
        "temperature_c": None,
        "humidity_percent": None,
        "weather_code": None,
        "source": "fallback",
    }


async def fetch_inflation_context() -> dict[str, Any]:
    """Return latest Saudi inflation context.

    Uses the World Bank API as the primary source and a static fallback value
    when the API is unreachable.
    """
    # World Bank inflation indicator (NY.GDP.DEFL.KD.ZG) for Saudi Arabia.
    url = "https://api.worldbank.org/v2/country/SAU/indicator/FP.CPI.TOTL.ZG?format=json&per_page=5&date=2024:2026"
    data = await _fetch_json(url)
    if data and len(data) > 1:
        records = [
            {"year": r.get("date"), "value": r.get("value")}
            for r in data[1]
            if r.get("value") is not None
        ]
        if records:
            return {"records": records, "source": "worldbank.org"}
    return {
        "records": [{"year": "2025", "value": 1.9}],
        "source": "fallback",
    }


async def fetch_regulation_context() -> dict[str, Any]:
    """Fetch Saudi regulation alerts from MoC RSS feed; fallback empty."""
    url = "https://www.mc.gov.sa/en/rss"
    try:
        import httpx
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            return {
                "feed_url": url,
                "content_length": len(response.text),
                "source": "mc.gov.sa",
            }
    except Exception as exc:
        logger.warning("Regulation adapter failed", extra={"url": url, "error": str(exc)})
    return {"feed_url": url, "content_length": 0, "source": "fallback"}


async def refresh_context_for_business(
    session: AsyncSession,
    business_id: UUID | str,
) -> dict[str, Any]:
    """Refresh all external context for a business and persist it.

    This is intended to be called by a Celery beat task or on demand.
    """
    business_id = _to_uuid(business_id)
    business = await session.get(Business, business_id)
    if not business:
        return {"status": "not_found"}

    results = {}
    now = datetime.now(timezone.utc)

    # Holidays
    holiday = await fetch_holiday_context()
    await create_context(
        session,
        business_id,
        {
            "context_type": "holiday",
            "source": holiday.get("source"),
            "effective_from": now,
            "effective_until": now + timedelta(days=365),
            "payload": holiday,
            "confidence": 1.0 if holiday.get("source") != "fallback" else 0.7,
        },
    )
    results["holiday"] = holiday.get("source")

    # Weather
    lat = float(business.latitude) if business.latitude else 24.7136
    lon = float(business.longitude) if business.longitude else 46.6753
    weather = await fetch_weather_context(lat, lon)
    await create_context(
        session,
        business_id,
        {
            "context_type": "weather",
            "source": weather.get("source"),
            "effective_from": now,
            "effective_until": now + timedelta(hours=6),
            "payload": weather,
            "confidence": 1.0 if weather.get("source") != "fallback" else 0.5,
        },
    )
    results["weather"] = weather.get("source")

    # Inflation
    inflation = await fetch_inflation_context()
    await create_context(
        session,
        business_id,
        {
            "context_type": "inflation",
            "source": inflation.get("source"),
            "effective_from": now,
            "effective_until": now + timedelta(days=90),
            "payload": inflation,
            "confidence": 1.0 if inflation.get("source") != "fallback" else 0.6,
        },
    )
    results["inflation"] = inflation.get("source")

    # Regulation
    regulation = await fetch_regulation_context()
    await create_context(
        session,
        business_id,
        {
            "context_type": "regulation",
            "source": regulation.get("source"),
            "effective_from": now,
            "effective_until": now + timedelta(days=7),
            "payload": regulation,
            "confidence": 1.0 if regulation.get("source") != "fallback" else 0.3,
        },
    )
    results["regulation"] = regulation.get("source")

    await session.commit()
    return {"status": "refreshed", "business_id": str(business_id), "sources": results}
