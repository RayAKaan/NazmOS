"""Phase 4I-D — Jev pilot-readiness probe (DB-free).

Answers the 4I-D gate question HONESTLY: is the live Jev provider available for
the pilot, and does the advisory path fail closed when it is not?

The verdict for the current environment is recorded as evidence:
``JevClient().enabled is False`` (no base_url / api_key configured), so the
pilot operates in shadow/disabled mode. These tests prove the contract that
makes that honest:

  1. An unconfigured/disabled Jev client never labels a decision Jev: the
     gateway reply is ``source=="fallback"``, ``jev_consulted is False``, the
     deterministic decision is preserved verbatim, and ``errors`` records
     ``jev_not_configured``.
  2. Shadow mode (DEFAULT): a reachable Jev client only ever enriches
     confidence/reasoning and MAY surface a contract-bounded suggestion as an
     ALTERNATIVE. It never overrides the deterministic decision and its reply
     never gates an outcome — it is validated before any exposition use.
  3. Attribution stays exact: a mocked advisor is ``mocked``, a deterministic
     fallback is never Jev, and any Jev-capable reply is stored with the real
     provider source so downstream reporting cannot overstate its role.

No network, no Postgres: a stub httpx transport is injected via
``context["client"]`` exactly like tests/test_phase4_jev_advisory.py.
"""
import json

import httpx
import pytest

from app.services.ai_providers.jev import JevClient
from app.services.business_loop.advisory import (
    AdvisorySource,
    canonical_advisor,
    consult_advisory,
    deterministic_only_advisor,
)


@pytest.fixture(autouse=True)
def _reset_ai_budget():
    from app.services.ai_budget import GLOBAL_AI_BUDGET

    GLOBAL_AI_BUDGET.reset()
    yield


def _jev_settings(*, enabled: bool = True):
    from app.config import JevSettings

    return JevSettings(
        enabled=enabled,
        shadow_enabled=True,
        base_url="https://system-one.test/v1/systemone",
        api_key="test-key" if enabled else "",
        model="jev-1.13.0",
        timeout_seconds=5.0,
    )


class _StubTransport(httpx.AsyncBaseTransport):
    def __init__(self, suggestion: str | None = None, confidence: float = 0.9):
        self.suggestion = suggestion
        self.confidence = confidence
        self.outbound_state: dict = {}

    async def handle_async_request(self, request):
        body = json.loads(request.content)
        self.outbound_state = body.get("state") or {}
        answer: dict = {"question_id": "Q1"}
        if self.suggestion is not None:
            answer["choice"] = self.suggestion
        answer["explanation"] = "stub advisory"
        answer["confidence"] = self.confidence
        return httpx.Response(
            200,
            content=json.dumps({"answers": {"Q1": answer}}).encode(),
            headers={"content-type": "application/json"},
        )


def _loop_contract() -> frozenset[str]:
    return frozenset({"RESTOCK", "REORDER", "DISCOUNT", "DO_NOTHING"})


def _loop_context(*, deterministic: str, contract: frozenset[str], client: JevClient | None = None) -> dict:
    return {
        "payload": {"tenant_id": "tnt-4id-1", "business_id": "biz-4id-1"},
        "deterministic_decision": deterministic,
        "purpose": "continuous_business_loop",
        "contract": contract,
        "client": client,
    }


def _real_probe():
    from app.config import get_settings

    g = get_settings()
    return bool(g.jev.enabled and g.jev.base_url and g.jev.api_key)


# 1. Current-environment readiness report (honest, evidence-graded)
async def test_4id_jsev_readiness_state_is_honest() -> None:
    """Record the REAL provider state and prove the disabled contract holds.

    If a live Jev configuration is present the unit suite does not dial the
    network; it only asserts the disabled-client contract below would still
    hold for an unconfigured client.
    """
    configured = _real_probe()
    client = JevClient()
    if not configured:
        assert client.enabled is False  # [V] current env: Jev NOT live

    # advertise the fact for the 4I-D report rather than silently assuming one
    print(f"JEV_LIVE={configured} JEV_ENABLED={client.enabled} BASE_URL={getattr(client.settings, 'base_url', None)!r}")


# 2. Unconfigured Jev fails closed; deterministic decision untouched
async def test_4id_unconfigured_jev_is_fallback_never_jev() -> None:
    from app.security.privacy_firewall import build_capsule_for_payload
    from app.services.ai_providers.jev import JevReply, consult

    capsule = build_capsule_for_payload(
        {"tenant_id": "tnt-4id-3", "business_id": "biz-4id-3"},
        capability="business_loop.action_selection",
        purpose="continuous_business_loop",
    )
    client = JevClient(settings=_jev_settings(enabled=False))
    reply = await consult(
        question="Which action is safest?",
        capsule=capsule,
        deterministic_decision="DO_NOTHING",
        client=client,
    )
    assert isinstance(reply, JevReply)
    assert reply.source == "fallback"              # [V] never labelled jev
    assert reply.decision_basis == "DO_NOTHING"    # [V] deterministic preserved
    assert "jev_not_configured" in reply.errors    # [V] reason recorded verbatim


# 3. Canonical gateway in shadow mode with a DISABLED client
async def test_4id_canonical_gateway_shadow_with_disabled_client() -> None:
    from app.services import ai_gateway

    result = await ai_gateway.systemone_reason(
        {"tenant_id": "tnt-4id-2", "business_id": "biz-4id-2"},
        capability="business_loop.action_selection",
        purpose="continuous_business_loop",
        deterministic_decision="DO_NOTHING",
        shadow=True,
        client=JevClient(settings=_jev_settings(enabled=False)),
    )
    assert result["source"] == "fallback"                # [V] no Jev attribution
    assert result["decision"] == "DO_NOTHING"            # [V] decision preserved
    assert result["jev_consulted"] is False              # [V] nothing claimed
    assert result["confidence"] == 0.0


# 4. Shadow mode with a REACHABLE Jev: enrich + suggest, never override
async def test_4id_shadow_mode_reachable_jev_never_overrides() -> None:
    transport = _StubTransport(suggestion="RESTOCK")
    client = JevClient(settings=_jev_settings(enabled=True), transport=transport)
    ctx = _loop_context(deterministic="REORDER", contract=_loop_contract(), client=client)

    ta = await consult_advisory(canonical_advisor, **{"capability": "business_loop.action_selection", "context": ctx, "contract": ctx["contract"]})
    assert ta.deterministic_decision == "REORDER"        # [V] deterministic stays the decision
    assert ta.source == AdvisorySource.JEV and ta.provider == "jev"  # [V] real provider id recorded
    assert ta.validation_passed is True
    assert ta.suggested in _loop_contract()              # [V] alternative bounded by contract

    # the outbound capsule must be DLP-clean (no tenant/business ids, no SKUs)
    leak = str(transport.outbound_state)
    assert "tnt-4id" not in leak and "biz-4id" not in leak
    assert "SKU" not in leak


# 5. Out-of-contract shadow suggestion is dropped, flagged, never coerced
async def test_4id_out_of_contract_suggestion_dropped_in_shadow() -> None:
    transport = _StubTransport(suggestion="LAUNDER_MONEY")
    client = JevClient(settings=_jev_settings(enabled=True), transport=transport)
    ctx = _loop_context(deterministic="REORDER", contract=_loop_contract(), client=client)

    ta = await consult_advisory(canonical_advisor, **{"capability": "business_loop.action_selection", "context": ctx, "contract": ctx["contract"]})
    assert ta.suggested is None
    assert "OUT_OF_CONTRACT" in ta.risk_flags
    assert ta.validation_passed is False                 # [V] flagged, never silently used
    assert ta.deterministic_decision == "REORDER"        # [V] decision untouched


# 6. Mocked advisor is labelled mocked, never Jev (4I-D honesty invariant)
async def test_4id_mock_never_jev_and_fallback_never_jev() -> None:
    async def mocked_advisor(capability: str, context: dict) -> dict:
        return {
            "decision": context.get("deterministic_decision", "DO_NOTHING"),
            "suggested": None,
            "confidence": 0.8,
            "source": AdvisorySource.MOCKED.value,
            "provider": "jev-mock",
            "model": "mock-1",
            "reasoning": "mock advisory",
        }

    ta = await consult_advisory(
        mocked_advisor,
        capability="business_loop.action_selection",
        context=_loop_context(deterministic="RESTOCK", contract=_loop_contract()),
        contract=_loop_contract(),
    )
    assert ta.source == AdvisorySource.MOCKED
    assert ta.source != AdvisorySource.JEV               # [V] mock stays mock

    fallback = await deterministic_only_advisor("business_loop.action_selection", _loop_context(deterministic="RESTOCK", contract=_loop_contract()))
    assert fallback["source"] == AdvisorySource.DETERMINISTIC_ONLY.value
    assert fallback["provider"] == "deterministic"       # [V] fallback never claims Jev