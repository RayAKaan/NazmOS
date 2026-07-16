from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.schemas.common import HealthResponse

router = APIRouter(tags=["Health"])
settings = get_settings()


@router.get("/health", response_model=HealthResponse)
async def health_check():
    return HealthResponse(
        status="healthy",
        version="1.0.0",
        timestamp=datetime.utcnow(),
    )


@router.get("/live")
async def liveness_check():
    return {"status": "alive", "service": "nazmos-api", "timestamp": datetime.utcnow().isoformat()}


@router.get("/ready")
async def readiness_check(db: AsyncSession = Depends(get_db)):
    checks = {
        "database": "unknown",
        "redis": "unknown",
        "environment": settings.ENVIRONMENT,
        "uploads_dir": settings.UPLOAD_DIR,
    }
    status = "ready"

    try:
        await db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:
        checks["database"] = f"error: {exc}"
        status = "not_ready"

    try:
        import redis.asyncio as aioredis
        redis = aioredis.from_url(settings.REDIS_URL)
        await redis.ping()
        await redis.aclose()
        checks["redis"] = "ok"
    except Exception as exc:
        checks["redis"] = f"error: {exc}"
        # Redis failure means background import/progress may fail, but API can still answer.
        status = "degraded" if status == "ready" else status

    required_env = ["SECRET_KEY", "DATABASE_URL", "REDIS_URL"]
    missing = [name for name in required_env if not getattr(settings, name, None)]
    checks["required_env_missing"] = missing
    if missing:
        status = "not_ready"

    return {
        "status": status,
        "checks": checks,
        "timestamp": datetime.utcnow().isoformat(),
    }
