from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from app.config import get_settings
from app.database import engine, Base, AsyncSessionLocal
from app.routers.pilot import router as pilot_router
from app.routers import (
    auth_router, businesses_router, dashboard_router, inventory_router, health_router,
    upload_router, chat_router, forecast_router, decisions_router, money_audit_router, ops_router,
    organizations_router, subscriptions_router, adapters_router, actions_router,
    agent_router, suppliers_router, pharmacy_router, whatsapp_router, partners_router,
    admin_backup_router, oauth_router,
    pos_webhooks_router, orchestrator_router, recovery_match_router, compliance_router, events_router,
    intelligence_router, guest_audit_router, audits_router,
)
from app.middleware.advanced_rate_limiter import RedisRateLimiter, InMemoryRateLimiter, AdvancedRateLimitMiddleware, get_rate_limiter
from app.middleware.logging_middleware import LoggingMiddleware
from app.middleware.security_headers import SecurityHeadersMiddleware
from app.middleware.idempotency import IdempotencyMiddleware
from app.middleware.rls_tenant import TenantContextMiddleware
from app.middleware.prometheus_metrics import PrometheusMiddleware, metrics_response
from app.middleware.api_version import APIVersionMiddleware
from app.middleware.deprecation import DeprecationMiddleware
from app.database.seed import seed_demo_data
from app.services.feature_flags import seed_default_flags
from app.utils.problem_details import problem_response
from app.utils.openapi_helpers import COMMON_ERROR_RESPONSES
from app.utils.logger import configure_global, setup_logger
from app.utils.tracing import init_tracing, instrument_fastapi, instrument_sqlalchemy
from app.utils.startup_checks import run_startup_checks
from app.utils.exceptions import (
    NotFoundException,
    UnauthorizedException,
    ForbiddenException,
    ValidationException,
    RateLimitedException,
    DuplicateResourceException,
)

settings = get_settings()
configure_global()
logger = setup_logger("app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting NazmOS API...")

    # Distributed tracing: initialize before Sentry so Sentry can attach trace context.
    init_tracing(service_name="nazmos-api")

    # Observability: Sentry is initialized as early as possible so it can capture
    # startup errors and unhandled exceptions in the async event loop.
    if settings.SENTRY_DSN:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

        sentry_sdk.init(
            dsn=settings.SENTRY_DSN,
            environment=settings.SENTRY_ENVIRONMENT or settings.ENVIRONMENT,
            traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE,
            profiles_sample_rate=settings.SENTRY_PROFILES_SAMPLE_RATE,
            integrations=[
                FastApiIntegration(),
                SqlalchemyIntegration(),
            ],
        )
        logger.info("Sentry error tracking initialized")

    # Trust warnings: fail-closed checks that make dangerous misconfigurations
    # visible immediately on startup rather than silently at runtime.
    if settings.ENVIRONMENT == "production":
        if settings.USE_MOCK_LLM:
            logger.warning(
                "MOCK_LLM_ENABLED_IN_PRODUCTION",
                extra={"detail": "USE_MOCK_LLM=true in production. Merchant-facing LLM responses are canned keyword matches, not a real model."},
            )
        if not settings.SENTRY_DSN:
            logger.warning(
                "SENTRY_NOT_CONFIGURED",
                extra={"detail": "SENTRY_DSN is empty in production. Uncaught exceptions will not be aggregated or alerted."},
            )
        if settings.DATABASE_URL.startswith("sqlite"):
            logger.error(
                "SQLITE_IN_PRODUCTION",
                extra={"detail": "SQLite is configured in production. NazmOS requires PostgreSQL for multi-tenant data integrity."},
            )
            raise RuntimeError("SQLite is not supported in production")
    else:
        logger.warning(
            "CREATE_ALL_DEV_ONLY",
            extra={"detail": "Development mode: auto-creating tables from models via Base.metadata.create_all. Production uses Alembic migrations; do not rely on create_all for schema changes."},
        )
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as session:
        try:
            await seed_default_flags(session)
            logger.info("Feature flags seeded successfully")
        except Exception as e:
            logger.warning(f"Feature flag seeding skipped: {e}")

    async with AsyncSessionLocal() as session:
        try:
            from app.services.event_registry_seed import seed_builtin_event_types
            await seed_builtin_event_types(session)
            logger.info("Event type registry seeded successfully")
        except Exception as e:
            logger.warning(f"Event type registry seeding skipped: {e}")

    async with AsyncSessionLocal() as session:
        try:
            await seed_demo_data(session)
            logger.info("Demo data seeded successfully")
        except Exception as e:
            logger.warning(f"Demo data seeding skipped: {e}")

    # Fail closed if Redis/Celery are required but unreachable.
    try:
        await run_startup_checks()
    except Exception as e:
        logger.error(f"Startup dependency check failed: {e}")
        raise

    yield

    logger.info("Shutting down NazmOS API...")
    await engine.dispose()


app = FastAPI(
    title="NazmOS API – Retail Recovery",
    description="Retail Recovery API for Saudi stores: Money Audits, stockout prevention, WhatsApp approvals, and Recovery Match preview.",
    version="2.1.0-ksa",
    lifespan=lifespan,
)

# OpenTelemetry instrumentation for FastAPI and SQLAlchemy.
instrument_fastapi(app)
instrument_sqlalchemy(engine)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.CORS_ORIGINS.split(",") if origin.strip()],
    allow_credentials=True,
    allow_methods=[method.strip() for method in settings.CORS_METHODS.split(",") if method.strip()],
    allow_headers=[
        "Accept",
        "Accept-Language",
        "Authorization",
        "Content-Type",
        "X-Request-ID",
        "X-Idempotency-Key",
        "X-API-Version",
    ],
)

app.add_middleware(APIVersionMiddleware)
app.add_middleware(DeprecationMiddleware)
app.add_middleware(LoggingMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(IdempotencyMiddleware)
app.add_middleware(TenantContextMiddleware)
app.add_middleware(PrometheusMiddleware)

@app.get("/metrics")
async def metrics_endpoint(request: Request):
    if settings.METRICS_TOKEN and request.headers.get("X-Metrics-Token") != settings.METRICS_TOKEN:
        return problem_response(
            status=401,
            title="Unauthorized",
            detail="Missing or invalid X-Metrics-Token header",
            request=request,
        )
    return metrics_response()

rate_limiter_instance = get_rate_limiter()
app.state.rate_limiter = rate_limiter_instance
app.add_middleware(AdvancedRateLimitMiddleware, limiter=rate_limiter_instance)
if isinstance(rate_limiter_instance, RedisRateLimiter):
    logger.info("Using Redis distributed rate limiter")
else:
    logger.info("Using in-memory rate limiter (development mode)")

app.include_router(health_router, prefix="/api/v1", responses=COMMON_ERROR_RESPONSES)
app.include_router(auth_router, prefix="/api/v1", responses=COMMON_ERROR_RESPONSES)
app.include_router(businesses_router, responses=COMMON_ERROR_RESPONSES)
app.include_router(dashboard_router, prefix="/api/v1", responses=COMMON_ERROR_RESPONSES)
app.include_router(inventory_router, prefix="/api/v1", responses=COMMON_ERROR_RESPONSES)
app.include_router(upload_router, responses=COMMON_ERROR_RESPONSES)
app.include_router(guest_audit_router, responses=COMMON_ERROR_RESPONSES)
app.include_router(audits_router, responses=COMMON_ERROR_RESPONSES)
app.include_router(forecast_router, responses=COMMON_ERROR_RESPONSES)
app.include_router(decisions_router, responses=COMMON_ERROR_RESPONSES)
app.include_router(money_audit_router, responses=COMMON_ERROR_RESPONSES)
app.include_router(ops_router, responses=COMMON_ERROR_RESPONSES)
app.include_router(compliance_router, responses=COMMON_ERROR_RESPONSES)
app.include_router(events_router, responses=COMMON_ERROR_RESPONSES)
app.include_router(intelligence_router, responses=COMMON_ERROR_RESPONSES)
app.include_router(pilot_router, responses=COMMON_ERROR_RESPONSES)

# Retail Recovery routers only.
app.include_router(pos_webhooks_router, responses=COMMON_ERROR_RESPONSES)
app.include_router(orchestrator_router, responses=COMMON_ERROR_RESPONSES)
if recovery_match_router is not None:
    app.include_router(recovery_match_router, responses=COMMON_ERROR_RESPONSES)
logger.info("✓ NazmOS Retail Recovery enabled (Money Audit, POS Webhooks, WhatsApp approvals, Recovery Match preview)")

# Nazm Agent – KSA Agent OS – $0 LLM
if getattr(settings, "AGENT_ENABLED", True) and agent_router is not None:
    app.include_router(agent_router, responses=COMMON_ERROR_RESPONSES)
    logger.info("✓ Nazm Agent API enabled – /api/v1/agent/feed")
else:
    logger.info("Nazm Agent API disabled")

# Supplier Network – two-sided moat
if suppliers_router is not None:
    app.include_router(suppliers_router, responses=COMMON_ERROR_RESPONSES)
    logger.info("✓ Supplier Network API enabled")

# Partner program – accountants / Monshaat advisors
if partners_router is not None:
    app.include_router(partners_router, responses=COMMON_ERROR_RESPONSES)
    logger.info("✓ Partner program API enabled")

# Admin backups
if admin_backup_router is not None:
    app.include_router(admin_backup_router, responses=COMMON_ERROR_RESPONSES)
    logger.info("✓ Admin backup API enabled")

# OAuth connectors
if oauth_router is not None:
    app.include_router(oauth_router, responses=COMMON_ERROR_RESPONSES)
    logger.info("✓ OAuth connector API enabled")

# Pharmacy Vertical – FEFO / SFDA
if pharmacy_router is not None and getattr(settings, "VERTICAL_PHARMACY", True):
    app.include_router(pharmacy_router, responses=COMMON_ERROR_RESPONSES)
    logger.info("✓ Pharmacy module enabled – expiry/FEFO/SFDA")

# WhatsApp – approval bridge – always on (mock mode = $0)
if whatsapp_router is not None:
    app.include_router(whatsapp_router, responses=COMMON_ERROR_RESPONSES)
    logger.info("✓ WhatsApp webhook enabled – /api/v1/whatsapp/webhook")

# Chat / Baseer – disabled by default for implementation sales
if settings.CHAT_ENABLED:
    app.include_router(chat_router, responses=COMMON_ERROR_RESPONSES)
    logger.info("Baseer Chat API enabled")
else:
    logger.info("Baseer Chat API disabled – KSA Lite mode")

@app.get("/health")
async def root_health():
    return {"status": "healthy", "service": "nazmos-api"}


# Billing / SaaS – disabled for one-time implementation model
if settings.BILLING_ENABLED:
    app.include_router(subscriptions_router, responses=COMMON_ERROR_RESPONSES)
    app.include_router(organizations_router, responses=COMMON_ERROR_RESPONSES)
    app.include_router(adapters_router, responses=COMMON_ERROR_RESPONSES)
    app.include_router(actions_router, responses=COMMON_ERROR_RESPONSES)
    logger.info("Billing/SaaS routers enabled")
else:
    logger.info("Billing/SaaS routers disabled – KSA Implementation mode")


@app.exception_handler(NotFoundException)
async def not_found_handler(request: Request, exc: NotFoundException):
    return problem_response(
        status=exc.status_code,
        title="Not Found",
        detail=exc.detail,
        request=request,
    )


@app.exception_handler(UnauthorizedException)
async def unauthorized_handler(request: Request, exc: UnauthorizedException):
    return problem_response(
        status=exc.status_code,
        title="Unauthorized",
        detail=exc.detail,
        request=request,
    )


@app.exception_handler(ForbiddenException)
async def forbidden_handler(request: Request, exc: ForbiddenException):
    return problem_response(
        status=exc.status_code,
        title="Forbidden",
        detail=exc.detail,
        request=request,
    )


@app.exception_handler(ValidationException)
async def validation_handler(request: Request, exc: ValidationException):
    return problem_response(
        status=exc.status_code,
        title="Validation Error",
        detail=exc.detail,
        request=request,
    )


@app.exception_handler(RateLimitedException)
async def rate_limited_handler(request: Request, exc: RateLimitedException):
    return problem_response(
        status=exc.status_code,
        title="Rate Limited",
        detail=exc.detail,
        request=request,
    )


@app.exception_handler(DuplicateResourceException)
async def duplicate_handler(request: Request, exc: DuplicateResourceException):
    return problem_response(
        status=exc.status_code,
        title="Duplicate Resource",
        detail=exc.detail,
        request=request,
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return problem_response(
        status=500,
        title="Internal Server Error",
        detail="An unexpected error occurred",
        request=request,
    )
