"""Phase 4D — durable business improvement cycle over real Temporal (Postgres).

Proves the consumer-driven 21-stage loop is resumable across process restarts,
durably isolated per tenant, idempotent under a duplicate trigger, and never
blind-retries a stage whose outcome is unknown:

    * test_cycle_end_to_end_completes        real server + prod worker drives all
                                             21 stages; one durable cycle_runs row;
                                             the exact advisory attribution (mocked,
                                             never jev) survives the wire
    * test_duplicate_trigger_suppressed      same trigger/token -> same workflow id
                                             and same cycle_id; the unique key keeps
                                             ONE row (already-covered row is reused)
    * test_worker_restart_resumes_cursor     a run advanced to stage k before a
                                             (simulated) worker loss resumes from the
                                             persisted stage_index — stages 0..k-1 are
                                             NOT re-executed (attempts stay 1)
    * test_budget_exhausted_is_blocked       an unknown-outcome stage at its retry
                                             budget ends the workflow BLOCKED, never
                                             re-run past the budget
    * test_reconcile_requeues_within_budget  the reconcile activity re-queues an
                                             orphaned ``running`` stage only while
                                             attempts stay inside policy budget and
                                             never touches an already-ok stage

Scenario G (Phase 4F) appends the verified outcome path: the canonical
execution->outcome linkage lands in OutcomeLedger V1 exactly once per
execution (readback-confirmed), verbatim attribution is preserved, a duplicate
trigger leaves ONE ledger row, a run with no measurable outcome is captured but
never verified, and an execution with unknown approval results in NO verified
row and NO learning.

Evidence labels: [V] running code, [B] baseline regression, [X] limitation.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from app.config import get_settings
from app.orchestration.operations import WF_BUSINESS_CYCLE, operation_workflow_id
from app.orchestration.temporal.activities import ACTIVITIES
from app.services.business_loop.advisory import AdvisorySource
from app.services.business_loop.contracts import CycleStage
from app.services.business_loop.cycle import CycleOrchestrator, CycleStageState, derive_cycle_id
from app.services.business_loop.evidence import EvidenceStore, normalize_observation
from app.services.business_loop.outcome_linkage import derive_outcome_key
from app.services.business_loop.policy_registry import resolve_cycle_policy
from app.services.cycle_run_repository import PostgresCycleRepository
from app.services.outcome_ledger import OutcomeLedger

from tests.fixtures.merchants import seed_business

pytestmark = [
    pytest.mark.skipif(
        not (os.environ.get("DATABASE_URL") or "").startswith("postgresql"),
        reason="Postgres-backed Temporal integration: point DATABASE_URL at a real Postgres test database.",
    ),
    pytest.mark.asyncio(loop_scope="session"),
]

TENANT = "tnt-4d"


def _t() -> str:
    return (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(timespec="seconds")


def _observation(
    *, sku: str, stock: float, cost: float, sell: float, days_of_supply: float
) -> dict:
    return {
        "raw": {"sku": sku, "stock": stock, "cost": cost, "sell": sell, "days_of_supply": days_of_supply},
        "source_type": "synthetic.pos",
        "source_reference": sku,
        "observation_type": "inventory.observed",
        "event_timestamp": _t(),
        "observed_at": _t(),
        "required_fields": ["sku", "stock", "cost", "sell", "days_of_supply"],
    }


def _cycle_payload(*, business_id: str, token: str, observations: list[dict], verification_observations: list[dict]) -> dict:
    return {
        "tenant_id": TENANT,
        "business_id": business_id,
        "trigger": "synthetic",
        "trigger_token": token,
        "policy": "synthetic",
        "observations": observations,
        "verification_observations": verification_observations,
    }


def _excess_slice() -> tuple[list[dict], list[dict]]:
    """Pre-state triggers EXCESS_INVENTORY; post-state measurement shows recovery."""
    pre = [_observation(sku="SKU-4D", stock=120, cost=20, sell=28, days_of_supply=45)]
    post = [_observation(sku="SKU-4D", stock=20, cost=20, sell=28, days_of_supply=5)]
    return pre, post


async def _build_orchestrator(db, payload: dict):
    """The SAME construction the advance activity performs (payload-driven)."""
    evidence = EvidenceStore()
    for obs in payload.get("observations", []):
        rec, reason = normalize_observation(
            tenant_id=TENANT,
            business_id=payload["business_id"],
            raw=obs["raw"],
            source_type=obs.get("source_type", "synthetic.pos"),
            source_reference=obs.get("source_reference", ""),
            observation_type=obs.get("observation_type", "inventory.observed"),
            event_timestamp=obs.get("event_timestamp", ""),
            observed_at=obs.get("observed_at", ""),
            required_fields=tuple(obs.get("required_fields", ())),
        )
        assert rec is not None, reason
        evidence.put(rec)
    verif = EvidenceStore()
    for obs in payload.get("verification_observations", []):
        rec, reason = normalize_observation(
            tenant_id=TENANT,
            business_id=payload["business_id"],
            raw=obs["raw"],
            source_type=obs.get("source_type", "synthetic.pos"),
            source_reference=obs.get("source_reference", ""),
            observation_type=obs.get("observation_type", "inventory.observed"),
            event_timestamp=obs.get("event_timestamp", ""),
            observed_at=obs.get("observed_at", ""),
            required_fields=tuple(obs.get("required_fields", ())),
        )
        assert rec is not None, reason
        verif.put(rec)
    repo = PostgresCycleRepository(db)
    return CycleOrchestrator(
        repository=repo,
        evidence=evidence,
        verification_evidence=verif,
        policy=resolve_cycle_policy(str(payload.get("policy", "synthetic"))),
    )


async def _cycle_row_count(db, business_id: str) -> int:
    return (
        await db.execute(
            text("SELECT COUNT(*) FROM cycle_runs WHERE business_id=:b"), {"b": business_id}
        )
    ).scalar()


# ── Scenario A: real server + production worker completes the whole cycle ──


async def test_cycle_end_to_end_completes(temporal_server, db):
    bid = await seed_business(db, "4D E2E")
    await db.commit()
    pre, post = _excess_slice()
    payload = _cycle_payload(business_id=bid, token="tok-e2e", observations=pre, verification_observations=post)
    workflow_id = operation_workflow_id(WF_BUSINESS_CYCLE, payload)

    result = await temporal_server.execute_workflow(
        WF_BUSINESS_CYCLE, payload, id=workflow_id, task_queue=get_settings().TEMPORAL_TASK_QUEUE
    )

    assert result["done"] is True
    assert result["blocked"] is False
    assert result["completed"] is True
    assert result["stage_index"] >= 20
    assert await _cycle_row_count(db, bid) == 1

    repo = PostgresCycleRepository(db)
    persisted = await repo.load(bid, workflow_id)
    assert persisted is not None and persisted.completed is True
    assert len(persisted.stages) == 21
    assert all(s.status in ("ok", "skipped") for s in persisted.stages[:20])
    assert persisted.stages[20].stage == CycleStage.NEXT_CYCLE

    out = persisted.state_output
    assert out.get("learning_eligible") is True
    # The advisory attribution survives the wire EXACTLY (mocked, never jev).
    assert out["advisory"]["source"] == AdvisorySource.MOCKED.value
    assert out["advisory"]["provider"] == "jev-mock"
    assert out["advisory"]["validation_passed"] is True
    # Executed locally only ever as a synthetic dry-run.
    assert out["execution"]["receipt"]["ok"] is True
    assert out["execution"]["receipt"]["synthetic"] is True


# ── Scenario B: duplicate trigger -> same workflow id -> ONE durable row ──


async def test_duplicate_trigger_suppressed(temporal_server, db):
    bid = await seed_business(db, "4D Duplicate")
    await db.commit()
    pre, post = _excess_slice()
    payload = _cycle_payload(business_id=bid, token="tok-dup", observations=pre, verification_observations=post)
    workflow_id = operation_workflow_id(WF_BUSINESS_CYCLE, payload)

    first = await temporal_server.execute_workflow(
        WF_BUSINESS_CYCLE, payload, id=workflow_id, task_queue=get_settings().TEMPORAL_TASK_QUEUE
    )
    second = await temporal_server.execute_workflow(
        WF_BUSINESS_CYCLE, payload, id=workflow_id, task_queue=get_settings().TEMPORAL_TASK_QUEUE
    )

    assert first["cycle_id"] == second["cycle_id"] == workflow_id
    assert first["completed"] is True
    assert second["completed"] is True  # re-dispatched run re-used the row
    assert await _cycle_row_count(db, bid) == 1  # idempotent, one row only


# ── Scenario C: worker restart resumes from the persisted stage cursor ──


async def test_worker_restart_resumes_cursor(temporal_server, db):
    bid = await seed_business(db, "4D Resume")
    await db.commit()
    pre, post = _excess_slice()
    payload = _cycle_payload(business_id=bid, token="tok-resume", observations=pre, verification_observations=post)

    # Simulate the pre-restart worker: create the run and advance it exactly to
    # stage k (persisted after every step) before "losing" the process.
    orch = await _build_orchestrator(db, payload)
    run = await orch.start(tenant_id=TENANT, business_id=bid, trigger="synthetic", trigger_token="tok-resume")
    k = 4  # persisted through STATE_PROJECTION (index 3 -> cursor 4)
    for _ in range(k):
        assert await orch.run_one_stage(run) is True
    await db.commit()

    persisted_before = await PostgresCycleRepository(db).load(bid, run.cycle_id)
    assert persisted_before.stage_index == k
    assert all(s.status == "ok" and s.attempts == 1 for s in persisted_before.stages[:k])

    workflow_id = operation_workflow_id(WF_BUSINESS_CYCLE, payload)
    result = await temporal_server.execute_workflow(
        WF_BUSINESS_CYCLE, payload, id=workflow_id, task_queue=get_settings().TEMPORAL_TASK_QUEUE
    )

    assert result["completed"] is True
    assert result["stage_index"] >= 20
    assert await _cycle_row_count(db, bid) == 1

    persisted = await PostgresCycleRepository(db).load(bid, workflow_id)
    assert persisted is not None
    # Stages 0..k-1 were NOT re-executed after resume (attempts stay 1).
    assert all(s.status == "ok" and s.attempts == 1 for s in persisted.stages[:k])
    # The resumed run re-uses the exact same cycle row.
    assert persisted.cycle_id == workflow_id


# ── Scenario D: budget-exhausted stage ends the workflow BLOCKED, no blind retry ──


async def test_budget_exhausted_is_blocked(temporal_server, db):
    bid = await seed_business(db, "4D Budget")
    await db.commit()
    pre, post = _excess_slice()
    payload = _cycle_payload(business_id=bid, token="tok-budget", observations=pre, verification_observations=post)

    # Start + advance one stage normally, then script an unbeknownst failure
    # with attempts pinned AT the policy budget (unknown external outcome).
    orch = await _build_orchestrator(db, payload)
    run = await orch.start(tenant_id=TENANT, business_id=bid, trigger="synthetic", trigger_token="tok-budget")
    await orch.run_one_stage(run)
    await db.commit()

    repo = PostgresCycleRepository(db)
    run = await repo.load(bid, run.cycle_id)
    budget = resolve_cycle_policy("synthetic").max_retries_per_stage
    stage = run.stages[run.stage_index]
    stage.status = "failed"
    stage.attempts = budget  # at the retry cap: anything further is a blind retry
    stage.error = "unknown_external_outcome"
    run.last_error = stage.error
    await repo.save(run)

    workflow_id = operation_workflow_id(WF_BUSINESS_CYCLE, payload)
    result = await temporal_server.execute_workflow(
        WF_BUSINESS_CYCLE, payload, id=workflow_id, task_queue=get_settings().TEMPORAL_TASK_QUEUE
    )

    assert result["blocked"] is True
    assert result["completed"] is False
    persisted = await repo.load(bid, workflow_id)
    assert persisted.completed is False
    # The stage is NOT re-run past its budget (no blind retry).
    assert persisted.stages[persisted.stage_index].attempts == budget
    assert persisted.last_error == "unknown_external_outcome"


# ── Scenario E: reconcile activity re-queues only within budget, never ok stages ──


async def test_reconcile_requeues_orphaned_stage_within_budget(temporal_server, db):
    bid = await seed_business(db, "4D Reconcile")
    await db.commit()
    pre, post = _excess_slice()
    payload = _cycle_payload(business_id=bid, token="tok-rec", observations=pre, verification_observations=post)

    orch = await _build_orchestrator(db, payload)
    run = await orch.start(tenant_id=TENANT, business_id=bid, trigger="synthetic", trigger_token="tok-rec")
    await orch.run_one_stage(run)  # stage 0 ok, cursor at 1
    await db.commit()

    p = dict(payload)
    p["cycle_id"] = run.cycle_id

    repo = PostgresCycleRepository(db)
    run = await repo.load(bid, run.cycle_id)
    budget = resolve_cycle_policy("synthetic").max_retries_per_stage
    # Orphaned "running" stage within budget: outcome unknown, worker lost mid-write.
    stage = run.stages[run.stage_index]
    stage.status = "running"
    stage.attempts = max(1, budget - 1)
    await repo.save(run)

    reconciled = await ACTIVITIES["business_cycle_reconcile"](p)

    assert reconciled["allow_retry"] is True  # re-queued within budget
    assert reconciled["reconciliation"] == "reconcile_requeued"
    run = await repo.load(bid, run.cycle_id)
    assert run.stages[run.stage_index].status == "pending"


async def test_reconcile_never_allows_retry_past_budget_or_ok_stage(temporal_server, db):
    bid = await seed_business(db, "4D Reconcile2")
    await db.commit()
    pre, post = _excess_slice()
    payload = _cycle_payload(business_id=bid, token="tok-rec2", observations=pre, verification_observations=post)

    orch = await _build_orchestrator(db, payload)
    run = await orch.start(tenant_id=TENANT, business_id=bid, trigger="synthetic", trigger_token="tok-rec2")
    await orch.run_one_stage(run)
    await db.commit()

    p = dict(payload)
    p["cycle_id"] = run.cycle_id

    repo = PostgresCycleRepository(db)
    run = await repo.load(bid, run.cycle_id)
    budget = resolve_cycle_policy("synthetic").max_retries_per_stage
    stage = run.stages[run.stage_index]
    stage.status = "running"
    stage.attempts = budget  # at the cap: retry would exceed budget
    await repo.save(run)

    reconciled = await ACTIVITIES["business_cycle_reconcile"](p)
    assert reconciled["allow_retry"] is False
    assert reconciled["reconciliation"] == "budget_exhausted"
    run = await repo.load(bid, run.cycle_id)
    assert run.stages[run.stage_index].status == "failed"
    assert run.stages[run.stage_index].error == "unknown_external_outcome_incomplete"

    # An already-ok stage is NEVER re-queued by reconcile.
    run = await repo.load(bid, run.cycle_id)
    for s in run.stages:
        if s.status == "ok":
            assert s.attempts == 1


# ── Scenario H (Phase 4I): reconcile NEVER blind-re-runs an orphaned
#    EXECUTION stage. A worker lost mid-EXECUTION leaves the stage ``running``:
#    the durable hammer is an unconfirmed receipt = UNKNOWN external outcome.
#    Re-queueing it to ``pending`` (the pre-4I behavior) lets run_one_stage
#    re-invoke the EXECUTION handler because its convergence guard only fires
#    on a persisted ``running`` status. The 4I fix converges the stage exactly
#    like that guard instead (ok + unconfirmed receipt), allows the workflow to
#    advance INTO RECONCILIATION so reconciliation_required is written durably,
#    and NEVER consumes another EXECUTION attempt. ──


async def test_reconcile_never_blind_reruns_running_execution(temporal_server, db):
    bid = await seed_business(db, "4I ReconcileExec")
    await db.commit()
    pre, post = _excess_slice()
    payload = _cycle_payload(business_id=bid, token="tok-4i-exec", observations=pre, verification_observations=post)

    # Drive the run up TO (but not through) the EXECUTION stage, exactly like
    # the advance activity would in production: start + one stage at a time.
    orch = await _build_orchestrator(db, payload)
    run = await orch.start(tenant_id=TENANT, business_id=bid, trigger="synthetic", trigger_token="tok-4i-exec")
    while run.stages[run.stage_index].stage != CycleStage.EXECUTION:
        assert await orch.run_one_stage(run) is True
    await db.commit()
    assert run.stages[run.stage_index].stage == CycleStage.EXECUTION

    p = dict(payload)
    p["cycle_id"] = run.cycle_id

    repo = PostgresCycleRepository(db)
    run = await repo.load(bid, run.cycle_id)
    budget = resolve_cycle_policy("synthetic").max_retries_per_stage
    # Simulate the worker dying mid-EXECUTION: stage persisted as ``running``,
    # well within budget (the exactly-the-dangerous case for a blind re-run).
    stage = run.stages[run.stage_index]
    assert stage.stage == CycleStage.EXECUTION
    stage.status = "running"
    stage.attempts = max(1, budget - 1)
    await repo.save(run)

    reconciled = await ACTIVITIES["business_cycle_reconcile"](p)

    # Converged, never re-queued: the EXECUTION stage is marked ok (NOT pending)
    # and the workflow is allowed to advance so RECONCILIATION writes the
    # durable reconciliation_required record.
    assert reconciled["allow_retry"] is True
    assert reconciled["reconciliation"] == "execution_unconfirmed"
    assert reconciled["reconcile_guard"] == "execution_converged_unconfirmed"
    run = await repo.load(bid, run.cycle_id)
    exec_stage = run.stages[run.stage_index]
    assert exec_stage.stage == CycleStage.EXECUTION
    assert exec_stage.status == "ok"
    assert exec_stage.attempts == max(1, budget - 1)  # no attempt consumed
    execution = run.state_output.get("execution", {})
    assert execution.get("resumed_crashed") is True
    assert execution.get("receipt", {}).get("ok") is False
    assert "unconfirmed" in execution["receipt"]["details"]["reason"]

    # A subsequent advance does NOT re-invoke EXECUTION: the cursor moves past
    # the converged stage onto RECONCILIATION, and the following advance runs
    # that stage's compute, which writes the durable allow_retry=False /
    # reconciliation_required record. EXECUTION's attempt count stays whatever
    # the crashed worker left it at.
    step = await _advance_via_activity(p)
    assert step["blocked"] is False
    assert step["advanced"] is True
    run = await repo.load(bid, run.cycle_id)
    assert run.stages[run.stage_index].stage == CycleStage.RECONCILIATION
    step2 = await _advance_via_activity(p)
    assert step2["blocked"] is False
    run = await repo.load(bid, run.cycle_id)
    conc = run.state_output.get("reconciliation", {})
    assert conc.get("allow_retry") is False
    assert conc.get("reconciliation_required") is True
    exec_stage = next(s for s in run.stages if s.stage == CycleStage.EXECUTION)
    assert exec_stage.attempts == max(1, budget - 1)  # never re-run


# ── Scenario F (Phase 4E): a drifted resume cannot reproduce the persisted
#    baseline, so the advance activity BLOCKS — no stage attempt consumed,
#    verdict recorded durably. A same-evidence resume keeps passing. ──


async def _advance_via_activity(payload: dict) -> dict:
    return await ACTIVITIES["business_cycle_advance"](payload)


async def test_revalidation_blocks_drifted_resume(temporal_server, db):
    bid = await seed_business(db, "4E Revalidate")
    await db.commit()
    pre, post = _excess_slice()
    payload = _cycle_payload(business_id=bid, token="tok-revalidate", observations=pre, verification_observations=post)

    # Pin the baseline exactly as a real run would: start + advance through
    # STATE_PROJECTION (index 3 -> cursor 4) with evidence A, all persisted.
    orch = await _build_orchestrator(db, payload)
    run = await orch.start(tenant_id=TENANT, business_id=bid, trigger="synthetic", trigger_token="tok-revalidate")
    for _ in range(4):
        assert await orch.run_one_stage(run) is True
    await db.commit()
    assert run.starting_state_version
    assert run.evidence_watermark

    # Drifted resume: same cycle_id, but the projected evidence has changed
    # (stock 120 -> 80). The persisted baseline can no longer be reproduced.
    drifted = _cycle_payload(
        business_id=bid,
        token="tok-revalidate",
        observations=[_observation(sku="SKU-4D", stock=80, cost=20, sell=28, days_of_supply=20)],
        verification_observations=post,
    )
    drifted.update({"cycle_id": run.cycle_id})
    result = await _advance_via_activity(drifted)

    assert result.get("found") is not False
    assert result["blocked"] is True
    assert result["advanced"] is False
    assert result["done"] is False
    revalidation = result["revalidation"]
    assert revalidation["ok"] is False
    assert "state_version_drift" in revalidation["status"]
    assert revalidation["recomputed_state_version"] != revalidation["persisted_state_version"]

    # No stage attempt was consumed by the blocked advance (drift is a hard
    # block, never a blind retry): cursor stays at 4.
    repo = PostgresCycleRepository(db)
    persisted = await repo.load(bid, run.cycle_id)
    assert persisted.stage_index == 4
    assert persisted.last_error.startswith("revalidation_blocked:")
    assert persisted.state_output["revalidation"]["ok"] is False
    assert all(s.status == "ok" and s.attempts == 1 for s in persisted.stages[:4])

    # A resume with the SAME evidence the baseline pinned keeps revalidating OK.
    same = _cycle_payload(business_id=bid, token="tok-revalidate", observations=pre, verification_observations=post)
    same.update({"cycle_id": run.cycle_id})
    next_result = await _advance_via_activity(same)
    assert next_result["blocked"] is False
    assert next_result["advanced"] is True
    assert next_result["done"] is False


# ── Scenario G (Phase 4F): the verified outcome lands in OutcomeLedger V1 ──
#
# The advance activity persists the canonical execution->outcome linkage and,
# when a real execution produced a result, attaches it to the EXISTING V1
# ledger — idempotent by (tenant, execution_key, recommendation) and confirmed
# by readback, never by a bare best-effort True.


@pytest.fixture()
def outcome_ledger_path(tmp_path) -> str:
    """Point the settings singleton at a fresh ledger file for one test."""
    cfg = get_settings()
    orig = cfg.AI_OUTCOME_LEDGER_PATH
    path = str(tmp_path / f"ledger-{uuid.uuid4().hex[:8]}.sqlite")
    cfg.AI_OUTCOME_LEDGER_PATH = path
    yield path
    cfg.AI_OUTCOME_LEDGER_PATH = orig


def _linkage(out: dict) -> dict:
    linkage = out.get("outcome_linkage") or {}
    assert linkage, "outcome_linkage must be present in the persisted run state"
    return linkage


async def test_cycle_end_to_end_attaches_verified_linkage(temporal_server, db, outcome_ledger_path):
    bid = await seed_business(db, "4F Ledger E2E")
    await db.commit()
    pre, post = _excess_slice()
    payload = _cycle_payload(business_id=bid, token="tok-4f-e2e", observations=pre, verification_observations=post)
    workflow_id = operation_workflow_id(WF_BUSINESS_CYCLE, payload)

    result = await temporal_server.execute_workflow(
        WF_BUSINESS_CYCLE, payload, id=workflow_id, task_queue=get_settings().TEMPORAL_TASK_QUEUE
    )

    assert result["completed"] is True
    repo = PostgresCycleRepository(db)
    persisted = await repo.load(bid, workflow_id)
    out = persisted.state_output

    # canonical linkage + capture landed with the run
    linkage = _linkage(out)
    assert linkage["verification_status"] == "verified"
    assert linkage["attribution_quality"] == "deterministic_measurement"
    # attribution is verbatim (mocked advisory, never jev), surviving the wire
    assert linkage["attribution_source"] == AdvisorySource.MOCKED.value
    assert linkage["attribution_provider"] == "jev-mock"
    assert out["learning_eligible"] is True

    # the row itself is readback-confirmed, verified=1, capability exact
    attach = out["outcome_attachment"]
    assert attach["recorded"] is True
    assert attach["row_present"] is True
    assert attach["row_verified"] is True
    assert attach["outcome_status"] == "confirmed"
    assert attach["capability"] == "business_loop.verified"
    assert attach["ledger"] == "outcome_ledger_v1"

    ledger = OutcomeLedger(outcome_ledger_path)
    row = ledger.row(attach["outcome_key"])
    assert row is not None
    assert row["verified"] == 1
    assert row["capability"] == "business_loop.verified"
    assert row["capsule_hash"] == linkage["execution_key"]
    assert row["provider"] == "jev-mock"
    assert row["source"] == AdvisorySource.MOCKED.value
    assert row["deterministic_decision"] == linkage["recommendation_id"]
    assert ledger.summary()["total_captured"] == 1
    assert ledger.summary()["verified"] == 1


async def test_duplicate_trigger_leaves_one_ledger_row(temporal_server, db, outcome_ledger_path):
    bid = await seed_business(db, "4F Ledger Dup")
    await db.commit()
    pre, post = _excess_slice()
    payload = _cycle_payload(business_id=bid, token="tok-4f-dup", observations=pre, verification_observations=post)
    workflow_id = operation_workflow_id(WF_BUSINESS_CYCLE, payload)

    for _ in range(2):
        result = await temporal_server.execute_workflow(
            WF_BUSINESS_CYCLE, payload, id=workflow_id, task_queue=get_settings().TEMPORAL_TASK_QUEUE
        )
        assert result["completed"] is True

    repo = PostgresCycleRepository(db)
    persisted = await repo.load(bid, workflow_id)
    attach = persisted.state_output["outcome_attachment"]

    # idempotent: the replayed execution coalesces onto the SAME ledger row
    ledger = OutcomeLedger(outcome_ledger_path)
    row = ledger.row(attach["outcome_key"])
    assert row is not None and row["verified"] == 1
    assert ledger.summary()["total_captured"] == 1
    assert ledger.summary()["verified"] == 1
    # persisted marker kept the replay from double-attaching
    assert persisted.state_output["outcome_recorded"]["outcome_key"] == attach["outcome_key"]


async def test_no_measurable_outcome_is_captured_but_never_verified(temporal_server, db, outcome_ledger_path):
    bid = await seed_business(db, "4F No Measure")
    await db.commit()
    pre, _ = _excess_slice()
    payload = _cycle_payload(business_id=bid, token="tok-4f-nom", observations=pre, verification_observations=[])
    workflow_id = operation_workflow_id(WF_BUSINESS_CYCLE, payload)

    result = await temporal_server.execute_workflow(
        WF_BUSINESS_CYCLE, payload, id=workflow_id, task_queue=get_settings().TEMPORAL_TASK_QUEUE
    )
    assert result["completed"] is True

    repo = PostgresCycleRepository(db)
    persisted = await repo.load(bid, workflow_id)
    out = persisted.state_output
    # no measurement -> REPORTED (execution ran, awaiting measurement) — but
    # never VERIFIED, never eligible for learning
    assert out["outcome"]["verification_status"] == "reported"
    assert out["learning_eligible"] is False
    linkage = _linkage(out)
    assert linkage["verification_status"] == "reported"

    # the run still executed (dry-run) so the reported state is captured,
    # but NO verified row may ever reach the learning-facing read
    ledger = OutcomeLedger(outcome_ledger_path)
    assert ledger.verified_outcomes() == []
    attach = out.get("outcome_attachment") or {}
    assert attach.get("row_present") is True
    assert attach.get("row_verified") is False
    assert attach.get("outcome_status") == "unknown"


async def test_unknown_execution_never_verified_no_ledger_row_no_learning(temporal_server, db, outcome_ledger_path):
    bid = await seed_business(db, "4F Unknown Exec")
    await db.commit()
    pre, post = _excess_slice()
    payload = _cycle_payload(business_id=bid, token="tok-4f-unknown", observations=pre, verification_observations=post)
    workflow_id = operation_workflow_id(WF_BUSINESS_CYCLE, payload)

    # Advance a real run to JUST before EXECUTION (index 14), then flip the
    # recommendation to pending: the resumed execution has NO approval -> unknown
    # execution outcome, which must never attach, verify, or feed learning.
    orch = await _build_orchestrator(db, payload)
    run = await orch.start(tenant_id=TENANT, business_id=bid, trigger="synthetic", trigger_token="tok-4f-unknown")
    for _ in range(14):
        assert await orch.run_one_stage(run) is True
    repo = PostgresCycleRepository(db)
    run = await repo.load(bid, run.cycle_id)
    run.state_output["recommendations"][0]["status"] = "pending"
    await repo.save(run)
    await db.commit()

    result = await temporal_server.execute_workflow(
        WF_BUSINESS_CYCLE, payload, id=workflow_id, task_queue=get_settings().TEMPORAL_TASK_QUEUE
    )
    assert result["completed"] is True

    persisted = await repo.load(bid, workflow_id)
    out = persisted.state_output
    assert out["execution"]["skipped"] is True
    assert out["outcome"]["verification_status"] == "unverified"
    assert out["learning_eligible"] is False
    # no realized execution -> no capture attempted at all
    assert "outcome_attachment" not in out
    assert "outcome_recorded" not in out
    ledger = OutcomeLedger(outcome_ledger_path)
    assert ledger.summary()["total_captured"] == 0
    assert ledger.verified_outcomes() == []