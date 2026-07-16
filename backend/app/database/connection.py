from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from app.config import get_settings

settings = get_settings()

_is_sqlite = settings.DATABASE_URL.startswith("sqlite")

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


async def get_session():
    async with AsyncSessionLocal() as session:
        if _is_sqlite:
            await session.execute(
                __import__("sqlalchemy").text("PRAGMA journal_mode=WAL")
            )
        try:
            yield session
        finally:
            await session.close()

get_db = get_session


def get_sync_session():
    """Synchronous session for Celery background tasks."""
    from sqlalchemy.orm import Session
    with Session(_get_sync_engine()) as session:
        try:
            yield session
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
