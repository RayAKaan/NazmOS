"""Manual-action read + reversal operations (ExecutedAction surface).

These thin operations replace the legacy ``ActionExecutor`` read/reversal
methods. They operate directly on the ``executed_actions`` table and are
idempotent (single-transition guards on reversal).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import ExecutedAction, Item, Inventory
from app.orchestration.contracts import ActionResult

logger = structlog.get_logger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def get_action_history(
    db: AsyncSession,
    business_id: UUID,
    entity_type: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> list[ExecutedAction]:
    query = select(ExecutedAction).where(ExecutedAction.business_id == business_id)
    if entity_type:
        query = query.where(ExecutedAction.entity_type == entity_type)
    if status:
        query = query.where(ExecutedAction.status == status)
    query = query.order_by(ExecutedAction.created_at.desc()).limit(limit).offset(offset)
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_pending_actions(db: AsyncSession, business_id: UUID) -> list[ExecutedAction]:
    result = await db.execute(
        select(ExecutedAction).where(
            ExecutedAction.business_id == business_id,
            ExecutedAction.status == "pending",
        ).order_by(ExecutedAction.created_at)
    )
    return list(result.scalars().all())


async def reverse_action(
    db: AsyncSession,
    action_id: UUID,
    user_id: UUID,
    reason: str,
) -> ActionResult:
    """Reverse a completed action (idempotent via is_reversed guard)."""
    action = await db.get(ExecutedAction, action_id)

    if not action:
        return ActionResult(success=False, action_id=action_id, message="Action not found",
                            error="Action not found")
    if action.is_reversed:
        return ActionResult(success=False, action_id=action_id, message="Action already reversed",
                            error="Already reversed")
    if not action.is_reversible:
        return ActionResult(success=False, action_id=action_id, message="Action is not reversible",
                            error="Not reversible")

    try:
        if action.action_type == "RESTOCK":
            await _reverse_restock(db, action.business_id, action.entity_id, action.previous_state)
        elif action.action_type == "PRICE_CHANGE":
            await _reverse_price_change(db, action.business_id, action.entity_id, action.previous_state)

        action.is_reversed = True
        action.reversed_at = _now()
        action.reversed_by = user_id
        action.reversal_reason = reason

        await db.commit()

        logger.info("orchestration_action_reversed",
                    action_id=str(action_id), reversed_by=str(user_id), reason=reason)
        return ActionResult(success=True, action_id=action_id, message="Action reversed successfully")
    except Exception as e:
        logger.exception("orchestration_action_reversal_failed", action_id=str(action_id), error=str(e))
        return ActionResult(success=False, action_id=action_id, message=str(e), error=str(e))


async def _reverse_restock(db: AsyncSession, business_id: UUID, item_id: UUID, previous_state: dict) -> None:
    inv_result = await db.execute(
        select(Inventory).where(Inventory.business_id == business_id, Inventory.item_id == item_id)
    )
    inv = inv_result.scalar_one_or_none()
    if inv:
        inv.current_stock = previous_state.get("current_stock", inv.current_stock)


async def _reverse_price_change(db: AsyncSession, business_id: UUID, item_id: UUID, previous_state: dict) -> None:
    item = await db.get(Item, item_id)
    if item:
        item.sell_price = previous_state.get("sell_price", item.sell_price)
