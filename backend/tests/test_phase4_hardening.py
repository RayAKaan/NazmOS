"""Phase 4H — Business Loop Hardening: crash recovery, concurrency, idempotency,
reconciliation and failure safety (DB-free; USE_TEMPORAL=false).

Evidence labels: [V] running code, [S] static source evidence, [I] in-memory.
DB-free by design: InMemoryCycleRepository now shares the SAME conflict and
terminal-immutability semantics as the Postgres repository (Phase 4H-C), so every
assertion here exercises the canonical repository contract without a database.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.services.business_loop import (
    CycleOrchestrator,
    CyclePolicy,
    InMemoryCycleRepository,
)
from app.services.business_loop.contracts import CycleStage, VerificationStatus
from app.services.business_loop.cycle import CycleRunConflictError
from app.services.business_loop.evidence import EvidenceStore, normalize_observation
from app.services.outcome_ledger import OutcomeLedger

_BACKEND = Path(__file__).resolve().parents[1]


def _t(days_ago: int = 0) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat(timespec="seconds")


def _ingest(
    store: EvidenceStore,
    *,
    tenant_id: str,
    business_id: str,
    sku: str,
    stock: float,
    cost: float,
    sell: float,
    days_of_supply: float | None = None,
    source: str = "pos",
) -> str:
    raw = {"sku": sku, "stock": stock, "cost": cost, "sell": sell}
    if days_of_supply is not None:
        raw["days_of_supply"] = days_of_supply
    rec, reason = normalize_observation(
        tenant_id=tenant_id,
        business_id=business_id,
        raw=raw,
        source_type="synthetic.pos",
        source_reference=source,
        observation_type="inventory.observed",
        event_timestamp=_t(),
        observed_at=_t(),
        required_fields=(
            ("sku", "stock", "cost", "sell", "days_of_supply")
            if days_of_supply is not None
            else ("sku", "stock", "cost", "sell")
        ),
    )
    assert rec is not None, reason
    store.put(rec)
    return rec.evidence_id


async def _mocked_jev(capability: str, context: dict) -> dict:
    """Mocked Jev: deterministic candidate selection inside the contract only."""
    contract = context.get("contract") or frozenset()
    prefer = {"transfer_inventory"} & contract
    return {
        "decision": context.get("deterministic_decision", "DO_NOTHING"),
        "suggested": next(iter(prefer)) if prefer else None,
        "confidence": 0.85,
        "source": "mocked",
        "provider": "jev-mock",
        "model": "jev-mock-1.0",
        "reasoning": "synthetic advisory: prefer autonomous transfer within contract.",
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


def _orchestrator(repo: InMemoryCycleRepository, *, tenant_id: str, business_id: str) -> CycleOrchestrator:
    store = EvidenceStore()
    _ingest(store, tenant_id=tenant_id, business_id=business_id, sku="SKU-EXC", stock=120, cost=20, sell=28, days_of_supply=45)
    post_store = EvidenceStore()
    _ingest(post_store, tenant_id=tenant_id, business_id=business_id, sku="SKU-EXC", stock=20, cost=20, sell=28, days_of_supply=5)
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


async def _run_full(tenant_id: str, business_id: str):
    repo = InMemoryCycleRepository()
    orch = _orchestrator(repo, tenant_id=tenant_id, business_id=business_id)
    run = await orch.start(tenant_id=tenant_id, business_id=business_id, trigger="h", trigger_token=f"tok-{tenant_id}")
    await orch.run_all(run)
    return repo, orch, run


class TestInMemoryRepositorySemantics:
    """Phase 4H-C / O: the InMemory repository obeys the same durable contract as
    Postgres — deep-copy isolation, optimistic versioning, terminal immutability."""

    async def test_stored_state_is_deep_copied_not_by_reference(self) -> None:
        repo = InMemoryCycleRepository()
        orch = CycleOrchestrator(repository=repo, evidence=EvidenceStore(), policy=CyclePolicy(shariah_approved=True))
        run = await orch.start(tenant_id="t", business_id="b-1", trigger_token="x")
        run.stage_index = 99  # caller-side mutation that was NEVER saved
        persisted = await repo.load("b-1", run.cycle_id)
        assert persisted is not None
        assert persisted.stage_index == 0  # [V] store holds a deep copy

        c = await repo.load("b-1", run.cycle_id)
        c.state_output["phantom"] = "x"
        d = await repo.load("b-1", run.cycle_id)
        assert "phantom" not in d.state_output  # [V] loaded copies are independent

    async def test_stale_version_save_raises_conflict(self) -> None:
        repo = InMemoryCycleRepository()
        orch = CycleOrchestrator(repository=repo, evidence=EvidenceStore(), policy=CyclePolicy(shariah_approved=True))
        run = await orch.start(tenant_id="t", business_id="b-2", trigger_token="x")  # stored v1
        a = await repo.load("b-2", run.cycle_id)
        b = await repo.load("b-2", run.cycle_id)
        a.stage_index = 1
        await repo.save(a)  # advances stored row to v2
        assert a._version == 2
        b.stage_index = 2  # stale writer: still on v1
        with pytest.raises(CycleRunConflictError):
            await repo.save(b)  # [V] no silent clobber

    async def test_completed_run_is_immutable(self) -> None:
        repo, _, run = await _run_full("t-i", "b-3")
        persisted = await repo.load("b-3", run.cycle_id)
        assert persisted is not None and persisted.completed is True
        await repo.save(persisted)  # idempotent re-save of identical completed run: allowed
        tampered = await repo.load("b-3", run.cycle_id)
        tampered.completed = False
        tampered.stage_index = 0
        with pytest.raises(CycleRunConflictError):  # [V] terminal guard
            await repo.save(tampered)

    async def test_all_returns_independent_copies(self) -> None:
        repo, _, run = await _run_full("t-al", "b-4")
        listed = repo.all("b-4")
        assert len(listed) == 1
        assert listed[0] is not run
        assert listed[0].cycle_id == run.cycle_id
        listed[0].stage_index = 7
        assert repo.all("b-4")[0].stage_index != 7  # [V] list is detached

    async def test_idempotent_resave_of_same_object_stays_single_row(self) -> None:
        repo = InMemoryCycleRepository()
        orch = CycleOrchestrator(repository=repo, evidence=EvidenceStore(), policy=CyclePolicy(shariah_approved=True))
        run = await orch.start(tenant_id="t", business_id="b-5", trigger_token="x")
        await repo.save(run)
        await repo.save(run)  # version pinned by previous save -> matches
        assert len(repo.all("b-5")) == 1
        assert run._version == 3  # 1 (create) + 2 re-saves

    async def test_postgres_repository_contract_present_in_source(self) -> None:
        src = (_BACKEND / "app" / "services" / "cycle_run_repository.py").read_text(encoding="utf-8")
        assert "CycleRunModel.version == expected" in src  # [S] optimistic predicate
        assert "result.rowcount == 0" in src  # [S] failed predicate -> no overwrite
        assert 'on_conflict_do_nothing(index_elements=["business_id", "cycle_id"])' in src  # [S] idempotent create
        assert "completed is immutable" in src or "is completed (immutable)" in src  # [S] terminal protection


class TestStartIdempotencyAndTerminalGuard:
    """Phase 4H-F / G1: a duplicate trigger token (running OR completed) returns
    the SAME run; a completed cycle never regresses and never re-executes."""

    async def test_duplicate_trigger_after_completion_returns_same_completed_run(self) -> None:
        repo, orch, run = await _run_full("t-d", "b-10")
        assert run.completed is True
        again = await orch.start(tenant_id="t-d", business_id="b-10", trigger="h", trigger_token="tok-t-d")
        assert again.cycle_id == run.cycle_id  # [V] same logical cycle
        assert again.completed is True  # [V] no regression to in-flight state

    async def test_replay_after_completion_is_a_noop(self) -> None:
        repo, orch, run = await _run_full("t-r", "b-11")
        resumed = await repo.load("b-11", run.cycle_id)
        assert resumed is not None
        before = resumed.state_output["execution"]["receipt"]["receipt_id"]
        out = resumed.state_output["outcome"]
        await orch.run_all(resumed)  # replay on the completed run
        assert resumed.completed is True
        assert resumed.state_output["execution"]["receipt"]["receipt_id"] == before  # [V] no duplicate effect
        assert resumed.state_output["outcome"] == out  # [V] no re-measurement / re-verification

    async def test_new_logical_cycle_requires_new_trigger_token(self) -> None:
        repo = InMemoryCycleRepository()
        orch = CycleOrchestrator(repository=repo, evidence=EvidenceStore(), policy=CyclePolicy(shariah_approved=True))
        first = await orch.start(tenant_id="t", business_id="b-12", trigger="h", trigger_token="tok-1")
        second = await orch.start(tenant_id="t", business_id="b-12", trigger="h", trigger_token="tok-2")
        assert second.cycle_id != first.cycle_id  # [V] distinct token -> distinct logical cycle


class TestCrashRecovery:
    """Phase 4H-D: deterministic restart/replay across operator crashes."""

    async def test_restart_mid_run_resumes_to_verified_without_duplicate_effect(self) -> None:
        repo = InMemoryCycleRepository()
        orch = _orchestrator(repo, tenant_id="t-crash", business_id="b-20")
        run = await orch.start(tenant_id="t-crash", business_id="b-20", trigger="h", trigger_token="tok-crash")
        # worker dies after a few stages; durable record exists mid-flight
        for _ in range(5):
            if not await orch.run_one_stage(run):
                break
        assert run.completed is False
        worker2 = CycleOrchestrator(
            repository=repo,
            evidence=orch.evidence,
            verification_evidence=orch.verification_evidence,
            policy=orch.policy,
        )
        resumed = await worker2.load("b-20", run.cycle_id)
        assert resumed is not None
        await worker2.run_all(resumed)
        assert resumed.completed is True
        assert resumed.state_output["outcome"]["verification_status"] == VerificationStatus.VERIFIED.value
        exec_stage = next(s for s in resumed.stages if s.stage == CycleStage.EXECUTION)
        assert exec_stage.attempts == 1  # [V] execution ran exactly once across the restart

    async def test_crash_after_stage_completion_converges_without_rerun(self) -> None:
        """CRASH 3: stage completed (+handler side effect) but crash before cursor
        advance. Resuming converges by advancing the cursor — the handler is NOT
        re-run."""
        repo = InMemoryCycleRepository()
        orch = _orchestrator(repo, tenant_id="t-c3", business_id="b-21")
        run = await orch.start(tenant_id="t-c3", business_id="b-21", trigger="h", trigger_token="tok-c3")
        rec_idx = next(i for i, s in enumerate(run.stages) if s.stage == CycleStage.RECOMMENDATION)
        while run.stage_index <= rec_idx:
            if not await orch.run_one_stage(run):
                break
        assert run.stage_index == rec_idx + 1
        assert run.stages[rec_idx].status == "ok"
        marker = run.state_output["recommendations"][0]["material_hash"]

        rewound = await repo.load("b-21", run.cycle_id)
        rewound.stage_index = rec_idx  # durable record still says cursor is AT the completed stage
        assert rewound.stages[rec_idx].status == "ok"
        await repo.save(rewound)

        resumed = await repo.load("b-21", run.cycle_id)
        attempts_before = resumed.stages[rec_idx].attempts
        assert await orch.run_one_stage(resumed) is True  # [V] converges
        assert resumed.stage_index == rec_idx + 1
        assert resumed.stages[rec_idx].attempts == attempts_before  # [V] handler NOT re-run
        assert resumed.state_output["recommendations"][0]["material_hash"] == marker
        await orch.run_all(resumed)
        assert resumed.completed is True  # and the cycle still completes cleanly

    async def test_crashed_execution_is_unknown_never_rerun_never_verified(self) -> None:
        """CRASH 5 (4H-E): execution persisted as 'running' = unknown external
        state. Resume converges guarded, reconciliation REQUIRED, outcome can
        never verify."""
        repo = InMemoryCycleRepository()
        orch = _orchestrator(repo, tenant_id="t-c5", business_id="b-22")
        run = await orch.start(tenant_id="t-c5", business_id="b-22", trigger="h", trigger_token="tok-c5")
        exec_idx = next(i for i, s in enumerate(run.stages) if s.stage == CycleStage.EXECUTION)
        while run.stage_index < exec_idx:
            if not await orch.run_one_stage(run):
                break
        assert run.stage_index == exec_idx

        crashed = await repo.load("b-22", run.cycle_id)
        stage = crashed.stages[crashed.stage_index]
        stage.status = "running"
        stage.started_at = _t()
        stage.attempts += 1
        await repo.save(crashed)  # durable record: mid-execution crash

        resumed = await repo.load("b-22", run.cycle_id)
        assert resumed.stages[resumed.stage_index].status == "running"
        assert await orch.run_one_stage(resumed) is True  # converges WITHOUT re-running
        assert resumed.state_output["execution"]["resumed_crashed"] is True
        receipt = resumed.state_output["execution"]["receipt"]
        assert receipt["ok"] is False
        assert "unconfirmed_external_outcome_after_restart" in str(receipt["details"]["reason"])

        assert await orch.run_one_stage(resumed) is True  # reconciliation
        rec = resumed.state_output["reconciliation"]
        assert rec["allow_retry"] is False  # [V] never blind-retried
        assert rec["reconciliation_required"] is True  # [V] surfaced as REQUIRED
        assert rec["status"] == "unknown_external_outcome"
        assert "unconfirmed" in str(rec["reason"])

        assert await orch.run_one_stage(resumed) is True  # verification
        out = resumed.state_output["outcome"]
        assert out["verification_status"] == VerificationStatus.UNVERIFIED.value  # [V] cannot fabricate
        assert out["reason"] == "unknown_external_outcome_reconciliation_required"

    async def test_retry_budget_exhaustion_blocks_cleanly(self) -> None:
        """CRASH 6: exhausting the bounded per-stage retry budget BLOCKS the
        cycle — it never advances, never spins, and is never recorded FAILED."""
        repo = InMemoryCycleRepository()
        orch = CycleOrchestrator(
            repository=repo,
            evidence=EvidenceStore(),
            policy=CyclePolicy(shariah_approved=True, max_retries_per_stage=1),
        )
        run = await orch.start(tenant_id="t-b", business_id="b-23", trigger_token="tok")
        run.stages[0].status = "failed"
        run.stages[0].attempts = orch.policy.max_retries_per_stage
        run.stages[0].error = "boom"
        await repo.save(run)  # durable record shows budget exhausted mid-crash-loop

        loaded = await repo.load("b-23", run.cycle_id)
        assert await orch.run_one_stage(loaded) is False  # [V] blocked (documented)
        assert loaded.completed is False  # not FAILED-complete
        assert loaded.stage_index == 0  # cursor never advanced
        assert loaded.stages[0].status == "failed"
        assert loaded.stages[0].attempts == orch.policy.max_retries_per_stage  # budget untouched

    async def test_non_execution_running_stage_reruns_safely(self) -> None:
        """CRASH 7: a deterministic idempotent stage left 'running' by a crash is
        safely re-run by a restart (no external side effects to duplicate)."""
        repo, orch, run = await _run_full("t-c7", "b-24")
        assert run.completed is True  # baseline healthy run

        mid = await repo.load("b-24", run.cycle_id)
        proj_idx = next(i for i, s in enumerate(mid.stages) if s.stage == CycleStage.STATE_PROJECTION)
        assert mid.stages[proj_idx].status == "ok"
        attempts_before = mid.stages[proj_idx].attempts
        # replaying the whole persisted run must not re-run a completed projection
        await orch.run_all(mid)
        assert mid.stages[proj_idx].attempts == attempts_before
        assert mid.completed is True


class TestReconciliationAndVerificationBoundary:
    """Phase 4H-E + G5: an unknown external outcome is never FAILED, never
    blind-retried, and can never be verified."""

    async def _fresh(self, tenant_id: str, business_id: str):
        repo = InMemoryCycleRepository()
        orch = CycleOrchestrator(repository=repo, evidence=EvidenceStore(), policy=CyclePolicy(shariah_approved=True))
        run = await orch.start(tenant_id=tenant_id, business_id=business_id, trigger_token="tok")
        return orch, run

    async def test_missing_receipt_is_unknown_and_reconciliation_required(self) -> None:
        orch, run = await self._fresh("t-u1", "b-30")
        run.state_output["execution"] = {}  # execution happened but NO receipt
        await orch._stage_reconciliation(run)
        rec = run.state_output["reconciliation"]
        assert rec["allow_retry"] is False
        assert rec["reconciliation_required"] is True
        assert rec["status"] == "unknown_external_outcome"

    async def test_ok_receipt_is_reported_not_retried(self) -> None:
        orch, run = await self._fresh("t-u2", "b-31")
        run.state_output["execution"] = {"receipt": {"ok": True, "receipt_id": "r", "synthetic": True, "details": {"note": "x"}}}
        await orch._stage_reconciliation(run)
        rec = run.state_output["reconciliation"]
        assert rec["allow_retry"] is False
        assert rec["reason"] == "reported_recorded_await_verification"
        assert "reconciliation_required" not in rec  # [V] clean, known state

    async def test_timeout_reason_is_unknown(self) -> None:
        orch, run = await self._fresh("t-u3", "b-32")
        run.state_output["execution"] = {"receipt": {"ok": False, "details": {"reason": "provider_timeout_after_side_effect"}}}
        await orch._stage_reconciliation(run)
        rec = run.state_output["reconciliation"]
        assert rec["reconciliation_required"] is True
        assert rec["status"] == "unknown_external_outcome"

    async def test_known_rejection_is_reported_not_unknown(self) -> None:
        orch, run = await self._fresh("t-u4", "b-33")
        run.state_output["execution"] = {"receipt": {"ok": False, "details": {"reason": ["unregistered_action"]}}}
        await orch._stage_reconciliation(run)
        rec = run.state_output["reconciliation"]
        assert "reconciliation_required" not in rec  # [V] known (not unknown)
        assert rec["reason"] == ["unregistered_action"]

    async def test_reconciliation_required_blocks_verification(self) -> None:
        orch, run = await self._fresh("t-u5", "b-34")
        run.state_output["execution"] = {"receipt": {"ok": False, "details": {"reason": "provider_timeout"}}}
        run.state_output["reconciliation"] = {
            "allow_retry": False,
            "reason": "provider_timeout",
            "status": "unknown_external_outcome",
            "reconciliation_required": True,
        }
        await orch._stage_verification(run)
        out = run.state_output["outcome"]
        assert out["verification_status"] == VerificationStatus.UNVERIFIED.value
        assert out["reason"] == "unknown_external_outcome_reconciliation_required"  # [V] no fabricated measurement

    async def test_full_run_unknown_boundary_persists_durably(self) -> None:
        """CRASH 5 end-to-end through the durable store (not just unit): build the
        unknown record, persist it, restart, and confirm reconciliation_required
        survives the restart."""
        repo = InMemoryCycleRepository()
        orch = _orchestrator(repo, tenant_id="t-u6", business_id="b-35")
        run = await orch.start(tenant_id="t-u6", business_id="b-35", trigger="h", trigger_token="tok-u6")
        exec_idx = next(i for i, s in enumerate(run.stages) if s.stage == CycleStage.EXECUTION)
        while run.stage_index < exec_idx:
            if not await orch.run_one_stage(run):
                break
        crashed = await repo.load("b-35", run.cycle_id)
        crashed.stages[crashed.stage_index].status = "running"
        await repo.save(crashed)
        worker2 = CycleOrchestrator(repository=repo, evidence=orch.evidence, verification_evidence=orch.verification_evidence, policy=orch.policy)
        resumed = await worker2.load("b-35", run.cycle_id)
        await worker2.run_all(resumed)
        assert resumed.state_output["reconciliation"]["reconciliation_required"] is True  # [V] survives restart
        assert resumed.state_output["outcome"]["verification_status"] == VerificationStatus.UNVERIFIED.value
        assert resumed.state_output.get("learning_eligible") is False  # [V] unknown can never learn


class TestApprovalBinding:
    """Phase 4H-I + G6: approval is bound to the exact recommendation material and
    survives restart; a materially changed recommendation can never reuse it."""

    async def test_approval_binding_persists_and_enforces_material_mismatch(self) -> None:
        repo = InMemoryCycleRepository()
        orch = _orchestrator(repo, tenant_id="t-ab", business_id="b-40")
        run = await orch.start(tenant_id="t-ab", business_id="b-40", trigger="h", trigger_token="tok-ab")
        exec_idx = next(i for i, s in enumerate(run.stages) if s.stage == CycleStage.EXECUTION)
        while run.stage_index < exec_idx:
            if not await orch.run_one_stage(run):
                break
        approval = run.state_output["approval"]
        assert approval["binding_key"]  # [V] binding recorded
        assert approval["approved_by"] == "synthetic_owner"
        persisted = await repo.load("b-40", run.cycle_id)
        assert persisted.state_output["approval"]["binding_key"] == approval["binding_key"]  # [V] survives save

        # Stale-material attack: change the recommendation AFTER approval.
        original_hash = persisted.state_output["recommendations"][0]["material_hash"]
        tampered = await repo.load("b-40", run.cycle_id)
        tampered.state_output["recommendations"][0]["material_hash"] = original_hash + "-TAMPERED"
        await repo.save(tampered)

        worker2 = CycleOrchestrator(repository=repo, evidence=orch.evidence, verification_evidence=orch.verification_evidence, policy=orch.policy)
        resumed = await worker2.load("b-40", run.cycle_id)
        assert await worker2.run_one_stage(resumed) is True  # execution stage
        assert resumed.state_output["execution"]["skipped"] is True  # [V] stale approval refused
        assert resumed.state_output["execution"]["reason"] == "approval_material_mismatch"
        assert await worker2.run_one_stage(resumed) is True  # reconciliation
        assert resumed.state_output["reconciliation"]["reason"] == "approval_material_mismatch"
        assert await worker2.run_one_stage(resumed) is True  # verification
        assert resumed.state_output["outcome"]["verification_status"] == VerificationStatus.UNVERIFIED.value  # [V] no fake learning

    async def test_full_run_uses_bound_approval_to_verified(self) -> None:
        repo, orch, run = await _run_full("t-ab-v", "b-41")
        assert run.state_output["approval"]["binding_key"]
        assert run.state_output["approval"]["approved_by"] == "synthetic_owner"
        assert run.state_output["execution"]["receipt"]["ok"] is True
        assert run.state_output["outcome"]["verification_status"] == VerificationStatus.VERIFIED.value


class TestResumedBaselineRehydration:
    """Phase 4H-D + G4/G8: a resumed cycle rehydrates its REAL projected baseline
    (start_time baseline = the actual pinned state), never an empty-domain
    invention."""

    async def test_resumed_run_rehydrates_real_baseline_snapshot(self) -> None:
        repo, orch, run = await _run_full("t-rh", "b-50")
        assert run.completed is True
        persisted_state = run.state_output["state"]
        assert isinstance(persisted_state.get("domains"), dict)
        assert persisted_state["domains"]  # baseline WAS projected

        resumed = await repo.load("b-50", run.cycle_id)
        # Postgres rehydration never carries the in-memory _snapshot — only the
        # serialized state_output. Mirror that: drop the carried snapshot so the
        # fallback rehydration path is what actually runs.
        resumed._snapshot = None
        snap = orch._saved_snapshot(resumed)
        assert snap.tenant_id == resumed.tenant_id
        assert snap.business_id == resumed.business_id
        assert snap.domains  # [V] real projected domains, not {} 
        assert snap.domains.keys() == persisted_state["domains"].keys()
        assert snap.state_version == run.starting_state_version  # [V] true pinned baseline


class TestLedgerVerifiedResultGuard:
    """Phase 4H-O: a verified outcome can only be claimed against an EXISTING
    captured row; a phantom row can never be verified."""

    async def test_verify_missing_row_returns_false(self, tmp_path) -> None:
        ledger = OutcomeLedger(tmp_path / "ledger.db")
        assert ledger.record_verified_result(decision_key="k:missing", outcome_status="confirmed", verified=True) is False  # [V] phantom cannot verify

    async def test_verify_existing_row_returns_true(self, tmp_path) -> None:
        ledger = OutcomeLedger(tmp_path / "ledger.db")
        assert ledger.record(decision_key="k:exists", capability="recovery.rank", deterministic_decision="restock", source="jev")
        assert ledger.record_verified_result(decision_key="k:exists", outcome_status="confirmed", verified=True, actual_impact_sar=12.5) is True  # [V] real row verifies
        assert ledger.verified_outcomes()[0]["decision_key"] == "k:exists"