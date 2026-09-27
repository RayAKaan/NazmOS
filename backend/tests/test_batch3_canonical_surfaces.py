"""Batch 3: procurement.reorder_urgency / pricing.margin_erosion_risk /
report.finding_priority canonical migration acceptance.

Covers MIGRATION_MATRIX sec 3,7 for the three Batch 3 surfaces:
  1. Deterministic bands exist (owner-module wrappers, fail-closed).
  2. Determinism gate: Jev off => deterministic band preserved, source=fallback.
  3. Shadow parity: Jev advisory; deterministic always wins.
  4. Contract gate: Jev out-of-contract suggestion discarded + JEV_OUT_OF_CONTRACT.

DB-free / network-free: jev mock transport injected; temp ledger files.
"""
import json

import httpx
import pytest

from app.orchestration.contracts import (
    FINDING_PRIORITY_TOKENS,
    MARGIN_EROSION_BANDS,
    REORDER_URGENCY_BANDS,
)
from app.services.ai_providers.jev import JevClient
from app.services.canonical_controller import (
    CanonicalControllerError,
    canonical_finding_priority,
    canonical_margin_erosion,
    canonical_reorder_urgency,
)
from app.services.finding_service import finding_priority_token
from app.services.margin_erosion import margin_erosion_band
from app.services.reorder_urgency import reorder_urgency_band
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


# --- deterministic band helpers -------------------------------------------


def test_reorder_urgency_band_mirrors_ladder():
    assert reorder_urgency_band(1.5) == "HIGH"          # 0.7 rung: days < 5
    assert reorder_urgency_band(4.99) == "HIGH"
    assert reorder_urgency_band(5) == "LOW"              # 0.4 rung
    assert reorder_urgency_band(10) == "LOW"
    assert reorder_urgency_band(None) == "LOW"           # no projection => no urgency
    assert {"HIGH", "LOW"} == set(REORDER_URGENCY_BANDS)


def test_margin_erosion_band_mirrors_thresholds():
    assert margin_erosion_band(0.14) == "LOW"            # below margin_agent floor
    assert margin_erosion_band(0.149) == "LOW"
    assert margin_erosion_band(0.15) == "MEDIUM"         # at floor
    assert margin_erosion_band(0.22) == "MEDIUM"          # leakage target inside
    assert margin_erosion_band(0.40) == "MEDIUM"          # at ceiling
    assert margin_erosion_band(0.41) == "HIGH"
    assert margin_erosion_band(None) == "LOW"
    assert {"LOW", "MEDIUM", "HIGH"} == set(MARGIN_EROSION_BANDS)


def test_finding_priority_token_normalizes_severity():
    assert finding_priority_token("critical") == "CRITICAL"
    assert finding_priority_token("high") == "HIGH"
    assert finding_priority_token("medium") == "MEDIUM"
    assert finding_priority_token("low") == "LOW"
    assert finding_priority_token("info") == "INFO"
    assert finding_priority_token(None) == "MEDIUM"
    assert finding_priority_token("  high ") == "HIGH"
    assert {"CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"} == set(FINDING_PRIORITY_TOKENS)


# --- determinism gate -----------------------------------------------------


@pytest.mark.asyncio
async def test_determinism_gate_reorder_urgency_jev_off(tmp_path):
    out = await canonical_reorder_urgency(
        payload=_payload(),
        deterministic_band="high",
        client=_disabling_client(),
        recorder=ShadowParityRecorder(str(tmp_path / "ledger.jsonl")),
    )
    assert out["decision"] == "HIGH"
    assert out["source"] == "fallback"
    assert out["jev_consulted"] is False
    rec = json.loads((tmp_path / "ledger.jsonl").read_text().splitlines()[0])
    assert rec["decision"] == "HIGH"
    assert rec["source_label"] == "deterministic_authoritative"


@pytest.mark.asyncio
async def test_determinism_gate_margin_erosion_jev_off(tmp_path):
    out = await canonical_margin_erosion(
        payload=_payload(),
        deterministic_band="medium",
        client=_disabling_client(),
        recorder=ShadowParityRecorder(str(tmp_path / "ledger.jsonl")),
    )
    assert out["decision"] == "MEDIUM"
    assert out["source"] == "fallback"
    assert out["jev_consulted"] is False


@pytest.mark.asyncio
async def test_determinism_gate_finding_priority_jev_off(tmp_path):
    out = await canonical_finding_priority(
        payload=_payload(),
        deterministic_priority="high",
        client=_disabling_client(),
        recorder=ShadowParityRecorder(str(tmp_path / "ledger.jsonl")),
    )
    assert out["decision"] == "HIGH"
    assert out["source"] == "fallback"
    assert out["jev_consulted"] is False


# --- shadow parity --------------------------------------------------------


@pytest.mark.asyncio
async def test_shadow_parity_reorder_urgency_agrees_and_dissents(tmp_path):
    ag = await canonical_reorder_urgency(
        payload=_payload(),
        deterministic_band="low",
        client=_mock_client("LOW"),
        recorder=ShadowParityRecorder(str(tmp_path / "ledger.jsonl")),
    )
    assert ag["decision"] == "LOW"
    assert ag["alternative_decision"] == "LOW"
    assert "JEV_DISSENT" not in ag["risk_flags"]

    di = await canonical_reorder_urgency(
        payload=_payload(),
        deterministic_band="low",
        client=_mock_client("HIGH"),
        recorder=ShadowParityRecorder(str(tmp_path / "ledger.jsonl")),
    )
    assert di["decision"] == "LOW"  # deterministic ALWAYS wins
    assert di["alternative_decision"] == "HIGH"
    assert "JEV_DISSENT" in di["risk_flags"]


@pytest.mark.asyncio
async def test_shadow_parity_margin_erosion_agrees_and_dissents(tmp_path):
    ag = await canonical_margin_erosion(
        payload=_payload(),
        deterministic_band="medium",
        client=_mock_client("MEDIUM"),
        recorder=ShadowParityRecorder(str(tmp_path / "ledger.jsonl")),
    )
    assert ag["decision"] == "MEDIUM"
    assert "JEV_DISSENT" not in ag["risk_flags"]

    di = await canonical_margin_erosion(
        payload=_payload(),
        deterministic_band="medium",
        client=_mock_client("LOW"),
        recorder=ShadowParityRecorder(str(tmp_path / "ledger.jsonl")),
    )
    assert di["decision"] == "MEDIUM"
    assert "JEV_DISSENT" in di["risk_flags"]


@pytest.mark.asyncio
async def test_shadow_parity_finding_priority_agrees_and_dissents(tmp_path):
    ag = await canonical_finding_priority(
        payload=_payload(),
        deterministic_priority="high",
        client=_mock_client("HIGH"),
        recorder=ShadowParityRecorder(str(tmp_path / "ledger.jsonl")),
    )
    assert ag["decision"] == "HIGH"
    assert "JEV_DISSENT" not in ag["risk_flags"]

    di = await canonical_finding_priority(
        payload=_payload(),
        deterministic_priority="high",
        client=_mock_client("CRITICAL"),
        recorder=ShadowParityRecorder(str(tmp_path / "ledger.jsonl")),
    )
    assert di["decision"] == "HIGH"
    assert "JEV_DISSENT" in di["risk_flags"]


# --- contract gates -------------------------------------------------------


@pytest.mark.asyncio
async def test_contract_gate_reorder_urgency_out_of_contract_discarded(tmp_path):
    out = await canonical_reorder_urgency(
        payload=_payload(),
        deterministic_band="low",
        client=_mock_client("URGENT"),
        recorder=ShadowParityRecorder(str(tmp_path / "ledger.jsonl")),
    )
    assert out["decision"] == "LOW"
    assert out["alternative_decision"] is None
    assert "JEV_OUT_OF_CONTRACT" in out["risk_flags"]


@pytest.mark.asyncio
async def test_contract_gate_margin_erosion_out_of_contract_discarded(tmp_path):
    out = await canonical_margin_erosion(
        payload=_payload(),
        deterministic_band="high",
        client=_mock_client("MODERATE"),
        recorder=ShadowParityRecorder(str(tmp_path / "ledger.jsonl")),
    )
    assert out["decision"] == "HIGH"
    assert out["alternative_decision"] is None
    assert "JEV_OUT_OF_CONTRACT" in out["risk_flags"]


@pytest.mark.asyncio
async def test_contract_gate_finding_priority_out_of_contract_discarded(tmp_path):
    out = await canonical_finding_priority(
        payload=_payload(),
        deterministic_priority="medium",
        client=_mock_client("SEMI_URGENT"),
        recorder=ShadowParityRecorder(str(tmp_path / "ledger.jsonl")),
    )
    assert out["decision"] == "MEDIUM"
    assert out["alternative_decision"] is None
    assert "JEV_OUT_OF_CONTRACT" in out["risk_flags"]


@pytest.mark.asyncio
async def test_contract_enforcement_deterministic_band(tmp_path):
    with pytest.raises(CanonicalControllerError):
        await canonical_reorder_urgency(
            payload=_payload(),
            deterministic_band="URGENT",
            client=_disabling_client(),
            recorder=ShadowParityRecorder(str(tmp_path / "ledger.jsonl")),
        )


@pytest.mark.asyncio
async def test_contract_enforcement_finding_priority(tmp_path):
    with pytest.raises(CanonicalControllerError):
        await canonical_finding_priority(
            payload=_payload(),
            deterministic_priority="SEMI_URGENT",
            client=_disabling_client(),
            recorder=ShadowParityRecorder(str(tmp_path / "ledger.jsonl")),
        )