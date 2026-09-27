"""Temporal workflow definitions for NazmOS execution.

These classes are the exact orchestration skeletons executed by the Temporal
server under ``USE_TEMPORAL=True``. They mirror the step order of the local
deterministic functions in ``app.orchestration.workflows`` so both substrates
produce identical outcomes:

- ``ManualActionWorkflow``: capability → constraints → idempotency → apply → record
- ``AgentApprovalWorkflow``: approve → executing → apply → terminal → learning
- ``SimulatedWorkflow``: apply-simulated (no business-data mutation)

No business logic lives here: every side effect is delegated to a real
activity (``app.orchestration.temporal.activities``) whose name and explicit
retry policy are resolved from ``app.orchestration.temporal.policies``.
Determinism requirements are respected: no clocks, no random, no I/O outside
``workflow.execute_activity`` (the one best-effort learning call is itself an
activity, executed last with a catch).
"""
from __future__ import annotations

import datetime
from typing import Any

from temporalio import workflow

from app.orchestration.operations import (
    ACTIVITY_TIMEOUTS_SECONDS,
    BUSINESS_CYCLE_MAX_ADVANCES,
    WF_BUSINESS_CYCLE,
    WF_CLEANUP_STALE_UPLOADS,
    WF_DAILY_FULL_AUDIT,
    WF_DRAIN_UNPROCESSED_EVENTS,
    WF_EVENT_PROCESS,
    WF_FORECAST_REFRESH_ALL,
    WF_GOAL_PROGRESS_SNAPSHOT,
    WF_LEARNING_RECONCILIATION,
    WF_NIGHTLY_RECOVERY_MATCH_SCAN,
    WF_POS_SWEEP,
    WF_POS_SYNC_RUN,
    WF_PROCESS_PENDING_DELETIONS,
    WF_REBUILD_DAILY_SUMMARIES,
    WF_REFRESH_MODEL_PERFORMANCE,
    WF_UPLOAD_INGEST,
)
from app.orchestration.temporal.policies import activity_retry_policy

# Direct workflow-start path (all steps; matches the local composition).
START_TO_CLOSE = datetime.timedelta(seconds=30)

# Manual action-type → apply activity name (mirrors workflows.py dispatch).
APPLY_ACTIVITY_BY_ACTION: dict[str, str] = {
    "RESTOCK": "apply_restock",
    "PRICE_CHANGE": "apply_price_change",
    "DISCOUNT": "apply_discount",
    "ALERT_DISMISS": "apply_alert_dismiss",
}

with workflow.unsafe.imports_passed_through():
    # Imported only for the sandbox import pass; no clock/UUID usage in workflows.
    from app.orchestration.workflows import WF_AGENT_APPROVAL, WF_MANUAL_ACTION, WF_SIMULATED  # noqa: F401  (type names)


async def _act(name: str, payload: dict[str, Any]) -> Any:
    return await workflow.execute_activity(
        name,
        payload,
        start_to_close_timeout=START_TO_CLOSE,
        retry_policy=activity_retry_policy(name),
    )


async def _act_long(name: str, payload: dict[str, Any]) -> Any:
    timeout = datetime.timedelta(
        seconds=ACTIVITY_TIMEOUTS_SECONDS.get(name, int(START_TO_CLOSE.total_seconds()))
    )
    return await workflow.execute_activity(
        name,
        payload,
        start_to_close_timeout=timeout,
        retry_policy=activity_retry_policy(name),
    )


def _meta(workflow_type: str) -> dict[str, str]:
    return {
        "workflow": workflow_type,
        "run_id": workflow.info().run_id,
        "workflow_id": workflow.info().workflow_id,
    }


@workflow.defn(name=WF_MANUAL_ACTION)
class ManualActionWorkflow:
    @workflow.run
    async def run(self, req: dict) -> dict:
        business_id = req["business_id"]
        action_type = req["action_type"]
        entity_id = req["entity_id"]

        # 1. Capability revalidation (only when an actor is attached).
        if req.get("user_id"):
            cap = await _act(
                "revalidate_capability",
                {"business_id": business_id, "user_id": req["user_id"]},
            )
            if not cap["ok"]:
                return {
                    **_meta(WF_MANUAL_ACTION),
                    "blocked": True,
                    "reason_code": "INSUFFICIENT_CAPABILITY",
                    "reason": "User lacks can_approve_actions capability for this business.",
                }

        # 2. Owner-constraint / state guard (verdict only).
        verdict = await _act(
            "validate_action_constraints",
            {
                "business_id": business_id,
                "entity_id": entity_id,
                "action_type": action_type,
                "payload": {**req.get("payload", {}), "item_id": str(entity_id)},
                "previous_state": req.get("previous_state") or {},
                "new_state": req.get("new_state") or {},
            },
        )
        if verdict.get("blocked"):
            await _act(
                "record_constraint_block",
                {
                    "business_id": business_id,
                    "action_type": action_type,
                    "reason_code": verdict.get("reason_code"),
                    "reason": verdict.get("reason"),
                    "attempted_by": req.get("user_id"),
                    "new_state": req.get("new_state") or {},
                },
            )
            return {
                **_meta(WF_MANUAL_ACTION),
                "blocked": True,
                "reason_code": verdict.get("reason_code"),
                "reason": verdict.get("reason"),
            }

        # 3. Durable idempotency check.
        idem = await _act(
            "check_execution_idempotency",
            {
                "business_id": business_id,
                "execution_key": req["execution_key"],
                "table": "executed_actions",
            },
        )
        if idem.get("existing"):
            return {
                **_meta(WF_MANUAL_ACTION),
                "replayed": True,
                "action_id": idem.get("id"),
                "reason": f"Action already executed (replayed key={req['execution_key'][:8]})",
            }

        # 4. Apply business mutation (exactly-once: deterministic policy, never retried).
        apply_name = APPLY_ACTIVITY_BY_ACTION.get(action_type)
        outcome: dict[str, Any]
        if apply_name == "apply_alert_dismiss":
            outcome = await _act(apply_name, {"decision_id": entity_id})
        elif apply_name is not None:
            outcome = await _act(
                apply_name,
                {
                    "business_id": business_id,
                    "item_id": entity_id,
                    "new_state": req.get("new_state") or {},
                },
            )
        else:
            outcome = {"executed": False, "reason": f"Unknown action type: {action_type}"}

        # 5. Record outcome (idempotent, transient-retry).
        rec = await _act(
            "record_manual_action",
            {
                "business_id": business_id,
                "action_type": action_type,
                "entity_type": req.get("entity_type", ""),
                "entity_id": entity_id,
                "previous_state": req.get("previous_state") or {},
                "new_state": req.get("new_state") or {},
                "source": req.get("source", "manual"),
                "execution_key": req["execution_key"],
                "decision_id": req.get("decision_id"),
                "user_id": req.get("user_id"),
                "outcome": outcome,
            },
        )

        if outcome.get("executed"):
            return {
                **_meta(WF_MANUAL_ACTION),
                "success": True,
                "action_id": rec.get("action_id"),
                "outcome": outcome,
                "message": outcome.get("message", "Executed"),
            }
        return {
            **_meta(WF_MANUAL_ACTION),
            "success": False,
            "action_id": rec.get("action_id"),
            "outcome": outcome,
            "message": outcome.get("reason", "Execution failed"),
            "error": outcome.get("reason"),
        }


@workflow.defn(name=WF_AGENT_APPROVAL)
class AgentApprovalWorkflow:
    @workflow.run
    async def run(self, req: dict) -> dict:
        action_id = req["action_id"]

        # 1. Approve (pending_approval → approved; single-transition guard).
        approval = await _act(
            "record_agent_approval",
            {
                "business_id": req.get("business_id"),
                "action_id": action_id,
                "note": req.get("note") or "Approved",
                "decided_by": req.get("decided_by"),
            },
        )
        if not approval.get("ok"):
            return {**_meta(WF_AGENT_APPROVAL), **approval}

        # 2. approve → executing (raced/stale approvals never proceed).
        mark = await _act(
            "agent_mark_executing",
            {
                "business_id": req.get("business_id"),
                "action_id": action_id,
            },
        )
        if not mark.get("ok"):
            return {**_meta(WF_AGENT_APPROVAL), "ok": False, "reason": mark.get("reason")}

        # 3. Apply business mutation (exactly-once).
        outcome = await _act(
            "apply_agent_action",
            {
                "business_id": approval["business_id"],
                "action_id": action_id,
                "action_type": approval["action_type"],
                "payload": approval.get("payload"),
            },
        )

        # 4. Record terminal status.
        await _act(
            "record_agent_terminal",
            {
                "business_id": approval.get("business_id"),
                "action_id": action_id,
                "outcome": outcome,
            },
        )

        # 5. Best-effort learning/KG distillation (never fails the workflow).
        try:
            await _act(
                "record_terminal_outcome",
                {"business_id": approval.get("business_id"), "action_id": action_id},
            )
        except Exception:  # noqa: BLE001 - best-effort by design
            pass

        return {
            **_meta(WF_AGENT_APPROVAL),
            "ok": True,
            "action_id": str(action_id),
            "outcome": outcome,
        }


@workflow.defn(name=WF_SIMULATED)
class SimulatedWorkflow:
    @workflow.run
    async def run(self, req: dict) -> dict:
        # apply_simulated_execution records an ExecutionJob and never mutates
        # business data (ADR §7). Deterministic policy: never retried.
        outcome = await _act(
            "apply_simulated_execution",
            {
                "business_id": req["business_id"],
                "action_type": req["action_type"],
                "entity_type": req.get("entity_type", ""),
                "entity_id": req["entity_id"],
                "payload": req.get("payload", {}),
            },
        )
        return {**_meta(WF_SIMULATED), **outcome}


# ── Phase 2A — background / scheduled operations ──────────────────────


@workflow.defn(name=WF_UPLOAD_INGEST)
class UploadIngestWorkflow:
    @workflow.run
    async def run(self, req: dict) -> dict:
        outcome = await _act_long(
            "process_upload_ingestion",
            {
                "upload_id": req["upload_id"],
                "business_id": req.get("business_id"),
                "column_mapping": req.get("column_mapping") or {},
            },
        )
        return {**_meta(WF_UPLOAD_INGEST), **outcome}


@workflow.defn(name=WF_POS_SYNC_RUN)
class PosSyncRunWorkflow:
    @workflow.run
    async def run(self, req: dict) -> dict:
        outcome = await _act_long(
            "run_single_pos_sync",
            {
                "connection_id": req["connection_id"],
                "business_id": req.get("business_id"),
            },
        )
        return {**_meta(WF_POS_SYNC_RUN), **outcome}


@workflow.defn(name=WF_EVENT_PROCESS)
class EventProcessWorkflow:
    @workflow.run
    async def run(self, req: dict) -> dict:
        outcome = await _act_long("process_single_event", req)
        return {**_meta(WF_EVENT_PROCESS), **outcome}


@workflow.defn(name=WF_DRAIN_UNPROCESSED_EVENTS)
class DrainUnprocessedEventsWorkflow:
    @workflow.run
    async def run(self, req: dict) -> dict:
        outcome = await _act_long("drain_unprocessed_events", req or {})
        return {**_meta(WF_DRAIN_UNPROCESSED_EVENTS), **outcome}


@workflow.defn(name=WF_POS_SWEEP)
class PosSweepWorkflow:
    @workflow.run
    async def run(self, req: dict) -> dict:
        scan = await _act_long("scan_due_pos_connections", req or {})
        due = scan.get("connections") or []
        results: list[dict] = []
        for conn in due:
            try:
                results.append(
                    await _act_long("run_single_pos_sync", conn)
                )
            except Exception as exc:  # noqa: BLE001 - per-connection isolation
                results.append(
                    {
                        "connection_id": conn.get("connection_id"),
                        "success": False,
                        "error": str(exc)[:1000],
                    }
                )
        return {**_meta(WF_POS_SWEEP), "scanned": len(due), "results": results}


# ── Phase 4D — durable business improvement cycle ─────────────────────

# Stable per-trigger workflow id: a duplicate trigger with the SAME
# tenant/business/trigger/token resolves to the SAME cycle_id and SAME
# workflow id, so the row's unique (business_id, cycle_id) key guarantees
# exactly one cycle row per trigger even across duplicate dispatches.
#
# Recovery contract (reconcile-before-retry): the workflow never retries a
# stage blindly. On any unknown outcome it runs ``business_cycle_reconcile``
# FIRST, which loads the persisted stage cursor from Postgres and only allows
# a retry when the durable state is still within budget. Every advance is also
# itself reconcile-first (the activity re-loads the cursor before acting).
@workflow.defn(name=WF_BUSINESS_CYCLE)
class CycleRunWorkflow:
    @workflow.run
    async def run(self, req: dict) -> dict:
        started = await _act_long("business_cycle_start", req or {})
        if started.get("completed"):
            return {**_meta(WF_BUSINESS_CYCLE), **started, "done": True}
        # ``duplicate`` here means the cycle row already exists and is NOT
        # completed — a resume (e.g. worker-restart recovery) or a duplicate
        # dispatch of a running cycle. Either way the correct move is to carry
        # on advancing from the persisted cursor, never to short-circuit.
        cycle_payload = {**(req or {}), "cycle_id": started.get("cycle_id")}
        for _ in range(BUSINESS_CYCLE_MAX_ADVANCES):
            try:
                step = await _act_long("business_cycle_advance", cycle_payload)
            except Exception as exc:
                # Unknown external outcome — reconcile-before-retry: load the
                # persisted cursor and only re-advance when durable state allows.
                reconciled = await _act_long("business_cycle_reconcile", cycle_payload)
                if not reconciled.get("allow_retry"):
                    return {
                        **_meta(WF_BUSINESS_CYCLE),
                        **reconciled,
                        "cycle_id": started.get("cycle_id"),
                        "blocked": True,
                        "last_error": str(exc)[:1000],
                    }
                continue
            if step.get("done") or step.get("blocked"):
                return {**_meta(WF_BUSINESS_CYCLE), **step}
        return {
            **_meta(WF_BUSINESS_CYCLE),
            "cycle_id": started.get("cycle_id"),
            "blocked": True,
            "last_error": "cycle_guard_exceeded",
        }


def _make_generic_wf(name: str, activity_name: str):  # noqa: D401
    """Factory for a simple one-activity workflow class.

    Every generated class gets its own ``@workflow.run`` method (with a matching
    ``__qualname__``, which the Temporal SDK requires for a valid workflow
    class) and is registered via ``workflow.defn(name=...)``, so the worker
    sees a fully-decorated runtime workflow exactly like the hand-written ones.
    """
    cls_name = f"{name.title().replace('_', '')}Workflow"

    async def run(self, req: dict) -> dict:
        result = await _act_long(self.ACTIVITY_NAME, req or {})
        return {**_meta(self.WF_TYPE), **result}

    run.__qualname__ = f"{cls_name}.run"
    run = workflow.run(run)
    cls = type(
        cls_name,
        (),
        {
            "__qualname__": cls_name,
            "ACTIVITY_NAME": activity_name,
            "WF_TYPE": name,
            "run": run,
        },
    )
    return workflow.defn(name=name)(cls)

# Bulk one-activity workflows (former Beat schedules) — each maps 1:1 to a
# single activity whose body opens the right supervisor / per-tenant scope.
# `name` = WF_* constant; activity name = the class's ACTIVITY_NAME.
__GENERIC = [
    ("rebuild_daily_summaries", "run_rebuild_daily_summaries"),
    ("cleanup_stale_uploads", "run_cleanup_stale_uploads"),
    ("forecast_refresh_all", "run_forecast_refresh_all"),
    ("process_pending_deletions", "run_process_pending_deletions"),
    ("refresh_model_performance", "run_refresh_model_performance"),
    ("daily_full_audit", "run_daily_full_audit"),
    ("goal_progress_snapshot", "run_goal_progress_snapshot"),
    ("learning_reconciliation", "run_learning_reconciliation"),
    ("nightly_recovery_match_scan", "run_nightly_recovery_match_scan"),
]

# Build the concrete workflow classes in bulk.
_bulk_wfs: dict[str, Any] = {}
for _wf_name, _act_name in __GENERIC:
    cls = _make_generic_wf(_wf_name, _act_name)
    _bulk_wfs[_wf_name] = cls

# Registration table for the worker + tests.
WORKFLOWS: dict[str, Any] = {
    WF_MANUAL_ACTION: ManualActionWorkflow,
    WF_AGENT_APPROVAL: AgentApprovalWorkflow,
    WF_SIMULATED: SimulatedWorkflow,
    WF_UPLOAD_INGEST: UploadIngestWorkflow,
    WF_POS_SYNC_RUN: PosSyncRunWorkflow,
    WF_EVENT_PROCESS: EventProcessWorkflow,
    WF_DRAIN_UNPROCESSED_EVENTS: DrainUnprocessedEventsWorkflow,
    WF_POS_SWEEP: PosSweepWorkflow,
    WF_BUSINESS_CYCLE: CycleRunWorkflow,
    **_bulk_wfs,
}