from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from datetime import timedelta

from app.middleware.auth_middleware import get_current_user
from app.middleware.business_access import assert_business_access
from app.database import get_db, User
from app.services.forecasting.cache import write_forecast
from app.services.forecasting.prophet_provider import ProphetProvider
from app.utils.timezone import now_utc

router = APIRouter(prefix="/api/v1/forecast", tags=["forecast"])


@router.post("/")
async def generate_forecast(
    business_id: str,
    item_id: str = None,
    days: int = Query(default=30, ge=7, le=90),
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    """Generate a fresh Prophet forecast – KSA edition, with Saudi holidays.

    Uses the canonical forecasting pipeline: daily demand builder → quality
    gate → ProphetProvider (SQL timezone-safe date aggregation included).
    """
    await assert_business_access(db, business_id, current_user)

    if not item_id:
        raise HTTPException(422, "item_id required")

    provider = ProphetProvider()
    forecast = await provider.forecast(
        db, business_id, item_id, horizon_days=days
    )

    # Existing API contract: refuse to train on almost no history.
    if forecast.context_days < 7:
        raise HTTPException(422, "Need at least 7 days of sales history for forecasting")

    await write_forecast(db, forecast, ttl_hours=24)
    return {"item_id": item_id, "forecast": forecast.as_legacy_dict(), "cached": True}


@router.get("/summary")
async def get_forecast_summary(
    business_id: str,
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    """Get a summary of all active forecasts for a business."""
    await assert_business_access(db, business_id, current_user)
    result = await db.execute(
        text("""
            SELECT
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE trend_direction = 'up') AS trending_up,
                COUNT(*) FILTER (WHERE trend_direction = 'down') AS trending_down,
                COUNT(*) FILTER (WHERE trend_direction = 'stable') AS stable,
                AVG(trend_strength) AS avg_trend_strength,
                MAX(trained_at) AS last_trained_at
            FROM forecast_cache
            WHERE business_id = :business_id
            AND expires_at > NOW()
        """),
        {"business_id": business_id}
    )
    row = result.fetchone()
    return {
        "total_forecasts": int(row.total) if row.total else 0,
        "trending_up": int(row.trending_up) if row.trending_up else 0,
        "trending_down": int(row.trending_down) if row.trending_down else 0,
        "stable": int(row.stable) if row.stable else 0,
        "avg_trend_strength": float(row.avg_trend_strength) if row.avg_trend_strength else 0,
        "last_trained_at": row.last_trained_at.isoformat() if row.last_trained_at else None,
    }


@router.get("/cache")
async def get_cached_forecasts(
    business_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    """List cached forecasts for a business."""
    await assert_business_access(db, business_id, current_user)
    result = await db.execute(
        text("""
            SELECT fc.item_id, i.name AS item_name, fc.model_version, fc.provider, fc.interval_type,
                   fc.trend_direction, fc.trend_strength, fc.trained_at, fc.expires_at,
                   fc.mape_score, fc.rmse_score
            FROM forecast_cache fc
            LEFT JOIN items i ON i.id = fc.item_id
            WHERE fc.business_id = :business_id
            AND fc.expires_at > NOW()
            ORDER BY fc.trained_at DESC
            LIMIT :limit
        """),
        {"business_id": business_id, "limit": limit}
    )
    rows = result.fetchall()
    return {
        "forecasts": [
            {
                "item_id": str(r.item_id),
                "item_name": r.item_name,
                "model_version": r.model_version,
                "provider": r.provider,
                "interval_type": r.interval_type,
                "trend_direction": r.trend_direction,
                "trend_strength": float(r.trend_strength) if r.trend_strength else 0,
                "mape_score": float(r.mape_score) if r.mape_score else None,
                "rmse_score": float(r.rmse_score) if r.rmse_score else None,
                "trained_at": r.trained_at.isoformat() if r.trained_at else None,
                "expires_at": r.expires_at.isoformat() if r.expires_at else None,
            }
            for r in rows
        ],
        "total": len(rows),
    }


@router.get("/{item_id}")
async def get_forecast(
    item_id: str,
    business_id: str,
    horizon: int = Query(default=7, ge=7, le=30),
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    await assert_business_access(db, business_id, current_user)
    result = await db.execute(
        text("""
            SELECT * FROM forecast_cache
            WHERE item_id = :item_id AND business_id = :business_id
            AND expires_at > NOW()
            ORDER BY trained_at DESC
            LIMIT 1
        """),
        {"item_id": item_id, "business_id": business_id}
    )
    cache = result.fetchone()

    if not cache:
        item_result = await db.execute(
            text("SELECT name FROM items WHERE id = :id AND business_id = :business_id"),
            {"id": item_id, "business_id": business_id}
        )
        item = item_result.fetchone()
        
        if not item:
            raise HTTPException(404, detail="Item not found")

        today = now_utc().date()
        return {
            "item_id": item_id,
            "item_name": item.name,
            "trend_direction": "stable",
            "trend_strength": 0,
            "model_version": "fallback_ksa",
            "mape_score": None,
            "trained_at": None,
            "forecast_7d": [
                {"date": (today + timedelta(days=i)).isoformat(),
                 "predicted_qty": 0, "lower": 0, "upper": 0}
                for i in range(1, 8)
            ],
            "weekly_pattern": {
                # KSA weekend: Friday/Saturday peak
                "monday": 0.88, "tuesday": 0.85, "wednesday": 0.90,
                "thursday": 1.15, "friday": 1.42, "saturday": 1.35, "sunday": 0.95
            },
            "from_cache": False,
        }

    forecast_data = cache.forecast_7d
    if horizon == 30:
        forecast_data = cache.forecast_30d
    
    weekly_pattern = cache.weekly_pattern
    if isinstance(weekly_pattern, str):
        import json
        weekly_pattern = json.loads(weekly_pattern)
    if isinstance(forecast_data, str):
        import json
        forecast_data = json.loads(forecast_data)

    return {
        "item_id": item_id,
        "item_name": None,
        "trend_direction": cache.trend_direction,
        "trend_strength": float(cache.trend_strength) if cache.trend_strength else 0,
        "model_version": cache.model_version,
        "provider": cache.provider,
        "interval_type": cache.interval_type,
        "fallback_reason": cache.fallback_reason,
        "mape_score": float(cache.mape_score) if cache.mape_score else None,
        "rmse_score": float(cache.rmse_score) if cache.rmse_score else None,
        "trained_at": cache.trained_at.isoformat() if cache.trained_at else None,
        "forecast_7d": forecast_data[:7] if horizon == 7 else forecast_data[:30],
        "weekly_pattern": weekly_pattern,
        "from_cache": True,
    }


@router.get("/all/{business_id}")
async def get_all_forecasts(
    business_id: str,
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    await assert_business_access(db, business_id, current_user)
    result = await db.execute(
        text("""
            SELECT fc.*, i.name as item_name
            FROM forecast_cache fc
            JOIN items i ON i.id = fc.item_id
            WHERE fc.business_id = :business_id
            AND fc.expires_at > NOW()
            ORDER BY fc.trained_at DESC
        """),
        {"business_id": business_id}
    )
    forecasts = result.fetchall()

    return {
        "forecasts": [
            {
                "item_id": str(f.item_id),
                "item_name": f.item_name,
                "trend_direction": f.trend_direction,
                "trend_strength": float(f.trend_strength) if f.trend_strength else 0,
                "trained_at": f.trained_at.isoformat() if f.trained_at else None,
            }
            for f in forecasts
        ],
        "total": len(forecasts),
    }
