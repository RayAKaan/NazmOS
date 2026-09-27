"""Infrastructure probes for Redis and the Temporal execution substrate."""
from __future__ import annotations

import asyncio
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


async def ping_temporal() -> dict[str, Any]:
    """Probe the Temporal server (the single production execution substrate).

    Uses the same hard-failure contract as the runner: when ``USE_TEMPORAL`` is
    true the substrate is required, so an unreachable server is reported as an
    operational failure (``reachable=False``), never silently downgraded.
    """
    if not settings.USE_TEMPORAL:
        return {"enabled": False, "reachable": False, "reason": "USE_TEMPORAL=false"}

    try:
        from temporalio.client import Client

        client = await asyncio.wait_for(
            Client.connect(
                settings.TEMPORAL_ADDRESS,
                namespace=settings.TEMPORAL_NAMESPACE,
            ),
            timeout=settings.TEMPORAL_CONNECT_TIMEOUT_SECONDS,
        )
        try:
            info = await asyncio.wait_for(
                client.workflow_service.get_system_info(),
                timeout=settings.TEMPORAL_CONNECT_TIMEOUT_SECONDS,
            )
            server_version = str(getattr(info, "server_version", "unknown"))
        except Exception:  # noqa: BLE001 - version is informational only
            server_version = "unknown"
        return {
            "enabled": True,
            "reachable": True,
            "address": settings.TEMPORAL_ADDRESS,
            "namespace": settings.TEMPORAL_NAMESPACE,
            "server_version": server_version,
        }
    except Exception as exc:
        return {
            "enabled": True,
            "reachable": False,
            "address": settings.TEMPORAL_ADDRESS,
            "reason": str(exc),
        }


async def infra_status() -> dict[str, Any]:
    return {
        "redis": await ping_redis(),
        "temporal": await ping_temporal(),
    }