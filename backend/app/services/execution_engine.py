"""Execution Engine service (Phase 5).

Idempotently applies approved actions to external systems and emits
execution.completed / execution.failed events.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Event, ExecutionJob
from app.utils.logger import setup_logger

logger = setup_logger("execution_engine")


def _to_uuid(value: UUID | str) -> UUID:
    if isinstance(value, UUID):
        return value
    return UUID(value)


async def create_execution_job(
    session: AsyncSession,
    business_id: UUID | str,
    action_type: str,
    entity_type: str,
    entity_id: UUID | str,
    payload: dict[str, Any],
    decision_id: UUID | str | None = None,
    plan_id: UUID | str | None = None,
) -> ExecutionJob:
    """Create an idempotent execution job."""
    business_id = _to_uuid(business_id)
    entity_id = _to_uuid(entity_id)

    # Idempotency: if an identical pending/completed job exists, return it.
    result = await session.execute(
        select(ExecutionJob).where(
            ExecutionJob.business_id == business_id,
            ExecutionJob.action_type == action_type,
            ExecutionJob.entity_type == entity_type,
            ExecutionJob.entity_id == entity_id,
            ExecutionJob.status.in_(["pending", "completed"]),
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        return existing

    job = ExecutionJob(
        business_id=business_id,
        decision_id=_to_uuid(decision_id) if decision_id else None,
        plan_id=_to_uuid(plan_id) if plan_id else None,
        action_type=action_type,
        entity_type=entity_type,
        entity_id=entity_id,
        payload=payload,
        status="pending",
    )
    session.add(job)
    await session.flush()
    return job


async def execute_job(
    session: AsyncSession,
    job: ExecutionJob,
) -> ExecutionJob:
    """Execute a pending job and record the outcome.

    External adapters are invoked here. For now, the engine simulates the
    external call and emits an event so the event stream records the action.
    """
    if job.status != "pending":
        return job

    job.status = "executing"
    await session.flush()

    try:
        # Simulate external execution. In production this would call POS,
        # WhatsApp, supplier API, etc.
        external_reference = f"EXT-{job.action_type.upper()}-{job.id.hex[:8]}"
        result = {
            "simulated": True,
            "external_reference": external_reference,
            "action_type": job.action_type,
            "entity_type": job.entity_type,
            "entity_id": str(job.entity_id),
            "payload": job.payload,
        }

        # Emit execution.completed event.
        event_payload = {
            "job_id": str(job.id),
            "action_type": job.action_type,
            "external_reference": external_reference,
        }
        checksum = hashlib.sha256(
            json.dumps(event_payload, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()
        event = Event(
            business_id=job.business_id,
            event_type="execution.completed",
            source="execution_engine",
            source_id=str(job.id),
            payload=event_payload,
            checksum=checksum,
            occurred_at=datetime.now(timezone.utc),
            processed=True,
            processed_at=datetime.now(timezone.utc),
        )
        session.add(event)

        job.status = "completed"
        job.result = result
        job.external_reference = external_reference
        job.executed_at = datetime.now(timezone.utc)
        logger.info(
            "Execution job completed",
            extra={"job_id": str(job.id), "action_type": job.action_type},
        )
    except Exception as exc:
        job.status = "failed"
        job.error = str(exc)
        logger.exception("Execution job failed", extra={"job_id": str(job.id)})

    await session.flush()
    return job


async def get_execution_job(
    session: AsyncSession,
    job_id: UUID | str,
    business_id: UUID | str | None = None,
) -> ExecutionJob | None:
    query = select(ExecutionJob).where(ExecutionJob.id == _to_uuid(job_id))
    if business_id is not None:
        query = query.where(ExecutionJob.business_id == _to_uuid(business_id))
    result = await session.execute(query)
    return result.scalar_one_or_none()


async def execute_from_request(
    session: AsyncSession,
    business_id: UUID | str,
    action_type: str,
    entity_type: str,
    entity_id: UUID | str,
    payload: dict[str, Any],
    decision_id: UUID | str | None = None,
    plan_id: UUID | str | None = None,
) -> ExecutionJob:
    """Create and immediately execute an execution job."""
    job = await create_execution_job(
        session,
        business_id,
        action_type,
        entity_type,
        entity_id,
        payload,
        decision_id=decision_id,
        plan_id=plan_id,
    )
    return await execute_job(session, job)
