"""Execution runner — single canonical entrypoint for all execution paths.

Dispatches to the appropriate workflow. Under ``USE_TEMPORAL=False``
(explicitly selected dev / test mode) runs the workflow in-process via the
local deterministic runner. Under ``USE_TEMPORAL=True`` (the default; the only
production-legal mode) connects to the Temporal server via the temporalio SDK.

There is NO silent fallback: if ``USE_TEMPORAL`` is true and the Temporal
substrate is unreachable or fails, ``TemporalExecutionError`` is raised and the
caller surfaces it as an explicit operational failure. Nothing is executed
locally behind the caller's back.

Routers MUST call ``run_manual_action``, ``run_agent_approval``, or
``run_simulated`` — never instantiate legacy executors directly.
"""
from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.orchestration.keys import derive_execution_key

logger = structlog.get_logger(__name__)


class TemporalExecutionError(RuntimeError):
    """Raised when Temporal execution is selected but cannot be performed.

    This is the explicit failure surface for an unavailable or failing Temporal
    substrate — it deliberately replaces any local-fallback behavior.
    """


# ── Facade functions (routers call these) ─────────────────────────────


async def run_manual_action(
    db: AsyncSession,
    *,
    business_id: UUID,
    action_type: str,
    entity_type: str,
    entity_id: UUID,
    payload: dict[str, Any] | None = None,
    previous_state: dict[str, Any] | None = None,
    new_state: dict[str, Any] | None = None,
    source: str = "manual",
    decision_id: Optional[UUID] = None,
    user_id: Optional[UUID] = None,
) -> Any:
    """Execute a manual action (actions.py / money_audit.py path).

    Returns an ActionResult with success/message/error fields.
    """
    from app.orchestration.contracts import ExecutionRequest
    from app.orchestration.workflows import manual_action_workflow

    payload = payload if payload not in (None, {}) else (new_state or {})
    key = derive_execution_key(business_id, action_type, entity_type, entity_id,
                               payload, source)
    req = ExecutionRequest(
        business_id=business_id,
        action_type=action_type,
        entity_type=entity_type,
        entity_id=entity_id,
        payload=payload,
        previous_state=previous_state or {},
        new_state=new_state or {},
        source=source,
        execution_key=key,
        decision_id=decision_id,
        user_id=user_id,
    )

    return await _dispatch(manual_action_workflow, db, req)


async def run_agent_approval(
    db: AsyncSession,
    *,
    action_id: UUID | str,
    business_id: UUID | str | None = None,
    note: str = "Approved",
    decided_by: UUID | str | None = None,
) -> dict[str, Any]:
    """Approve and execute an agent action (agent.py / whatsapp.py path).

    ``business_id`` is optional defense-in-depth: the action's own
    business_id is read from the row (matching legacy WhatsApp behavior).

    Returns a dict with ok, action_id, outcome fields.
    """
    from app.orchestration.contracts import ExecutionRequest
    from app.orchestration.workflows import agent_approval_workflow

    req = ExecutionRequest(
        business_id=business_id,
        action_id=action_id,
        note=note,
        decided_by=decided_by,
    )

    return await _dispatch(agent_approval_workflow, db, req)


async def run_agent_rejection(
    db: AsyncSession,
    *,
    action_id: UUID | str,
    business_id: UUID | str | None = None,
    note: str = "Rejected",
    decided_by: UUID | str | None = None,
) -> dict[str, Any]:
    """Reject an agent action (agent.py / whatsapp.py path).

    Returns a dict with ok, action_id fields.
    """
    from app.orchestration.record import record_agent_rejection

    return await record_agent_rejection(
        db,
        action_id=action_id,
        note=note,
        decided_by=decided_by,
        business_id=business_id,
    )


async def run_simulated(
    db: AsyncSession,
    *,
    business_id: UUID,
    action_type: str,
    entity_type: str,
    entity_id: UUID,
    payload: dict[str, Any],
    decision_id: Optional[UUID] = None,
    plan_id: Optional[UUID] = None,
) -> Any:
    """Execute a simulated action (intelligence.py path).

    Returns the ExecutionJob ORM row (matching the legacy execution_engine API
    so the intelligence router and tests keep the same shape).
    """
    from app.orchestration.contracts import ExecutionRequest
    from app.orchestration.workflows import simulated_workflow

    key = derive_execution_key(business_id, action_type, entity_type, entity_id,
                               payload, "simulated")
    req = ExecutionRequest(
        business_id=business_id,
        action_type=action_type,
        entity_type=entity_type,
        entity_id=entity_id,
        payload=payload,
        source="simulated",
        execution_key=key,
        decision_id=decision_id,
        plan_id=plan_id,
    )

    result = await _dispatch(simulated_workflow, db, req)
    job_id = result.get("job_id")
    if job_id:
        job = await get_execution_job(db, UUID(job_id), business_id)
        if job:
            return job
    return result


# ── Dispatcher ────────────────────────────────────────────────────────


async def _dispatch(workflow_fn: Any, db: AsyncSession, req: Any) -> Any:
    """Route to the correct runner based on USE_TEMPORAL setting.

    Strict dispatch: Temporal is the canonical substrate and there is NO
    fallback to the local runner when Temporal is unavailable. If
    ``USE_TEMPORAL`` is set the request MUST complete through Temporal or raise
    ``TemporalExecutionError``. The local runner is used ONLY when
    ``USE_TEMPORAL`` is explicitly disabled (development/test selection).
    """
    from app.config import get_settings
    settings = get_settings()

    if settings.USE_TEMPORAL:
        return await _temporal_run(workflow_fn, db, req)
    return await _local_run(workflow_fn, db, req)


async def get_execution_job(
    db: AsyncSession,
    job_id: UUID,
    business_id: Optional[UUID] = None,
) -> Any:
    """Fetch an execution job (simulated path read, replaces execution_engine.get_execution_job)."""
    from sqlalchemy import select
    from app.database.models import ExecutionJob

    query = select(ExecutionJob).where(ExecutionJob.id == job_id)
    if business_id is not None:
        query = query.where(ExecutionJob.business_id == business_id)
    result = await db.execute(query)
    return result.scalar_one_or_none()


# ── Local deterministic runner (USE_TEMPORAL=False, CI / tests) ──────


async def _local_run(workflow_fn: Any, db: AsyncSession, req: Any) -> Any:
    """Execute the workflow in-process — deterministic, no Temporal server.

    This runner is selected ONLY when ``USE_TEMPORAL`` is explicitly disabled
    (development / test mode). It executes the same deterministic composition
    the Temporal worker executes, so composition-level invariants are testable
    here; production execution always flows through the Temporal substrate.
    """
    return await workflow_fn(db, req)


# ── request payload serialization (Temporal-safe transport) ──────────


def _jsonable(value: Any) -> Any:
    """Coerce an execution request/value into a Temporal-payload-safe tree.

    UUIDs become strings; datetimes become ISO strings; everything else either
    stays a JSON primitive or is stringified. Activity/workflow code that needs
    a UUID re-parses it (the definitions in app.orchestration.temporal do).
    """
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


# ── Temporal client runner (USE_TEMPORAL=True, the canonical substrate) ─


async def _temporal_run(workflow_fn: Any, db: AsyncSession, req: Any) -> Any:
    """Execute the workflow via the Temporal server.

    Requires the temporalio SDK and a running Temporal server (see the
    ``temporal`` and ``nazmos-worker`` services in docker-compose.yml, and the
    ``temporal-backend`` job in CI). The workflow type is the canonical name
    registered by the NazmOS Temporal worker (app.orchestration.temporal).

    This function NEVER downgrades to the local runner. Any connection or
    execution failure is raised as ``TemporalExecutionError`` so the caller can
    surface an explicit operational failure.
    """
    import asyncio
    import dataclasses
    import uuid as _uuid

    from temporalio.client import Client

    from app.config import get_settings
    from app.orchestration.workflows import WORKFLOW_TYPE_BY_FN_NAME

    settings = get_settings()
    workflow_type = WORKFLOW_TYPE_BY_FN_NAME.get(workflow_fn.__name__, workflow_fn.__name__)
    payload = _jsonable(dataclasses.asdict(req))
    workflow_id = _workflow_id(req)

    try:
        client = await asyncio.wait_for(
            Client.connect(
                settings.TEMPORAL_ADDRESS,
                namespace=settings.TEMPORAL_NAMESPACE,
            ),
            timeout=settings.TEMPORAL_CONNECT_TIMEOUT_SECONDS,
        )
        result = await client.execute_workflow(
            workflow_type,
            payload,
            id=workflow_id,
            task_queue=settings.TEMPORAL_TASK_QUEUE,
        )
    except TemporalExecutionError:
        raise
    except Exception as exc:  # noqa: BLE001 - every failure is an explicit error
        raise TemporalExecutionError(
            f"Temporal execution failed (workflow={workflow_type}, "
            f"workflow_id={workflow_id}, "
            f"address={settings.TEMPORAL_ADDRESS}, "
            f"task_queue={settings.TEMPORAL_TASK_QUEUE}): {exc}"
        ) from exc

    return _adapt_result(workflow_type, result)


def _workflow_id(req: Any) -> str:
    """Deterministic workflow id (idempotent starts) with a random fallback."""
    action_id = getattr(req, "action_id", None)
    if action_id is not None:
        return f"agent-{action_id}"
    execution_key = getattr(req, "execution_key", "") or ""
    if execution_key:
        return f"exec-{execution_key}"
    entity_id = getattr(req, "entity_id", None)
    if entity_id is not None:
        return f"exec-{entity_id}-{getattr(req, 'action_type', '')}"
    return f"exec-{_uuid.uuid4()}"


def _adapt_result(workflow_type: str, result: Any) -> Any:
    """Map the Temporal workflow result back to the same shape local workflows return."""
    from app.orchestration.contracts import ActionResult

    if workflow_type == "manual_action":
        if result.get("blocked"):
            return ActionResult(
                success=False,
                action_id=None,
                message=result.get("reason") or "Blocked",
                error=result.get("reason_code") or result.get("reason"),
            )
        if result.get("replayed"):
            return ActionResult(
                success=True,
                action_id=None,
                message=result.get("reason") or "Action already executed (replayed)",
            )
        return ActionResult(
            success=bool(result.get("success")),
            action_id=result.get("action_id"),
            message=result.get("message") or "",
            error=result.get("error"),
        )
    return result
