"""Shadow parity + determinism/availability gates for the Jev channel.

TEST_AND_ACCEPTANCE_GATES §6.1-6.3:
  1. Determinism gate: Jev disabled/unavailable => byte-identical deterministic
     output (source label, risk_flags).
  2. Shadow parity audit: observed-case divergence logging; deterministic wins.
  3. Availability gate: outage/budget-exhaust => deterministic + source
     "fallback" + audit event.

All DB-free / network-free: Jev consult is stubbed; ledger is a temp file.
"""
import asyncio
import json

import pytest

from app.services.ai_providers.jev import JevReply
from app.services.shadow_capture import ShadowParityRecorder, run_shadow_parity


@pytest.fixture(autouse=True)
def _reset_ai_budget():
    from app.services.ai_budget import GLOBAL_AI_BUDGET

    GLOBAL_AI_BUDGET.reset()
    yield

PAYLOAD_RESTOCK = {
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

PAYLOAD_DISCOUNT = {
    "items": [
        {
            "ref": "item_B",
            "classification": "food",
            "stock_band": "200-499",
            "velocity_band": "NONE",
            "is_overstock": True,
            "candidate_decisions": ["DISCOUNT", "TRANSFER", "DO_NOTHING"],
            "evidence_fields": ["stock_band", "velocity_band", "is_overstock"],
        }
    ],
    "business": {"business_type": "food", "capital_at_risk_band": "MEDIUM"},
}


def _stub_consult(*, source: str = "jev", suggested: str | None = None):
    async def consult(*, question, capsule, deterministic_decision, client=None):
        # When the caller wants a divergence, suggest something different from
        # the deterministic decision (TRANSFER as the "surprise" alternative).
        suggestion = suggested
        if suggestion is None:
            suggestion = "TRANSFER" if deterministic_decision != "TRANSFER" else deterministic_decision
        return JevReply(
            source=source,
            decision_basis=deterministic_decision,
            suggested_decision=suggestion,
            confidence=0.9,
            reasoning="stub",
            challenge=False,
        )

    return consult


def test_determinism_gate_bypasses_jev_when_disabled(tmp_path):
    """GATE 1: Jev disabled => source=fallback, deterministic preserved."""
    async def run():
        return await run_shadow_parity(
            cases=[(PAYLOAD_RESTOCK, "REORDER")],
            recorder=ShadowParityRecorder(str(tmp_path / "ledger.jsonl")),
            consult=_stub_consult(source="fallback", suggested=None),
        )

    out = asyncio.run(run())
    assert out["deterministic_total"] == 1
    assert out["agree"] == 1
    assert out["diverge"] == 0


def test_shadow_parity_agreement_and_divergence_logging(tmp_path):
    """GATE 2: divergence logged, deterministic wins."""
    counter = {"i": 0}
    answers = ["REORDER", "TRANSFER"]  # 1st case agrees, 2nd diverges

    async def consult(*, question, capsule, deterministic_decision, client=None):
        suggestion = answers[counter["i"] % len(answers)]
        counter["i"] += 1
        return JevReply(
            source="jev",
            decision_basis=deterministic_decision,
            suggested_decision=suggestion,
            confidence=0.9,
            reasoning="stub",
            challenge=False,
        )

    async def run():
        return await run_shadow_parity(
            cases=[
                (PAYLOAD_RESTOCK, "REORDER"),   # Jev agrees (REORDER)
                (PAYLOAD_DISCOUNT, "DISCOUNT")  # Jev diverges (TRANSFER)
            ],
            recorder=ShadowParityRecorder(str(tmp_path / "ledger.jsonl")),
            consult=consult,
        )

    out = asyncio.run(run())
    assert out["total"] == 2
    assert out["agree"] == 1  # only REORDER=REORDER matches
    assert out["diverge"] == 1
    assert out["deterministic_total"] == 2  # deterministic ALWAYS wins
    assert out["divergences"][0]["deterministic"] == "DISCOUNT"
    assert out["divergences"][0]["jev"] == "TRANSFER"
    # ledger has two shadow records
    with open(tmp_path / "ledger.jsonl", encoding="utf-8") as fh:
        lines = [json.loads(ln) for ln in fh if ln.strip()]
    assert len(lines) == 2
    assert lines[0]["decision"] == "REORDER"
    assert lines[1]["decision"] == "DISCOUNT"
    assert lines[1]["agree"] is False


def test_shadow_parity_jev_down_preserves_deterministic(tmp_path):
    """GATE 3: Jev outage => deterministic preserved; recorded as error."""
    async def exploding(*, question, capsule, deterministic_decision, client=None):
        raise RuntimeError("transport exploded")

    async def run():
        return await run_shadow_parity(
            cases=[(PAYLOAD_RESTOCK, "REORDER")],
            recorder=ShadowParityRecorder(str(tmp_path / "ledger.jsonl")),
            consult=exploding,
        )

    out = asyncio.run(run())
    assert out["total"] == 1
    assert out["jev_down"] == 1
    assert out["deterministic_total"] == 1
    with open(tmp_path / "ledger.jsonl", encoding="utf-8") as fh:
        rec = json.loads(fh.readline())
    assert rec["decision"] == "REORDER"
    assert rec["jev_source"] == "error"


def test_shadow_parity_empty_cases_is_benign(tmp_path):
    async def run():
        return await run_shadow_parity(
            cases=[], recorder=ShadowParityRecorder(str(tmp_path / "l.jsonl"))
        )

    out = asyncio.run(run())
    assert out == {
        "total": 0,
        "agree": 0,
        "diverge": 0,
        "jev_down": 0,
        "deterministic_total": 0,
        "divergences": [],
    }