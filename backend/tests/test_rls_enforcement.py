"""Prove that PostgreSQL Row-Level Security isolates tenant rows.

This test runs the full Alembic migration chain (including RLS policies and
``nazmos_app`` role creation) against a disposable schema in the test database,
then verifies that:

1. The table owner bypasses RLS and sees all rows.
2. When the application issues ``SET ROLE nazmos_app`` and sets
   ``app.current_tenant_id`` to a single tenant, only that tenant's rows are
   visible.

This is the production enforcement path: the app connects as the migration
owner but assumes the restricted role so RLS policies are active.
"""
import os
import subprocess
import uuid
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import get_settings
from app.database import connection as connection_mod


TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://nazmos:nazmos_dev@localhost:5432/nazmos_test",
)
APP_ROLE = "nazmos_app"


def _run_alembic_upgrade() -> None:
    """Run ``alembic upgrade head`` in the backend directory."""
    import sys

    backend_dir = os.path.join(os.path.dirname(__file__), "..")
    env = os.environ.copy()
    env["DATABASE_URL"] = TEST_DATABASE_URL
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=backend_dir,
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Alembic upgrade failed:\n{result.stdout}\n{result.stderr}")


@pytest.fixture(scope="module")
def rls_engine():
    """Create a migrated test schema with RLS policies and app role."""
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)

    async def setup():
        async with engine.begin() as conn:
            # Drop everything in public to get a clean slate, then recreate it.
            await conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
            await conn.execute(text("CREATE SCHEMA public"))
            await conn.execute(text("GRANT ALL ON SCHEMA public TO nazmos"))
            await conn.execute(text("GRANT ALL ON SCHEMA public TO public"))
        await engine.dispose()

    import asyncio
    asyncio.run(setup())
    _run_alembic_upgrade()

    # Re-create engine after schema recreation.
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    yield engine

    async def teardown():
        async with engine.begin() as conn:
            await conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
            await conn.execute(text("CREATE SCHEMA public"))
        await engine.dispose()

    asyncio.run(teardown())


@pytest_asyncio.fixture(scope="function")
async def rls_session(rls_engine) -> AsyncGenerator[AsyncSession, None]:
    SessionLocal = async_sessionmaker(rls_engine, class_=AsyncSession, expire_on_commit=False)
    async with SessionLocal() as session:
        yield session


@pytest_asyncio.fixture(scope="function")
def app_role_enabled(monkeypatch):
    """Patch connection settings so sessions will SET ROLE nazmos_app."""
    settings = get_settings()
    monkeypatch.setattr(settings, "DATABASE_APP_ROLE", APP_ROLE)
    monkeypatch.setattr(connection_mod, "settings", settings)


async def _seed_two_businesses(session: AsyncSession) -> tuple[str, str, str, str]:
    """Create two businesses, each with one item. Returns (bus_a, bus_b, item_a, item_b)."""
    bus_a = str(uuid.uuid4())
    bus_b = str(uuid.uuid4())
    item_a = str(uuid.uuid4())
    item_b = str(uuid.uuid4())

    await session.execute(
        text("""
            INSERT INTO users (id, email, password_hash, full_name, role, is_active)
            VALUES (:id, :email, 'hash', 'Owner', 'owner', true)
        """),
        {"id": str(uuid.uuid4()), "email": f"rls_owner_{uuid.uuid4().hex[:8]}@example.com"},
    )

    await session.execute(
        text("INSERT INTO businesses (id, name, type, currency) VALUES (:id, 'A', 'retail', 'SAR')"),
        {"id": bus_a},
    )
    await session.execute(
        text("INSERT INTO businesses (id, name, type, currency) VALUES (:id, 'B', 'retail', 'SAR')"),
        {"id": bus_b},
    )

    await session.execute(
        text("""
            INSERT INTO items (id, business_id, name, sku, unit, cost_price, sell_price, is_active)
            VALUES (:id, :business_id, 'Item A', 'A-001', 'piece', 10, 20, true)
        """),
        {"id": item_a, "business_id": bus_a},
    )
    await session.execute(
        text("""
            INSERT INTO items (id, business_id, name, sku, unit, cost_price, sell_price, is_active)
            VALUES (:id, :business_id, 'Item B', 'B-001', 'piece', 10, 20, true)
        """),
        {"id": item_b, "business_id": bus_b},
    )
    await session.commit()
    return bus_a, bus_b, item_a, item_b


@pytest.mark.asyncio
async def test_owner_bypasses_rls(rls_session: AsyncSession):
    """Sanity check: owner connection sees rows from both tenants."""
    bus_a, bus_b, item_a, item_b = await _seed_two_businesses(rls_session)

    result = await rls_session.execute(text("SELECT id, business_id FROM items ORDER BY name"))
    rows = result.fetchall()
    ids = {str(r.id) for r in rows}
    assert {item_a, item_b}.issubset(ids), "Owner should see both items"


@pytest.mark.asyncio
async def test_app_role_isolates_tenant_rows(
    rls_engine, app_role_enabled, monkeypatch
):
    """With SET ROLE nazmos_app + tenant context, only tenant A rows are visible."""
    SessionLocal = async_sessionmaker(rls_engine, class_=AsyncSession, expire_on_commit=False)

    # Seed as owner.
    async with SessionLocal() as owner_session:
        bus_a, bus_b, item_a, item_b = await _seed_two_businesses(owner_session)

    # Now open a session that will assume the restricted role and tenant A.
    async with SessionLocal() as restricted_session:
        # The _set_rls_context helper reads the context var; set it for bus_a.
        from app.database.connection import set_rls_tenant_id
        token = set_rls_tenant_id(bus_a)
        try:
            await connection_mod._set_rls_context(restricted_session)
            result = await restricted_session.execute(
                text("SELECT id, business_id FROM items ORDER BY name")
            )
            rows = result.fetchall()
            ids = {str(r.id) for r in rows}
            assert item_a in ids, "Tenant A should see its own item"
            assert item_b not in ids, "Tenant A must not see tenant B item"
            assert len(ids) == 1, f"Expected exactly one row, got {ids}"
        finally:
            connection_mod._rls_tenant_id.reset(token)


@pytest.mark.asyncio
async def test_app_role_new_policies_isolate_findings(
    rls_engine, app_role_enabled, monkeypatch
):
    """WS2: the hardened findings/audit_runs/impact_ledger policies enforce
    row isolation AND reject cross-tenant inserts under SET ROLE nazmos_app."""
    SessionLocal = async_sessionmaker(rls_engine, class_=AsyncSession, expire_on_commit=False)

    async with SessionLocal() as owner_session:
        bus_a, bus_b, _, _ = await _seed_two_businesses(owner_session)
        # Seed one finding per tenant as the RLS-bypassing owner.
        for bid, label in ((bus_a, "A"), (bus_b, "B")):
            await owner_session.execute(
                text("""
                    INSERT INTO findings (id, business_id, domain, category, severity,
                                          title, status, source, created_at)
                    VALUES (:id, :b, 'inventory', 'stockout_risk', 'high',
                            :title, 'detected', 'audit_engine', NOW())
                """),
                {"id": str(uuid.uuid4()), "b": bid, "title": f"finding {label}"},
            )
        await owner_session.commit()

    async with SessionLocal() as restricted_session:
        from app.database.connection import set_rls_tenant_id
        token = set_rls_tenant_id(bus_a)
        try:
            await connection_mod._set_rls_context(restricted_session)
            rows = (await restricted_session.execute(
                text("SELECT business_id FROM findings")
            )).fetchall()
            ids = {str(r.business_id) for r in rows}
            assert ids == {bus_a}, f"Tenant A must only see its own finding, got {ids}"

            # Cross-tenant INSERT must be rejected by WITH CHECK.
            with pytest.raises(Exception):
                await restricted_session.execute(
                    text("""
                        INSERT INTO findings (id, business_id, domain, category, severity,
                                              title, status, source)
                        VALUES (:id, :b, 'inventory', 'stockout_risk', 'high',
                                'crosstenant', 'detected', 'audit_engine')
                    """),
                    {"id": str(uuid.uuid4()), "b": bus_b},
                )
                await restricted_session.commit()
        finally:
            connection_mod._rls_tenant_id.reset(token)


@pytest.mark.asyncio
async def test_app_role_join_policies_isolate_chat_messages(
    rls_engine, app_role_enabled, monkeypatch
):
    """chat_messages (no business_id) isolate through chat_sessions.session_id.

    The join-based policy must hide the other tenant's messages and reject a
    message written into the other tenant's session under SET ROLE nazmos_app.
    """
    SessionLocal = async_sessionmaker(rls_engine, class_=AsyncSession, expire_on_commit=False)

    async with SessionLocal() as owner_session:
        bus_a = str(uuid.uuid4())
        bus_b = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        await owner_session.execute(
            text("""
                INSERT INTO users (id, email, password_hash, full_name, role, is_active)
                VALUES (:id, :email, 'hash', 'Owner', 'owner', true)
            """),
            {"id": user_id, "email": f"rls_chat_{uuid.uuid4().hex[:8]}@example.com"},
        )
        for bid in (bus_a, bus_b):
            await owner_session.execute(
                text("INSERT INTO businesses (id, name, type, currency) VALUES (:id, 'C', 'retail', 'SAR')"),
                {"id": bid},
            )
        session_ids = {}
        msg_ids = {}
        for bid, tag in ((bus_a, "a"), (bus_b, "b")):
            session_id = str(uuid.uuid4())
            session_ids[tag] = session_id
            await owner_session.execute(
                text("""
                    INSERT INTO chat_sessions (id, business_id, user_id, title)
                    VALUES (:id, :b, :u, :title)
                """),
                {"id": session_id, "b": bid, "u": user_id, "title": f"session {tag}"},
            )
            msg_id = str(uuid.uuid4())
            msg_ids[tag] = msg_id
            await owner_session.execute(
                text("""
                    INSERT INTO chat_messages (id, session_id, role, content)
                    VALUES (:id, :sid, 'user', :content)
                """),
                {"id": msg_id, "sid": session_id, "content": f"message {tag}"},
            )
        await owner_session.commit()

    async with SessionLocal() as restricted_session:
        from app.database.connection import set_rls_tenant_id
        token = set_rls_tenant_id(bus_a)
        try:
            await connection_mod._set_rls_context(restricted_session)
            rows = (await restricted_session.execute(
                text("SELECT id FROM chat_messages")
            )).fetchall()
            assert {str(r.id) for r in rows} == {msg_ids["a"]}, (
                f"Tenant A must only see its own chat message, got {rows}"
            )

            with pytest.raises(Exception):
                await restricted_session.execute(
                    text("""
                        INSERT INTO chat_messages (id, session_id, role, content)
                        VALUES (:id, :sid, 'user', 'cross-tenant')
                    """),
                    {"id": str(uuid.uuid4()), "sid": session_ids["b"]},
                )
                await restricted_session.commit()
        finally:
            connection_mod._rls_tenant_id.reset(token)


@pytest.mark.asyncio
async def test_app_role_join_policies_isolate_pos_sync_logs(
    rls_engine, app_role_enabled, monkeypatch
):
    """pos_sync_logs (no business_id) isolate through pos_connections.connection_id."""
    SessionLocal = async_sessionmaker(rls_engine, class_=AsyncSession, expire_on_commit=False)

    async with SessionLocal() as owner_session:
        bus_a = str(uuid.uuid4())
        bus_b = str(uuid.uuid4())
        for bid in (bus_a, bus_b):
            await owner_session.execute(
                text("INSERT INTO businesses (id, name, type, currency) VALUES (:id, 'P', 'retail', 'SAR')"),
                {"id": bid},
            )
        connection_ids = {}
        log_ids = {}
        for bid, tag in ((bus_a, "a"), (bus_b, "b")):
            conn_id = str(uuid.uuid4())
            connection_ids[tag] = conn_id
            await owner_session.execute(
                text("""
                    INSERT INTO pos_connections
                        (id, business_id, adapter_type, connection_name, credentials_encrypted, credentials_version)
                    VALUES (:id, :b, 'mock', :name, :cred, 1)
                """),
                {"id": conn_id, "b": bid, "name": f"conn {tag}", "cred": b"\x00secret"},
            )
            log_id = str(uuid.uuid4())
            log_ids[tag] = log_id
            await owner_session.execute(
                text("""
                    INSERT INTO pos_sync_logs (id, connection_id, started_at, status, records_fetched)
                    VALUES (:id, :cid, NOW(), 'success', 1)
                """),
                {"id": log_id, "cid": conn_id},
            )
        await owner_session.commit()

    async with SessionLocal() as restricted_session:
        from app.database.connection import set_rls_tenant_id
        token = set_rls_tenant_id(bus_a)
        try:
            await connection_mod._set_rls_context(restricted_session)
            rows = (await restricted_session.execute(
                text("SELECT id FROM pos_sync_logs")
            )).fetchall()
            assert {str(r.id) for r in rows} == {log_ids["a"]}, (
                f"Tenant A must only see its own sync log, got {rows}"
            )

            with pytest.raises(Exception):
                await restricted_session.execute(
                    text("""
                        INSERT INTO pos_sync_logs (id, connection_id, started_at, status)
                        VALUES (:id, :cid, NOW(), 'success')
                    """),
                    {"id": str(uuid.uuid4()), "cid": connection_ids["b"]},
                )
                await restricted_session.commit()
        finally:
            connection_mod._rls_tenant_id.reset(token)


@pytest.mark.asyncio
async def test_whatsapp_webhook_approval_is_tenant_scoped_under_rls(
    rls_engine, app_role_enabled, monkeypatch,
):
    """The unauthenticated WhatsApp webhook must fail closed under real RLS.

    The webhook session assumes ``nazmos_app`` with a tenant resolved from the
    button id.  A button for the correct business transitions the action; a
    button whose tenant does not own the action must see zero rows (RLS) and
    must NOT emit an approval confirmation.
    """
    import hashlib
    import hmac
    import json
    import types

    from httpx import AsyncClient, ASGITransport

    from app.main import app
    from app.database import get_db  # noqa: F401

    SessionLocal = async_sessionmaker(rls_engine, class_=AsyncSession, expire_on_commit=False)

    async with SessionLocal() as owner_session:
        bus_a = str(uuid.uuid4())
        bus_b = str(uuid.uuid4())
        action_a = str(uuid.uuid4())
        action_b = str(uuid.uuid4())
        owner_row = await owner_session.execute(
            text("""
                INSERT INTO users (id, email, password_hash, full_name, role, is_active)
                VALUES (:id, :email, 'hash', 'Owner', 'owner', true)
            """),
            {"id": str(uuid.uuid4()), "email": f"rls_wa_{uuid.uuid4().hex[:8]}@example.com"},
        )
        for bid in (bus_a, bus_b):
            await owner_session.execute(
                text("INSERT INTO businesses (id, name, type, currency) VALUES (:id, 'W', 'retail', 'SAR')"),
                {"id": bid},
            )
        for bid, item_sku, action_id in (
            (bus_a, "A-1", action_a),
            (bus_b, "B-1", action_b),
        ):
            item_id = str(uuid.uuid4())
            await owner_session.execute(
                text("""
                    INSERT INTO items (id, business_id, name, sku, unit, cost_price, sell_price, is_active)
                    VALUES (:id, :business_id, 'I', :sku, 'piece', 10, 20, true)
                """),
                {"id": item_id, "business_id": bid, "sku": item_sku},
            )
            await owner_session.execute(
                text("""
                    INSERT INTO agent_actions
                        (id, business_id, action_type, status, confidence, priority, title, summary,
                         payload, autonomy_dial_at_creation, estimated_value_sar)
                    VALUES
                        (:id, :business_id, 'restock', 'pending_approval', 0.9, 1, 'T', 'S',
                         CAST(:payload AS JSON), 50, 100)
                """),
                {
                    "id": action_id,
                    "business_id": bid,
                    "payload": f'{{"item_id": "{item_id}", "recommended_qty": 15}}',
                },
            )
        await owner_session.commit()

    # Webhook scenarios operate against the NORMAL app dependency so the engine
    # begin-listener (which reads app_role_enabled's patched settings and the
    # tenant ContextVar) is the code path under test.
    def _button_payload(button_id: str) -> bytes:
        body = {
            "entry": [{"changes": [{"value": {"messages": [
                {"from": "+966500000000", "type": "interactive",
                 "interactive": {"type": "button", "button_reply": {"id": button_id}}},
            ]}}]}],
        }
        return json.dumps(body).encode()

    def _headers(body: bytes) -> dict:
        return {"x-hub-signature-256":
                "sha256=" + hmac.new(b"rls-secret", body, hashlib.sha256).hexdigest()}

    sent: list[tuple[str, str]] = []

    async def fake_send(to_number: str, text: str):
        sent.append((to_number, text))

    monkeypatch.setattr(
        "app.routers.whatsapp.settings",
        types.SimpleNamespace(WHATSAPP_APP_SECRET="rls-secret"),
    )
    monkeypatch.setattr("app.routers.whatsapp.send_notification", fake_send)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # 1. Correct tenant button -> action_a actually transitions.
        body = _button_payload(f"approve_{bus_a}_{action_a}")
        r = await ac.post("/api/v1/whatsapp/webhook", content=body, headers=_headers(body))
        assert r.status_code == 200

        # 2. Wrong-tenant button targeting action_a -> must fail closed.
        body = _button_payload(f"approve_{bus_b}_{action_a}")
        r = await ac.post("/api/v1/whatsapp/webhook", content=body, headers=_headers(body))
        assert r.status_code == 200

    async with SessionLocal() as check_session:
        rows = (await check_session.execute(
            text("SELECT id, status FROM agent_actions WHERE id IN (:a, :b)"),
            {"a": action_a, "b": action_b},
        )).fetchall()
        statuses = {str(row.id): row.status for row in rows}

    assert statuses[action_a] == "executed", "correct-tenant webhook must approve+execute"
    assert statuses[action_b] == "pending_approval", "other tenant's action untouched"
    assert len(sent) == 2, f"expected one confirmation + one denial, got {sent}"
    assert sent[0][1].startswith("✅"), f"expected confirmed text, got {sent[0]}"
    assert sent[1][1].startswith("⚠️"), f"expected fail-closed denial, got {sent[1]}"
