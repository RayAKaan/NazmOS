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
    from kombu import Queue

    celery_app = Celery(
        "NazmOS",
        broker=settings.REDIS_URL,
        backend=settings.REDIS_URL,
        include=[
            "app.tasks.forecast_tasks",
            "app.tasks.ingestion_tasks",
            "app.tasks.analytics_tasks",
            "app.tasks.compliance_tasks",
            "app.tasks.event_tasks",
            "app.tasks.business_memory_tasks",
            "app.tasks.learning_tasks",
        ],
    )

    celery_app.conf.update(
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="Asia/Riyadh",
        enable_utc=True,
        task_acks_late=True,
        task_reject_on_worker_lost=True,
        worker_prefetch_multiplier=1,
        task_soft_time_limit=300,
        task_time_limit=600,
        result_expires=3600,
        # Retry policy: exponential backoff, max 3 attempts, then dead-letter queue.
        task_default_retry_delay=60,
        task_max_retries=3,
        task_default_queue="celery",
        task_default_routing_key="celery",
        task_queues=(
            Queue("celery", routing_key="celery"),
            Queue("forecasting", routing_key="forecasting"),
            Queue("ingestion", routing_key="ingestion"),
            Queue("analytics", routing_key="analytics"),
            Queue("dead_letter", routing_key="dead_letter"),
        ),
        task_routes={
            "app.tasks.forecast_tasks.*": {"queue": "forecasting"},
            "app.tasks.ingestion_tasks.*": {"queue": "ingestion"},
            "app.tasks.analytics_tasks.*": {"queue": "analytics"},
        },
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
            "process-pending-deletions": {
                "task": "app.tasks.compliance_tasks.process_pending_deletions",
                "schedule": crontab(hour=4, minute=0),
            },
            "process-unprocessed-events": {
                "task": "app.tasks.event_tasks.process_unprocessed_events",
                "schedule": 60.0,  # every minute
            },
            "refresh-model-performance": {
                "task": "app.tasks.learning_tasks.refresh_model_performance",
                "schedule": crontab(hour=5, minute=0),  # daily at 05:00 Asia/Riyadh
            },
        },
    )

    # Register a dead-letter handler so failed tasks are not silently dropped.
    @celery_app.task(bind=True, queue="dead_letter")
    def dead_letter_handler(self, task_name: str, args: list, kwargs: dict, exception: str) -> None:
        from app.utils.logger import setup_logger
        logger = setup_logger("celery.dead_letter")
        logger.error(
            "Task moved to dead letter queue",
            extra={
                "task_name": task_name,
                "task_id": self.request.id,
                "args": args,
                "kwargs": kwargs,
                "exception": exception,
            },
        )

    # Register signal to capture final failures and route to DLQ.
    @celery_app.task_failure.connect
    def on_task_failure(sender=None, task_id=None, exception=None, args=None, kwargs=None, **kw):
        if sender and task_id:
            dead_letter_handler.delay(sender.name, list(args or []), dict(kwargs or {}), str(exception))
