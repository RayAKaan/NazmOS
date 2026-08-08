"""Tests for the tenant-scoped idempotency cache (Phase 1.5).

Verifies the model-level unique scope isolates tenants and that the middleware
threads the resolved tenant into the cache SQL.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import select, text

from app.database.models import Base, IdempotencyKey
from app.middleware.idempotency import (
    IdempotencyMiddleware,
    NO_TENANT,
    _business_scope,
)

TENANT_A = str(uuid.uuid4())
TENANT_B = str(uuid.uuid4())
KEY = "req-123"
METHOD = "POST"
PATH = "/api/v1/items"


@pytest.fixture
async def sqlite_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as session:
        yield session
    await engine.dispose()


async def _insert(session, business_id: str, idempotency_key: str = KEY):
    session.add(
        IdempotencyKey(
            business_id=business_id,
            idempotency_key=idempotency_key,
            scope_method=METHOD,
            scope_path=PATH,
            request_hash="abc",
            response_status=200,
            response_body='{"ok": true}',
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
    )
    await session.commit()


async def _count(session, business_id: str) -> int:
    result = await session.execute(
        select(IdempotencyKey).where(
            IdempotencyKey.business_id == business_id,
            IdempotencyKey.idempotency_key == KEY,
        )
    )
    return len(result.scalars().all())


async def test_same_key_different_tenants_coexist(sqlite_session):
    await _insert(sqlite_session, TENANT_A)
    await _insert(sqlite_session, TENANT_B)

    assert await _count(sqlite_session, TENANT_A) == 1
    assert await _count(sqlite_session, TENANT_B) == 1


async def test_same_tenant_same_key_conflicts(sqlite_session):
    from sqlalchemy.exc import IntegrityError

    await _insert(sqlite_session, TENANT_A)
    with pytest.raises(IntegrityError):
        await _insert(sqlite_session, TENANT_A)


async def test_same_key_different_path_same_tenant_coexists(sqlite_session):
    await _insert(sqlite_session, TENANT_A)
    session2 = sqlite_session
    session2.add(
        IdempotencyKey(
            business_id=TENANT_A,
            idempotency_key=KEY,
            scope_method=METHOD,
            scope_path=PATH + "/bulk",
            request_hash="def",
            response_status=200,
            response_body="{}",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
    )
    await session2.commit()
    # Original (key, method, path) row is still unique and present.
    result = await session2.execute(
        select(IdempotencyKey).where(
            IdempotencyKey.business_id == TENANT_A,
            IdempotencyKey.idempotency_key == KEY,
            IdempotencyKey.scope_path == PATH,
        )
    )
    assert len(result.scalars().all()) == 1


def test_business_scope_uses_rls_tenant(monkeypatch):
    monkeypatch.setattr("app.middleware.idempotency.get_rls_tenant_id", lambda: TENANT_A)
    assert _business_scope(None) == TENANT_A


def test_business_scope_falls_back_to_sentinel(monkeypatch):
    monkeypatch.setattr("app.middleware.idempotency.get_rls_tenant_id", lambda: None)
    assert _business_scope(None) == NO_TENANT


async def test_lookup_sql_scoped_by_business(monkeypatch):
    captured = {}

    class FakeResult:
        def fetchone(self):
            return None

    class FakeSession:
        def __init__(self):
            self.result = None

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def execute(self, stmt, params):
            captured["sql"] = str(stmt)
            captured["params"] = params
            return FakeResult()

    class FakeScope:
        async def __aenter__(self):
            return FakeSession()

        async def __aexit__(self, *args):
            return False

    monkeypatch.setattr("app.middleware.idempotency.async_session_scope", FakeScope)
    mw = IdempotencyMiddleware(app=object())
    await mw._lookup_cache(KEY, METHOD, PATH, TENANT_A)

    assert "business_id = :business_id" in captured["sql"]
    assert captured["params"]["business_id"] == TENANT_A


async def test_store_sql_scoped_by_business(monkeypatch):
    captured = {}

    class FakeSession:
        def __init__(self):
            self.result = None

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def execute(self, stmt, params):
            captured["sql"] = str(stmt)
            captured["params"] = params

        async def commit(self):
            pass

    class FakeScope:
        async def __aenter__(self):
            return FakeSession()

        async def __aexit__(self, *args):
            return False

    monkeypatch.setattr("app.middleware.idempotency.async_session_scope", FakeScope)
    mw = IdempotencyMiddleware(app=object())
    request = _fake_request()

    await mw._store_cache(
        idempotency_key=KEY,
        method=METHOD,
        scope_path=PATH,
        business_id=TENANT_A,
        request=request,
        response_status=200,
        response_body='{"ok": true}',
    )

    assert "ON CONFLICT (business_id, idempotency_key, scope_method, scope_path)" in captured["sql"]
    assert "business_id" in captured["params"]
    assert captured["params"]["business_id"] == TENANT_A


def _fake_request():
    scope = {
        "type": "http",
        "method": METHOD,
        "path": PATH,
        "raw_path": PATH.encode(),
        "headers": [],
        "query_string": b"",
        "client": ("1.2.3.4", 1234),
        "scheme": "http",
        "server": ("test", 80),
        "app": None,
        "route": None,
    }
    from fastapi import Request

    return Request(scope)
