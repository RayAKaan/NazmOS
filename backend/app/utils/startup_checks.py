"""Startup dependency validation.

Fail closed when required services are unreachable in production.
"""
from __future__ import annotations

from app.config import get_settings
from app.utils.logger import setup_logger

settings = get_settings()
logger = setup_logger("startup")


async def validate_redis() -> None:
    """Ping Redis when USE_REDIS or USE_CELERY is enabled. Raise on failure."""
    if not settings.REDIS_URL:
        return

    try:
        import redis.asyncio as aioredis
    except ImportError:  # pragma: no cover
        raise RuntimeError("redis.asyncio is required when REDIS_URL is set")

    client = aioredis.from_url(settings.REDIS_URL)
    try:
        await client.ping()
        logger.info("Redis connectivity verified")
    except Exception as exc:
        raise RuntimeError(f"Redis is unreachable at {settings.REDIS_URL}: {exc}") from exc
    finally:
        await client.aclose()


def validate_celery_broker() -> None:
    """Validate Celery broker connectivity. Raise on failure."""
    if not settings.USE_CELERY:
        return

    from app.celery_app import celery_app

    try:
        # Inspect the broker connection directly without importing heavy task code.
        with celery_app.connection() as conn:
            conn.ensure_connection(max_retries=2)
        logger.info("Celery broker connectivity verified")
    except Exception as exc:
        raise RuntimeError(f"Celery broker is unreachable: {exc}") from exc


async def run_startup_checks() -> None:
    """Run all fail-closed startup checks."""
    if settings.USE_REDIS or settings.USE_CELERY:
        await validate_redis()
    if settings.USE_CELERY:
        validate_celery_broker()
        from app.celery_app import check_celery_health

        if check_celery_health():
            logger.info("task_backend=celery")
        else:
            logger.warning(
                "CELERY_WORKERS_UNHEALTHY",
                message="task_backend=backgroundtasks — one or more Celery queues did not answer health.ping. Background tasks will run in-process; check celery_worker logs.",
            )
