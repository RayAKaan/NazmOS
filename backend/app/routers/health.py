from datetime import datetime

import asyncio

from fastapi import APIRouter, Depends, HTTPException
from typing import Any
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.schemas.common import HealthResponse
from app.services.infra_service import ping_redis, ping_celery, get_celery_queue_lengths

router = APIRouter(tags=["Health"])
settings = get_settings()


async def _dependency_checks(db: AsyncSession | None = None) -> tuple[str, dict]:
    """Run dependency probes and return an aggregate status plus a checks map."""
    checks: dict[str, Any] = {
        "database": "unknown",
        "redis": "unknown",
        "environment": settings.ENVIRONMENT,
    }
    status = "healthy"
    strict_runtime = settings.ENVIRONMENT in {"runtime_test", "production", "staging"} or settings.USE_CELERY or settings.USE_REDIS

    try:
        if db is None:
            from app.database.connection import AsyncSessionLocal
            async with AsyncSessionLocal() as probe_db:
                await probe_db.execute(text("SELECT 1"))
        else:
            await db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception:
        checks["database"] = "error"
        status = "unhealthy"

    try:
        import redis.asyncio as aioredis
        redis = aioredis.from_url(settings.REDIS_URL)
        await redis.ping()
        await redis.aclose()
        checks["redis"] = "ok"
    except Exception:
        checks["redis"] = "error"
        if strict_runtime:
            status = "unhealthy"
        elif status == "healthy":
            status = "degraded"

    if strict_runtime:
        # Celery inspect broadcasts are blocking Kombu calls; run them on a
        # worker thread so the event loop is never blocked by health probes.
        celery_probe = await asyncio.to_thread(ping_celery)
        checks["celery"] = "ok" if celery_probe.get("reachable") and celery_probe.get("workers_online") else "error"
        if checks["celery"] != "ok":
            status = "unhealthy"

    required_env = ["SECRET_KEY", "DATABASE_URL", "REDIS_URL"]
    checks["required_env_missing"] = [name for name in required_env if not getattr(settings, name, None)]
    if checks["required_env_missing"]:
        status = "unhealthy"

    return status, checks


@router.get("/health", response_model=HealthResponse)
async def health_check(db: AsyncSession = Depends(get_db)):
    status, checks = await _dependency_checks(db)
    return HealthResponse(
        status=status,
        version="1.0.0",
        timestamp=datetime.utcnow(),
        checks=checks,
        environment=settings.ENVIRONMENT,
    )


@router.get("/live")
async def liveness_check():
    return {"status": "alive", "service": "nazmos-api", "timestamp": datetime.utcnow().isoformat()}


@router.get("/ready")
async def readiness_check(db: AsyncSession = Depends(get_db)):
    status, checks = await _dependency_checks(db)
    # ready/unhealthy terminology for Kubernetes probes.  Fail closed: a
    # service that cannot reach its dependencies must never advertise ready.
    ready_status = "ready" if status == "healthy" else "not_ready" if status == "unhealthy" else status
    if status == "unhealthy":
        raise HTTPException(status_code=503, detail={"status": "not_ready", "checks": checks})
    return {
        "status": ready_status,
        "checks": checks,
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.get("/health/redis")
async def redis_health():
    result = await ping_redis()
    if not result.get("reachable"):
        result["reason"] = "redis_unreachable"
    return {
        "service": "redis",
        "timestamp": datetime.utcnow().isoformat(),
        **result,
    }


@router.get("/health/celery")
async def celery_health():
    probe, queues = await asyncio.gather(
        asyncio.to_thread(ping_celery),
        asyncio.to_thread(get_celery_queue_lengths),
    )
    if not probe.get("reachable") and "reason" in probe and not probe.get("enabled"):
        probe["reason"] = "celery_disabled"
    elif not probe.get("reachable"):
        probe["reason"] = "celery_unreachable"
    if "error" in queues:
        queues["error"] = "queue_probe_failed"
    return {
        "service": "celery",
        "timestamp": datetime.utcnow().isoformat(),
        **probe,
        "queues": queues.get("queues", {}),
    }
