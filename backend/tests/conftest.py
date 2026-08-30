import asyncio
import os
import socket
from typing import AsyncGenerator
from urllib.parse import urlparse

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

# Allow the test database endpoint to be overridden (e.g. when running the
# suite inside a container where `postgres` is the docker-network hostname).
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://nazmos:nazmos_dev@localhost:5432/nazmos_test",
)

# Route the application-level engine (used by code that opens its own session,
# e.g. access-denial audit writes and Celery-style background paths) at the same
# database the test fixtures use. Without this the app engine would try the dev
# database with default credentials and those writes would fail mid-test. Env
# vars win over defaults in pydantic-settings, so this MUST run before any app
# module is imported (the imports below) so get_settings() bakes it in.
if not os.environ.get("DATABASE_URL"):
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL

from app.main import app
from app.database.models import Base
from app.database.connection import get_db


def _postgres_available(host: str | None = None, port: int | None = None, timeout: float = 0.35) -> bool:
    # Derive host/port from TEST_DATABASE_URL if not provided, so the probe
    # follows the same endpoint the tests actually connect to (important when
    # running inside a container where `localhost` is not the database host).
    if host is None or port is None:
        url = TEST_DATABASE_URL.replace("+asyncpg", "")
        try:
            parsed = urlparse(url)
            host = host or parsed.hostname or "localhost"
            port = port or (parsed.port or 5432)
        except Exception:
            host = host or "localhost"
            port = port or 5432
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="function")
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    if not _postgres_available():
        pytest.skip("Postgres test database is not available on localhost:5432; skipping DB integration test.")

    # Engine-per-test avoids asyncpg pooled connections tied to stale event loops.
    test_engine = create_async_engine(TEST_DATABASE_URL, echo=False, poolclass=NullPool)
    TestSessionLocal = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)

    # Reset the schema in a circular-FK-safe way. The model metadata contains a
    # mutual FK cycle (agent_actions.finding_id <-> findings.agent_action_id); a
    # plain `Base.metadata.drop_all` cannot topological-sort such a cycle without
    # named constraints and fails with CircularDependencyError. Resetting the
    # `public` schema via CASCADE avoids that and still runs against the real
    # PostgreSQL test database (no SQLite substitution).
    async with test_engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.run_sync(Base.metadata.create_all)

    async with TestSessionLocal() as session:
        yield session

    async with test_engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
    await test_engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture(scope="function")
async def authenticated_client(client: AsyncClient) -> dict:
    """Return an authenticated client + business context for router tests.

    Creates a fresh user, logs in, and bootstraps a single business so tests
    have a real, accessible business_id instead of hard-coded UUIDs.
    """
    email = "test_user@example.com"
    password = "TestPass123!"
    full_name = "Test User"

    register_response = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "full_name": full_name},
    )
    if register_response.status_code not in (200, 201):
        raise RuntimeError(f"Registration failed: {register_response.text}")

    login_response = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    if login_response.status_code != 200:
        raise RuntimeError(f"Login failed: {login_response.text}")

    token = login_response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    bootstrap_response = await client.post(
        "/api/v1/businesses/bootstrap",
        json={"name": "Test Baqala", "type": "baqala", "city": "Riyadh"},
        headers=headers,
    )
    if bootstrap_response.status_code != 200:
        raise RuntimeError(f"Business bootstrap failed: {bootstrap_response.text}")

    business_id = bootstrap_response.json()["id"]
    return {
        "client": client,
        "token": token,
        "business_id": business_id,
        "headers": headers,
    }
