"""Infrastructure probes for Redis, Celery, and worker health."""
from __future__ import annotations

from typing import Any

from app.config import get_settings

settings = get_settings()


async def ping_redis(redis_url: str | None = None) -> dict[str, Any]:
    url = redis_url if redis_url is not None else settings.REDIS_URL
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
        # Single broadcast: stats() already identifies online workers.
        # Multiple inspect calls each burn a full broadcast timeout and,
        # when called synchronously inside async endpoints, block the
        # event loop long enough to saturate the service.
        inspect = celery_app.control.inspect(timeout=2)
        stats = (inspect.stats() or {}) if hasattr(inspect, "stats") else {}
        return {
            "enabled": True,
            "reachable": True,
            "workers_online": list(stats.keys()),
            "registered_task_count": None,
            "active_task_count": sum(
                len(stats.get(name, {}).get("pool", []) or []) for name in stats
            ) if stats else 0,
        }
    except Exception as exc:
        return {"enabled": True, "reachable": False, "reason": str(exc)}


def get_celery_queue_lengths() -> dict[str, Any]:
    if not settings.USE_CELERY:
        return {"enabled": False, "queues": {}}

    try:
        from app.celery_app import celery_app
        inspect = celery_app.control.inspect(timeout=2)
        reserved = inspect.reserved() or {}
        return {
            "enabled": True,
            "queues": {
                worker: len(tasks) for worker, tasks in reserved.items()
            },
        }
    except Exception as exc:
        return {"enabled": True, "queues": {}, "error": str(exc)}


async def infra_status() -> dict[str, Any]:
    import asyncio

    return {
        "redis": await ping_redis(),
        "celery": await asyncio.to_thread(ping_celery),
        "celery_queues": await asyncio.to_thread(get_celery_queue_lengths),
    }
