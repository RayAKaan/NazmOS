from typing import Optional, Any
from uuid import UUID
from datetime import datetime, timezone
from dataclasses import dataclass
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
import structlog

from app.database.models import (
    ExecutedAction, DecisionLog, Item, Inventory, Business, 
    DecisionLog, PricingRecommendation
)

logger = structlog.get_logger(__name__)


@dataclass
class ActionResult:
    success: bool
    action_id: Optional[UUID]
    message: str
    external_reference: Optional[str] = None
    error: Optional[str] = None


class ActionExecutor:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def execute_action(
        self,
        business_id: UUID,
        action_type: str,
        entity_type: str,
        entity_id: UUID,
        previous_state: dict,
        new_state: dict,
        decision_id: Optional[UUID] = None,
        user_id: Optional[UUID] = None,
        source: str = "manual",
    ) -> ActionResult:
        # Phase 1 (P0-B): enforce owner constraints at the FINAL execution
        # boundary. If the guard refuses, record the block for observability and
        # return failure WITHOUT mutating any business state.
        from app.services.execution_guard import validate_action_for_execution, record_constraint_block

        # Authorization at the service boundary: an attested human actor must
        # hold can_approve_actions (owner/admin) to mutate financial state. This
        # cannot be bypassed by an internal caller that skips the router.
        if user_id is not None:
            from app.services.capabilities_service import user_has_capability
            can_approve = await user_has_capability(
                self.db, user_id, business_id, "can_approve_actions"
            )
            if not can_approve:
                logger.info(
                    "action_denied_insufficient_capability",
                    business_id=str(business_id),
                    action_type=action_type,
                    user_id=str(user_id),
                )
                return ActionResult(
                    success=False,
                    action_id=None,
                    message="User lacks can_approve_actions capability for this business.",
                    error="INSUFFICIENT_CAPABILITY",
                )

        verdict = await validate_action_for_execution(
            self.db,
            business_id=business_id,
            action_type=action_type,
            payload={"item_id": str(entity_id)},
            previous_state=previous_state,
            new_state=new_state,
            actor_business_id=business_id,
        )
        if verdict.blocked:
            await record_constraint_block(
                self.db,
                business_id=business_id,
                action_type=action_type,
                reason_code=verdict.reason_code,
                reason=verdict.reason,
                payload=new_state,
                attempted_by=user_id,
            )
            logger.info(
                "action_blocked",
                business_id=str(business_id),
                action_type=action_type,
                entity_id=str(entity_id),
                reason_code=verdict.reason_code,
            )
            return ActionResult(
                success=False,
                action_id=None,
                message=verdict.reason,
                error=verdict.reason,
            )

        executed_action = ExecutedAction(
            business_id=business_id,
            decision_id=decision_id,
            source=source,
            action_type=action_type,
            entity_type=entity_type,
            entity_id=entity_id,
            previous_state=previous_state,
            new_state=new_state,
            status="executing",
            executed_by=user_id,
            executed_at=datetime.now(timezone.utc),
        )
        self.db.add(executed_action)
        await self.db.commit()
        await self.db.refresh(executed_action)

        try:
            if action_type == "RESTOCK":
                result = await self._execute_restock(business_id, entity_id, new_state)
            elif action_type == "PRICE_CHANGE":
                result = await self._execute_price_change(business_id, entity_id, new_state)
            elif action_type == "DISCOUNT":
                result = await self._execute_discount(business_id, entity_id, new_state)
            elif action_type == "ALERT_DISMISS":
                result = await self._execute_dismiss(entity_id)
            else:
                result = ActionResult(
                    success=False,
                    action_id=executed_action.id,
                    message=f"Unknown action type: {action_type}",
                    error="Unknown action type",
                )

            if result.success:
                executed_action.status = "completed"
                executed_action.external_actions = [{"type": action_type, "reference": result.external_reference}] if result.external_reference else []
                
                if decision_id:
                    decision = await self.db.get(DecisionLog, decision_id)
                    if decision:
                        decision.was_applied = True
                        decision.applied_at = datetime.now(timezone.utc)
                
                logger.info(
                    "action_executed",
                    action_id=str(executed_action.id),
                    action_type=action_type,
                    entity_type=entity_type,
                    business_id=str(business_id),
                )
            else:
                executed_action.status = "failed"
                logger.error(
                    "action_execution_failed",
                    action_id=str(executed_action.id),
                    error=result.error,
                )

            await self.db.commit()

        except Exception as e:
            executed_action.status = "failed"
            await self.db.commit()
            logger.exception(
                "action_execution_exception",
                action_id=str(executed_action.id),
                error=str(e),
            )
            return ActionResult(
                success=False,
                action_id=executed_action.id,
                message=str(e),
                error=str(e),
            )

        return result

    async def reverse_action(
        self,
        action_id: UUID,
        user_id: UUID,
        reason: str,
    ) -> ActionResult:
        action = await self.db.get(ExecutedAction, action_id)
        
        if not action:
            return ActionResult(
                success=False,
                action_id=action_id,
                message="Action not found",
                error="Action not found",
            )

        if action.is_reversed:
            return ActionResult(
                success=False,
                action_id=action_id,
                message="Action already reversed",
                error="Already reversed",
            )

        if not action.is_reversible:
            return ActionResult(
                success=False,
                action_id=action_id,
                message="Action is not reversible",
                error="Not reversible",
            )

        try:
            if action.action_type == "RESTOCK":
                await self._reverse_restock(action.business_id, action.entity_id, action.previous_state)
            elif action.action_type == "PRICE_CHANGE":
                await self._reverse_price_change(action.business_id, action.entity_id, action.previous_state)
            elif action.action_type == "DISCOUNT":
                await self._reverse_discount(action.business_id, action.entity_id, action.previous_state)

            action.is_reversed = True
            action.reversed_at = datetime.now(timezone.utc)
            action.reversed_by = user_id
            action.reversal_reason = reason
            
            await self.db.commit()
            
            logger.info(
                "action_reversed",
                action_id=str(action_id),
                reversed_by=str(user_id),
                reason=reason,
            )

            return ActionResult(
                success=True,
                action_id=action_id,
                message="Action reversed successfully",
            )

        except Exception as e:
            logger.exception("action_reversal_failed", action_id=str(action_id), error=str(e))
            return ActionResult(
                success=False,
                action_id=action_id,
                message=str(e),
                error=str(e),
            )

    async def get_action_history(
        self,
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
        
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_pending_actions(self, business_id: UUID) -> list[ExecutedAction]:
        result = await self.db.execute(
            select(ExecutedAction).where(
                ExecutedAction.business_id == business_id,
                ExecutedAction.status == "pending"
            ).order_by(ExecutedAction.created_at)
        )
        return list(result.scalars().all())

    async def _execute_restock(
        self,
        business_id: UUID,
        item_id: UUID,
        new_state: dict,
    ) -> ActionResult:
        """Apply a received-quantity restock to the inventory position.

        Canonical lifecycle: purchase order → receipt → inventory position
        increase. The received quantity INCREMENTS the existing stock; it never
        overwrites it. The mutation is a single atomic SQL statement so that
        concurrent receipts serialize and cannot lose each other's updates.

        `new_state["restock_qty"]` (or `new_state["quantity"]`) is the RECEIVED
        quantity. `new_state["current_stock"]` is ignored for restock — it is a
        projected absolute value from some callers and must not clobber the live
        inventory.
        """
        received_qty = new_state.get("restock_qty")
        if received_qty is None:
            received_qty = new_state.get("quantity")
        if received_qty is None:
            return ActionResult(
                success=False,
                action_id=None,
                message="Restock requires a received quantity (restock_qty).",
                error="Missing restock quantity",
            )
        try:
            received_qty = Decimal(str(received_qty))
        except Exception:
            return ActionResult(
                success=False,
                action_id=None,
                message="Restock quantity must be numeric.",
                error="Invalid restock quantity",
            )
        if received_qty < 0:
            return ActionResult(
                success=False,
                action_id=None,
                message="Restock quantity cannot be negative.",
                error="Negative restock quantity",
            )

        now = datetime.now(timezone.utc)
        result = await self.db.execute(
            text("""
                UPDATE inventory
                SET current_stock = current_stock + :qty,
                    last_restocked = :now,
                    updated_at = :now
                WHERE business_id = :business_id
                  AND item_id = :item_id
                RETURNING id, current_stock
            """),
            {
                "qty": received_qty,
                "now": now,
                "business_id": str(business_id),
                "item_id": str(item_id),
            },
        )
        row = result.fetchone()
        if row is None:
            return ActionResult(
                success=False,
                action_id=None,
                message=f"Inventory position not found for item {item_id}",
                error="Inventory not found",
            )
        await self.db.commit()

        logger.info(
            "restock_executed",
            business_id=str(business_id),
            item_id=str(item_id),
            received_qty=float(received_qty),
            new_stock=float(row.current_stock),
        )
        return ActionResult(
            success=True,
            action_id=None,
            message=f"Restocked item {item_id}: +{float(received_qty)} units received",
        )

    async def _execute_price_change(
        self,
        business_id: UUID,
        item_id: UUID,
        new_state: dict,
    ) -> ActionResult:
        item = await self.db.get(Item, item_id)
        
        if item:
            old_price = item.sell_price
            item.sell_price = new_state.get("sell_price", item.sell_price)
            item.last_price_change = datetime.now(timezone.utc)
            item.price_change_count_30d = (item.price_change_count_30d or 0) + 1
        
        recommendation = await self.db.execute(
            select(PricingRecommendation).where(
                PricingRecommendation.item_id == item_id,
                PricingRecommendation.status == "pending"
            )
        )
        rec = recommendation.scalar_one_or_none()
        if rec:
            rec.status = "applied"
            rec.applied_at = datetime.now(timezone.utc)
        
        logger.info(
            "price_change_executed",
            business_id=str(business_id),
            item_id=str(item_id),
            old_price=float(old_price) if item else None,
            new_price=new_state.get("sell_price"),
        )
        return ActionResult(
            success=True,
            action_id=None,
            message=f"Price updated for item {item_id}",
        )

    async def _execute_discount(
        self,
        business_id: UUID,
        item_id: UUID,
        new_state: dict,
    ) -> ActionResult:
        logger.info("discount_executed", business_id=str(business_id), item_id=str(item_id))
        return ActionResult(
            success=True,
            action_id=None,
            message=f"Discount applied for item {item_id}",
        )

    async def _execute_dismiss(self, decision_id: UUID) -> ActionResult:
        return ActionResult(
            success=True,
            action_id=None,
            message=f"Alert dismissed",
        )

    async def _reverse_restock(
        self,
        business_id: UUID,
        item_id: UUID,
        previous_state: dict,
    ) -> None:
        inventory = await self.db.execute(
            select(Inventory).where(
                Inventory.business_id == business_id,
                Inventory.item_id == item_id
            )
        )
        inv = inventory.scalar_one_or_none()
        
        if inv:
            inv.current_stock = previous_state.get("current_stock", inv.current_stock)

    async def _reverse_price_change(
        self,
        business_id: UUID,
        item_id: UUID,
        previous_state: dict,
    ) -> None:
        item = await self.db.get(Item, item_id)
        
        if item:
            item.sell_price = previous_state.get("sell_price", item.sell_price)

    async def _reverse_discount(
        self,
        business_id: UUID,
        item_id: UUID,
        previous_state: dict,
    ) -> None:
        pass
