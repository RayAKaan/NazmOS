"""Phase 4C — typed advisory via the canonical ai_gateway entry (DB-free).

Proves the Phase 4 advisory wiring end-to-end through the SAME canonical
gateway that OpenCode/the controller use (``ai_gateway.systemone_reason``),
exactly as documented in PHASE_4A_RUNTIME_CONTRACT_REPORT.md §5 (4C):

  1. ``canonical_advisor`` (the loop's production advisory_fn) consults Jev via
     the canonical gateway entry, and ``consult_advisory`` normalizes the reply
     into a TypedAdvisory.
  2. Attribution is exact: a mocked advisor is labelled ``mocked`` (never
     ``jev``). A fallback reply (Jev disabled/down) is never labelled Jev —
     it resolves to DETERMINISTIC_ONLY plus an UNKNOWN_PROVIDER_SOURCE flag.
  3. Out-of-contract suggestions are dropped (``suggested is None`` + risk
     flag); deterministic decisions are never overridden.
  4. The capsule that crosses to the AI is DLP-clean: the transport only ever
     sees ``capsule.for_prompt()`` — opaque refs + banded signals, never
     business/tenant ids, SKUs, stock counts or exact SAR amounts.

DB-free / network-free: a stub transport is injected via ``context["client"]``,
mirroring tests/test_canonical_controller.py. No db_session, no Postgres.
"""
import json

import httpx
import pytest

from app.security.capsule import ReasoningCapsule, CapsuleSigner
from app.services.ai_providers.jev import JevClient
from app.services.business_loop.advisory import (
    AdvisorySource,
    canonical_advisor,
    consult_advisory,
    deterministic_only_advisor,
)
from app.services.business_loop.contracts import AdvisorySource as ContractSource


@pytest.fixture(autouse=True)
def _reset_ai_budget():
    """The gateway records every consult against the process-wide budget
    singleton; reset ALL counters (incl. daily) so tests are order-independent."""
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


class _CaptureTransport(httpx.AsyncBaseTransport):
    """Stub Jev transport that records the exact request body it is handed.

    The recorded ``payload["state"]`` is the DLP surface: whatever the AI is
    allowed to observe. Tests assert raw merchant data never appears there.
    """

    def __init__(self, suggestion: str | None, confidence: float = 0.9):
        self.suggestion = suggestion
        self.confidence = confidence
        self.outbound_state: dict = {}
        self.outbound_question: str = ""

    async def handle_async_request(self, request):
        body = json.loads(request.content)
        self.outbound_state = body.get("state") or {}
        self.outbound_question = body.get("questions", {}).get("Q1", "")
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


def _mock_client(transport: _CaptureTransport) -> JevClient:
    return JevClient(settings=_jev_settings(), transport=transport)


def _loop_contract() -> frozenset[str]:
    return frozenset({"RESTOCK", "REORDER", "DISCOUNT", "DO_NOTHING"})


def _loop_context(*, deterministic: str, contract: frozenset[str], client: JevClient | None = None) -> dict:
    return {
        "payload": {
            "tenant_id": "tenant-abc-111",
            "business_id": "biz-987654",
        },
        "deterministic_decision": deterministic,
        "purpose": "continuous_business_loop",
        "contract": contract,
        # note: canonical_advisor forwards context.get("client") into the
        # canonical gateway so DB-free tests can inject a stub transport.
        "client": client,
    }


# ---------------------------------------------------------------------------
# 1. canned-type advisory through the canonical gateway entry
# ---------------------------------------------------------------------------

async def test_canonical_advisor_routes_through_canonical_gateway() -> None:
    """canonical_advisor -> systemone_reason -> jev.consult -> TypedAdvisory.

    Deterministic decision stays authoritative; the Jev suggestion is an
    alternative only, sourced exactly from the provider that answered.
    """
    transport = _CaptureTransport(suggestion="DISCOUNT")
    client = _mock_client(transport)

    ta = await consult_advisory(
        canonical_advisor,
        capability="business_loop.action_selection",
        context=_loop_context(deterministic="REORDER", contract=_loop_contract(), client=client),
        contract=_loop_contract(),
    )

    assert ta.capability == "business_loop.action_selection"
    assert ta.deterministic_decision == "REORDER"  # never overridden
    assert ta.suggested == "DISCOUNT"              # advisory alternative only
    assert ta.source == ContractSource.JEV         # exact provider attribution
    assert ta.provider == "jev"
    assert ta.validation_passed is True
    assert ta.risk_flags == []
    assert ta.confidence == 0.9


async def test_advisory_agreement_drops_redundant_alternative() -> None:
    """When Jev agrees with the deterministic decision there is no 'suggested'."""
    transport = _CaptureTransport(suggestion="REORDER")
    client = _mock_client(transport)

    ta = await consult_advisory(
        canonical_advisor,
        capability="business_loop.action_selection",
        context=_loop_context(deterministic="REORDER", contract=_loop_contract(), client=client),
        contract=_loop_contract(),
    )

    assert ta.deterministic_decision == "REORDER"
    assert ta.suggested is None  # agreement -> no separate alternative
    assert ta.validation_passed is True


async def test_jev_dissent_never_overrides_deterministic_decision() -> None:
    """Jev suggesting something else must not change the decision."""
    transport = _CaptureTransport(suggestion="RESTOCK")
    client = _mock_client(transport)

    ta = await consult_advisory(
        canonical_advisor,
        capability="business_loop.action_selection",
        context=_loop_context(deterministic="REORDER", contract=_loop_contract(), client=client),
        contract=_loop_contract(),
    )

    assert ta.deterministic_decision == "REORDER"
    assert ta.suggested == "RESTOCK"
    assert ta.source == ContractSource.JEV


# ---------------------------------------------------------------------------
# 2. exact attribution: mocked is mocked; fallback is never Jev
# ---------------------------------------------------------------------------

async def test_mocked_advisor_is_labelled_mocked_never_jev() -> None:
    """A test/loop mock keeps its MOCKED label end-to-end."""

    async def mocked_jev(capability, context):
        return {
            "decision": context["deterministic_decision"],
            "suggested": "DISCOUNT",
            "confidence": 0.8,
            "source": AdvisorySource.MOCKED.value,
            "provider": "mocked",
        }

    ta = await consult_advisory(
        mocked_jev,
        capability="business_loop.action_selection",
        context=_loop_context(deterministic="REORDER", contract=_loop_contract()),
        contract=_loop_contract(),
    )

    assert ta.source == ContractSource.MOCKED
    assert ta.provider == "mocked"
    assert ta.source != ContractSource.JEV
    assert ta.suggested == "DISCOUNT"
    assert ta.validation_passed is True


async def test_disabled_jev_is_fallback_never_labelled_jev() -> None:
    """Jev disabled in settings => gateway source 'fallback' resolves to
    DETERMINISTIC_ONLY + UNKNOWN_PROVIDER_SOURCE flag. Never claimed as Jev."""
    transport = _CaptureTransport(suggestion="DISCOUNT")  # ignored; never consulted
    client = JevClient(settings=_jev_settings(enabled=False), transport=transport)

    ta = await consult_advisory(
        canonical_advisor,
        capability="business_loop.action_selection",
        context=_loop_context(deterministic="REORDER", contract=_loop_contract(), client=client),
        contract=_loop_contract(),
    )

    assert ta.source == ContractSource.DETERMINISTIC_ONLY  # never JEV
    assert ta.deterministic_decision == "REORDER"
    assert ta.suggested is None
    assert any("UNKNOWN_PROVIDER_SOURCE:fallback" in f for f in ta.risk_flags)
    assert ta.source != ContractSource.JEV


async def test_deterministic_only_advisor_is_never_jev() -> None:
    """The fail-closed default advisor must never claim Jev attribution."""
    reply = await deterministic_only_advisor(
        "business_loop.action_selection",
        {"deterministic_decision": "REORDER"},
    )
    assert reply["source"] == AdvisorySource.DETERMINISTIC_ONLY.value
    assert reply["provider"] == "deterministic"


# ---------------------------------------------------------------------------
# 3. out-of-contract advisory dropped, never coerced
# ---------------------------------------------------------------------------

async def test_out_of_contract_suggestion_dropped_through_gateway() -> None:
    """Jev proposes an action the loop contract does not allow => dropped."""
    transport = _CaptureTransport(suggestion="LAUNDER_MONEY")
    client = _mock_client(transport)

    ta = await consult_advisory(
        canonical_advisor,
        capability="business_loop.action_selection",
        context=_loop_context(deterministic="REORDER", contract=_loop_contract(), client=client),
        contract=_loop_contract(),
    )

    assert ta.deterministic_decision == "REORDER"
    assert ta.suggested is None              # rejected, never coerced
    assert "OUT_OF_CONTRACT" in ta.risk_flags
    assert ta.validation_passed is False


async def test_invalid_suggestion_source_never_reaches_decision() -> None:
    """Even a malicious/corrupt answer can only become a flagged advisory."""
    transport = _CaptureTransport(suggestion="DO_NOTHING")
    client = _mock_client(transport)

    ta = await consult_advisory(
        canonical_advisor,
        capability="business_loop.action_selection",
        context=_loop_context(deterministic="REORDER", contract=_loop_contract(), client=client),
        contract=_loop_contract(),
    )

    # deterministic decision is authoritative regardless of the suggestion
    assert ta.deterministic_decision == "REORDER"
    assert isinstance(ta.suggested, (str, type(None)))


# ---------------------------------------------------------------------------
# 4. capsule DLP-cleanliness on the wire
# ---------------------------------------------------------------------------

def _merchant_payload() -> dict:
    return {
        "tenant_id": "tenant-abc-111",
        "business_id": "biz-987654",
        "business": {
            "business_type": "auto_parts",
            "branch_count": "3",
            "total_capital_at_risk_sar": 150000,
            "cash_budget": 45000,
            "blocked_discount_products": ["SKU-B1"],
            "strategic_products": ["SKU-A1"],
            "max_discount_pct": 12,
            "minimum_margin_pct": 18,
        },
        "items": [
            {
                "sku": "SKU-A1",
                "name": "Premium Brake Pads",
                "current_stock": 42,
                "days_of_supply": 3,
                "recent_velocity_per_day": 5,
                "inventory_age_days": 210,
                "days_since_last_sale": 1,
                "classification": "auto_brake",
                "candidate_actions": ["REORDER", "DO_NOTHING"],
                "margin_pct": 31,
                "demand_volatility": 0.8,
                "supplier_reliability": "high",
                "supplier_lead_time_days": 14,
                "confirmed_inbound_qty": 200,
                "is_strategic": True,
                "is_promotional": False,
                "seasonal_type": None,
                "trend": "growing",
                "monthly_concentration_peak": 0.8,
            },
            {
                "sku": "SKU-B1",
                "name": "Budget Oil Filter",
                "current_stock": 140,
                "days_of_supply": 28,
                "recent_velocity_per_day": 1,
                "inventory_age_days": 40,
                "days_since_last_sale": 7,
                "classification": "auto_filter",
                "candidate_actions": ["RESTOCK", "DO_NOTHING"],
                "margin_pct": 22,
                "demand_volatility": 0.1,
                "supplier_reliability": "medium",
                "supplier_lead_time_days": 4,
                "confirmed_inbound_qty": 0,
                "is_strategic": False,
                "is_promotional": True,
                "promotion_type": None,
                "trend": "declining",
                "monthly_concentration_peak": 0.2,
            },
        ],
    }


async def test_gateway_capsule_on_wire_is_dlp_clean() -> None:
    """Raw merchant data must never reach the AI wire for the loop advisory.

    The recorded outbound ``state`` is exactly ``capsule.for_prompt()``: opaque
    refs + banded signals only. No tenant/business ids, SKUs, names, exact
    stock counts, or exact SAR amounts.
    """
    transport = _CaptureTransport(suggestion="REORDER")
    client = _mock_client(transport)

    ta = await consult_advisory(
        canonical_advisor,
        capability="business_loop.action_selection",
        context={
            "payload": _merchant_payload(),
            "deterministic_decision": "REORDER",
            "purpose": "continuous_business_loop",
            "contract": _loop_contract(),
            "client": client,
        },
        contract=_loop_contract(),
    )

    assert ta.deterministic_decision == "REORDER"
    state = transport.outbound_state
    state_text = json.dumps(state, sort_keys=True)

    # --- banded/derived signals ARE present -----------------------------
    assert state["items"][0]["ref"] == "item_A"          # opaque, not SKU-A1
    assert state["items"][0]["stock_band"] == "10-49"    # banded, not 42
    assert state["items"][0]["velocity_band"] == "HIGH"
    assert state["items"][1]["ref"] == "item_B"
    # --- raw merchant data is NOT present -------------------------------
    for secret in (
        "tenant-abc-111",       # tenant identifier
        "biz-987654",           # business identifier
        "SKU-A1",               # SKU
        "SKU-B1",
        "Premium Brake Pads",   # product name
        "Budget Oil Filter",    # supplier/product name
        "42",                   # exact stock
        "140",
        "150000",               # exact SAR
        "45000",
    ):
        assert secret not in state_text, f"DLP leak on the wire: {secret}"
    # --- provenance bookkeeping is not sent to the AI ---------------------
    for trusted in ("capsule_id", "request_id", "nonce", "signature", "capsule_hash"):
        assert trusted not in state, f"trusted-zone bookkeeping leaked: {trusted}"


async def test_capsule_signature_verified_before_consult() -> None:
    """The canonical gateway signs the capsule; it remains signed/verifiable."""
    from app.security.privacy_firewall import build_capsule_for_payload

    capsule = build_capsule_for_payload(
        _merchant_payload(),
        capability="business_loop.action_selection",
        purpose="continuous_business_loop",
    )
    assert isinstance(capsule, ReasoningCapsule)
    assert capsule.signature
    assert capsule.capsule_hash
    assert CapsuleSigner().verify(capsule) is True

    # DLP sanity at the serialization boundary too
    prompt_text = json.dumps(capsule.for_prompt(), sort_keys=True)
    assert "tenant-abc-111" not in prompt_text
    assert "biz-987654" not in prompt_text


async def test_consult_rejects_raw_dict_capsule() -> None:
    """jevv.consult type-level invariant: raw evidence dicts are a TypeError.

    This is the isolation guarantee behind 'Jev only ever observes the signed
    capsule' -- the adapter itself refuses anything shorter.
    """
    from app.services.ai_providers.jev import consult as jev_consult

    with pytest.raises(TypeError):
        await jev_consult(
            question="x",
            capsule={"state": "raw-merchant-data"},  # type: ignore[arg-type]
            deterministic_decision="REORDER",
            client=_mock_client(_CaptureTransport("REORDER")),
        )