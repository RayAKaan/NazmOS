"""Execution runner — single canonical entrypoint for all execution paths.

Dispatches to the appropriate workflow. Under ``USE_TEMPORAL=False``
(default / CI) runs the workflow in-process via the local deterministic
runner. Under ``USE_TEMPORAL=True`` (prod) connects to the Temporal
server via the temporalio SDK.

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
    """Route to the correct runner based on USE_TEMPORAL setting."""
    from app.config import get_settings
    settings = get_settings()

    if settings.USE_TEMPORAL:
        return await _temporal_run(workflow_fn, db, req)
    else:
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

    This is the same code path that Temporal would replay. CI runs with
    this runner; determinism is testable by calling the workflow function
    twice with identical inputs and asserting the same result.
    """
    return await workflow_fn(db, req)


# ── Temporal client runner (USE_TEMPORAL=True, prod) ─────────────────


async def _temporal_run(workflow_fn: Any, db: AsyncSession, req: Any) -> Any:
    """Execute the workflow via the Temporal server.

    Requires the temporalio SDK and a running Temporal server (see
    docker-compose for the Temporal service definition).

    The workflow function is registered with the Temporal worker;
    here we start it as a client and await the result.
    """
    try:
        from temporalio.client import Client
    except ImportError:
        raise RuntimeError(
            "temporalio is not installed. Install it with: pip install temporalio"
        )

    from app.config import get_settings
    settings = get_settings()

    temporal_endpoint = getattr(settings, "TEMPORAL_ENDPOINT", "localhost:7233")
    task_queue = "nazm-execution"

    client = await Client.connect(temporal_endpoint)

    # The workflow function name must match what's registered with the worker.
    # For now, fall back to local execution if Temporal connection fails.
    try:
        result = await client.execute_workflow(
            workflow_fn.__name__,
            req,
            id=f"exec-{req.execution_key}" if req.execution_key else f"exec-{req.entity_id}",
            task_queue=task_queue,
        )
        return result
    except Exception as exc:
        logger.warning(
            "temporal_workflow_fallback_to_local",
            error=str(exc),
            workflow=workflow_fn.__name__,
        )
        # Fallback: run locally if Temporal server is unavailable
        return await _local_run(workflow_fn, db, req)
