"""Real Temporal activities for NazmOS execution.

Each ``@activity.defn`` is a thin transport boundary: it opens its own
tenant-scoped database session, calls the SAME canonical NazmOS business
functions the local deterministic composition uses (apply.py / record.py /
precheck.py — the bodies never move into Temporal), commits, and returns a
JSON-safe outcome.

Business semantics stay in NazmOS. Temporal owns only durable scheduling,
retries, and replay — the activity bodies here merely adapt the transport
(JSON payloads in, JSON-safe outcomes out) to the existing services.
"""
from __future__ import annotations

import asyncio
import uuid
from contextlib import asynccontextmanager
from typing import Any, Callable

from temporalio import activity

from app.database.connection import async_session_scope, sync_rls_tenant_context


def _uuid(value: Any) -> uuid.UUID:
    if isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(str(value))


@asynccontextmanager
async def _db_scope(business_id: str | None = None):
    """Tenant-scoped DB session context for an activity invocation.

    Wraps ``async_session_scope`` (auto-commit on success, auto-rollback on
    failure) with the Postgres RLS tenant context. ``None`` runs without a
    tenant scope (decision-level work that needs none).
    """
    if business_id:
        with sync_rls_tenant_context(str(business_id)):
            async with async_session_scope() as db:
                yield db
    else:
        async with async_session_scope() as db:
            yield db


# ── Manual path (manual_action) ───────────────────────────────────────


@activity.defn(name="revalidate_capability")
async def act_revalidate_capability(payload: dict) -> dict:
    """Re-check the actor still holds can_approve_actions."""
    business_id = _uuid(payload["business_id"])
    user_id = _uuid(payload["user_id"])
    async with _db_scope(str(business_id)) as db:
        from app.orchestration.precheck import revalidate_capability

        ok = await revalidate_capability(db, user_id, business_id)
    return {"ok": bool(ok)}


@activity.defn(name="validate_action_constraints")
async def act_validate_action_constraints(payload: dict) -> dict:
    """Run the owner-constraint / state guard (verdict only, no side effects)."""
    business_id = _uuid(payload["business_id"])
    entity_id = _uuid(payload["entity_id"])
    action_type = payload["action_type"]
    guarded_payload = {**payload.get("payload", {}), "item_id": str(entity_id)}
    async with _db_scope(str(business_id)) as db:
        from app.orchestration.precheck import validate_action_constraints

        verdict = await validate_action_constraints(
            db,
            business_id=business_id,
            action_type=action_type,
            payload=guarded_payload,
            previous_state=payload.get("previous_state") or {},
            new_state=payload.get("new_state") or {},
            actor_business_id=business_id,
        )
    return {
        "blocked": bool(getattr(verdict, "blocked", False)),
        "reason_code": getattr(verdict, "reason_code", None),
        "reason": getattr(verdict, "reason", None),
    }


@activity.defn(name="record_constraint_block")
async def act_record_constraint_block(payload: dict) -> dict:
    """Durably record a blocked execution attempt (best-effort, never raises)."""
    business_id = _uuid(payload["business_id"])
    attempted_by = (
        _uuid(payload["attempted_by"]) if payload.get("attempted_by") else None
    )
    async with _db_scope(str(business_id)) as db:
        from app.orchestration.precheck import record_constraint_block

        await record_constraint_block(
            db,
            business_id=business_id,
            action_type=payload.get("action_type", ""),
            reason_code=payload.get("reason_code", ""),
            reason=payload.get("reason", ""),
            attempted_by=attempted_by,
            payload=payload.get("new_state") or payload.get("payload"),
        )
    return {"ok": True}


@activity.defn(name="check_execution_idempotency")
async def act_check_execution_idempotency(payload: dict) -> dict:
    """Durable idempotency probe: does this execution_key already terminate?"""
    business_id = payload.get("business_id")
    async with _db_scope(str(business_id) if business_id else None) as db:
        from app.orchestration.record import check_execution_idempotency

        existing = await check_execution_idempotency(
            db,
            payload.get("execution_key", ""),
            table=payload.get("table", "executed_actions"),
        )
    if existing:
        return {"existing": True, "replayed": True, "id": existing["id"], "status": existing["status"]}
    return {"existing": False}


@activity.defn(name="apply_restock")
async def act_apply_restock(payload: dict) -> dict:
    business_id = _uuid(payload["business_id"])
    item_id = _uuid(payload["item_id"])
    async with _db_scope(str(business_id)) as db:
        from app.orchestration.apply import apply_restock

        return await apply_restock(db, business_id, item_id, payload.get("new_state") or {})


@activity.defn(name="apply_price_change")
async def act_apply_price_change(payload: dict) -> dict:
    business_id = _uuid(payload["business_id"])
    item_id = _uuid(payload["item_id"])
    async with _db_scope(str(business_id)) as db:
        from app.orchestration.apply import apply_price_change

        return await apply_price_change(db, business_id, item_id, payload.get("new_state") or {})


@activity.defn(name="apply_discount")
async def act_apply_discount(payload: dict) -> dict:
    business_id = _uuid(payload["business_id"])
    item_id = _uuid(payload["item_id"])
    async with _db_scope(str(business_id)) as db:
        from app.orchestration.apply import apply_discount

        return await apply_discount(db, business_id, item_id, payload.get("new_state") or {})


@activity.defn(name="apply_alert_dismiss")
async def act_apply_alert_dismiss(payload: dict) -> dict:
    decision_id = _uuid(payload["decision_id"])
    async with _db_scope(None) as db:
        from app.orchestration.apply import apply_alert_dismiss

        return await apply_alert_dismiss(db, decision_id)


@activity.defn(name="record_manual_action")
async def act_record_manual_action(payload: dict) -> dict:
    """Persist the manual-action outcome with its execution_key."""
    business_id = _uuid(payload["business_id"])
    entity_id = _uuid(payload["entity_id"])
    decision_id = _uuid(payload["decision_id"]) if payload.get("decision_id") else None
    user_id = _uuid(payload["user_id"]) if payload.get("user_id") else None
    async with _db_scope(str(business_id)) as db:
        from app.orchestration.record import record_manual_action

        action_id = await record_manual_action(
            db,
            business_id=business_id,
            action_type=payload["action_type"],
            entity_type=payload.get("entity_type", ""),
            entity_id=entity_id,
            previous_state=payload.get("previous_state") or {},
            new_state=payload.get("new_state") or {},
            source=payload.get("source", "manual"),
            execution_key=payload.get("execution_key", ""),
            decision_id=decision_id,
            user_id=user_id,
            outcome=payload.get("outcome"),
        )
    return {"action_id": str(action_id)}


# ── Agent path (agent_approval) ───────────────────────────────────────


@activity.defn(name="record_agent_approval")
async def act_record_agent_approval(payload: dict) -> dict:
    """pending_approval -> approved (single-transition guard), returns row data."""
    business_id = payload.get("business_id")
    async with _db_scope(str(business_id) if business_id else None) as db:
        from app.orchestration.record import record_agent_approval

        return await record_agent_approval(
            db,
            action_id=payload["action_id"],
            note=payload.get("note") or "Approved",
            decided_by=payload.get("decided_by"),
            business_id=business_id,
        )


@activity.defn(name="agent_mark_executing")
async def act_agent_mark_executing(payload: dict) -> dict:
    """approved -> executing, guarded (stale/raced approvals never proceed)."""
    business_id = payload.get("business_id")
    async with _db_scope(str(business_id) if business_id else None) as db:
        from sqlalchemy import text

        from app.utils.clock import utcnow

        res = await db.execute(
            text(
                "UPDATE agent_actions SET status='executing', updated_at=:now "
                "WHERE id=:id AND status='approved'"
            ),
            {"id": str(_uuid(payload["action_id"])), "now": utcnow()},
        )
    if res.rowcount != 1:
        return {
            "ok": False,
            "reason": f"Action {payload['action_id']} is not in the approved state",
        }
    return {"ok": True}


@activity.defn(name="apply_agent_action")
async def act_apply_agent_action(payload: dict) -> dict:
    """Apply the agent mutation (owns its own guard + mutation transaction)."""
    business_id = _uuid(payload["business_id"])
    async with _db_scope(str(business_id)) as db:
        from app.orchestration.apply import apply_agent_action

        return await apply_agent_action(
            db,
            business_id,
            payload["action_id"],
            payload["action_type"],
            payload.get("payload") or {},
        )


@activity.defn(name="record_agent_terminal")
async def act_record_agent_terminal(payload: dict) -> dict:
    """Record the terminal agent-action status after apply."""
    async with _db_scope(str(payload["business_id"]) if payload.get("business_id") else None) as db:
        from app.orchestration.record import record_agent_terminal

        await record_agent_terminal(
            db, action_id=_uuid(payload["action_id"]), outcome=payload.get("outcome") or {}
        )
    return {"ok": True}


@activity.defn(name="record_terminal_outcome")
async def act_record_terminal_outcome(payload: dict) -> dict:
    """Best-effort learning/KG distillation — must never fail the workflow."""
    try:
        async with _db_scope(str(payload["business_id"]) if payload.get("business_id") else None) as db:
            from app.orchestration.record import record_terminal_outcome

            await record_terminal_outcome(db, payload["business_id"], payload["action_id"])
    except Exception:  # noqa: BLE001 - intentionally best-effort
        return {"ok": False}
    return {"ok": True}


# ── Simulated path (simulated) ────────────────────────────────────────


@activity.defn(name="apply_simulated_execution")
async def act_apply_simulated_execution(payload: dict) -> dict:
    """Simulated execution — records an ExecutionJob, never mutates business data."""
    business_id = _uuid(payload["business_id"])
    async with _db_scope(str(business_id)) as db:
        from app.orchestration.apply import apply_simulated_execution

        return await apply_simulated_execution(
            db,
            business_id,
            payload["action_type"],
            payload.get("entity_type", ""),
            _uuid(payload["entity_id"]),
            payload.get("payload") or {},
        )


# ── Phase 2A — background / scheduled operations ─────────────────────


def _jsonable(value):
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


@activity.defn(name="process_upload_ingestion")
async def act_process_upload_ingestion(payload: dict) -> dict:
    """Run the canonical NazmOS ETL ingestion body in a worker thread.

    The sync body opens its own RLS-scoped session, parses the file, runs the
    ETL pipeline, and updates the uploaded_files row status accordingly.
    """
    upload_id = str(payload["upload_id"])
    business_id = str(payload["business_id"]) if payload.get("business_id") else None
    column_mapping = payload.get("column_mapping") or {}

    def _run():
        from app.tasks.ingestion_tasks import run_process_upload

        return run_process_upload(upload_id, business_id, column_mapping)

    result = await asyncio.to_thread(_run)
    return _jsonable(result)


@activity.defn(name="process_single_event")
async def act_process_single_event(payload: dict) -> dict:
    """Full canonical event processing (projections + bus publish) via a fresh session."""
    from app.database.models import Event

    event_id = payload["event_id"]
    business_id = payload.get("business_id")

    async with _db_scope(str(business_id) if business_id else None) as db:
        event = await db.get(Event, _uuid(event_id))
        if not event:
            return {"status": "not_found", "event_id": str(event_id)}

        from app.services.event_processor import process_event_sync

        await process_event_sync(db, event)

    return {"status": "processed", "event_id": str(event_id), "processed": True}


@activity.defn(name="drain_unprocessed_events")
async def act_drain_unprocessed_events(payload: dict) -> dict:
    """Supervisor: drain the cross-tenant event queue using the full processor."""
    limit = int(payload.get("limit", 1000))

    async with _db_scope(None) as db:
        from app.services.event_processor import process_unprocessed_events

        return await process_unprocessed_events(db, limit)


@activity.defn(name="run_single_pos_sync")
async def act_run_single_pos_sync(payload: dict) -> dict:
    """Run one POS connection sync (business-body in a worker thread)."""
    connection_id = str(payload["connection_id"])
    business_id = str(payload["business_id"]) if payload.get("business_id") else None

    def _run():
        from app.tasks.pos_sync_tasks import run_sync_pos_connection

        return run_sync_pos_connection(connection_id, business_id)

    result = await asyncio.to_thread(_run)
    return _jsonable(result)


@activity.defn(name="scan_due_pos_connections")
async def act_scan_due_pos_connections(payload: dict) -> dict:
    """Supervisor: return the list of POS connections due for a sync."""

    def _run():
        from app.tasks.pos_sync_tasks import scan_due_pos_connections

        return scan_due_pos_connections()

    result = await asyncio.to_thread(_run)
    return {"connections": _jsonable(result)}


def _sync_activity(name: str, module_path: str, function_name: str):
    """Factory for a one-activity sync wrapper that delegates to a NazmOS task body."""

    async def _act_body(payload: dict) -> dict:  # noqa: ANN401
        def _run():
            import importlib

            mod = importlib.import_module(module_path)
            return getattr(mod, function_name)()

        result = await asyncio.to_thread(_run)
        return _jsonable(result)

    _act_body.__name__ = f"act_{name}"
    _act_body.__qualname__ = f"act_{name}"
    _act_body = activity.defn(name=name)(_act_body)
    return _act_body


# Bulk-registered sync supervisor activities (one NazmOS task body each).
_act_rebuild_daily_summaries = _sync_activity(
    "run_rebuild_daily_summaries",
    "app.tasks.analytics_tasks",
    "run_rebuild_summaries_yesterday",
)
_act_cleanup_stale_uploads = _sync_activity(
    "run_cleanup_stale_uploads",
    "app.tasks.ingestion_tasks",
    "run_cleanup_stale_uploads",
)
_act_forecast_refresh_all = _sync_activity(
    "run_forecast_refresh_all",
    "app.tasks.forecast_tasks",
    "run_refresh_all_forecasts",
)
_act_process_pending_deletions = _sync_activity(
    "run_process_pending_deletions",
    "app.tasks.compliance_tasks",
    "run_process_pending_deletions",
)
_act_daily_full_audit = _sync_activity(
    "run_daily_full_audit",
    "app.tasks.audit_tasks",
    "run_daily_full_audit",
)
_act_goal_progress_snapshot = _sync_activity(
    "run_goal_progress_snapshot",
    "app.tasks.audit_tasks",
    "run_goal_progress_snapshot",
)
_act_learning_reconciliation = _sync_activity(
    "run_learning_reconciliation",
    "app.tasks.audit_tasks",
    "run_learning_reconciliation",
)
_act_nightly_recovery_match = _sync_activity(
    "run_nightly_recovery_match_scan",
    "app.tasks.ingestion_tasks",
    "run_nightly_recovery_match_scan",
)

# Per-business supervisor — iterates active businesses and refreshes learning
# for each with per-business RLS isolation.  Corrects the legacy beat behavior
# that passed ``business_id=None`` to the per-business async helper.
_act_refresh_model_performance = _sync_activity(
    "run_refresh_model_performance",
    "app.tasks.learning_tasks",
    "run_refresh_model_performance_all",
)

# ── Phase 4D — durable business improvement cycle ─────────────────────
#
# One cycle is decomposed into THREE activities so a workflow can drive the
# consumer durable stage machine one stage per activity call, exactly like the
# deterministic ``run_all`` loop but resumable across process restarts:
#
#   business_cycle_start     idempotent run creation (duplicate trigger -> the
#                            SAME cycle_id; the row's unique key keeps one row)
#   business_cycle_advance   load the persisted cursor FIRST (reconcile-before-
#                            retry), then advance exactly one stage
#   business_cycle_reconcile first recovery step when an external outcome is
#                            unknown: load the persisted stage cursor and allow
#                            a retry ONLY within budget — never blind-retry an
#                            already-ok stage or a recorded/reported outcome
#
# Policy callables never cross the wire: payloads carry the policy NAME and
# each activity resolves the concrete immutable CyclePolicy from the registry.


def _rebuild_evidence(tenant_id: str, business_id: str, observations: list[dict] | None) -> Any:
    """Rehydrate the loop's EvidenceStore from JSON-safe payload observations."""
    from app.services.business_loop.evidence import EvidenceStore, normalize_observation

    store = EvidenceStore()
    for obs in observations or []:
        rec, reason = normalize_observation(
            tenant_id=tenant_id,
            business_id=business_id,
            raw=obs.get("raw", {}),
            source_type=obs.get("source_type", "synthetic.pos"),
            source_reference=obs.get("source_reference", ""),
            observation_type=obs.get("observation_type", "inventory.observed"),
            event_timestamp=obs.get("event_timestamp", ""),
            observed_at=obs.get("observed_at", ""),
            required_fields=tuple(obs.get("required_fields", ())),
        )
        if rec is not None:
            store.put(rec)
    return store


def _cycle_cursor(run: Any, **extra: Any) -> dict:
    """JSON-safe cursor over a durable CycleRun (stage machine + composite output)."""
    return {
        "cycle_id": run.cycle_id,
        "tenant_id": run.tenant_id,
        "business_id": run.business_id,
        "stage_index": run.stage_index,
        "completed": bool(run.completed),
        "last_error": run.last_error,
        "starting_state_version": run.starting_state_version,
        "stages": [
            {
                "stage": s.stage.value if hasattr(s.stage, "value") else str(s.stage),
                "status": s.status,
                "attempts": s.attempts,
                "error": s.error,
            }
            for s in run.stages
        ],
        "state_output": _jsonable(run.state_output),
        **extra,
    }


@activity.defn(name="business_cycle_start")
async def act_business_cycle_start(payload: dict) -> dict:
    """Idempotent cycle start — duplicate trigger returns the existing run."""
    tenant_id = str(payload["tenant_id"])
    business_id = str(payload["business_id"])
    trigger = str(payload.get("trigger", "synthetic"))
    trigger_token = str(payload.get("trigger_token", ""))
    async with _db_scope(business_id) as db:
        from app.services.business_loop.cycle import CycleOrchestrator, derive_cycle_id
        from app.services.business_loop.policy_registry import resolve_cycle_policy
        from app.services.cycle_run_repository import PostgresCycleRepository

        policy = resolve_cycle_policy(str(payload.get("policy", "synthetic")))
        repo = PostgresCycleRepository(db)
        cycle_id = derive_cycle_id(
            tenant_id=tenant_id, business_id=business_id, trigger=trigger, trigger_token=trigger_token
        )
        existing = await repo.load(business_id, cycle_id)
        if existing is not None:
            return _cycle_cursor(existing, duplicate=True)
        evidence = _rebuild_evidence(tenant_id, business_id, payload.get("observations"))
        verif = _rebuild_evidence(tenant_id, business_id, payload.get("verification_observations"))
        orch = CycleOrchestrator(
            repository=repo,
            evidence=evidence,
            verification_evidence=verif,
            policy=policy,
        )
        run = await orch.start(
            tenant_id=tenant_id,
            business_id=business_id,
            trigger=trigger,
            trigger_token=trigger_token,
        )
    return _cycle_cursor(run, duplicate=False, phase4d_started=True)


@activity.defn(name="business_cycle_advance")
async def act_business_cycle_advance(payload: dict) -> dict:
    """Load the persisted cursor, then advance exactly ONE stage (reconcile-first)."""
    tenant_id = str(payload["tenant_id"])
    business_id = str(payload["business_id"])
    cycle_id = str(payload["cycle_id"])
    async with _db_scope(business_id) as db:
        from app.services.business_loop.cycle import CycleOrchestrator
        from app.services.business_loop.policy_registry import resolve_cycle_policy
        from app.services.business_loop.state import BusinessStateSnapshot
        from app.services.cycle_run_repository import PostgresCycleRepository

        repo = PostgresCycleRepository(db)
        # Reconcile-before-retry: the durable cursor is the source of truth.
        run = await repo.load(business_id, cycle_id)
        if run is None:
            return {"found": False, "cycle_id": cycle_id}
        # Rehydrate the snapshot from the persisted projection (lossless 4A
        # round-trip) so freshness/opportunity/verification measure the REAL
        # pre-state, not the empty-domain fallback.
        if run._snapshot is None and run.state_output.get("state"):
            run._snapshot = BusinessStateSnapshot.from_dict(run.state_output["state"])
        evidence = _rebuild_evidence(tenant_id, business_id, payload.get("observations"))
        verif = _rebuild_evidence(tenant_id, business_id, payload.get("verification_observations"))
        policy = resolve_cycle_policy(str(payload.get("policy", "synthetic")))
        orch = CycleOrchestrator(
            repository=repo,
            evidence=evidence,
            verification_evidence=verif,
            policy=policy,
        )
        # Phase 4E — a persisted cycle may NOT advance past its pinned baseline
        # when the evidence the resume projects can no longer reproduce it. Drift
        # is a hard block (never a blind retry): no stage attempt is consumed.
        revalidation = await orch.revalidate_persisted(run)
        if not revalidation["ok"]:
            run.last_error = f"revalidation_blocked:{revalidation['status']}"
            run.state_output["revalidation"] = revalidation
            await repo.save(run)
            return _cycle_cursor(
                run, advanced=False, done=False, blocked=True, revalidation=revalidation
            )
        advanced = await orch.run_one_stage(run)
        # Phase 4F — persist the canonical cycle→outcome linkage once per run.
        # Idempotent: the ledger key derives from (tenant, execution_key,
        # recommendation) and the marker is persisted with the run, so replays
        # never double-attach. Best-effort: capture must never block the cycle.
        if not run.state_output.get("outcome_recorded"):
            from app.services.business_loop.outcome_linkage import attach_cycle_outcome

            attach = attach_cycle_outcome(run)
            if attach is not None:
                run.state_output["outcome_recorded"] = attach.to_dict()
                run.state_output["outcome_attachment"] = attach.to_dict()
                await repo.save(run)
        done = run.completed or run.stage_index >= len(run.stages) or not advanced
        blocked = (not advanced) and not run.completed
    return _cycle_cursor(run, advanced=bool(advanced), done=bool(done), blocked=bool(blocked))


@activity.defn(name="business_cycle_reconcile")
async def act_business_cycle_reconcile(payload: dict) -> dict:
    """First recovery step on an unknown external outcome: report the persisted
    stage cursor and allow a retry ONLY within budget.

    Never re-runs an already-ok stage and never blind-retries a record/receipt
    (the RECONCILIATION stage already wrote allow_retry=False). A pure-compute
    orphaned ``running`` stage (worker lost mid-write) is re-queued only while its
    attempt count stays inside the policy budget; an orphaned running EXECUTION is
    an UNKNOWN external outcome and is NEVER re-queued (converged to an
    unconfirmed receipt instead, mirroring the run_one_stage guard).
    """
    business_id = str(payload["business_id"])
    cycle_id = str(payload["cycle_id"])
    async with _db_scope(business_id) as db:
        from app.services.business_loop.contracts import CycleStage
        from app.services.business_loop.policy_registry import resolve_cycle_policy
        from app.services.business_loop.state import BusinessStateSnapshot
        from app.services.cycle_run_repository import PostgresCycleRepository

        repo = PostgresCycleRepository(db)
        run = await repo.load(business_id, cycle_id)
        if run is None:
            return {"found": False, "cycle_id": cycle_id, "allow_retry": False}
        if run._snapshot is None and run.state_output.get("state"):
            run._snapshot = BusinessStateSnapshot.from_dict(run.state_output["state"])
        if run.completed or run.stage_index >= len(run.stages):
            return dict(_cycle_cursor(run), allow_retry=False, reconciliation="completed")
        policy = resolve_cycle_policy(str(payload.get("policy", "synthetic")))
        stage = run.stages[run.stage_index]
        base = {
            "cycle_id": cycle_id,
            "stage_index": run.stage_index,
            "stage": stage.stage.value if hasattr(stage.stage, "value") else str(stage.stage),
            "status": stage.status,
            "attempts": stage.attempts,
            "error": stage.error,
            "completed": False,
        }
        if stage.status == "ok":
            return dict(base, allow_retry=False, reconciliation="stage_already_ok")
        if stage.status == "running":
            if stage.stage == CycleStage.EXECUTION:
                # 4I blind-rerun fix: a resumed EXECUTION still ``running`` is an
                # UNKNOWN external outcome (the handler may have partially
                # executed). Re-queueing it would erase the ``running`` marker and
                # let run_one_stage re-invoke the EXECUTION handler (its guard
                # only checks a persisted ``running`` status, cycle.py). Converge
                # exactly like that guard: record an unconfirmed receipt so
                # RECONCILIATION becomes reconciliation-required and nothing is
                # blind-retried. Allow the workflow to advance so the very next
                # stage writes that durable record — never a re-run of EXECUTION.
                execution = dict(run.state_output.get("execution") or {})
                run.state_output["execution"] = {
                    **execution,
                    "resumed_crashed": True,
                    "receipt": execution.get("receipt")
                    or {
                        "ok": False,
                        "details": {"reason": "unconfirmed_external_outcome_after_restart"},
                    },
                }
                stage.status = "ok"
                await repo.save(run)
                return dict(base, status="ok", reconcile_guard="execution_converged_unconfirmed", allow_retry=True, reconciliation="execution_unconfirmed")
            # Worker lost mid-write: outcome unknown. Re-queue within budget only.
            if stage.attempts < policy.max_retries_per_stage:
                stage.status = "pending"
                stage.error = ""
                await repo.save(run)
                return dict(base, status="pending", attempts=stage.attempts, allow_retry=True, reconciliation="reconcile_requeued")
            stage.status = "failed"
            stage.error = "unknown_external_outcome_incomplete"
            await repo.save(run)
            return dict(base, status="failed", attempts=stage.attempts, allow_retry=False, reconciliation="budget_exhausted")
        if stage.status == "failed":
            return dict(base, allow_retry=bool(stage.attempts < policy.max_retries_per_stage), reconciliation="recorded_failure")
        return dict(base, allow_retry=True, reconciliation="pending_fresh")


# ── Registration table (single source for the worker + tests) ─────────

ACTIVITIES: dict[str, Callable[[dict], Any]] = {
    "revalidate_capability": act_revalidate_capability,
    "validate_action_constraints": act_validate_action_constraints,
    "record_constraint_block": act_record_constraint_block,
    "check_execution_idempotency": act_check_execution_idempotency,
    "apply_restock": act_apply_restock,
    "apply_price_change": act_apply_price_change,
    "apply_discount": act_apply_discount,
    "apply_alert_dismiss": act_apply_alert_dismiss,
    "record_manual_action": act_record_manual_action,
    "record_agent_approval": act_record_agent_approval,
    "agent_mark_executing": act_agent_mark_executing,
    "apply_agent_action": act_apply_agent_action,
    "record_agent_terminal": act_record_agent_terminal,
    "record_terminal_outcome": act_record_terminal_outcome,
    "apply_simulated_execution": act_apply_simulated_execution,
    # Phase 2A — background / scheduled operations
    "process_upload_ingestion": act_process_upload_ingestion,
    "process_single_event": act_process_single_event,
    "drain_unprocessed_events": act_drain_unprocessed_events,
    "run_single_pos_sync": act_run_single_pos_sync,
    "scan_due_pos_connections": act_scan_due_pos_connections,
    "run_rebuild_daily_summaries": _act_rebuild_daily_summaries,
    "run_cleanup_stale_uploads": _act_cleanup_stale_uploads,
    "run_forecast_refresh_all": _act_forecast_refresh_all,
    "run_process_pending_deletions": _act_process_pending_deletions,
    "run_refresh_model_performance": _act_refresh_model_performance,
    "run_daily_full_audit": _act_daily_full_audit,
    "run_goal_progress_snapshot": _act_goal_progress_snapshot,
    "run_learning_reconciliation": _act_learning_reconciliation,
    "run_nightly_recovery_match_scan": _act_nightly_recovery_match,
    # Phase 4D — durable business improvement cycle
    "business_cycle_start": act_business_cycle_start,
    "business_cycle_advance": act_business_cycle_advance,
    "business_cycle_reconcile": act_business_cycle_reconcile,
}

ALL_ACTIVITY_FUNCTIONS = list(ACTIVITIES.values())
ALL_ACTIVITY_NAMES = frozenset(ACTIVITIES)