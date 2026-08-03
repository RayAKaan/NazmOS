import asyncio
import socket
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.main import app
from app.database.models import Base
from app.database.connection import get_db

TEST_DATABASE_URL = "postgresql+asyncpg://nazmos:nazmos_dev@localhost:5432/nazmos_test"


def _postgres_available(host: str = "localhost", port: int = 5432, timeout: float = 0.35) -> bool:
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

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    async with TestSessionLocal() as session:
        yield session

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
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
