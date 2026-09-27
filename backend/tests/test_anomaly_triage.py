"""Batch 2: inventory.anomaly_triage canonical migration acceptance.

Covers MIGRATION_MATRIX sec 2,7 for the anomaly triage surface:
  1. Pre-req: detector output PERSISTS as findings (ground truth exists).
  2. The persistence path is OPT-IN (no production trigger wired in Phase 2).
  3. Determinism gate: Jev off => deterministic bucket preserved.
  4. Shadow parity + contract gate: Jev advisory; SPIKE/DROP contract enforced.

DB-free: sqlite in-memory for findings; jev mock transport; temp ledger files.
"""
import json

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database.models import Base, Finding
from app.orchestration.contracts import ANOMALY_TRIAGE_BUCKETS
from app.services.ai_providers.jev import JevClient
from app.services.anomaly_triage import (
    detect_and_persist,
    persist_anomalies,
    persist_anomaly,
    triage_severity,
)
from app.services.canonical_controller import (
    CanonicalControllerError,
    canonical_anomaly_triage,
)
from app.services.shadow_capture import ShadowParityRecorder


@pytest_asyncio.fixture
async def sqlite_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        yield SessionLocal, engine.sync_engine
    finally:
        await engine.dispose()


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


def test_triage_severity_mapping():
    assert triage_severity("spike") == "high"
    assert triage_severity("drop") == "medium"
    assert triage_severity("unknown_thing") == "medium"


async def test_persist_anomaly_writes_a_finding(sqlite_db):
    SessionLocal, _ = sqlite_db
    async with SessionLocal() as db:
        fid = await persist_anomaly(
            db,
            business_id="11111111-1111-1111-1111-111111111111",
            anomaly={
                "item_id": "item_A",
                "item_name": "Milk",
                "type": "spike",
                "magnitude_pct": 74.8,
                "date": "2026-09-01",
                "value": 100,
                "expected_value": 16,
                "z_score": 3.74,
            },
            threshold_z=2.5,
        )
        await db.commit()

    async with SessionLocal() as db:
        row = (await db.execute(select(Finding).where(Finding.id == fid))).scalar_one()
        assert row.category == "anomaly"
        assert row.severity == "high"
        assert row.source == "anomaly_detector.zscore"
        assert row.evidence.get("detector") == "anomaly_detector.zscore"
        assert row.evidence.get("threshold_z") == 2.5
        assert row.affected_entities[0]["id"] == "item_A"


async def test_persist_anomalies_empty_and_multiple(sqlite_db):
    SessionLocal, _ = sqlite_db
    async with SessionLocal() as db:
        assert await persist_anomalies(db, "b", []) == []
        fids = await persist_anomalies(
            db,
            "22222222-2222-2222-2222-222222222222",
            [
                {"item_id": "i1", "item_name": "A", "type": "spike", "date": "d", "value": 9, "expected_value": 1, "z_score": 3.0},
                {"item_id": "i1", "item_name": "A", "type": "drop", "date": "d", "value": 0, "expected_value": 8, "z_score": -3.1},
            ],
        )
        await db.commit()
        assert len(fids) == 2

    async with SessionLocal() as db:
        rows = (await db.execute(select(Finding))).scalars().all()
        severities = sorted(r.severity for r in rows)
        assert severities == ["high", "medium"]


async def test_detect_and_persist_is_opt_in_consumer(sqlite_db):
    """detector runs, output persists; insufficient data yields nothing."""
    SessionLocal, _ = sqlite_db
    daily_sales = [{"date": f"2026-09-{d:02d}", "quantity": 10} for d in range(1, 15)]
    daily_sales[13]["quantity"] = 100  # one clear spike

    async with SessionLocal() as db:
        fids = await detect_and_persist(
            db,
            "33333333-3333-3333-3333-333333333333",
            "item_B",
            "Eggs",
            daily_sales,
            threshold_z=2.5,
        )
        await db.commit()
        assert len(fids) == 1  # only the spike clears |z| > 2.5

    async with SessionLocal() as db:
        rows = (await db.execute(select(Finding))).scalars().all()
        assert len(rows) == 1
        assert rows[0].severity == "high"
        assert rows[0].title == "Sales anomaly spike: Eggs"

    # insufficient history (len < 14) => detector returns [] => nothing persisted
    async with SessionLocal() as db:
        fids = await detect_and_persist(
            db,
            "33333333-3333-3333-3333-333333333333",
            "item_C",
            "Bread",
            [{"date": "2026-09-01", "quantity": 5}],
        )
        await db.commit()
        assert fids == []


@pytest.mark.asyncio
async def test_determinism_gate_anomaly_triage_jev_off(tmp_path):
    out = await canonical_anomaly_triage(
        payload=_payload(),
        deterministic_bucket="spike",
        client=_disabling_client(),
        recorder=ShadowParityRecorder(str(tmp_path / "ledger.jsonl")),
    )
    assert out["decision"] == "SPIKE"
    assert out["source"] == "fallback"
    assert out["jev_consulted"] is False


@pytest.mark.asyncio
async def test_shadow_parity_and_contract_gate_anomaly_triage(tmp_path):
    ag = await canonical_anomaly_triage(
        payload=_payload(),
        deterministic_bucket="spike",
        client=_mock_client("SPIKE"),
        recorder=ShadowParityRecorder(str(tmp_path / "ledger.jsonl")),
    )
    assert ag["decision"] == "SPIKE"
    assert "JEV_DISSENT" not in ag["risk_flags"]

    di = await canonical_anomaly_triage(
        payload=_payload(),
        deterministic_bucket="spike",
        client=_mock_client("DROP"),
        recorder=ShadowParityRecorder(str(tmp_path / "ledger.jsonl")),
    )
    assert di["decision"] == "SPIKE"
    assert di["alternative_decision"] == "DROP"
    assert "JEV_DISSENT" in di["risk_flags"]

    bad = await canonical_anomaly_triage(
        payload=_payload(),
        deterministic_bucket="spike",
        client=_mock_client("NEEDS_REVIEW"),
        recorder=ShadowParityRecorder(str(tmp_path / "ledger.jsonl")),
    )
    assert bad["alternative_decision"] is None
    assert "JEV_OUT_OF_CONTRACT" in bad["risk_flags"]


@pytest.mark.asyncio
async def test_contract_enforcement_deterministic_bucket(tmp_path):
    assert "SPIKE" in ANOMALY_TRIAGE_BUCKETS
    with pytest.raises(CanonicalControllerError):
        await canonical_anomaly_triage(
            payload=_payload(),
            deterministic_bucket="PENDING_REVIEW",
            client=_disabling_client(),
            recorder=ShadowParityRecorder(str(tmp_path / "ledger.jsonl")),
        )


def test_anomaly_triage_buckets_are_discrete():
    assert ANOMALY_TRIAGE_BUCKETS == frozenset({"SPIKE", "DROP"})