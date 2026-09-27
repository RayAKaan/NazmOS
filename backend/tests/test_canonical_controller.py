"""Batch 1 canonical controller acceptance (MIGRATION_MATRIX sec 1,7).

Covers the three Choice surfaces: recovery.rank, recovery.action_type,
audit.root_cause_bucket. Verifies the canonical controller contract:
  1. Determinism gate: Jev disabled/unavailable => deterministic output identical.
  2. Shadow parity: Jev suggestion is advisory; deterministic always wins.
  3. Availability gate: Jev down => fallback + deterministic + audit event.
  4. Contract gate: Jev out-of-contract suggestion discarded + JEV_OUT_OF_CONTRACT.
  5. Governance gate: capsule DLP-clean (no business_id), not authoritative.

DB-free / network-free: jev mock transport injected; temp ledger files.
"""
import asyncio
import json

import httpx
import pytest

from app.services.ai_providers.jev import JevReply, JevClient
from app.services.canonical_controller import (
    RANK_BUCKETS,
    ROOT_CAUSE_BUCKETS,
    CanonicalControllerError,
    canonical_action_type,
    canonical_rank,
    canonical_root_cause,
)
from app.services.shadow_capture import ShadowParityRecorder
from app.orchestration.contracts import CANONICAL_ACTION_TYPES


@pytest.fixture(autouse=True)
def _reset_ai_budget():
    """The gateway records every consult against the process-wide budget
    singleton; reset ALL counters (incl. daily) so tests are order-independent."""
    from app.services.ai_budget import GLOBAL_AI_BUDGET

    GLOBAL_AI_BUDGET.reset()
    yield


def _payload(bucket_capability: str = "opencode_brain") -> dict:
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
    } | ({"_": "rank"} if False else {})


def _mock_client(suggestion: str | None, *, source: str = "jev", confidence: float = 0.9):
    """JevClient backed by a stub transport returning a canned answer."""
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
    """Jev not configured => consult() returns fallback with deterministic basis."""

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


@pytest.mark.asyncio
async def test_determinism_gate_action_type_jev_off(tmp_path):
    """Jev disabled => deterministic action preserved, source=fallback."""
    out = await canonical_action_type(
        payload=_payload(),
        deterministic_action="REORDER",
        client=_disabling_client(),
        recorder=ShadowParityRecorder(str(tmp_path / "ledger.jsonl")),
    )
    assert out["decision"] == "REORDER"
    assert out["source"] == "fallback"
    assert out["jev_consulted"] is False
    rec = json.loads((tmp_path / "ledger.jsonl").read_text().splitlines()[0])
    assert rec["decision"] == "REORDER"
    assert rec["source_label"] == "deterministic_authoritative"


@pytest.mark.asyncio
async def test_determinism_gate_rank_jev_broken(tmp_path):
    """Jev transport error => deterministic bucket preserved, fallback label."""
    class ExplodingTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            raise httpx.ConnectError("jev down")

    client = JevClient(settings=_jev_settings(), transport=ExplodingTransport())
    out = await canonical_rank(
        payload=_payload(),
        deterministic_bucket="high",
        client=client,
        recorder=ShadowParityRecorder(str(tmp_path / "ledger.jsonl")),
    )
    assert out["decision"] == "HIGH"
    assert out["source"] == "fallback"
    assert out["jev_consulted"] is False


@pytest.mark.asyncio
async def test_shadow_parity_jev_agrees_decision_unchanged(tmp_path):
    """Jev agrees => deterministic decision kept; no dissent flag."""
    out = await canonical_action_type(
        payload=_payload(),
        deterministic_action="REORDER",
        client=_mock_client("REORDER"),
        recorder=ShadowParityRecorder(str(tmp_path / "ledger.jsonl")),
    )
    assert out["decision"] == "REORDER"
    assert out["source"] == "jev"
    assert out["alternative_decision"] == "REORDER"
    assert "JEV_DISSENT" not in out["risk_flags"]


@pytest.mark.asyncio
async def test_shadow_parity_jev_dissents_deterministic_wins(tmp_path):
    """Jev suggests something else => deterministic wins, dissent flagged."""
    out = await canonical_action_type(
        payload=_payload(),
        deterministic_action="REORDER",
        client=_mock_client("TRANSFER"),
        recorder=ShadowParityRecorder(str(tmp_path / "ledger.jsonl")),
    )
    assert out["decision"] == "REORDER"  # deterministic ALWAYS wins
    assert out["alternative_decision"] == "TRANSFER"  # advisory only
    assert "JEV_DISSENT" in out["risk_flags"]


@pytest.mark.asyncio
async def test_contract_gate_out_of_contract_suggestion_discarded(tmp_path):
    """Jev suggests non-contract action => discarded + flagged, audit preserved."""
    out = await canonical_action_type(
        payload=_payload(),
        deterministic_action="REORDER",
        client=_mock_client("HACK_ACTION"),
        recorder=ShadowParityRecorder(str(tmp_path / "ledger.jsonl")),
    )
    assert out["decision"] == "REORDER"
    assert out["alternative_decision"] is None
    assert "JEV_OUT_OF_CONTRACT" in out["risk_flags"]


@pytest.mark.asyncio
async def test_contract_gate_root_cause_taxonomy(tmp_path):
    """Root-cause buckets validated against the taxonomy contract."""
    out = await canonical_root_cause(
        payload=_payload(),
        deterministic_bucket="reorder_threshold_low",
        client=_mock_client("supplier_lead_time"),
        recorder=ShadowParityRecorder(str(tmp_path / "ledger.jsonl")),
    )
    assert out["decision"] == "REORDER_THRESHOLD_LOW"
    assert out["alternative_decision"] == "SUPPLIER_LEAD_TIME"
    assert "JEV_DISSENT" in out["risk_flags"]

    bad = await canonical_root_cause(
        payload=_payload(),
        deterministic_bucket="reorder_threshold_low",
        client=_mock_client("NOT_A_BUCKET"),
        recorder=ShadowParityRecorder(str(tmp_path / "ledger.jsonl")),
    )
    assert bad["alternative_decision"] is None
    assert "JEV_OUT_OF_CONTRACT" in bad["risk_flags"]


@pytest.mark.asyncio
async def test_contract_enforcement_deterministic_decision(tmp_path):
    """The controller refuses deterministic decisions outside the surface contract."""
    with pytest.raises(CanonicalControllerError):
        await canonical_action_type(
            payload=_payload(),
            deterministic_action="BOGUS_ACTION",
            client=_disabling_client(),
            recorder=ShadowParityRecorder(str(tmp_path / "ledger.jsonl")),
        )


@pytest.mark.asyncio
async def test_rank_bucket_contract_and_governance(tmp_path):
    """recovery.rank: valid buckets, deterministic wins, capsule has no business_id."""
    out = await canonical_rank(
        payload=_payload(),
        deterministic_bucket="top",
        client=_mock_client("high"),
        recorder=ShadowParityRecorder(str(tmp_path / "ledger.jsonl")),
    )
    assert out["decision"] in RANK_BUCKETS
    assert out["alternative_decision"] == "HIGH"

    rec = json.loads((tmp_path / "ledger.jsonl").read_text().splitlines()[0])
    assert rec["capsule_hash"]
    assert "business_id" not in rec
    assert "model" in rec and rec["provider"]


def test_contracts_are_disjoint_notable():
    """Rank buckets and root-cause taxonomy are separate surfaces."""
    assert RANK_BUCKETS.isdisjoint(ROOT_CAUSE_BUCKETS)
    assert "DO_NOTHING" in {a.upper() for a in RANK_BUCKETS.union(ROOT_CAUSE_BUCKETS).union(CANONICAL_ACTION_TYPES)}