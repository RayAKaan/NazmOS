"""Record activities — persist execution outcomes with idempotency.

Each record function writes the execution-tracking row (ExecutedAction,
AgentAction, or ExecutionJob) with the execution_key. The ``check_idempotency``
function enables the workflow to detect and skip duplicate executions.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ── Idempotency check ────────────────────────────────────────────────


async def check_execution_idempotency(
    db: AsyncSession,
    execution_key: str,
    *,
    table: str = "executed_actions",
) -> dict[str, Any] | None:
    """Check whether this execution_key already has a terminal outcome.

    Returns the existing outcome dict if found, None otherwise.
    """
    if not execution_key:
        return None

    if table == "executed_actions":
        result = await db.execute(
            text("""
                SELECT id, status, outcome FROM executed_actions
                WHERE execution_key = :key AND status IN ('completed', 'failed')
                LIMIT 1
            """),
            {"key": execution_key},
        )
    elif table == "agent_actions":
        result = await db.execute(
            text("""
                SELECT id, status, outcome_json FROM agent_actions
                WHERE execution_key = :key AND status IN ('executed', 'failed', 'approved')
                LIMIT 1
            """),
            {"key": execution_key},
        )
    elif table == "execution_jobs":
        result = await db.execute(
            text("""
                SELECT id, status, result FROM execution_jobs
                WHERE execution_key = :key AND status IN ('completed', 'failed')
                LIMIT 1
            """),
            {"key": execution_key},
        )
    else:
        return None

    row = result.fetchone()
    if row is None:
        return None

    logger.info(
        "orchestration_idempotent_replay",
        execution_key=execution_key[:12],
        table=table,
        existing_status=row.status,
    )
    return {"replayed": True, "id": str(row.id), "status": row.status}


# ── Manual path recording ────────────────────────────────────────────


async def record_manual_action(
    db: AsyncSession,
    *,
    business_id: UUID,
    action_type: str,
    entity_type: str,
    entity_id: UUID,
    previous_state: dict[str, Any],
    new_state: dict[str, Any],
    source: str,
    execution_key: str,
    decision_id: Optional[UUID] = None,
    user_id: Optional[UUID] = None,
    outcome: dict[str, Any] | None = None,
) -> UUID:
    """Insert an ExecutedAction row with execution_key."""
    from app.database.models import ExecutedAction

    now = _now()
    executed_action = ExecutedAction(
        business_id=business_id,
        decision_id=decision_id,
        source=source,
        action_type=action_type,
        entity_type=entity_type,
        entity_id=entity_id,
        previous_state=previous_state,
        new_state=new_state,
        status="completed" if (outcome and outcome.get("executed")) else "failed",
        executed_by=user_id,
        executed_at=now,
        outcome=outcome,
        execution_key=execution_key,
    )
    db.add(executed_action)
    await db.flush()

    # Mark decision applied if present (mutate the ORM object so the session
    # identity map stays in sync, matching the legacy executor).
    if decision_id and outcome and outcome.get("executed"):
        from app.database.models import DecisionLog

        decision = await db.get(DecisionLog, decision_id)
        if decision:
            decision.was_applied = True
            decision.applied_at = now

    logger.info(
        "orchestration_manual_recorded",
        action_id=str(executed_action.id),
        action_type=action_type,
        status=executed_action.status,
    )
    return executed_action.id


# ── Agent path recording ─────────────────────────────────────────────


async def record_agent_approval(
    db: AsyncSession,
    *,
    action_id: UUID | str,
    note: str = "Approved",
    decided_by: Optional[UUID | str] = None,
    business_id: Optional[UUID | str] = None,
) -> dict[str, Any]:
    """Transition agent_actions from pending_approval → approved → executing.

    Uses a guarded WHERE clause for the tenant-safety single-transition.
    Returns the action row data if successful, None if not found/already transitioned.
    """
    from app.utils.clock import utcnow

    now = utcnow()
    tenant_clause = "AND business_id = :business_id" if business_id else ""
    params: dict = {
        "id": str(action_id),
        "decided_by": str(decided_by) if decided_by else None,
        "note": note,
        "now": now,
    }
    if business_id:
        params["business_id"] = str(business_id)

    # Service-boundary authorization
    if decided_by is not None:
        from app.services.capabilities_service import user_has_capability
        action_ctx = await db.execute(
            text("SELECT business_id FROM agent_actions WHERE id = :id"),
            {"id": str(action_id)},
        )
        action_row = action_ctx.fetchone()
        ctx_business = str(action_row.business_id) if action_row else (str(business_id) if business_id else None)
        if ctx_business is None:
            return {"ok": False, "reason": "Action not found", "action_id": str(action_id)}
        if not await user_has_capability(db, decided_by, ctx_business, "can_approve_actions"):
            return {"ok": False, "reason": "User lacks can_approve_actions capability for this business",
                    "action_id": str(action_id)}

    # Atomic pending_approval → approved (single-transition guard)
    res = await db.execute(text(f"""
        UPDATE agent_actions
        SET status = 'approved',
            decided_at = :now,
            decided_by = COALESCE(CAST(:decided_by AS UUID), decided_by),
            decision_note = :note,
            updated_at = :now
        WHERE id = :id AND status = 'pending_approval' {tenant_clause}
        RETURNING id, business_id, action_type, payload
    """), params)  # nosec B608
    row = res.fetchone()
    if not row:
        return {"ok": False, "reason": "Action not found or not pending approval",
                "action_id": str(action_id)}

    return {
        "ok": True,
        "action_id": str(row.id),
        "business_id": str(row.business_id),
        "action_type": row.action_type,
        "payload": row.payload,
    }


async def record_agent_terminal(
    db: AsyncSession,
    *,
    action_id: UUID,
    outcome: dict[str, Any],
) -> None:
    """Transition agent_actions to terminal status after apply."""
    from app.utils.clock import utcnow

    executed = outcome.get("executed", False)
    terminal_status = "executed" if executed else (
        "failed" if outcome.get("execution_mode") != "MANUAL" else "approved"
    )

    await db.execute(text("""
        UPDATE agent_actions
        SET status = :terminal_status,
            applied_at = CASE WHEN :executed THEN :now ELSE applied_at END,
            outcome_json = CAST(:outcome AS JSON),
            updated_at = :now
        WHERE id = :id
    """), {
        "id": str(action_id),
        "terminal_status": terminal_status,
        "executed": bool(executed),
        "outcome": json.dumps(outcome),
        "now": utcnow(),
    })


async def record_agent_rejection(
    db: AsyncSession,
    *,
    action_id: UUID | str,
    note: str = "Rejected",
    decided_by: Optional[UUID | str] = None,
    business_id: Optional[UUID | str] = None,
) -> dict[str, Any]:
    """Transition agent_actions to rejected (single-transition guard)."""
    from app.utils.clock import utcnow

    now = utcnow()
    tenant_clause = "AND business_id = :business_id" if business_id else ""
    params: dict = {"id": str(action_id), "note": note, "now": now}
    if business_id:
        params["business_id"] = str(business_id)

    # Service-boundary authorization for the decision-maker.
    if decided_by is not None:
        from app.services.capabilities_service import user_has_capability
        action_ctx = await db.execute(
            text("SELECT business_id FROM agent_actions WHERE id = :id"),
            {"id": str(action_id)},
        )
        action_row = action_ctx.fetchone()
        ctx_business = str(action_row.business_id) if action_row else (str(business_id) if business_id else None)
        if ctx_business is None:
            return {"ok": False, "reason": "Action not found", "action_id": str(action_id)}
        if not await user_has_capability(db, decided_by, ctx_business, "can_approve_actions"):
            return {"ok": False, "reason": "User lacks can_approve_actions capability for this business",
                    "action_id": str(action_id)}

    res = await db.execute(text(f"""
        UPDATE agent_actions
        SET status = 'rejected',
            decided_at = :now,
            decision_note = :note,
            updated_at = :now
        WHERE id = :id AND status = 'pending_approval' {tenant_clause}
        RETURNING id, business_id
    """), params)  # nosec B608
    row = res.fetchone()
    await db.commit()
    if row:
        await record_terminal_outcome(db, row.business_id, row.id)
    return {"ok": bool(row), "action_id": str(action_id)}


async def record_terminal_outcome(
    db: AsyncSession,
    business_id: UUID | str,
    action_id: UUID | str,
) -> None:
    """Best-effort: distill terminal AgentAction into LearnedOutcome + KG edge.

    Neither write may ever fail the action transition it observes.
    """
    meta = await db.execute(
        text("SELECT action_type, status, outcome_json, payload, finding_id FROM agent_actions WHERE id = :id"),
        {"id": str(action_id)},
    )
    row = meta.fetchone()
    finding_id = row.finding_id if row else None

    try:
        from app.services.outcome_learning import record_unified_outcome
        await record_unified_outcome(db, business_id, action_id, finding_id=finding_id, commit=True)
    except Exception as exc:
        logger.warning("orchestration_learning_skip action=%s: %s", action_id, exc)

    try:
        from app.services.knowledge_graph import project_action_to_graph
        if row:
            payload = row.payload if isinstance(row.payload, dict) else (json.loads(row.payload) if row.payload else {})
            outcome = row.outcome_json if isinstance(row.outcome_json, dict) else (json.loads(row.outcome_json) if row.outcome_json else {})
            targets = []
            if payload.get("item_id"):
                targets.append({"type": "product", "id": str(payload["item_id"])})
            await project_action_to_graph(
                db, business_id, action_id, action_type=row.action_type, status=row.status,
                executed=bool(outcome.get("executed")) if isinstance(outcome, dict) else None,
                outcome=outcome, targets=targets,
                finding_id=str(finding_id) if finding_id else None,
            )
            await db.commit()
    except Exception as exc:
        logger.warning("orchestration_kg_projection_skip: %s", exc)
