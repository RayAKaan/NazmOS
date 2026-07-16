from app.config import get_settings

settings = get_settings()

if settings.USE_CELERY:
    from app.tasks.forecast_tasks import refresh_all_forecasts, train_forecast_for_item
    from app.tasks.ingestion_tasks import process_upload_task, cleanup_stale_uploads
    from app.tasks.analytics_tasks import rebuild_summaries_yesterday, refresh_daily_summaries
