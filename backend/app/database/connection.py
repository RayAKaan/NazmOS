from contextlib import contextmanager, asynccontextmanager
from contextvars import ContextVar, Token

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from app.config import get_settings

settings = get_settings()

_is_sqlite = settings.DATABASE_URL.startswith("sqlite")

# Per-request tenant context for PostgreSQL Row-Level Security.  Set by the
# TenantContextMiddleware and consumed by get_session()/async_session_scope().
_rls_tenant_id: ContextVar[str | None] = ContextVar("rls_tenant_id", default=None)


def set_rls_tenant_id(tenant_id: str | None) -> Token:
    return _rls_tenant_id.set(tenant_id)


def get_rls_tenant_id() -> str | None:
    return _rls_tenant_id.get()


def clear_rls_tenant_id() -> None:
    _rls_tenant_id.set(None)


def _sanitize_tenant_id(tenant_id: str | None) -> str | None:
    """Validate a tenant id for safe use inside a ``SET LOCAL`` literal.

    ``SET LOCAL app.current_tenant_id = '<tenant_id>'`` cannot use bound
    parameters with asyncpg, so the value is inlined.  Rejecting quote /
    comment / control characters prevents anything other than a clean
    identifier (a UUID in practice) from reaching the SQL text.
    """
    if tenant_id is None:
        return None
    value = str(tenant_id).strip()
    if not value:
        return None
    for ch in ("'", '"', "\\", ";", "--", "\n", "\r", "/*", "*/"):
        if ch in value:
            raise ValueError(f"Invalid tenant identifier {value!r}")
    return value


@contextmanager
def sync_rls_tenant_context(tenant_id: str | None):
    """Scope background/sync execution to a single tenant via RLS.

    Celery tasks, thread-pool executors, and CLI jobs have no HTTP request, so
    nothing sets the tenant ContextVar.  Wrapping a task body in this context
    makes every session created inside (``get_sync_session`` and
    ``AsyncSessionLocal`` alike) inherit the tenant: the sync engine begin
    listener and the async ``_set_rls_context`` both apply
    ``SET LOCAL app.current_tenant_id`` at the start of every transaction.

    ``None`` is a no-op (supervisor / cross-tenant sections keep whatever
    context was active).
    """
    if tenant_id is None:
        yield
        return
    from uuid import UUID
    try:
        UUID(str(tenant_id))
    except (TypeError, ValueError):
        raise ValueError(f"Tenant context requires a UUID business id, got {tenant_id!r}")
    token = _rls_tenant_id.set(str(tenant_id))
    try:
        yield
    finally:
        _rls_tenant_id.reset(token)


def enforce_tenant_filter(business_id: str | None) -> str:
    """Validate and normalize a tenant (business_id) scope for a bulk operation.

    Postgres RLS is the primary isolation boundary in production; this guard is
    the defense-in-depth that also protects SQLite development, where RLS
    policies do not exist. It blocks unscoped bulk reads and any attempt to act
    outside the request's tenant context.
    """
    from app.utils.exceptions import TenantViolationError

    context_tenant = get_rls_tenant_id()
    if business_id is None or not str(business_id).strip():
        raise TenantViolationError("Missing business_id scope for tenant-scoped operation")
    scope = str(business_id)
    if context_tenant and scope != context_tenant:
        raise TenantViolationError("Cross-tenant access attempt blocked")
    return scope

_engine_kwargs: dict = {
    "echo": settings.ENVIRONMENT == "development",
}
if _is_sqlite:
    _engine_kwargs["connect_args"] = {"check_same_thread": False}
else:
    _engine_kwargs.update({
        "pool_pre_ping": True,
        "pool_size": getattr(settings, "DATABASE_POOL_SIZE", 10),
        "max_overflow": getattr(settings, "DATABASE_MAX_OVERFLOW", 20),
        "pool_recycle": getattr(settings, "DATABASE_POOL_RECYCLE", 1800),
        "pool_timeout": getattr(settings, "DATABASE_POOL_TIMEOUT", 30),
    })

engine = create_async_engine(settings.DATABASE_URL, **_engine_kwargs)

if not _is_sqlite:
    from sqlalchemy import event

    @event.listens_for(engine.sync_engine, "begin")
    def _after_begin(conn):
        """Re-apply tenant context on every transaction begin.

        ``SET LOCAL`` is scoped to the current transaction, so code that commits
        mid-request (e.g. agent action approval) would otherwise lose the RLS
        tenant context on the next statement.  Re-issuing the SET LOCAL at the
        start of each transaction keeps ``app.current_tenant_id`` (and the
        restricted app role) active for the whole request regardless of commit
        points.
        """
        tenant_id = _sanitize_tenant_id(get_rls_tenant_id())
        if tenant_id:
            conn.exec_driver_sql(
                f"SET LOCAL app.current_tenant_id = '{tenant_id}'"
            )
        if settings.DATABASE_APP_ROLE:
            conn.exec_driver_sql(
                f'SET LOCAL ROLE "{settings.DATABASE_APP_ROLE}"'
            )

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

# Lazy sync engine for Celery workers (created on first use)
_sync_engine = None


def _get_sync_engine():
    global _sync_engine
    if _sync_engine is None:
        from sqlalchemy import create_engine, event
        if _is_sqlite:
            sync_database_url = settings.DATABASE_URL.replace("+aiosqlite", "")
        else:
            sync_database_url = settings.DATABASE_URL.replace("+asyncpg", "")
        sync_kwargs = {}
        if not _is_sqlite:
            sync_kwargs.update({"pool_pre_ping": True, "pool_size": 5})
        _sync_engine = create_engine(sync_database_url, **sync_kwargs)
        if not _is_sqlite:
            @event.listens_for(_sync_engine, "begin")
            def _after_sync_begin(conn):
                """Re-apply RLS tenant context on every sync transaction begin.

                Mirrors the async engine listener so Celery/background sessions
                opened without an explicit ``_set_rls_context`` still inherit
                the tenant context set by ``sync_rls_tenant_context``.
                """
                tenant_id = _sanitize_tenant_id(get_rls_tenant_id())
                if tenant_id:
                    conn.exec_driver_sql(
                        f"SET LOCAL app.current_tenant_id = '{tenant_id}'"
                    )
                if settings.DATABASE_APP_ROLE:
                    conn.exec_driver_sql(
                        f'SET LOCAL ROLE "{settings.DATABASE_APP_ROLE}"'
                    )
    return _sync_engine


async def _set_rls_context(session: AsyncSession) -> None:
    """Set tenant context and optionally switch to the restricted app role."""
    tenant_id = _sanitize_tenant_id(get_rls_tenant_id())
    if tenant_id:
        # SET LOCAL cannot use bound parameters with asyncpg, so we inline the
        # validated tenant string.  _sanitize_tenant_id rejects every character
        # that could break out of the literal.
        await session.execute(
            __import__("sqlalchemy").text(
                f"SET LOCAL app.current_tenant_id = '{tenant_id}'"
            )
        )
    if settings.DATABASE_APP_ROLE:
        # Quoted identifier prevents SQL injection via config.
        await session.execute(
            __import__("sqlalchemy").text(
                f'SET LOCAL ROLE "{settings.DATABASE_APP_ROLE}"'
            )
        )


async def get_session():
    """Async generator for FastAPI dependency injection."""
    async with AsyncSessionLocal() as session:
        if _is_sqlite:
            await session.execute(
                __import__("sqlalchemy").text("PRAGMA journal_mode=WAL")
            )
        else:
            await _set_rls_context(session)
        try:
            yield session
        finally:
            await session.close()


get_db = get_session


@asynccontextmanager
async def async_session_scope():
    """Async context manager for direct use outside of FastAPI dependencies."""
    async with AsyncSessionLocal() as session:
        if _is_sqlite:
            await session.execute(
                __import__("sqlalchemy").text("PRAGMA journal_mode=WAL")
            )
        else:
            await _set_rls_context(session)
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@contextmanager
def get_sync_session(tenant_id: str | None = None):
    """Synchronous session for Celery background tasks.

    Pass ``tenant_id`` (a business UUID) to scope the session AND any sibling
    sessions created while the context is active (e.g. the fresh async engine
    used by the ETL pipeline) to that tenant via Postgres RLS.  Omit it to run
    as a supervisor (cross-tenant scheduled work).
    """
    from sqlalchemy.orm import Session
    session = Session(_get_sync_engine())
    with sync_rls_tenant_context(tenant_id):
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


class DatabaseManager:
    """Small compatibility facade for health/chaos tests and ops probes."""

    async def connect(self):
        async with engine.connect() as conn:
            return conn

    def get_session(self):
        return AsyncSessionLocal()

    async def disconnect(self):
        await engine.dispose()
