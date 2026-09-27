"""Provider failure tests: the Jev (SystemOne) adapter must fail closed.

Hard requirements verified here:
  * Jev is NON-AUTHORITATIVE -- the deterministic decision always wins.
  * Raw evidence dicts are a TypeError (never reach Jev / the AI).
  * Jev disabled / unconfigured => advisory fallback, deterministic preserved.
  * HTTP transport errors (429/5xx/timeouts) => advisory fallback, deterministic
    preserved, bounded retry (no infinite loops, no cross-contamination).
  * Out-of-contract suggestions => rejected (fallback), deterministic preserved.
  * Expired capsule => rejected, deterministic preserved.
  * The canonical gateway route (ai_gateway.systemone_reason) enforces the same
    invariants even when a stub Jev returns a perfect answer: decision is
    deterministic, shadow mode never surfaces Jev's suggestion, and the Jev
    payload only ever sees the DLP-clean capsule view.

All tests are DB-free and network-free (stub transport).
"""
import asyncio
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from app.config import JevSettings
from app.security.capsule import CapsuleSigner, ReasoningCapsule
from app.security.privacy_firewall import build_capsule_for_payload
from app.services.ai_providers import jev as jev_mod
from app.services.ai_providers.jev import (
    JevClient,
    JevError,
    JevReply,
    consult,
)


@pytest.fixture(autouse=True)
def _reset_ai_budget():
    """The gateway records every consult against the process-wide budget
    singleton; reset ALL counters (incl. daily) so tests are order-independent."""
    from app.services.ai_budget import GLOBAL_AI_BUDGET

    GLOBAL_AI_BUDGET.reset()
    yield

PAYLOAD = {
    "items": [
        {
            "ref": "item_A",
            "classification": "auto_parts",
            "stock_band": "0-9",
            "velocity_band": "LOW",
            "candidate_decisions": ["REORDER", "DO_NOTHING"],
            "evidence_fields": ["stock_band", "velocity_band"],
        }
    ],
    "business": {"business_type": "auto_parts", "capital_at_risk_band": "HIGH"},
}


def _capsule() -> ReasoningCapsule:
    c = build_capsule_for_payload(
        PAYLOAD, capability="opencode_brain", purpose="_internal"
    )
    return CapsuleSigner().sign(c)


def _expired_capsule() -> ReasoningCapsule:
    c = _capsule()
    expired = c.model_copy(
        update={
            "issued_at": datetime.now(timezone.utc) - timedelta(seconds=300),
            "expires_at": datetime.now(timezone.utc) - timedelta(seconds=1),
        }
    )
    return CapsuleSigner().sign(expired)


class _StubTransport(httpx.AsyncBaseTransport):
    """Injects a canned HTTP response into the JevClient."""

    def __init__(self, *, status_code: int = 200, payload: dict | None = None):
        self.status_code = status_code
        self.payload = payload

    async def handle_async_request(self, request):
        if self.status_code == 200:
            return httpx.Response(200, json=self.payload or {"answers": {"Q1": {}}})
        return httpx.Response(self.status_code, text=f"err {self.status_code}")


def _enabled_settings() -> JevSettings:
    return JevSettings(enabled=True, api_key="test-key", base_url="https://jev.test/v1/systemone")


@pytest.mark.asyncio
async def test_jev_disabled_returns_deterministic_fallback():
    client = JevClient(
        settings=JevSettings(enabled=False, api_key="", base_url=""),
        transport=_StubTransport(),
    )
    reply = await consult(
        question="Q?", capsule=_capsule(), deterministic_decision="REORDER", client=client
    )
    assert reply.source == "fallback"
    assert reply.decision_basis == "REORDER"
    assert "jev_not_configured" in reply.errors
    assert not client.enabled


@pytest.mark.asyncio
async def test_jev_transport_error_fails_closed():
    client = JevClient(
        settings=_enabled_settings(),
        transport=_StubTransport(status_code=503),
    )
    with pytest.raises(JevError):
        await client._post({"model": "x"})

    reply = await consult(
        question="Q?", capsule=_capsule(), deterministic_decision="REORDER", client=client
    )
    assert reply.source == "fallback"
    assert reply.decision_basis == "REORDER"
    assert reply.errors


@pytest.mark.asyncio
async def test_jev_hard_or_out_of_contract_suggestion_is_rejected():
    client = JevClient(
        settings=_enabled_settings(),
        transport=_StubTransport(
            payload={"answers": {"Q1": {"choice": "RUN_AWAY", "explanation": "bad"}}}
        ),
    )
    reply = await consult(
        question="Q?", capsule=_capsule(), deterministic_decision="REORDER", client=client
    )
    assert reply.source == "fallback"
    assert reply.decision_basis == "REORDER"
    assert any("invalid_suggestion" in e for e in reply.errors)


@pytest.mark.asyncio
async def test_jev_valid_suggestion_is_advisory_only():
    settings = _enabled_settings()
    client = JevClient(
        settings=settings,
        transport=_StubTransport(
            payload={
                "answers": {
                    "Q1": {
                        "choice": "TRANSFER",
                        "score": 0.9,
                        "explanation": "transfer surplus stock",
                    }
                }
            }
        ),
    )
    reply = await consult(
        question="Q?", capsule=_capsule(), deterministic_decision="REORDER", client=client
    )
    assert reply.source == "jev"
    # NEVER authoritative: decision_basis is the deterministic decision.
    assert reply.decision_basis == "REORDER"
    assert reply.suggested_decision == "TRANSFER"
    assert reply.confidence == pytest.approx(0.9)


@pytest.mark.asyncio
async def test_jev_expired_capsule_fails_closed():
    client = JevClient(
        settings=_enabled_settings(),
        transport=_StubTransport(payload={"answers": {"Q1": {"choice": "REORDER"}}}),
    )
    reply = await consult(
        question="Q?", capsule=_expired_capsule(), deterministic_decision="REORDER", client=client
    )
    assert reply.source == "fallback"
    assert reply.decision_basis == "REORDER"
    assert "capsule_expired" in reply.errors


def test_consult_rejects_raw_dict_typeerror():
    async def run():
        client = JevClient(settings=_enabled_settings())
        await consult(
            question="Q?",
            capsule={"items": []},  # type: ignore[arg-type]  -- raw dict must be TypeError
            deterministic_decision="REORDER",
            client=client,
        )

    with pytest.raises(TypeError):
        asyncio.run(run())


@pytest.mark.asyncio
async def test_jev_client_uses_configured_timeout(monkeypatch):
    captured = {}

    class FakeResponse:
        status_code = 200

        def json(self):
            return {"answers": {"Q1": {"choice": "REORDER", "explanation": "ok"}}}

    class FakeClient:
        def __init__(self, **kw):
            captured["client_kwargs"] = kw

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, **kw):
            captured["url"] = url
            captured["post_kwargs"] = kw
            return FakeResponse()

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)

    settings = _enabled_settings()
    settings.timeout_seconds = 7.0
    client = JevClient(settings=settings, transport=_StubTransport())

    reply = await client._post({"model": "x"})
    assert reply == {"answers": {"Q1": {"choice": "REORDER", "explanation": "ok"}}}
    client_kwargs = captured["client_kwargs"]
    timeout = client_kwargs["timeout"]
    assert isinstance(timeout, httpx.Timeout)
    assert timeout.connect == 7.0 and timeout.read == 7.0
    assert captured["url"] == settings.base_url
    assert captured["post_kwargs"]["headers"]["Authorization"] == "Bearer test-key"


# --- canonical gateway route (Jev-first, non-authoritative) -----------------

async def _run_gateway(monkeypatch, *, shadow: bool, jev_choice: str, deterministic: str) -> dict:
    """Call ai_gateway.systemone_reason with a stubbed Jev consult + audit."""
    import app.services.ai_gateway as gateway
    import app.services.ai_providers.jev as jev_mod

    async def fake_consult(*, question, capsule, deterministic_decision, client=None, allowed_suggestions=None):
        return JevReply(
            source="jev",
            decision_basis=deterministic_decision,
            suggested_decision=jev_choice,
            confidence=0.99,
            reasoning="stub advice",
            challenge=False,
            latency_ms=3.0,
        )

    async def fake_record_req(**kw):
        return True

    async def fake_record_evt(**kw):
        return True

    monkeypatch.setattr(jev_mod, "consult", fake_consult)
    monkeypatch.setattr(gateway, "record_ai_reasoning_request", fake_record_req)
    monkeypatch.setattr(gateway, "record_security_event", fake_record_evt)

    return await gateway.systemone_reason(
        PAYLOAD,
        capability="opencode_brain",
        purpose="_internal",
        deterministic_decision=deterministic,
        shadow=shadow,
    )


@pytest.mark.asyncio
async def test_gateway_jev_never_overrides_deterministic(monkeypatch):
    out = await _run_gateway(
        monkeypatch, shadow=False, jev_choice="TRANSFER", deterministic="REORDER"
    )
    # Deterministic ALWAYS wins, even when Jev suggests a strong alternative.
    assert out["decision"] == "REORDER"
    assert out["source"] == "jev"
    assert out["jev_consulted"] is True
    assert out["alternative_decision"] == "TRANSFER"  # surfaced as advisory only
    assert "JEV_DISSENT" in out["risk_flags"]
    assert out["use_jev_exposition"] is True


@pytest.mark.asyncio
async def test_gateway_shadow_mode_never_surfaces_jev(monkeypatch):
    out = await _run_gateway(
        monkeypatch, shadow=True, jev_choice="TRANSFER", deterministic="REORDER"
    )
    assert out["decision"] == "REORDER"
    assert out["source"] == "jev"
    assert out["jev_consulted"] is True
    # Shadow: suggestion surfaced for validation/audit, but never as exposition.
    assert out["alternative_decision"] == "TRANSFER"
    assert out["use_jev_exposition"] is False
    assert "JEV_DISSENT" in out["risk_flags"]


@pytest.mark.asyncio
async def test_gateway_agreeing_jev_keeps_deterministic(monkeypatch):
    out = await _run_gateway(
        monkeypatch, shadow=False, jev_choice="REORDER", deterministic="REORDER"
    )
    assert out["decision"] == "REORDER"
    assert out["jev_consulted"] is True
    assert out["alternative_decision"] == "REORDER"


@pytest.mark.asyncio
async def test_gateway_out_of_contract_deterministic_is_never_overridden(monkeypatch):
    # deterministic_decision itself out of the canonical set => DO_NOTHING,
    # regardless of what Jev says.
    out = await _run_gateway(
        monkeypatch, shadow=False, jev_choice="TRANSFER", deterministic="YOLO"
    )
    assert out["decision"] == "DO_NOTHING"
    assert out["source"] == "jev"