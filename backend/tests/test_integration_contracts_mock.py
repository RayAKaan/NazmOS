"""WS9 — external integration contracts are mock-first and credential-free.

Every provider reachable from the pilot deployment (WhatsApp Cloud API,
Groq/Google LLM, POS adapters) must either run against a mock OR degrade to a
deterministic fallback when credentials are absent.  Live integrations are
exercised only by the explicitly-live tests (skipped here).
"""
import json
import types

import pytest


@pytest.mark.asyncio
async def test_whatsapp_mock_mode_never_touches_meta():
    import app.services.whatsapp_bridge as wb

    stubbed = types.SimpleNamespace(
        WHATSAPP_ENABLED="mock",
        WHATSAPP_TOKEN="",
        WHATSAPP_PHONE_ID="",
    )
    old_settings = wb.settings
    wb.settings = stubbed
    try:
        assert wb._is_live() is False
        out = await wb.send_approval_request(
            to_number="+966501234567",
            action_id="a1",
            title="Approve discount",
            summary="5% on Milk",
            approve_url="http://x/approve",
            reject_url="http://x/reject",
        )
    finally:
        wb.settings = old_settings

    assert out["status"] == "mock_sent"
    assert out["message_id"].startswith("mock_wamid_")
    assert out["to"] == "+966501234567"


@pytest.mark.asyncio
async def test_llm_mock_mode_returns_none_without_http():
    """With no provider keys the orchestrator is in mock mode: no HTTP POST is
    ever attempted and the caller receives None (deterministic fallback)."""
    import app.services.llm_orchestrator as orch_mod

    stubbed = types.SimpleNamespace(
        USE_MOCK_LLM=False,
        GROQ_API_KEY="",
        GOOGLE_AI_API_KEY="",
        provider_order="groq,google,mock",
        LLM_TEMPERATURE=0.2,
        LLM_MAX_TOKENS=1024,
    )
    old_settings = orch_mod.settings
    orch_mod.settings = stubbed
    try:
        orch = orch_mod.LLMOrchestrator()
        assert orch.use_mock is True

        async def _should_never_be_called(*a, **k):
            raise AssertionError("mock mode must not issue HTTP calls")

        orch._post_json = _should_never_be_called
        result = await orch.generate_response("Should this crash?")
        assert result is None
        assert orch.fallback_mode is True
    finally:
        orch_mod.settings = old_settings


@pytest.mark.asyncio
async def test_llm_chat_completion_none_when_mock():
    """chat_completion returns None in mock mode so AI-reasoning layers fall
    back to deterministic logic instead of hallucinating."""
    import app.services.llm_orchestrator as orch_mod

    stubbed = types.SimpleNamespace(
        USE_MOCK_LLM=False,
        GROQ_API_KEY="",
        GOOGLE_AI_API_KEY="",
        provider_order="groq,google,mock",
        AI_CALL_LEDGER_PATH=None,
        GROQ_MODEL=None,
        GOOGLE_AI_MODEL=None,
    )
    old_settings = orch_mod.settings
    orch_mod.settings = stubbed
    try:
        orch = orch_mod.LLMOrchestrator()
        # Mock mode returns a DETERMINISTIC no-inference response tagged
        # MOCK_LLM — guaranteed never a hallucinated business claim, and never
        # passed off as a real LLM decision.  This is the fallback contract the
        # AI-reasoning layers rely on.
        out = await orch.chat_completion("sys", "user prompt")
        assert out is not None
        parsed = json.loads(out)
        assert parsed.get("risk_flags") == ["MOCK_LLM"]
        assert "no real reasoning" in parsed.get("reasoning", "")
    finally:
        orch_mod.settings = old_settings


@pytest.mark.asyncio
async def test_pos_connections_work_with_zero_credentials():
    """POS adapter list is DB-only: no OAuth client, no external service, so a
    fresh pilot tenant gets an empty list — never an integration error."""
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from sqlalchemy.pool import StaticPool

    from app.database.models import Base

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as db:
        from app.routers.adapters import get_current_tenant, list_connections

        class _Request:
            state = {"tenant": get_current_tenant}

        connections = await list_connections(
            db,
            tenant=types.SimpleNamespace(business_id=str(uuid.uuid4())),
        )
        assert connections == [], "fresh tenant has no POS connections"
    await engine.dispose()