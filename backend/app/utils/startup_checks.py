"""Startup dependency validation.

Fail closed when required services are unreachable in production.
"""
from __future__ import annotations

from app.config import get_settings
from app.services.infra_service import ping_redis, ping_celery
from app.utils.logger import setup_logger

settings = get_settings()
logger = setup_logger("startup")


async def validate_redis() -> None:
    """Ping Redis when USE_REDIS or USE_CELERY is enabled. Raise on failure."""
    if not settings.REDIS_URL:
        return

    result = await ping_redis()
    if not result.get("reachable"):
        raise RuntimeError(f"Redis is unreachable at {settings.REDIS_URL}: {result.get('reason')}")
    logger.info("Redis connectivity verified", extra={"version": result.get("version")})


def validate_celery_broker() -> None:
    """Validate Celery broker connectivity and worker presence. Raise on failure."""
    if not settings.USE_CELERY:
        return

    result = ping_celery()
    if not result.get("reachable"):
        raise RuntimeError(f"Celery broker is unreachable: {result.get('reason')}")
    if not result.get("workers_online"):
        logger.warning("Celery broker reachable but no workers are online")
    else:
        logger.info(
            "Celery connectivity verified",
            extra={"workers": result.get("workers_online", [])},
        )


def validate_production_secrets() -> None:
    """Fail closed in production if critical secrets are still defaults."""
    if settings.ENVIRONMENT != "production":
        return
    if not settings.SENTRY_DSN:
        raise RuntimeError("FATAL: SENTRY_DSN is required in production")
    if settings.USE_MOCK_LLM:
        raise RuntimeError("FATAL: USE_MOCK_LLM must be False in production")
    if not settings.GROQ_API_KEY and not settings.GOOGLE_AI_API_KEY:
        raise RuntimeError(
            "FATAL: at least one of GROQ_API_KEY or GOOGLE_AI_API_KEY is "
            "required in production (merchant-facing LLM responses must use a real provider)"
        )
    if settings.WHATSAPP_ENABLED == "live" and (
        not settings.WHATSAPP_TOKEN or not settings.WHATSAPP_PHONE_ID
    ):
        raise RuntimeError(
            "FATAL: WHATSAPP_ENABLED=live requires WHATSAPP_TOKEN and WHATSAPP_PHONE_ID"
        )
    if not settings.CREDENTIAL_MASTER_KEY or len(settings.CREDENTIAL_MASTER_KEY) < 32:
        raise RuntimeError("FATAL: CREDENTIAL_MASTER_KEY is required in production and must be >= 32 chars")
    if "dev-secret-key" in settings.SECRET_KEY:
        raise RuntimeError("FATAL: SECRET_KEY is still the dev default in production")


async def run_startup_checks() -> None:
    """Run all fail-closed startup checks."""
    validate_production_secrets()
    if settings.USE_REDIS or settings.USE_CELERY:
        await validate_redis()
    if settings.USE_CELERY:
        validate_celery_broker()
