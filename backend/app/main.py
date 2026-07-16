from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
import uuid

from app.config import get_settings
from app.database import engine, Base, AsyncSessionLocal
from app.routers import (
    auth_router, businesses_router, dashboard_router, inventory_router, health_router,
    upload_router, chat_router, forecast_router, decisions_router, money_audit_router, ops_router,
    organizations_router, subscriptions_router, adapters_router, actions_router,
    agent_router, suppliers_router, pharmacy_router, whatsapp_router,
    pos_webhooks_router, orchestrator_router, recovery_match_router,
)
from app.middleware.advanced_rate_limiter import RedisRateLimiter, InMemoryRateLimiter, AdvancedRateLimitMiddleware, get_rate_limiter
from app.middleware.logging_middleware import LoggingMiddleware
from app.middleware.security_headers import SecurityHeadersMiddleware
from app.database.seed import seed_demo_data
from app.utils.logger import setup_logger
from app.utils.exceptions import (
    NotFoundException,
    UnauthorizedException,
    ForbiddenException,
    ValidationException,
    RateLimitedException,
    DuplicateResourceException,
)

settings = get_settings()
logger = setup_logger("app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting NazmOS API...")
    
    if settings.ENVIRONMENT != "production":
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    else:
        logger.info("Production mode: skipping Base.metadata.create_all; use Alembic migrations")
    
    async with AsyncSessionLocal() as session:
        try:
            await seed_demo_data(session)
            logger.info("Demo data seeded successfully")
        except Exception as e:
            logger.warning(f"Demo data seeding skipped: {e}")
    
    yield
    
    logger.info("Shutting down NazmOS API...")
    await engine.dispose()


app = FastAPI(
    title="NazmOS API – Retail Recovery",
    description="Retail Recovery API for Saudi stores: Money Audits, stockout prevention, WhatsApp approvals, and Recovery Match preview.",
    version="2.1.0-ksa",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(LoggingMiddleware)
app.add_middleware(SecurityHeadersMiddleware)

rate_limiter_instance = get_rate_limiter()
app.state.rate_limiter = rate_limiter_instance
app.add_middleware(AdvancedRateLimitMiddleware, limiter=rate_limiter_instance)
if isinstance(rate_limiter_instance, RedisRateLimiter):
    logger.info("Using Redis distributed rate limiter")
else:
    logger.info("Using in-memory rate limiter (development mode)")

app.include_router(health_router, prefix="/api/v1")
app.include_router(auth_router, prefix="/api/v1")
app.include_router(businesses_router)
app.include_router(dashboard_router, prefix="/api/v1")
app.include_router(inventory_router, prefix="/api/v1")
app.include_router(upload_router)
app.include_router(forecast_router)
app.include_router(decisions_router)
app.include_router(money_audit_router)
app.include_router(ops_router)

# Retail Recovery routers only.
app.include_router(pos_webhooks_router)
app.include_router(orchestrator_router)
if recovery_match_router is not None:
    app.include_router(recovery_match_router)
logger.info("✓ NazmOS Retail Recovery enabled (Money Audit, POS Webhooks, WhatsApp approvals, Recovery Match preview)")

# Nazm Agent – KSA Agent OS – $0 LLM
if getattr(settings, "AGENT_ENABLED", True) and agent_router is not None:
    app.include_router(agent_router)
    logger.info("✓ Nazm Agent API enabled – /api/v1/agent/feed")
else:
    logger.info("Nazm Agent API disabled")

# Supplier Network – two-sided moat
if suppliers_router is not None:
    app.include_router(suppliers_router)
    logger.info("✓ Supplier Network API enabled")

# Pharmacy Vertical – FEFO / SFDA
if pharmacy_router is not None and getattr(settings, "VERTICAL_PHARMACY", True):
    app.include_router(pharmacy_router)
    logger.info("✓ Pharmacy module enabled – expiry/FEFO/SFDA")

# WhatsApp – approval bridge – always on (mock mode = $0)
if whatsapp_router is not None:
    app.include_router(whatsapp_router)
    logger.info("✓ WhatsApp webhook enabled – /api/v1/whatsapp/webhook")

# Chat / Baseer – disabled by default for implementation sales
if settings.CHAT_ENABLED:
    app.include_router(chat_router)
    logger.info("Baseer Chat API enabled")
else:
    logger.info("Baseer Chat API disabled – KSA Lite mode")

@app.get("/health")
async def root_health():
    return {"status": "healthy", "service": "nazmos-api"}


# Billing / SaaS – disabled for one-time implementation model
if settings.BILLING_ENABLED:
    app.include_router(subscriptions_router)
    app.include_router(organizations_router)
    app.include_router(adapters_router)
    app.include_router(actions_router)
    logger.info("Billing/SaaS routers enabled")
else:
    logger.info("Billing/SaaS routers disabled – KSA Implementation mode")


@app.exception_handler(NotFoundException)
async def not_found_handler(request: Request, exc: NotFoundException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": True,
            "code": "NOT_FOUND",
            "message": exc.detail,
            "detail": None,
            "timestamp": str(uuid.uuid4()),
        },
    )


@app.exception_handler(UnauthorizedException)
async def unauthorized_handler(request: Request, exc: UnauthorizedException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": True,
            "code": "UNAUTHORIZED",
            "message": exc.detail,
            "detail": None,
            "timestamp": str(uuid.uuid4()),
        },
    )


@app.exception_handler(ForbiddenException)
async def forbidden_handler(request: Request, exc: ForbiddenException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": True,
            "code": "FORBIDDEN",
            "message": exc.detail,
            "detail": None,
            "timestamp": str(uuid.uuid4()),
        },
    )


@app.exception_handler(ValidationException)
async def validation_handler(request: Request, exc: ValidationException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": True,
            "code": "VALIDATION_ERROR",
            "message": exc.detail,
            "detail": None,
            "timestamp": str(uuid.uuid4()),
        },
    )


@app.exception_handler(RateLimitedException)
async def rate_limited_handler(request: Request, exc: RateLimitedException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": True,
            "code": "RATE_LIMITED",
            "message": exc.detail,
            "detail": None,
            "timestamp": str(uuid.uuid4()),
        },
    )


@app.exception_handler(DuplicateResourceException)
async def duplicate_handler(request: Request, exc: DuplicateResourceException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": True,
            "code": "DUPLICATE_RESOURCE",
            "message": exc.detail,
            "detail": None,
            "timestamp": str(uuid.uuid4()),
        },
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": True,
            "code": "INTERNAL_ERROR",
            "message": "An unexpected error occurred",
            "detail": None,
            "timestamp": str(uuid.uuid4()),
        },
    )
