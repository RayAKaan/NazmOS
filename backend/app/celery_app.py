from app.config import get_settings

settings = get_settings()

if not settings.USE_CELERY:
    # When Celery is disabled, create a stub module so imports don't crash.
    class _StubCeleryApp:
        """Minimal stub that satisfies isinstance checks without importing Celery."""
        task = lambda self, *a, **kw: (lambda fn: fn)
        def send_task(self, *a, **kw):
            raise RuntimeError("Celery is disabled (USE_CELERY=False)")
        conf = type("Conf", (), {"update": lambda self, **kw: None})()

    celery_app = _StubCeleryApp()
else:
    from celery import Celery
    from celery.schedules import crontab

    celery_app = Celery(
        "NazmOS",
        broker=settings.REDIS_URL,
        backend=settings.REDIS_URL,
        include=[
            "app.tasks.forecast_tasks",
            "app.tasks.ingestion_tasks",
            "app.tasks.analytics_tasks",
        ]
    )

    celery_app.conf.update(
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="Asia/Kolkata",
        enable_utc=True,
        task_routes={
            "app.tasks.forecast_tasks.*": {"queue": "forecasting"},
            "app.tasks.ingestion_tasks.*": {"queue": "ingestion"},
            "app.tasks.analytics_tasks.*": {"queue": "analytics"},
        },
        task_acks_late=True,
        task_reject_on_worker_lost=True,
        worker_prefetch_multiplier=1,
        task_soft_time_limit=300,
        task_time_limit=600,
        result_expires=3600,
        beat_schedule={
            "refresh-all-forecasts": {
                "task": "app.tasks.forecast_tasks.refresh_all_forecasts",
                "schedule": crontab(hour=3, minute=0),
            },
            "rebuild-daily-summaries": {
                "task": "app.tasks.analytics_tasks.rebuild_summaries_yesterday",
                "schedule": crontab(hour=1, minute=0),
            },
            "cleanup-stale-uploads": {
                "task": "app.tasks.ingestion_tasks.cleanup_stale_uploads",
                "schedule": crontab(hour=2, minute=0),
            },
        }
    )
