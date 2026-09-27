"""sec 17: outcome / business-state foundation (V1 outcome ledger).

Covers the outcome-capture foundation (MASTER_PLAN sec 17):
  1. V1 outcome ledger schema exists, versioned, SQLite-captured.
  2. Capture rows bind decision + evidence + outcome on one snapshot row.
  3. Verified-only consumption: learning reads `verified_outcomes` (verified=1)
     and never raw rows (MASTER_PLAN sec 8: verified outcomes only).
  4. Best-effort capture: missing/invalid ledger path never blocks or changes
     a decision (determinism gate preserved with capture enabled).
  5. Idempotency under retry: replaying the same decision_key coalesces.

DB-free / network-free: temp SQLite ledger files; no Postgres/Temporal.
"""
import json

import httpx
import pytest

from app.config import get_settings
from app.services.ai_providers.jev import JevClient
from app.services.canonical_controller import canonical_rank, canonical_reorder_urgency
from app.services.outcome_ledger import (
    OUTCOME_SCHEMA_VERSION,
    OutcomeLedger,
    derive_decision_key,
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


def _set_outcome_ledger_path(tmp_path) -> str:
    path = str(tmp_path / "outcome_ledger.sqlite")
    cfg = get_settings()
    cfg.AI_OUTCOME_LEDGER_PATH = path
    return path


def _clear_outcome_ledger_path():
    get_settings().AI_OUTCOME_LEDGER_PATH = ""


@pytest.fixture(autouse=True)
def _clean_outcome_ledger_path():
    yield
    _clear_outcome_ledger_path()


# --- V1 schema -------------------------------------------------------------


def test_v1_outcome_ledger_schema_versioned():
    assert OUTCOME_SCHEMA_VERSION == "v1"


def test_capture_row_binds_decision_evidence_outcome(tmp_path):
    ledger = OutcomeLedger(str(tmp_path / "ledger.sqlite"))
    assert ledger.record(
        decision_key=derive_decision_key(
            business_id="b1", capability="audit.root_cause_bucket", deterministic_decision="UNCERTAIN"
        ),
        capability="audit.root_cause_bucket",
        deterministic_decision="UNCERTAIN",
        source="fallback",
        jev_suggested="LOW_DEMAND",
        agree=False,
        risk_flags=["DLP_OK"],
        capsule_hash="capsule-a1b2",
        model="jev-1.13.0",
        provider="fallback",
        latency_ms=12.5,
    )
    s = ledger.summary()
    assert s["schema_version"] == "v1"
    assert s["total_captured"] == 1
    assert s["verified"] == 0
    assert s["by_outcome_status"] == {"unknown": 1}


def test_verified_result_attach_flips_only_verified_row(tmp_path):
    path = str(tmp_path / "ledger.sqlite")
    ledger = OutcomeLedger(path)
    key = derive_decision_key(business_id="b1", capability="recovery.rank", deterministic_decision="HIGH")
    ledger.record(
        decision_key=key,
        capability="recovery.rank",
        deterministic_decision="HIGH",
        source="jev",
        jev_suggested="HIGH",
        agree=True,
        risk_flags=[],
        capsule_hash="c-hash",
        latency_ms=3.0,
    )
    assert ledger.record_verified_result(
        decision_key=key,
        outcome_status="confirmed",
        verified=True,
        actual_impact_sar=12.5,
        expected_impact_sar=10.0,
    )
    s = ledger.summary()
    assert s["verified"] == 1
    assert s["by_outcome_status"] == {"confirmed": 1}

    verified = ledger.verified_outcomes()
    assert len(verified) == 1
    assert verified[0]["verified"] is True
    assert verified[0]["outcome_status"] == "confirmed"
    assert verified[0]["agree"] is True


def test_verified_only_consumption_excludes_raw_rows(tmp_path):
    path = str(tmp_path / "ledger.sqlite")
    ledger = OutcomeLedger(path)
    k1 = derive_decision_key(business_id="b1", capability="a", deterministic_decision="X")
    k2 = derive_decision_key(business_id="b2", capability="a", deterministic_decision="Y")
    ledger.record(decision_key=k1, capability="a", deterministic_decision="X",
                  source="jev", agree=True, capsule_hash="h1", latency_ms=1.0)
    ledger.record(decision_key=k2, capability="a", deterministic_decision="Y",
                  source="fallback", agree=True, capsule_hash="h2", latency_ms=2.0)
    ledger.record_verified_result(decision_key=k2, outcome_status="confirmed", verified=True)
    verified = ledger.verified_outcomes()
    assert [r["deterministic_decision"] for r in verified] == ["Y"]
    assert [r["deterministic_decision"] for r in ledger.verified_outcomes()] != ["X", "Y"]


def test_idempotency_replay_coalesces_on_decision_key(tmp_path):
    path = str(tmp_path / "ledger.sqlite")
    ledger = OutcomeLedger(path)
    key = derive_decision_key(business_id="b1", capability="a", deterministic_decision="X")
    for _ in range(3):
        ledger.record(decision_key=key, capability="a", deterministic_decision="X",
                      source="jev", agree=False, capsule_hash="h", latency_ms=1.0)
    assert ledger.summary()["total_captured"] == 1


@pytest.mark.asyncio
async def test_capture_never_blocks_decision_when_path_unwritable(tmp_path):
    ledger_path = str(tmp_path / "missing" / "sub" / "ledger.sqlite")
    cfg = get_settings()
    cfg.AI_OUTCOME_LEDGER_PATH = ledger_path
    out = await canonical_reorder_urgency(
        payload=_payload(),
        deterministic_band="high",
        client=_disabling_client(),
    )
    assert out["decision"] == "HIGH"
    assert out["source"] == "fallback"


@pytest.mark.asyncio
async def test_determinism_gate_preserved_with_capture_enabled(tmp_path):
    path = _set_outcome_ledger_path(tmp_path)
    out = await canonical_rank(
        payload=_payload(),
        deterministic_bucket="low",
        client=_disabling_client(),
        recorder=ShadowParityRecorder(str(tmp_path / "parity.jsonl")),
    )
    assert out["decision"] == "LOW"
    assert out["source"] == "fallback"
    assert out["jev_consulted"] is False
    assert OutcomeLedger(path).summary()["total_captured"] == 1


@pytest.mark.asyncio
async def test_capture_row_agreement_jevs_disabled(tmp_path):
    path = _set_outcome_ledger_path(tmp_path)
    out = await canonical_rank(
        payload=_payload(),
        deterministic_bucket="high",
        client=_disabling_client(),
        recorder=ShadowParityRecorder(str(tmp_path / "parity.jsonl")),
    )
    s = OutcomeLedger(path).summary()
    assert s["total_captured"] == 1
    assert s["dissent"] == 0
    rows = OutcomeLedger(path).verified_outcomes()
    assert rows == []  # raw capture is never consumable as verified


@pytest.mark.asyncio
async def test_capture_row_binds_jev_shadow_consult(tmp_path):
    path = _set_outcome_ledger_path(tmp_path)
    out = await canonical_rank(
        payload=_payload(),
        deterministic_bucket="high",
        client=_mock_client(suggestion="LOW"),
        recorder=ShadowParityRecorder(str(tmp_path / "parity.jsonl")),
    )
    assert out["decision"] == "HIGH"          # deterministic wins despite Jev dissent
    assert out["alternative_decision"] == "LOW"
    s = OutcomeLedger(path).summary()
    assert s["total_captured"] == 1
    assert s["dissent"] == 1                   # Jev dissented; dissent captured


def test_derive_decision_key_deterministic():
    a = derive_decision_key(business_id="b1", capability="recovery.rank", deterministic_decision="HIGH")
    b = derive_decision_key(business_id="b1", capability="recovery.rank", deterministic_decision="HIGH")
    c = derive_decision_key(business_id="b1", capability="recovery.rank", deterministic_decision="LOW")
    assert a == b
    assert a != c
    assert len(a) == 24


def test_ledger_row_never_contains_business_id_plaintext(tmp_path):
    path = str(tmp_path / "ledger.sqlite")
    ledger = OutcomeLedger(path)
    key = derive_decision_key(business_id="secret_biz_123", capability="a", deterministic_decision="X")
    ledger.record(decision_key=key, capability="a", deterministic_decision="X",
                  source="jev", agree=True, capsule_hash="h", latency_ms=1.0)
    for row in ledger.verified_outcomes():
        assert "secret_biz_123" not in json.dumps(row)
    with open(path, "rb") as fh:
        raw = fh.read()
    assert b"secret_biz_123" not in raw       # only the sha-derived key is stored


def test_summary_error_is_swallowed(tmp_path):
    cfg = get_settings()
    orig = cfg.AI_OUTCOME_LEDGER_PATH
    try:
        cfg.AI_OUTCOME_LEDGER_PATH = str(tmp_path / "bad.sqlite")
        ledger = OutcomeLedger(str(tmp_path / "bad.sqlite"))
        assert isinstance(ledger.summary(), dict)
        assert ledger.summary()["total_captured"] == 0
    finally:
        cfg.AI_OUTCOME_LEDGER_PATH = orig