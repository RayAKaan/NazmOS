from datetime import datetime, timedelta
import pandas as pd
from sqlalchemy import text

from app.config import get_settings
from app.database.connection import get_sync_session
from app.services.prophet_service import ProphetService

settings = get_settings()
prophet_service = ProphetService()


def run_refresh_all_forecasts():
    with get_sync_session() as session:
        # Top 10 items by transaction volume get full Prophet forecasting.
        # The rest use the fast KSA-aware fallback (no Prophet dependency).
        result = session.execute(
            text("""
                SELECT i.id, i.business_id, COUNT(t.id) as tx_count
                FROM items i
                LEFT JOIN transactions t ON t.item_id = i.id
                WHERE i.is_active = true
                GROUP BY i.id, i.business_id
                ORDER BY tx_count DESC
                LIMIT 10
            """)
        )
        top_items = result.fetchall()

        for item in top_items:
            try:
                run_train_forecast_for_item(str(item[0]), str(item[1]))
            except Exception:
                pass

    return {"status": "completed", "items_queued": len(top_items)}


def run_refresh_forecasts_for_business(business_id: str):
    with get_sync_session() as session:
        result = session.execute(
            text("SELECT id FROM items WHERE business_id = :business_id AND is_active = true"),
            {"business_id": business_id}
        )
        items = result.fetchall()

        for item in items:
            try:
                run_train_forecast_for_item(str(item[0]), business_id)
            except Exception:
                pass

    return {"status": "completed", "business_id": business_id}


def run_train_forecast_for_item(item_id: str, business_id: str):
    with get_sync_session() as session:
        result = session.execute(
            text("""
                SELECT DATE(transaction_at) as ds, SUM(quantity) as y
                FROM transactions
                WHERE item_id = :item_id AND business_id = :business_id
                GROUP BY DATE(transaction_at)
                ORDER BY ds
            """),
            {"item_id": item_id, "business_id": business_id}
        )
        rows = result.fetchall()

        if not rows:
            return {"status": "no_data", "item_id": item_id}

        df = pd.DataFrame(rows, columns=["ds", "y"])
        df["ds"] = pd.to_datetime(df["ds"])

        result = prophet_service.train_and_forecast(item_id, "", df, forecast_days=30)

        if not result:
            return {"status": "failed", "item_id": item_id}

        expires_at = datetime.utcnow() + timedelta(hours=settings.FORECAST_CACHE_TTL_HOURS)

        session.execute(
            text("""
                INSERT INTO forecast_cache
                    (business_id, item_id, model_version, training_rows, forecast_7d, forecast_30d,
                     weekly_pattern, trend_direction, trend_strength, trained_at, expires_at)
                VALUES (:business_id, :item_id, 'prophet_v1', :training_rows, :forecast_7d, :forecast_30d,
                        :weekly_pattern, :trend_direction, :trend_strength, NOW(), :expires_at)
                ON CONFLICT (business_id, item_id) DO UPDATE SET
                    forecast_7d = EXCLUDED.forecast_7d,
                    forecast_30d = EXCLUDED.forecast_30d,
                    weekly_pattern = EXCLUDED.weekly_pattern,
                    trend_direction = EXCLUDED.trend_direction,
                    trend_strength = EXCLUDED.trend_strength,
                    trained_at = NOW(),
                    expires_at = EXCLUDED.expires_at
            """),
            {
                "business_id": business_id,
                "item_id": item_id,
                "training_rows": result.get("training_rows", 0),
                "forecast_7d": str(result["forecast_7d"]),
                "forecast_30d": str(result["forecast_30d"]),
                "weekly_pattern": str(result["weekly_pattern"]),
                "trend_direction": result["trend_direction"],
                "trend_strength": result["trend_strength"],
                "expires_at": expires_at,
            }
        )
        session.commit()

        return {"status": "completed", "item_id": item_id}


if settings.USE_CELERY:
    from celery import Task
    from app.celery_app import celery_app

    @celery_app.task(bind=True, name="app.tasks.forecast_tasks.refresh_all_forecasts")
    def refresh_all_forecasts(self):
        return run_refresh_all_forecasts()

    @celery_app.task(name="app.tasks.forecast_tasks.refresh_forecasts_for_business")
    def refresh_forecasts_for_business(business_id: str):
        return run_refresh_forecasts_for_business(business_id)

    @celery_app.task(name="app.tasks.forecast_tasks.train_forecast_for_item")
    def train_forecast_for_item(item_id: str, business_id: str):
        return run_train_forecast_for_item(item_id, business_id)
