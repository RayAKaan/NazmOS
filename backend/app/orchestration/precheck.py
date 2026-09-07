"""Pre-check activities — revalidate authz and action-state (no side effects).

These are the deterministic pre-flight activities that the workflow runs
BEFORE any business mutation. They call the existing NazmOS guard services
(execution_guard, capabilities_service) which remain canonical for
validation logic.
"""
from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

import structlog

logger = structlog.get_logger(__name__)


async def revalidate_capability(
    db: Any,
    user_id: UUID,
    business_id: UUID,
) -> bool:
    """Re-check that the attested actor still holds can_approve_actions.

    Must be called before any financial-state side effect. Returns True if
    the capability is held, False otherwise. Logs the denial for audit.
    """
    from app.services.capabilities_service import user_has_capability

    can_approve = await user_has_capability(db, user_id, business_id, "can_approve_actions")
    if not can_approve:
        logger.info(
            "orchestration_capability_denied",
            user_id=str(user_id),
            business_id=str(business_id),
        )
    return can_approve


async def validate_action_constraints(
    db: Any,
    *,
    business_id: UUID,
    action_type: str,
    payload: dict[str, Any],
    previous_state: dict[str, Any] | None = None,
    new_state: dict[str, Any] | None = None,
    actor_business_id: UUID | None = None,
) -> Any:
    """Run the owner-constraint / identity / permission guard.

    Returns the ExecutionVerdict from execution_guard. The caller should
    check ``verdict.blocked`` before proceeding.
    """
    from app.services.execution_guard import validate_action_for_execution

    return await validate_action_for_execution(
        db,
        business_id=business_id,
        action_type=action_type,
        payload=payload,
        previous_state=previous_state,
        new_state=new_state,
        actor_business_id=actor_business_id,
    )


async def record_constraint_block(
    db: Any,
    *,
    business_id: UUID,
    action_type: str,
    reason_code: str,
    reason: str,
    action_id: Optional[UUID] = None,
    payload: dict[str, Any] | None = None,
    attempted_by: Optional[UUID] = None,
) -> None:
    """Record a blocked execution attempt (best-effort, never raises)."""
    from app.services.execution_guard import record_constraint_block as _record

    await _record(
        db,
        business_id=business_id,
        action_type=action_type,
        reason_code=reason_code,
        reason=reason,
        action_id=action_id,
        payload=payload,
        attempted_by=attempted_by,
    )
