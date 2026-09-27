"""Phase 4I — Pilot Failure Drills (4I-N): drills A–L.

Each drill is a rehearsed FAILURE the pilot must absorb without fabricating an
outcome, executing twice, or bypassing governance:

   A. duplicate delivery of the same trigger   -> one logical cycle, one effect
   B. crash DURING execution (no receipt)      -> reconciliation REQUIRED, never blind-rerun
   C. crash AFTER a stage completes            -> cursor converges, handler NOT re-run
   D. global kill switch (EXECUTION_ENABLED)   -> every dispatch refused, zero mutation
   E. cross-tenant read                        -> fail closed, owner rows only
   F. phantom verification                     -> absent ledger row NEVER verifies
   G. known rejection vs unknown outcome       -> only unknown demands reconciliation
   H. terminal regression                      -> completed cycle is immutable
   I. retry budget exhaustion                  -> blocks; cursor and attempts frozen
   J. provider identity                        -> mocked/fallback never labelled Jev
   K. DLP prompt leak                          -> raw merchant data never crosses the wire
   L. stale approval                           -> materially changed rec cannot reuse approval

DB-free by design (Drill D uses one in-memory SQLite session for the runner
funnel only). USE_TEMPORAL=false; no Postgres, no Temporal, no live Jev.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database.models import Base
from app.services.business_loop import (
    CycleOrchestrator,
    CyclePolicy,
    InMemoryCycleRepository,
)
from app.services.business_loop.contracts import CycleStage, VerificationStatus
from app.services.business_loop.cycle import CycleRunConflictError, CycleRun, CycleStageState
from app.services.business_loop.evidence import EvidenceStore, normalize_observation
from app.services.business_loop.outcome_linkage import attribution_quality
from app.services.outcome_ledger import OutcomeLedger

_BACKEND = Path(__file__).resolve().parents[2]

TENANT, BIZ = "tnt-4I-d", "biz-4I-d"


@pytest.fixture(autouse=True)
def _reset_ai_budget():
    """Jev gateway drills record against the process-wide budget singleton."""
    from app.services.ai_budget import GLOBAL_AI_BUDGET

    GLOBAL_AI_BUDGET.reset()
    yield


def _t(days_ago: int = 0) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat(timespec="seconds")


def _ingest(store: EvidenceStore, *, tenant_id: str, business_id: str, sku: str, stock: float, cost: float, sell: float, days_of_supply: float) -> None:
    raw = {"sku": sku, "stock": stock, "cost": cost, "sell": sell, "days_of_supply": days_of_supply}
    rec, reason = normalize_observation(
        tenant_id=tenant_id,
        business_id=business_id,
        raw=raw,
        source_type="synthetic.pos",
        source_reference=sku,
        observation_type="inventory.observed",
        event_timestamp=_t(),
        observed_at=_t(),
        required_fields=tuple(raw),
    )
    assert rec is not None, reason
    store.put(rec)


async def _mocked_jev(capability: str, context: dict) -> dict:
    contract = context.get("contract") or frozenset()
    prefer = {"transfer_inventory"} & contract
    return {
        "decision": context.get("deterministic_decision", "DO_NOTHING"),
        "suggested": next(iter(prefer)) if prefer else None,
        "confidence": 0.85,
        "source": "mocked",
        "provider": "jev-mock",
        "model": "jev-mock-1.0",
        "reasoning": "synthetic advisory.",
    }


def _measurement_authority(pre: dict, post: dict) -> dict:
    pre_inv = (pre.get("domains") or {}).get("inventory", {}).get("values", {})
    post_inv = (post.get("domains") or {}).get("inventory", {}).get("values", {})
    keys = set(pre_inv) & set(post_inv)
    if not keys:
        return {"observed_impact_sar": None}
    total_pre = sum(float(pre_inv[k].get("stock", 0) or 0) * float(pre_inv[k].get("cost", 0) or 0) for k in keys)
    total_post = sum(float(post_inv[k].get("stock", 0) or 0) * float(post_inv[k].get("cost", 0) or 0) for k in keys)
    observed = round(total_pre - total_post, 2)
    return {"observed_impact_sar": observed if observed > 0 else None}


def _orchestrator(repo: InMemoryCycleRepository, *, biz: str) -> CycleOrchestrator:
    store = EvidenceStore()
    _ingest(store, tenant_id=TENANT, business_id=biz, sku="SKU-4I", stock=120, cost=20, sell=28, days_of_supply=45)
    post_store = EvidenceStore()
    _ingest(post_store, tenant_id=TENANT, business_id=biz, sku="SKU-4I", stock=20, cost=20, sell=28, days_of_supply=5)
    return CycleOrchestrator(
        repository=repo,
        evidence=store,
        verification_evidence=post_store,
        policy=CyclePolicy(
            shariah_approved=True,
            advisory_fn=_mocked_jev,
            verification_evaluator=_measurement_authority,
        ),
    )


def _craft_run(**overrides) -> CycleRun:
    now = _t()
    base = dict(
        cycle_id="cycle-craft", tenant_id=TENANT, business_id=BIZ,
        trigger="synthetic", trigger_token="", created_at=now,
        starting_state_version="sv-1", evidence_watermark="wm-1",
        stages=[CycleStageState(stage=s) for s in CycleStage.ordered()],
        stage_index=0, completed=False, last_error="",
    )
    base.update(overrides)
    run = CycleRun(**base)
    run.state_output = dict(overrides.pop("state_output", {}) or {})
    return run


# ── Drill D support: in-memory SQLite runner funnel + kill switch ──────


@pytest_asyncio.fixture(scope="function")
async def sqlite_session() -> AsyncSession:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with SessionLocal() as session:
        yield session
    await engine.dispose()


async def _seed_business(db: AsyncSession, business_id):
    await db.execute(
        text(
            "INSERT INTO businesses (id, name, type, currency, constraints_json) "
            "VALUES (:id, 'Drill Biz', 'retail', 'SAR', :constraints)"
        ),
        {"id": str(business_id), "constraints": json.dumps({})},
    )


async def _seed_item(db: AsyncSession, business_id, item_id, *, stock=50.0):
    await db.execute(
        text(
            "INSERT INTO items (id, business_id, name, sku, unit, cost_price, sell_price, is_active) "
            "VALUES (:id, :b, 'Widget', 'DRL1', 'piece', 10, 20, true)"
        ),
        {"id": str(item_id), "b": str(business_id)},
    )
    await db.execute(
        text(
            "INSERT INTO inventory (id, item_id, business_id, current_stock, safety_stock, lead_time_days, updated_at) "
            "VALUES (:inv, :iid, :b, :stock, 5, 7, CURRENT_TIMESTAMP)"
        ),
        {"inv": str(uuid.uuid4()), "iid": str(item_id), "b": str(business_id), "stock": stock},
    )


async def _stock(db: AsyncSession, item_id) -> float:
    res = await db.execute(text("SELECT current_stock FROM inventory WHERE item_id = :i"), {"i": str(item_id)})
    return float(res.scalar_one())


async def _executed_count(db: AsyncSession, business_id) -> int:
    res = await db.execute(text("SELECT count(*) FROM executed_actions WHERE business_id = :b"), {"b": str(business_id)})
    return int(res.scalar_one())


def _manual_kwargs(business_id, item_id, qty=25.0):
    return dict(
        business_id=business_id, action_type="RESTOCK", entity_type="item", entity_id=item_id,
        payload={"restock_qty": qty}, previous_state={"current_stock": 50.0},
        new_state={"restock_qty": qty}, user_id=None, source="money_audit",
    )


@pytest_asyncio.fixture()
async def kill_switch_env(monkeypatch):
    from app.config import get_settings

    monkeypatch.setenv("USE_TEMPORAL", "false")
    monkeypatch.setenv("EXECUTION_ENABLED", "false")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


# ── Drills A–L ─────────────────────────────────────────────────────────


class TestPhase4IFailureDrills:
    # A · duplicate delivery of the same trigger
    async def test_drill_a_duplicate_delivery_single_logical_cycle(self) -> None:
        repo, orch, run = await self._run_full(BIZ, "tok-a")
        assert run.completed is True
        again = await orch.start(tenant_id=TENANT, business_id=BIZ, trigger="synthetic", trigger_token="tok-a")
        assert again.cycle_id == run.cycle_id                  # [V] same logical cycle
        assert again.completed is True                         # [V] no regression
        replay = await orch.load(BIZ, run.cycle_id)
        receipt_before = replay.state_output["execution"]["receipt"]["receipt_id"]
        await orch.run_all(replay)
        assert replay.state_output["execution"]["receipt"]["receipt_id"] == receipt_before  # [V] no duplicate effect
        assert len(repo.all(BIZ)) == 1                         # [V] one durable row

    @staticmethod
    async def _run_full(biz: str, token: str):
        repo = InMemoryCycleRepository()
        orch = _orchestrator(repo, biz=biz)
        run = await orch.start(tenant_id=TENANT, business_id=biz, trigger="synthetic", trigger_token=token)
        await orch.run_all(run)
        return repo, orch, run

    # B · crash DURING execution (no receipt) -> never blind-rerun, never verified
    async def test_drill_b_crash_during_execution_is_unknown_required(self) -> None:
        repo = InMemoryCycleRepository()
        orch = _orchestrator(repo, biz=BIZ)
        run = await orch.start(tenant_id=TENANT, business_id=BIZ, trigger="synthetic", trigger_token="tok-b")
        exec_idx = next(i for i, s in enumerate(run.stages) if s.stage == CycleStage.EXECUTION)
        while run.stage_index < exec_idx:
            if not await orch.run_one_stage(run):
                break
        crashed = await repo.load(BIZ, run.cycle_id)
        stage = crashed.stages[crashed.stage_index]
        stage.status = "running"
        stage.started_at = _t()
        stage.attempts += 1
        await repo.save(crashed)

        resumed = await repo.load(BIZ, run.cycle_id)
        assert await orch.run_one_stage(resumed) is True       # converges WITHOUT re-running
        charge = resumed.state_output["execution"]["receipt"]["details"]["reason"]
        assert "unconfirmed_external_outcome_after_restart" in str(charge)
        assert await orch.run_one_stage(resumed) is True
        rec = resumed.state_output["reconciliation"]
        assert rec["allow_retry"] is False                     # [V] never blind-retried
        assert rec["reconciliation_required"] is True          # [V] REQUIRED
        assert rec["status"] == "unknown_external_outcome"
        assert await orch.run_one_stage(resumed) is True
        out = resumed.state_output["outcome"]
        assert out["verification_status"] == VerificationStatus.UNVERIFIED.value  # [V] cannot fabricate
        assert out["reason"] == "unknown_external_outcome_reconciliation_required"

    # C · crash AFTER a stage completes -> handler NOT re-run
    async def test_drill_c_crash_after_ok_converges_without_rerun(self) -> None:
        repo, orch, run = await self._run_full(BIZ, "tok-c")
        rec_idx = next(i for i, s in enumerate(run.stages) if s.stage == CycleStage.RECOMMENDATION)
        rewound = await repo.load(BIZ, run.cycle_id)
        marker_before = rewound.state_output["recommendations"][0]["material_hash"]
        attempts_before = rewound.stages[rec_idx].attempts
        await orch.run_all(rewound)
        assert rewound.stages[rec_idx].attempts == attempts_before          # [V] no duplicate handler run
        assert rewound.state_output["recommendations"][0]["material_hash"] == marker_before
        assert rewound.completed is True

    # D · global kill switch: every dispatch refused, zero mutation
    async def test_drill_d_kill_switch_refuses_manual_and_simulated(self, sqlite_session, kill_switch_env):
        from app.orchestration.runner import ExecutionDisabledError, run_manual_action, run_simulated

        biz, item = uuid.uuid4(), uuid.uuid4()
        await _seed_business(sqlite_session, biz)
        await _seed_item(sqlite_session, biz, item)
        await sqlite_session.commit()

        with pytest.raises(ExecutionDisabledError) as excinfo:
            await run_manual_action(sqlite_session, **_manual_kwargs(biz, item))
        assert "EXECUTION_ENABLED=false" in str(excinfo.value)
        with pytest.raises(ExecutionDisabledError):
            await run_simulated(
                sqlite_session, business_id=biz, action_type="RESTOCK",
                entity_type="item", entity_id=item, payload={"restock_qty": 25.0},
            )
        await sqlite_session.commit()
        assert await _stock(sqlite_session, item) == 50.0      # [V] no business mutation
        assert await _executed_count(sqlite_session, biz) == 0  # [V] no execution record

    # E · cross-tenant read fails closed
    def test_drill_e_cross_tenant_read_fails_closed(self, tmp_path) -> None:
        ledger = OutcomeLedger(str(tmp_path / "ledger.db"))
        for key in ("tA:1", "tB:1", "tB:2"):
            ledger.record(decision_key=key, capability="business_loop.verified", deterministic_decision="r", source="business_loop")
            ledger.record_verified_result(decision_key=key, outcome_status="confirmed", verified=True, actual_impact_sar=10.0)
        rows = ledger.verified_outcomes()

        def scoped(*allowed: str) -> list[dict]:
            return [r for r in rows if r.get("decision_key") in set(allowed)]

        assert {r["decision_key"] for r in scoped("tA:1")} == {"tA:1"}  # [V] owner sees own rows only
        assert {r["decision_key"] for r in scoped("tB:1")} == {"tB:1"}  # [V] tenant B sees B only (never tA)
        assert scoped() == []                                     # [V] empty access -> zero rows (fail closed)

    # F · phantom verification: absent row NEVER verifies
    async def test_drill_f_phantom_can_never_verify(self, tmp_path) -> None:
        ledger = OutcomeLedger(str(tmp_path / "ledger.db"))
        assert ledger.record_verified_result(decision_key="k:phantom", outcome_status="confirmed", verified=True) is False  # [V]
        assert ledger.record(decision_key="k:real", capability="recovery.rank", deterministic_decision="restock", source="jev")
        assert ledger.record_verified_result(decision_key="k:real", outcome_status="confirmed", verified=True, actual_impact_sar=12.5) is True  # [V]
        assert ledger.verified_outcomes()[0]["decision_key"] == "k:real"

    # G · known rejection vs unknown outcome: only unknown demands reconciliation
    async def test_drill_g_known_rejection_is_not_reconciliation_required(self) -> None:
        known = _craft_run(
            stage_index=15, completed=False,
            state_output={
                "execution": {"action_type": "reorder", "execution_key": "exec-1", "attempt": 1,
                              "receipt": {"ok": False, "details": {"reason": "dry_run_rejected"}}},
                "reconciliation": {"allow_retry": False, "reason": "dry_run_rejected"},
            },
        )
        assert known.state_output["reconciliation"].get("reconciliation_required") is not True  # [V] known rejection
        assert known.state_output["reconciliation"]["allow_retry"] is False

        unknown = _craft_run(
            stage_index=15, completed=False,
            state_output={
                "execution": {"action_type": "reorder", "execution_key": "exec-2", "attempt": 1,
                              "receipt": {"ok": False, "details": {"reason": "timeout_unknown_external_outcome"}}},
                "reconciliation": {"allow_retry": False, "reason": "timeout",
                                   "reconciliation_required": True, "status": "unknown_external_outcome"},
            },
        )
        assert unknown.state_output["reconciliation"]["reconciliation_required"] is True   # [V] unknown REQUIRED
        assert unknown.state_output["reconciliation"]["status"] == "unknown_external_outcome"

    # H · terminal regression: completed cycle immutable
    async def test_drill_h_terminal_regression_is_conflict(self) -> None:
        repo, orch, run = await self._run_full(BIZ, "tok-h")
        persisted = await repo.load(BIZ, run.cycle_id)
        await repo.save(persisted)                             # identical re-save allowed
        tampered = await repo.load(BIZ, run.cycle_id)
        tampered.completed = False
        tampered.stage_index = 0
        with pytest.raises(CycleRunConflictError):             # [V] terminal guard
            await repo.save(tampered)

    # I · retry budget exhaustion: cursor and attempts frozen
    async def test_drill_i_retry_budget_exhaustion_blocks_cleanly(self) -> None:
        repo = InMemoryCycleRepository()
        orch = CycleOrchestrator(
            repository=repo, evidence=EvidenceStore(),
            policy=CyclePolicy(shariah_approved=True, max_retries_per_stage=1),
        )
        run = await orch.start(tenant_id=TENANT, business_id=BIZ, trigger_token="tok-i")
        run.stages[0].status = "failed"
        run.stages[0].attempts = orch.policy.max_retries_per_stage
        run.stages[0].error = "boom"
        await repo.save(run)
        loaded = await repo.load(BIZ, run.cycle_id)
        assert await orch.run_one_stage(loaded) is False       # [V] blocked
        assert loaded.completed is False                       # not FAILED-complete
        assert loaded.stage_index == 0                         # cursor frozen
        assert loaded.stages[0].attempts == orch.policy.max_retries_per_stage  # [V] budget untouched

    # J · provider identity: mocked/fallback NEVER labelled Jev
    async def test_drill_j_attribution_honesty(self) -> None:
        from app.services.business_loop.advisory import AdvisorySource as AdvisorySourceMod
        from app.services.business_loop.advisory import deterministic_only_advisor

        contract = frozenset({"RESTOCK", "REORDER", "DISCOUNT", "DO_NOTHING"})
        ctx = {"payload": {"tenant_id": TENANT, "business_id": BIZ},
               "deterministic_decision": "REORDER", "purpose": "continuous_business_loop", "contract": contract}

        async def mocked(capability, context):
            return {"decision": "REORDER", "suggested": None, "confidence": 0.8, "source": "mocked", "provider": "mocked"}

        from app.services.business_loop.advisory import consult_advisory

        ta = await consult_advisory(mocked, capability="business_loop.action_selection", context=ctx, contract=contract)
        assert ta.source == AdvisorySourceMod.MOCKED and ta.source != AdvisorySourceMod.JEV  # [V] mocked stays mocked
        fallback = await deterministic_only_advisor("business_loop.action_selection", ctx)
        assert fallback["provider"] == "deterministic"         # [V] fallback never claims Jev
        assert fallback["source"] == "deterministic_only"
        quality = attribution_quality(
            verification_status=VerificationStatus.REPORTED, verification_method="",
            observed_impact_sar=None,
            advisory_source=AdvisorySourceMod.JEV.value, advisory_provider="jev-live",
        )
        assert quality == "jev_advisory_only"                  # [V] Jev alone insufficient

    # K · DLP prompt leak: raw merchant data never crosses the wire
    async def test_drill_k_dlp_prompt_is_clean_on_the_wire(self) -> None:
        from app.security.capsule import CapsuleSigner
        from app.security.privacy_firewall import build_capsule_for_payload

        payload = {
            "tenant_id": "tenant-abc-111",
            "business_id": "biz-987654",
            "business": {"business_type": "auto_parts", "total_capital_at_risk_sar": 150000, "cash_budget": 45000},
            "items": [{"sku": "SKU-A1", "name": "Premium Brake Pads", "current_stock": 42, "days_of_supply": 3},
                      {"sku": "SKU-B1", "name": "Budget Oil Filter", "current_stock": 140, "days_of_supply": 28}],
        }
        capsule = build_capsule_for_payload(payload, capability="business_loop.action_selection", purpose="continuous_business_loop")
        assert CapsuleSigner().verify(capsule) is True
        state = capsule.for_prompt()
        state_text = json.dumps(state, sort_keys=True)
        for secret in ("tenant-abc-111", "biz-987654", "SKU-A1", "SKU-B1", "Premium Brake Pads",
                       "Budget Oil Filter", "42", "140", "150000", "45000"):
            assert secret not in state_text                   # [V] no raw merchant data on the wire
        assert state["items"][0]["ref"] and "stock_band" in state["items"][0]  # [V] opaque refs + bands

        from app.services.ai_providers.jev import consult as jev_consult

        with pytest.raises(TypeError):                        # [V] raw dict can never reach Jev
            await jev_consult(question="x", capsule={"state": "raw"}, deterministic_decision="REORDER", client=None)  # type: ignore[arg-type]

    # L · stale approval: materially changed recommendation cannot reuse it
    async def test_drill_l_stale_approval_never_authorizes(self) -> None:
        approval = self._approve("rec-9", 3, "material-hash-9")
        assert approval["binding_key"] == "rec-9:v3:material-hash-9"
        stale = self._approve("rec-9", 3, "material-hash-9-TAMPERED")
        assert stale["binding_key"] != approval["binding_key"]  # [V] different material -> different binding
        assert "TAMPERED" not in approval["binding_key"]

    @staticmethod
    def _approve(recommendation_id: str, version: int, material_hash: str) -> dict:
        from app.services.business_loop.governance import approve_binding

        return approve_binding(
            recommendation_id=recommendation_id, recommendation_version=version,
            material_hash=material_hash, approved_by="owner",
        )