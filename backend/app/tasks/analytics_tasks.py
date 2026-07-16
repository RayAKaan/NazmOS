from datetime import datetime, timedelta
from sqlalchemy import text

from app.config import get_settings
from app.database.connection import get_sync_session

settings = get_settings()


def run_refresh_daily_summaries(date_str: str):
    with get_sync_session() as session:
        result = session.execute(
            text("""
                INSERT INTO daily_summaries (business_id, date, total_sales, total_profit, total_transactions, top_item_id, top_item_qty)
                SELECT
                    t.business_id,
                    DATE(:date) as date,
                    COALESCE(SUM(t.total_amount), 0) as total_sales,
                    COALESCE(SUM(t.profit), 0) as total_profit,
                    COUNT(*) as total_transactions,
                    (
                        SELECT item_id
                        FROM transactions t2
                        WHERE t2.business_id = t.business_id
                        AND DATE(t2.transaction_at) = DATE(:date)
                        GROUP BY item_id
                        ORDER BY SUM(t2.quantity) DESC
                        LIMIT 1
                    ) as top_item_id,
                    (
                        SELECT SUM(quantity)
                        FROM transactions t3
                        WHERE t3.business_id = t.business_id
                        AND DATE(t3.transaction_at) = DATE(:date)
                        GROUP BY item_id
                        ORDER BY SUM(t3.quantity) DESC
                        LIMIT 1
                    ) as top_item_qty
                FROM transactions t
                WHERE DATE(t.transaction_at) = :date
                GROUP BY t.business_id
                ON CONFLICT (business_id, date) DO UPDATE SET
                    total_sales = EXCLUDED.total_sales,
                    total_profit = EXCLUDED.total_profit,
                    total_transactions = EXCLUDED.total_transactions
            """),
            {"date": date_str}
        )
        session.commit()

    return {"status": "completed", "date": date_str}


def run_rebuild_summaries_yesterday():
    yesterday = datetime.utcnow().date() - timedelta(days=1)
    return run_refresh_daily_summaries(yesterday.strftime("%Y-%m-%d"))


if settings.USE_CELERY:
    from celery import Task
    from app.celery_app import celery_app

    @celery_app.task(name="app.tasks.analytics_tasks.rebuild_summaries_yesterday")
    def rebuild_summaries_yesterday():
        return run_rebuild_summaries_yesterday()

    @celery_app.task(name="app.tasks.analytics_tasks.refresh_daily_summaries")
    def refresh_daily_summaries(date_str: str):
        return run_refresh_daily_summaries(date_str)
