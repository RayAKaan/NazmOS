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

_engine_kwargs: dict = {
    "echo": settings.ENVIRONMENT == "development",
}
if _is_sqlite:
    _engine_kwargs["connect_args"] = {"check_same_thread": False}
else:
    _engine_kwargs.update({
        "pool_pre_ping": True,
        "pool_size": 10,
        "max_overflow": 20,
    })

engine = create_async_engine(settings.DATABASE_URL, **_engine_kwargs)

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
        from sqlalchemy import create_engine
        if _is_sqlite:
            sync_database_url = settings.DATABASE_URL.replace("+aiosqlite", "")
        else:
            sync_database_url = settings.DATABASE_URL.replace("+asyncpg", "")
        sync_kwargs = {}
        if not _is_sqlite:
            sync_kwargs.update({"pool_pre_ping": True, "pool_size": 5})
        _sync_engine = create_engine(sync_database_url, **sync_kwargs)
    return _sync_engine


async def _set_rls_context(session: AsyncSession) -> None:
    """Set tenant context and optionally switch to the restricted app role."""
    tenant_id = get_rls_tenant_id()
    if tenant_id:
        # SET LOCAL cannot use bound parameters with asyncpg, so we inline the
        # validated UUID string.  This is safe because the value is either a
        # trusted UUID or None.
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
def get_sync_session():
    """Synchronous session for Celery background tasks."""
    from sqlalchemy.orm import Session
    session = Session(_get_sync_engine())
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
