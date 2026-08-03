from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4
import json
import pandas as pd

from app.middleware.auth_middleware import get_current_user
from app.middleware.business_access import assert_business_access
from app.database import get_db, User
from app.services.prophet_service import ProphetService

router = APIRouter(prefix="/api/v1/forecast", tags=["forecast"])

R_RIYADH = timezone(timedelta(hours=3))

def _now_riyadh():
    return datetime.now(R_RIYADH)

prophet_service = ProphetService()


@router.post("/")
async def generate_forecast(
    business_id: str,
    item_id: str = None,
    days: int = Query(default=30, ge=7, le=90),
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    """Generate a fresh Prophet forecast – KSA edition, with Saudi holidays"""
    await assert_business_access(db, business_id, current_user)
    
    # Get transaction history
    if item_id:
        tx = await db.execute(text("""
            SELECT transaction_at as ds, SUM(quantity) as y
            FROM transactions
            WHERE business_id = :bid AND item_id = :iid
            GROUP BY transaction_at ORDER BY transaction_at
        """), {"bid": business_id, "iid": item_id})
        rows = tx.fetchall()
        if len(rows) < 7:
            raise HTTPException(422, "Need at least 7 days of sales history for forecasting")
        df = pd.DataFrame(rows, columns=["ds","y"])
        item_name_r = await db.execute(text("SELECT name FROM items WHERE id = :id"), {"id": item_id})
        iname = item_name_r.fetchone()
        item_name = iname[0] if iname else "Item"
        
        result = prophet_service.train_and_forecast(item_id, item_name, df, forecast_days=days)
        
        # Cache it
        from datetime import datetime as dt
        expires = _now_riyadh() + timedelta(hours=24)
        await db.execute(text("""
            INSERT INTO forecast_cache 
            (id, business_id, item_id, model_version, training_rows, forecast_7d, forecast_30d, weekly_pattern, trend_direction, trend_strength, expires_at)
            VALUES (:id, :bid, :iid, 'prophet_v1_ksa', :rows, :f7, :f30, :wp, :td, :ts, :exp)
            ON CONFLICT (business_id, item_id) DO UPDATE SET
            forecast_7d = EXCLUDED.forecast_7d,
            forecast_30d = EXCLUDED.forecast_30d,
            weekly_pattern = EXCLUDED.weekly_pattern,
            trend_direction = EXCLUDED.trend_direction,
            trend_strength = EXCLUDED.trend_strength,
            trained_at = NOW(),
            expires_at = EXCLUDED.expires_at
        """), {
            "id": str(uuid4()), "bid": business_id, "iid": item_id,
            "rows": result["training_rows"],
            "f7": json.dumps(result["forecast_7d"]),
            "f30": json.dumps(result["forecast_30d"]),
            "wp": json.dumps(result["weekly_pattern"]),
            "td": result["trend_direction"],
            "ts": result["trend_strength"],
            "exp": expires
        })
        await db.commit()
        return {"item_id": item_id, "forecast": result, "cached": True}
    
    raise HTTPException(422, "item_id required")


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

        today = _now_riyadh().date()
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
        "mape_score": float(cache.mape_score) if cache.mape_score else None,
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
