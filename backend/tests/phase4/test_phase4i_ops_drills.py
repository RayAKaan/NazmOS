"""Phase 4I-Q/R/S — pilot observability, kill-switch, durability drills (DB-free).

Honest pilot-operations checks that run WITHOUT infra touch:

  4I-Q · OBSERVABILITY
      A completed pilot cycle is fully observable through the owner-facing
      read model (``loop_console_readmodel``): lifecycle ladder, execution
      surrogate, advisory attribution, governance certification, simulated
      approval, and outcome verification are all surfaced with their REAL
      values. An unknown external outcome (crash mid-execution) is reported
      as unverified / reconciliation-required — never manufactured into
      ``verified``.

  4I-R · KILL SWITCH
      The in-loop EXECUTION stage is a DRY-RUN surrogate: its receipt is
      always ``synthetic=True`` so the loop itself never touches live money.
      Liveness is gated separately by the orchestration runner's strict
      dispatch honoring ``EXECUTION_ENABLED`` (proven in Drill D / the
      4I-FIX-2 suite). Both surfaces are asserted present and coherent.

  4I-S · DURABILITY / RESTORE PROCEDURE
      Evidence is the durable source of truth: (1) a persisted completed
      CycleRun round-trips every critical field, and (2) reconstituting state
      from the SAME evidence yields deterministic state version + watermark,
      so a restore converges to a consistent picture. The real backup/restore
      procedure (volume + Postgres dump) is a runbook deliverable, not a unit
      test — this file proves the evaluation side a restore depends on.

No db_session, no Postgres, no Temporal, no network.
"""
from datetime import datetime, timezone

import pytest

from app.services.business_loop.cycle import CycleStage, CycleOrchestrator, InMemoryCycleRepository
from app.services.business_loop.evidence import EvidenceStore
from app.services.business_loop.execution import ExecutionIntent, dry_run_execute
from app.services.business_loop.governance import GovernanceOutcome
from app.services.business_loop.recommendation import RecommendationStatus
from app.services.loop_console_readmodel import build_cycle_read_model, compute_lifecycle

from tests.phase4.test_phase4i_pilot_rehearsal import (
    BIZ,
    TENANT,
    _ingest,
    _measurement_authority,
    _mocked_jev,
    _orchestrator,
    _t,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ── 4I-Q · Observable pilot state ─────────────────────────────────────────
async def test_q1_completed_pilot_cycle_is_fully_observable() -> None:
    repo = InMemoryCycleRepository()
    orch = _orchestrator(repo, biz=BIZ)
    run = await orch.start(tenant_id=TENANT, business_id=BIZ, trigger="synthetic", trigger_token="tok-q1")
    run = await orch.run_all(run)
    run = await repo.load(BIZ, run.cycle_id)

    model = build_cycle_read_model(run)
    assert model["read_model_version"]
    assert model["cycle"]["completed"] is True                       # [V] status observable
    assert model["cycle"]["business_id"] == BIZ
    assert model["cycle"]["trigger"] == "synthetic"

    lc = compute_lifecycle(run)
    assert lc["lifecycle_status"] in ("verified", "executed", "learning_eligible", "blocked")
    assert not lc["flags"]["blocked"]                                # [V] run is healthy, not stuck

    assert model["execution"]["receipt_present"] is True
    assert model["execution"]["synthetic"] is True                   # [V] in-loop surrogate only
    assert model["governance"]["certified_by"] == "deterministic-governance"  # [V] never AI
    assert model["approval"]["mode"] == "simulated_owner_approval"   # [V] approval honestly labelled
    assert model["approval"]["simulated"] is True
    assert "SYNTHETIC" in (model["approval"]["note"] or "")          # [V] not a real owner decision
    # attribution is exact: the mocked advisory reports 'mocked', never Jev
    assert model["advisory"]["source"] == "mocked"
    assert model["advisory"]["provider"] == "jev-mock"


async def test_q2_unknown_external_outcome_is_observable_not_fabricated() -> None:
    repo = InMemoryCycleRepository()
    orch = _orchestrator(repo, biz=BIZ)
    run = await orch.start(tenant_id=TENANT, business_id=BIZ, trigger="synthetic", trigger_token="tok-q2")
    exec_idx = next(i for i, s in enumerate(run.stages) if s.stage == CycleStage.EXECUTION)
    while run.stage_index < exec_idx:
        if not await orch.run_one_stage(run):
            break
    assert run.stage_index == exec_idx                                # [V] reached execution

    crashed = await repo.load(BIZ, run.cycle_id)
    stage = crashed.stages[crashed.stage_index]
    stage.status = "running"                                          # simulated crash mid-execution
    stage.started_at = _now()
    stage.attempts += 1
    await repo.save(crashed)
    resumed = await repo.load(BIZ, run.cycle_id)

    # resume converges WITHOUT re-running: unconfirmed external outcome
    assert await orch.run_one_stage(resumed) is True
    exec_state = resumed.state_output["execution"]
    assert exec_state["resumed_crashed"] is True                     # [V] honest restart marker
    assert exec_state["receipt"]["ok"] is False                      # [V] never fake a success
    assert "unconfirmed_external_outcome_after_restart" in exec_state["receipt"]["details"]["reason"]

    await orch.run_all(resumed)
    final = await repo.load(BIZ, resumed.cycle_id)

    model = build_cycle_read_model(final)
    assert model["outcome"]["verification_status"] == "unverified"   # [V] never verified
    assert compute_lifecycle(final)["flags"]["verified"] is False     # [V] not surfaced as verified
    # reconciliation is REQUIRED so an operator action is the only way forward
    assert final.state_output.get("reconciliation", {}).get("reconciliation_required") is True


# ── 4I-R · Kill switch / execution surrogate ──────────────────────────────
def test_r1_in_loop_execution_is_always_a_dry_run_surrogate() -> None:
    intent = ExecutionIntent(
        business_id=BIZ,
        action_type="restock",
        entity_type="item",
        entity_id="item-q1",
        payload={"recommendation_id": "rec-q1"},
        recommendation_id="rec-q1",
    )
    receipt = dry_run_execute(intent, decision=GovernanceOutcome.PERMITTED, recommendation_status=RecommendationStatus.APPROVED)
    assert receipt.ok is True
    assert receipt.synthetic is True                                 # [V] surrogate, never live money


def test_r2_execution_kill_switch_flag_is_present_and_defaulted() -> None:
    from app.config import Settings

    # The liveness switch is an explicit configuration surface (env/override);
    # CI sets it for the deterministic gate; Drill D proves the runner honors it.
    assert hasattr(Settings(), "EXECUTION_ENABLED")
    assert Settings().EXECUTION_ENABLED is True                      # [V] default ON, but separate


# ── 4I-S · Durability / restore determinism ───────────────────────────────
async def test_s1_persisted_completed_run_round_trips_every_critical_field() -> None:
    repo = InMemoryCycleRepository()
    orch = _orchestrator(repo, biz=BIZ)
    run = await orch.start(tenant_id=TENANT, business_id=BIZ, trigger="synthetic", trigger_token="tok-s1")
    await orch.run_all(run)
    persisted = await repo.load(BIZ, run.cycle_id)
    assert persisted.cycle_id == run.cycle_id
    assert persisted.business_id == BIZ
    assert persisted.tenant_id == TENANT
    assert persisted.completed is True                               # [V] durable completion marker
    assert persisted.stage_index == len(persisted.stages) - 1         # last stage reached
    assert persisted.evidence_watermark == run.evidence_watermark     # [V] watermark intact
    assert persisted.state_output["recommendations"][0]["recommendation_id"]
    assert persisted.state_output["execution"]["execution_key"]
    assert persisted.state_output["outcome"]["outcome_id"]


async def test_s2_restore_converges_on_deterministic_state() -> None:
    from app.services.business_loop.cycle import CyclePolicy

    # Prove evidence reconstitution is deterministic: two independent fresh
    # starts from the SAME durable evidence yield IDENTICAL state version and
    # evidence watermark — the invariant a restore depends on.

    def build(repo, evidence, post):
        return CycleOrchestrator(
            repository=repo, evidence=evidence, verification_evidence=post,
            policy=CyclePolicy(
                shariah_approved=True,
                advisory_fn=_mocked_jev,
                verification_evaluator=_measurement_authority,
            ),
        )

    store_a, store_b = EvidenceStore(), EvidenceStore()
    for store in (store_a, store_b):
        _ingest(store, tenant_id=TENANT, business_id=BIZ, sku="SKU-4I", stock=120, cost=20, sell=28, days_of_supply=45)
        _ingest(store, tenant_id=TENANT, business_id=BIZ, sku="SKU-4I", stock=20, cost=20, sell=28, days_of_supply=5)

    post_a, post_b = EvidenceStore(), EvidenceStore()
    for store in (post_a, post_b):
        _ingest(store, tenant_id=TENANT, business_id=BIZ, sku="SKU-4I", stock=20, cost=20, sell=28, days_of_supply=5)

    orch_a = build(InMemoryCycleRepository(), store_a, post_a)
    orch_b = build(InMemoryCycleRepository(), store_b, post_b)

    run_a = await orch_a.start(tenant_id=TENANT, business_id=BIZ, trigger="synthetic", trigger_token="tok-a")
    run_b = await orch_b.start(tenant_id=TENANT, business_id=BIZ, trigger="synthetic", trigger_token="tok-b")
    assert run_b.cycle_id != run_a.cycle_id                          # independent cycles
    # [V] same evidence -> identical reconstitution (restore determinism)
    assert run_b.starting_state_version == run_a.starting_state_version
    assert run_b.evidence_watermark == run_a.evidence_watermark