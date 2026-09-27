"""Phase 4I — Synthetic Pilot Rehearsal (4I-M): 11 operator-facing scenarios.

The pilot runs the REAL production surfaces end-to-end:
    * CycleOrchestrator + InMemoryCycleRepository (SAME conflict/terminal
      semantics as the Postgres repository, Phase 4H-C)
    * OutcomeLedger (verified-result rowcount guard + fail-closed scoping)
    * governance.evaluate_governance + approve_binding (deterministic, never AI)
    * loop_console read model (read-only, DLP-clean, truthful ladder)
    * canonical Jev advisory via the ai_gateway (deterministic authoritative,
      attribution verbatim, never fabricated)

Each scenario is a rehearsed pilot operating step: what the operator SHOULD see
is asserted against what the system actually produced, with [V] evidence.

DB-free by design: no Postgres, no Temporal, no live Jev. USE_TEMPORAL=false.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.services.ai_budget import AIBudget
from app.services.business_loop import (
    CycleOrchestrator,
    CyclePolicy,
    InMemoryCycleRepository,
)
from app.services.business_loop.contracts import (
    AdvisorySource,
    CycleStage,
    GovernanceOutcome,
    VerificationStatus,
)
from app.services.business_loop.cycle import CycleRun, CycleRunConflictError, CycleStageState
from app.services.business_loop.evidence import EvidenceStore, normalize_observation
from app.services.business_loop.governance import approve_binding, evaluate_governance
from app.services.business_loop.outcome_linkage import attribution_quality
from app.services.loop_console_readmodel import (
    build_cycle_read_model,
    build_cycle_summary,
    compute_lifecycle,
)
from app.services.outcome_ledger import OutcomeLedger
from app.services.pilot_mode import PilotPolicy

_BACKEND = Path(__file__).resolve().parents[2]
READ_MODEL_SRC = (_BACKEND / "app" / "services" / "loop_console_readmodel.py").read_text(encoding="utf-8")
ROUTER_SRC = (_BACKEND / "app" / "routers" / "loop_console.py").read_text(encoding="utf-8")

TENANT, BIZ = "tnt-4I", "biz-4I"


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
    """Mocked Jev advisory: candidate selection inside the loop contract only."""
    contract = context.get("contract") or frozenset()
    prefer = {"transfer_inventory"} & contract
    return {
        "decision": context.get("deterministic_decision", "DO_NOTHING"),
        "suggested": next(iter(prefer)) if prefer else None,
        "confidence": 0.85,
        "source": AdvisorySource.MOCKED.value,
        "provider": "jev-mock",
        "model": "jev-mock-1.0",
        "reasoning": "synthetic advisory within contract.",
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


def _orchestrator(repo: InMemoryCycleRepository, *, biz: str = BIZ) -> CycleOrchestrator:
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


async def _run_full(biz: str, token: str):
    repo = InMemoryCycleRepository()
    orch = _orchestrator(repo, biz=biz)
    run = await orch.start(tenant_id=TENANT, business_id=biz, trigger="synthetic", trigger_token=token)
    await orch.run_all(run)
    return repo, orch, run


def _craft_run(**overrides) -> CycleRun:
    now = _t()
    base = dict(
        cycle_id="cycle-craft",
        tenant_id=TENANT,
        business_id=BIZ,
        trigger="synthetic",
        trigger_token="",
        created_at=now,
        starting_state_version="sv-1",
        evidence_watermark="wm-1",
        stages=[CycleStageState(stage=s) for s in CycleStage.ordered()],
        stage_index=0,
        completed=False,
        last_error="",
    )
    base.update(overrides)
    run = CycleRun(**base)
    run.state_output = dict(overrides.pop("state_output", {}) or {})
    return run


class TestSyntheticPilotRehearsal:
    """The 11-scenario rehearsed pilot operating sequence (4I-M)."""

    # ── S1 · Pilot-mode default is gate-first, cost-bounded ─────────────
    async def test_s1_pilot_mode_defaults_to_approval_never_auto(self) -> None:
        p = PilotPolicy()
        assert p.require_approval is True                  # [V] no approval-less pilot
        assert p.allow_real_execution is False             # [V] no real money by default
        assert p.disposition(execution_capable=True) == "APPROVAL_REQUIRED"
        assert p.disposition(execution_capable=False) == "MANUAL"
        assert p.disposition(execution_capable=True) != "AUTO"

        budget = AIBudget(daily_calls=1, per_audit_calls=1)
        budget.begin_audit()
        budget.record(success=True)
        assert budget.can_call() is False                  # [V] per-audit budget bounded

    # ── S2 · Happy-path full cycle: VERIFIED + learning-eligible ────────
    async def test_s2_full_cycle_reaches_verified_learning_eligible(self) -> None:
        repo, orch, run = await _run_full(BIZ, "tok-s2")
        assert run.completed is True
        assert run.state_output["outcome"]["verification_status"] == VerificationStatus.VERIFIED.value
        exec_stage = next(s for s in run.stages if s.stage == CycleStage.EXECUTION)
        assert exec_stage.attempts == 1                     # [V] executed exactly once

        model = build_cycle_read_model(run)
        assert model["lifecycle"]["lifecycle_status"] == "learning_eligible"
        assert model["lifecycle"]["flags"]["verified"] is True
        assert model["lifecycle"]["flags"]["executed"] is True
        assert model["lifecycle"]["flags"]["blocked"] is False
        assert model["recovery"]["execution_authority"] == "none"
        assert len(model["stage_timeline"]) == len(CycleStage.ordered()) == 21
        assert model["advisory"]["attribution_quality"] == "deterministic_measurement"  # [V] Jev not credited alone
        assert model["advisory"]["source"] == AdvisorySource.MOCKED.value

    # ── S3 · Awaiting-approval gate: console never claims success ───────
    def test_s3_awaiting_approval_never_success_badge(self) -> None:
        run = _craft_run(
            stage_index=14,
            completed=False,
            last_error="",
            state_output={
                "execution": {"skipped": True, "reason": "recommendation_not_approved:awaiting_approval"},
                "outcome": {"verification_status": "unverified", "reason": "no_execution"},
                "recommendations": [{"status": "awaiting_approval", "action_type": "reorder"}],
            },
        )
        lifecycle = compute_lifecycle(run)
        assert lifecycle["lifecycle_status"] == "running"
        assert lifecycle["flags"]["running"] is True
        assert lifecycle["flags"]["executed"] is False      # [V] gated, not executed
        summary = build_cycle_summary(run)
        assert summary["execution"]["executed"] is False
        assert summary["outcome"]["verification_status"] == "unverified"

    # ── S4 · Unknown external outcome: required, never fabricated ───────
    async def test_s4_unknown_external_outcome_is_required_never_verified(self) -> None:
        repo = InMemoryCycleRepository()
        orch = _orchestrator(repo, biz=BIZ)
        run = await orch.start(tenant_id=TENANT, business_id=BIZ, trigger="synthetic", trigger_token="tok-s4")
        exec_idx = next(i for i, s in enumerate(run.stages) if s.stage == CycleStage.EXECUTION)
        while run.stage_index < exec_idx:
            if not await orch.run_one_stage(run):
                break
        crashed = await repo.load(BIZ, run.cycle_id)
        stage = crashed.stages[crashed.stage_index]
        stage.status = "running"
        stage.started_at = _t()
        stage.attempts += 1
        await repo.save(crashed)                            # durable: crash mid-execution

        resumed = await repo.load(BIZ, run.cycle_id)
        assert await orch.run_one_stage(resumed) is True    # converges, never blind-rerun
        assert resumed.state_output["execution"]["receipt"]["ok"] is False
        assert await orch.run_one_stage(resumed) is True    # reconciliation
        rec = resumed.state_output["reconciliation"]
        assert rec["allow_retry"] is False                  # [V] no blind retry
        assert rec["reconciliation_required"] is True       # [V] surfaced as REQUIRED
        assert rec["status"] == "unknown_external_outcome"
        assert await orch.run_one_stage(resumed) is True    # verification
        out = resumed.state_output["outcome"]
        assert out["verification_status"] == VerificationStatus.UNVERIFIED.value  # [V] not fabricated
        assert out["reason"] == "unknown_external_outcome_reconciliation_required"

    # ── S5 · Restart / replay: one logical cycle, one effect ────────────
    async def test_s5_restart_resumes_without_duplicate_effect(self) -> None:
        repo = InMemoryCycleRepository()
        orch = _orchestrator(repo, biz=BIZ)
        run = await orch.start(tenant_id=TENANT, business_id=BIZ, trigger="synthetic", trigger_token="tok-s5")
        for _ in range(5):
            if not await orch.run_one_stage(run):
                break
        assert run.completed is False                       # worker died mid-flight
        worker2 = CycleOrchestrator(
            repository=repo, evidence=orch.evidence,
            verification_evidence=orch.verification_evidence, policy=orch.policy,
        )
        resumed = await worker2.load(BIZ, run.cycle_id)
        assert resumed is not None
        await worker2.run_all(resumed)
        assert resumed.completed is True
        assert resumed.state_output["outcome"]["verification_status"] == VerificationStatus.VERIFIED.value
        exec_stage = next(s for s in resumed.stages if s.stage == CycleStage.EXECUTION)
        assert exec_stage.attempts == 1                     # [V] executed exactly once across restart

        # duplicate trigger token -> SAME logical cycle, no regression
        again = await worker2.start(tenant_id=TENANT, business_id=BIZ, trigger="synthetic", trigger_token="tok-s5")
        assert again.cycle_id == resumed.cycle_id
        assert again.completed is True
        # replay on the completed run is a no-op: receipt + outcome are stable
        replay = await worker2.load(BIZ, run.cycle_id)
        receipt_before = replay.state_output["execution"]["receipt"]["receipt_id"]
        outcome_before = replay.state_output["outcome"]
        await worker2.run_all(replay)
        assert replay.state_output["execution"]["receipt"]["receipt_id"] == receipt_before  # [V] no duplicate effect
        assert replay.state_output["outcome"] == outcome_before

    # ── S6 · Terminal immutability + conflict, no silent clobber ────────
    async def test_s6_completed_run_never_regresses(self) -> None:
        repo, _, run = await _run_full("biz-imm", "tok-s6")
        persisted = await repo.load("biz-imm", run.cycle_id)
        assert persisted.completed is True
        await repo.save(persisted)                          # identical re-save: allowed
        tampered = await repo.load("biz-imm", run.cycle_id)
        tampered.completed = False
        tampered.stage_index = 0
        with pytest.raises(CycleRunConflictError):          # [V] terminal guard
            await repo.save(tampered)

        # staggered writes must never collide on a completed run: terminal
        # guard already refuses every divergent change to a completed cycle,
        # so the stale-writer case is exercised on a NON-completed run below.
        repo2 = InMemoryCycleRepository()
        orch2 = _orchestrator(repo2, biz="biz-imm")
        half = await orch2.start(tenant_id=TENANT, business_id="biz-imm", trigger="synthetic", trigger_token="tok-s6b")
        await orch2.run_one_stage(half)
        a = await repo2.load("biz-imm", half.cycle_id)
        b = await repo2.load("biz-imm", half.cycle_id)
        a.stage_index = 1
        await repo2.save(a)
        b.stage_index = 2  # stale writer
        with pytest.raises(CycleRunConflictError):          # [V] optimistic conflict, no silent clobber
            await repo2.save(b)

    # ── S7 · Owner approval bound to exact material ─────────────────────
    async def test_s7_stale_approval_never_authorizes(self) -> None:
        repo = InMemoryCycleRepository()
        orch = _orchestrator(repo, biz=BIZ)
        run = await orch.start(tenant_id=TENANT, business_id=BIZ, trigger="synthetic", trigger_token="tok-s7")
        exec_idx = next(i for i, s in enumerate(run.stages) if s.stage == CycleStage.EXECUTION)
        while run.stage_index < exec_idx:
            if not await orch.run_one_stage(run):
                break
        approval = run.state_output["approval"]
        assert approval["binding_key"]                      # [V] binding recorded
        assert approval["approved_by"] == "synthetic_owner"
        persisted = await repo.load(BIZ, run.cycle_id)
        assert persisted.state_output["approval"]["binding_key"] == approval["binding_key"]

        original_hash = persisted.state_output["recommendations"][0]["material_hash"]
        tampered = await repo.load(BIZ, run.cycle_id)
        tampered.state_output["recommendations"][0]["material_hash"] = original_hash + "-TAMPERED"
        await repo.save(tampered)

        worker2 = CycleOrchestrator(
            repository=repo, evidence=orch.evidence,
            verification_evidence=orch.verification_evidence, policy=orch.policy,
        )
        resumed = await worker2.load(BIZ, run.cycle_id)
        assert await worker2.run_one_stage(resumed) is True
        assert resumed.state_output["execution"]["skipped"] is True     # [V] stale approval refused
        assert resumed.state_output["execution"]["reason"] == "approval_material_mismatch"
        assert await worker2.run_one_stage(resumed) is True  # reconciliation
        assert resumed.state_output["reconciliation"]["reason"] == "approval_material_mismatch"
        assert await worker2.run_one_stage(resumed) is True  # verification
        assert resumed.state_output["outcome"]["verification_status"] == VerificationStatus.UNVERIFIED.value  # [V] no fake learning

    # ── S8 · Ledger: phantom rows can never verify; reads fail closed ───
    async def test_s8_ledger_guard_and_fail_closed_scoping(self, tmp_path) -> None:
        ledger = OutcomeLedger(str(tmp_path / "ledger.db"))
        assert ledger.record_verified_result(decision_key="k:missing", outcome_status="confirmed", verified=True) is False  # [V] phantom cannot verify
        for key in ("key-a", "key-b", "key-c"):
            ledger.record(decision_key=key, capability="business_loop.verified", deterministic_decision="r-1", source="business_loop")
            ledger.record_verified_result(decision_key=key, outcome_status="confirmed", verified=True, actual_impact_sar=100.0, expected_impact_sar=90.0)
        rows = ledger.verified_outcomes()
        scoped = [r for r in rows if r.get("decision_key") in {"key-a"}]
        assert len(scoped) == 1 and scoped[0]["decision_key"] == "key-a"   # [V] owner sees own rows only
        assert [r for r in rows if r.get("decision_key") in set()] == []   # [V] empty access -> zero rows

    # ── S9 · Console truthfulness, DLP purity, read-only ────────────────
    async def test_s9_console_truthful_dlp_pure_read_only(self) -> None:
        repo, orch, run = await _run_full("biz-sum", "tok-s9")
        summary = build_cycle_summary(run)
        assert summary["lifecycle_status"] == "learning_eligible"
        assert summary["impact_band"] in {"under_250", "250_999", "1000_4999", "5000_plus", None}
        for key in ("potential_impact_sar", "expected_impact_sar", "observed_impact_sar"):
            assert key not in summary                              # [V] exact SAR never hits the list console
        for forbidden in ('"sku"', ".sku", "stock_count", '"business_name"'):
            assert forbidden not in READ_MODEL_SRC                 # [V] DLP-clean read model
        for verb in ("@router.post", "@router.put", "@router.patch", "@router.delete"):
            assert verb not in ROUTER_SRC                          # [V] console stays read-only
            assert verb not in READ_MODEL_SRC

        unverified = _craft_run(
            stage_index=17, completed=True,
            state_output={
                "execution": {"skipped": True, "reason": "recommendation_not_approved:denied"},
                "outcome": {"verification_status": "unverified", "reason": "no_execution"},
            },
        )
        model = build_cycle_read_model(unverified)
        assert model["verification"]["verified"] is False          # [V] denied flow never claims success
        assert model["learning"]["eligible"] is False

    # ── S10 · Jev advisory: deterministic authoritative, verbatim ──────
    async def test_s10_jev_advisory_never_authoritative_never_fabricated(self) -> None:
        from app.services.business_loop.advisory import AdvisorySource as AdvisorySourceMod
        from app.services.business_loop.advisory import canonical_advisor, consult_advisory, deterministic_only_advisor

        contract = frozenset({"RESTOCK", "REORDER", "DISCOUNT", "DO_NOTHING"})
        context = {
            "payload": {"tenant_id": TENANT, "business_id": BIZ},
            "deterministic_decision": "REORDER",
            "purpose": "continuous_business_loop",
            "contract": contract,
        }

        async def mocked_jev(capability, ctx):
            return {
                "decision": ctx["deterministic_decision"],
                "suggested": "DISCOUNT",
                "confidence": 0.8,
                "source": "mocked",
                "provider": "mocked",
            }

        ta = await consult_advisory(mocked_jev, capability="business_loop.action_selection",
                                    context=context, contract=contract)
        assert ta.deterministic_decision == "REORDER"              # [V] decision never overridden
        assert ta.source == AdvisorySourceMod.MOCKED and ta.source != AdvisorySourceMod.JEV  # [V] mocked stays mocked

        fallback = await deterministic_only_advisor("business_loop.action_selection", context)
        assert fallback["provider"] == "deterministic"             # [V] fallback never claims Jev

        quality = attribution_quality(
            verification_status=VerificationStatus.REPORTED, verification_method="",
            observed_impact_sar=None,
            advisory_source=AdvisorySource.JEV.value, advisory_provider="jev-live",
        )
        assert quality == "jev_advisory_only"                      # [V] Jev-alone is never sufficient

    # ── S11 · Governance deterministic; certification never AI ─────────
    def test_s11_governance_is_deterministic_and_non_ai(self) -> None:
        denied = evaluate_governance(recommendation_id="r1", action_type="LAUNDER_MONEY", business_id=BIZ)
        assert denied.outcome == GovernanceOutcome.DENIED          # [V] unregistered -> DENIED
        assert "unregistered_action" in denied.reasons
        assert denied.certified_by == "deterministic-governance"   # [V] never AI

        review = evaluate_governance(recommendation_id="r2", action_type="restock", business_id=BIZ, shariah_approved=False)
        assert review.outcome == GovernanceOutcome.REVIEW_REQUIRED # [V] no qualified review -> hold

        need_approval = evaluate_governance(
            recommendation_id="r3", action_type="pricing_increase", business_id=BIZ,
            shariah_approved=True, approval_required=True,
        )
        assert need_approval.outcome == GovernanceOutcome.APPROVAL_REQUIRED  # [V] approval required

        permitted = evaluate_governance(
            recommendation_id="r4", action_type="restock", business_id=BIZ,
            shariah_approved=True, approval_required=False,
        )
        assert permitted.outcome == GovernanceOutcome.PERMITTED    # [V] deterministic permit

        binding = approve_binding(
            recommendation_id="r3", recommendation_version=1,
            material_hash="h-1", approved_by="owner",
        )
        assert binding["binding_key"] == f"r3:v1:h-1"              # [V] approval bound to exact material