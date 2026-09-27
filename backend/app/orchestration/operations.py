"""NazmOS background-operations surface (Phase 2A — Temporal single substrate).

Converges every previously-Celery execution path (upload ingestion, POS sync,
event processing, and the formerly-dormant Celery Beat schedules) onto Temporal
as the SINGLE production execution substrate, reusing the existing
``app.orchestration.runner`` strict-dispatch rules:

- ``USE_TEMPORAL=True`` (default, the only production-legal mode): every
  operation is executed as a real Temporal workflow with the exact name in
  ``temporal/workflows.py``. A workflow id is derived deterministically per
  entity and there is NO silent local fallback — an unreachable/failing
  Temporal substrate raises ``TemporalExecutionError``.
- ``USE_TEMPORAL=False`` (explicit dev/test selection): the operation runs
  in-process by invoking the SAME temporal activity function directly, so
  local/test runs share the identical body the worker executes.

Every activity is a thin transport boundary that calls the existing canonical
NazmOS ``run_*`` functions in ``app.tasks`` (the bodies never move into
Temporal). Scheduled operations (the former 9 Beat entries + the POS sweep)
are registered as Temporal Schedules by ``app.orchestration.temporal.schedules``.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

# ── Operation identifiers (canonical ops surface) ─────────────────────
# Directly produced by a request path.
OP_UPLOAD_INGEST = "upload_ingest"
OP_POS_SYNC_RUN = "pos_sync_run"
OP_EVENT_PROCESS = "event_process"

# Produced by a schedule (former Celery Beat entries) or on demand.
OP_DRAIN_UNPROCESSED_EVENTS = "drain_unprocessed_events"
OP_POS_SWEEP = "pos_sweep"
OP_REBUILD_DAILY_SUMMARIES = "rebuild_daily_summaries"
OP_CLEANUP_STALE_UPLOADS = "cleanup_stale_uploads"
OP_FORECAST_REFRESH_ALL = "forecast_refresh_all"
OP_PROCESS_PENDING_DELETIONS = "process_pending_deletions"
OP_REFRESH_MODEL_PERFORMANCE = "refresh_model_performance"
OP_DAILY_FULL_AUDIT = "daily_full_audit"
OP_GOAL_PROGRESS_SNAPSHOT = "goal_progress_snapshot"
OP_LEARNING_RECONCILIATION = "learning_reconciliation"

# Preserved bodies (previously Celery-dormant): callable via the ops surface,
# deliberately NOT scheduled — no behavior change vs the audited production set.
OP_NIGHTLY_RECOVERY_MATCH_SCAN = "nightly_recovery_match_scan"

# Phase 4D — durable business improvement cycle (resumable consumer-driven run).
OP_BUSINESS_CYCLE = "business_cycle_run"

# ── Temporal workflow type names (registered in temporal/workflows.py) ──
WF_UPLOAD_INGEST = OP_UPLOAD_INGEST
WF_POS_SYNC_RUN = OP_POS_SYNC_RUN
WF_EVENT_PROCESS = OP_EVENT_PROCESS
WF_DRAIN_UNPROCESSED_EVENTS = OP_DRAIN_UNPROCESSED_EVENTS
WF_POS_SWEEP = OP_POS_SWEEP
WF_REBUILD_DAILY_SUMMARIES = OP_REBUILD_DAILY_SUMMARIES
WF_CLEANUP_STALE_UPLOADS = OP_CLEANUP_STALE_UPLOADS
WF_FORECAST_REFRESH_ALL = OP_FORECAST_REFRESH_ALL
WF_PROCESS_PENDING_DELETIONS = OP_PROCESS_PENDING_DELETIONS
WF_REFRESH_MODEL_PERFORMANCE = OP_REFRESH_MODEL_PERFORMANCE
WF_DAILY_FULL_AUDIT = OP_DAILY_FULL_AUDIT
WF_GOAL_PROGRESS_SNAPSHOT = OP_GOAL_PROGRESS_SNAPSHOT
WF_LEARNING_RECONCILIATION = OP_LEARNING_RECONCILIATION
WF_NIGHTLY_RECOVERY_MATCH_SCAN = OP_NIGHTLY_RECOVERY_MATCH_SCAN

# Phase 4D.
WF_BUSINESS_CYCLE = OP_BUSINESS_CYCLE

# op -> Temporal workflow type name.
OPERATION_WORKFLOW: dict[str, str] = {
    OP_UPLOAD_INGEST: WF_UPLOAD_INGEST,
    OP_POS_SYNC_RUN: WF_POS_SYNC_RUN,
    OP_EVENT_PROCESS: WF_EVENT_PROCESS,
    OP_DRAIN_UNPROCESSED_EVENTS: WF_DRAIN_UNPROCESSED_EVENTS,
    OP_POS_SWEEP: WF_POS_SWEEP,
    OP_REBUILD_DAILY_SUMMARIES: WF_REBUILD_DAILY_SUMMARIES,
    OP_CLEANUP_STALE_UPLOADS: WF_CLEANUP_STALE_UPLOADS,
    OP_FORECAST_REFRESH_ALL: WF_FORECAST_REFRESH_ALL,
    OP_PROCESS_PENDING_DELETIONS: WF_PROCESS_PENDING_DELETIONS,
    OP_REFRESH_MODEL_PERFORMANCE: WF_REFRESH_MODEL_PERFORMANCE,
    OP_DAILY_FULL_AUDIT: WF_DAILY_FULL_AUDIT,
    OP_GOAL_PROGRESS_SNAPSHOT: WF_GOAL_PROGRESS_SNAPSHOT,
    OP_LEARNING_RECONCILIATION: WF_LEARNING_RECONCILIATION,
    OP_NIGHTLY_RECOVERY_MATCH_SCAN: WF_NIGHTLY_RECOVERY_MATCH_SCAN,
    OP_BUSINESS_CYCLE: WF_BUSINESS_CYCLE,
}

# Single-activity ops: op -> activity name (must equal POLICY_REGISTRY keys).
OPERATION_ACTIVITY: dict[str, str] = {
    OP_UPLOAD_INGEST: "process_upload_ingestion",
    OP_POS_SYNC_RUN: "run_single_pos_sync",
    OP_EVENT_PROCESS: "process_single_event",
    OP_DRAIN_UNPROCESSED_EVENTS: "drain_unprocessed_events",
    OP_REBUILD_DAILY_SUMMARIES: "run_rebuild_daily_summaries",
    OP_CLEANUP_STALE_UPLOADS: "run_cleanup_stale_uploads",
    OP_FORECAST_REFRESH_ALL: "run_forecast_refresh_all",
    OP_PROCESS_PENDING_DELETIONS: "run_process_pending_deletions",
    OP_REFRESH_MODEL_PERFORMANCE: "run_refresh_model_performance",
    OP_DAILY_FULL_AUDIT: "run_daily_full_audit",
    OP_GOAL_PROGRESS_SNAPSHOT: "run_goal_progress_snapshot",
    OP_LEARNING_RECONCILIATION: "run_learning_reconciliation",
    OP_NIGHTLY_RECOVERY_MATCH_SCAN: "run_nightly_recovery_match_scan",
}

# Per-activity start_to_close timeout (scheduled jobs are long-lived by nature).
ACTIVITY_TIMEOUTS_SECONDS: dict[str, int] = {
    "process_upload_ingestion": 900,
    "run_single_pos_sync": 900,
    "process_single_event": 300,
    "drain_unprocessed_events": 1800,
    "run_rebuild_daily_summaries": 1800,
    "run_cleanup_stale_uploads": 600,
    "run_forecast_refresh_all": 1800,
    "run_process_pending_deletions": 3600,
    "run_refresh_model_performance": 1800,
    "run_daily_full_audit": 3600,
    "run_goal_progress_snapshot": 1800,
    "run_learning_reconciliation": 1800,
    "run_nightly_recovery_match_scan": 3600,
    "scan_due_pos_connections": 120,
    # Phase 4D — business cycle activities (postgres-backed, per-stage unit).
    "business_cycle_start": 60,
    "business_cycle_advance": 60,
    "business_cycle_reconcile": 60,
}

SCHEDULED_OPERATIONS: tuple[str, ...] = (
    OP_DRAIN_UNPROCESSED_EVENTS,
    OP_REBUILD_DAILY_SUMMARIES,
    OP_CLEANUP_STALE_UPLOADS,
    OP_FORECAST_REFRESH_ALL,
    OP_PROCESS_PENDING_DELETIONS,
    OP_REFRESH_MODEL_PERFORMANCE,
    OP_DAILY_FULL_AUDIT,
    OP_GOAL_PROGRESS_SNAPSHOT,
    OP_LEARNING_RECONCILIATION,
    OP_POS_SWEEP,
)


def operation_workflow_id(op: str, payload: Optional[dict]) -> str:
    """Deterministic workflow id for per-entity ops; unique for scheduled runs.

    Directly-dispatched ops reuse a stable id (upload-<id>, pos-sync-<id>,
    event-<id>); the routers reject re-dispatch of an already-running entity, so
    a re-run with the same id is safe (idempotent bodies, ALLOW_DUPLICATE).
    Scheduled runs always carry a unique timestamped id.
    """
    payload = payload or {}
    if op == OP_UPLOAD_INGEST:
        return f"upload-{payload.get('upload_id')}"
    if op == OP_POS_SYNC_RUN:
        return f"pos-sync-{payload.get('connection_id')}"
    if op == OP_EVENT_PROCESS:
        return f"event-{payload.get('event_id')}"
    if op == OP_BUSINESS_CYCLE:
        # Stable per-trigger workflow id: a duplicate trigger reuses the SAME
        # workflow id and cycle row (idempotent by design).
        from app.services.business_loop.cycle import derive_cycle_id

        return derive_cycle_id(
            tenant_id=str(payload.get("tenant_id", "")),
            business_id=str(payload.get("business_id", "")),
            trigger=str(payload.get("trigger", "")),
            trigger_token=str(payload.get("trigger_token", "")),
        )
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    return f"{op}-{ts}-{uuid.uuid4().hex[:8]}"


def default_schedule_payload(op: str) -> dict:
    """Default cross-tenant supervisor payload for a scheduled operation."""
    return {"operation": op}


# ── Local compositions (USE_TEMPORAL=False test/dev mirror of Temporal wf) ─


async def local_pos_sweep_run(payload: dict) -> dict:
    """Mirror of the Temporal ``pos_sweep`` workflow, run in-process.

    Invokes the identical activity functions the worker executes so local and
    production runs share bodies: scan due connections, then run each sync
    with per-connection failure isolation.
    """
    from app.orchestration.temporal.activities import ACTIVITIES

    scan = await ACTIVITIES["scan_due_pos_connections"](payload or {})
    due = scan.get("connections") or []
    results: list[dict] = []
    for conn in due:
        try:
            results.append(await ACTIVITIES["run_single_pos_sync"](conn))
        except Exception as exc:  # noqa: BLE001 - per-connection failure isolation
            results.append(
                {
                    "connection_id": conn.get("connection_id"),
                    "success": False,
                    "error": str(exc)[:1000],
                }
            )
    return {"scanned": len(due), "results": results}


# Phase 4D — durable business improvement cycle: upgrade budget cap.
# Bound the advance loop the way the deterministic ``run_all`` guard does:
# at most one advance per stage, plus one extra reconcile-before-retry pass.
BUSINESS_CYCLE_MAX_ADVANCES = 128


async def local_business_cycle_run(payload: dict) -> dict:
    """In-process mirror of the Temporal ``business_cycle_run`` workflow.

    Invokes the identical activity bodies (``business_cycle_start`` /
    ``business_cycle_advance`` / ``business_cycle_reconcile``) so local/test
    runs share the exact durable-stage-machined behavior the worker executes:
    idempotent start, one stage per advance, reconcile-before-retry on an
    unknown outcome, and the same upgrade budget guard.
    """
    from app.orchestration.temporal.activities import ACTIVITIES

    started = await ACTIVITIES["business_cycle_start"](payload or {})
    if started.get("completed"):
        return started
    cycle_payload = {**(payload or {}), "cycle_id": started.get("cycle_id")}
    advanced = 0
    while advanced < BUSINESS_CYCLE_MAX_ADVANCES:
        try:
            step = await ACTIVITIES["business_cycle_advance"](cycle_payload)
        except Exception:
            # Reconcile-before-retry: load the persisted cursor first and only
            # re-advance when the durable state explicitly allows it.
            reconciled = await ACTIVITIES["business_cycle_reconcile"](cycle_payload)
            if reconciled.get("allow_retry"):
                advanced += 1
                continue
            return {**reconciled, "cycle_id": started.get("cycle_id"), "blocked": True}
        if step.get("done") or step.get("blocked"):
            return step
        advanced += 1
    return {"cycle_id": started.get("cycle_id"), "blocked": True, "last_error": "cycle_guard_exceeded"}


async def local_run(op: str, payload: dict) -> Any:
    """In-process execution of an operation (dev/tests only, never production)."""
    from app.orchestration.temporal.activities import ACTIVITIES

    if op == OP_POS_SWEEP:
        return await local_pos_sweep_run(payload)
    if op == OP_BUSINESS_CYCLE:
        return await local_business_cycle_run(payload)
    activity_name = OPERATION_ACTIVITY[op]
    return await ACTIVITIES[activity_name](payload or {})


# ── Strict dispatcher (mirrors runner._dispatch rules) ────────────────


async def dispatch_operation(
    op: str,
    payload: Optional[dict] = None,
    *,
    wait: bool = False,
) -> tuple[str, Any]:
    """Dispatch an operation, returning ``(workflow_id, result)``.

    The returned ``workflow_id`` is the durable handle under which the
    operation runs on the Temporal server (or the deterministic id the caller
    reports back in its API response when in local mode).

    ``USE_TEMPORAL=True`` (production): starts the workflow on the server and
    returns immediately unless ``wait=True`` (then the outcome is awaited).
    ``USE_TEMPORAL=False`` (explicit dev/test selection): executes the same
    activity bodies in-process and returns the outcome immediately.

    There is NO fallback: a Temporal failure raises ``TemporalExecutionError``.
    """
    from app.config import get_settings

    settings = get_settings()
    payload = payload or {}
    workflow_id = operation_workflow_id(op, payload)

    if not settings.USE_TEMPORAL:
        result = await local_run(op, payload)
        return workflow_id, result

    return await _temporal_dispatch(op, payload, workflow_id, wait=wait)


async def _temporal_dispatch(
    op: str,
    payload: dict,
    workflow_id: str,
    *,
    wait: bool,
) -> tuple[str, Any]:
    """Start/await a real Temporal workflow (the canonical production path)."""
    import asyncio

    try:
        from temporalio.client import Client
    except ImportError as exc:  # pragma: no cover
        raise TemporalExecutionError("temporalio SDK is not installed") from exc

    from app.config import get_settings
    from app.orchestration.runner import TemporalExecutionError

    settings = get_settings()
    workflow_type = OPERATION_WORKFLOW[op]

    try:
        client = await asyncio.wait_for(
            Client.connect(
                settings.TEMPORAL_ADDRESS,
                namespace=settings.TEMPORAL_NAMESPACE,
            ),
            timeout=settings.TEMPORAL_CONNECT_TIMEOUT_SECONDS,
        )
        if wait:
            result = await client.execute_workflow(
                workflow_type,
                payload,
                id=workflow_id,
                task_queue=settings.TEMPORAL_TASK_QUEUE,
            )
        else:
            await client.start_workflow(
                workflow_type,
                payload,
                id=workflow_id,
                task_queue=settings.TEMPORAL_TASK_QUEUE,
            )
            result = None
    except TemporalExecutionError:
        raise
    except Exception as exc:  # noqa: BLE001 - every failure is an explicit error
        raise TemporalExecutionError(
            f"Temporal operation failed (operation={op}, workflow={workflow_type}, "
            f"workflow_id={workflow_id}, address={settings.TEMPORAL_ADDRESS}, "
            f"task_queue={settings.TEMPORAL_TASK_QUEUE}): {exc}"
        ) from exc

    return workflow_id, result