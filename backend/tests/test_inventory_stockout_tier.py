"""Batch 2: inventory.stockout_tier canonical migration acceptance.

Covers MIGRATION_MATRIX sec 2,7 for the stockout urgency tier:
  1. Deterministic tier exists: classify_tier maps classify_status
     output onto the INVENTORY_STATUS_TIERS contract, fail-closed.
  2. Determinism gate: Jev off => deterministic tier preserved, source=fallback.
  3. Shadow parity: Jev advisory; deterministic always wins.
  4. Contract gate: Jev out-of-contract tier discarded + JEV_OUT_OF_CONTRACT.

DB-free / network-free: jev mock transport injected; temp ledger files.
"""
import json

import httpx
import pytest

from app.analytics.metrics import classify_status, classify_tier, status_to_tier
from app.orchestration.contracts import INVENTORY_STATUS_TIERS
from app.services.ai_providers.jev import JevClient
from app.services.canonical_controller import (
    CanonicalControllerError,
    canonical_stockout_tier,
)
from app.services.shadow_capture import ShadowParityRecorder


@pytest.fixture(autouse=True)
def _reset_ai_budget():
    from app.services.ai_budget import GLOBAL_AI_BUDGET

    GLOBAL_AI_BUDGET.reset()
    yield


def _payload() -> dict:
    return {
        "items": [
            {
                "ref": "item_A",
                "stock_band": "0-9",
                "velocity_band": "LOW",
                "candidate_decisions": ["REORDER", "DO_NOTHING"],
                "evidence_fields": ["stock_band", "velocity_band"],
            }
        ],
        "business": {"business_type": "auto_parts", "capital_at_risk_band": "HIGH"},
    }


def _mock_client(suggestion: str | None, *, source: str = "jev", confidence: float = 0.9):
    answer: dict = {"question_id": "Q1"}
    if suggestion is not None:
        answer["choice"] = suggestion
    answer["explanation"] = "stub advisory"
    answer["confidence"] = confidence

    class StubTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            body = json.dumps({"answers": {"Q1": answer}})
            return httpx.Response(200, content=body.encode(), headers={"content-type": "application/json"})

    return JevClient(settings=_jev_settings(), transport=StubTransport())


def _disabling_client():
    class DisabledTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            raise AssertionError("Jev must NOT be contacted when disabled")

    return JevClient(settings=_jev_settings(enabled=False), transport=DisabledTransport())


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


def test_classify_status_tiers_cover_the_contract():
    assert classify_status(10, 0) == "dead"
    assert classify_status(1, 1) == "critical"          # 1 day < 2
    assert classify_status(3, 1) == "low"               # 3 days < 5
    assert classify_status(60, 1) == "overstock"         # 60 > 20
    assert classify_status(60, 1, include_overstock=False) == "healthy"
    assert {status_to_tier(s) for s in ("dead", "critical", "low", "overstock", "healthy")} == set(
        INVENTORY_STATUS_TIERS
    )


def test_classify_tier_returns_contract_tiers():
    assert classify_tier(10, 0) == "DEAD"
    assert classify_tier(1, 1) == "CRITICAL"
    assert classify_tier(3, 1) == "LOW"
    assert classify_tier(60, 1) == "OVERSTOCK"
    assert classify_tier(60, 1, include_overstock=False) == "HEALTHY"


def test_status_to_tier_is_fail_closed():
    with pytest.raises(KeyError):
        status_to_tier("not_a_status")


@pytest.mark.asyncio
async def test_determinism_gate_stockout_tier_jev_off(tmp_path):
    out = await canonical_stockout_tier(
        payload=_payload(),
        deterministic_tier="dead",
        client=_disabling_client(),
        recorder=ShadowParityRecorder(str(tmp_path / "ledger.jsonl")),
    )
    assert out["decision"] == "DEAD"
    assert out["source"] == "fallback"
    assert out["jev_consulted"] is False
    rec = json.loads((tmp_path / "ledger.jsonl").read_text().splitlines()[0])
    assert rec["decision"] == "DEAD"
    assert rec["source_label"] == "deterministic_authoritative"


@pytest.mark.asyncio
async def test_shadow_parity_jev_agrees_and_dissents(tmp_path):
    ag = await canonical_stockout_tier(
        payload=_payload(),
        deterministic_tier="low",
        client=_mock_client("LOW"),
        recorder=ShadowParityRecorder(str(tmp_path / "ledger.jsonl")),
    )
    assert ag["decision"] == "LOW"
    assert ag["alternative_decision"] == "LOW"
    assert "JEV_DISSENT" not in ag["risk_flags"]

    di = await canonical_stockout_tier(
        payload=_payload(),
        deterministic_tier="low",
        client=_mock_client("OVERSTOCK"),
        recorder=ShadowParityRecorder(str(tmp_path / "ledger.jsonl")),
    )
    assert di["decision"] == "LOW"  # deterministic ALWAYS wins
    assert di["alternative_decision"] == "OVERSTOCK"
    assert "JEV_DISSENT" in di["risk_flags"]


@pytest.mark.asyncio
async def test_contract_gate_out_of_contract_tier_discarded(tmp_path):
    out = await canonical_stockout_tier(
        payload=_payload(),
        deterministic_tier="healthy",
        client=_mock_client("FROZEN"),
        recorder=ShadowParityRecorder(str(tmp_path / "ledger.jsonl")),
    )
    assert out["decision"] == "HEALTHY"
    assert out["alternative_decision"] is None
    assert "JEV_OUT_OF_CONTRACT" in out["risk_flags"]


@pytest.mark.asyncio
async def test_contract_enforcement_deterministic_tier(tmp_path):
    with pytest.raises(CanonicalControllerError):
        await canonical_stockout_tier(
            payload=_payload(),
            deterministic_tier="FROZEN",
            client=_disabling_client(),
            recorder=ShadowParityRecorder(str(tmp_path / "ledger.jsonl")),
        )