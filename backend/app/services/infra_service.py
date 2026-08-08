"""Infrastructure probes for Redis, Celery, and worker health."""
from __future__ import annotations

from typing import Any

from app.config import get_settings

settings = get_settings()


async def ping_redis(redis_url: str | None = None) -> dict[str, Any]:
    url = redis_url or settings.REDIS_URL
    if not url:
        return {"reachable": False, "reason": "REDIS_URL not configured"}
    try:
        import redis.asyncio as aioredis
        client = aioredis.from_url(url)
        await client.ping()
        info = await client.info()
        await client.aclose()
        return {
            "reachable": True,
            "version": info.get("redis_version"),
            "used_memory_human": info.get("used_memory_human"),
        }
    except Exception as exc:
        return {"reachable": False, "reason": str(exc)}


def ping_celery() -> dict[str, Any]:
    if not settings.USE_CELERY:
        return {"enabled": False, "reachable": False, "reason": "USE_CELERY=false"}

    try:
        from app.celery_app import celery_app
        with celery_app.connection() as conn:
            conn.ensure_connection(max_retries=2)
        inspect = celery_app.control.inspect(timeout=5)
        active = (inspect.active() or {}) if hasattr(inspect, "active") else {}
        registered = (inspect.registered() or {}) if hasattr(inspect, "registered") else {}
        stats = (inspect.stats() or {}) if hasattr(inspect, "stats") else {}
        return {
            "enabled": True,
            "reachable": True,
            "workers_online": list(stats.keys()),
            "active_task_count": sum(len(v) for v in active.values()),
            "registered_task_count": sum(len(v) for v in registered.values()),
        }
    except Exception as exc:
        return {"enabled": True, "reachable": False, "reason": str(exc)}


def get_celery_queue_lengths() -> dict[str, Any]:
    if not settings.USE_CELERY:
        return {"enabled": False, "queues": {}}

    try:
        from app.celery_app import celery_app
        inspect = celery_app.control.inspect(timeout=5)
        scheduled = inspect.scheduled() or {}
        reserved = inspect.reserved() or {}
        return {
            "enabled": True,
            "queues": {
                worker: len(tasks) for worker, tasks in {**scheduled, **reserved}.items()
            },
        }
    except Exception as exc:
        return {"enabled": True, "queues": {}, "error": str(exc)}


async def infra_status() -> dict[str, Any]:
    return {
        "redis": await ping_redis(),
        "celery": ping_celery(),
        "celery_queues": get_celery_queue_lengths(),
    }
