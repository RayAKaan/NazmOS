"""Deterministic workflows — pure orchestration skeletons.

Each workflow function composes precheck → idempotency → apply → record
in a fixed, deterministic order.  No business logic lives here: every
side-effect is delegated to an activity.

These functions are the SAME code path whether executed by the local
deterministic runner (USE_TEMPORAL=False) or by the Temporal server
(USE_TEMPORAL=True).  Temporal replay determinism is guaranteed because
the function has no I/O beyond activity calls.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.orchestration.contracts import ExecutionRequest, ActionResult

logger = structlog.get_logger(__name__)

# Canonical workflow identifiers
WF_MANUAL_ACTION = "manual_action"
WF_AGENT_APPROVAL = "agent_approval"
WF_AGENT_REJECTION = "agent_rejection"
WF_SIMULATED = "simulated"

# Canonical mapping: workflow function name -> Temporal workflow type.
# The Temporal client and the worker MUST agree on these names. Local runners
# use the function reference; the Temporal substrate uses the type string.
WORKFLOW_TYPE_BY_FN_NAME = {
    "manual_action_workflow": WF_MANUAL_ACTION,
    "agent_approval_workflow": WF_AGENT_APPROVAL,
    "simulated_workflow": WF_SIMULATED,
}


async def manual_action_workflow(
    db: AsyncSession,
    req: ExecutionRequest,
) -> ActionResult:
    """Workflow for manual actions (actions.py / money_audit.py).

    Steps: precheck → idempotency → apply → record.
    """
    from app.orchestration.precheck import revalidate_capability, validate_action_constraints, record_constraint_block
    from app.orchestration.record import check_execution_idempotency, record_manual_action
    from app.orchestration.apply import apply_restock, apply_price_change, apply_discount, apply_alert_dismiss

    # 1. Capability revalidation
    if req.user_id is not None:
        if not await revalidate_capability(db, req.user_id, req.business_id):
            return ActionResult(
                success=False, action_id=None,
                message="User lacks can_approve_actions capability for this business.",
                error="INSUFFICIENT_CAPABILITY",
            )

    # 2. Owner-constraint / state guard
    # The guard needs the entity id in its payload to resolve the unit cost
    # (legacy executor always validated with payload={"item_id": entity_id}).
    verdict = await validate_action_constraints(
        db,
        business_id=req.business_id,
        action_type=req.action_type,
        payload={**req.payload, "item_id": str(req.entity_id)},
        previous_state=req.previous_state,
        new_state=req.new_state,
        actor_business_id=req.business_id,
    )
    if verdict.blocked:
        await record_constraint_block(
            db,
            business_id=req.business_id,
            action_type=req.action_type,
            reason_code=verdict.reason_code,
            reason=verdict.reason,
            payload=req.new_state,
            attempted_by=req.user_id,
        )
        return ActionResult(
            success=False, action_id=None,
            message=verdict.reason, error=verdict.reason,
        )

    # 3. Idempotency check
    existing = await check_execution_idempotency(db, req.execution_key, table="executed_actions")
    if existing:
        return ActionResult(
            success=True, action_id=None,
            message=f"Action already executed (replayed key={req.execution_key[:8]})",
        )

    # 4. Apply business mutation
    if req.action_type == "RESTOCK":
        outcome = await apply_restock(db, req.business_id, req.entity_id, req.new_state)
    elif req.action_type == "PRICE_CHANGE":
        outcome = await apply_price_change(db, req.business_id, req.entity_id, req.new_state)
    elif req.action_type == "DISCOUNT":
        outcome = await apply_discount(db, req.business_id, req.entity_id, req.new_state)
    elif req.action_type == "ALERT_DISMISS":
        outcome = await apply_alert_dismiss(db, req.entity_id)
    else:
        outcome = {"executed": False, "reason": f"Unknown action type: {req.action_type}"}

    # 5. Record outcome
    action_id = await record_manual_action(
        db,
        business_id=req.business_id,
        action_type=req.action_type,
        entity_type=req.entity_type,
        entity_id=req.entity_id,
        previous_state=req.previous_state,
        new_state=req.new_state,
        source=req.source,
        execution_key=req.execution_key,
        decision_id=req.decision_id,
        user_id=req.user_id,
        outcome=outcome,
    )
    await db.commit()

    if outcome.get("executed"):
        return ActionResult(success=True, action_id=action_id, message=outcome.get("message", "Executed"))
    else:
        return ActionResult(
            success=False, action_id=action_id,
            message=outcome.get("reason", "Execution failed"),
            error=outcome.get("reason"),
        )


async def agent_approval_workflow(
    db: AsyncSession,
    req: ExecutionRequest,
) -> dict[str, Any]:
    """Workflow for agent approvals (agent.py / whatsapp.py).

    Steps: record_approval → apply → record_terminal → record_learning.
    """
    from app.orchestration.record import (
        record_agent_approval, record_agent_terminal, record_terminal_outcome,
    )
    from app.orchestration.apply import apply_agent_action
    from app.utils.clock import utcnow

    # 1. Approve (pending_approval → approved → executing)
    approval = await record_agent_approval(
        db,
        action_id=req.action_id,
        note=req.note,
        decided_by=req.decided_by,
        business_id=req.business_id,
    )
    if not approval.get("ok"):
        return approval

    action_id = UUID(approval["action_id"])
    action_type = approval["action_type"]
    business_id = UUID(approval["business_id"])
    payload = approval["payload"]
    if isinstance(payload, str):
        import json
        payload = json.loads(payload)

    # 2. Move to executing status
    await db.execute(
        text("UPDATE agent_actions SET status='executing', updated_at=:now WHERE id=:id AND status='approved'"),
        {"id": str(action_id), "now": utcnow()},
    )

    # 3. Apply business mutation
    outcome = await apply_agent_action(db, business_id, action_id, action_type, payload)

    # 4. Record terminal status
    await record_agent_terminal(db, action_id=action_id, outcome=outcome)
    await db.commit()

    # 5. Best-effort learning + KG (after commit)
    await record_terminal_outcome(db, business_id, action_id)

    return {"ok": True, "action_id": str(action_id), "outcome": outcome}


async def simulated_workflow(
    db: AsyncSession,
    req: ExecutionRequest,
) -> dict[str, Any]:
    """Workflow for simulated executions (intelligence.py).

    Steps: apply_simulated → record_job.
    Does NOT mutate business data — preserves the ADR §7 invariant.
    """
    from app.orchestration.apply import apply_simulated_execution

    outcome = await apply_simulated_execution(
        db,
        req.business_id,
        req.action_type,
        req.entity_type,
        req.entity_id,
        req.payload,
    )
    await db.commit()
    return outcome
