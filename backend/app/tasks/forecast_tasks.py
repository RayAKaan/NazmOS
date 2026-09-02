import logging
from sqlalchemy import text

from app.config import get_settings
from app.database.connection import get_sync_session
from app.services.forecasting.prophet_provider import ProphetProvider
from app.services.forecasting.sync_runner import run_provider_forecast_sync

settings = get_settings()
logger = logging.getLogger("forecast_tasks")


def _run_for_items(pairs):
    """Run item-level forecasts, isolating per-item failures.

    A single bad item must not abort the batch: failures are logged and
    skipped, and the batch continues with the remaining items.
    """
    results = {"completed": 0, "failed": 0, "no_data": 0}
    provider = ProphetProvider()
    for (item_id, business_id) in pairs:
        try:
            legacy = run_provider_forecast_sync(
                provider, business_id, item_id, horizon_days=30
            )
        except Exception as exc:
            logger.exception("Item forecast failed item=%s", item_id)
            results["failed"] += 1
            continue
        if not legacy:
            results["failed"] += 1
            logger.warning("Item forecast failed item=%s", item_id)
        elif legacy.get("fallback_reason") == "no_transactions":
            results["no_data"] += 1
        else:
            results["completed"] += 1
    return results


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

        pairs = [(str(r[0]), str(r[1])) for r in top_items]
        results = _run_for_items(pairs)

    return {"status": "completed", "items_queued": len(top_items), **results}


def run_refresh_forecasts_for_business(business_id: str):
    with get_sync_session() as session:
        result = session.execute(
            text("SELECT id FROM items WHERE business_id = :business_id AND is_active = true"),
            {"business_id": business_id}
        )
        items = result.fetchall()
        pairs = [(str(r[0]), business_id) for r in items]

        results = _run_for_items(pairs)

    return {"status": "completed", "business_id": business_id, **results}


def run_train_forecast_for_item(item_id: str, business_id: str):
    provider = ProphetProvider()
    return run_provider_forecast_sync(provider, business_id, item_id, horizon_days=30)


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
