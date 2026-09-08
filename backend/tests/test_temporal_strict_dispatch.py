"""Strict-dispatch tests — Temporal failures must never downgrade to local.

Phase 1 blocker: the dispatch layer previously swallowed Temporal connection
failures and executed workflows locally (a silent production downgrade). These
tests lock the replacement contract:

  A. Temporal selected + server unavailable -> explicit ``TemporalExecutionError``
  B. the local deterministic runner is NOT invoked on the Temporal path
  C. a failed Temporal dispatch performs NO business mutation
  D. the local deterministic runner works only when explicitly selected
     (``USE_TEMPORAL=false``) — dev / test mode
  E. production configuration cannot select the local runner
     (``USE_TEMPORAL=false`` is rejected when ``ENVIRONMENT=production``)

Plus a static AST lock: ``runner._dispatch`` never contains an exception
handler that falls back to ``_local_run``.
"""
from __future__ import annotations

import ast
import json
import os
import pathlib
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database.models import Base
from app.orchestration import runner
from app.orchestration.runner import TemporalExecutionError, run_manual_action

RUNNER_PY = pathlib.Path(runner.__file__)

_TEST_ENV_KEYS = [
    "USE_TEMPORAL",
    "TEMPORAL_ADDRESS",
    "TEMPORAL_NAMESPACE",
    "TEMPORAL_TASK_QUEUE",
    "TEMPORAL_CONNECT_TIMEOUT_SECONDS",
    "ENVIRONMENT",
    "DATABASE_URL",
    "SECRET_KEY",
    "SENTRY_DSN",
    "USE_MOCK_LLM",
    "GROQ_API_KEY",
    "GOOGLE_AI_API_KEY",
    "CORS_ORIGINS",
    "WHATSAPP_ENABLED",
    "CREDENTIAL_MASTER_KEY",
]

_PROD_REQUIRED_ENV = {
    "ENVIRONMENT": "production",
    "DATABASE_URL": "postgresql+asyncpg://nazmos:nazmos_dev@localhost:5432/nazmos",
    "SECRET_KEY": "prod-test-key-0123456789abcdef-0123456789",
    "SENTRY_DSN": "https://example.sentry.io/test/1",
    "USE_MOCK_LLM": "false",
    "GROQ_API_KEY": "test-key",
    "CORS_ORIGINS": "https://app.nazm.ai",
    "WHATSAPP_ENABLED": "mock",
    "CREDENTIAL_MASTER_KEY": "0123456789abcdef0123456789abcdef",
    "DATABASE_APP_ROLE": "nazmos_app_role",
}


@pytest.fixture(autouse=True)
def _clean_settings_env(monkeypatch):
    """Isolate every test against get_settings()'s lru_cache + env snapshot."""
    saved = {k: os.environ.get(k) for k in _TEST_ENV_KEYS}
    from app.config import get_settings

    get_settings.cache_clear()
    yield
    for k in _TEST_ENV_KEYS:
        if saved.get(k) is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = saved[k]
    get_settings.cache_clear()


@pytest.fixture
def temporal_down_env(monkeypatch):
    """Postgres-shaped settings URL + USE_TEMPORAL=true + dead Temporal address."""
    monkeypatch.setenv("USE_TEMPORAL", "true")
    monkeypatch.setenv("TEMPORAL_ADDRESS", "127.0.0.1:1")
    monkeypatch.setenv("TEMPORAL_CONNECT_TIMEOUT_SECONDS", "2")
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+asyncpg://nazmos:nazmos_dev@localhost:5432/nazmos",
    )


@pytest_asyncio.fixture(scope="function")
async def sqlite_session() -> AsyncSession:
    """In-memory SQLite session over the real Base.metadata schema."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with SessionLocal() as session:
        yield session
    await engine.dispose()


async def _seed_business(db: AsyncSession, business_id):
    await db.execute(
        text(
            "INSERT INTO businesses (id, name, type, currency, constraints_json) "
            "VALUES (:id, 'Strict Biz', 'retail', 'SAR', :constraints)"
        ),
        {"id": str(business_id), "constraints": json.dumps({})},
    )


async def _seed_item(db: AsyncSession, business_id, item_id, *, stock=50.0):
    await db.execute(
        text(
            "INSERT INTO items (id, business_id, name, sku, unit, cost_price, sell_price, is_active) "
            "VALUES (:id, :b, 'Widget', 'STR1', 'piece', 10, 20, true)"
        ),
        {"id": str(item_id), "b": str(business_id)},
    )
    await db.execute(
        text(
            "INSERT INTO inventory (id, item_id, business_id, current_stock, safety_stock, lead_time_days, updated_at) "
            "VALUES (:inv, :iid, :b, :stock, 5, 7, CURRENT_TIMESTAMP)"
        ),
        {"inv": str(uuid.uuid4()), "iid": str(item_id), "b": str(business_id), "stock": stock},
    )


async def _stock(db: AsyncSession, item_id) -> float:
    res = await db.execute(
        text("SELECT current_stock FROM inventory WHERE item_id = :i"),
        {"i": str(item_id)},
    )
    return float(res.scalar_one())


async def _executed_count(db: AsyncSession, business_id) -> int:
    res = await db.execute(
        text("SELECT count(*) FROM executed_actions WHERE business_id = :b"),
        {"b": str(business_id)},
    )
    return int(res.scalar_one())


def _manual_kwargs(business_id, item_id, qty=25.0):
    return dict(
        business_id=business_id,
        action_type="RESTOCK",
        entity_type="item",
        entity_id=item_id,
        payload={"restock_qty": qty},
        previous_state={"current_stock": 50.0},
        new_state={"restock_qty": qty},
        user_id=None,
        source="money_audit",
    )


# ── A / B / C: Temporal down → explicit failure, no local fallback, no mutation ──


@pytest.mark.asyncio
async def test_a_temporal_unavailable_is_explicit_failure(
    sqlite_session: AsyncSession, temporal_down_env
):
    """USE_TEMPORAL=true + unreachable server raises TemporalExecutionError."""
    biz, item = uuid.uuid4(), uuid.uuid4()
    await _seed_business(sqlite_session, biz)
    await _seed_item(sqlite_session, biz, item)
    await sqlite_session.commit()

    with pytest.raises(TemporalExecutionError) as excinfo:
        await run_manual_action(sqlite_session, **_manual_kwargs(biz, item))
    assert "Temporal execution failed" in str(excinfo.value)
    assert "workflow=manual_action" in str(excinfo.value)


@pytest.mark.asyncio
async def test_b_local_runner_never_invoked_on_temporal_path(
    sqlite_session: AsyncSession, temporal_down_env, monkeypatch
):
    """The local deterministic runner must NOT run when Temporal is selected."""
    calls: list[str] = []

    async def _forbidden_local_run(*args, **kwargs):
        calls.append("local_run")
        return {"forbidden": True}

    monkeypatch.setattr(runner, "_local_run", _forbidden_local_run)

    biz, item = uuid.uuid4(), uuid.uuid4()
    await _seed_business(sqlite_session, biz)
    await _seed_item(sqlite_session, biz, item)
    await sqlite_session.commit()

    with pytest.raises(TemporalExecutionError):
        await run_manual_action(sqlite_session, **_manual_kwargs(biz, item))
    assert calls == [], "local runner must never be invoked as a downgrade path"


@pytest.mark.asyncio
async def test_c_temporal_failure_leaves_no_mutation(
    sqlite_session: AsyncSession, temporal_down_env
):
    """A failed Temporal dispatch performs zero business side effects."""
    biz, item = uuid.uuid4(), uuid.uuid4()
    await _seed_business(sqlite_session, biz)
    await _seed_item(sqlite_session, biz, item, stock=50.0)
    await sqlite_session.commit()

    with pytest.raises(TemporalExecutionError):
        await run_manual_action(sqlite_session, **_manual_kwargs(biz, item))

    assert await _stock(sqlite_session, item) == 50.0, "no inventory change on Temporal failure"
    assert await _executed_count(sqlite_session, biz) == 0, "no execution record on Temporal failure"


# ── D: explicit local / dev mode still works ───────────────────────────


@pytest.mark.asyncio
async def test_d_explicit_local_dev_mode_works(sqlite_session: AsyncSession, monkeypatch):
    """USE_TEMPORAL=false (explicit dev/test selection) runs locally and mutates."""
    monkeypatch.setenv("USE_TEMPORAL", "false")
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+asyncpg://nazmos:nazmos_dev@localhost:5432/nazmos",
    )

    biz, item = uuid.uuid4(), uuid.uuid4()
    await _seed_business(sqlite_session, biz)
    await _seed_item(sqlite_session, biz, item, stock=50.0)
    await sqlite_session.commit()

    result = await run_manual_action(sqlite_session, **_manual_kwargs(biz, item))
    await sqlite_session.commit()
    assert result.success is True, result.message
    assert await _stock(sqlite_session, item) == 75.0
    assert await _executed_count(sqlite_session, biz) == 1


# ── E: production cannot select the local runner ───────────────────────


def test_e_production_rejects_local_downgrade(monkeypatch):
    """ENVIRONMENT=production + USE_TEMPORAL=false must fail configuration."""
    from app.config import Settings, get_settings

    monkeypatch.delenv("USE_TEMPORAL", raising=False)
    monkeypatch.setenv("USE_TEMPORAL", "false")
    for key, value in _PROD_REQUIRED_ENV.items():
        monkeypatch.setenv(key, value)

    with pytest.raises(ValueError, match="USE_TEMPORAL must be true in production"):
        Settings()

    get_settings.cache_clear()
    with pytest.raises(ValueError, match="USE_TEMPORAL must be true in production"):
        get_settings()


def test_e_production_allows_temporal_substrate(monkeypatch):
    """ENVIRONMENT=production + USE_TEMPORAL=true + TEMPORAL_ADDRESS is valid."""
    from app.config import get_settings

    monkeypatch.setenv("USE_TEMPORAL", "true")
    monkeypatch.setenv("TEMPORAL_ADDRESS", "temporal:7233")
    for key, value in _PROD_REQUIRED_ENV.items():
        monkeypatch.setenv(key, value)

    settings = get_settings()
    assert settings.USE_TEMPORAL is True
    assert settings.TEMPORAL_ADDRESS == "temporal:7233"
    assert settings.TEMPORAL_TASK_QUEUE == "nazm-execution"


# ── Static lock: no fallback branch may exist in _dispatch ─────────────


def test_dispatch_ast_has_no_fallback_branch():
    """``runner._dispatch`` must contain no exception handler at all.

    The no-silent-downgrade contract is so load-bearing that we also verify it
    statically: the presence of any Try/except in ``_dispatch`` adjacent to a
    ``_local_run`` call is a regression in the fallback contract.
    """
    tree = ast.parse(RUNNER_PY.read_text(encoding="utf-8"))
    dispatch = next(
        node for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "_dispatch"
    )
    handlers = [
        node
        for node in ast.walk(dispatch)
        if isinstance(node, (ast.Try, ast.ExceptHandler))
    ]
    assert handlers == [], "dispatch must contain no try/except fallback path"