from datetime import datetime

from fastapi import APIRouter, Depends
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
        "uploads_dir": settings.UPLOAD_DIR,
    }
    status = "healthy"

    try:
        if db is None:
            from app.database.connection import AsyncSessionLocal
            async with AsyncSessionLocal() as probe_db:
                await probe_db.execute(text("SELECT 1"))
        else:
            await db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:
        checks["database"] = f"error: {exc}"
        status = "unhealthy"

    try:
        import redis.asyncio as aioredis
        redis = aioredis.from_url(settings.REDIS_URL)
        await redis.ping()
        await redis.aclose()
        checks["redis"] = "ok"
    except Exception as exc:
        checks["redis"] = f"error: {exc}"
        # Redis is optional in zero-cost mode; do not flip to unhealthy, only degraded.
        if status == "healthy":
            status = "degraded"

    required_env = ["SECRET_KEY", "DATABASE_URL", "REDIS_URL"]
    missing = [name for name in required_env if not getattr(settings, name, None)]
    checks["required_env_missing"] = missing
    if missing:
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
    # ready/unhealthy terminology for Kubernetes probes.
    ready_status = "ready" if status == "healthy" else "not_ready" if status == "unhealthy" else status
    return {
        "status": ready_status,
        "checks": checks,
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.get("/health/redis")
async def redis_health():
    return {
        "service": "redis",
        "timestamp": datetime.utcnow().isoformat(),
        **await ping_redis(),
    }


@router.get("/health/celery")
async def celery_health():
    return {
        "service": "celery",
        "timestamp": datetime.utcnow().isoformat(),
        **ping_celery(),
        "queues": get_celery_queue_lengths().get("queues", {}),
    }
